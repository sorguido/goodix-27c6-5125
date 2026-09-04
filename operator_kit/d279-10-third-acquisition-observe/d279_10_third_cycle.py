#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Sanitize a passive USBPcap capture at the APP12509 third-acquisition edge.

This module reuses the reviewed D274/03 framing parser.  It exports metadata
only: no B0 body, TLS plaintext, image, biometric hash, PIN or secret material.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
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

HOST_CAPTURE_DEADLINE_SECONDS = 300
WORKFLOW = "WINDOWS_HELLO_SETUP_CANDIDATE_THIRD_EDGE_NO_COMMIT_ASSUMPTION"

# The first part is the already reviewed D274/03 sequence through second B0.
# The suffix tests the new hypothesis: the same release/re-arm lifecycle repeats
# after image two before the third finger-down edge.
SUFFIX = (
    ("second_release_0x34", "COMMAND", 0x34),
    ("second_release_0x34_ack", "ACK", 0x34),
    ("second_release_irq0200", "IRQ", 0x0200),
    ("second_release_0x20", "COMMAND", 0x20),
    ("second_release_0x20_ack", "ACK", 0x20),
    ("second_release_b0", "FINGERPRINT_B0", None),
    ("second_release_0x50", "COMMAND", 0x50),
    ("second_release_0x50_ack", "ACK", 0x50),
    ("second_release_nav", "NAV", 0x50),
    ("third_rearm_0x32", "COMMAND", 0x32),
    ("third_rearm_0x32_ack", "ACK", 0x32),
    ("third_irq2", "IRQ", 0x0002),
    ("third_0x22", "COMMAND", 0x22),
    ("third_0x22_ack", "ACK", 0x22),
    ("third_b0", "FINGERPRINT_B0", None),
)


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


def _matches(event: dict, kind: str, value: int | None) -> bool:
    if not D274._matches(event, kind, value):
        return False
    if kind == "COMMAND" and value == 0x34:
        body = event.get("body", b"")
        return len(body) == 14 and body[:2] == b"\x0a\x01"
    if kind == "COMMAND" and value == 0x32:
        return len(event.get("body", b"")) == 14
    return True


def _lifecycle_bearing(event: dict) -> bool:
    if event.get("kind") == "COMMAND":
        return event.get("control") in {0x20, 0x22, 0x32, 0x34, 0x50}
    if event.get("kind") == "ACK":
        return event.get("echo") in {0x20, 0x22, 0x32, 0x34, 0x50}
    if event.get("kind") == "IRQ":
        return event.get("irq") in {0x0002, 0x0200}
    return (event.get("kind") == "NAV" or
            (event.get("kind") == "B0" and
             event.get("b0_class") == "FINGERPRINT_B0"))


def _frame_metadata(frame, event: dict, event_class: str, base: float) -> dict:
    row = D274._meta(frame, base, event_class, event)
    # No body bytes are serialized.  Shape-sensitive checks stay in memory.
    return row


def _match_prefix(events: list[tuple[object, dict]]) -> tuple[int, dict]:
    observed: dict[str, tuple[object, dict]] = {}
    active = False
    index = 0
    for position, (frame, event) in enumerate(events):
        if not active:
            if D274._matches(event, "IRQ", 0x0002):
                active = True
            else:
                continue
        name, kind, value = D274.SEQUENCE[index]
        if not D274._matches(event, kind, value):
            raise EvidenceError("D279_10_PREFIX_" +
                                D274._failure(name, event))
        observed[name] = (frame, event)
        index += 1
        if index == len(D274.SEQUENCE):
            return position + 1, observed
    missing = D274.SEQUENCE[index][0] if active else "first_irq2"
    raise EvidenceError("D279_10_PREFIX_MISSING_" + missing.upper())


def _match_suffix(events: list[tuple[object, dict]], start: int) -> tuple[int, dict]:
    observed: dict[str, tuple[object, dict]] = {}
    index = 0
    for position in range(start, len(events)):
        frame, event = events[position]
        name, kind, value = SUFFIX[index]
        if _matches(event, kind, value):
            observed[name] = (frame, event)
            index += 1
            if index == len(SUFFIX):
                return position + 1, observed
            continue
        # FDT polling (0x36/IRQ0100), housekeeping and non-fingerprint B0 are
        # allowed between edges.  A conflicting lifecycle event is not.
        if _lifecycle_bearing(event):
            raise EvidenceError("THIRD_CYCLE_PROTOCOL_CONTRADICTION_AT_" + name.upper())
    raise EvidenceError("MISSING_" + SUFFIX[index][0].upper())


