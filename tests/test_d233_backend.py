from __future__ import annotations

import hashlib
import json
import os
import ssl
import tempfile
import unittest
from pathlib import Path

from src.goodix5125_d232_offline import (
    AbortClass,
    ContractError,
    DurableReportPublisher,
    PreflightSnapshot,
    ProtectedFilePolicy,
    ReplayAbort,
    SecretBuffer,
    SyntheticResponseBodies,
    TargetMaterial,
    _config90_finalizer,
    _load_target_material,
    build_a0,
    build_b0,
    happy_synthetic_script,
)
from src.goodix5125_d233_backend import (
    B0TlsBridge,
    D233LiveUnavailable,
    LibusbSystemApi,
    ProductionOsPreflight,
    ProductionReplayBackend,
    ProductionUsbTransport,
    RuntimePskE4Binder,
    Tls12PskServer,
    USB_EP_IN,
    USB_EP_OUT,
    USB_INTERFACE,
    UsbAmbiguousCompletion,
    UsbFailure,
    UsbIdentity,
    UsbTimeout,
    d233_offline_entrypoint,
    request_live_mode,
    run_reviewed_backend_offline,
)


def synthetic_validator(secret: memoryview) -> bytes:
    return hashlib.sha256(b"D233 synthetic validator\0" + bytes(secret)).digest()


def client_hello_placeholder() -> bytes:
    random = bytes((13 * index + 1) & 0xFF for index in range(32))
    body = b"\x03\x03" + random + b"\x00\x00\x02\x00\xa8\x01\x00"
    handshake = b"\x01" + len(body).to_bytes(3, "big") + body
    return b"\x16\x03\x03" + len(handshake).to_bytes(2, "big") + handshake


def synthetic_objects(secret_bytes: bytes = bytes(range(1, 33))):
    config = bytearray((17 * index + 3) & 0xFF for index in range(224))
    dac = []
    for register, value, offset in (
        (0x0220, b"\xd8\x0b", 117),
        (0x0236, b"\xbe\x00", 121),
        (0x0238, b"\xbd\x00", 125),
        (0x023A, b"\xbc\x00", 129),
    ):
        config[offset : offset + 4] = register.to_bytes(2, "little") + value
        dac.append((register, value, offset))
    config[-2:] = _config90_finalizer(bytes(config))
    responses = SyntheticResponseBodies(
        e4_validator=synthetic_validator(memoryview(secret_bytes)),
        a2_irq=b"\x12\x34\x56",
        chip82=b"\x01\x25\x09\x41",
        otp_a6=bytes((9 * index + 11) & 0xFF for index in range(64)),
        tls_client_hello_record=client_hello_placeholder(),
    )
    material = TargetMaterial(
        e4_validator_sha256=hashlib.sha256(responses.e4_validator).hexdigest(),
        a2_response_sha256=hashlib.sha256(responses.a2_irq).hexdigest(),
        chip82_response_sha256=hashlib.sha256(responses.chip82).hexdigest(),
        otp_a6_response_sha256=hashlib.sha256(responses.otp_a6).hexdigest(),
        dac=tuple(dac),
        config90=bytes(config),
        config90_sha256=hashlib.sha256(config).hexdigest(),
    )
    return material, responses


def preflight(**changes):
    values = dict(
        euid=0,
        sudo_uid=1000,
        operator_uid=1000,
        single_use_marker_absent=True,
        process_count=1,
        thread_count=1,
        external_holder_count=0,
        fprintd_state_captured=True,
        usb_identity_expected=True,
        vid=0x27C6,
        pid=0x5125,
        serial_or_path_stable=True,
        signals_blocked_before_transport=True,
        report_path_ready=True,
        restore_plan_present=True,
    )
    values.update(changes)
    return PreflightSnapshot(**values)


