#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline-only D255 USBPcap/cache/log sanitizer and correlator.

Raw evidence remains outside the repository.  This tool hash-gates every input
and emits only protocol metadata, FDT12 values, cache-region hashes, redacted
OEM event labels, and bounded cancel/re-entry classifications.
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
KNOWN_CONTROLS = {
    0x20, 0x22, 0x32, 0x34, 0x36, 0x70, 0x80, 0x82, 0x90,
    0xA2, 0xA6, 0xA8, 0xAE, 0xAF, 0xB0, 0xD1, 0xD2, 0xD4, 0xD5, 0xE4,
}
CACHE_SIZE = 64 + 12 + 3200 + 10240 + 4


class EvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_utc(value: str) -> float:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.timestamp()


@dataclass(frozen=True)
class InputFile:
    path: Path
    relative: str
    role: str
    size: int
    sha256: str


def load_manifest(run_dir: Path, manifest_path: Path, expected_hash: str) -> list[InputFile]:
    require(re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash) is not None,
            "manifest SHA-256 must be 64 hexadecimal characters")
    require(sha256_file(manifest_path) == expected_hash.lower(), "input manifest hash mismatch")
    document = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    require(document.get("schema") == "D255_WINDOWS_EVIDENCE_INPUT_MANIFEST_V1",
            "unexpected input manifest schema")
    root = run_dir.resolve()
    result: list[InputFile] = []
    seen: set[str] = set()
    for row in document.get("files", []):
        relative = row.get("path", "")
        require(isinstance(relative, str) and relative and relative not in seen,
                "manifest path missing or duplicated")
        require(not Path(relative).is_absolute() and ".." not in Path(relative).parts,
                "manifest path escapes run directory")
        path = (root / relative).resolve()
        require(path.is_relative_to(root), "manifest path resolves outside run directory")
        require(path.is_file(), f"manifest input missing: {relative}")
        expected_size = int(row.get("size", -1))
        expected_file_hash = str(row.get("sha256", "")).lower()
        require(path.stat().st_size == expected_size, f"input size mismatch: {relative}")
        require(sha256_file(path) == expected_file_hash, f"input hash mismatch: {relative}")
        result.append(InputFile(path, relative, str(row.get("role", "metadata")),
                                expected_size, expected_file_hash))
        seen.add(relative)
    require(result, "input manifest is empty")
    return result


@dataclass
class UsbPacket:
    index: int
    timestamp: float
    bus: int
    device: int
    endpoint: int
    transfer: int
    info: int
    function: int
    status: int
    payload: bytes
    data_len: int


def _idb_ts_resolution(body: bytes, endian: str) -> float:
    offset = 8
    while offset + 4 <= len(body):
        code, length = struct.unpack_from(endian + "HH", body, offset)
        offset += 4
        value = body[offset:offset + length]
        offset += (length + 3) & ~3
        if code == 0:
            break
        if code == 9 and value:
            raw = value[0]
            return float(2 ** -(raw & 0x7F) if raw & 0x80 else 10 ** -raw)
    return 1e-6


def iter_usbpcap(path: Path) -> Iterable[UsbPacket]:
    data = path.read_bytes()
    require(len(data) >= 12, "capture is empty or truncated")
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
                raise EvidenceError("invalid pcapng byte-order magic")
            block_type = SHB
        block_length = struct.unpack_from(endian + "I", data, offset + 4)[0]
        require(block_length >= 12 and offset + block_length <= len(data),
                f"invalid pcapng block at {offset:#x}")
        require(struct.unpack_from(endian + "I", data, offset + block_length - 4)[0] == block_length,
                f"pcapng trailing length mismatch at {offset:#x}")
        body = data[offset + 8:offset + block_length - 4]
        if block_type == IDB:
            require(len(body) >= 8, "short pcapng interface block")
            linktype = struct.unpack_from(endian + "H", body, 0)[0]
            interfaces.append((linktype, _idb_ts_resolution(body, endian)))
        elif block_type == EPB:
            require(len(body) >= 20, "short pcapng enhanced packet block")
            interface_id, ts_hi, ts_lo, captured, original = struct.unpack_from(
                endian + "IIIII", body, 0)
            require(interface_id < len(interfaces), "packet references absent interface")
            require(captured == original and 20 + captured <= len(body), "truncated USBPcap packet")
            linktype, resolution = interfaces[interface_id]
            require(linktype == USBPCAP_LINKTYPE, "capture interface is not USBPcap linktype 249")
            raw = body[20:20 + captured]
            require(len(raw) >= 27, "short USBPcap pseudoheader")
            header_len = struct.unpack_from("<H", raw, 0)[0]
            require(27 <= header_len <= len(raw), "invalid USBPcap pseudoheader length")
            data_len = struct.unpack_from("<I", raw, 23)[0]
            require(header_len + data_len <= len(raw), "USBPcap payload is truncated")
            yield UsbPacket(
                packet_index, ((ts_hi << 32) | ts_lo) * resolution,
                struct.unpack_from("<H", raw, 17)[0],
                struct.unpack_from("<H", raw, 19)[0], raw[21], raw[22], raw[16],
                struct.unpack_from("<H", raw, 14)[0], struct.unpack_from("<I", raw, 10)[0],
                raw[header_len:header_len + data_len], data_len,
            )
            packet_index += 1
        offset += block_length
    require(offset == len(data), "trailing bytes after final pcapng block")


