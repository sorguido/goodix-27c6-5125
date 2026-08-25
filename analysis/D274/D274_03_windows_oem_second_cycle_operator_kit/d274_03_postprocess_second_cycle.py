#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Sanitizer offline D274/03 per il boundary OEM del secondo ciclo.

Legge una sola capture USBPcap hash-gated, ricostruisce esclusivamente metadata
di framing A0/B0 e si ferma logicamente al secondo B0 fingerprint strutturale.
Non apre USB, non decifra TLS e non serializza contenuto biometrico.
"""

from __future__ import annotations

import argparse
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
TARGET_VID_LE = bytes.fromhex("c627")
TARGET_PID_LE = bytes.fromhex("2551")
HOST_CAPTURE_DEADLINE_SECONDS = 180
FINGERPRINT_B0_TOTAL_LENGTH = 7726
FINGERPRINT_B0_DECLARED_LENGTH = 7722
WORKFLOW = "WINDOWS_HELLO_SETUP_CANDIDATE_NO_COMMIT"


class EvidenceError(RuntimeError):
    """Errore tipizzato fail-closed."""


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
            interfaces.append((struct.unpack_from(endian + "H", body, 0)[0],
                               _ts_resolution(body[8:], endian)))
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
            require(len(raw) >= 27, "TRUNCATED_USBCAP_METADATA")
            header_len = struct.unpack_from("<H", raw, 0)[0]
            require(27 <= header_len <= len(raw), "MALFORMED_USBCAP_HEADER")
            data_len = struct.unpack_from("<I", raw, 23)[0]
            require(header_len + data_len <= len(raw), "TRUNCATED_USBCAP_PAYLOAD")
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
            expected = 4 + int.from_bytes(current.raw[1:3], "little")
            if len(current.raw) >= expected:
                current.raw = current.raw[:expected]
                frames.append(current)
                del pending[key]
            continue
        if packet.payload[0] not in (0xA0, 0xB0):
            continue
        require(len(packet.payload) >= 4, "MALFORMED_OUTER_FRAME")
        expected = 4 + int.from_bytes(packet.payload[1:3], "little")
        require(expected >= (8 if packet.payload[0] == 0xA0 else 4),
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


def classify_b0(frame: Frame) -> str:
    if (frame.direction != "device_to_host" or frame.truncated
            or frame.outer != 0xB0 or len(frame.raw) != FINGERPRINT_B0_TOTAL_LENGTH):
        return "B0_OTHER"
    declared = int.from_bytes(frame.raw[1:3], "little")
    if declared != FINGERPRINT_B0_DECLARED_LENGTH or frame.raw[4:7] != b"\x17\x03\x03":
        return "B0_OTHER"
    tls_declared = int.from_bytes(frame.raw[7:9], "big")
    return "FINGERPRINT_B0" if tls_declared + 5 == declared else "B0_OTHER"


def _event(frame: Frame) -> dict:
    if frame.outer == 0xB0:
        require(not frame.truncated, "MALFORMED_B0")
        return {"kind": "B0", "b0_class": classify_b0(frame), "frame": frame}
    # Il NAV target-observed ha una forma A0 command-specific senza checksum
    # corto ordinario: 2417 byte outer, inner 2410, control wire esatto 0x50.
    if (frame.direction == "device_to_host" and not frame.truncated
            and len(frame.raw) == 2417 and frame.raw[4] == 0x50
            and int.from_bytes(frame.raw[5:7], "little") == 2410):
        return {"kind": "NAV", "control": 0x50, "frame": frame}
    control, body = parse_a0(frame)
    if frame.direction == "host_to_device":
        return {"kind": "COMMAND", "control": control, "body": body, "frame": frame}
    if control == 0xB0 and len(body) == 2:
        return {"kind": "ACK", "echo": body[0], "status": body[1], "frame": frame}
    if control in (0x32, 0x34, 0x36) and len(body) >= 2:
        return {"kind": "IRQ", "irq": int.from_bytes(body[:2], "little"),
                "control": control, "frame": frame}
    return {"kind": "A0_OTHER", "control": control, "frame": frame}


# Il prefisso distingue il re-arm dal primo arm: senza il lifecycle precedente
# non si può promuovere il B0 seguente a "secondo" in modo non ambiguo.
SEQUENCE = (
    ("first_irq2", "IRQ", 0x0002),
    ("first_0x22", "COMMAND", 0x22),
    ("first_0x22_ack", "ACK", 0x22),
    ("first_b0", "FINGERPRINT_B0", None),
    ("first_0x34", "COMMAND", 0x34),
    ("first_0x34_ack", "ACK", 0x34),
    ("first_irq0200", "IRQ", 0x0200),
    ("post_up_0x20", "COMMAND", 0x20),
    ("post_up_0x20_ack", "ACK", 0x20),
    ("post_up_b0", "FINGERPRINT_B0", None),
    ("post_up_0x50", "COMMAND", 0x50),
    ("post_up_0x50_ack", "ACK", 0x50),
    ("post_0x50_nav", "NAV", 0x50),
    ("rearm_0x32", "COMMAND", 0x32),
    ("rearm_0x32_ack", "ACK", 0x32),
    ("second_irq2", "IRQ", 0x0002),
    ("second_0x22", "COMMAND", 0x22),
    ("second_0x22_ack", "ACK", 0x22),
    ("second_b0", "FINGERPRINT_B0", None),
)


def _matches(event: dict, kind: str, value: int | None) -> bool:
    if kind == "FINGERPRINT_B0":
        return event.get("kind") == "B0" and event.get("b0_class") == "FINGERPRINT_B0"
    if event.get("kind") != kind:
        return False
    if kind == "COMMAND":
        if event["control"] != value:
            return False
        return value not in (0x20, 0x22) or event["body"] == b"\x01\x00"
    if kind == "ACK":
        return event["echo"] == value and event["status"] == 0x01
    if kind == "IRQ":
        return event["irq"] == value
    if kind == "NAV":
        frame = event["frame"]
        return event["control"] == 0x50 and len(frame.raw) == 2417
    return True


def _failure(expected: str, event: dict | None) -> str:
    if event is None:
        return "MISSING_" + expected.upper()
    if expected == "second_irq2" and event.get("kind") == "IRQ":
        return "WRONG_SECOND_IRQ"
    if expected == "second_irq2":
        return "MISSING_SECOND_IRQ2"
    if expected == "second_0x22" and not (event.get("kind") == "COMMAND"
                                           and event.get("control") == 0x22):
        return "MISSING_SECOND_0X22"
    if expected == "second_0x22_ack":
        if event.get("kind") == "COMMAND" and event.get("control") == 0x22:
            return "DUPLICATE_SECOND_0X22"
        if event.get("kind") == "ACK":
            if event.get("echo") != 0x22:
                return "ACK_ECHO_MISMATCH"
            if event.get("status") != 0x01:
                return "ACK_STATUS_NOT_EXACT_0X01"
    if expected == "second_b0" and event.get("kind") == "B0":
        return "SECOND_B0_NOT_FINGERPRINT_SHAPE"
    if expected.endswith("_ack") and event.get("kind") == "ACK":
        return ("ACK_ECHO_MISMATCH" if event.get("echo") != SEQUENCE[
            next(i for i, row in enumerate(SEQUENCE) if row[0] == expected)][2]
                else "ACK_STATUS_NOT_EXACT_0X01")
    return "PROTOCOL_SEQUENCE_OUT_OF_ALLOWLIST"


def _meta(frame: Frame, base: float, event_class: str, event: dict) -> dict:
    row = {
        "frame": frame.packet_index,
        "direction": frame.direction,
        "outer_wrapper": f"0x{frame.outer:02x}",
        "physical_length": frame.physical_length,
        "declared_outer_length": len(frame.raw),
        "relative_timestamp_ms": round((frame.timestamp - base) * 1000, 3),
        "event_class": event_class,
    }
    if event["kind"] == "COMMAND":
        row["control"] = event["control"]
    elif event["kind"] == "IRQ":
        row["irq_code"] = event["irq"]
    elif event["kind"] == "ACK":
        row["ack_echo"] = event["echo"]
        row["ack_status"] = event["status"]
    elif event["kind"] == "B0":
        row["declared_b0_length"] = int.from_bytes(frame.raw[1:3], "little")
        row["tls_record_type_class"] = "TLS_APPLICATION_DATA"
    return row


OUTPUT_EVENTS = {
    "rearm_0x32": "REARM_0X32",
    "rearm_0x32_ack": "ACK_0X32_STATUS_0X01",
    "second_irq2": "IRQ_0X0002",
    "second_0x22": "WIRE_0X22",
    "second_0x22_ack": "ACK_0X22_STATUS_0X01",
    "second_b0": "FINGERPRINT_B0",
}


def analyze_frames(frames: list[Frame], base: float, synthetic: bool) -> dict:
    events: list[dict] = []
    observed: dict[str, tuple[Frame, dict]] = {}
    active = False
    index = 0
    complete_at: int | None = None
    failure: str | None = None
    for frame in frames:
        try:
            event = _event(frame)
        except EvidenceError:
            if active:
                raise
            continue
        events.append(event)
        if complete_at is not None:
            continue
        if not active:
            if _matches(event, "IRQ", 0x0002):
                active = True
            else:
                continue
        expected, kind, value = SEQUENCE[index]
        if not _matches(event, kind, value):
            failure = _failure(expected, event)
            break
        observed[expected] = (frame, event)
        index += 1
        if index == len(SEQUENCE):
            complete_at = len(events) - 1
    if failure is None and index < len(SEQUENCE):
        failure = _failure(SEQUENCE[index][0], None)

    remaining = events[complete_at + 1:] if complete_at is not None else []
    third_cycle = any(
        (event.get("kind") == "IRQ" and event.get("irq") == 0x0002)
        or (event.get("kind") == "COMMAND" and event.get("control") == 0x22)
        or (event.get("kind") == "B0" and event.get("b0_class") == "FINGERPRINT_B0")
        for event in remaining
    )
    if third_cycle:
        failure = "THIRD_CYCLE_OBSERVED"

    complete = index == len(SEQUENCE) and failure is None
    metadata = {}
    for name, event_class in OUTPUT_EVENTS.items():
        pair = observed.get(name)
        metadata[name + "_frame"] = (_meta(pair[0], base, event_class, pair[1])
                                      if pair else None)
    timing = {}
    names = [name for name in OUTPUT_EVENTS if name in observed]
    for name in names:
        timing[name] = round((observed[name][0].timestamp - base) * 1000, 3)
    for previous, current in zip(names, names[1:]):
        timing[f"delta_{previous}_to_{current}"] = round(
            (observed[current][0].timestamp - observed[previous][0].timestamp) * 1000, 3)

    return {
        "schema": "D274_03_SECOND_CYCLE_EVIDENCE_V1",
        "capture_sha256": None,
        "target_vid": "27c6",
        "target_pid": "5125",
        "firmware_identity_status": "SYNTHETIC_APP12509" if synthetic else "UNKNOWN",
        "workflow_class": WORKFLOW,
        "boundary_status": "OBSERVED_COMPLETE" if complete else "NOT_OBSERVED_COMPLETE",
        **metadata,
        "third_cycle_observed": third_cycle,
        "stop_reason": "SECOND_FINGERPRINT_B0" if complete else "FAIL_CLOSED",
        "failure_class": failure,
        "host_capture_deadline_seconds": HOST_CAPTURE_DEADLINE_SECONDS,
        "host_deadline_policy": "EVIDENCE_BOUNDED_NOT_DEVICE_TIMEOUT_CLAIM",
        "device_timeout_claim": "UNKNOWN",
        "timing_observations_ms": timing,
        "counts": {
            "irq0002": sum(e.get("kind") == "IRQ" and e.get("irq") == 0x0002 for e in events),
            "wire_0x22": sum(e.get("kind") == "COMMAND" and e.get("control") == 0x22 for e in events),
            "fingerprint_b0": sum(e.get("kind") == "B0" and e.get("b0_class") == "FINGERPRINT_B0" for e in events),
        },
        "privacy_payload_exported": False,
        "biometric_plaintext_exported": False,
        "biometric_hash_exported": False,
        "secret_material_exported": False,
    }


def _strict_validate(node, schema: dict, defs: dict) -> None:
    while "$ref" in schema:
        schema = defs[schema["$ref"].rpartition("/")[2]]
    if "const" in schema:
        require(node == schema["const"], "SCHEMA_CONST")
        return
    if "enum" in schema:
        require(node in schema["enum"], "SCHEMA_ENUM")
        return
    if "anyOf" in schema:
        for sub in schema["anyOf"]:
            try:
                _strict_validate(node, sub, defs)
                return
            except EvidenceError:
                pass
        raise EvidenceError("SCHEMA_ANYOF")
    kind = schema.get("type")
    matches = {
        "object": isinstance(node, dict),
        "array": isinstance(node, list),
        "string": isinstance(node, str),
        "boolean": isinstance(node, bool),
        "null": node is None,
        "integer": isinstance(node, int) and not isinstance(node, bool),
        "number": isinstance(node, (int, float)) and not isinstance(node, bool),
    }
    if kind:
        require(matches.get(kind, False), "SCHEMA_TYPE")
    if isinstance(node, dict):
        allowed = set(schema.get("properties", {}))
        if schema.get("additionalProperties") is False:
            require(set(node) <= allowed, "SCHEMA_ADDITIONAL_PROPERTY")
        require(set(schema.get("required", [])) <= set(node), "SCHEMA_REQUIRED")
        for key, value in node.items():
            if key in schema.get("properties", {}):
                _strict_validate(value, schema["properties"][key], defs)
            elif isinstance(schema.get("additionalProperties"), dict):
                _strict_validate(value, schema["additionalProperties"], defs)
    if isinstance(node, str) and "pattern" in schema:
        require(re.fullmatch(schema["pattern"], node) is not None, "SCHEMA_PATTERN")


def validate_document(document: dict) -> None:
    schema_path = Path(__file__).resolve().with_name("D274_03_evidence_schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    _strict_validate(document, schema, schema.get("$defs", {}))
    serialized_keys = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            serialized_keys.update(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document)
    forbidden = {"raw", "body", "payload", "plaintext", "image", "raster",
                 "pixel", "template", "descriptor", "psk", "secret"}
    require(not (serialized_keys & forbidden), "PRIVACY_FORBIDDEN_FIELD")


def target_descriptors(packets: list[UsbPacket]) -> list[UsbPacket]:
    return [packet for packet in packets
            if len(packet.payload) >= 12 and packet.payload[:2] == b"\x12\x01"
            and packet.payload[8:10] == TARGET_VID_LE
            and packet.payload[10:12] == TARGET_PID_LE]


def process_capture(path: Path, expected_sha256: str, *, synthetic: bool = False) -> dict:
    require(re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
            "EXPECTED_SHA256_INVALID")
    actual = sha256_file(path)
    require(actual == expected_sha256, "CAPTURE_HASH_MISMATCH")
    packets = list(iter_usbpcap(path))
    require(bool(packets), "CAPTURE_EMPTY")
    require(packets[-1].timestamp - packets[0].timestamp <= HOST_CAPTURE_DEADLINE_SECONDS,
            "CAPTURE_DEADLINE_EXCEEDED")
    descriptors = target_descriptors(packets)
    require(bool(descriptors), "TARGET_27C6_5125_NOT_IDENTIFIED")
    devices = {(packet.bus, packet.device) for packet in descriptors}
    require(len(devices) == 1, "AMBIGUOUS_TARGET")
    episodes = 1 + sum(current.timestamp - previous.timestamp > 2.0
                       for previous, current in zip(descriptors, descriptors[1:]))
    require(episodes == 1, "TARGET_REENUMERATION_OBSERVED")
    selected = next(iter(devices))
    frames = [frame for frame in split_frames(packets)
              if (frame.bus, frame.device) == selected]
    firmware_ok = False
    for frame in frames:
        if frame.direction != "device_to_host" or frame.outer != 0xA0 or frame.truncated:
            continue
        try:
            control, body = parse_a0(frame)
        except EvidenceError:
            continue
        if control == 0xA8 and EXPECTED_FIRMWARE.encode() in body:
            firmware_ok = True
            break
    require(firmware_ok, "WRONG_OR_MISSING_FIRMWARE_APP12509")
    document = analyze_frames(frames, packets[0].timestamp, synthetic)
    document["capture_sha256"] = actual
    document["firmware_identity_status"] = (
        "SYNTHETIC_APP12509" if synthetic else "TARGET_CAPTURE_OBSERVED_APP12509")
    validate_document(document)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pcap", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), "SANITIZED_OUTPUT_COLLISION")
        result = process_capture(args.pcap, args.expected_sha256.lower())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"boundary_status": result["boundary_status"],
                          "stop_reason": result["stop_reason"],
                          "failure_class": result["failure_class"]}))
        return 0 if result["failure_class"] is None else 2
    except (EvidenceError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"boundary_status": "NOT_OBSERVED_COMPLETE",
                          "stop_reason": "FAIL_CLOSED", "failure_class": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
