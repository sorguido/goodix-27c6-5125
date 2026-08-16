from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.goodix5125_d232_offline import (
    AbortClass,
    DurableReportPublisher,
    SecretBuffer,
    build_a0,
    build_b0,
    happy_synthetic_script,
)
from src.goodix5125_d233_backend import (
    ProductionReplayBackend,
    ProductionUsbTransport,
    RuntimePskE4Binder,
    UsbTimeout,
    run_reviewed_backend_offline,
)
from tests.test_d233_backend import (
    FakeUsbApi,
    client_hello_placeholder,
    preflight,
    synthetic_objects,
    synthetic_validator,
)


class CapturingImmediateTlsEngine:
    def __init__(self, secret: SecretBuffer):
        self.secret_object = secret
        self.complete = False
        self.closed = False
        self.handshake_count = 0
        self.feeds: list[bytes] = []

    def feed(self, payload: bytes) -> None:
        self.feeds.append(bytes(payload))

    def advance(self) -> None:
        self.handshake_count = 1
        self.complete = True

    def drain(self) -> tuple[bytes, ...]:
        return ()

    def close(self) -> None:
        self.closed = True


class TimeoutAfterResponsesUsbApi(FakeUsbApi):
    def bulk_in(self, handle, endpoint, maximum, timeout_ms):
        if not self.incoming:
            self.calls.append(("in_timeout", endpoint, timeout_ms))
            raise UsbTimeout("synthetic bounded TLS stall")
        return super().bulk_in(handle, endpoint, maximum, timeout_ms)


class StalledTlsEngine(CapturingImmediateTlsEngine):
    emit_server_flight = False

    def __init__(self, secret: SecretBuffer):
        super().__init__(secret)
        self._drained = False

    def advance(self) -> None:
        self.handshake_count = 1

    def drain(self) -> tuple[bytes, ...]:
        if self.emit_server_flight and not self._drained:
            self._drained = True
            return (b"\x16\x03\x03\x00\x01\x02",)
        return ()


class StalledAfterServerFlightTlsEngine(StalledTlsEngine):
    emit_server_flight = True


