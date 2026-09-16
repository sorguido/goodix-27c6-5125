from __future__ import annotations

import dataclasses
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from poc.goodix5125.tools.binding_reference.known_answers import (
    EXPECTED_VALIDATORS,
    VECTORS,
)
from poc.goodix5125.tools.binding_reference.pe_parser import (
    _require_unique_instruction_pattern,
)
from poc.goodix5125.tools.binding_reference.runtime import (
    derive_validator_from_canonical_pe,
)
from src.goodix5125_d232_offline import (
    AbortClass,
    DurableReportPublisher,
    ReplayAbort,
    SecretBuffer,
    SyntheticResponseBodies,
    happy_synthetic_script,
)
from src.goodix5125_d233_backend import (
    INJECTED_OFFLINE_MODE,
    PRODUCTION_CANDIDATE_SCHEMA,
    ProductionOsPreflight,
    ProductionReplayBackend,
    ProductionUsbTransport,
    RuntimePskE4Binder,
    UsbFailure,
    run_production_candidate_offline,
)
from tests.test_d233_backend import (
    FakeOsFacade,
    FakeUsbApi,
    ImmediateTlsEngine,
    preflight,
    synthetic_objects,
)

REPOSITORY = Path(__file__).resolve().parents[1]
CANONICAL_PE = REPOSITORY / "analysis/D230/work/GoodixExport/gfusb.dll"


def _canonical_objects(secret_bytes: bytes, *, e4: bytes | None = None):
    material, responses = synthetic_objects(secret_bytes)
    expected = derive_validator_from_canonical_pe(CANONICAL_PE, secret_bytes)
    try:
        validator = bytes(expected) if e4 is None else bytes(e4)
    finally:
        expected[:] = bytes(len(expected))
    responses = dataclasses.replace(responses, e4_validator=validator)
    material = dataclasses.replace(
        material, e4_validator_sha256=hashlib.sha256(validator).hexdigest()
    )
    return material, responses


class D190RecoveredReferenceTests(unittest.TestCase):
    @unittest.skipUnless(CANONICAL_PE.is_file(), "canonical PE intentionally excluded from closure bundle")
    def test_five_historical_oem_known_answers_are_noncircular(self):
        for name, secret in VECTORS.items():
            with self.subTest(vector=name):
                actual = derive_validator_from_canonical_pe(CANONICAL_PE, secret)
                try:
                    self.assertEqual(actual.hex(), EXPECTED_VALIDATORS[name])
                finally:
                    actual[:] = bytes(len(actual))

    def test_wrong_pe_hash_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="d233-wrong-pe-") as directory:
            wrong = Path(directory) / "gfusb.dll"
            wrong.write_bytes(b"MZ" + bytes(126))
            with self.assertRaisesRegex(ValueError, "PE hash mismatch"):
                derive_validator_from_canonical_pe(wrong, VECTORS["V0"])

    def test_instruction_pattern_ambiguity_fails_closed(self):
        instruction = bytes.fromhex("c7459f01020304c745a305060000")
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            _require_unique_instruction_pattern(instruction[:12] * 2, instruction)

    @unittest.skipUnless(CANONICAL_PE.is_file(), "canonical PE intentionally excluded from closure bundle")
    def test_kat_and_secret_mutations_do_not_match(self):
        mutated = bytearray(VECTORS["V2"])
        mutated[7] ^= 1
        actual = derive_validator_from_canonical_pe(CANONICAL_PE, mutated)
        try:
            self.assertNotEqual(actual.hex(), EXPECTED_VALIDATORS["V2"])
            wrong_expected = bytearray.fromhex(EXPECTED_VALIDATORS["V2"])
            wrong_expected[-1] ^= 1
            self.assertNotEqual(actual, wrong_expected)
        finally:
            actual[:] = bytes(len(actual))


