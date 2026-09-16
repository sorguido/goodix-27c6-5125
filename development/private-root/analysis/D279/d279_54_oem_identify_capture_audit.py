#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Strict metadata-only audit of the D279/54 OEM identify capture."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ATTEMPT_ID = "D27954_20260908_ATTEMPT01"
CAPTURE_SHA256 = "6875b2d784d11cd4b3a8b68bd02af249f4b318883441a26068ef894767985c9b"
OPERATOR_EVENTS_SHA256 = "bb258a20f00f01efe271ca282e3dd6d0cba1ac6a4d6747da67e16417b2ddf555"
ATTEMPT_STATUS_SHA256 = "20b45b1a07d0843a55e9314fe0d20668331258ba0a722b48126ed7d298f039bc"
ATTEMPT = ROOT / "captures" / "D279_54" / ATTEMPT_ID
PARSER_PATH = ROOT / (
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/"
    "d274_03_postprocess_second_cycle.py"
)
ACTION_TRACE = (
    "C32", "K32:01", "I0002", "C22", "K22:01", "BF", "C34",
    "K34:01", "I0200", "C20", "K20:01", "BF", "C50", "K50:01",
    "NAV",
)
KNOWN_PERSISTENT_COMMAND_FAMILIES = {0xE0, 0xA4, 0xF0, 0xF4}