class FakeUsbApi:
    def __init__(self, incoming=(), *, identity=None):
        self.incoming = [bytearray(item) for item in incoming]
        self.current_identity = identity or UsbIdentity(0x27C6, 0x5125, 1, 4, (2, 3))
        self.identities = []
        self.open_result = object()
        self.partial_out = False
        self.timeout_out = False
        self.timeout_in = False
        self.claim_fails = False
        self.calls = []
        self.outgoing = []

    def init(self):
        self.calls.append("init")
        return object()

    def open_exact(self, context, vid, pid):
        self.calls.append(("open", vid, pid))
        return self.open_result

    def identity(self, handle):
        self.calls.append("identity")
        return self.identities.pop(0) if self.identities else self.current_identity

    def claim_interface(self, handle, interface):
        self.calls.append(("claim", interface))
        if self.claim_fails:
            raise UsbFailure("claim")

    def bulk_out(self, handle, endpoint, data, timeout_ms):
        self.calls.append(("out", endpoint, timeout_ms))
        if self.timeout_out:
            raise UsbTimeout("out")
        self.outgoing.append(bytes(data))
        return len(data) - 1 if self.partial_out else len(data)

    def bulk_in(self, handle, endpoint, maximum, timeout_ms):
        self.calls.append(("in", endpoint, timeout_ms))
        if self.timeout_in:
            raise UsbTimeout("in")
        if not self.incoming:
            return b""
        item = self.incoming[0]
        result = bytes(item[:maximum])
        del item[:maximum]
        if not item:
            self.incoming.pop(0)
        return result

    def release_interface(self, handle, interface):
        self.calls.append(("release", interface))

    def close(self, handle):
        self.calls.append("close")

    def exit(self, context):
        self.calls.append("exit")


class ImmediateTlsEngine:
    def __init__(self, secret):
        self.complete = False
        self.closed = False
        self.feed_count = 0

    def feed(self, payload):
        self.feed_count += 1

    def advance(self):
        self.complete = True

    def drain(self):
        return ()

    def close(self):
        self.closed = True


class D233UsbBackendTests(unittest.TestCase):
    def test_real_libusb_api_is_sealed_before_init(self):
        api = LibusbSystemApi()
        with self.assertRaises(D233LiveUnavailable):
            api.init()

    def test_open_claim_identity_chunking_partial_read_and_cleanup_once(self):
        frame = build_a0(0x82, b"abcd")
        api = FakeUsbApi((frame[:2], frame[2:5], frame[5:]))
        transport = ProductionUsbTransport(api, expected_identity=api.current_identity)
        transport.transport_open()
        transport.write_frame(b"x" * 130, 1000)
        self.assertEqual([len(item) for item in api.outgoing], [64, 64, 2])
        self.assertEqual(transport.read_frame(1000), frame)
        transport.cleanup()
        transport.cleanup()
        self.assertEqual(transport.release_count, 1)
        self.assertEqual(transport.close_count, 1)
        self.assertEqual(transport.exit_count, 1)
        self.assertIn(("claim", USB_INTERFACE), api.calls)
        self.assertTrue(all(call[1] == USB_EP_OUT for call in api.calls if isinstance(call, tuple) and call[0] == "out"))
        self.assertTrue(all(call[1] == USB_EP_IN for call in api.calls if isinstance(call, tuple) and call[0] == "in"))

    def test_open_claim_wrong_identity_partial_out_timeout_and_malformed_fail_closed(self):
        cases = []
        api = FakeUsbApi(); api.open_result = None; cases.append((api, "open"))
        api = FakeUsbApi(); api.claim_fails = True; cases.append((api, "claim"))
        api = FakeUsbApi(identity=UsbIdentity(0x1234, 0x5125, 1, 4, (2,))); cases.append((api, "identity"))
        for api, name in cases:
            with self.subTest(name=name):
                transport = ProductionUsbTransport(api)
                with self.assertRaises(UsbFailure):
                    transport.transport_open()
                transport.cleanup()
                self.assertLessEqual(transport.release_count, 1)
                self.assertLessEqual(transport.close_count, 1)
                self.assertEqual(transport.exit_count, 1)

        api = FakeUsbApi(); transport = ProductionUsbTransport(api); transport.transport_open()
        api.partial_out = True
        with self.assertRaises(UsbAmbiguousCompletion):
            transport.write_frame(b"abc", 1000)
        transport.cleanup()

        api = FakeUsbApi(); transport = ProductionUsbTransport(api); transport.transport_open(); api.timeout_out = True
        with self.assertRaises(UsbTimeout):
            transport.write_frame(b"abc", 1000)
        transport.cleanup()

        api = FakeUsbApi((b"\xa0\x01\x00\x00x",)); transport = ProductionUsbTransport(api); transport.transport_open()
        with self.assertRaises(UsbFailure):
            transport.read_frame(1000)
        transport.cleanup()

    def test_unexpected_reenumeration_stops(self):
        original = UsbIdentity(0x27C6, 0x5125, 1, 4, (2, 3))
        changed = UsbIdentity(0x27C6, 0x5125, 1, 5, (2, 3))
        api = FakeUsbApi(identity=original)
        transport = ProductionUsbTransport(api)
        transport.transport_open()
        api.current_identity = changed
        with self.assertRaises(UsbFailure):
            transport.revalidate_identity()
        transport.cleanup()


