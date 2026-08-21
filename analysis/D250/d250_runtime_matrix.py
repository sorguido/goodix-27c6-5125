# SPDX-License-Identifier: GPL-2.0-or-later
"""D250 synthetic D4 -> exactly-one AF runtime matrix.

Run only after the D245, D246 and D250 patches have been applied in a
temporary tree.  No system USB implementation or protected input is used.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from core.post_d4 import (
    PLAIN,
    _checksum,
    build_af,
    build_cached_image,
    build_fdt_down,
    build_set_image,
)
from poc.goodix5125.tools.binding_reference.known_answers import VECTORS
from src.goodix5125_d232_offline import (
    AbortClass,
    DurableReportPublisher,
    EXACT_PHASE_ORDER,
    ReplayAbort,
    SecretBuffer,
    build_a0,
    happy_synthetic_script,
)
from src.goodix5125_d233_backend import (
    A8_FIRMWARE_QUERY_PHASE,
    A8_TARGET_RESPONSE_BODY,
    AF_PHASE,
    D4_CANONICAL_REQUEST,
    D4_PHASE,
    ProductionOsPreflight,
    ProductionReplayBackend,
    ProductionUsbTransport,
    UsbAmbiguousCompletion,
    UsbIdentity,
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
AF_TS16 = 0x67B2


def payload(control: int, data: bytes, checksum: int | None = None) -> bytes:
    size = len(data) + 1
    check = _checksum(control, data) if checksum is None else checksum
    return bytes((control, size & 0xFF, size >> 8)) + data + bytes((check,))


def outer(body: bytes) -> bytes:
    return bytes((PLAIN, len(body) & 0xFF, len(body) >> 8, (PLAIN + len(body)) & 0xFF)) + body


def ae_response(flags: int = 0x02, *, version: int = 1, size: int = 16) -> bytes:
    data = (bytes((version, flags)) + bytes(14))[:size].ljust(size, b"\x00")
    return outer(payload(0xAE, data))


def af_ack() -> bytes:
    return outer(payload(0xB0, b"\xaf\x01"))


class TimeoutAfterIncomingUsbApi(FakeUsbApi):
    def bulk_in(self, handle, endpoint, maximum, timeout_ms):
        if not self.incoming:
            self.calls.append(("in_timeout", endpoint, timeout_ms))
            raise UsbTimeout("D250 injected bounded timeout")
        return super().bulk_in(handle, endpoint, maximum, timeout_ms)


class AmbiguousAfCompletionApi(FakeUsbApi):
    def bulk_out(self, handle, endpoint, data, timeout_ms):
        wire = bytes(data)
        if wire[:13] == build_af(AF_TS16):
            self.calls.append(("af_out_ambiguous", endpoint, timeout_ms))
            self.outgoing.append(wire)
            return len(wire) - 1
        return super().bulk_out(handle, endpoint, wire, timeout_ms)


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
    d4_pacing: list[float] = []
    af_pacing: list[float] = []
    with tempfile.TemporaryDirectory(prefix="d250-runtime-case-") as directory:
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
                d4_pacer=d4_pacing.append,
                af_pacer=af_pacing.append,
                af_timestamp_factory=lambda: AF_TS16,
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
            d4_pacing=d4_pacing,
            af_pacing=af_pacing,
        )
    return captured


def assert_cleanup(case: dict[str, object]) -> None:
    report = case["report"]
    require(report == case["final"], "final durable report differs")
    require(report["cleanup_count"] == 1, "cleanup not exactly once")
    require(report["secret_zeroized"] is True, "secret not zeroized")
    require(case["restore_count"] == 1, "restore not exactly once")
    require(("restore", "old") in case["facade_calls"], "signals not restored")
    require("close" in case["api"].calls, "USB handle not closed")


def boundary_out_counts(case: dict[str, object]) -> tuple[int, int]:
    d4 = 0
    af = 0
    for wire in case["api"].outgoing:
        if len(wire) != 64:
            continue
        if wire[:10] == D4_CANONICAL_REQUEST:
            d4 += 1
        if wire[:13] == build_af(AF_TS16):
            af += 1
    return d4, af


def assert_terminal_counts(case: dict[str, object], *, af_response_count: int) -> None:
    report = case["report"]
    require(report["d4_attempt_count"] == 1, "D4 attempt count")
    require(report["d4_send_count"] == 1, "D4 send count")
    require(report["af_attempt_count"] == 1, "AF attempt count")
    require(report["af_response_count"] == af_response_count, "AF response count")
    require(boundary_out_counts(case) == (1, 1), "D4/AF physical multiplicity")
    assert_cleanup(case)


def run_matrix() -> dict[str, object]:
    tests: dict[str, str] = {}

    tls_api = TimeoutAfterIncomingUsbApi(normal_frames())
    tls_stop = run_case([], api=tls_api, tls_factory=StalledAfterServerFlightTlsEngine)
    require(tls_stop["report"]["abort_class"] == AbortClass.TLS_TIMEOUT.value, "TLS regression")
    require(tls_stop["report"]["d4_attempt_count"] == 0, "TLS reached D4")
    require(tls_stop["report"]["af_attempt_count"] == 0, "TLS reached AF")
    assert_cleanup(tls_stop)
    tests["T1_D245_D246_PREDECESSOR_REGRESSION"] = "PASS_STOP_BEFORE_D4_AF"

    happy = run_case([*normal_frames(), D4_ACK, ae_response(0x32)])
    report = happy["report"]
    backend = happy["backend"]
    require(report["result"] == "pass", "happy result")
    require(report["d4_completed"] is True and report["af_completed"] is True, "happy completion")
    require(report["af_send_count"] == 1 and report["af_response_count"] == 1, "happy AF")
    require(report["af_state_version"] == 1, "state version not recorded")
    require(report["af_state_flags"] == 0x32, "state flags not preserved")
    require(report["af_unknown_flag_bits"] == 0x30, "unknown flags not preserved")
    require(happy["d4_pacing"] == [0.02] and happy["af_pacing"] == [0.02], "pacing")
    require(happy["api"].outgoing[-1][13:] == bytes(51), "AF tail is not zero")
    phases = [row["phase"] for row in backend.protocol_observations]
    require(phases == [A8_FIRMWARE_QUERY_PHASE, *EXACT_PHASE_ORDER[:-1], D4_PHASE, AF_PHASE], "phase order")
    require(boundary_out_counts(happy) == (1, 1), "happy boundary count")
    mapped = map_production_report(report, ProductionReportPolicy("offline_dry_run", "not_applicable", "no"))
    require(mapped["decision"] == "D250_AF_RESPONSE_VALIDATED_STOP_AFTER_AF", "decision mapping")
    require(mapped["D250_STOP_BOUNDARY"] == "STOP_AFTER_AF", "terminal mapping")
    require(mapped["retry_count"] == 0 and mapped["persistent_write_family_count"] == 0, "safety counters")
    assert_terminal_counts(happy, af_response_count=1)
    tests["T2_D4_AF_AE_HAPPY"] = "PASS_STOP_AFTER_AF"

    timeout = run_case([], api=TimeoutAfterIncomingUsbApi([*normal_frames(), D4_ACK]))
    require(timeout["report"]["af_failure_class"] == "response_timeout", "AF timeout class")
    assert_terminal_counts(timeout, af_response_count=0)
    tests["T3_AF_TIMEOUT"] = "PASS_BOUNDED_NO_RETRY"

    ambiguous_api = AmbiguousAfCompletionApi([*normal_frames(), D4_ACK])
    ambiguous = run_case([], api=ambiguous_api)
    require(ambiguous["report"]["af_failure_class"] == "ambiguous_usb_completion", "ambiguous class")
    require(ambiguous["report"]["af_send_count"] == 0, "ambiguous marked sent")
    before = tuple(ambiguous_api.outgoing)
    try:
        ambiguous["backend"]._exchange_af_after_d4()
    except ReplayAbort as exc:
        require(exc.abort_class == AbortClass.EXTRA_OR_REORDERED, "ambiguous re-entry class")
    else:
        raise AssertionError("ambiguous AF re-entry unexpectedly succeeded")
    require(tuple(ambiguous_api.outgoing) == before, "ambiguous re-entry wrote again")
    require(ambiguous["backend"].af_attempt_count == 1, "attempt latch changed")
    require(boundary_out_counts(ambiguous) == (1, 1), "ambiguous physical attempts")
    assert_cleanup(ambiguous)
    tests["T4_AMBIGUOUS_COMPLETION"] = "PASS_ATTEMPT_LATCHED_NO_REENTRY"

    unexpected_ack = run_case([*normal_frames(), D4_ACK, af_ack()])
    require(unexpected_ack["report"]["af_failure_class"] == "unexpected_ack", "AF ACK accepted")
    assert_terminal_counts(unexpected_ack, af_response_count=0)
    tests["T5_UNEXPECTED_AF_ACK"] = "PASS_FAIL_CLOSED"

    malformed_cases = {
        "short": ae_response(size=15),
        "long": ae_response(size=17),
        "wrong_control": outer(payload(0xAC, bytes(16))),
        "bad_checksum": outer(payload(0xAE, bytes(16), checksum=0)),
    }
    for name, response in malformed_cases.items():
        case = run_case([*normal_frames(), D4_ACK, response])
        require(case["report"]["af_failure_class"] == "malformed_ae_response", f"malformed {name}")
        assert_terminal_counts(case, af_response_count=0)
    tests["T6_MALFORMED_AE_MATRIX"] = "PASS_LENGTH_CONTROL_CHECKSUM"

    version_mismatch = run_case([*normal_frames(), D4_ACK, ae_response(version=2)])
    require(
        version_mismatch["report"]["af_failure_class"]
        == "semantic_state_version_mismatch",
        "AF state version mismatch classification",
    )
    require(version_mismatch["report"]["af_state_version"] is None, "unexpected version accepted")
    assert_terminal_counts(version_mismatch, af_response_count=0)
    tests["T7_STATE_VERSION_MISMATCH"] = "PASS_FAIL_CLOSED_STOP_AFTER_AF"

    duplicate = run_case([*normal_frames(), D4_ACK, ae_response() + ae_response()])
    require(duplicate["report"]["af_failure_class"] == "unexpected_trailing_frame", "duplicate AE")
    require(duplicate["report"]["af_response_count"] == 1, "first AE not recorded")
    assert_terminal_counts(duplicate, af_response_count=1)
    tests["T8_DUPLICATE_COALESCED_RESPONSE"] = "PASS_FAIL_CLOSED"

    trailing_api = FakeUsbApi([*normal_frames(), D4_ACK, ae_response(), build_a0(0xB0, b"\x32\x01")])
    trailing = run_case([], api=trailing_api)
    require(trailing["report"]["result"] == "pass", "unowned trailing changed AF result")
    require(len(trailing_api.incoming) == 1, "unowned frame was consumed")
    require(trailing_api.outgoing[-1][:13] == build_af(AF_TS16), "command after AF")
    before = tuple(trailing_api.outgoing)
    for forbidden in (build_fdt_down(bytes(12), 1), build_set_image(), build_cached_image()):
        try:
            trailing["backend"].exchange("POST_AF", forbidden, 500)
        except ReplayAbort as exc:
            require(exc.abort_class == AbortClass.EXTRA_OR_REORDERED, "post-AF class")
        else:
            raise AssertionError("post-AF sensor command unexpectedly reachable")
    require(tuple(trailing_api.outgoing) == before, "post-AF command emitted")
    assert_terminal_counts(trailing, af_response_count=1)
    tests["T9_TRAILING_UNOWNED_AND_POST_AF_FENCE"] = "PASS_UNCONSUMED_NO_SENSOR_ACTION"

    try:
        happy["backend"]._exchange_af_after_d4()
    except ReplayAbort as exc:
        require(exc.abort_class == AbortClass.EXTRA_OR_REORDERED, "second AF class")
    else:
        raise AssertionError("second AF unexpectedly reachable")
    require(boundary_out_counts(happy) == (1, 1), "second AF wrote")
    tests["T10_SECOND_AF"] = "PASS_UNREACHABLE"

    require(D235_RESULT_SCHEMA == "d250-live-af-single-shot-result-v1", "D250 schema")
    paths = ProductionRuntimePaths.system_default()
    require(paths.report_directory.name == "d250-results", "D250 result namespace")
    require(paths.single_use_marker.name == "d250-operator-invocation.marker", "D250 marker")

    return {
        "schema": "d250-runtime-matrix-v1",
        "status": "PASS",
        "tests": tests,
        "synthetic_af_success_count": 2,
        "real_usb_open_count": 0,
        "real_tls_handshake_count": 0,
        "real_d4_send_count": 0,
        "real_af_attempt_count": 0,
        "real_af_send_count": 0,
        "retry_count": 0,
        "persistent_write_family_count": 0,
        "terminal_boundary": "STOP_AFTER_AF",
    }


def main() -> int:
    print(json.dumps(run_matrix(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