def _event_rows(frames: list) -> list[tuple[object, dict]]:
    rows = []
    for frame in frames:
        try:
            rows.append((frame, D274._event(frame)))
        except D274.EvidenceError as exc:
            raise EvidenceError(str(exc)) from exc
    return rows


def analyze_frames(frames: list, base: float, synthetic: bool) -> dict:
    events = _event_rows(frames)
    suffix_start, prefix = _match_prefix(events)
    after_third, suffix = _match_suffix(events, suffix_start)

    trailing = [event for _, event in events[after_third:]]
    fourth = D274._third_cycle_lifecycle(trailing)
    if fourth is D274.ThirdCycleLifecycleResult.COMPLETE:
        raise EvidenceError("FOURTH_CYCLE_OBSERVED")
    if fourth is D274.ThirdCycleLifecycleResult.CONTRADICTION:
        raise EvidenceError("FOURTH_CYCLE_PROTOCOL_CONTRADICTION")

    observed = {**prefix, **suffix}
    sequence_frames = {}
    timing = {}
    for name, _, _ in SUFFIX:
        frame, event = observed[name]
        sequence_frames[name] = _frame_metadata(
            frame, event, name.upper(), base)
        timing[name] = round((frame.timestamp - base) * 1000, 3)

    terminal = observed["third_b0"][0]
    return {
        "schema": "D279_10_THIRD_ACQUISITION_EVIDENCE_V1",
        "capture_sha256": None,
        "target_vid": "27c6",
        "target_pid": "5125",
        "firmware_identity_status": (
            "SYNTHETIC_APP12509" if synthetic else
            "TARGET_CAPTURE_OBSERVED_APP12509"
        ),
        "workflow_class": WORKFLOW,
        "boundary_status": "OBSERVED_COMPLETE",
        "stop_reason": "THIRD_FINGERPRINT_B0",
        "failure_class": None,
        "terminal_frame": terminal.packet_index,
        "sequence_frames": sequence_frames,
        "timing_observations_ms": timing,
        "host_capture_deadline_seconds": HOST_CAPTURE_DEADLINE_SECONDS,
        "host_deadline_policy": "EVIDENCE_BOUNDED_NOT_DEVICE_TIMEOUT_CLAIM",
        "device_timeout_claim": "UNKNOWN",
        "automatic_retry_count": 0,
        "fourth_cycle_observed": False,
        "privacy_payload_exported": False,
        "biometric_plaintext_exported": False,
        "biometric_hash_exported": False,
        "secret_material_exported": False,
        "pin_value_exported": False,
    }


def _target_analysis(data: bytes, *, growing: bool, synthetic: bool) -> dict:
    try:
        packets = D274.parse_usbpcap_bytes(
            data, allow_trailing_incomplete=growing)
        frames, firmware_ok = D274._target_frames(
            packets, include_incomplete=False)
    except D274.EvidenceError as exc:
        raise EvidenceError(str(exc)) from exc
    require(firmware_ok or synthetic, "WRONG_OR_MISSING_FIRMWARE_APP12509")
    require(bool(frames), "TARGET_FRAMES_MISSING")
    base = min(frame.timestamp for frame in frames)
    document = analyze_frames(frames, base, synthetic)
    if frames[-1].timestamp - base > HOST_CAPTURE_DEADLINE_SECONDS:
        raise EvidenceError("CAPTURE_DEADLINE_EXCEEDED")
    return document


