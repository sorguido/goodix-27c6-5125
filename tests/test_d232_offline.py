from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from src.goodix5125_d232_offline import (
    AbortClass,
    ContractError,
    D232_LIVE_CAPABILITY,
    DurableReportPublisher,
    EXACT_PHASE_ORDER,
    ExactOemReplayStateMachine,
    LiveCapabilityUnavailable,
    PreflightSnapshot,
    ProtectedFilePolicy,
    ScriptedSyntheticBackend,
    SecretBuffer,
    SyntheticResponseBodies,
    TargetMaterial,
    _config90_finalizer,
    _load_target_material,
    _read_exact_protected,
    build_a0,
    build_b0,
    d232_offline_entrypoint,
    happy_synthetic_script,
    parse_a0,
    parse_b0,
    request_live_mode,
    run_synthetic_from_protected_paths,
)


FIXTURE = Path(__file__).parent / "fixtures" / "d232_synthetic_oracle.json"


def _client_hello() -> bytes:
    random = bytes((13 * index + 1) & 0xFF for index in range(32))
    body = b"\x03\x03" + random + b"\x00\x00\x02\x00\xa8\x01\x00"
    handshake = b"\x01" + len(body).to_bytes(3, "big") + body
    return b"\x16\x03\x03" + len(handshake).to_bytes(2, "big") + handshake