class D233RuntimeD190BindingTests(unittest.TestCase):
    def setUp(self):
        if not CANONICAL_PE.is_file():
            self.skipTest("canonical PE intentionally excluded from closure bundle")

    def _backend_run(self, loaded_secret: bytes, device_validator: bytes):
        material, responses = _canonical_objects(VECTORS["V2"], e4=device_validator)
        incoming = [frame for step in happy_synthetic_script(material, responses) for frame in step.responses]
        secret = SecretBuffer.synthetic(loaded_secret)
        backend = ProductionReplayBackend(
            ProductionUsbTransport(FakeUsbApi(incoming)),
            secret,
            RuntimePskE4Binder.from_canonical_pe(CANONICAL_PE),
            tls_factory=ImmediateTlsEngine,
        )
        from src.goodix5125_d233_backend import run_reviewed_backend_offline
        with tempfile.TemporaryDirectory(prefix="d233-binding-") as directory:
            report = run_reviewed_backend_offline(
                preflight=preflight(),
                material=material,
                secret=secret,
                backend=backend,
                publisher=DurableReportPublisher(Path(directory) / "report.json"),
            )
        return report, backend

    def test_correct_d190_vector_matches_and_same_buffer_reaches_tls(self):
        expected = bytes.fromhex(EXPECTED_VALIDATORS["V2"])
        report, backend = self._backend_run(VECTORS["V2"], expected)
        self.assertEqual(report["result"], "pass")
        self.assertEqual(backend.binder.compare_count, 1)
        self.assertEqual(backend.tls_handshake_count, 1)

    def test_one_bit_psk_and_wrong_e4_stop_before_a2(self):
        expected = bytes.fromhex(EXPECTED_VALIDATORS["V2"])
        mutated = bytearray(VECTORS["V2"]); mutated[0] ^= 1
        for name, secret, validator in (
            ("psk", bytes(mutated), expected),
            ("e4", VECTORS["V2"], expected[:-1] + bytes((expected[-1] ^ 1,))),
        ):
            with self.subTest(name=name):
                report, backend = self._backend_run(secret, validator)
                self.assertEqual(report["terminal_state"], "STOP")
                self.assertEqual(report["abort_class"], AbortClass.SECRET_BOUNDARY.value)
                self.assertEqual(report["command_count"], 1)
                self.assertEqual(backend.tls_handshake_count, 0)

    def test_wrong_derived_kat_stops(self):
        expected = bytes.fromhex(EXPECTED_VALIDATORS["V2"])
        secret = SecretBuffer.synthetic(VECTORS["V2"])
        binder = RuntimePskE4Binder(lambda _secret: bytes(32))
        from src.goodix5125_d232_offline import build_a0
        responses = (
            build_a0(0xB0, b"\xe4\x01"),
            build_a0(0xE4, binder.E4_PREFIX + expected),
        )
        with self.assertRaises(ReplayAbort) as caught:
            binder.validate(secret, responses)
        self.assertEqual(caught.exception.abort_class, AbortClass.SECRET_BOUNDARY)
        secret.close()


class FailingCheckpointPublisher:
    publish_count = 0
    def publish(self, _report):
        raise OSError("injected checkpoint failure")