class D233BindingAndStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="d233-")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def _run(self, secret_bytes=bytes(range(1, 33))):
        material, responses = synthetic_objects()
        script = happy_synthetic_script(material, responses)
        incoming = [frame for step in script for frame in step.responses]
        api = FakeUsbApi(incoming)
        secret = SecretBuffer.synthetic(secret_bytes)
        backend = ProductionReplayBackend(
            ProductionUsbTransport(api),
            secret,
            RuntimePskE4Binder(synthetic_validator),
            tls_factory=ImmediateTlsEngine,
        )
        report = run_reviewed_backend_offline(
            preflight=preflight(),
            material=material,
            secret=secret,
            backend=backend,
            publisher=DurableReportPublisher(self.root / ("result-" + secret_bytes.hex()[:4] + ".json")),
        )
        return report, backend, api

    def test_happy_path_uses_unchanged_state_machine(self):
        report, backend, _ = self._run()
        self.assertEqual(report["result"], "pass")
        self.assertEqual(report["command_count"], 12)
        self.assertEqual(report["tls_handshake_count"], 1)
        self.assertEqual(report["usb_open_count"], 1)
        self.assertEqual(report["cleanup_count"], 1)
        self.assertTrue(report["secret_zeroized"])
        self.assertEqual(backend.binder.compare_count, 1)

    def test_one_bit_psk_mutation_stops_after_e4_before_a2(self):
        mutated = bytearray(range(1, 33)); mutated[0] ^= 1
        report, backend, api = self._run(bytes(mutated))
        self.assertEqual(report["terminal_state"], "STOP")
        self.assertEqual(report["abort_class"], AbortClass.SECRET_BOUNDARY.value)
        self.assertEqual(report["command_count"], 1)
        self.assertEqual(backend.tls_handshake_count, 0)
        self.assertEqual(len(api.outgoing), 1)

    def test_d4_and_reordering_are_not_representable(self):
        material, _ = synthetic_objects()
        secret = SecretBuffer.synthetic(bytes(range(1, 33)))
        backend = ProductionReplayBackend(
            ProductionUsbTransport(FakeUsbApi()), secret, RuntimePskE4Binder(synthetic_validator), tls_factory=ImmediateTlsEngine
        )
        with self.assertRaises(ReplayAbort):
            backend.exchange("D4", build_a0(0x82, b""), 1000)
        for control in (0xD4, 0xE0, 0xA4, 0xF0, 0xF4):
            with self.subTest(control=hex(control)), self.assertRaises(ContractError):
                build_a0(control, b"")
        secret.close()

    def test_config90_boundary_length_hash_finalizer_dac_and_manifest(self):
        material, _ = synthetic_objects()
        root = self.root / "material"; root.mkdir()
        config = root / "config.bin"; config.write_bytes(material.config90); config.chmod(0o600)
        manifest_data = {
            "schema": "d232-target-material-v1",
            "e4": {"validator_sha256": material.e4_validator_sha256},
            "a2": {"response_body_sha256": material.a2_response_sha256},
            "chip82": {"response_body_sha256": material.chip82_response_sha256},
            "otp_a6": {"response_body_sha256": material.otp_a6_response_sha256},
            "dac": [
                {"order": index, "register": hex(reg), "value_le_hex": value.hex(), "config_tuple_offset": offset}
                for index, (reg, value, offset) in enumerate(material.dac, 1)
            ],
            "config90": {"body_length": 224, "body_sha256": material.config90_sha256},
        }
        manifest = root / "manifest.json"; manifest.write_text(json.dumps(manifest_data, sort_keys=True)); manifest.chmod(0o600)
        policy = ProtectedFilePolicy(owner_uid=os.getuid(), mode=0o600)
        digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
        self.assertEqual(_load_target_material(manifest, config, expected_manifest_sha256=digest, file_policy=policy), material)
        variants = (
            ("length", material.config90[:-1]),
            ("hash", b"x" * 224),
            ("finalizer", material.config90[:-2] + b"\x00\x00"),
        )
        for name, value in variants:
            with self.subTest(name=name):
                config.write_bytes(value)
                with self.assertRaises(ContractError):
                    _load_target_material(manifest, config, expected_manifest_sha256=digest, file_policy=policy)
        config.write_bytes(material.config90)
        bad_manifest = dict(manifest_data); bad_manifest["dac"] = list(reversed(manifest_data["dac"]))
        manifest.write_text(json.dumps(bad_manifest, sort_keys=True))
        bad_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
        with self.assertRaises(ContractError):
            _load_target_material(manifest, config, expected_manifest_sha256=bad_digest, file_policy=policy)
        with self.assertRaises(ContractError):
            _load_target_material(manifest, config, expected_manifest_sha256="0" * 64, file_policy=policy)