def _synthetic_objects() -> tuple[TargetMaterial, SyntheticResponseBodies]:
    spec = json.loads(FIXTURE.read_text())
    config = bytearray((17 * index + 3) & 0xFF for index in range(224))
    dac = []
    for row in spec["config_recipe"]["dac"]:
        register = int(row["register"], 0)
        value = bytes.fromhex(row["value_le_hex"])
        offset = row["config_tuple_offset"]
        config[offset:offset + 4] = register.to_bytes(2, "little") + value
        dac.append((register, value, offset))
    config[-2:] = _config90_finalizer(bytes(config))
    responses = SyntheticResponseBodies(
        e4_validator=bytes((5 * index + 7) & 0xFF for index in range(32)),
        a2_irq=bytes.fromhex(spec["response_recipes"]["a2_irq_hex"]),
        chip82=bytes.fromhex(spec["response_recipes"]["chip82_hex"]),
        otp_a6=bytes((9 * index + 11) & 0xFF for index in range(64)),
        tls_client_hello_record=_client_hello(),
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


def _preflight(**changes: object) -> PreflightSnapshot:
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


class D232OfflineTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory(prefix="d232-tests-")
        self.tmp_path = Path(self._temporary.name)

    def tearDown(self):
        self._temporary.cleanup()

    def _run(self, path, script=None, *, tls_outcome="ok", material=None, preflight=None):
        base_material, responses = _synthetic_objects()
        selected_material = base_material if material is None else material
        selected_script = happy_synthetic_script(base_material, responses) if script is None else script
        backend = ScriptedSyntheticBackend(selected_script, tls_outcome=tls_outcome)
        secret = SecretBuffer.synthetic(bytes(range(1, 33)))
        report_path = path / "result.json"
        publisher = DurableReportPublisher(report_path)
        report = ExactOemReplayStateMachine().run(
            preflight=_preflight() if preflight is None else preflight,
            material=selected_material,
            secret=secret,
            backend=backend,
            publisher=publisher,
        )
        self.assertTrue(report_path.exists())
        self.assertEqual(stat.S_IMODE(report_path.stat().st_mode), 0o600)
        self.assertEqual(json.loads(report_path.read_text()), report)
        serialized = report_path.read_bytes()
        self.assertNotIn(bytes(range(1, 33)), serialized)
        self.assertNotIn(base_material.config90, serialized)
        self.assertIn(report["terminal_state"], ("STOP", "CLOSE"))
        self.assertEqual(report["cleanup_count"], 1)
        self.assertIs(report["secret_zeroized"], True)
        self.assertEqual(publisher.publish_count, 1)
        return report, backend, selected_script

    @staticmethod
    def _replace_step(script, phase, *, responses=None, outcome=None):
        output = list(script)
        index = [step.phase_id for step in output].index(phase)
        step = output[index]
        output[index] = replace(
            step,
            responses=step.responses if responses is None else tuple(responses),
            outcome=step.outcome if outcome is None else outcome,
        )
        return tuple(output)

    def _assert_abort_at(self, report, backend, maximum_commands, abort_class=None):
        self.assertEqual(report["result"], "abort")
        self.assertEqual(report["terminal_state"], "STOP")
        self.assertLessEqual(backend.exchange_count, maximum_commands)
        self.assertLessEqual(backend.tls_handshake_count, 1)
        self.assertEqual(report["cleanup_count"], 1)
        if abort_class is not None:
            self.assertEqual(report["abort_class"], abort_class.value)

    def test_framing_golden_vectors_and_forbidden_control(self):
        self.assertEqual(build_a0(0xA2, bytes.fromhex("0114")).hex(), "a00600a6a203000114f0")
        self.assertEqual(build_a0(0x70, bytes.fromhex("1400")).hex(), "a00600a6700300140023")
        d1 = build_a0(0xD1, b"\x00\x00", checksum_seed_control=0xD0)
        self.assertEqual(d1.hex(), "a00600a6d103000000d7")
        self.assertEqual(parse_a0(d1, checksum_seed_control=0xD0).control, 0xD1)
        self.assertEqual(parse_b0(build_b0(_client_hello())), _client_hello())
        with self.assertRaises(ContractError):
            build_a0(0xD4, b"")

    def test_happy_path_is_exact_single_shot_and_redacted(self):
        report, backend, script = self._run(self.tmp_path)
        self.assertEqual(report["result"], "pass")
        self.assertEqual(report["reached_phase"], "TLS_HANDSHAKE_OK")
        self.assertEqual(report["command_count"], 12)
        self.assertEqual(backend.exchange_count, len(EXACT_PHASE_ORDER) - 1)
        self.assertEqual(backend.tls_handshake_count, 1)
        self.assertEqual([step.phase_id for step in script], list(EXACT_PHASE_ORDER[:-1]))

    def test_required_phase_failures_stop_without_next_command(self):
        cases = [
            ("E4", "typed_bad", AbortClass.UNEXPECTED_DATA, 1),
            ("A2_1", "timeout", AbortClass.TIMEOUT, 2),
            ("CHIP_82", "typed_bad", AbortClass.WRONG_CHIPID, 3),
            ("OTP_A6", "typed_short", AbortClass.OTP_MALFORMED, 4),
            ("A2_2", "typed_bad", AbortClass.UNEXPECTED_IRQ, 5),
            ("MODE_70", "extra", AbortClass.UNEXPECTED_DATA, 6),
            ("DAC_220", "bad_ack", AbortClass.UNEXPECTED_ACK, 7),
            ("DAC_236", "bad_ack", AbortClass.UNEXPECTED_ACK, 8),
            ("DAC_238", "bad_ack", AbortClass.UNEXPECTED_ACK, 9),
            ("DAC_23A", "bad_ack", AbortClass.UNEXPECTED_ACK, 10),
            ("CONFIG_90", "config_bad", AbortClass.CONFIG_MISMATCH, 11),
            ("D1", "a0_instead_b0", AbortClass.UNEXPECTED_DATA, 12),
            ("A2_1", "ambiguous", AbortClass.AMBIGUOUS, 2),
        ]
        for case_number, (phase, mutation, abort_class, maximum) in enumerate(cases):
            with self.subTest(phase=phase):
                material, responses = _synthetic_objects()
                script = happy_synthetic_script(material, responses)
                step = next(item for item in script if item.phase_id == phase)
                if mutation == "timeout":
                    script = self._replace_step(script, phase, outcome="timeout")
                elif mutation == "ambiguous":
                    script = self._replace_step(script, phase, outcome="ambiguous")
                elif mutation == "typed_short":
                    script = self._replace_step(
                        script, phase, responses=(step.responses[0], build_a0(0xA6, b"x"))
                    )
                elif mutation == "extra":
                    script = self._replace_step(
                        script, phase, responses=step.responses + (build_a0(0x70, b"x"),)
                    )
                elif mutation == "a0_instead_b0":
                    script = self._replace_step(script, phase, responses=(build_a0(0xD1, b"x"),))
                elif mutation == "bad_ack":
                    script = self._replace_step(script, phase, responses=(build_a0(0xB0, b"\x81\x01"),))
                elif mutation == "config_bad":
                    script = self._replace_step(
                        script, phase, responses=(step.responses[0], build_a0(0x90, b"\x00\x00"))
                    )
                else:
                    control = parse_a0(step.responses[1]).control
                    script = self._replace_step(
                        script, phase, responses=(step.responses[0], build_a0(control, b"\x00"))
                    )
                report, backend, _ = self._run(self.tmp_path / str(case_number), script)
                self._assert_abort_at(report, backend, maximum, abort_class)

    def test_tls_failures_are_terminal_and_not_retried(self):
        cases = {
            "bad_record_mac": AbortClass.BAD_RECORD_MAC,
            "timeout": AbortClass.TLS_TIMEOUT,
            "alert": AbortClass.TLS_ALERT,
        }
        for index, (outcome, expected) in enumerate(cases.items()):
            with self.subTest(outcome=outcome):
                report, backend, _ = self._run(
                    self.tmp_path / str(index), tls_outcome=outcome
                )
                self._assert_abort_at(report, backend, 12, expected)
                self.assertEqual(backend.tls_handshake_count, 1)

    def test_preflight_reenumeration_is_terminal_before_first_command(self):
        report, backend, _ = self._run(
            self.tmp_path, preflight=_preflight(unexpected_reenumeration=True)
        )
        self._assert_abort_at(report, backend, 0, AbortClass.PREFLIGHT)

    def test_dac_order_and_config_length_hash_fail_closed_with_report(self):
        material, _ = _synthetic_objects()
        variants = (
            ("dac", replace(material, dac=(material.dac[1], material.dac[0], *material.dac[2:]))),
            ("length", replace(material, config90=material.config90[:-1])),
            ("hash", replace(material, config90_sha256="0" * 64)),
        )
        for name, variant in variants:
            with self.subTest(name=name):
                report, backend, _ = self._run(self.tmp_path / name, material=variant)
                self._assert_abort_at(report, backend, 0, AbortClass.INTERNAL)

    def test_extra_reordered_and_retry_attempts_are_rejected(self):
        material, responses = _synthetic_objects()
        base = happy_synthetic_script(material, responses)
        variants = (
            ("extra", base[:1], 1),
            ("reordered", (base[1], base[0], *base[2:]), 1),
            ("retry", (base[0], base[0], *base[1:]), 2),
        )
        for name, script, maximum in variants:
            with self.subTest(name=name):
                report, backend, _ = self._run(self.tmp_path / name, script)
                self._assert_abort_at(report, backend, maximum, AbortClass.EXTRA_OR_REORDERED)

    def _write_synthetic_protected_inputs(self, path):
        path.mkdir(parents=True, exist_ok=True)
        material, responses = _synthetic_objects()
        config_path = path / "config.bin"
        config_path.write_bytes(material.config90)
        manifest_data = {
            "schema": "d232-target-material-v1",
            "e4": {"validator_sha256": material.e4_validator_sha256},
            "a2": {"response_body_sha256": material.a2_response_sha256},
            "chip82": {"response_body_sha256": material.chip82_response_sha256},
            "otp_a6": {"response_body_sha256": material.otp_a6_response_sha256},
            "dac": [
                {
                    "order": index,
                    "register": hex(register),
                    "value_le_hex": value.hex(),
                    "config_tuple_offset": offset,
                }
                for index, (register, value, offset) in enumerate(material.dac, 1)
            ],
            "config90": {"body_length": 224, "body_sha256": material.config90_sha256},
        }
        manifest_path = path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest_data, sort_keys=True))
        psk_path = path / "psk.bin"
        psk_path.write_bytes(bytes(range(1, 33)))
        for file_path in (manifest_path, config_path, psk_path):
            file_path.chmod(0o600)
        policy = ProtectedFilePolicy(owner_uid=os.getuid(), mode=0o600)
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        return material, responses, manifest_path, config_path, psk_path, policy, digest

    def test_protected_target_material_positive_and_provenance_negative(self):
        material, responses, manifest, config, psk, policy, digest = self._write_synthetic_protected_inputs(
            self.tmp_path
        )
        loaded = _load_target_material(
            manifest, config, expected_manifest_sha256=digest, file_policy=policy
        )
        self.assertEqual(loaded, material)
        with self.assertRaisesRegex(ContractError, "manifest hash mismatch"):
            _load_target_material(
                manifest, config, expected_manifest_sha256="0" * 64, file_policy=policy
            )
        backend = ScriptedSyntheticBackend(happy_synthetic_script(material, responses))
        publisher = DurableReportPublisher(self.tmp_path / "provenance-result.json")
        report = run_synthetic_from_protected_paths(
            preflight=_preflight(),
            manifest_path=manifest,
            config_path=config,
            psk_path=psk,
            expected_manifest_sha256="0" * 64,
            file_policy=policy,
            backend=backend,
            publisher=publisher,
        )
        self._assert_abort_at(report, backend, 0, AbortClass.CONFIG_MISMATCH)
        self.assertTrue(publisher.path.exists())

    def test_secret_boundary_failures_publish_report_before_commands(self):
        for index, secret_case in enumerate(("short", "long", "symlink")):
            with self.subTest(secret_case=secret_case):
                root = self.tmp_path / str(index)
                material, responses, manifest, config, psk, policy, digest = (
                    self._write_synthetic_protected_inputs(root)
                )
                if secret_case == "short":
                    psk.write_bytes(b"x" * 31)
                elif secret_case == "long":
                    psk.write_bytes(b"x" * 33)
                else:
                    target = root / "psk-target.bin"
                    target.write_bytes(b"x" * 32)
                    target.chmod(0o600)
                    psk.unlink()
                    psk.symlink_to(target)
                backend = ScriptedSyntheticBackend(happy_synthetic_script(material, responses))
                publisher = DurableReportPublisher(root / "secret-result.json")
                report = run_synthetic_from_protected_paths(
                    preflight=_preflight(),
                    manifest_path=manifest,
                    config_path=config,
                    psk_path=psk,
                    expected_manifest_sha256=digest,
                    file_policy=policy,
                    backend=backend,
                    publisher=publisher,
                )
                self._assert_abort_at(report, backend, 0, AbortClass.SECRET_BOUNDARY)
                self.assertEqual(stat.S_IMODE(publisher.path.stat().st_mode), 0o600)

    def test_secret_buffer_zeroization_and_exact_length(self):
        path = self.tmp_path / "secret"
        path.write_bytes(bytes(range(32)))
        path.chmod(0o600)
        owned = _read_exact_protected(
            path, 32, ProtectedFilePolicy(owner_uid=os.getuid(), mode=0o600)
        )
        secret = SecretBuffer(owned)
        self.assertEqual(bytes(secret.view()), bytes(range(32)))
        secret.close()
        self.assertTrue(secret.is_zeroized)
        self.assertFalse(any(owned))
        with self.assertRaises(ContractError):
            SecretBuffer.synthetic(b"x" * 31)

    def test_live_flag_and_environment_die_before_backend_or_usb(self):
        self.assertEqual(D232_LIVE_CAPABILITY, 0)
        cases = (("--live",), {}), ((), {"D232_LIVE": "1"}), ((), {"enable_live": "yes"})
        for argv, environ in cases:
            with self.subTest(argv=argv, environ=environ):
                with self.assertRaises(LiveCapabilityUnavailable):
                    d232_offline_entrypoint(argv, environ)
        with self.assertRaises(LiveCapabilityUnavailable):
            request_live_mode()
        self.assertEqual(
            d232_offline_entrypoint(),
            {
                "d232_live_capability": 0,
                "live_hard_disabled": True,
                "live_runtime_enablement_exists": False,
                "usb_open_count": 0,
            },
        )

    def test_non_exact_backend_type_is_rejected(self):
        class PretendLiveBackend(ScriptedSyntheticBackend):
            pass

        material, responses = _synthetic_objects()
        backend = PretendLiveBackend(happy_synthetic_script(material, responses))
        report = ExactOemReplayStateMachine().run(
            preflight=_preflight(),
            material=material,
            secret=SecretBuffer.synthetic(bytes(range(32))),
            backend=backend,
            publisher=DurableReportPublisher(self.tmp_path / "rejected.json"),
        )
        self.assertEqual(report["terminal_state"], "STOP")
        self.assertEqual(report["command_count"], 0)
        self.assertEqual(report["usb_open_count"], 0)
        self.assertEqual(report["cleanup_status"], "no_resources_acquired")
        self.assertTrue((self.tmp_path / "rejected.json").exists())


if __name__ == "__main__":
    unittest.main()
