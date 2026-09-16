from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from poc.goodix5125.tools.binding_reference.known_answers import VECTORS
from poc.goodix5125.tools.binding_reference.runtime import (
    derive_validator_from_canonical_pe,
)
from src.goodix5125_d232_offline import (
    AbortClass,
    ContractError,
    DurableReportPublisher,
    ProtectedFilePolicy,
    ReplayAbort,
    SecretBuffer,
    _load_target_material,
    _read_exact_protected,
    build_a0,
    happy_synthetic_script,
)
from src.goodix5125_d233_backend import (
    LibusbSystemApi,
    SystemOsFacade,
    Tls12PskServer,
    UsbIdentity,
)
from src.goodix5125_d235_entrypoint import (
    D235_LIVE_CAPABILITY,
    D235LiveUnavailable,
    ProductionRuntimePaths,
    ResolvedUsbTarget,
    RootProtectedInputProvider,
    SystemUsbTargetSelector,
    _d235_source_seal,
    d235_entrypoint,
    map_future_live_decision,
    run_injected_offline_entrypoint_review,
)
from tests.test_d233_backend import (
    FakeOsFacade,
    FakeUsbApi,
    ImmediateTlsEngine,
    synthetic_objects,
)


REPOSITORY = Path(__file__).resolve().parents[1]
CANONICAL_PE = REPOSITORY / "analysis/D230/work/GoodixExport/gfusb.dll"


class OfflineFacade(FakeOsFacade):
    offline_only = True


class OfflineUsbApi(FakeUsbApi):
    offline_only = True


class FixtureProtectedInputs:
    offline_only = True

    def __init__(self, paths: ProductionRuntimePaths, material, secret: bytes):
        self.paths = paths
        self.material = material
        self.secret = secret
        self.material_load_count = 0
        self.secret_load_count = 0
        self.policy = ProtectedFilePolicy(owner_uid=os.getuid(), mode=0o600)
        paths.psk_store.write_bytes(secret)
        paths.psk_store.chmod(0o600)
        paths.config90_store.write_bytes(material.config90)
        paths.config90_store.chmod(0o600)
        manifest = {
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
            "config90": {
                "body_length": 224,
                "body_sha256": material.config90_sha256,
            },
        }
        paths.target_material_manifest.write_text(
            json.dumps(manifest, sort_keys=True), encoding="utf-8"
        )
        paths.target_material_manifest.chmod(0o600)
        self.manifest_digest = hashlib.sha256(
            paths.target_material_manifest.read_bytes()
        ).hexdigest()

    def load_material(self):
        if self.material_load_count:
            raise ContractError("fixture material loaded twice")
        self.material_load_count = 1
        return _load_target_material(
            self.paths.target_material_manifest,
            self.paths.config90_store,
            expected_manifest_sha256=self.manifest_digest,
            file_policy=self.policy,
        )

    def load_secret(self):
        if self.secret_load_count:
            raise ContractError("fixture PSK loaded twice")
        self.secret_load_count = 1
        return SecretBuffer(
            _read_exact_protected(self.paths.psk_store, 32, self.policy)
        )


class FailingPublisher:
    publish_count = 0

    def publish(self, _report):
        raise OSError("injected publication failure")


class RestoreFailFacade(OfflineFacade):
    def start_fprintd(self):
        self.calls.append("start_failed")
        raise OSError("injected restore failure")


class SignalFailFacade(OfflineFacade):
    def block_signals(self, _signals):
        self.calls.append("signal_failed")
        raise KeyboardInterrupt("injected signal interruption")


class BadMacTlsEngine(ImmediateTlsEngine):
    def advance(self):
        raise ReplayAbort(AbortClass.BAD_RECORD_MAC)