def inspect_growing_capture(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        return {"status": "PENDING", "failure_class": "CAPTURE_NOT_MATERIALIZED"}
    try:
        document = _target_analysis(path.read_bytes(), growing=True,
                                    synthetic=False)
    except EvidenceError as exc:
        failure = str(exc)
        pending = (failure.startswith("MISSING_") or
                   failure.startswith("D279_10_PREFIX_MISSING_") or
                   failure in {"TRUNCATED_PCAP_METADATA", "PCAP_INTERFACE_MISSING",
                               "TARGET_27C6_5125_NOT_IDENTIFIED",
                               "WRONG_OR_MISSING_FIRMWARE_APP12509",
                               "TARGET_FRAMES_MISSING"})
        return {"status": "PENDING" if pending else "FAIL_CLOSED",
                "failure_class": failure}
    return {"status": "THIRD_FINGERPRINT_B0_OBSERVED",
            "terminal_frame": document["terminal_frame"]}


def validate_document(document: dict) -> None:
    required = {
        "schema", "capture_sha256", "target_vid", "target_pid",
        "firmware_identity_status", "workflow_class", "boundary_status",
        "stop_reason", "failure_class", "terminal_frame", "sequence_frames",
        "timing_observations_ms", "host_capture_deadline_seconds",
        "host_deadline_policy", "device_timeout_claim",
        "automatic_retry_count", "fourth_cycle_observed",
        "privacy_payload_exported", "biometric_plaintext_exported",
        "biometric_hash_exported", "secret_material_exported",
        "pin_value_exported",
    }
    require(set(document) == required, "SCHEMA_TOP_LEVEL_FIELDS")
    require(document["schema"] == "D279_10_THIRD_ACQUISITION_EVIDENCE_V1",
            "SCHEMA_ID")
    require(set(document["sequence_frames"]) == {row[0] for row in SUFFIX},
            "SCHEMA_SEQUENCE_FIELDS")
    require(isinstance(document["terminal_frame"], int) and
            document["terminal_frame"] >= 0, "SCHEMA_TERMINAL_FRAME")
    require(document["automatic_retry_count"] == 0, "SCHEMA_RETRY")
    require(document["fourth_cycle_observed"] is False, "SCHEMA_FOURTH")
    forbidden = re.compile(
        r"(^|_)(raw|body|payload|plaintext|image|raster|pixel|template|"
        r"descriptor|psk|secret|pin)($|_)", re.IGNORECASE)

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                require(forbidden.search(key) is None or key in {
                    "privacy_payload_exported", "biometric_plaintext_exported",
                    "secret_material_exported", "pin_value_exported"
                }, "PRIVACY_FORBIDDEN_FIELD")
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document)
    for key in ("privacy_payload_exported", "biometric_plaintext_exported",
                "biometric_hash_exported", "secret_material_exported",
                "pin_value_exported", "fourth_cycle_observed"):
        require(document[key] is False, "PRIVACY_OR_SCOPE_FLAG")


def process_capture(path: Path, expected_sha256: str, *, synthetic=False,
                    observer_signal: Path | None = None) -> dict:
    require(re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
            "EXPECTED_SHA256_INVALID")
    require(path.is_file(), "CAPTURE_NOT_REGULAR")
    actual = sha256_file(path)
    require(actual == expected_sha256, "CAPTURE_SHA256_MISMATCH")
    document = _target_analysis(path.read_bytes(), growing=False,
                                synthetic=synthetic)
    document["capture_sha256"] = actual
    validate_document(document)
    if observer_signal is not None:
        require(observer_signal.is_file(), "OBSERVER_SIGNAL_MISSING")
        signal = json.loads(observer_signal.read_text(encoding="utf-8"))
        require(signal == {
            "schema": "D279_10_WIRE_OBSERVER_SIGNAL_V1",
            "status": "THIRD_FINGERPRINT_B0_OBSERVED",
            "terminal_frame": document["terminal_frame"],
            "stop_trigger": "WIRE_DRIVEN",
            "automatic_retry_count": 0,
        }, "OBSERVER_SIGNAL_FINAL_MISMATCH")
    return document


def write_once(path: Path, document: dict) -> None:
    require(not path.exists(), "OUTPUT_COLLISION")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    os.replace(str(temporary), str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcap", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--observer-signal", type=Path)
    args = parser.parse_args()
    try:
        document = process_capture(args.pcap, args.expected_sha256,
                                   observer_signal=args.observer_signal)
        write_once(args.output, document)
        print(json.dumps({"boundary_status": document["boundary_status"],
                          "terminal_frame": document["terminal_frame"]}))
        return 0
    except (EvidenceError, OSError, ValueError) as exc:
        print(json.dumps({"boundary_status": "NOT_OBSERVED_COMPLETE",
                          "failure_class": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
