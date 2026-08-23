#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Execute the D257 lifecycle/seed/image scenarios without opening USB.

Private D255 cache and pcapng inputs are read by reference and never copied to
the output.  The emitted JSON contains hashes, booleans, counts and lifecycle
events, but no raw cache, OTP, seed, USB payload or biometric material.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("repository root not found")


REPO = find_repo_root(Path(__file__))

import sys

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from analysis.D255 import d255_postprocess_windows_evidence as d255
from analysis.D257 import d257_exact_bootstrap_audit as exact_audit
from core.fdt_lifecycle import (
    EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE,
    FIRST_FDT36_COMMAND_TIMEOUT_MS,
    ExactFreshFdtBootstrapMachine,
    FdtLifecycle,
    FreshFdtBootstrapMachine,
)
from core.fdt_seed import CRC_OFFSET, FDT12_OFFSET, NAV_OFFSET, provide_fdt12
from core.post_d4 import (
    FIRST_IMAGE_RECEIVED,
    InvalidTransition,
    PLAIN,
    FirstImageMachine,
    _checksum,
    parse_outer,
    parse_payload,
)
from src.goodix5125_cleanroom import crc32_mpeg2, encode_synthetic_record


D255_RUN = Path("captures/D255_20260822T205631772Z_85c8c41f")
D255_EVIDENCE = Path("analysis/D255/D255_recovered_postprocess/D255_sanitized_evidence.json")
D256_DECISION = Path("analysis/D256/D256_decision.json")
D253_DECISION = Path("analysis/D253/D253_decision.json")
D249_REPORT = Path("analysis/D249/D249_rocky_assisted_af_fdt_first_image.md")
D230_CAPTURE = Path("analysis/D230/work/GoodixExport/rilevamento.pcapng")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


class ScriptedTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[bytes] = []
        self.timeouts: list[int | None] = []

    def exchange(self, request: bytes, *, timeout_ms: int | None = None):
        self.requests.append(request)
        self.timeouts.append(timeout_ms)
        require(bool(self.responses), "unexpected offline transport exchange")
        return self.responses.pop(0)


def _payload(control: int, data: bytes) -> bytes:
    size = len(data) + 1
    return bytes((control, size & 0xFF, size >> 8)) + data + bytes((_checksum(control, data),))


def _outer(payload: bytes) -> bytes:
    return bytes((PLAIN, len(payload) & 0xFF, len(payload) >> 8, (PLAIN + len(payload)) & 0xFF)) + payload


def _ack(echo: int) -> bytes:
    return _outer(_payload(0xB0, bytes((echo, 1))))


def _af_response() -> bytes:
    return _outer(_payload(0xAE, bytes((0, 0x02)) + bytes(14)))


def _irq2() -> bytes:
    return _payload(0x32, b"\x02\x00\x3f\x00" + bytes(12))