class D233TlsTests(unittest.TestCase):
    @staticmethod
    def _client(secret: bytes, identity="Client_identity", *, minimum=ssl.TLSVersion.TLSv1_2, maximum=ssl.TLSVersion.TLSv1_2, cipher="PSK-AES128-GCM-SHA256"):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.minimum_version = minimum
        context.maximum_version = maximum
        context.set_ciphers(cipher)
        context.options |= ssl.OP_NO_TICKET
        context.set_psk_client_callback(lambda _hint: (identity, secret))
        incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
        return context.wrap_bio(incoming, outgoing, server_side=False), incoming, outgoing

    @staticmethod
    def _drive(engine, client, client_in, client_out, *, fragment=7):
        client_done = False
        for _ in range(100):
            try:
                client.do_handshake(); client_done = True
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                pass
            wire = client_out.read()
            for offset in range(0, len(wire), fragment):
                engine.feed(wire[offset : offset + fragment])
                engine.advance()
                for record in engine.drain():
                    client_in.write(record)
            if client_done and engine.complete:
                return
        raise AssertionError("loopback handshake did not converge")

    def test_real_tls12_psk_00a8_loopback_fragmented_and_no_second_handshake(self):
        secret_bytes = bytes(range(1, 33))
        secret = SecretBuffer.synthetic(secret_bytes)
        engine = Tls12PskServer(secret)
        client, client_in, client_out = self._client(secret_bytes)
        self._drive(engine, client, client_in, client_out)
        self.assertTrue(engine.complete)
        self.assertEqual(engine.handshake_count, 1)
        with self.assertRaises(ReplayAbort):
            engine.advance()
        engine.close(); secret.close()
        self.assertTrue(engine.is_zeroized)

    def test_wrong_identity_suite_and_version_fail(self):
        cases = (
            ("identity", dict(identity="wrong")),
            ("suite", dict(cipher="PSK-AES256-GCM-SHA384")),
            ("version", dict(minimum=ssl.TLSVersion.TLSv1_3, maximum=ssl.TLSVersion.TLSv1_3)),
        )
        for name, kwargs in cases:
            with self.subTest(name=name):
                secret_bytes = bytes(range(1, 33)); secret = SecretBuffer.synthetic(secret_bytes); engine = Tls12PskServer(secret)
                client, client_in, client_out = self._client(secret_bytes, **kwargs)
                with self.assertRaises((ReplayAbort, ssl.SSLError, AssertionError)):
                    self._drive(engine, client, client_in, client_out)
                engine.close(); secret.close()

    def test_alert_and_malformed_record_are_terminal(self):
        for record in (b"\x15\x03\x03\x00\x02\x02\x28", b"\x16\x03\x03\x00\x04bad!"):
            secret = SecretBuffer.synthetic(bytes(range(1, 33))); engine = Tls12PskServer(secret)
            engine.feed(record)
            with self.assertRaises(ReplayAbort):
                engine.advance()
            engine.close(); secret.close()

    def test_corrupted_encrypted_finished_is_bad_record_mac(self):
        secret_bytes = bytes(range(1, 33))
        secret = SecretBuffer.synthetic(secret_bytes)
        engine = Tls12PskServer(secret)
        client, client_in, client_out = self._client(secret_bytes)
        with self.assertRaises(ssl.SSLWantReadError):
            client.do_handshake()
        engine.feed(client_out.read())
        engine.advance()
        client_in.write(b"".join(engine.drain()))
        with self.assertRaises(ssl.SSLWantReadError):
            client.do_handshake()
        corrupted = bytearray(client_out.read())
        corrupted[-1] ^= 1
        engine.feed(corrupted)
        with self.assertRaises(ReplayAbort) as caught:
            engine.advance()
        self.assertEqual(caught.exception.abort_class, AbortClass.BAD_RECORD_MAC)
        engine.close(); secret.close()

    def test_b0_bridge_preserves_fragmented_input_and_multiple_output_records(self):
        records = (b"\x16\x03\x03\x00\x01a", b"\x14\x03\x03\x00\x01b")

        class Engine:
            complete = False
            def __init__(self): self.input = bytearray(); self.once = False
            def feed(self, value): self.input.extend(value)
            def advance(self): pass
            def drain(self):
                if self.once: return ()
                self.once = True
                return records

        class Transport:
            def __init__(self): self.frames = []
            def write_frame(self, frame, timeout): self.frames.append(frame)

        engine, transport = Engine(), Transport()
        bridge = B0TlsBridge(engine, transport)
        bridge.accept_b0(build_b0(b"first-"), 1000)
        bridge.accept_b0(build_b0(b"fragment"), 1000)
        self.assertEqual(bytes(engine.input), b"first-fragment")
        from src.goodix5125_d232_offline import parse_b0
        self.assertEqual(tuple(parse_b0(frame) for frame in transport.frames), records)