@unittest.skipUnless(CANONICAL_PE.is_file(), "canonical PE intentionally excluded")
class D235EntrypointCompositionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="d235-entrypoint-")
        self.root = Path(self.temporary.name).resolve()
        self.secret = VECTORS["V2"]
        material, responses = synthetic_objects(self.secret)
        expected = derive_validator_from_canonical_pe(CANONICAL_PE, self.secret)
        try:
            validator = bytes(expected)
        finally:
            expected[:] = bytes(len(expected))
        self.responses = dataclasses.replace(responses, e4_validator=validator)
        self.material = dataclasses.replace(
            material,
            e4_validator_sha256=hashlib.sha256(validator).hexdigest(),
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _case(self, name: str):
        root = self.root / name
        store = root / "store"
        reports = root / "reports"
        store.mkdir(parents=True)
        reports.mkdir()
        paths = ProductionRuntimePaths(
            psk_store=store / "transport-material.bin",
            target_material_manifest=store / "target-material-manifest.json",
            config90_store=store / "target-config-90.bin",
            canonical_gfusb=CANONICAL_PE,
            report_directory=reports,
            checkpoint_report=reports / "checkpoint.json",
            final_report=reports / "final.json",
            single_use_marker=store / "single-use.marker",
        )
        inputs = FixtureProtectedInputs(paths, self.material, self.secret)
        identity = UsbIdentity(0x27C6, 0x5125, 1, 4, (2, 3))
        target = ResolvedUsbTarget(identity, Path("/dev/bus/usb/001/004"))
        incoming = [
            frame
            for step in happy_synthetic_script(self.material, self.responses)
            for frame in step.responses
        ]
        return root, paths, inputs, target, incoming

    def _run(
        self,
        name: str,
        *,
        facade=None,
        api=None,
        tls_factory=ImmediateTlsEngine,
        checkpoint=None,
        final=None,
        mutate_inputs=None,
    ):
        root, paths, inputs, target, incoming = self._case(name)
        if mutate_inputs:
            mutate_inputs(paths, inputs)
        facade = facade or OfflineFacade()
        api = api or OfflineUsbApi(incoming, identity=target.identity)
        checkpoint = checkpoint or DurableReportPublisher(paths.checkpoint_report)
        final = final or DurableReportPublisher(paths.final_report)
        report = run_injected_offline_entrypoint_review(
            offline_root=root,
            paths=paths,
            os_facade=facade,
            operator_uid=1000,
            target=target,
            inputs=inputs,
            usb_api=api,
            tls_factory=tls_factory,
            checkpoint_delegate=checkpoint,
            final_delegate=final,
        )
        return report, facade, api, inputs, paths

    def test_happy_path_wires_same_secret_exact_core_report_cleanup_restore(self):
        report, facade, api, inputs, paths = self._run("happy")
        self.assertEqual(report["schema"], "d235-production-entrypoint-result-v1")
        self.assertEqual(report["decision"], "D236_LIVE_TLS_HANDSHAKE_SUCCESS")
        self.assertEqual(report["execution_mode"], "injected_offline_entrypoint_review")
        self.assertEqual(report["command_count"], 12)
        self.assertEqual(report["usb_open_count"], 1)
        self.assertEqual(report["tls_handshake_count"], 1)
        self.assertEqual(report["cleanup_count"], 1)
        self.assertTrue(report["same_validated_psk_used_by_tls"])
        self.assertTrue(report["secret_zeroized"])
        self.assertEqual(inputs.material_load_count, 1)
        self.assertEqual(inputs.secret_load_count, 1)
        self.assertEqual(api.calls.count("init"), 1)
        self.assertEqual(facade.calls.count("stop"), 1)
        self.assertEqual(facade.calls.count("start"), 1)
        self.assertTrue(paths.checkpoint_report.is_file())
        self.assertTrue(paths.final_report.is_file())
        self.assertEqual(paths.final_report.stat().st_mode & 0o777, 0o600)
        self.assertEqual(report["d4_count"], 0)
        self.assertEqual(report["application_data_count"], 0)
        self.assertEqual(report["retry_count"], 0)

    def test_preflight_failures_stop_before_inputs_and_usb(self):
        cases = {
            "euid": ("root", 1000),
            "operator": ("sudo", 2000),
            "holder": ("holders", (99,)),
        }
        for name, (attribute, value) in cases.items():
            with self.subTest(name=name):
                facade = OfflineFacade()
                setattr(facade, attribute, value)
                report, _facade, api, inputs, _paths = self._run(
                    "preflight-" + name, facade=facade
                )
                self.assertEqual(report["decision"], "D236_BLOCKED_BY_PREFLIGHT")
                self.assertEqual(report["usb_open_count"], 0)
                self.assertEqual(inputs.material_load_count, 0)
                self.assertNotIn("init", api.calls)

    def test_bad_protected_file_metadata_and_pe_fail_before_usb(self):
        mutations = {
            "psk": lambda paths, _inputs: paths.psk_store.chmod(0o644),
            "config": lambda paths, _inputs: paths.config90_store.chmod(0o644),
            "manifest": lambda paths, _inputs: paths.target_material_manifest.chmod(0o644),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                report, _facade, api, _inputs, _paths = self._run(
                    "metadata-" + name, mutate_inputs=mutation
                )
                self.assertEqual(report["decision"], "D236_BLOCKED_BY_PROTECTED_INPUT")
                self.assertEqual(report["usb_open_count"], 0)
                self.assertNotIn("init", api.calls)

        root, paths, inputs, target, incoming = self._case("bad-pe")
        wrong = root / "wrong.dll"
        wrong.write_bytes(b"MZ" + bytes(126))
        paths = dataclasses.replace(paths, canonical_gfusb=wrong)
        api = OfflineUsbApi(incoming, identity=target.identity)
        report = run_injected_offline_entrypoint_review(
            offline_root=root,
            paths=paths,
            os_facade=OfflineFacade(),
            operator_uid=1000,
            target=target,
            inputs=inputs,
            usb_api=api,
            tls_factory=ImmediateTlsEngine,
            checkpoint_delegate=DurableReportPublisher(paths.checkpoint_report),
            final_delegate=DurableReportPublisher(paths.final_report),
        )
        self.assertEqual(report["decision"], "D236_BLOCKED_BY_PROTECTED_INPUT")
        self.assertNotIn("init", api.calls)

        root, paths, inputs, target, incoming = self._case("symlink-pe")
        linked = root / "linked-gfusb.dll"
        linked.symlink_to(CANONICAL_PE)
        paths = dataclasses.replace(paths, canonical_gfusb=linked)
        api = OfflineUsbApi(incoming, identity=target.identity)
        report = run_injected_offline_entrypoint_review(
            offline_root=root,
            paths=paths,
            os_facade=OfflineFacade(),
            operator_uid=1000,
            target=target,
            inputs=inputs,
            usb_api=api,
            tls_factory=ImmediateTlsEngine,
            checkpoint_delegate=DurableReportPublisher(paths.checkpoint_report),
            final_delegate=DurableReportPublisher(paths.final_report),
        )
        self.assertEqual(report["decision"], "D236_BLOCKED_BY_PROTECTED_INPUT")
        self.assertNotIn("init", api.calls)

    def test_e4_mismatch_open_and_claim_failures_are_precise_and_terminal(self):
        root, paths, inputs, target, incoming = self._case("e4-mismatch")
        incoming[1] = build_a0(
            0xE4,
            bytes.fromhex("00030002bb20000000") + bytes(32),
        )
        api = OfflineUsbApi(incoming, identity=target.identity)
        report = run_injected_offline_entrypoint_review(
            offline_root=root,
            paths=paths,
            os_facade=OfflineFacade(),
            operator_uid=1000,
            target=target,
            inputs=inputs,
            usb_api=api,
            tls_factory=ImmediateTlsEngine,
            checkpoint_delegate=DurableReportPublisher(paths.checkpoint_report),
            final_delegate=DurableReportPublisher(paths.final_report),
        )
        self.assertEqual(report["decision"], "D236_ABORTED_E4_BINDING")
        self.assertEqual(report["command_count"], 1)
        self.assertEqual(report["tls_handshake_count"], 0)

        for name in ("open", "claim"):
            with self.subTest(name=name):
                _root, _paths, _inputs, _target, frames = self._case("usb-" + name)
                failing = OfflineUsbApi(frames, identity=_target.identity)
                if name == "open":
                    failing.open_result = None
                else:
                    failing.claim_fails = True
                report, _facade, _api, _inputs, _paths = self._run(
                    "usb-run-" + name, api=failing
                )
                self.assertEqual(report["decision"], "D236_ABORTED_USB_TRANSPORT")
                self.assertLessEqual(report["usb_open_count"], 1)

    def test_each_protocol_phase_has_a_unique_terminal_family(self):
        expected = {
            "E4": "D236_ABORTED_E4_BINDING",
            "A2_1": "D236_ABORTED_A2",
            "CHIP_82": "D236_ABORTED_CHIPID",
            "OTP_A6": "D236_ABORTED_OTP",
            "A2_2": "D236_ABORTED_A2",
            "MODE_70": "D236_ABORTED_MODE70",
            "DAC_220": "D236_ABORTED_DAC",
            "DAC_236": "D236_ABORTED_DAC",
            "DAC_238": "D236_ABORTED_DAC",
            "DAC_23A": "D236_ABORTED_DAC",
            "CONFIG_90": "D236_ABORTED_CONFIG90",
            "D1": "D236_ABORTED_D1",
        }
        script = happy_synthetic_script(self.material, self.responses)
        for phase, decision in expected.items():
            with self.subTest(phase=phase):
                root, paths, inputs, target, _incoming = self._case("phase-" + phase)
                incoming = []
                for step in script:
                    responses = list(step.responses)
                    if step.phase_id == phase:
                        responses[0] = build_a0(0xB0, b"\x00\x00")
                    incoming.extend(responses)
                api = OfflineUsbApi(incoming, identity=target.identity)
                report = run_injected_offline_entrypoint_review(
                    offline_root=root,
                    paths=paths,
                    os_facade=OfflineFacade(),
                    operator_uid=1000,
                    target=target,
                    inputs=inputs,
                    usb_api=api,
                    tls_factory=ImmediateTlsEngine,
                    checkpoint_delegate=DurableReportPublisher(paths.checkpoint_report),
                    final_delegate=DurableReportPublisher(paths.final_report),
                )
                self.assertEqual(report["decision"], decision)
                self.assertEqual(report["tls_handshake_count"], 0)
                self.assertEqual(report["cleanup_count"], 1)

    def test_tls_bad_record_mac_is_terminal_and_single_shot(self):
        report, _facade, _api, _inputs, _paths = self._run(
            "bad-mac", tls_factory=BadMacTlsEngine
        )
        self.assertEqual(report["decision"], "D236_ABORTED_TLS")
        self.assertEqual(report["tls_handshake_count"], 1)
        self.assertEqual(report["cleanup_count"], 1)
        self.assertEqual(report["retry_count"], 0)

    def test_checkpoint_restore_signal_and_final_publication_fail_closed(self):
        report, facade, _api, _inputs, paths = self._run(
            "checkpoint-fail", checkpoint=FailingPublisher()
        )
        self.assertEqual(report["decision"], "D236_INTERNAL_SAFETY_VIOLATION")
        self.assertIn("start", facade.calls)
        self.assertTrue(paths.final_report.is_file())

        report, _facade, _api, _inputs, paths = self._run(
            "restore-fail", facade=RestoreFailFacade()
        )
        self.assertEqual(report["decision"], "D236_INTERNAL_SAFETY_VIOLATION")
        self.assertEqual(report["fprintd_restore_status"], "failed")
        self.assertTrue(paths.checkpoint_report.is_file())
        self.assertTrue(paths.final_report.is_file())

        report, _facade, api, _inputs, _paths = self._run(
            "signal-fail", facade=SignalFailFacade()
        )
        self.assertEqual(report["decision"], "D236_INTERNAL_SAFETY_VIOLATION")
        self.assertNotIn("init", api.calls)

        root, paths, inputs, target, incoming = self._case("final-fail")
        facade = OfflineFacade()
        with self.assertRaisesRegex(OSError, "publication"):
            run_injected_offline_entrypoint_review(
                offline_root=root,
                paths=paths,
                os_facade=facade,
                operator_uid=1000,
                target=target,
                inputs=inputs,
                usb_api=OfflineUsbApi(incoming, identity=target.identity),
                tls_factory=ImmediateTlsEngine,
                checkpoint_delegate=DurableReportPublisher(paths.checkpoint_report),
                final_delegate=FailingPublisher(),
            )
        self.assertIn("start", facade.calls)
        self.assertTrue(paths.checkpoint_report.is_file())

    def test_offline_review_rejects_all_system_dependency_substitution(self):
        root, paths, inputs, target, incoming = self._case("guard")
        common = dict(
            offline_root=root,
            paths=paths,
            operator_uid=1000,
            target=target,
            inputs=inputs,
            usb_api=OfflineUsbApi(incoming, identity=target.identity),
            tls_factory=ImmediateTlsEngine,
            checkpoint_delegate=DurableReportPublisher(paths.checkpoint_report),
            final_delegate=DurableReportPublisher(paths.final_report),
        )
        with self.assertRaises(ContractError):
            run_injected_offline_entrypoint_review(os_facade=SystemOsFacade(), **common)
        common["os_facade"] = OfflineFacade()
        common["usb_api"] = LibusbSystemApi()
        with self.assertRaises(ContractError):
            run_injected_offline_entrypoint_review(**common)
        common["usb_api"] = OfflineUsbApi(incoming, identity=target.identity)
        common["inputs"] = RootProtectedInputProvider(paths)
        with self.assertRaises(ContractError):
            run_injected_offline_entrypoint_review(**common)


class D235PathMappingAndHardDisableTests(unittest.TestCase):
    def test_production_paths_are_absolute_fixed_and_not_home_relative(self):
        paths = ProductionRuntimePaths.system_default()
        paths.validate()
        self.assertEqual(paths.psk_store, Path("/var/lib/goodix-5125-poc/transport-material.bin"))
        self.assertEqual(paths.config90_store, Path("/var/lib/goodix-5125-poc/target-config-90.bin"))
        self.assertEqual(paths.canonical_gfusb, CANONICAL_PE)
        source = REPOSITORY / "src/goodix5125_d235_entrypoint.py"
        self.assertNotIn("os.environ.get(\"HOME\")", source.read_text(encoding="utf-8"))

    def test_sysfs_selector_requires_one_exact_target_without_device_open(self):
        with tempfile.TemporaryDirectory(prefix="d235-sysfs-") as directory:
            sysfs = Path(directory)

            def add(name, vid="27c6", pid="5125", bus="1", address="4"):
                entry = sysfs / name
                entry.mkdir()
                for filename, value in (
                    ("idVendor", vid),
                    ("idProduct", pid),
                    ("busnum", bus),
                    ("devnum", address),
                ):
                    (entry / filename).write_text(value, encoding="ascii")

            add("1-2.3")
            add("1-9", vid="1234", address="7")
            selector = SystemUsbTargetSelector()
            selector.SYSFS_USB = sysfs
            char_status = SimpleNamespace(st_mode=stat.S_IFCHR | 0o600)
            with mock.patch(
                "src.goodix5125_d235_entrypoint.os.lstat", return_value=char_status
            ):
                target = selector.resolve_exact(0x27C6, 0x5125)
                self.assertEqual(target.identity, UsbIdentity(0x27C6, 0x5125, 1, 4, (2, 3)))
                self.assertEqual(target.device_path, Path("/dev/bus/usb/001/004"))
                add("1-5", address="8")
                with self.assertRaisesRegex(ContractError, "exactly one"):
                    selector.resolve_exact(0x27C6, 0x5125)

    def test_result_mapper_covers_every_terminal_family(self):
        cases = (
            ({"result": "pass"}, "D236_LIVE_TLS_HANDSHAKE_SUCCESS"),
            ({"reached_phase": "PREFLIGHT", "abort_class": "preflight_failed"}, "D236_BLOCKED_BY_PREFLIGHT"),
            ({"reached_phase": "SECRET_LOAD_GATE", "abort_class": "secret_boundary_failure"}, "D236_BLOCKED_BY_PROTECTED_INPUT"),
            ({"reached_phase": "IDENTITY_REVALIDATED", "attempted_phase": "E4", "backend_failure_domain": "usb_transport", "abort_class": "unexpected_data"}, "D236_ABORTED_USB_TRANSPORT"),
            ({"reached_phase": "IDENTITY_REVALIDATED", "attempted_phase": "E4", "abort_class": "secret_boundary_failure"}, "D236_ABORTED_E4_BINDING"),
            ({"attempted_phase": "A2_1", "abort_class": "unexpected_irq"}, "D236_ABORTED_A2"),
            ({"attempted_phase": "CHIP_82", "abort_class": "wrong_chipid"}, "D236_ABORTED_CHIPID"),
            ({"attempted_phase": "OTP_A6", "abort_class": "otp_shape_or_hash_mismatch"}, "D236_ABORTED_OTP"),
            ({"attempted_phase": "MODE_70", "abort_class": "unexpected_data"}, "D236_ABORTED_MODE70"),
            ({"attempted_phase": "DAC_220", "abort_class": "unexpected_data"}, "D236_ABORTED_DAC"),
            ({"attempted_phase": "CONFIG_90", "abort_class": "config_mismatch"}, "D236_ABORTED_CONFIG90"),
            ({"attempted_phase": "D1", "abort_class": "unexpected_data"}, "D236_ABORTED_D1"),
            ({"attempted_phase": "TLS", "abort_class": "tls_bad_record_mac"}, "D236_ABORTED_TLS"),
            ({"abort_class": "internal_fail_closed"}, "D236_INTERNAL_SAFETY_VIOLATION"),
        )
        for report, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(map_future_live_decision(report), expected)

    def test_all_shipped_entrypoint_enablement_attempts_keep_usb_zero(self):
        cases = (
            ((), {}, None, None),
            (("--live",), {}, None, None),
            (("--force",), {}, None, None),
            (("unexpected",), {}, None, None),
            ((), {"LIVE": "1"}, None, None),
            ((), {"D235_LIVE": "1", "HOME": "/tmp/confused"}, None, None),
            ((), {}, {"enable_live": True}, None),
            ((), {}, None, "libusb"),
        )
        for argv, env, config, backend in cases:
            with self.subTest(argv=argv, env=env, config=config, backend=backend):
                result = d235_entrypoint(argv, env, config, backend)
                self.assertEqual(result["d235_live_capability"], D235_LIVE_CAPABILITY)
                self.assertEqual(result["usb_init_count"], 0)
                self.assertEqual(result["usb_open_count"], 0)
                self.assertFalse(result["runtime_live_enablement_exists"])
        with self.assertRaises(D235LiveUnavailable):
            _d235_source_seal()

    def test_alternate_module_invocation_is_sealed(self):
        for argv in ((), ("--live",), ("--force",)):
            result = subprocess.run(
                [sys.executable, "-m", "src.goodix5125_d235_entrypoint", *argv],
                cwd=REPOSITORY,
                check=False,
                text=True,
                capture_output=True,
            )
            report = json.loads(result.stdout)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(report["usb_open_count"], 0)


if __name__ == "__main__":
    unittest.main()
