"""Offline-only D245 runtime matrix; execute only in a patched temporary tree."""

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
    build_b0,
    expected_request_frames,
    happy_synthetic_script,
    parse_a0,
)
from src.goodix5125_d233_backend import (
    A8_CANONICAL_REQUEST,
    A8_FIRMWARE_QUERY_PHASE,
    A8_TARGET_RESPONSE_BODY,
    B0TlsBridge,
    ProductionOsPreflight,
    ProductionReplayBackend,
    ProductionUsbTransport,
    TLS_RECORD_PACING_MS,
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


REPOSITORY = Path(__file__).resolve().parents[2]
SECRET = VECTORS["V2"]
A8_ACK01 = build_a0(0xB0, b"\xa8\x01")
A8_ACK07 = build_a0(0xB0, b"\xa8\x07")
A8_RESPONSE = build_a0(0xA8, A8_TARGET_RESPONSE_BODY)


class TwoRecordServerFlight:
    complete = False

    def __init__(self):
        self._drained = False

    def feed(self, _payload):
        pass

    def advance(self):
        pass

    def drain(self):
        if self._drained:
            return ()
        self._drained = True
        return (
            b"\x16\x03\x03\x00\x51\x02\x00\x00\x4d" + bytes(77),
            b"\x16\x03\x03\x00\x04\x0e\x00\x00\x00",
        )


class TimeoutAfterIncomingUsbApi(FakeUsbApi):
    def bulk_in(self, handle, endpoint, maximum, timeout_ms):
        if not self.incoming:
            self.calls.append(("in_timeout", endpoint, timeout_ms))
            raise UsbTimeout("D245 injected bounded timeout")
        return super().bulk_in(handle, endpoint, maximum, timeout_ms)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _normal_frames(*, ack_status: int = 0x01) -> tuple[object, list[bytes]]:
    material, responses = _canonical_objects(SECRET)
    frames = [
        frame
        for step in happy_synthetic_script(material, responses, ack_status=ack_status)
        for frame in step.responses
    ]
    return material, [A8_ACK01, A8_RESPONSE, *frames]


def _run_candidate(
    incoming: list[bytes],
    *,
    api: FakeUsbApi | None = None,
    tls_factory=ImmediateTlsEngine,
    fprintd_active: bool = True,
) -> dict[str, object]:
    material, _responses = _canonical_objects(SECRET)
    usb = api or FakeUsbApi(incoming)
    captured: dict[str, object] = {}
    with tempfile.TemporaryDirectory(prefix="d245-runtime-case-") as directory:
        root = Path(directory)
        facade = FakeOsFacade()
        facade.active = fprintd_active
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
        checkpoint = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
        final = json.loads((root / "final.json").read_text(encoding="utf-8"))
        captured.update(
            report=report,
            checkpoint=checkpoint,
            final=final,
            api=usb,
            facade_calls=tuple(facade.calls),
            restore_count=preflight.restore_count,
        )
    return captured


def _assert_durable(case: dict[str, object], *, active: bool = True) -> None:
    report = case["report"]
    checkpoint = case["checkpoint"]
    _require(report == case["final"], "final durable report differs")
    _require(checkpoint["report_publish_count"] == 1, "checkpoint count")
    _require(report["report_publish_count"] == 2, "final publish count")
    _require(report["cleanup_count"] == 1, "cleanup is not exactly once")
    _require(report["secret_zeroized"] is True, "secret not zeroized")
    _require(case["restore_count"] == 1, "restore is not exactly once")
    calls = case["facade_calls"]
    _require(("restore", "old") in calls, "signal mask not restored")
    _require(("start" in calls) is active, "fprintd restore does not match initial state")


def run_matrix() -> dict[str, object]:
    _require(A8_CANONICAL_REQUEST.hex() == "a00600a6a803000000ff", "A8 bytes")
    _require(len(A8_CANONICAL_REQUEST) == 10, "A8 logical length")
    parsed = parse_a0(A8_CANONICAL_REQUEST)
    _require((parsed.control, parsed.body) == (0xA8, b"\x00\x00"), "A8 parse")

    # T2: both currently admitted E4 ACK statuses continue after the stricter A8 ACK01.
    happy_cases = []
    for e4_ack in (0x01, 0x07):
        material, incoming = _normal_frames(ack_status=e4_ack)
        case = _run_candidate(incoming)
        report = case["report"]
        backend = case["backend"]
        api = case["api"]
        _require(report["result"] == "pass", f"happy E4 ACK {e4_ack:02x}")
        _require(report["runtime_psk_e4_binding_status"] == "match", "E4 binding")
        _require(report["client_hello_observed"] is True, "ClientHello observability")
        _require(report["client_key_exchange_observed"] is False, "unexpected ClientKeyExchange")
        _require(report["tls_handshake_completed"] is True, "TLS completion observability")
        _require(report["command_count"] == 13, "A8 plus exact pre-D1 count")
        _require(api.outgoing[0] == A8_CANONICAL_REQUEST, "A8 not first or not short")
        e4 = expected_request_frames(material)["E4"]
        _require(api.outgoing[1] == e4, "E4 bytes or short-OUT changed")
        phases = [row["phase"] for row in backend.protocol_observations]
        _require(phases == [A8_FIRMWARE_QUERY_PHASE, *EXACT_PHASE_ORDER[:-1]], "phase order")
        _require(phases.count(A8_FIRMWARE_QUERY_PHASE) == 1, "A8 repeated")
        _require(not any(phase == "D4" for phase in phases), "D4 reached")
        _assert_durable(case)
        happy_cases.append(f"E4_ACK_{e4_ack:02X}_PASS")

    # T3/T4/T5: every A8 terminal stops before E4 with granular direction.
    ack07 = _run_candidate([A8_ACK07])
    _require(ack07["report"]["a8_ack_status"] == 7, "ACK07 not observed")
    _require(ack07["report"]["a8_response_observed"] is False, "ACK07 read response")
    _require(ack07["report"]["e4_usb_out_attempted"] is False, "ACK07 sent E4")
    _assert_durable(ack07)

    out_api = FakeUsbApi()
    out_api.timeout_out = True
    out_timeout = _run_candidate([], api=out_api)
    _require(out_timeout["report"]["a8_failure_class"] == "out_timeout", "A8 OUT timeout")
    _require(out_timeout["report"]["a8_usb_in_attempted"] is False, "IN after OUT timeout")
    _require(out_timeout["report"]["e4_usb_out_attempted"] is False, "E4 after OUT timeout")
    _assert_durable(out_timeout)

    in_api = FakeUsbApi()
    in_api.timeout_in = True
    in_timeout = _run_candidate([], api=in_api)
    _require(in_timeout["report"]["a8_usb_out_completed_length"] == 10, "A8 OUT completion lost")
    _require(in_timeout["report"]["a8_failure_class"] == "in_timeout", "A8 IN timeout")
    _require(in_timeout["report"]["e4_usb_out_attempted"] is False, "E4 after IN timeout")
    _assert_durable(in_timeout)

    mismatch_results = []
    for version in (b"GF_ST411SEC_APP_12508\x00", b"GF_ST411SEC_APP_12510\x00"):
        mismatch = _run_candidate([A8_ACK01, build_a0(0xA8, version)])
        report = mismatch["report"]
        _require(report["a8_response_observed"] is True, "valid mismatch not parsed")
        _require(report["a8_firmware_version_match"] is False, "mismatch accepted")
        _require(report["a8_failure_class"] == "firmware_mismatch", "mismatch class")
        _require(report["e4_usb_out_attempted"] is False, "E4 after mismatch")
        _assert_durable(mismatch)
        mismatch_results.append(version[:-1].decode("ascii"))

    # T6: historical fragmentation/coalescing accepted, stale/malformed/order rejected.
    coalesced = _run_candidate([A8_ACK01 + A8_RESPONSE, *_normal_frames()[1][2:]])
    _require(coalesced["report"]["result"] == "pass", "coalesced ACK/response")
    _require(
        coalesced["backend"].protocol_observations[0]["completion_classification"]
        == "ack_and_response_same_usb_completion",
        "coalesced classification",
    )
    fragmented = _run_candidate(
        [A8_ACK01[:3], A8_ACK01[3:], A8_RESPONSE[:7], A8_RESPONSE[7:], *_normal_frames()[1][2:]]
    )
    _require(fragmented["report"]["result"] == "pass", "fragmented A8")
    stale = _run_candidate([A8_ACK01 + A8_RESPONSE + build_a0(0x82, b"stale")])
    _require(stale["report"]["a8_failure_class"] == "stale_or_unowned_frame", "stale accepted")
    _require(stale["report"]["e4_usb_out_attempted"] is False, "E4 after stale")
    wrong_order = _run_candidate([A8_RESPONSE, A8_ACK01])
    _require(wrong_order["report"]["e4_usb_out_attempted"] is False, "E4 after wrong order")
    malformed = bytearray(A8_ACK01)
    malformed[-1] ^= 1
    malformed_case = _run_candidate([bytes(malformed)])
    _require(malformed_case["report"]["e4_usb_out_attempted"] is False, "E4 after malformed")

    # T7: A8 succeeds, E4 OUT completes, and the IN timeout direction is explicit.
    e4_api = TimeoutAfterIncomingUsbApi([A8_ACK01, A8_RESPONSE])
    e4_timeout = _run_candidate([], api=e4_api)
    e4_report = e4_timeout["report"]
    _require(e4_report["e4_usb_out_attempted"] is True, "E4 OUT not attempted")
    _require(e4_report["e4_usb_out_completed_length"] == 16, "E4 OUT not completed")
    _require(e4_report["e4_usb_in_result"] == "timeout", "E4 IN timeout direction")
    _assert_durable(e4_timeout)

    # T9: fixed-64 B0 staging, deterministic zero tail and 10 ms per record.
    pacing: list[float] = []
    tls_api = FakeUsbApi()
    tls_transport = ProductionUsbTransport(tls_api)
    tls_transport.transport_open()
    bridge = B0TlsBridge(TwoRecordServerFlight(), tls_transport, pacer=pacing.append)
    client_body = b"\x03\x03" + bytes(32) + b"\x00\x00\x04\x00\xa8\x00\xff\x01\x00"
    client = b"\x16\x03\x03" + (4 + len(client_body)).to_bytes(2, "big") + b"\x01" + len(client_body).to_bytes(3, "big") + client_body
    bridge.accept_b0(build_b0(client), 1000, first_record=True)
    _require([len(chunk) for chunk in tls_api.outgoing] == [64, 64, 64], "B0 fixed64")
    _require(pacing == [TLS_RECORD_PACING_MS / 1000] * 2, "TLS pacing")
    _require(all(len(chunk) == 64 for chunk in tls_api.outgoing), "physical B0 length")

    # T11: TLS timeout and success both preserve the durable terminal sequence.
    _material, normal = _normal_frames()
    tls_timeout_api = TimeoutAfterIncomingUsbApi(normal)
    tls_timeout = _run_candidate(
        [], api=tls_timeout_api, tls_factory=StalledAfterServerFlightTlsEngine
    )
    _require(tls_timeout["report"]["abort_class"] == AbortClass.TLS_TIMEOUT.value, "TLS timeout")
    _require(tls_timeout["report"]["client_hello_observed"] is True, "timeout ClientHello")
    _require(tls_timeout["report"]["tls_handshake_completed"] is False, "false TLS success")
    _require(tls_timeout["report"]["post_server_flight_bulk_in_call_count"] == 1, "post-flight RX")
    _assert_durable(tls_timeout)

    inactive_success = _run_candidate(_normal_frames()[1], fprintd_active=False)
    _require(inactive_success["report"]["result"] == "pass", "inactive fprintd success")
    _assert_durable(inactive_success, active=False)

    mapped = map_production_report(
        happy_cases and _run_candidate(_normal_frames()[1])["report"],
        ProductionReportPolicy("live_single_shot", "granted", "yes"),
    )
    _require(D235_RESULT_SCHEMA == "d245-live-tls-single-shot-result-v1", "D245 schema")
    _require(mapped["D245_A8_REQUIRED_FOR_E4_IN_THIS_KIT"] is True, "A8 gate mapping")
    _require(mapped["D245_D4_REACHABLE"] is False, "D4 mapping")
    _require(mapped["retry_count"] == 0, "retry mapping")
    paths = ProductionRuntimePaths.system_default()
    _require(paths.report_directory.name == "d245-results", "result namespace")
    _require(paths.single_use_marker.name == "d245-operator-invocation.marker", "marker namespace")

    return {
        "schema": "d245-runtime-matrix-v1",
        "status": "PASS",
        "a8_request_hex": A8_CANONICAL_REQUEST.hex(),
        "happy_cases": happy_cases,
        "firmware_mismatch_cases": mismatch_results,
        "a8_ack07_e4_count": int(ack07["report"]["e4_usb_out_attempted"]),
        "a8_out_timeout_e4_count": int(out_timeout["report"]["e4_usb_out_attempted"]),
        "a8_in_timeout_e4_count": int(in_timeout["report"]["e4_usb_out_attempted"]),
        "e4_timeout_direction": "IN_AFTER_COMPLETED_OUT",
        "full_command_count": 13,
        "server_flight_usb_chunk_lengths": [len(chunk) for chunk in tls_api.outgoing],
        "server_flight_pacing_count": bridge.pacing_count,
        "tls_timeout_durable": True,
        "tls_success_stop_before_d4": True,
        "retry_count": 0,
        "d4_count": 0,
        "application_data_count": 0,
        "persistent_write_family_count": 0,
        "real_usb_access": 0,
    }


def main() -> int:
    print(json.dumps(run_matrix(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