@dataclass
class Frame:
    timestamp: float
    packet_index: int
    bus: int
    device: int
    direction: str
    endpoint: int
    outer: int
    raw: bytes
    physical_length: int
    physical_payload: bytes
    truncated: bool = False


def split_frames(packets: list[UsbPacket]) -> list[Frame]:
    frames: list[Frame] = []
    pending: dict[tuple[int, int, int, int], Frame] = {}
    for packet in packets:
        if packet.transfer != 3 or packet.endpoint not in (0x01, 0x81) or not packet.payload:
            continue
        direction = "IN" if packet.endpoint & 0x80 else "OUT"
        key = (packet.bus, packet.device, packet.endpoint, packet.info)
        current = pending.get(key)
        if current:
            current.raw += packet.payload
            if len(current.raw) >= 4 + int.from_bytes(current.raw[1:3], "little"):
                expected = 4 + int.from_bytes(current.raw[1:3], "little")
                current.raw = current.raw[:expected]
                frames.append(current)
                del pending[key]
            continue
        if packet.payload[0] not in (0xA0, 0xB0) or len(packet.payload) < 4:
            continue
        expected = 4 + int.from_bytes(packet.payload[1:3], "little")
        frame = Frame(packet.timestamp, packet.index, packet.bus, packet.device, direction,
                      packet.endpoint, packet.payload[0], packet.payload[:expected],
                      packet.data_len, packet.payload)
        if len(packet.payload) >= expected:
            frames.append(frame)
        else:
            pending[key] = frame
    for frame in pending.values():
        frame.truncated = True
        frames.append(frame)
    return sorted(frames, key=lambda row: (row.timestamp, row.packet_index))


def parse_a0(frame: Frame) -> tuple[int, bytes] | None:
    if frame.outer != 0xA0 or len(frame.raw) < 8 or frame.truncated:
        return None
    inner_len = int.from_bytes(frame.raw[5:7], "little")
    inner = frame.raw[7:7 + inner_len]
    if len(inner) != inner_len or inner_len < 1:
        return None
    control = frame.raw[4]
    if ((control & 0xFE) + frame.raw[5] + frame.raw[6] + sum(inner)) & 0xFF != 0xAA:
        return None
    return control, inner[:-1]


def select_device(frames: list[Frame], requested: str | None) -> tuple[tuple[int, int], str, bool]:
    devices = {(frame.bus, frame.device) for frame in frames if parse_a0(frame)}
    if requested:
        match = re.fullmatch(r"(\d+):(\d+)", requested)
        require(match is not None, "--usb-device must be BUS:DEVICE")
        selected = (int(match.group(1)), int(match.group(2)))
        require(selected in devices, "requested USB device has no decoded A0 traffic")
    else:
        target_candidates = set()
        for frame in frames:
            parsed = parse_a0(frame)
            if parsed and frame.direction == "IN" and parsed[0] == 0xA8:
                text = parsed[1].decode("ascii", errors="ignore")
                if EXPECTED_FIRMWARE in text:
                    target_candidates.add((frame.bus, frame.device))
        if len(target_candidates) == 1:
            selected = next(iter(target_candidates))
        else:
            require(len(devices) == 1, "device selector is ambiguous and exact A8 identity is unavailable")
            selected = next(iter(devices))
    firmware = "UNKNOWN"
    for frame in frames:
        if (frame.bus, frame.device) != selected or frame.direction != "IN":
            continue
        parsed = parse_a0(frame)
        if parsed and parsed[0] == 0xA8:
            match = re.search(rb"GF_ST411SEC_APP_[0-9]+", parsed[1])
            if match:
                firmware = match.group(0).decode("ascii")
                break
    return selected, firmware, firmware == EXPECTED_FIRMWARE