class AuditError(RuntimeError):
    """Evidence is missing, malformed, or outside the strict contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def _load_parser():
    spec = importlib.util.spec_from_file_location("d279_54_d274_parser", PARSER_PATH)
    require(spec is not None and spec.loader is not None, "PARSER_NOT_LOADABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


D274 = _load_parser()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, expected_sha256: str) -> dict:
    require(path.is_file() and not path.is_symlink(), f"{path.name}_NOT_REGULAR")
    require(_sha256(path) == expected_sha256, f"{path.name}_SHA256_MISMATCH")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"{path.name}_INVALID_JSON") from exc
    require(isinstance(value, dict), f"{path.name}_NOT_OBJECT")
    return value


def _timestamp(value: object, field: str) -> float:
    require(isinstance(value, str), f"{field}_TYPE")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditError(f"{field}_INVALID") from exc
    require(parsed.tzinfo is not None, f"{field}_TIMEZONE")
    return parsed.astimezone(timezone.utc).timestamp()


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


def analyze(root: Path = ROOT) -> dict:
    attempt = root / "captures" / "D279_54" / ATTEMPT_ID
    capture = attempt / "raw" / "wire.pcapng"
    events_path = attempt / "sanitized" / "operator_events.json"
    status_path = attempt / "sanitized" / "attempt_status.json"

    require(capture.is_file() and not capture.is_symlink(), "CAPTURE_NOT_REGULAR")
    require(_sha256(capture) == CAPTURE_SHA256, "CAPTURE_SHA256_MISMATCH")
    operator = _read_json(events_path, OPERATOR_EVENTS_SHA256)
    status = _read_json(status_path, ATTEMPT_STATUS_SHA256)

    require(operator.get("schema") == "D279_54_OPERATOR_EVENTS_V1", "OPERATOR_SCHEMA")
    require(status.get("schema") == "D279_54_ATTEMPT_STATUS_V1", "STATUS_SCHEMA")
    require(operator.get("attempt_id") == ATTEMPT_ID, "OPERATOR_ATTEMPT_ID")
    require(status.get("attempt_id") == ATTEMPT_ID, "STATUS_ATTEMPT_ID")
    require(operator.get("capture_sha256") == CAPTURE_SHA256, "OPERATOR_CAPTURE_HASH")
    require(status.get("capture_sha256") == CAPTURE_SHA256, "STATUS_CAPTURE_HASH")
    require(operator.get("verification_attempt_count") == 1, "ATTEMPT_COUNT")
    require(operator.get("automatic_retry_count") == 0, "OPERATOR_RETRY")
    require(status.get("automatic_retry_count") == 0, "STATUS_RETRY")
    require(operator.get("verification_result") == "WINDOWS_UI_FINGERPRINT_SUCCESS",
            "OPERATOR_RESULT")
    require(status.get("result") == "PASS_UI_CONFIRMED", "STATUS_RESULT")
    require(status.get("verification_completed") is True, "STATUS_NOT_COMPLETED")

    capture_started = _timestamp(operator.get("capture_started_utc"), "CAPTURE_STARTED")
    verification_started = _timestamp(
        operator.get("verification_started_utc"), "VERIFICATION_STARTED")
    verification_completed = _timestamp(
        operator.get("verification_completed_utc"), "VERIFICATION_COMPLETED")
    capture_stopped = _timestamp(operator.get("capture_stopped_utc"), "CAPTURE_STOPPED")
    require(capture_started <= verification_started <= verification_completed <= capture_stopped,
            "OPERATOR_TIME_ORDER")
    tail_seconds = capture_stopped - verification_completed
    require(tail_seconds >= 5.0, "TERMINAL_TAIL_TOO_SHORT")

    packets = D274.parse_usbpcap_bytes(capture.read_bytes())
    frames, firmware_ok = D274._target_frames(packets, include_incomplete=False)
    require(firmware_ok, "APP12509_NOT_OBSERVED")
    descriptors = D274.target_descriptors(packets)
    targets = {(packet.bus, packet.device) for packet in descriptors}
    require(len(targets) == 1, "TARGET_AMBIGUOUS")
    target = next(iter(targets))
    target_packets = [packet for packet in packets if (packet.bus, packet.device) == target]
    require(frames and target_packets, "TARGET_TRAFFIC_MISSING")

    rows = [(frame, D274._event(frame)) for frame in frames]
    symbols = [_symbol(event) for _, event in rows]
    irq2_index = symbols.index("I0002")
    require(symbols.count("I0002") == 1, "FINGER_ON_COUNT")
    require(irq2_index >= 2 and tuple(symbols[irq2_index - 2:]) == ACTION_TRACE,
            "IDENTIFY_ACTION_TRACE")
    require("C32" not in symbols[irq2_index + 1:], "POST_TOUCH_REARM_OBSERVED")
    require(symbols[-1] == "NAV", "LAST_PROTOCOL_EVENT_NOT_NAV")

    commands = [event["control"] for _, event in rows if event["kind"] == "COMMAND"]
    persistent = sorted(set(commands) & KNOWN_PERSISTENT_COMMAND_FAMILIES)
    require(not persistent, "KNOWN_PERSISTENT_COMMAND_OBSERVED")
    require(symbols[irq2_index:].count("BF") == 2, "ACTION_B0_COUNT")
    require(symbols[irq2_index:].count("C22") == 1, "PRIMARY_COMMAND_COUNT")
    require(symbols[irq2_index:].count("C34") == 1, "RELEASE_COMMAND_COUNT")
    require(symbols[irq2_index:].count("C20") == 1, "POST_UP_COMMAND_COUNT")
    require(symbols[irq2_index:].count("C50") == 1, "TERMINAL_NAV_COMMAND_COUNT")

    last_frame = max(frames, key=lambda frame: frame.timestamp)
    last_packet = max(target_packets, key=lambda packet: packet.timestamp)
    protocol_frames_after_ui = sum(
        frame.timestamp >= verification_completed for frame in frames)
    target_packets_after_ui = [
        packet for packet in target_packets if packet.timestamp >= verification_completed]
    require(protocol_frames_after_ui == 0, "PROTOCOL_FRAME_AFTER_UI_COMPLETION")
    require(all(packet.data_len == 0 for packet in target_packets_after_ui),
            "NONEMPTY_TARGET_PACKET_AFTER_UI_COMPLETION")

    counter = Counter(symbols[irq2_index - 2:])
    return {
        "schema": "D279_54_OEM_IDENTIFY_CAPTURE_AUDIT_V1",
        "attempt_id": ATTEMPT_ID,
        "capture_sha256": CAPTURE_SHA256,
        "operator_events_sha256": OPERATOR_EVENTS_SHA256,
        "attempt_status_sha256": ATTEMPT_STATUS_SHA256,
        "source_integrity": {
            "pcapng_packet_count": len(packets),
            "target_packet_count": len(target_packets),
            "target_protocol_frame_count": len(frames),
            "firmware_identity": "GF_ST411SEC_APP_12509",
            "strict_finalized_parse": "PASS",
        },
        "operator_outcome": {
            "verification_attempt_count": 1,
            "verification_result": "WINDOWS_UI_FINGERPRINT_SUCCESS",
            "automatic_retry_count": 0,
            "terminal_tail_seconds": round(tail_seconds, 3),
        },
        "identify_action": {
            "trace": "C32,K32:01,I0002,C22,K22:01,BF,C34,K34:01,I0200,C20,K20:01,BF,C50,K50:01,NAV",
            "finger_on_count": counter["I0002"],
            "primary_image_count": 1,
            "post_up_b0_count": 1,
            "post_touch_rearm_0x32_count": 0,
            "second_finger_on_count": 0,
            "second_primary_image_count": 0,
            "terminal_protocol_event": "NAV",
            "single_touch_single_acquisition": True,
        },
        "terminal_observation": {
            "last_protocol_frame": last_frame.packet_index,
            "last_target_packet": last_packet.index,
            "protocol_frames_after_ui_completion": protocol_frames_after_ui,
            "target_packets_after_ui_completion": len(target_packets_after_ui),
            "nonempty_target_packets_after_ui_completion": 0,
        },
        "safety": {
            "known_persistent_command_family_count": 0,
            "automatic_retry_count": 0,
            "capture_was_passive": True,
            "linux_sender_action_count": 0,
            "adaptive_template_persistence_excluded": False,
        },
        "privacy": {
            "payload_exported": False,
            "plaintext_exported": False,
            "raster_exported": False,
            "biometric_feature_or_template_exported": False,
            "secret_exported": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = analyze()
        payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output is None:
            print(payload, end="")
        else:
            args.output.write_text(payload, encoding="utf-8")
        return 0
    except (AuditError, OSError, ValueError, KeyError) as error:
        print(f"D279_54_AUDIT_FAIL_CLOSED={type(error).__name__}:{error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