class D233CandidateOrchestratorTests(unittest.TestCase):
    def setUp(self):
        if not CANONICAL_PE.is_file():
            self.skipTest("canonical PE intentionally excluded from closure bundle")
        self.temporary = tempfile.TemporaryDirectory(prefix="d233-orchestrator-")
        self.root = Path(self.temporary.name)
        self.secret_bytes = VECTORS["V2"]

    def tearDown(self):
        self.temporary.cleanup()

    def _preflight(self, facade=None):
        facade = facade or FakeOsFacade()
        return ProductionOsPreflight(
            facade,
            operator_uid=1000,
            device_path=Path("/dev/injected-goodix"),
            marker=self.root / "marker",
            report=(self.root / "final.json").absolute(),
        )

    def _run(self, *, pe=CANONICAL_PE, facade=None, checkpoint=None, incoming=None,
             material_loader=None, api_factory=None):
        material, responses = _canonical_objects(self.secret_bytes)
        normal = [frame for step in happy_synthetic_script(material, responses) for frame in step.responses]
        captured = {}
        def backend_factory(secret, binder):
            api = api_factory() if api_factory else FakeUsbApi(normal if incoming is None else incoming)
            backend = ProductionReplayBackend(
                ProductionUsbTransport(api), secret, binder, tls_factory=ImmediateTlsEngine
            )
            captured.update(backend=backend, api=api, secret=secret)
            return backend
        final = DurableReportPublisher(self.root / "final.json")
        tx = self._preflight(facade)
        report = run_production_candidate_offline(
            preflight_tx=tx,
            material_loader=material_loader or (lambda: material),
            secret_loader=lambda: SecretBuffer.synthetic(self.secret_bytes),
            canonical_pe_path=pe,
            backend_factory=backend_factory,
            checkpoint_publisher=checkpoint or DurableReportPublisher(self.root / "pre-restore.json"),
            final_publisher=final,
        )
        return report, tx, captured

    def test_success_report_is_truthful_and_ordered(self):
        report, tx, captured = self._run()
        self.assertEqual(report["schema"], PRODUCTION_CANDIDATE_SCHEMA)
        self.assertNotIn("synthetic-run-report", report["schema"])
        self.assertEqual(report["execution_mode"], INJECTED_OFFLINE_MODE)
        self.assertEqual(report["source_seal_state"], "sealed")
        self.assertEqual(report["live_authorization"], "no")
        self.assertEqual(report["runtime_psk_e4_binding_status"], "match")
        self.assertTrue(report["same_validated_psk_used_by_tls"])
        self.assertEqual(report["cleanup_count"], 1)
        self.assertEqual(tx.restore_count, 1)
        self.assertEqual(report["report_publish_count"], 2)
        self.assertTrue(report["secret_zeroized"])
        self.assertTrue((self.root / "pre-restore.json").is_file())
        self.assertEqual(json.loads((self.root / "final.json").read_text()), report)
        self.assertIs(captured["backend"].secret, captured["secret"])

    def test_wrong_pe_stops_before_backend_or_command(self):
        wrong = self.root / "wrong.dll"; wrong.write_bytes(b"MZ" + bytes(64))
        report, tx, captured = self._run(pe=wrong)
        self.assertEqual(report["runtime_psk_e4_binding_status"], "reference_failed")
        self.assertEqual(report["command_count"], 0)
        self.assertEqual(report["usb_open_count"], 0)
        self.assertFalse(captured)
        self.assertEqual(tx.restore_count, 1)

    def test_preflight_protected_input_open_claim_and_e4_fail_closed(self):
        cases = []
        facade = FakeOsFacade(); facade.holders = (9,)
        cases.append(("preflight", dict(facade=facade), AbortClass.PREFLIGHT.value))
        cases.append(("material", dict(material_loader=lambda: (_ for _ in ()).throw(ValueError("bad"))), AbortClass.CONFIG_MISMATCH.value))
        def absent_api():
            api = FakeUsbApi(); api.open_result = None; return api
        cases.append(("open", dict(api_factory=absent_api), AbortClass.UNEXPECTED_DATA.value))
        def claim_api():
            api = FakeUsbApi(); api.claim_fails = True; return api
        cases.append(("claim", dict(api_factory=claim_api), AbortClass.UNEXPECTED_DATA.value))
        material, responses = _canonical_objects(self.secret_bytes)
        bad = dataclasses.replace(responses, e4_validator=bytes(32))
        material = dataclasses.replace(material, e4_validator_sha256=hashlib.sha256(bytes(32)).hexdigest())
        bad_incoming = [frame for step in happy_synthetic_script(material, bad) for frame in step.responses]
        cases.append(("e4", dict(incoming=bad_incoming), AbortClass.SECRET_BOUNDARY.value))
        for name, kwargs, expected_abort in cases:
            with self.subTest(name=name):
                # Each case needs distinct durable paths.
                case_root = self.root / name; case_root.mkdir()
                old_root, self.root = self.root, case_root
                try:
                    report, tx, _ = self._run(**kwargs)
                finally:
                    self.root = old_root
                self.assertEqual(report["terminal_state"], "STOP")
                self.assertEqual(report["abort_class"], expected_abort)
                self.assertEqual(tx.restore_count, 1)

    def test_checkpoint_failure_still_restores_and_final_report_is_durable(self):
        report, tx, _ = self._run(checkpoint=FailingCheckpointPublisher())
        self.assertEqual(report["terminal_state"], "STOP")
        self.assertEqual(report["abort_class"], AbortClass.INTERNAL.value)
        self.assertEqual(tx.restore_count, 1)
        self.assertEqual(report["report_publish_count"], 1)
        self.assertTrue((self.root / "final.json").is_file())

    def test_restore_failure_keeps_checkpoint_and_publishes_final_failure(self):
        class RestoreFailFacade(FakeOsFacade):
            def start_fprintd(self):
                self.calls.append("start-failed")
                raise OSError("injected restore failure")
        report, tx, _ = self._run(facade=RestoreFailFacade())
        self.assertEqual(report["terminal_state"], "STOP")
        self.assertEqual(report["fprintd_restore_status"], "failed")
        self.assertEqual(report["signal_restore_status"], "restored")
        self.assertEqual(tx.restore_count, 1)
        self.assertTrue((self.root / "pre-restore.json").is_file())
        self.assertTrue((self.root / "final.json").is_file())

    def test_final_publication_failure_keeps_checkpoint_and_restores(self):
        material, responses = _canonical_objects(self.secret_bytes)
        incoming = [frame for step in happy_synthetic_script(material, responses) for frame in step.responses]
        facade = FakeOsFacade()
        tx = self._preflight(facade)
        def backend_factory(secret, binder):
            return ProductionReplayBackend(
                ProductionUsbTransport(FakeUsbApi(incoming)),
                secret,
                binder,
                tls_factory=ImmediateTlsEngine,
            )
        with self.assertRaisesRegex(OSError, "injected checkpoint failure"):
            run_production_candidate_offline(
                preflight_tx=tx,
                material_loader=lambda: material,
                secret_loader=lambda: SecretBuffer.synthetic(self.secret_bytes),
                canonical_pe_path=CANONICAL_PE,
                backend_factory=backend_factory,
                checkpoint_publisher=DurableReportPublisher(self.root / "pre-restore.json"),
                final_publisher=FailingCheckpointPublisher(),
            )
        self.assertEqual(tx.restore_count, 1)
        checkpoint = json.loads((self.root / "pre-restore.json").read_text())
        self.assertTrue(checkpoint["secret_zeroized"])
        self.assertEqual(checkpoint["cleanup_count"], 1)


if __name__ == "__main__":
    unittest.main()
