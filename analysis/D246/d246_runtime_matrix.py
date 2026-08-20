"""Offline-only D246 runtime matrix; run only in the patched temporary tree."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from poc.goodix5125.tools.binding_reference.known_answers import VECTORS
from src.goodix5125_d232_offline import (
    AbortClass,
    DurableReportPublisher,
    EXACT_PHASE_ORDER,
    SecretBuffer,
    build_a0,
    happy_synthetic_script,
)
from src.goodix5125_d233_backend import (
    A8_FIRMWARE_QUERY_PHASE,
    A8_TARGET_RESPONSE_BODY,
    D4_CANONICAL_REQUEST,
    D4_PHASE,
    ProductionOsPreflight,
    ProductionReplayBackend,
    ProductionUsbTransport,
    UsbTimeout,
    run_production_candidate_offline,
)
from src.goodix5125_d235_entrypoint import (
    D235_RESULT_SCHEMA,
    ProductionReportPolicy,
    ProductionRuntimePaths,
    map_production_report,
)
from tests.test_d233_backend import FakeOsFacade, FakeUsbApi, ImmediateTlsEngine
from tests.test_d233_closure import CANONICAL_PE, _canonical_objects
from tests.test_d241_transition import StalledAfterServerFlightTlsEngine


SECRET = VECTORS["V2"]
D4_ACK = build_a0(0xB0, b"\xd4\x01")


class TimeoutAfterIncomingUsbApi(FakeUsbApi):
    def bulk_in(self, handle, endpoint, maximum, timeout_ms):
        if not self.incoming:
            self.calls.append(("in_timeout", endpoint, timeout_ms))
            raise UsbTimeout("D246 injected bounded timeout")
        return super().bulk_in(handle, endpoint, maximum, timeout_ms)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def normal_frames() -> list[bytes]:
    material, responses = _canonical_objects(SECRET)
    pre_d1 = [
        frame
        for step in happy_synthetic_script(material, responses)
        for frame in step.responses
    ]
    return [
        build_a0(0xB0, b"\xa8\x07"),
        build_a0(0xA8, A8_TARGET_RESPONSE_BODY),
        *pre_d1,
    ]


def run_case(
    incoming: list[bytes],
    *,
    api: FakeUsbApi | None = None,
    tls_factory=ImmediateTlsEngine,
) -> dict[str, object]:
    material, _responses = _canonical_objects(SECRET)
    usb = api or FakeUsbApi(incoming)
    captured: dict[str, object] = {}
    pacing: list[float] = []
    with tempfile.TemporaryDirectory(prefix="d246-runtime-case-") as directory:
        root = Path(directory)
        facade = FakeOsFacade()
        facade.active = True
        preflight = ProductionOsPreflight(
            facade,
            operator_uid=1000,
            device_path=Path("/dev/injected-goodix"),
            marker=root / "marker",
            report=(root / "final.json").absolute(),
        )

        def backend_factory(secret, binder):
            backend = ProductionReplayBackend(
                ProductionUsbTransport(usb),
                secret,
                binder,
                tls_factory=tls_factory,
                tls_pacer=lambda _delay: None,
                d4_pacer=pacing.append,
            )
            captured["backend"] = backend
            return backend

        report = run_production_candidate_offline(
            preflight_tx=preflight,
            material_loader=lambda: material,
            secret_loader=lambda: SecretBuffer.synthetic(SECRET),
            canonical_pe_path=CANONICAL_PE,
            backend_factory=backend_factory,
            checkpoint_publisher=DurableReportPublisher(root / "checkpoint.json"),
            final_publisher=DurableReportPublisher(root / "final.json"),
        )
        captured.update(
            report=report,
            final=json.loads((root / "final.json").read_text(encoding="utf-8")),
            api=usb,
            facade_calls=tuple(facade.calls),
            restore_count=preflight.restore_count,
            pacing=pacing,
        )
    return captured


def assert_cleanup(case: dict[str, object]) -> None:
    report = case["report"]
    require(report == case["final"], "final durable report differs")
    require(report["cleanup_count"] == 1, "cleanup not exactly once")
    require(report["secret_zeroized"] is True, "secret not zeroized")
    require(case["restore_count"] == 1, "restore not exactly once")
    require(("restore", "old") in case["facade_calls"], "signal mask not restored")
    require("close" in case["api"].calls, "USB handle not closed")


def d4_out_count(case: dict[str, object]) -> int:
    return sum(
        1
        for chunk in case["api"].outgoing
        if len(chunk) == 64 and chunk[:10] == D4_CANONICAL_REQUEST
    )


def run_matrix() -> dict[str, object]:
    tests: dict[str, str] = {}

    # T1: the D245 boundary is unchanged when TLS does not complete.
    tls_api = TimeoutAfterIncomingUsbApi(normal_frames())
    tls_stop = run_case([], api=tls_api, tls_factory=StalledAfterServerFlightTlsEngine)
    tls_report = tls_stop["report"]
    require(tls_report["abort_class"] == AbortClass.TLS_TIMEOUT.value, "T1 TLS timeout")
    require(tls_report["d4_send_count"] == 0, "T1 reached D4")
    require(tls_report["d4_send_count"] == 0, "T1 retry-equivalent D4 count")
    assert_cleanup(tls_stop)
    tests["T1_D245_TLS_REGRESSION"] = "PASS_STOP_BEFORE_D4"

    # T2: one exact fixed-64 D4, one exact ACK, then STOP_AFTER_D4.
    happy = run_case([*normal_frames(), D4_ACK])
    report = happy["report"]
    backend = happy["backend"]
    outgoing = happy["api"].outgoing
    require(report["result"] == "pass", "T2 result")
    require(report["tls_handshake_completed"] is True, "T2 TLS")
    require(report["d4_send_count"] == 1 and report["d4_completed"] is True, "T2 D4")
    require(report["d4_ack_status"] == 1 and report["d4_response_count"] == 0, "T2 ACK")
    require(report["command_count"] == 14, "T2 command count")
    require(len(outgoing[-1]) == 64, "T2 physical length")
    require(outgoing[-1][:10] == D4_CANONICAL_REQUEST, "T2 exact D4")
    require(outgoing[-1][10:] == bytes(54), "T2 nonzero tail")
    phases = [row["phase"] for row in backend.protocol_observations]
    require(phases == [A8_FIRMWARE_QUERY_PHASE, *EXACT_PHASE_ORDER[:-1], D4_PHASE], "T2 phase order")
    require(phases.count(D4_PHASE) == 1, "T2 repeated D4")
    require(happy["pacing"] == [0.02], "T2 pacing")
    assert_cleanup(happy)
    tests["T2_D4_ONCE_HAPPY"] = "PASS_STOP_AFTER_D4"

    mapped = map_production_report(
        report, ProductionReportPolicy("offline_dry_run", "not_applicable", "no")
    )
    require(mapped["d246_result"] == "D4_EXACTLY_ONCE_STOP_AFTER_D4", "T2 mapping")
    require(mapped["application_data_count"] == 0, "T2 application data")
    require(mapped["persistent_write_family_count"] == 0, "T2 persistent write")
    require(mapped["retry_count"] == 0, "T2 mapped retry")

    # T3: D4 ACK timeout is bounded and never retried.
    timeout_api = TimeoutAfterIncomingUsbApi(normal_frames())
    timeout = run_case([], api=timeout_api)
    timeout_report = timeout["report"]
    require(timeout_report["tls_handshake_completed"] is True, "T3 TLS")
    require(timeout_report["d4_send_count"] == 1, "T3 D4 count")
    require(timeout_report["d4_failure_class"] == "ack_timeout", "T3 class")
    require(d4_out_count(timeout) == 1, "T3 retry")
    assert_cleanup(timeout)
    tests["T3_D4_TIMEOUT"] = "PASS_NO_RETRY_CLEANUP_RESEAL"

    # T4: any ACK other than the capture-proven d4/01 pair fails closed.
    wrong = run_case([*normal_frames(), build_a0(0xB0, b"\xd4\x07")])
    require(wrong["report"]["d4_send_count"] == 1, "T4 D4 count")
    require(wrong["report"]["d4_failure_class"] == "unexpected_ack", "T4 class")
    require(d4_out_count(wrong) == 1, "T4 retry")
    assert_cleanup(wrong)
    tests["T4_UNEXPECTED_ACK"] = "PASS_FAIL_CLOSED"

    # T5: coalesced trailing protocol data cannot authorize a next action.
    trailing = run_case([*normal_frames(), D4_ACK + build_a0(0xAF, b"\x00\x00")])
    trailing_report = trailing["report"]
    require(trailing_report["d4_send_count"] == 1, "T5 D4 count")
    require(trailing_report["d4_failure_class"] == "unexpected_trailing_frame", "T5 class")
    require(d4_out_count(trailing) == 1, "T5 host action after D4")
    require(trailing["api"].outgoing[-1][:10] == D4_CANONICAL_REQUEST, "T5 terminal OUT")
    require(d4_out_count(trailing) == 1, "T5 retry")
    assert_cleanup(trailing)
    tests["T5_NOTHING_AFTER_D4"] = "PASS_NEXT_ACTION_UNREACHABLE"

    require(D235_RESULT_SCHEMA == "d246-live-d4-single-shot-result-v1", "D246 schema")
    paths = ProductionRuntimePaths.system_default()
    require(paths.report_directory.name == "d246-results", "D246 result namespace")
    require(paths.single_use_marker.name == "d246-operator-invocation.marker", "D246 marker")

    return {
        "schema": "d246-runtime-matrix-v1",
        "status": "PASS",
        "tests": tests,
        "synthetic_d4_success_count": 1,
        "real_usb_open_count": 0,
        "real_tls_handshake_count": 0,
        "real_d4_send_count": 0,
        "persistent_write_family_count": 0,
    }


def main() -> int:
    print(json.dumps(run_matrix(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
