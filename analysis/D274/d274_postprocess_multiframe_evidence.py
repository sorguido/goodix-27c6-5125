#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""D274 offline USBPcap multiframe evidence sanitizer.

The program never opens USB and never decrypts or serializes B0 contents.  It
accepts one hash-gated pcapng, reconstructs only A0/B0 framing metadata, and
recognizes the bounded OEM sequence ending at the second B0.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SHB = 0x0A0D0D0A
IDB = 0x00000001
EPB = 0x00000006
USBPCAP_LINKTYPE = 249
EXPECTED_FIRMWARE = "GF_ST411SEC_APP_12509"
TARGET_VID = "27c6"
TARGET_PID = "5125"
TARGET_VID_LE = bytes.fromhex("c627")
TARGET_PID_LE = bytes.fromhex("2551")
HOST_CAPTURE_DEADLINE_SECONDS = 180
HOST_DEADLINE_POLICY = "EVIDENCE_BOUNDED_NOT_DEVICE_TIMEOUT_CLAIM"
DEVICE_TIMEOUT_CLAIM = "UNKNOWN"
EVIDENCE_CLASSES = {
    "TARGET_CAPTURE_OBSERVED", "STATICALLY_VERIFIED_OEM",
    "STRONG_CAUSAL_INFERENCE", "INFERRED", "THIRD_PARTY_CORROBORATION",
    "OPERATOR_MARKER_ONLY", "UNKNOWN", "SYNTHETIC_FIXTURE_PASS",
}


