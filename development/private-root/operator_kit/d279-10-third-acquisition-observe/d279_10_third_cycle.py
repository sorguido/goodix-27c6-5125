#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Finalize a passive capture of a complete Windows Hello OEM enrollment.

The Windows UI/operator event is the enrollment-completion authority. Wire
events are metadata-only observations: the third fingerprint B0 is a milestone,
not a stop condition, and no number of contacts is assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
D274_PATH = ROOT / (
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/"
    "d274_03_postprocess_second_cycle.py"
)
SPEC = importlib.util.spec_from_file_location("d279_10_d274_parser", D274_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("D279_10_D274_PARSER_NOT_LOADABLE")
D274 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = D274
SPEC.loader.exec_module(D274)

HOST_CAPTURE_DEADLINE_SECONDS = 1200
MINIMUM_TERMINAL_TAIL_SECONDS = 5
WORKFLOW = "WINDOWS_HELLO_FIRST_OEM_ENROLLMENT_COMPLETE_UI_CONFIRMED"
KNOWN_PERSISTENT_COMMAND_FAMILIES = {0xE0, 0xA4, 0xF0, 0xF4}


class EvidenceError(RuntimeError):
    """Fail-closed evidence error."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _event_rows(frames: list) -> list[tuple[object, dict]]:
    rows = []
    for frame in frames:
        try:
            rows.append((frame, D274._event(frame)))
        except D274.EvidenceError as exc:
            raise EvidenceError(str(exc)) from exc
    return rows


def _is_irq2(event: dict) -> bool:
    return D274._matches(event, "IRQ", 0x0002)


def _is_command_22(event: dict) -> bool:
    return D274._matches(event, "COMMAND", 0x22)


def _is_ack_22(event: dict) -> bool:
    return D274._matches(event, "ACK", 0x22)


def _is_fingerprint_b0(event: dict) -> bool:
    return D274._matches(event, "FINGERPRINT_B0", None)


def _cycle_lifecycle_bearing(event: dict) -> bool:
    return (
        _is_irq2(event)
        or (event.get("kind") == "COMMAND" and event.get("control") == 0x22)
        or (event.get("kind") == "ACK" and event.get("echo") == 0x22)
        or _is_fingerprint_b0(event)
    )


def _frame_metadata(frame, event: dict, event_class: str, base: float) -> dict:
    return D274._meta(frame, base, event_class, event)


def detect_acquisition_cycles(events: list[tuple[object, dict]], base: float) -> tuple[list[dict], int]:
    """Find every exact IRQ2 -> 0x22 -> ACK -> fingerprint-B0 lifecycle."""
    state = 0
    current: list[tuple[str, object, dict]] = []
    cycles: list[dict] = []
    contradictions = 0

    for frame, event in events:
        if state == 0:
            if _is_irq2(event):
                state = 1
                current = [("irq2", frame, event)]
            continue

        matched = False
        if state == 1 and _is_command_22(event):
            state = 2
            current.append(("command_0x22", frame, event))
            matched = True
        elif state == 2 and _is_ack_22(event):
            state = 3
            current.append(("ack_0x22", frame, event))
            matched = True
        elif state == 3 and _is_fingerprint_b0(event):
            current.append(("fingerprint_b0", frame, event))
            cycle_number = len(cycles) + 1
            cycles.append({
                "cycle_number": cycle_number,
                "frames": {
                    name: _frame_metadata(
                        row_frame, row_event,
                        f"ACQUISITION_{cycle_number}_{name.upper()}", base,
                    )
                    for name, row_frame, row_event in current
                },
            })
            state = 0
            current = []
            matched = True

        if matched:
            continue
        if _cycle_lifecycle_bearing(event):
            contradictions += 1
            if _is_irq2(event):
                state = 1
                current = [("irq2", frame, event)]
            else:
                state = 0
                current = []

    if state != 0:
        contradictions += 1
    return cycles, contradictions


def _parse_utc(value: object, field: str) -> datetime:
    require(isinstance(value, str), "OPERATOR_EVENTS_" + field.upper())
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("OPERATOR_EVENTS_" + field.upper()) from exc
    require(parsed.tzinfo is not None, "OPERATOR_EVENTS_" + field.upper())
    return parsed.astimezone(timezone.utc)


def load_operator_events(path: Path, attempt_id: str) -> dict:
    require(path.is_file(), "OPERATOR_EVENTS_MISSING")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise EvidenceError("OPERATOR_EVENTS_INVALID_JSON") from exc
    required = {
        "schema", "attempt_id", "capture_started_utc", "wizard_started_utc",
        "enrollment_completed_utc", "capture_stopped_utc", "contact_count",
        "enrollment_completed", "terminal_tail_seconds",
        "automatic_retry_count",
    }
    require(isinstance(document, dict) and set(document) == required,
            "OPERATOR_EVENTS_SCHEMA_FIELDS")
    require(document["schema"] == "D279_10_OPERATOR_EVENTS_V2",
            "OPERATOR_EVENTS_SCHEMA_ID")
    require(document["attempt_id"] == attempt_id,
            "OPERATOR_EVENTS_ATTEMPT_ID")
    require(document["enrollment_completed"] is True,
            "WINDOWS_UI_ENROLLMENT_NOT_CONFIRMED")
    require(isinstance(document["contact_count"], int)
            and document["contact_count"] >= 1,
            "OPERATOR_EVENTS_CONTACT_COUNT")
    require(document["automatic_retry_count"] == 0,
            "OPERATOR_EVENTS_RETRY")
    require(document["terminal_tail_seconds"] == MINIMUM_TERMINAL_TAIL_SECONDS,
            "OPERATOR_EVENTS_TAIL_POLICY")
    started = _parse_utc(document["capture_started_utc"], "capture_started_utc")
    wizard = _parse_utc(document["wizard_started_utc"], "wizard_started_utc")
    complete = _parse_utc(
        document["enrollment_completed_utc"], "enrollment_completed_utc")
    stopped = _parse_utc(document["capture_stopped_utc"], "capture_stopped_utc")
    require(started <= wizard <= complete <= stopped,
            "OPERATOR_EVENTS_TIME_ORDER")
    tail = (stopped - complete).total_seconds()
    require(tail >= MINIMUM_TERMINAL_TAIL_SECONDS,
            "TERMINAL_TAIL_TOO_SHORT")
    require((stopped - started).total_seconds() <= HOST_CAPTURE_DEADLINE_SECONDS + 15,
            "CAPTURE_DEADLINE_EXCEEDED")
    return {**document, "validated_tail_seconds": round(tail, 3),
            "completion_epoch": complete.timestamp()}


def analyze_frames(frames: list, base: float, synthetic: bool,
                   operator_events: dict, attempt_id: str) -> dict:
    events = _event_rows(frames)
    cycles, contradictions = detect_acquisition_cycles(events, base)
    require(bool(cycles), "ACQUISITION_CYCLE_MISSING")

    control_counts: dict[str, int] = {}
    persistent_observed: set[int] = set()
    for _, event in events:
        if event.get("kind") != "COMMAND":
            continue
        control = event.get("control")
        if not isinstance(control, int):
            continue
        key = f"0x{control:02x}"
        control_counts[key] = control_counts.get(key, 0) + 1
        if control in KNOWN_PERSISTENT_COMMAND_FAMILIES:
            persistent_observed.add(control)

    third = cycles[2] if len(cycles) >= 3 else None
    completion_epoch = operator_events["completion_epoch"]
    post_ui_target_frames = sum(
        1 for frame in frames if frame.timestamp >= completion_epoch)
    if persistent_observed:
        sensor_risk = "KNOWN_PERSISTENT_COMMAND_FAMILY_OBSERVED"
    else:
        sensor_risk = (
            "NO_KNOWN_PERSISTENT_FAMILY_OBSERVED_"
            "BUT_ENCRYPTED_TEMPLATE_PERSISTENCE_NOT_EXCLUDED"
        )

    return {
        "schema": "D279_10_FULL_ENROLLMENT_EVIDENCE_V2",
        "attempt_id": attempt_id,
        "capture_sha256": None,
        "target_vid": "27c6",
        "target_pid": "5125",
        "firmware_identity_status": (
            "SYNTHETIC_APP12509" if synthetic else
            "TARGET_CAPTURE_OBSERVED_APP12509"
        ),
        "workflow_class": WORKFLOW,
        "boundary_status": "OBSERVED_COMPLETE_UI_CONFIRMED",
        "completion_authority": "WINDOWS_UI_OPERATOR_NUMERIC_CONFIRMATION",
        "stop_reason": "WINDOWS_UI_ENROLLMENT_CONFIRMED_PLUS_TERMINAL_TAIL",
        "operator_contact_count": operator_events["contact_count"],
        "wire_acquisition_cycle_count": len(cycles),
        "operator_wire_count_equal": (
            operator_events["contact_count"] == len(cycles)),
        "acquisition_cycles": cycles,
        "third_b0_milestone_observed": third is not None,
        "third_b0_milestone_frame": (
            third["frames"]["fingerprint_b0"]["frame"]
            if third is not None else None
        ),
        "protocol_contradiction_count": contradictions,
        "terminal_tail_host_seconds": operator_events["validated_tail_seconds"],
        "terminal_tail_target_frame_count": post_ui_target_frames,
        "host_capture_deadline_seconds": HOST_CAPTURE_DEADLINE_SECONDS,
        "host_deadline_policy": "EVIDENCE_BOUNDED_NOT_DEVICE_TIMEOUT_CLAIM",
        "device_timeout_claim": "UNKNOWN",
        "command_family_counts": dict(sorted(control_counts.items())),
        "known_persistent_command_families_observed": [
            f"0x{value:02x}" for value in sorted(persistent_observed)
        ],
        "sensor_side_risk_assessment": sensor_risk,
        "automatic_retry_count": 0,
        "observer_is_passive": True,
        "goodix_sender_present": False,
        "privacy_payload_exported": False,
        "biometric_plaintext_exported": False,
        "biometric_hash_exported": False,
        "secret_material_exported": False,
        "pin_value_exported": False,
    }


def _target_frames(data: bytes, *, growing: bool, synthetic: bool) -> tuple[list, float]:
    try:
        packets = D274.parse_usbpcap_bytes(
            data, allow_trailing_incomplete=growing)
        frames, firmware_ok = D274._target_frames(
            packets, include_incomplete=False)
    except D274.EvidenceError as exc:
        raise EvidenceError(str(exc)) from exc
    require(firmware_ok or synthetic, "WRONG_OR_MISSING_FIRMWARE_APP12509")
    require(bool(frames), "TARGET_FRAMES_MISSING")
    return frames, min(frame.timestamp for frame in frames)


def inspect_growing_capture(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        return {"status": "PENDING", "wire_acquisition_cycle_count": 0,
                "third_b0_milestone_observed": False}
    try:
        frames, base = _target_frames(path.read_bytes(), growing=True,
                                      synthetic=False)
        cycles, contradictions = detect_acquisition_cycles(
            _event_rows(frames), base)
    except EvidenceError as exc:
        failure = str(exc)
        pending = failure in {
            "TRUNCATED_PCAP_METADATA", "PCAP_INTERFACE_MISSING",
            "TARGET_27C6_5125_NOT_IDENTIFIED",
            "WRONG_OR_MISSING_FIRMWARE_APP12509", "TARGET_FRAMES_MISSING",
        }
        return {"status": "PENDING" if pending else "FAIL_CLOSED",
                "failure_class": failure,
                "wire_acquisition_cycle_count": 0,
                "third_b0_milestone_observed": False}
    return {
        "status": "OBSERVING",
        "wire_acquisition_cycle_count": len(cycles),
        "third_b0_milestone_observed": len(cycles) >= 3,
        "protocol_contradiction_count": contradictions,
    }


def validate_document(document: dict) -> None:
    require(document["schema"] == "D279_10_FULL_ENROLLMENT_EVIDENCE_V2",
            "SCHEMA_ID")
    require(document["boundary_status"] == "OBSERVED_COMPLETE_UI_CONFIRMED",
            "SCHEMA_BOUNDARY")
    require(document["automatic_retry_count"] == 0, "SCHEMA_RETRY")
    require(document["observer_is_passive"] is True, "SCHEMA_OBSERVER")
    require(document["goodix_sender_present"] is False, "SCHEMA_SENDER")
    require(document["wire_acquisition_cycle_count"] ==
            len(document["acquisition_cycles"]), "SCHEMA_CYCLE_COUNT")
    forbidden = re.compile(
        r"(^|_)(raw|body|payload|plaintext|image|raster|pixel|descriptor|"
        r"psk|secret|pin_value)($|_)", re.IGNORECASE)

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                require(forbidden.search(key) is None or key in {
                    "privacy_payload_exported", "biometric_plaintext_exported",
                    "secret_material_exported", "pin_value_exported",
                }, "PRIVACY_FORBIDDEN_FIELD")
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document)
    for key in (
        "privacy_payload_exported", "biometric_plaintext_exported",
        "biometric_hash_exported", "secret_material_exported",
        "pin_value_exported", "goodix_sender_present",
    ):
        require(document[key] is False, "PRIVACY_OR_SCOPE_FLAG")


def process_capture(path: Path, expected_sha256: str, operator_events_path: Path,
                    attempt_id: str, *, synthetic: bool = False) -> dict:
    require(re.fullmatch(r"D27910_[A-Za-z0-9_-]{8,64}", attempt_id) is not None,
            "ATTEMPT_ID_INVALID")
    require(re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
            "EXPECTED_SHA256_INVALID")
    require(path.is_file(), "CAPTURE_NOT_REGULAR")
    actual = sha256_file(path)
    require(actual == expected_sha256, "CAPTURE_SHA256_MISMATCH")
    operator_events = load_operator_events(operator_events_path, attempt_id)
    frames, base = _target_frames(path.read_bytes(), growing=False,
                                  synthetic=synthetic)
    document = analyze_frames(frames, base, synthetic, operator_events,
                              attempt_id)
    document["capture_sha256"] = actual
    validate_document(document)
    return document


def write_once(path: Path, document: dict) -> None:
    require(not path.exists(), "OUTPUT_COLLISION")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    require(not temporary.exists(), "OUTPUT_TEMP_COLLISION")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    os.replace(str(temporary), str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcap", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--operator-events", type=Path, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = process_capture(
            args.pcap, args.expected_sha256, args.operator_events,
            args.attempt_id)
        write_once(args.output, document)
        print(json.dumps({
            "boundary_status": document["boundary_status"],
            "wire_acquisition_cycle_count":
                document["wire_acquisition_cycle_count"],
            "third_b0_milestone_observed":
                document["third_b0_milestone_observed"],
        }))
        return 0
    except (EvidenceError, OSError, ValueError) as exc:
        print(json.dumps({"boundary_status": "NOT_OBSERVED_COMPLETE",
                          "failure_class": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
