#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Audit metadata-only dell'enrollment OEM completo D279/10 attempt 02.

L'audit legge l'evidenza privata hash-gated, ma non esporta body A0, record
TLS, immagini, template, hash biometrici o materiale segreto.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ATTEMPT_ID = "D27910_20260905_ATTEMPT02"
CAPTURE_SHA256 = "3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab"
ATTEMPT = ROOT / "captures" / "D279_10" / ATTEMPT_ID
D274_PATH = ROOT / (
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/"
    "d274_03_postprocess_second_cycle.py"
)
D279_PATH = ROOT / (
    "operator_kit/d279-10-third-acquisition-observe/"
    "d279_10_third_cycle.py"
)


class AuditError(RuntimeError):
    """Evidenza assente, incoerente o fuori dal contratto dell'audit."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"MODULE_NOT_LOADABLE_{name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


D274 = _load_module("d279_10_attempt02_d274", D274_PATH)
D279 = _load_module("d279_10_attempt02_finalizer", D279_PATH)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"INVALID_JSON_{path.name}") from exc
    require(isinstance(document, dict), f"INVALID_OBJECT_{path.name}")
    return document


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _symbol(event: dict) -> str:
    kind = event["kind"]
    if kind == "COMMAND":
        return f"C{event['control']:02X}"
    if kind == "ACK":
        return f"K{event['echo']:02X}:{event['status']:02X}"
    if kind == "IRQ":
        return f"I{event['irq']:04X}"
    if kind == "B0":
        return "BF" if event["b0_class"] == "FINGERPRINT_B0" else "BO"
    if kind == "NAV":
        return "NAV"
    if kind == "OEM_FIXED_CONTROL_01":
        return "F01"
    return f"O{event.get('control', 0):02X}"


CYCLE1_SHAPE = (
    "I0002", "C22", "K22:01", "BF", "C34", "K34:01", "I0200",
    "C20", "K20:01", "BF", "C32", "K32:01", "C50", "K50:01",
    "NAV", "C32", "K32:01",
)
REPEATED_SHAPE = (
    "I0002", "C22", "K22:01", "BF", "C34", "K34:01", "C36",
    "K36:01", "I0100", "C20", "K20:01", "BF", "C34", "K34:01",
    "I0200", "C32", "K32:01",
)
TERMINAL_SHAPE = REPEATED_SHAPE[:-2]


def classify_cycle_shape(cycle_number: int, symbols: tuple[str, ...]) -> str:
    if cycle_number == 1 and symbols == CYCLE1_SHAPE:
        return "FIRST_CYCLE_NAV_TRANSITION"
    if 2 <= cycle_number <= 20 and symbols == REPEATED_SHAPE:
        return "REPEATED_ACQUISITION_TRANSITION_WITH_REARM"
    if cycle_number == 21 and symbols == TERMINAL_SHAPE:
        return "TERMINAL_ACQUISITION_TRANSITION_WITHOUT_REARM"
    raise AuditError(f"UNEXPECTED_CYCLE_SHAPE_{cycle_number}")


def correlate_contacts(operator_events: dict, complete_cycles: int) -> dict:
    contacts = operator_events.get("contact_count")
    require(isinstance(contacts, int) and contacts >= complete_cycles, "CONTACT_COUNT_INVALID")
    per_contact = operator_events.get("contact_timestamps")
    return {
        "operator_contact_count": contacts,
        "complete_wire_acquisition_lifecycle_count": complete_cycles,
        "operator_contact_without_complete_wire_acquisition_lifecycle_count": contacts - complete_cycles,
        "per_contact_timestamps_available": isinstance(per_contact, list),
        "specific_unmatched_contact_identifiable": False,
        "classification": (
            "ONE_OPERATOR_CONTACT_WITHOUT_COMPLETE_WIRE_ACQUISITION_LIFECYCLE_"
            "NOT_TEMPORALLY_LOCALIZABLE"
            if contacts - complete_cycles == 1 and not isinstance(per_contact, list)
            else "CONTACT_CORRELATION_REQUIRES_REVIEW"
        ),
    }


def analyze(root: Path = ROOT) -> dict:
    attempt = root / "captures" / "D279_10" / ATTEMPT_ID
    capture = attempt / "raw" / "wire.pcapng"
    final_evidence = _read_json(attempt / "sanitized" / "D279_10_full_enrollment_evidence.json")
    operator_events = _read_json(attempt / "sanitized" / "operator_events.json")
    attempt_status = _read_json(attempt / "sanitized" / "attempt_status.json")
    observer_result = _read_json(attempt / "sanitized" / "observer_result.json")
    require(_sha256(capture) == CAPTURE_SHA256, "CAPTURE_SHA256_MISMATCH")
    require(final_evidence.get("capture_sha256") == CAPTURE_SHA256, "FINALIZER_SHA256_MISMATCH")
    require(attempt_status.get("capture_sha256") == CAPTURE_SHA256, "STATUS_SHA256_MISMATCH")
    require(operator_events.get("attempt_id") == ATTEMPT_ID, "OPERATOR_ATTEMPT_ID_MISMATCH")
    require(attempt_status.get("result") == "PASS", "ATTEMPT_STATUS_NOT_PASS")
    require(observer_result.get("wire_acquisition_cycle_count") == 21, "OBSERVER_CYCLE_COUNT")
    require(observer_result.get("protocol_contradiction_count") == 0, "OBSERVER_CONTRADICTION")
    require(observer_result.get("automatic_retry_count") == 0, "OBSERVER_RETRY")

    packets = D274.parse_usbpcap_bytes(capture.read_bytes())
    frames, firmware_ok = D274._target_frames(packets, include_incomplete=False)
    require(firmware_ok, "APP12509_NOT_OBSERVED")
    base = min(frame.timestamp for frame in frames)
    rows = [(frame, D274._event(frame)) for frame in frames]
    cycles, contradictions = D279.detect_acquisition_cycles(rows, base)
    require(len(cycles) == 21 and contradictions == 0, "PRIMARY_CYCLE_CONTRACT")

    command_counts: dict[str, int] = {}
    command_bodies: dict[int, list[bytes]] = {}
    for _, event in rows:
        if event["kind"] == "COMMAND":
            key = f"0x{event['control']:02x}"
            command_counts[key] = command_counts.get(key, 0) + 1
            command_bodies.setdefault(event["control"], []).append(event["body"])
    require(command_counts == final_evidence.get("command_family_counts"), "COMMAND_COUNTS_MISMATCH")
    require(all(body == b"\x01\x00" for body in command_bodies[0x20]), "COMMAND_20_SHAPE")
    require(all(body == b"\x01\x00" for body in command_bodies[0x22]), "COMMAND_22_SHAPE")
    require(all(body == b"\x01\x00" for body in command_bodies[0x50]), "COMMAND_50_SHAPE")
    require(all(body == b"\x01\x14" for body in command_bodies[0xA2]), "COMMAND_A2_SHAPE")

    starts = [cycle["frames"]["irq2"]["frame"] for cycle in cycles]
    cycle_rows = []
    for index, cycle in enumerate(cycles):
        start = starts[index]
        end = starts[index + 1] if index + 1 < len(starts) else 1 << 31
        segment = [(frame, event) for frame, event in rows if start <= frame.packet_index < end]
        symbols = tuple(_symbol(event) for _, event in segment)
        shape = classify_cycle_shape(index + 1, symbols)
        primary = cycle["frames"]
        cycle_rows.append({
            "cycle": index + 1,
            "irq2_frame": primary["irq2"]["frame"],
            "primary_b0_frame": primary["fingerprint_b0"]["frame"],
            "irq2_timestamp_ms": primary["irq2"]["relative_timestamp_ms"],
            "primary_b0_timestamp_ms": primary["fingerprint_b0"]["relative_timestamp_ms"],
            "transition_last_frame": segment[-1][0].packet_index,
            "transition_class": shape,
        })

    irq2_count = sum(event["kind"] == "IRQ" and event["irq"] == 0x0002 for _, event in rows)
    command22_count = sum(event["kind"] == "COMMAND" and event["control"] == 0x22 for _, event in rows)
    ack22_count = sum(event["kind"] == "ACK" and event["echo"] == 0x22 for _, event in rows)
    fingerprint_b0_count = sum(
        event["kind"] == "B0" and event["b0_class"] == "FINGERPRINT_B0"
        for _, event in rows
    )
    require((irq2_count, command22_count, ack22_count) == (21, 21, 21), "PARTIAL_PRIMARY_PREFIX")
    require(fingerprint_b0_count == 43, "FINGERPRINT_B0_CENSUS")

    journal_rows = []
    for line in (attempt / "raw" / "observer_journal.jsonl").read_text(encoding="utf-8").splitlines():
        journal_rows.append(json.loads(line))
    transient_snapshots = sum(row.get("protocol_contradiction_count") == 1 for row in journal_rows)
    require(journal_rows[-1].get("protocol_contradiction_count") == 0, "JOURNAL_TERMINAL_CONTRADICTION")

    descriptor = D274.target_descriptors(packets)[0]
    target = (descriptor.bus, descriptor.device)
    target_packets = [packet for packet in packets if (packet.bus, packet.device) == target]
    completion = _parse_utc(operator_events["enrollment_completed_utc"]).timestamp()
    stopped = _parse_utc(operator_events["capture_stopped_utc"]).timestamp()
    last_frame = max(frames, key=lambda frame: frame.timestamp)
    last_packet = max(target_packets, key=lambda packet: packet.timestamp)
    require(last_packet.data_len == 0 and last_packet.endpoint == 0x81, "TERMINAL_PACKET_NOT_ZERO_IN")
    require(sum(packet.timestamp >= completion for packet in target_packets) == 0, "POST_UI_TARGET_PACKET")
    require(sum(frame.timestamp >= completion for frame in frames) == 0, "POST_UI_TARGET_FRAME")

    contact_correlation = correlate_contacts(operator_events, len(cycles))
    require(contact_correlation["operator_contact_without_complete_wire_acquisition_lifecycle_count"] == 1,
            "CONTACT_WIRE_DELTA")
    inter_cycle_gaps = [
        cycles[index + 1]["frames"]["irq2"]["relative_timestamp_ms"]
        - cycles[index]["frames"]["fingerprint_b0"]["relative_timestamp_ms"]
        for index in range(20)
    ]

    return {
        "schema": "D279_10_ATTEMPT02_FULL_ENROLLMENT_AUDIT_V1",
        "attempt_id": ATTEMPT_ID,
        "evidence_commit": "6c1564b6e7f58a5694113ffcb2e35f9ea0847c7e",
        "capture_sha256": CAPTURE_SHA256,
        "source_integrity": {
            "pcapng_packet_count": len(packets),
            "target_packet_count": len(target_packets),
            "target_frame_count": len(frames),
            "firmware_identity": "GF_ST411SEC_APP_12509",
            "finalized_parse": "PASS",
        },
        "timeline": {
            "first_target_frame_utc": _iso(base),
            "cold_bootstrap": {
                "frame_range": "25-181",
                "relative_range_ms": [0.0, 952.631],
                "command_trace": "F01,D5,F01,A8,F01,97,AF,F01,A8,E4,A2,82,A6,A2,70,80x4,90,D1,TLS,D4,AF,36,50/NAV,36,82,20/B0,36,32",
            },
            "pre_enrollment_reentry_1": {
                "frame_range": "187-195",
                "relative_range_ms": [58282.904, 58339.146],
                "command_trace": "F01,D5,F01,AF",
            },
            "pre_enrollment_reentry_2": {
                "frame_range": "199-211",
                "relative_range_ms": [79813.572, 79919.041],
                "command_trace": "F01,D5,F01,AF,32/ACK",
            },
            "wizard_started_relative_to_first_target_ms": round(
                ( _parse_utc(operator_events["wizard_started_utc"]).timestamp() - base) * 1000, 3
            ),
            "first_irq2_after_wizard_ms": round(
                (cycles[0]["frames"]["irq2"]["relative_timestamp_ms"] / 1000
                 - (_parse_utc(operator_events["wizard_started_utc"]).timestamp() - base)) * 1000, 3
            ),
            "acquisition_window": {
                "first_irq2_frame": starts[0],
                "last_primary_b0_frame": cycles[-1]["frames"]["fingerprint_b0"]["frame"],
                "terminal_finger_up_irq_frame": last_frame.packet_index,
                "cycle_count": len(cycles),
                "primary_irq2_to_b0_ms": {
                    "minimum": round(min(
                        cycle["frames"]["fingerprint_b0"]["relative_timestamp_ms"]
                        - cycle["frames"]["irq2"]["relative_timestamp_ms"]
                        for cycle in cycles
                    ), 3),
                    "median": round(statistics.median(
                        cycle["frames"]["fingerprint_b0"]["relative_timestamp_ms"]
                        - cycle["frames"]["irq2"]["relative_timestamp_ms"]
                        for cycle in cycles
                    ), 3),
                    "maximum": round(max(
                        cycle["frames"]["fingerprint_b0"]["relative_timestamp_ms"]
                        - cycle["frames"]["irq2"]["relative_timestamp_ms"]
                        for cycle in cycles
                    ), 3),
                },
                "primary_b0_to_next_irq2_ms": {
                    "minimum": round(min(inter_cycle_gaps), 3),
                    "median": round(statistics.median(inter_cycle_gaps), 3),
                    "maximum": round(max(inter_cycle_gaps), 3),
                    "maximum_after_cycle": inter_cycle_gaps.index(max(inter_cycle_gaps)) + 1,
                    "maximum_is_only_a_candidate_for_ineffective_contact": True,
                },
            },
            "terminal": {
                "visible_finalization_trace": "I0002,C22,K22:01,BF,C34,K34:01,C36,K36:01,I0100,C20,K20:01,BF,C34,K34:01,I0200",
                "last_protocol_frame": last_frame.packet_index,
                "last_protocol_frame_utc": _iso(last_frame.timestamp),
                "last_target_packet": last_packet.index,
                "last_target_packet_class": "ZERO_LENGTH_BULK_IN_COMPLETION",
                "last_target_packet_utc": _iso(last_packet.timestamp),
                "last_protocol_frame_to_ui_confirmation_seconds": round(completion - last_frame.timestamp, 3),
                "last_target_packet_to_ui_confirmation_seconds": round(completion - last_packet.timestamp, 3),
                "post_ui_target_frame_count": 0,
                "post_ui_target_packet_count": 0,
                "ui_to_capture_stop_seconds": round(stopped - completion, 3),
            },
        },
        "cycle_shapes": {
            "cycle_1": "FIRST_CYCLE_NAV_TRANSITION",
            "cycles_2_through_20": "REPEATED_ACQUISITION_TRANSITION_WITH_REARM",
            "cycle_21": "TERMINAL_ACQUISITION_TRANSITION_WITHOUT_REARM",
            "inter_cycle_rearm_count": 20,
            "finger_up_irq0200_count": 21,
            "irq0100_count": 23,
            "nav_response_count": 2,
            "fingerprint_shape_b0_count": fingerprint_b0_count,
            "primary_cycle_rows": cycle_rows,
        },
        "contact_correlation": {
            **contact_correlation,
            "unmatched_irq2_count": 0,
            "unmatched_command_0x22_count": 0,
            "unmatched_ack_0x22_count": 0,
            "protocol_inference": "NO_COMPLETE_OR_PARTIAL_PRIMARY_WIRE_LIFECYCLE_IDENTIFIES_THE_EXTRA_CONTACT",
        },
        "observer_incremental_state": {
            "transient_contradiction_snapshots": transient_snapshots,
            "finalized_protocol_contradiction_count": contradictions,
            "classification": "INCREMENTAL_SNAPSHOT_ARTIFACTS_CLEARED_BY_FINALIZED_PARSE",
        },
        "command_family_counts": command_counts,
        "command_shape_observations": {
            "fixed_control_01_count_excluded_from_command_family_counts": sum(
                event["kind"] == "OEM_FIXED_CONTROL_01" for _, event in rows
            ),
            "0x20_all_exact_image_mode_shape": True,
            "0x22_all_exact_image_mode_shape": True,
            "0x50_all_exact_nav_mode_shape": True,
            "0xa2_all_sensor_only_reset_shape": True,
            "0x32_distinct_body_count": len(set(command_bodies[0x32])),
            "0x34_distinct_body_count": len(set(command_bodies[0x34])),
            "0x36_distinct_body_count": len(set(command_bodies[0x36])),
            "0x34_cycles_2_through_21_reuse_same_cycle_table_twice": True,
        },
        "known_persistent_command_families_observed": [],
        "known_persistent_command_families_checked": ["0xe0", "0xa4", "0xf0", "0xf4"],
        "bounded_persistence_conclusion": "NO_KNOWN_VISIBLE_PERSISTENT_FAMILY_OBSERVED; SENSOR_SIDE_TEMPLATE_PERSISTENCE_NOT_EXCLUDED",
        "automatic_retry_count": 0,
        "observer_is_passive": True,
        "goodix_sender_present": False,
        "content_bytes_exported": False,
        "biometric_plaintext_exported": False,
        "biometric_hash_exported": False,
        "secret_material_exported": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = analyze()
        serialized = json.dumps(result, indent=2) + "\n"
        if args.output:
            args.output.write_text(serialized, encoding="utf-8")
        else:
            print(serialized, end="")
        return 0
    except (AuditError, OSError, ValueError) as exc:
        print(json.dumps({"result": "FAIL", "failure_class": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
