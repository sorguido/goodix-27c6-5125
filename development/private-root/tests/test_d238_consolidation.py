from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from src.goodix5125_d232_offline import (
    AbortClass,
    DurableReportPublisher,
    ExactOemReplayStateMachine,
    PHASE_RESPONSE_POLICIES,
    ReplayAbort,
    ScriptedSyntheticBackend,
    SecretBuffer,
    build_a0,
    happy_synthetic_script,
)
from src.goodix5125_d233_backend import (
    ProductionReplayBackend,
    ProductionUsbTransport,
    RuntimePskE4Binder,
)
from tests.test_d232_offline import _preflight, _synthetic_objects
from tests.test_d233_backend import FakeUsbApi, ImmediateTlsEngine


def _synthetic_validator(secret: memoryview) -> bytes:
    return hashlib.sha256(b"D233 synthetic validator\0" + bytes(secret)).digest()


class D238ConsolidatedAckPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="d238-tests-")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def _run_script(self, script):
        material, _responses = _synthetic_objects()
        backend = ScriptedSyntheticBackend(script)
        report = ExactOemReplayStateMachine().run(
            preflight=_preflight(),
            material=material,
            secret=SecretBuffer.synthetic(bytes(range(1, 33))),
            backend=backend,
            publisher=DurableReportPublisher(self.root / f"result-{len(list(self.root.iterdir()))}.json"),
        )
        return report, backend

    def test_complete_pre_d1_accepts_recovered_capture_status_01(self):
        material, responses = _synthetic_objects()
        report, backend = self._run_script(
            happy_synthetic_script(material, responses, ack_status=0x01)
        )
        self.assertEqual(report["result"], "pass")
        self.assertEqual(backend.exchange_count, 12)
        self.assertEqual(backend.tls_handshake_count, 1)

    def test_complete_pre_d1_accepts_live_family_status_07(self):
        material, responses = _synthetic_objects()
        report, backend = self._run_script(
            happy_synthetic_script(material, responses, ack_status=0x07)
        )
        self.assertEqual(report["result"], "pass")
        self.assertEqual(backend.exchange_count, 12)
        self.assertEqual(backend.tls_handshake_count, 1)

    def test_every_ack_phase_rejects_unproven_statuses_and_never_retries(self):
        material, responses = _synthetic_objects()
        base = happy_synthetic_script(material, responses)
        ack_phases = [
            phase for phase, policy in PHASE_RESPONSE_POLICIES.items()
            if policy.allowed_ack_statuses
        ]
        for index, phase in enumerate(ack_phases):
            with self.subTest(phase=phase):
                script = list(base)
                position = [step.phase_id for step in script].index(phase)
                step = script[position]
                bad_ack = build_a0(
                    0xB0,
                    bytes((PHASE_RESPONSE_POLICIES[phase].request_control, 0x02)),
                )
                script[position] = replace(
                    step, responses=(bad_ack, *step.responses[1:])
                )
                report, backend = self._run_script(tuple(script))
                self.assertEqual(report["abort_class"], AbortClass.UNEXPECTED_ACK.value)
                self.assertEqual(backend.exchange_count, position + 1)
                self.assertEqual(backend.tls_handshake_count, 0)

    def test_unexpected_order_unrelated_frame_malformed_b0_and_echo_fail_closed(self):
        material, responses = _synthetic_objects()
        base = list(happy_synthetic_script(material, responses))
        cases = {
            "order": (base[1].responses[1], base[1].responses[0]),
            "unrelated": (base[1].responses[0], build_a0(0x82, b"xxxx")),
            "malformed_ack": (b"\xa0\x06\x00\x00" + bytes(6), base[1].responses[1]),
            "unexpected_echo": (build_a0(0xB0, b"\x82\x01"), base[1].responses[1]),
        }
        for index, (name, incoming) in enumerate(cases.items()):
            with self.subTest(name=name):
                script = list(base)
                script[1] = replace(script[1], responses=incoming)
                report, backend = self._run_script(tuple(script))
                self.assertIn(
                    report["abort_class"],
                    (AbortClass.UNEXPECTED_ACK.value, AbortClass.UNEXPECTED_DATA.value),
                )
                self.assertEqual(backend.exchange_count, 2)
                self.assertEqual(backend.tls_handshake_count, 0)

        script = list(base)
        script[-1] = replace(script[-1], responses=(b"\xb0\x05\x00\xb5\x16",))
        report, backend = self._run_script(tuple(script))
        self.assertEqual(report["abort_class"], AbortClass.UNEXPECTED_DATA.value)
        self.assertEqual(backend.exchange_count, 12)
        self.assertEqual(backend.tls_handshake_count, 0)

    def test_coalesced_ack_and_response_is_framed_and_reported_without_payload(self):
        secret_bytes = bytes(range(1, 33))
        material, responses = _synthetic_objects()
        validator = _synthetic_validator(memoryview(secret_bytes))
        responses = replace(responses, e4_validator=validator)
        material = replace(
            material, e4_validator_sha256=hashlib.sha256(validator).hexdigest()
        )
        script = happy_synthetic_script(material, responses, ack_status=0x07)
        incoming = [
            b"".join(step.responses) if len(step.responses) == 2 else step.responses[0]
            for step in script
        ]
        api = FakeUsbApi(incoming)
        secret = SecretBuffer.synthetic(secret_bytes)
        backend = ProductionReplayBackend(
            ProductionUsbTransport(api),
            secret,
            RuntimePskE4Binder(_synthetic_validator),
            tls_factory=ImmediateTlsEngine,
        )
        report = ExactOemReplayStateMachine().run(
            preflight=_preflight(),
            material=material,
            secret=secret,
            backend=backend,
            publisher=DurableReportPublisher(self.root / "coalesced.json"),
        )
        self.assertEqual(report["result"], "abort")  # exact model rejects non-synthetic type

        # Exercise the reviewed production seam directly after the type gate.
        secret = SecretBuffer.synthetic(secret_bytes)
        api = FakeUsbApi(incoming)
        backend = ProductionReplayBackend(
            ProductionUsbTransport(api),
            secret,
            RuntimePskE4Binder(_synthetic_validator),
            tls_factory=ImmediateTlsEngine,
        )
        from src.goodix5125_d233_backend import run_reviewed_backend_offline

        report = run_reviewed_backend_offline(
            preflight=_preflight(),
            material=material,
            secret=secret,
            backend=backend,
            publisher=DurableReportPublisher(self.root / "coalesced-production.json"),
        )
        self.assertEqual(report["result"], "pass")
        e4 = backend.protocol_observations[0]
        self.assertEqual(e4["ack_status"], "0x07")
        self.assertEqual(e4["ordering_classification"], "ack_then_same_control_response")
        self.assertEqual(
            e4["completion_classification"],
            "ack_and_response_same_usb_completion",
        )
        self.assertFalse(any("payload" in key for key in e4))

    def test_d4_and_application_data_remain_unreachable(self):
        material, responses = _synthetic_objects()
        script = happy_synthetic_script(material, responses, ack_status=0x07)
        self.assertNotIn("D4", [step.phase_id for step in script])
        self.assertEqual(script[-1].phase_id, "D1")
        with self.assertRaises(ReplayAbort):
            backend = ScriptedSyntheticBackend(script)
            backend.exchange("D4", b"not-a-request", 1000)


if __name__ == "__main__":
    unittest.main()