class EvidenceError(RuntimeError):
    """Typed, fail-closed evidence error."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ts_resolution(options: bytes, endian: str) -> float:
    offset = 0
    while offset + 4 <= len(options):
        code, length = struct.unpack_from(endian + "HH", options, offset)
        offset += 4
        value = options[offset:offset + length]
        offset += (length + 3) & ~3
        if code == 0:
            break
        if code == 9 and value:
            raw = value[0]
            return float(2 ** -(raw & 0x7F) if raw & 0x80 else 10 ** -raw)
    return 1e-6


@dataclass(frozen=True)
class UsbPacket:
    index: int
    timestamp: float
    bus: int
    device: int
    endpoint: int
    transfer: int
    info: int
    payload: bytes
    data_len: int


def iter_usbpcap(path: Path) -> Iterable[UsbPacket]:
    data = path.read_bytes()
    require(len(data) >= 28, "TRUNCATED_PCAP_METADATA")
    endian = "<"
    interfaces: list[tuple[int, float]] = []
    offset = 0
    packet_index = 0
    while offset + 12 <= len(data):
        block_type = struct.unpack_from(endian + "I", data, offset)[0]
        if block_type == SHB:
            require(offset + 12 <= len(data), "TRUNCATED_PCAP_METADATA")
            bom = data[offset + 8:offset + 12]
            if bom == b"\x4d\x3c\x2b\x1a":
                endian = "<"
            elif bom == b"\x1a\x2b\x3c\x4d":
                endian = ">"
            else:
                raise EvidenceError("MALFORMED_PCAPNG_BYTE_ORDER")
            block_type = SHB
        block_length = struct.unpack_from(endian + "I", data, offset + 4)[0]
        require(block_length >= 12 and offset + block_length <= len(data),
                "TRUNCATED_PCAP_METADATA")
        require(struct.unpack_from(endian + "I", data, offset + block_length - 4)[0]
                == block_length, "MALFORMED_PCAPNG_TRAILER")
        body = data[offset + 8:offset + block_length - 4]
        if block_type == IDB:
            require(len(body) >= 8, "TRUNCATED_PCAP_METADATA")
            linktype = struct.unpack_from(endian + "H", body, 0)[0]
            interfaces.append((linktype, _ts_resolution(body[8:], endian)))
        elif block_type == EPB:
            require(len(body) >= 20, "TRUNCATED_PCAP_METADATA")
            interface_id, ts_hi, ts_lo, captured, original = struct.unpack_from(
                endian + "IIIII", body, 0)
            require(interface_id < len(interfaces), "PCAP_INTERFACE_MISSING")
            require(captured == original and 20 + captured <= len(body),
                    "TRUNCATED_PCAP_METADATA")
            linktype, resolution = interfaces[interface_id]
            require(linktype == USBPCAP_LINKTYPE, "UNEXPECTED_LINKTYPE")
            raw = body[20:20 + captured]
            require(len(raw) >= 27, "TRUNCATED_USBPcap_METADATA")
            header_len = struct.unpack_from("<H", raw, 0)[0]
            require(27 <= header_len <= len(raw), "MALFORMED_USBPcap_HEADER")
            data_len = struct.unpack_from("<I", raw, 23)[0]
            require(header_len + data_len <= len(raw), "TRUNCATED_USBPcap_PAYLOAD")
            yield UsbPacket(
                packet_index,
                ((ts_hi << 32) | ts_lo) * resolution,
                struct.unpack_from("<H", raw, 17)[0],
                struct.unpack_from("<H", raw, 19)[0],
                raw[21], raw[22], raw[16], raw[header_len:header_len + data_len],
                data_len,
            )
            packet_index += 1
        offset += block_length
    require(offset == len(data), "TRUNCATED_PCAP_METADATA")
    require(bool(interfaces), "PCAP_INTERFACE_MISSING")


@dataclass
class Frame:
    packet_index: int
    timestamp: float
    bus: int
    device: int
    direction: str
    endpoint: int
    outer: int
    raw: bytes
    physical_length: int
    truncated: bool = False


def split_frames(packets: list[UsbPacket]) -> list[Frame]:
    frames: list[Frame] = []
    pending: dict[tuple[int, int, int, int], Frame] = {}
    for packet in packets:
        if packet.transfer != 3 or packet.endpoint not in (0x01, 0x81) or not packet.payload:
            continue
        direction = "host_to_device" if packet.endpoint == 0x01 else "device_to_host"
        key = (packet.bus, packet.device, packet.endpoint, packet.info)
        current = pending.get(key)
        if current is not None:
            current.raw += packet.payload
            current.physical_length += packet.data_len
            if len(current.raw) >= 4 + int.from_bytes(current.raw[1:3], "little"):
                expected = 4 + int.from_bytes(current.raw[1:3], "little")
                current.raw = current.raw[:expected]
                frames.append(current)
                del pending[key]
            continue
        if packet.payload[0] not in (0xA0, 0xB0):
            continue
        require(len(packet.payload) >= 4, "MALFORMED_OUTER_FRAME")
        expected = 4 + int.from_bytes(packet.payload[1:3], "little")
        require(expected >= 8 if packet.payload[0] == 0xA0 else expected >= 4,
                "MALFORMED_OUTER_FRAME")
        frame = Frame(packet.index, packet.timestamp, packet.bus, packet.device,
                      direction, packet.endpoint, packet.payload[0],
                      packet.payload[:expected], packet.data_len)
        if len(packet.payload) >= expected:
            frames.append(frame)
        else:
            pending[key] = frame
    for frame in pending.values():
        frame.truncated = True
        frames.append(frame)
    return sorted(frames, key=lambda item: (item.timestamp, item.packet_index))


def parse_a0(frame: Frame) -> tuple[int, bytes]:
    require(frame.outer == 0xA0 and not frame.truncated and len(frame.raw) >= 8,
            "MALFORMED_A0")
    inner_len = int.from_bytes(frame.raw[5:7], "little")
    inner = frame.raw[7:7 + inner_len]
    require(inner_len >= 1 and len(inner) == inner_len, "MALFORMED_A0")
    require(((frame.raw[4] & 0xFE) + frame.raw[5] + frame.raw[6] + sum(inner)) & 0xFF
            == 0xAA, "MALFORMED_A0")
    return frame.raw[4], inner[:-1]


def target_descriptors(packets: list[UsbPacket]) -> list[UsbPacket]:
    return [packet for packet in packets
            if len(packet.payload) >= 12 and packet.payload[:2] == b"\x12\x01"
            and packet.payload[8:10] == TARGET_VID_LE
            and packet.payload[10:12] == TARGET_PID_LE]


def _frame_meta(frame: Frame, base_timestamp: float) -> dict:
    row = {
        "frame": frame.packet_index,
        "direction": frame.direction,
        "outer_wrapper": f"0x{frame.outer:02x}",
        "physical_length": frame.physical_length,
        "declared_outer_length": len(frame.raw),
        "relative_timestamp_ms": round((frame.timestamp - base_timestamp) * 1000, 3),
    }
    if frame.outer == 0xB0:
        row["declared_b0_length"] = int.from_bytes(frame.raw[1:3], "little")
        body_prefix = frame.raw[4:7]
        row["tls_record_type_class"] = (
            "TLS_APPLICATION_DATA" if body_prefix == b"\x17\x03\x03" else "UNKNOWN"
        )
    return row


def _event(frame: Frame) -> dict:
    if frame.outer == 0xB0:
        require(not frame.truncated, "MALFORMED_B0")
        return {"kind": "B0", "frame": frame}
    # The target-observed post-0x50 NAV response is an exact command-specific
    # A0 shape (wire control 0x50, physical/outer 2417, inner 2410). Its final
    # byte does not satisfy the ordinary short-command checksum equation, so
    # it must not be rejected or normalized through generic A0 semantics.
    if (frame.direction == "device_to_host" and not frame.truncated
            and len(frame.raw) == 2417 and frame.raw[0] == 0xA0
            and frame.raw[4] == 0x50
            and int.from_bytes(frame.raw[5:7], "little") == 2410):
        return {"kind": "NAV", "control": 0x50, "body_length": 2409, "frame": frame}
    control, body = parse_a0(frame)
    if frame.direction == "host_to_device":
        return {"kind": "COMMAND", "control": control, "body": body, "frame": frame}
    if control == 0xB0 and len(body) == 2:
        return {"kind": "ACK", "echo": body[0], "status": body[1], "frame": frame}
    if control in (0x32, 0x34, 0x36) and len(body) >= 2:
        return {"kind": "IRQ", "irq": int.from_bytes(body[:2], "little"),
                "control": control, "frame": frame}
    if control == 0x50:
        return {"kind": "NAV", "control": control, "body_length": len(body), "frame": frame}
    return {"kind": "A0_OTHER", "control": control, "frame": frame}


SEQUENCE = (
    ("first_irq2", "IRQ", 0x0002),
    ("first_0x22", "COMMAND", 0x22),
    ("first_0x22_ack", "ACK", 0x22),
    ("first_image_b0", "B0", None),
    ("first_0x34", "COMMAND", 0x34),
    ("first_0x34_ack", "ACK", 0x34),
    ("first_irq0200", "IRQ", 0x0200),
    ("post_up_0x20", "COMMAND", 0x20),
    ("post_up_0x20_ack", "ACK", 0x20),
    ("post_up_b0", "B0", None),
    ("post_up_0x50", "COMMAND", 0x50),
    ("post_up_0x50_ack", "ACK", 0x50),
    ("post_0x50_nav", "NAV", 0x50),
    ("rearm_0x32", "COMMAND", 0x32),
    ("rearm_0x32_ack", "ACK", 0x32),
    ("second_irq2", "IRQ", 0x0002),
    ("second_0x22", "COMMAND", 0x22),
    ("second_0x22_ack", "ACK", 0x22),
    ("second_b0", "B0", None),
)


def _matches(event: dict, kind: str, value: int | None) -> bool:
    if event["kind"] != kind:
        return False
    if kind == "COMMAND":
        if event["control"] != value:
            return False
        if value in (0x20, 0x22):
            return event["body"] == b"\x01\x00"
        return True
    if kind == "ACK":
        return event["echo"] == value and event["status"] == 0x01
    if kind == "IRQ":
        return event["irq"] == value
    if kind == "NAV":
        frame = event["frame"]
        return (event["control"] == 0x50 and len(frame.raw) == 2417
                and int.from_bytes(frame.raw[5:7], "little") == 2410)
    return True


def _failure_for(expected_name: str, event: dict | None) -> str:
    if event is None:
        return "MISSING_" + expected_name.upper()
    if event["kind"] == "ACK" and expected_name.endswith("_ack"):
        if event["status"] != 0x01:
            return "ACK_STATUS_NOT_EXACT_0X01"
        return "ACK_ECHO_MISMATCH"
    if expected_name == "post_0x50_nav" and event.get("control") == 0x51:
        return "WIRE_0X51_IS_NOT_NAV"
    if expected_name == "second_0x22" and event["kind"] == "B0":
        return "B0_BEFORE_SECOND_0X22"
    if expected_name == "second_0x22_ack" and event.get("kind") == "COMMAND" \
            and event.get("control") == 0x22:
        return "DUPLICATE_SECOND_0X22"
    return "PROTOCOL_SEQUENCE_OUT_OF_ALLOWLIST"


def analyze_frames(frames: list[Frame], base_timestamp: float, workflow_class: str,
                   origin: str = "TARGET_CAPTURE") -> dict:
    events: list[dict] = []
    active = False
    sequence_index = 0
    completion_event_index: int | None = None
    observed: dict[str, Frame] = {}
    failure: str | None = None
    for frame in frames:
        try:
            event = _event(frame)
        except EvidenceError:
            if active:
                raise
            # Historical bootstrap traffic contains framing variants outside
            # the bounded multiframe window. They cannot establish or refute
            # this sequence; malformed framing after the first IRQ2 is fatal.
            continue
        events.append(event)
        if completion_event_index is not None:
            continue
        if not active:
            if _matches(event, "IRQ", 0x0002):
                active = True
            else:
                continue
        expected_name, expected_kind, expected_value = SEQUENCE[sequence_index]
        if not _matches(event, expected_kind, expected_value):
            failure = _failure_for(expected_name, event)
            break
        observed[expected_name] = event["frame"]
        sequence_index += 1
        if sequence_index == len(SEQUENCE):
            completion_event_index = len(events) - 1
    if failure is None and sequence_index < len(SEQUENCE):
        failure = _failure_for(SEQUENCE[sequence_index][0], None)

    remaining = events[completion_event_index + 1:] if completion_event_index is not None else []
    third_cycle = any(event["kind"] in {"B0", "COMMAND", "IRQ"} and (
        event["kind"] == "B0" or event.get("control") == 0x22 or event.get("irq") == 0x0002
    ) for event in remaining)
    if observed.get("second_b0") and remaining:
        if any(event["kind"] == "B0" for event in remaining):
            failure = "DUPLICATE_SECOND_B0"
        elif third_cycle:
            failure = "THIRD_CYCLE_OBSERVED"

    complete = sequence_index == len(SEQUENCE) and failure is None
    metadata = {name: _frame_meta(frame, base_timestamp) for name, frame in observed.items()}
    cycle_associations = {
        "first_image_b0": "FIRST_CYCLE_FINGERPRINT",
        "post_up_b0": "FIRST_CYCLE_POST_UP",
        "second_b0": "SECOND_CYCLE_FINGERPRINT",
    }
    for name, association in cycle_associations.items():
        if name in metadata:
            metadata[name]["cycle_association"] = association
    field_map = {
        "first_image_b0_frame": "first_image_b0",
        "first_0x34_frame": "first_0x34",
        "first_irq0200_frame": "first_irq0200",
        "post_up_0x20_frame": "post_up_0x20",
        "post_up_b0_frame": "post_up_b0",
        "post_up_0x50_frame": "post_up_0x50",
        "post_0x50_nav_frame": "post_0x50_nav",
        "rearm_0x32_frame": "rearm_0x32",
        "second_irq2_frame": "second_irq2",
        "second_0x22_frame": "second_0x22",
        "second_0x22_ack_frame": "second_0x22_ack",
        "second_b0_frame": "second_b0",
    }
    timing_names = ("first_image_b0", "first_0x34", "first_irq0200", "post_up_0x20",
                    "post_up_0x50", "post_0x50_nav", "rearm_0x32", "second_irq2",
                    "second_0x22", "second_b0")
    timing = {name: metadata[name]["relative_timestamp_ms"]
              for name in timing_names if name in metadata}
    present_timing_names = [name for name in timing_names if name in observed]
    for previous, current in zip(present_timing_names, present_timing_names[1:]):
        timing[f"delta_{previous}_to_{current}"] = round(
            (observed[current].timestamp - observed[previous].timestamp) * 1000, 3
        )
    result = {
        "capture_sha256": None,
        "target_vid": TARGET_VID,
        "target_pid": TARGET_PID,
        "firmware_identity_status": "UNKNOWN",
        "workflow_class": workflow_class,
        "first_cycle_status": ("OBSERVED_COMPLETE" if "rearm_0x32_ack" in observed
                               else "NOT_OBSERVED_COMPLETE"),
        **{output: metadata.get(source) for output, source in field_map.items()},
        "second_cycle_target_observed": bool(complete and origin == "TARGET_CAPTURE"),
        "third_cycle_observed": third_cycle,
        "timing_observations_ms": timing,
        "host_deadline_policy": HOST_DEADLINE_POLICY,
        "device_timeout_claim": DEVICE_TIMEOUT_CLAIM,
        "privacy_payload_exported": False,
        "biometric_plaintext_exported": False,
        "secret_material_exported": False,
        "result_class": ("TARGET_CAPTURE_OBSERVED" if complete and origin == "TARGET_CAPTURE"
                         else "SYNTHETIC_FIXTURE_PASS" if complete else "UNKNOWN"),
        "failure_class": failure,
    }
    return result


MARKER_ORDER = (
    "PREFLIGHT_COMPLETE", "CAPTURE_PROCESS_STARTED", "VM_USB_ATTACH_BEGIN",
    "VM_USB_ATTACH_END", "TARGET_APP12509_CONFIRMED", "OEM_UI_READY",
    "FIRST_FINGER_PROMPT", "FIRST_FINGER_DOWN_OPERATOR_CONFIRMED",
    "FIRST_FINGER_UP_OPERATOR_CONFIRMED", "SECOND_FINGER_PROMPT",
    "SECOND_FINGER_DOWN_OPERATOR_CONFIRMED", "SECOND_B0_OBSERVED",
    "CAPTURE_STOP_REQUESTED", "CAPTURE_PROCESS_STOPPED", "OFFLINE_VALIDATION_PENDING",
)
UI_TERMINAL_MARKERS = {
    "ENROLLMENT_COMMIT_UI", "ACCOUNT_MUTATION_UI", "PIN_MUTATION_UI",
    "THIRD_FINGER_PROMPT",
}


def validate_markers(path: Path) -> None:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if line_number == 1 and line.lower().startswith("timestamp_utc"):
            continue
        parts = line.split("\t")
        require(len(parts) >= 2, "MALFORMED_MARKER")
        timestamp = dt.datetime.fromisoformat(parts[0].replace("Z", "+00:00")).timestamp()
        rows.append((timestamp, parts[1]))
    require(rows == sorted(rows), "MARKER_OUT_OF_ORDER")
    names = [name for _, name in rows]
    require(not UI_TERMINAL_MARKERS.intersection(names), "UI_TERMINAL_CONDITION")
    positions = [MARKER_ORDER.index(name) for name in names if name in MARKER_ORDER]
    require(positions == sorted(positions) and len(positions) == len(set(positions)),
            "MARKER_OUT_OF_ORDER")


def validate_evidence_document(document: dict) -> None:
    required = {
        "capture_sha256", "target_vid", "target_pid", "firmware_identity_status",
        "workflow_class", "first_cycle_status", "first_image_b0_frame",
        "first_0x34_frame", "first_irq0200_frame", "post_up_0x20_frame",
        "post_up_b0_frame", "post_up_0x50_frame", "post_0x50_nav_frame",
        "rearm_0x32_frame", "second_irq2_frame", "second_0x22_frame",
        "second_0x22_ack_frame", "second_b0_frame", "second_cycle_target_observed",
        "third_cycle_observed", "timing_observations_ms", "host_deadline_policy",
        "device_timeout_claim", "privacy_payload_exported",
        "biometric_plaintext_exported", "secret_material_exported", "result_class",
        "failure_class",
    }
    require(required <= document.keys(), "EVIDENCE_SCHEMA_REQUIRED_FIELD_MISSING")
    require(document["result_class"] in EVIDENCE_CLASSES, "EVIDENCE_CLASS_INVALID")
    require(document["privacy_payload_exported"] is False, "PRIVACY_CONTRACT_VIOLATION")
    require(document["biometric_plaintext_exported"] is False,
            "PRIVACY_CONTRACT_VIOLATION")
    require(document["secret_material_exported"] is False, "PRIVACY_CONTRACT_VIOLATION")


def process_capture(pcap: Path, expected_sha256: str, workflow_class: str,
                    markers: Path | None = None, origin: str = "TARGET_CAPTURE") -> dict:
    require(re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
            "EXPECTED_SHA256_INVALID")
    actual_sha256 = sha256_file(pcap)
    require(actual_sha256 == expected_sha256, "CAPTURE_HASH_MISMATCH")
    if origin == "TARGET_CAPTURE":
        repository = Path(__file__).resolve().parents[2]
        resolved = pcap.resolve()
        historical = (repository / "analysis/D230/work/GoodixExport/rilevamento.pcapng").resolve()
        require(resolved == historical or resolved.is_relative_to((repository / "captures").resolve()),
                "RAW_CAPTURE_OUTSIDE_CANONICAL_PRIVATE_LOCATION")
    packets = list(iter_usbpcap(pcap))
    require(bool(packets), "CAPTURE_EMPTY")
    duration = packets[-1].timestamp - packets[0].timestamp
    require(duration <= HOST_CAPTURE_DEADLINE_SECONDS, "CAPTURE_DEADLINE_EXCEEDED")
    descriptors = target_descriptors(packets)
    require(bool(descriptors), "TARGET_27C6_5125_NOT_IDENTIFIED")
    devices = {(item.bus, item.device) for item in descriptors}
    require(len(devices) == 1, "SECOND_TARGET_OBSERVED")
    episodes = 1
    for previous, current in zip(descriptors, descriptors[1:]):
        if current.timestamp - previous.timestamp > 2.0:
            episodes += 1
    require(episodes == 1, "TARGET_REENUMERATION_OBSERVED")
    selected = next(iter(devices))
    frames = [frame for frame in split_frames(packets)
              if (frame.bus, frame.device) == selected]
    firmware = []
    for frame in frames:
        if frame.direction != "device_to_host" or frame.outer != 0xA0 or frame.truncated:
            continue
        try:
            parsed = parse_a0(frame)
        except EvidenceError:
            continue
        if parsed[0] == 0xA8 and EXPECTED_FIRMWARE.encode() in parsed[1]:
            firmware.append(frame)
    require(bool(firmware), "APP12509_A8_NOT_OBSERVED")
    if markers is not None:
        validate_markers(markers)
    result = analyze_frames(frames, packets[0].timestamp, workflow_class, origin)
    result["capture_sha256"] = actual_sha256
    result["firmware_identity_status"] = "TARGET_CAPTURE_OBSERVED_APP12509"
    validate_evidence_document(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcap", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--workflow-class", default="UNKNOWN")
    parser.add_argument("--markers", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), "SANITIZED_OUTPUT_COLLISION")
        result = process_capture(args.pcap, args.expected_sha256.lower(),
                                 args.workflow_class, args.markers)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"result_class": result["result_class"],
                          "failure_class": result["failure_class"],
                          "second_cycle_target_observed": result["second_cycle_target_observed"]}))
        return 0 if result["failure_class"] is None else 2
    except (EvidenceError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"result_class": "UNKNOWN", "failure_class": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