class D241DirectB0TransitionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="d241-transition-")
        self.root = Path(self.temporary.name)
        self.secret_bytes = bytes(range(1, 33))
        self.material, self.responses = synthetic_objects(self.secret_bytes)

    def tearDown(self):
        self.temporary.cleanup()

    def _incoming(self, *, d1_frame: bytes | None = None, fragmented: bool = False):
        script = happy_synthetic_script(self.material, self.responses, ack_status=0x07)
        incoming: list[bytes] = []
        for step in script:
            frames = step.responses
            if step.phase_id == "D1" and d1_frame is not None:
                frames = (d1_frame,)
            for frame in frames:
                if fragmented and step.phase_id == "D1":
                    split = max(4, len(frame) // 2)
                    incoming.extend((frame[:split], frame[split:]))
                else:
                    incoming.append(frame)
        return incoming

    def _run(self, incoming, tls_factory=CapturingImmediateTlsEngine, *, api_type=FakeUsbApi):
        api = api_type(incoming)
        secret = SecretBuffer.synthetic(self.secret_bytes)
        engines: list[CapturingImmediateTlsEngine] = []

        def factory(bound_secret: SecretBuffer):
            engine = tls_factory(bound_secret)
            engines.append(engine)
            return engine

        backend = ProductionReplayBackend(
            ProductionUsbTransport(api),
            secret,
            RuntimePskE4Binder(synthetic_validator),
            tls_factory=factory,
        )
        report = run_reviewed_backend_offline(
            preflight=preflight(),
            material=self.material,
            secret=secret,
            backend=backend,
            publisher=DurableReportPublisher(self.root / f"result-{len(list(self.root.iterdir()))}.json"),
        )
        return report, backend, api, engines

    def test_t1_direct_b0_is_handed_to_bridge_once_with_exact_payload(self):
        record = self.responses.tls_client_hello_record
        report, backend, _api, engines = self._run(self._incoming())
        self.assertEqual(report["result"], "pass")
        self.assertNotEqual(report["abort_class"], AbortClass.UNEXPECTED_DATA.value)
        self.assertEqual(backend.first_tls_record_handoff_count, 1)
        self.assertEqual(engines[0].feeds, [record])
        self.assertEqual(backend.tls_trace_redacted[0]["handshake_type_if_verified"], "client_hello")

    def test_t2_usb_completion_fragmentation_reassembles_the_same_stream_once(self):
        record = self.responses.tls_client_hello_record
        report, backend, api, engines = self._run(self._incoming(fragmented=True))
        self.assertEqual(report["result"], "pass")
        self.assertEqual(engines[0].feeds, [record])
        self.assertEqual(backend.first_tls_record_handoff_count, 1)
        self.assertEqual(
            backend.protocol_observations[-1]["completion_classification"],
            "frame_fragmented_across_usb_completions",
        )
        self.assertEqual(sum(call[0] == "in" for call in api.calls if isinstance(call, tuple)), 20)

    def test_t3_first_record_is_not_read_again_or_fed_twice(self):
        report, backend, api, engines = self._run(self._incoming())
        self.assertEqual(report["result"], "pass")
        self.assertEqual(backend.first_tls_record_handoff_count, 1)
        self.assertEqual(len(engines[0].feeds), 1)
        self.assertEqual(sum(call[0] == "in" for call in api.calls if isinstance(call, tuple)), 19)

    def test_t4_malformed_b0_and_tls_record_remain_terminal(self):
        valid = build_b0(self.responses.tls_client_hello_record)
        malformed = (
            valid[:3] + bytes((valid[3] ^ 1,)) + valid[4:],
            build_b0(b"\x16\x03\x03\x00\x09short"),
            build_b0(b"\x17\x03\x03\x00\x00"),
        )
        for index, frame in enumerate(malformed):
            with self.subTest(index=index):
                report, backend, _api, engines = self._run(self._incoming(d1_frame=frame))
                self.assertEqual(report["abort_class"], AbortClass.UNEXPECTED_DATA.value)
                self.assertEqual(backend.first_tls_record_handoff_count, 0)
                self.assertEqual(engines, [])

    def test_t5_unrelated_d1_data_is_rejected(self):
        report, backend, _api, engines = self._run(
            self._incoming(d1_frame=build_a0(0x82, b"unrelated"))
        )
        self.assertEqual(report["abort_class"], AbortClass.UNEXPECTED_DATA.value)
        self.assertEqual(backend.first_tls_record_handoff_count, 0)
        self.assertEqual(engines, [])

    def test_t6_tls_factory_receives_the_same_e4_validated_secret_object(self):
        report, backend, _api, engines = self._run(self._incoming())
        self.assertEqual(report["result"], "pass")
        self.assertEqual(backend.binder.compare_count, 1)
        self.assertTrue(backend.tls_secret_object_identity_verified)
        self.assertIs(engines[0].secret_object, backend.secret)

    def test_legacy_tls_record_version_reaches_openssl_boundary(self):
        record = bytearray(client_hello_placeholder())
        record[1:3] = b"\x03\x01"
        report, backend, _api, engines = self._run(
            self._incoming(d1_frame=build_b0(record))
        )
        self.assertEqual(report["result"], "pass")
        self.assertEqual(backend.first_tls_record_handoff_count, 1)
        self.assertEqual(engines[0].feeds, [bytes(record)])

    def test_t7_t8_forbidden_counts_cleanup_and_zeroization_remain_invariant(self):
        report, backend, api, _engines = self._run(self._incoming())
        self.assertEqual(report["command_count"], 12)
        self.assertNotIn("D4", [item["phase"] for item in backend.protocol_observations])
        self.assertTrue(report["secret_zeroized"])
        self.assertEqual(report["cleanup_count"], 1)
        self.assertEqual(api.calls.count(("release", 0)), 1)
        self.assertEqual(api.calls.count("close"), 1)
        self.assertEqual(api.calls.count("exit"), 1)

    def test_t12_timeout_is_bounded_classified_and_trace_is_redacted(self):
        cases = (
            (StalledTlsEngine, "TLS_HANDSHAKE_TIMEOUT_AFTER_CLIENTHELLO"),
            (StalledAfterServerFlightTlsEngine, "TLS_HANDSHAKE_TIMEOUT_AFTER_SERVER_FLIGHT"),
        )
        for engine, expected in cases:
            with self.subTest(expected=expected):
                report, backend, api, _engines = self._run(
                    self._incoming(), engine, api_type=TimeoutAfterResponsesUsbApi
                )
                self.assertEqual(report["abort_class"], AbortClass.TLS_TIMEOUT.value)
                self.assertEqual(backend.tls_failure_class, expected)
                self.assertEqual(backend.first_tls_record_handoff_count, 1)
                self.assertEqual(report["cleanup_count"], 1)
                self.assertEqual(api.calls.count(("release", 0)), 1)
                budgets = [
                    call[2]
                    for call in api.calls
                    if isinstance(call, tuple)
                    and call[0] in {"in", "in_timeout", "out"}
                ]
                self.assertTrue(budgets)
                self.assertTrue(all(0 < budget <= 3000 for budget in budgets))
                serialized = json.dumps(backend.tls_trace_redacted, sort_keys=True).encode()
                self.assertNotIn(self.secret_bytes, serialized)
                self.assertFalse(any("payload" in row for row in backend.tls_trace_redacted))


if __name__ == "__main__":
    unittest.main()