def load_markers(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if line_number == 1 and line.startswith("timestamp_utc\tevent\t"):
            continue
        parts = line.split("\t", 2)
        require(len(parts) >= 2, f"bad marker line {line_number}")
        rows.append({"timestamp": parse_utc(parts[0]), "event": parts[1], "line": line_number})
    require(rows == sorted(rows, key=lambda row: row["timestamp"]), "operator markers are not ordered")
    return rows


def one_marker(markers: list[dict], name: str, required: bool = True) -> dict | None:
    matches = [row for row in markers if row["event"] == name]
    if required:
        require(len(matches) == 1, f"marker {name} missing or duplicated")
    elif len(matches) > 1:
        raise EvidenceError(f"marker {name} duplicated")
    return matches[0] if matches else None


OEM_EVENT_PATTERNS = (
    ("BASE_FILE_READ", re.compile(r"read\s+13520-13520\s+bytes\s+from\s+base\s+file", re.I)),
    ("BASE_CRC_CHECK", re.compile(r"check\s+crc", re.I)),
    ("OTP_BINDING", re.compile(r"(?:file\s+otp|same\s+OTP|USED\s+OTP)", re.I)),
    ("UPDATE_ALL_BASE", re.compile(r"gf_update_all_base", re.I)),
    ("BASE_VALID", re.compile(r"base_is_valid", re.I)),
    ("SET_MODE", re.compile(r"ChicagoHUSetMode|setmode:\s*idle", re.I)),
    ("HOST_CANCEL", re.compile(r"gfOnCancel|cancel", re.I)),
    ("D0_EXIT", re.compile(r"D0\s*Exit|d0exit", re.I)),
    ("D0_ENTRY", re.compile(r"D0\s*Entry|d0entry", re.I)),
    ("DEVICE_CLOSE", re.compile(r"device\s+close|close\s+device", re.I)),
    ("DEVICE_RESET", re.compile(r"device\s+reset|reset\s+device", re.I)),
)


def _oem_timestamp(line: str) -> float | None:
    match = re.search(r"\b(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))\b", line)
    if not match:
        return None
    try:
        return parse_utc(match.group(1))
    except ValueError:
        return None


def parse_oem_logs(paths: list[Path]) -> tuple[list[dict], bytes | None]:
    events: list[dict] = []
    first_fdt: bytes | None = None
    for file_index, path in enumerate(paths):
        raw = path.read_bytes()
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            text = raw.decode("utf-16", errors="replace")
        elif raw.startswith(b"\xef\xbb\xbf"):
            text = raw.decode("utf-8-sig", errors="replace")
        elif raw[:4096].count(0) > max(4, len(raw[:4096]) // 8):
            text = raw.decode("utf-16le", errors="replace")
        else:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("cp1252", errors="replace")
        for line_number, line in enumerate(text.splitlines(), 1):
            if first_fdt is None:
                match = re.search(r"base\s+data\s+sent::0x([0-9a-fA-F]{24})(?![0-9a-fA-F])", line)
                if match:
                    first_fdt = bytes.fromhex(match.group(1))
            for label, pattern in OEM_EVENT_PATTERNS:
                if pattern.search(line):
                    events.append({"source_index": file_index, "line": line_number,
                                   "event": label, "timestamp": _oem_timestamp(line)})
    return events, first_fdt


def crc32_mpeg2(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for value in data:
        crc ^= value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc


def device_otp(frames: list[Frame], selected: tuple[int, int]) -> bytes | None:
    for frame in frames:
        if (frame.bus, frame.device) != selected or frame.direction != "IN":
            continue
        parsed = parse_a0(frame)
        if parsed and parsed[0] == 0xA6 and len(parsed[1]) >= 64:
            return parsed[1][:64]
    return None


def sanitize_cache(file: InputFile, otp: bytes | None, source_path: str | None) -> dict:
    data = file.path.read_bytes()
    row = {
        "SOURCE_PATH": source_path or "LOCAL_RAW_COPY_PATH_REDACTED",
        "FILE_SIZE": len(data),
        "FILE_SHA256": file.sha256,
        "LAYOUT_13520_COMPATIBLE": len(data) == CACHE_SIZE,
        "OTP_PREFIX_MATCH_WITH_DEVICE": "unknown",
        "FDT12_HEX": None,
        "CRC_VALID": "unknown",
        "CRC_BYTE_ORDER": "unknown",
        "NAV_REGION_SHA256": None,
        "IMAGE_REGION_SHA256": None,
    }
    if len(data) != CACHE_SIZE:
        return row
    otp64, fdt12 = data[:64], data[64:76]
    nav, image, stored_crc = data[76:3276], data[3276:13516], data[13516:]
    calculated = crc32_mpeg2(data[:13516])
    valid_be = calculated == int.from_bytes(stored_crc, "big")
    valid_le = calculated == int.from_bytes(stored_crc, "little")
    row.update({
        "OTP_PREFIX_MATCH_WITH_DEVICE": "unknown" if otp is None else otp64 == otp,
        "FDT12_HEX": fdt12.hex(),
        "CRC_VALID": valid_be or valid_le,
        "CRC_BYTE_ORDER": "big" if valid_be else "little" if valid_le else "none",
        "NAV_REGION_SHA256": sha256_bytes(nav),
        "IMAGE_REGION_SHA256": sha256_bytes(image),
    })
    return row


def cache_source_paths(inputs: list[InputFile]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in inputs:
        if item.relative.endswith("_metadata.json"):
            try:
                rows = json.loads(item.path.read_text(encoding="utf-8-sig"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            for row in rows if isinstance(rows, list) else []:
                if isinstance(row, dict) and row.get("raw_copy") and row.get("full_path"):
                    mapping[str(row["raw_copy"]).replace("\\", "/")] = str(row["full_path"])
    return mapping


def frame_metadata(frame: Frame, cancel_start: float) -> dict:
    parsed = parse_a0(frame)
    return {
        "relative_ms": round((frame.timestamp - cancel_start) * 1000, 3),
        "direction": frame.direction,
        "outer": f"0x{frame.outer:02x}",
        "control": f"0x{parsed[0]:02x}" if parsed else None,
        "logical_length": len(frame.raw),
        "physical_length": frame.physical_length,
    }


def analyze(run_dir: Path, manifest_path: Path, manifest_hash: str, output_dir: Path,
            usb_device: str | None = None) -> dict:
    require(not output_dir.exists(), "output collision: sanitized output directory already exists")
    inputs = load_manifest(run_dir, manifest_path, manifest_hash)
    wire = [row for row in inputs if row.role == "wire"]
    marker_files = [row for row in inputs if row.role == "markers"]
    require(len(wire) == 1 and len(marker_files) == 1, "manifest must identify one wire and one marker input")
    packets = list(iter_usbpcap(wire[0].path))
    frames = split_frames(packets)
    selected, firmware, target_specific = select_device(frames, usb_device)
    target_frames = [row for row in frames if (row.bus, row.device) == selected]
    markers = load_markers(marker_files[0].path)

    cancel_begin = one_marker(markers, "CANCEL_NO_FINGER_BEGIN")
    cancel_end = one_marker(markers, "CANCEL_NO_FINGER_END")
    reentry_begin = one_marker(markers, "REENTRY_BEGIN")
    reentry_end = one_marker(markers, "REENTRY_END")
    arm_marker = one_marker(markers, "ARM_OBSERVED_NO_FINGER")
    require(arm_marker["timestamp"] < cancel_begin["timestamp"] < cancel_end["timestamp"],
            "cancel marker order invalid")
    require(cancel_end["timestamp"] <= reentry_begin["timestamp"] < reentry_end["timestamp"],
            "re-entry marker order invalid")

    decoded = [(frame, parse_a0(frame)) for frame in target_frames]
    arms_before_cancel = [(frame, parsed) for frame, parsed in decoded
                          if parsed and frame.direction == "OUT" and parsed[0] == 0x32
                          and frame.timestamp < cancel_begin["timestamp"]]
    require(arms_before_cancel, "cancel occurred before any observed 0x32 arm")
    last_arm = arms_before_cancel[-1]
    require(last_arm[0].timestamp <= arm_marker["timestamp"] < cancel_begin["timestamp"],
            "operator arm marker is not correlated after the last wire 0x32")
    cancel_events = [frame_metadata(frame, cancel_begin["timestamp"])
                     for frame in target_frames
                     if last_arm[0].timestamp <= frame.timestamp < reentry_begin["timestamp"]]
    cancel_out = [(frame, parsed) for frame, parsed in decoded
                  if parsed and frame.direction == "OUT"
                  and cancel_begin["timestamp"] <= frame.timestamp < reentry_begin["timestamp"]]
    reentry_out = [(frame, parsed) for frame, parsed in decoded
                   if parsed and frame.direction == "OUT"
                   and reentry_begin["timestamp"] <= frame.timestamp <= reentry_end["timestamp"]]

    oem_paths = [row.path for row in inputs if row.role == "oem_log"]
    oem_events, oem_fdt = parse_oem_logs(oem_paths)
    otp = device_otp(target_frames, selected)
    path_mapping = cache_source_paths(inputs)
    cache_rows = [sanitize_cache(row, otp, path_mapping.get(row.relative))
                  for row in inputs if row.role in {"cache_before", "cache_after"}]
    compatible = [row for row in cache_rows if row["LAYOUT_13520_COMPATIBLE"]]
    cache_fdts = [bytes.fromhex(row["FDT12_HEX"]) for row in compatible]

    fdt36 = []
    first_seed: bytes | None = None
    for frame, parsed in decoded:
        if not parsed or frame.direction != "OUT" or parsed[0] != 0x36:
            continue
        body = parsed[1]
        seed = body[2:14] if len(body) == 14 and body[:2] == b"\x09\x01" else None
        if first_seed is None and seed is not None:
            first_seed = seed
        logical = len(frame.raw)
        tail = frame.physical_payload[logical:frame.physical_length]
        nonzero = [(logical + index, value) for index, value in enumerate(tail) if value]
        fdt36.append({
            "logical_length": logical,
            "physical_length": frame.physical_length,
            "tail_nonzero_offsets": [offset for offset, _ in nonzero],
            "tail_nonzero_values_hex": bytes(value for _, value in nonzero).hex(),
            "zero_tail": not nonzero,
        })

    cache_match = ("unknown" if first_seed is None or not cache_fdts
                   else any(first_seed == candidate for candidate in cache_fdts))
    log_match = "unknown" if first_seed is None or oem_fdt is None else first_seed == oem_fdt
    if cache_match is True and log_match is True:
        seed_class = "CACHE_AND_LOG_WIRE_MATCH"
    elif cache_match is True:
        seed_class = "HOST_CACHE_WIRE_MATCH"
    elif log_match is True:
        seed_class = "HOST_LOG_WIRE_MATCH"
    elif cache_match is False or log_match is False:
        seed_class = "NO_MATCH"
    else:
        seed_class = "NOT_OBSERVABLE"

    cancel_controls = [f"0x{parsed[0]:02x}" for _, parsed in cancel_out]
    reentry_controls = [f"0x{parsed[0]:02x}" for _, parsed in reentry_out]
    unknown_controls = sorted({f"0x{parsed[0]:02x}" for _, parsed in decoded
                               if parsed and parsed[0] not in KNOWN_CONTROLS})
    tls_alert = any(frame.outer == 0xB0 and len(frame.raw) >= 9 and frame.raw[4] == 21
                    for frame in target_frames
                    if cancel_begin["timestamp"] <= frame.timestamp < reentry_begin["timestamp"])
    window_log_events = [row for row in oem_events if row["timestamp"] is not None
                         and cancel_begin["timestamp"] <= row["timestamp"] < reentry_begin["timestamp"]]
    labels = {row["event"] for row in window_log_events}
    usb_close = True if labels & {"D0_EXIT", "DEVICE_CLOSE"} else "unknown"
    device_reset = True if "DEVICE_RESET" in labels else "unknown"
    idle = "0x70" in cancel_controls
    rearm = "0x32" in cancel_controls or "0x32" in reentry_controls
    host_cancel = "HOST_CANCEL" in labels
    if not cancel_controls and usb_close is True:
        restore_model = "HOST_CANCEL_THEN_DEVICE_CLOSE"
    elif not cancel_controls:
        restore_model = "HOST_ONLY_CANCEL_OBSERVED_ARM_LIFETIME_UNRESOLVED"
    elif idle:
        restore_model = "EXPLICIT_IDLE_MODE_OBSERVED_SEMANTICS_BOUNDED"
    else:
        restore_model = "DEVICE_COMMAND_SEQUENCE_UNCLASSIFIED"
    device_cancel = False if not cancel_controls else "unknown"
    cancel_is_host_only = bool(host_cancel and not cancel_controls)
    arm_state = "REARMED" if rearm else "POSSIBLY_ARMED_UNRESOLVED"
    no_finger_ready = one_marker(markers, "REENTRY_READY_NO_FINGER", required=False) is not None
    finger_used = one_marker(markers, "REENTRY_FINGER_BEGIN", required=False) is not None
    reentry_window = [(frame, parsed) for frame, parsed in decoded if parsed
                      and reentry_begin["timestamp"] <= frame.timestamp <= reentry_end["timestamp"]]
    reentry_proven = False
    for position, (request, request_parsed) in enumerate(reentry_window):
        if request.direction != "OUT":
            continue
        later = reentry_window[position + 1:]
        if request_parsed[0] == 0xA8 and any(
            response.direction == "IN" and response_parsed[0] == 0xA8
            and EXPECTED_FIRMWARE.encode() in response_parsed[1]
            for response, response_parsed in later
        ):
            reentry_proven = True
            break
        if request_parsed[0] == 0x32 and any(
            response.direction == "IN" and response_parsed[0] == 0xB0
            and response_parsed[1] in (b"\x32\x01", b"\x32\x07")
            for response, response_parsed in later
        ):
            reentry_proven = True
            break
    reentry_class = ("REENTRY_WITHOUT_FINGER" if reentry_proven and no_finger_ready and not finger_used
                     else "REENTRY_PROVEN_ONLY_AFTER_FINGER" if reentry_proven and finger_used
                     else "REENTRY_NOT_PROVEN")

    result = {
        "schema": "D255_SANITIZED_WINDOWS_EVIDENCE_V1",
        "execution_mode": "OFFLINE_POSTPROCESS_ONLY",
        "input_hashes": {"manifest_sha256": manifest_hash.lower(), "wire_sha256": wire[0].sha256},
        "target": {
            "usb_bus": selected[0], "usb_device": selected[1],
            "CAPTURE_FIRMWARE": firmware,
            "D255_EVIDENCE_TARGET_SPECIFIC": target_specific,
        },
        "seed_correlation": {
            "FIRST_FDT36_SEED": first_seed.hex() if first_seed else None,
            "CACHE_FDT12_MATCH": cache_match,
            "OEM_LOG_FDT12_MATCH": log_match,
            "SEED_SOURCE_CLASS": seed_class,
            "CAUSALITY_PROVEN": False,
            "CAUSALITY_LIMIT": "Equality alone does not prove timing or dataflow causality.",
        },
        "cache_candidates": cache_rows,
        "oem_log_events": oem_events,
        "restore_cancel": {
            "CANCEL_NO_FINGER_DEVICE_COMMANDS": cancel_controls,
            "CANCEL_NO_FINGER_LAST_FDT_STATE": f"0x{last_arm[1][0]:02x}_ARMED",
            "USB_CLOSE_AFTER_CANCEL": usb_close,
            "TLS_CLOSE_AFTER_CANCEL": tls_alert,
            "DEVICE_RESET_AFTER_CANCEL": device_reset,
            "IDLE_COMMAND_AFTER_CANCEL": idle,
            "FDT_REARM_AFTER_CANCEL": rearm,
            "REENTRY_COMMAND_SEQUENCE": reentry_controls,
            "RESTORE_MODEL": restore_model,
            "DEVICE_SIDE_CANCEL_COMMAND": device_cancel,
            "CANCEL_IS_HOST_ONLY": cancel_is_host_only,
            "ARM_STATE_AFTER_CANCEL": arm_state,
            "DETERMINISTIC_REENTRY_PROVEN": reentry_proven,
            "REENTRY_PROOF_CLASS": reentry_class,
            "window_events": cancel_events,
        },
        "physical_fdt36_contract": {
            "FDT36_COUNT": len(fdt36),
            "FDT36_LOGICAL_LENGTHS": sorted({row["logical_length"] for row in fdt36}),
            "FDT36_PHYSICAL_LENGTHS": sorted({row["physical_length"] for row in fdt36}),
            "FDT36_TAIL_PROFILES": fdt36,
            "FDT36_ZERO_TAIL_OBSERVED": any(row["zero_tail"] for row in fdt36),
        },
        "unknown_controls": unknown_controls,
        "safety": {
            "raw_payload_exported": False,
            "raw_biometric_exported": False,
            "otp_raw_exported": False,
            "psk_or_secret_exported": False,
            "usb_open_count": 0,
            "command_send_count": 0,
        },
    }
    require(target_specific,
            f"CAPTURE_FIRMWARE={firmware}; D255_EVIDENCE_TARGET_SPECIFIC=false; "
            "target-specific evidence gate failed")
    output_dir.mkdir(parents=True)
    json_path = output_dir / "D255_sanitized_evidence.json"
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = [
        f"CAPTURE_FIRMWARE={firmware}",
        f"D255_EVIDENCE_TARGET_SPECIFIC={str(target_specific).lower()}",
        f"FIRST_FDT36_SEED={result['seed_correlation']['FIRST_FDT36_SEED']}",
        f"CACHE_FDT12_MATCH={str(cache_match).lower()}",
        f"OEM_LOG_FDT12_MATCH={str(log_match).lower()}",
        f"SEED_SOURCE_CLASS={seed_class}",
        f"RESTORE_MODEL={restore_model}",
        f"DETERMINISTIC_REENTRY_PROVEN={str(reentry_proven).lower()}",
        f"REENTRY_PROOF_CLASS={reentry_class}",
        f"FDT36_COUNT={len(fdt36)}",
    ]
    (output_dir / "D255_sanitized_summary.txt").write_text("\n".join(summary) + "\n", encoding="ascii")
    return result


def _block(block_type: int, body: bytes) -> bytes:
    padding = bytes((-len(body)) % 4)
    length = 12 + len(body) + len(padding)
    return struct.pack("<II", block_type, length) + body + padding + struct.pack("<I", length)


def _a0(control: int, body: bytes) -> bytes:
    inner_len = len(body) + 1
    checksum = (0xAA - ((control & 0xFE) + (inner_len & 0xFF) + (inner_len >> 8) + sum(body))) & 0xFF
    payload = bytes((control,)) + inner_len.to_bytes(2, "little") + body + bytes((checksum,))
    outer_tag = (0x100 - ((0xA0 + len(payload) + sum(payload)) & 0xFF)) & 0xFF
    return b"\xa0" + len(payload).to_bytes(2, "little") + bytes((outer_tag,)) + payload


def _usbpcap_packet(timestamp: float, packet_index: int, payload: bytes, direction: str,
                    bus: int = 1, device: int = 5, physical: int | None = None) -> bytes:
    endpoint = 0x81 if direction == "IN" else 0x01
    info = 1 if direction == "IN" else 0
    if physical and len(payload) < physical:
        payload = payload + bytes(physical - len(payload))
    header = struct.pack("<HQIH BHHBBI", 27, packet_index + 1, 0, 9, info,
                         bus, device, endpoint, 3, len(payload))
    raw = header + payload
    ticks = int(timestamp * 1_000_000)
    body = struct.pack("<IIIII", 0, ticks >> 32, ticks & 0xFFFFFFFF, len(raw), len(raw)) + raw
    return _block(EPB, body)


def create_synthetic_fixture(directory: Path, *, cache_size: int = CACHE_SIZE,
                             crc_valid: bool = True, seed_match: bool = True,
                             firmware: bool = True, cancel_marker: bool = True,
                             cancel_before_arm: bool = False, reentry: bool = True,
                             unknown_control: bool = False, secret_marker: str = "SYNTHETIC_SECRET_NEVER_EXPORT") -> tuple[Path, str]:
    require(not directory.exists(), "synthetic fixture output collision")
    raw = directory / "raw"
    (raw / "cache_before").mkdir(parents=True)
    (raw / "cache_after").mkdir(parents=True)
    (raw / "oem_logs").mkdir(parents=True)
    base = 1_800_000_000.0
    otp = bytes(range(64))
    seed = bytes.fromhex("adadbdbda3a3b1b1a6a6b2b2")
    cache_seed = seed if seed_match else bytes.fromhex("b3b3c3c3a8a8b5b5a8a8b7b7")
    nav = bytes((index * 7) & 0xFF for index in range(3200))
    image = (secret_marker.encode() + bytes(10240))[:10240]
    cache_body = otp + cache_seed + nav + image
    crc = crc32_mpeg2(cache_body).to_bytes(4, "big")
    if not crc_valid:
        crc = bytes(value ^ 0xFF for value in crc)
    cache = (cache_body + crc)[:cache_size]
    if len(cache) < cache_size:
        cache += bytes(cache_size - len(cache))
    cache_path = raw / "cache_after" / "candidate.bin"
    cache_path.write_bytes(cache)
    (raw / "cache_before" / "candidate.bin").write_bytes(cache)
    metadata = [{"full_path": r"C:\ProgramData\Goodix\goodix.dat", "raw_copy": "raw/cache_after/candidate.bin"}]
    (directory / "cache_after_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    stamp = lambda seconds: dt.datetime.fromtimestamp(base + seconds, dt.timezone.utc).isoformat()
    log_lines = [
        f"{stamp(1.3)} read 13520-13520 bytes from base file",
        f"{stamp(1.4)} check crc :Crchost:",
        f"{stamp(1.5)} get file otp::" + otp.hex(),
        f"{stamp(1.6)} base data sent::0x" + cache_seed.hex(),
        f"{stamp(2.0)} gf_update_all_base",
        f"{stamp(3.0)} base_is_valid:1",
        f"{stamp(4.2)} gfOnCancel " + secret_marker,
        f"{stamp(4.4)} DeviceD0Exit",
        f"{stamp(6.1)} DeviceD0Entry",
    ]
    log_path = raw / "oem_logs" / "oem_000.log"
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    packets: list[tuple[float, bytes, str, int | None]] = []
    packets.append((base + 1, _a0(0xA8, b""), "OUT", 64))
    fw_body = (EXPECTED_FIRMWARE.encode() + b"\0") if firmware else b"OTHER_APP_00000\0"
    packets.append((base + 1.1, _a0(0xA8, fw_body), "IN", None))
    packets.append((base + 1.2, _a0(0xA6, otp), "IN", None))
    packets.append((base + 2, _a0(0x36, b"\x09\x01" + seed), "OUT", 64))
    if not cancel_before_arm:
        packets.append((base + 3, _a0(0x32, b"\x08\x01" + seed + b"\x00\x00"), "OUT", 64))
    if unknown_control:
        packets.append((base + 4.3, _a0(0x66, b"\x00"), "OUT", 64))
    if reentry:
        packets.append((base + 6.2, _a0(0xA8, b""), "OUT", 64))
        packets.append((base + 6.3, _a0(0xA8, fw_body), "IN", None))
        packets.append((base + 6.4, _a0(0x32, b"\x08\x01" + seed + b"\x01\x00"), "OUT", 64))
        packets.append((base + 6.5, _a0(0xB0, b"\x32\x01"), "IN", None))
    pcap = _block(SHB, b"\x4d\x3c\x2b\x1a" + struct.pack("<HHq", 1, 0, -1))
    pcap += _block(IDB, struct.pack("<HHI", USBPCAP_LINKTYPE, 0, 65535))
    for index, (timestamp, payload, direction, physical) in enumerate(packets):
        pcap += _usbpcap_packet(timestamp, index, payload, direction, physical=physical)
    wire_path = raw / "wire.pcapng"
    wire_path.write_bytes(pcap)

    marker_rows = [
        (base + 0.5, "CAPTURE_STARTED"),
        (base + 2.8 if cancel_before_arm else base + 3.5, "ARM_OBSERVED_NO_FINGER"),
    ]
    if cancel_marker:
        marker_rows.extend([(base + 4, "CANCEL_NO_FINGER_BEGIN"), (base + 5, "CANCEL_NO_FINGER_END")])
    marker_rows.extend([(base + 6, "REENTRY_BEGIN"), (base + 6.6, "REENTRY_READY_NO_FINGER"),
                        (base + 7, "REENTRY_END")])
    marker_text = "timestamp_utc\tevent\tdetail\n" + "".join(
        f"{dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()}\t{name}\tsynthetic\n"
        for ts, name in sorted(marker_rows)
    )
    marker_path = directory / "operator_markers.tsv"
    marker_path.write_text(marker_text, encoding="utf-8")

    roles = {
        "raw/wire.pcapng": "wire", "operator_markers.tsv": "markers",
        "raw/oem_logs/oem_000.log": "oem_log",
        "raw/cache_before/candidate.bin": "cache_before",
        "raw/cache_after/candidate.bin": "cache_after",
        "cache_after_metadata.json": "metadata",
    }
    files = []
    for relative, role in roles.items():
        path = directory / relative
        files.append({"path": relative, "role": role, "size": path.stat().st_size,
                      "sha256": sha256_file(path)})
    manifest = {"schema": "D255_WINDOWS_EVIDENCE_INPUT_MANIFEST_V1", "files": files}
    manifest_path = directory / "input_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path, sha256_file(manifest_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--usb-device", help="explicit BUS:DEVICE fallback when A8 identity is absent")
    parser.add_argument("--create-synthetic-fixture", type=Path)
    args = parser.parse_args()
    if args.create_synthetic_fixture:
        manifest, digest = create_synthetic_fixture(args.create_synthetic_fixture.resolve())
        print(json.dumps({"fixture": str(args.create_synthetic_fixture.resolve()),
                          "manifest": str(manifest), "manifest_sha256": digest}, sort_keys=True))
        return 0
    require(args.run_dir and args.manifest and args.manifest_sha256 and args.output_dir,
            "--run-dir, --manifest, --manifest-sha256, and --output-dir are required")
    result = analyze(args.run_dir.resolve(), args.manifest.resolve(), args.manifest_sha256,
                     args.output_dir.resolve(), args.usb_device)
    print(json.dumps({"result": "PASS", "firmware": result["target"]["CAPTURE_FIRMWARE"],
                      "seed_source": result["seed_correlation"]["SEED_SOURCE_CLASS"],
                      "restore_model": result["restore_cancel"]["RESTORE_MODEL"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceError as exc:
        raise SystemExit(f"D255_FAIL_CLOSED: {exc}")