class FakeOsFacade:
    def __init__(self):
        self.root = 0; self.sudo = 1000; self.processes = 1; self.threads = 1; self.holders = (); self.active = True; self.calls = []
    def euid(self): return self.root
    def sudo_uid(self): return self.sudo
    def process_count(self): return self.processes
    def thread_count(self): return self.threads
    def external_holders(self, path): return self.holders
    def fprintd_active(self): self.calls.append("capture"); return self.active
    def stop_fprintd(self): self.calls.append("stop")
    def start_fprintd(self): self.calls.append("start")
    def block_signals(self, signals): self.calls.append("block"); return "old"
    def restore_signals(self, previous): self.calls.append(("restore", previous))
    def claim_single_use_marker(self, path): self.calls.append("marker")
    def report_path_ready(self, path): return True


class D233OsAndHardDisableTests(unittest.TestCase):
    def test_os_preflight_restore_exact_prior_state_and_holder_abort(self):
        with tempfile.TemporaryDirectory(prefix="d233-os-") as directory:
            root = Path(directory); facade = FakeOsFacade()
            preflight_tx = ProductionOsPreflight(
                facade, operator_uid=1000, device_path=Path("/dev/bus/usb/001/004"), marker=root / "marker", report=(root / "report.json").absolute()
            )
            snapshot = preflight_tx.prepare()
            self.assertTrue(snapshot.signals_blocked_before_transport)
            preflight_tx.restore(); preflight_tx.restore()
            self.assertEqual(facade.calls, ["marker", "capture", "block", "stop", "start", ("restore", "old")])
            facade = FakeOsFacade(); facade.holders = (42,)
            with self.assertRaises(ReplayAbort):
                ProductionOsPreflight(facade, operator_uid=1000, device_path=Path("/dev/x"), marker=root / "m", report=(root / "r").absolute()).prepare()
            self.assertNotIn("stop", facade.calls)

    def test_all_runtime_enablement_attempts_keep_usb_open_zero(self):
        self.assertEqual(d233_offline_entrypoint()["usb_open_count"], 0)
        cases = (
            (("--live",), {}, None, None),
            ((), {"LIVE": "1"}, None, None),
            ((), {}, {"live": True}, None),
            ((), {}, None, "libusb"),
        )
        for argv, env, config, backend in cases:
            with self.subTest(argv=argv, env=env, config=config, backend=backend):
                with self.assertRaises(D233LiveUnavailable):
                    d233_offline_entrypoint(argv, env, config, backend)
        with self.assertRaises(D233LiveUnavailable):
            request_live_mode()


if __name__ == "__main__":
    unittest.main()