def _synthetic_raster() -> tuple[int, ...]:
    return tuple((index * 31 + index // 80 * 13) & 0xFFF for index in range(5120))


def _synthetic_image_payload() -> bytes:
    record = encode_synthetic_record(_synthetic_raster())
    return _payload(0x20, b"\x01\x00\x00\x00\x00" + record)


def _load_d255(repo: Path):
    run = repo / D255_RUN
    manifest = run / "recovery_manifest.json"
    manifest_hash = (run / "recovery_manifest.json.sha256").read_text(encoding="ascii").split()[0]
    inputs = d255.load_manifest(run, manifest, manifest_hash)
    wire = next(row for row in inputs if row.role == "wire")
    packets = list(d255.iter_usbpcap(wire.path))
    frames = d255.split_frames(packets)
    selected, firmware, target_specific = d255.select_device(frames, None)
    require(target_specific and firmware == d255.EXPECTED_FIRMWARE, "D255 target identity gate failed")
    target_frames = [frame for frame in frames if (frame.bus, frame.device) == selected]
    otp = d255.device_otp(target_frames, selected)
    require(otp is not None and len(otp) == 64, "D255 OTP identity unavailable")
    caches = [row for row in inputs if row.role == "cache_before" and row.path.stat().st_size == 13_520]
    require(len(caches) == 1, "expected one D255 13520-byte cache")
    return run, wire, target_frames, otp, caches[0]


def _decoded(target_frames):
    return [(frame, parsed) for frame in target_frames if (parsed := d255.parse_a0(frame))]


def _next_ack(records, start_position: int, echo: int):
    for frame, parsed in records[start_position + 1:]:
        if frame.direction == "IN" and parsed[0] == 0xB0 and parsed[1] == bytes((echo, 1)):
            return frame
    raise RuntimeError(f"missing D255 ACK for 0x{echo:02x}")


def scenario_d255(repo: Path) -> tuple[dict[str, object], dict[str, object]]:
    run, wire, target_frames, otp, cache = _load_d255(repo)
    records = _decoded(target_frames)
    positions = {id(frame): index for index, (frame, _parsed) in enumerate(records)}
    manual = [(frame, parsed) for frame, parsed in records
              if frame.direction == "OUT" and parsed[0] == 0x36]
    arms = [(frame, parsed) for frame, parsed in records
            if frame.direction == "OUT" and parsed[0] == 0x32]
    events = [(frame, parsed) for frame, parsed in records
              if frame.direction == "IN" and parsed[0] == 0x36
              and len(parsed[1]) >= 2 and int.from_bytes(parsed[1][:2], "little") == 0x100]
    af_states = [(frame, parsed) for frame, parsed in records
                 if frame.direction == "IN" and parsed[0] == 0xAE and len(parsed[1]) == 16]
    require(len(manual) == 3 and len(events) == 3 and len(arms) == 3, "D255 FDT census changed")
    require(any(not (parsed[1][1] & 1) for _frame, parsed in af_states), "D255 fresh AF state absent")

    cache_before_hash = sha256_file(cache.path)
    cache_before_stat = cache.path.stat()
    provider = provide_fdt12(cache.path, otp)
    require(provider.ok, f"D255 seed provider failed: {provider.failure_reason}")
    first_wire_seed = manual[0][1][1][2:14]
    require(provider.require_seed() == first_wire_seed, "D255 cache FDT12 does not match first wire seed")

    # Use the two arms bounded by the observed cancel/re-entry contract.  The
    # earlier arm belongs to the setup projection and is not conflated with the
    # operator's cancel window.
    lifecycle_arms = arms[-2:]
    response_rows = []
    for frame, _parsed in manual:
        response_rows.append([_next_ack(records, positions[id(frame)], 0x36).raw])
    for frame, _parsed in lifecycle_arms:
        response_rows.append([_next_ack(records, positions[id(frame)], 0x32).raw])

    transport = ScriptedTransport(response_rows)
    lifecycle = FdtLifecycle()
    lifecycle.observe_af_state(False)
    candidate = FreshFdtBootstrapMachine(transport, lifecycle)
    candidate.begin(provider)
    for event_frame, _parsed in events:
        candidate.manual_sample(event_frame.raw[4:])

    first_ts16 = int.from_bytes(lifecycle_arms[0][1][1][-2:], "little")
    second_ts16 = int.from_bytes(lifecycle_arms[1][1][1][-2:], "little")
    candidate.arm(first_ts16)

    d256_decision = json.loads((repo / D256_DECISION).read_text(encoding="utf-8"))
    reentry = d256_decision["lifecycle_contract"]["decision"]
    terminal = d256_decision["terminal_cancel_contract"]["decision"]
    require(reentry["REENTRY_WITHOUT_EXPLICIT_USB_RESTORE_PROVEN"] is True,
            "D256 re-entry contract is not closed")
    require(reentry["RESTORE_REQUIRED_FOR_REENTRY"] is False,
            "D256 unexpectedly requires restore")
    candidate.cancel_pending_receive()
    candidate.reenter_and_arm(second_ts16)
    require(terminal["OEM_TERMINAL_CANCEL_USB_QUIESCENCE_PROVEN"] is True,
            "D256 terminal quiescence contract is not closed")
    candidate.terminal_cancel_and_stop()

    expected_requests = [frame.raw for frame, _parsed in manual + lifecycle_arms]
    require(transport.requests == expected_requests, "D255 projected FDT requests are not wire-exact")
    require(not transport.responses, "unused D255 offline responses")
    cache_after_stat = cache.path.stat()
    require(sha256_file(cache.path) == cache_before_hash, "D255 cache changed during replay")
    require(cache_before_stat.st_mtime_ns == cache_after_stat.st_mtime_ns,
            "D255 cache mtime changed during replay")

    scenario = {
        "name": "D255_FRESH_BOOTSTRAP_CANCEL_REENTRY_TERMINAL_STOP",
        "provenance_class": "PRIVATE_D255_APP12509_CAPTURE_AND_CACHE_PROJECTED_FDT_SUBSEQUENCE",
        "source_capture_sha256": sha256_file(wire.path),
        "source_cache_sha256": cache_before_hash,
        "source_cache_bytes": cache.path.stat().st_size,
        "seed_provider_result": provider.status,
        "seed_provider_provenance": provider.provenance.redacted(),
        "cache_fdt12_equals_first_wire_seed": True,
        "manual_stage_count": candidate.manual_stage,
        "manual_requests_wire_exact": transport.requests[:3] == expected_requests[:3],
        "cancel_host_only": True,
        "reentry_requests_wire_exact": transport.requests[3:] == expected_requests[3:],
        "terminal_stop": lifecycle.state.value,
        "cache_modified": False,
        "lifecycle": lifecycle.audit(),
        "raw_seed_exported": False,
        "raw_otp_exported": False,
        "raw_payload_exported": False,
    }
    return scenario, {
        "run": run,
        "cache": cache,
        "cache_hash": cache_before_hash,
    }


def scenario_first_image(repo: Path) -> dict[str, object]:
    d253 = json.loads((repo / D253_DECISION).read_text(encoding="utf-8"))
    require(d253["image_command"]["post_irq2_image_command"] == "0x22_DATA_0100",
            "D253 target image command fact changed")
    transport = ScriptedTransport(([_af_response()], [_ack(0x32)], [_ack(0x22)]))
    lifecycle = FdtLifecycle()
    machine = FirstImageMachine(transport, lifecycle=lifecycle)
    require(machine.query_state(1).pov_valid is False, "synthetic AF did not select fresh path")
    machine.begin_capture(bytes(range(12)), 2)
    require(machine.receive_payload(_irq2()) is None, "IRQ2 did not trigger image command")
    image = machine.receive_payload(_synthetic_image_payload())
    require(machine.phase == FIRST_IMAGE_RECEIVED and image == _synthetic_raster(),
            "first-image offline closure failed")
    controls = [parse_payload(parse_outer(request)[1])[0] for request in transport.requests]
    return {
        "name": "TARGET_IRQ2_0x22_FIRST_IMAGE",
        "provenance_class": "D230_D253_TARGET_PROTOCOL_FACTS_PLUS_D249_SYNTHETIC_IMAGE_CODEC_FIXTURE",
        "distinct_from_scenario_1": True,
        "target_capture_reference_sha256": sha256_file(repo / D230_CAPTURE),
        "d253_decision_sha256": sha256_file(repo / D253_DECISION),
        "d249_report_sha256": sha256_file(repo / D249_REPORT),
        "request_controls": [f"0x{value:02x}" for value in controls],
        "irq2_0x22_count": controls.count(0x22),
        "first_image_received": True,
        "image_pixel_count": len(image),
        "image_fixture_class": "SYNTHETIC_NON_BIOMETRIC",
        "lifecycle": lifecycle.audit(),
        "raw_biometric_exported": False,
    }


def scenario_exact_target_blocked(
    repo: Path,
    context: dict[str, object],
    audit: dict[str, object],
) -> dict[str, object]:
    """Exercise the exact candidate until the first unavailable host gate."""
    _run, _wire, target_frames, otp, _cache = _load_d255(repo)
    by_frame = {frame.packet_index + 1: frame for frame in target_frames}
    rows = audit["timeline"]["rows"]

    def frame_for(event_class: str):
        row = next(row for row in rows if row["event_class"] == event_class)
        return by_frame[int(row["frame"])]

    first_request = frame_for("FDT36_STAGE_0_REQUEST")
    first_ack = frame_for("ACK_0x36_STATUS_01")
    first_event = frame_for("IRQ_0x0100_TOUCH_0")
    nav_request = frame_for("INTERSTAGE_NAV_0x50_REQUEST")
    nav_ack = frame_for("ACK_0x50_STATUS_01")
    nav_response = frame_for("INTERSTAGE_NAV_0x50_RESPONSE")

    provider = provide_fdt12(context["cache"].path, otp)
    require(provider.ok, "D255 exact candidate seed provider failed")
    transport = ScriptedTransport(([first_ack.raw], [nav_ack.raw, nav_response.raw]))
    lifecycle = FdtLifecycle()
    lifecycle.observe_af_state(False)
    candidate = ExactFreshFdtBootstrapMachine(transport, lifecycle)
    candidate.begin(provider)
    candidate.manual_sample(first_event.raw[4:])
    try:
        candidate.nav_interstage()
    except InvalidTransition as error:
        require(str(error) == "nav_semantic_gate_unavailable", "unexpected exact-candidate blocker")
    else:
        raise RuntimeError("D255 exact candidate incorrectly bypassed the NAV semantic gate")
    require(transport.requests == [first_request.raw, nav_request.raw],
            "exact candidate pre-blocker requests differ from D255")
    require(candidate.first_0x36_attempt_count == 1, "first 0x36 was not exactly once")
    require(transport.timeouts == [FIRST_FDT36_COMMAND_TIMEOUT_MS] * 2,
            "exact candidate did not enforce the bounded exchange timeout")
    require(lifecycle.retry_count == 0, "exact candidate retried")
    return {
        "name": "EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY",
        "status": "BLOCKED_FAIL_CLOSED_AT_FIRST_UNAVAILABLE_DYNAMIC_HOST_GATE",
        "full_target_out_control_trace": audit["timeline"]["out_control_trace"][1:],
        "core_exact_trace_contract": [f"0x{value:02x}" for value in EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE],
        "trace_contract_matches_target": tuple(EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE) == tuple(
            int(value, 16) for value in audit["timeline"]["out_control_trace"][1:]
        ),
        "requests_executed_before_fail_closed": ["0x36", "0x50"],
        "blocker": "0x50_DYNAMIC_NAV_HOST_SEMANTIC_GATE_UNAVAILABLE; LATER_0x82_AND_0x20_GATES_ALSO_UNRESOLVED",
        "first_0x36_attempt_count": candidate.first_0x36_attempt_count,
        "first_0x36_timeout_ms": FIRST_FDT36_COMMAND_TIMEOUT_MS,
        "first_0x36_ack_required": True,
        "first_0x36_irq100_touch0_required": True,
        "first_0x36_validator_transform_required": True,
        "automatic_retry_count": lifecycle.retry_count,
        "failed_before_later_stage": True,
        "terminal_host_cleanup": "STOP_NEW_TRAFFIC+CANCEL_PENDING_RECEIVE_IF_ANY+TERMINAL_HOST_CLEANUP",
        "special_recovery_command_count": 0,
        "persistent_write_family_count": lifecycle.persistent_write_family_count,
        "lifecycle": lifecycle.audit(),
    }


def scenario_invalid_cache(context: dict[str, object], otp: bytes) -> dict[str, object]:
    cache = context["cache"]
    source = cache.path.read_bytes()
    cases: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="d257-invalid-cache-") as directory:
        root = Path(directory)

        crc_bad = bytearray(source)
        crc_bad[100] ^= 0x01
        path = root / "crc.bin"
        path.write_bytes(crc_bad)
        cases["crc_error"] = provide_fdt12(path, otp).failure_reason or ""

        otp_bad = bytearray(source)
        otp_bad[0] ^= 0x01
        otp_bad[CRC_OFFSET:] = crc32_mpeg2(otp_bad[:CRC_OFFSET]).to_bytes(4, "little")
        path = root / "otp.bin"
        path.write_bytes(otp_bad)
        cases["otp_mismatch"] = provide_fdt12(path, otp).failure_reason or ""

        path = root / "size.bin"
        path.write_bytes(source[:-1])
        cases["size_layout_error"] = provide_fdt12(path, otp).failure_reason or ""

        seed_absent = bytearray(source)
        seed_absent[FDT12_OFFSET:NAV_OFFSET] = bytes(NAV_OFFSET - FDT12_OFFSET)
        seed_absent[CRC_OFFSET:] = crc32_mpeg2(seed_absent[:CRC_OFFSET]).to_bytes(4, "little")
        path = root / "seed.bin"
        path.write_bytes(seed_absent)
        cases["seed_absent"] = provide_fdt12(path, otp).failure_reason or ""

    expected = {
        "crc_error": "CACHE_CRC_MISMATCH",
        "otp_mismatch": "CACHE_OTP_BINDING_MISMATCH",
        "size_layout_error": "CACHE_SIZE_MISMATCH",
        "seed_absent": "CACHE_FDT12_ABSENT",
    }
    require(cases == expected, f"invalid-cache fail-closed matrix changed: {cases!r}")
    return {
        "name": "INVALID_SEED_CACHE_FAIL_CLOSED",
        "cases": cases,
        "all_fail_closed": True,
        "fallback_seed_count": 0,
        "raw_seed_exported": False,
        "raw_otp_exported": False,
    }


def freshness_audit(repo: Path, context: dict[str, object], audit: dict[str, object]) -> dict[str, object]:
    run = context["run"]
    metadata = json.loads((run / "cache_before_metadata.json").read_text(encoding="utf-8-sig"))
    compatible = [row for row in metadata if row.get("size") == 13_520]
    raw_target_caches = [path for path in (repo / "captures").rglob("*.bin")
                         if path.is_file() and path.stat().st_size == 13_520]
    evidence = json.loads((repo / D255_EVIDENCE).read_text(encoding="utf-8"))
    require(len(compatible) == 1 and len(raw_target_caches) == 1,
            "target cache snapshot census changed")
    require(evidence["seed_correlation"]["CACHE_FDT12_MATCH"] is True,
            "D255 cache/wire pair is no longer correlated")
    temporal = audit["temporal_provenance"]
    return {
        "scope": "D230_D257_CORRECTIVE_BOUNDED_EXISTING_LOCAL_CORPUS",
        "target_13520_cache_snapshot_count": 1,
        "target_cache_first_wire_seed_pair_count": 1,
        "target_cache_snapshot_stage": compatible[0].get("stage"),
        "target_cache_after_snapshot": "NOT_RECOVERABLE",
        "target_oem_log_status": evidence["evidence_sources"]["OEM_LOG_STATUS"],
        **temporal,
        "seed_freshness_generalization": "UNPROVEN",
        "current_corpus_exhausted_for_seed_freshness_generalization": True,
        "seed_freshness_is_sole_live_blocker": False,
    }


def run(repo: Path) -> dict[str, object]:
    scenario1, context = scenario_d255(repo)
    _run, _wire, _frames, otp, _cache = _load_d255(repo)
    scenario2 = scenario_first_image(repo)
    scenario3 = scenario_invalid_cache(context, otp)
    exact = exact_audit.audit(repo)
    scenario_exact = scenario_exact_target_blocked(repo, context, exact)
    freshness = freshness_audit(repo, context, exact)
    scenario4 = {
        "name": "LIFECYCLE_CANCEL_REENTRY",
        "provenance_class": "D256_OBSERVED_HOST_BUS_CONTRACT_PLUS_D257_OFFLINE_MODEL",
        "cancel_device_command_count": 0,
        "reentry_a2_injection_count": scenario1["lifecycle"]["a2_injection_count"],
        "reentry_0x70_injection_count": scenario1["lifecycle"]["0x70_injection_count"],
        "terminal_stop_device_command_count": 0,
        "full_cold_start_distinct": True,
        "persistent_command_families_reachable": False,
    }
    return {
        "schema": "D257_OFFLINE_REPLAY_INTEGRATION_V2_CORRECTIVE",
        "execution_mode": "OFFLINE_ONLY",
        "baseline_head": "417a1c543ed1a1d9217c462b6c0c33023d89b857",
        "scenarios": [scenario1, scenario_exact, scenario2, scenario3, scenario4],
        "exact_bootstrap_audit": exact,
        "freshness_audit": freshness,
        "provenance_separation": {
            "scenario_1": scenario1["provenance_class"],
            "scenario_2": scenario2["provenance_class"],
            "same_single_run_claimed": False,
        },
        "closure": {
            "PROJECTED_FDT_SUBSEQUENCE_REPLAY": "PASS_HISTORICAL",
            "EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY": "BLOCKED_DYNAMIC_HOST_GATES_NOT_DERIVABLE_FROM_D255_RAW",
            "FDT_OFFLINE_CANDIDATE_CLOSED": False,
            "IRQ2_0x22_PATH": "PASS_EXACTLY_ONCE",
            "FIRST_IMAGE_OFFLINE_CLOSURE": "PASS_SYNTHETIC_CODEC_FIXTURE",
            "PERSISTENT_COMMAND_FAMILIES_REACHABLE": False,
            "SEED_PROVIDER_RESULT": "PASS_D255_AND_FAIL_CLOSED_INVALID_MATRIX",
            "SEED_FRESHNESS_IS_SOLE_LIVE_BLOCKER": False,
            "READY_FOR_FDT_LIVE_REVIEW": False,
            "READY_FOR_FDT_LIVE": False,
        },
        "safety": {
            "REAL_USB_OPEN_COUNT": 0,
            "REAL_CAPTURE_COUNT": 0,
            "REAL_HARDWARE_ACTION_COUNT": 0,
            "REAL_COMMAND_SEND_COUNT": 0,
            "REAL_FINGER_INTERACTION_COUNT": 0,
            "raw_cache_exported": False,
            "raw_capture_exported": False,
            "raw_otp_exported": False,
            "raw_biometric_exported": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    result = run(repo)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else repo / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
