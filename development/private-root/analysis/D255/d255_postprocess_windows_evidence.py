#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline-only D255 USBPcap/cache/log sanitizer and correlator.

Raw evidence remains in the private repository capture area.  This tool hash-gates every input
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
RECOVERY_RUN_NAME = "D255_20260822T205631772Z_85c8c41f"
TARGET_DEVICE_DESCRIPTOR_PREFIX = b"\x12\x01"
TARGET_VID_LE = bytes.fromhex("c627")
TARGET_PID_LE = bytes.fromhex("2551")
KNOWN_CONTROLS = {
    0x20, 0x22, 0x32, 0x34, 0x36, 0x70, 0x80, 0x82, 0x90,
    0xA2, 0xA6, 0xA8, 0xAE, 0xAF, 0xB0, 0xD1, 0xD2, 0xD4, 0xD5, 0xE4,
}
CACHE_SIZE = 64 + 12 + 3200 + 10240 + 4
OEM_TIME_WINDOW_MARGIN_SECONDS = 300.0


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
    require(document.get("schema") == "D255_WINDOWS_EVIDENCE_INPUT_MANIFEST_V3",
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


def target_descriptor_packets(packets: list[UsbPacket]) -> list[UsbPacket]:
    """Return exact 27c6:5125 USB device descriptors observed during enumeration."""
    return [packet for packet in packets
            if len(packet.payload) >= 12
            and packet.payload[:2] == TARGET_DEVICE_DESCRIPTOR_PREFIX
            and packet.payload[8:10] == TARGET_VID_LE
            and packet.payload[10:12] == TARGET_PID_LE]


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


def require_guest_topology(inputs: list[InputFile], role: str, expected_count: int) -> None:
    matches = [row for row in inputs if row.role == role]
    require(len(matches) == 1, f"manifest must identify one {role} snapshot")
    document = json.loads(matches[0].path.read_text(encoding="utf-8-sig"))
    require(document.get("schema") == "D255_GUEST_PNP_TOPOLOGY_V1",
            f"unexpected {role} schema")
    require(document.get("target_vid_pid") == "27c6:5125",
            f"unexpected {role} target")
    require(document.get("target_present_count") == expected_count,
            f"{role} target presence count is not {expected_count}")


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


@dataclass(frozen=True)
class ClockContext:
    year: int
    offset_minutes: int
    timezone_id: str
    start_utc: float
    end_utc: float
    stable_offset: bool


def _load_clock_document(path: Path, expected_phase: str) -> tuple[dict, float, dt.datetime]:
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    require(document.get("schema") == "D255_WINDOWS_RUN_CLOCK_V1",
            "unexpected run clock schema")
    require(document.get("phase") == expected_phase, "unexpected run clock phase")
    utc_value = dt.datetime.fromisoformat(str(document["utc_iso"]).replace("Z", "+00:00"))
    local_value = dt.datetime.fromisoformat(str(document["local_iso_with_offset"]))
    require(utc_value.tzinfo is not None and utc_value.utcoffset() == dt.timedelta(0),
            "run clock utc_iso must carry UTC offset")
    require(local_value.tzinfo is not None, "run clock local_iso_with_offset lacks offset")
    offset_minutes = int(document["utc_offset_minutes"])
    require(local_value.utcoffset() == dt.timedelta(minutes=offset_minutes),
            "run clock offset fields disagree")
    require(abs(local_value.timestamp() - utc_value.timestamp()) < 0.002,
            "run clock UTC and local values disagree")
    require((local_value.year, local_value.month, local_value.day) ==
            (int(document["year"]), int(document["month"]), int(document["day"])),
            "run clock local date fields disagree")
    require(bool(str(document.get("windows_timezone_id", "")).strip()),
            "run clock Windows timezone ID missing")
    return document, utc_value.timestamp(), local_value


def load_clock_context(inputs: list[InputFile], markers: list[dict],
                       recovery_mode: bool = False) -> ClockContext:
    starts = [row for row in inputs if row.role == "clock_anchor"]
    ends = [row for row in inputs if row.role == "clock_end"]
    require(len(starts) == 1, "manifest must identify one start clock anchor")
    require(len(ends) == 1 or (recovery_mode and not ends),
            "manifest must identify one end clock anchor outside offline recovery")
    start_doc, start_utc, start_local = _load_clock_document(starts[0].path, "BEFORE_CAPTURE")
    if ends:
        end_doc, end_utc, _ = _load_clock_document(ends[0].path, "AFTER_CAPTURE")
        same_zone = str(start_doc["windows_timezone_id"]) == str(end_doc["windows_timezone_id"])
        same_offset = int(start_doc["utc_offset_minutes"]) == int(end_doc["utc_offset_minutes"])
    else:
        end_utc = max(row["timestamp"] for row in markers)
        same_zone = same_offset = False
    require(start_utc <= end_utc, "run clock anchors are reversed")
    clock_marker = one_marker(markers, "CLOCK_ANCHOR")
    require(abs(clock_marker["timestamp"] - start_utc) <= 5.0,
            "CLOCK_ANCHOR marker does not match run_clock.json")
    return ClockContext(
        year=start_local.year,
        offset_minutes=int(start_doc["utc_offset_minutes"]),
        timezone_id=str(start_doc["windows_timezone_id"]),
        start_utc=start_utc,
        end_utc=end_utc,
        stable_offset=same_zone and same_offset,
    )


def _utc_iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _oem_timestamp(line: str, clock: ClockContext) -> tuple[float | None, str, str]:
    iso_match = re.search(
        r"\b(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))\b",
        line,
    )
    if iso_match:
        try:
            return parse_utc(iso_match.group(1)), "ISO8601", "EXACT_ANCHORED"
        except ValueError:
            return None, "NONE", "UNAVAILABLE"
    goodix = re.search(r"\[(\d{2})(\d{2})-(\d{2}):(\d{2}):(\d{2}):(\d{3})\]", line)
    if not goodix:
        return None, "NONE", "UNAVAILABLE"
    if not clock.stable_offset:
        return None, "GOODIX_MMDD_LOCAL", "AMBIGUOUS"
    month, day, hour, minute, second, millisecond = map(int, goodix.groups())
    timezone = dt.timezone(dt.timedelta(minutes=clock.offset_minutes))
    candidates: list[float] = []
    for year in (clock.year - 1, clock.year, clock.year + 1):
        try:
            local = dt.datetime(year, month, day, hour, minute, second,
                                millisecond * 1000, tzinfo=timezone)
        except ValueError:
            continue
        timestamp = local.timestamp()
        if (clock.start_utc - OEM_TIME_WINDOW_MARGIN_SECONDS <= timestamp <=
                clock.end_utc + OEM_TIME_WINDOW_MARGIN_SECONDS):
            candidates.append(timestamp)
    if len(candidates) != 1:
        return None, "GOODIX_MMDD_LOCAL", "AMBIGUOUS"
    return candidates[0], "GOODIX_MMDD_LOCAL", "EXACT_ANCHORED"


def _decode_oem_log(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace")
    if raw[:4096].count(0) > max(4, len(raw[:4096]) // 8):
        return raw.decode("utf-16le", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def oem_log_deltas(inputs: list[InputFile]) -> tuple[list[bytes], list[dict], bool]:
    before = {row.path.name: row for row in inputs if row.role == "oem_log_before"}
    after = {row.path.name: row for row in inputs if row.role == "oem_log_after"}
    if not before and not after:
        return [], [], False
    require(before, "manifest contains OEM log after snapshot without before snapshot")
    deltas: list[bytes] = []
    states: list[dict] = []
    safe = True
    for source_index, name in enumerate(sorted(set(before) | set(after))):
        old = before.get(name)
        new = after.get(name)
        old_raw = old.path.read_bytes() if old else None
        new_raw = new.path.read_bytes() if new else None
        if old_raw is None:
            status, delta = "MISSING_BEFORE", new_raw or b""
        elif new_raw is None:
            status, delta = "MISSING_AFTER", b""
        elif old_raw == new_raw:
            status, delta = "UNCHANGED", b""
        elif len(new_raw) >= len(old_raw) and new_raw.startswith(old_raw):
            status, delta = "GREW", new_raw[len(old_raw):]
        elif len(new_raw) < len(old_raw):
            status, delta = "TRUNCATED", new_raw
        else:
            status, delta = "REPLACED_OR_ROTATED", new_raw
        if status in {"MISSING_BEFORE", "MISSING_AFTER", "TRUNCATED", "REPLACED_OR_ROTATED"}:
            safe = False
        deltas.append(delta)
        states.append({
            "source_index": source_index,
            "change": status,
            "size_before": len(old_raw) if old_raw is not None else None,
            "sha256_before": old.sha256 if old else None,
            "size_after": len(new_raw) if new_raw is not None else None,
            "sha256_after": new.sha256 if new else None,
        })
    return deltas, states, safe


def parse_oem_logs(raw_logs: list[bytes], clock: ClockContext,
                   cancel_begin: float, reentry_begin: float,
                   reentry_end: float) -> tuple[list[dict], bytes | None]:
    events: list[dict] = []
    first_fdt: bytes | None = None
    for file_index, raw in enumerate(raw_logs):
        text = _decode_oem_log(raw)
        for line_number, line in enumerate(text.splitlines(), 1):
            if first_fdt is None:
                match = re.search(r"base\s+data\s+sent::0x([0-9a-fA-F]{24})(?![0-9a-fA-F])", line)
                if match:
                    first_fdt = bytes.fromhex(match.group(1))
            for label, pattern in OEM_EVENT_PATTERNS:
                if pattern.search(line):
                    timestamp, source, quality = _oem_timestamp(line, clock)
                    window = ("CANCEL" if timestamp is not None and cancel_begin <= timestamp < reentry_begin
                              else "REENTRY" if timestamp is not None and reentry_begin <= timestamp <= reentry_end
                              else "OUTSIDE" if timestamp is not None else "UNCORRELATED")
                    events.append({"source_index": file_index, "line": line_number,
                                   "event": label, "timestamp_source": source,
                                   "timestamp_utc": _utc_iso(timestamp),
                                   "time_correlation_quality": quality,
                                   "time_window": window,
                                   "_timestamp": timestamp})
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
    manifest_document = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    recovery = manifest_document.get("recovery", {})
    recovery_mode = recovery.get("offline_recovery") is True
    if recovery_mode:
        require(run_dir.name == RECOVERY_RUN_NAME,
                "offline recovery exception is restricted to the known D255 run")
        require(manifest_path.name == "recovery_manifest.json"
                and manifest_document.get("created_by") == "D255_OFFLINE_RECOVERY_V1",
                "invalid recovery manifest provenance")
        artifact_status = recovery.get("artifact_status", {})
        for missing in ("run_clock_end.json", "guest_topology_after_capture.json",
                        "cache_after_metadata.json", "oem_logs_after_metadata.json",
                        "input_manifest.json", "input_manifest.json.sha256"):
            require(artifact_status.get(missing) == "NOT_RECOVERABLE",
                    f"recovery manifest does not classify {missing} as NOT_RECOVERABLE")
    wire = [row for row in inputs if row.role == "wire"]
    marker_files = [row for row in inputs if row.role == "markers"]
    require(len(wire) == 1 and len(marker_files) == 1, "manifest must identify one wire and one marker input")
    packets = list(iter_usbpcap(wire[0].path))
    markers = load_markers(marker_files[0].path)
    clock = load_clock_context(inputs, markers, recovery_mode)
    require_guest_topology(inputs, "guest_topology_before", 0)
    require_guest_topology(inputs, "guest_topology_after_attach", 1)
    after_capture_topology = [row for row in inputs if row.role == "guest_topology_after_capture"]
    if after_capture_topology:
        require_guest_topology(inputs, "guest_topology_after_capture", 1)
    else:
        require(recovery_mode,
                "manifest must identify one guest_topology_after_capture snapshot")

    vm_guest_ready = one_marker(markers, "VM_GUEST_READY")
    topology_before = one_marker(markers, "GUEST_TOPOLOGY_BEFORE")
    account_checked = one_marker(markers, "ACCOUNT_PREREQUISITES_CHECKED")
    capture_started = one_marker(markers, "CAPTURE_STARTED")
    attach_begin = one_marker(markers, "VM_USB_ATTACH_BEGIN")
    attach_end = one_marker(markers, "VM_USB_ATTACH_END")
    guest_present = one_marker(markers, "GUEST_27C6_5125_PRESENT")
    passive_settled = one_marker(markers, "PASSIVE_BOOTSTRAP_SETTLED")
    ui_check_begin = one_marker(markers, "HELLO_SETUP_UI_CHECK_BEGIN")
    operator_phases_complete = one_marker(markers, "OPERATOR_PHASES_COMPLETE")
    terminal_names = {
        "HELLO_SETUP_UI_READY": "READY_WAITING_FOR_FINGER",
        "HELLO_SETUP_UI_UNAVAILABLE": "UI_UNAVAILABLE",
        "HELLO_SETUP_NEW_PIN_REQUIRED": "NEW_PIN_REQUIRED",
        "HELLO_SETUP_UNEXPECTED_PREREQUISITE": "UNEXPECTED_PREREQUISITE",
    }
    terminal_markers = [(name, one_marker(markers, name, required=False))
                        for name in terminal_names]
    terminal_markers = [(name, marker) for name, marker in terminal_markers if marker]
    require(len(terminal_markers) == 1,
            "exactly one structured post-attach Hello UI result marker is required")
    ui_terminal_name, ui_terminal = terminal_markers[0]
    ui_result = terminal_names[ui_terminal_name]
    full_run = ui_terminal_name == "HELLO_SETUP_UI_READY"
    run_result = ("FULL_ZERO_FINGER_CANCEL_REENTRY" if full_run
                  else "PARTIAL_BOOTSTRAP_ONLY_UI_UNAVAILABLE")
    require(vm_guest_ready["timestamp"] <= topology_before["timestamp"]
            <= account_checked["timestamp"] < capture_started["timestamp"],
            "VM guest/topology/account/capture marker order invalid")
    require(capture_started["timestamp"] < attach_begin["timestamp"] < attach_end["timestamp"]
            <= guest_present["timestamp"] < passive_settled["timestamp"]
            < ui_check_begin["timestamp"] <= ui_terminal["timestamp"],
            "CAPTURE_STARTED -> VM_USB_ATTACH -> bootstrap -> Hello UI marker order invalid")
    require(not any("DETACH" in row["event"] for row in markers),
            "D255_EVIDENCE_VALIDITY=INVALID_VM_USB_TOPOLOGY_CHANGE")

    descriptors = target_descriptor_packets(packets)
    require(descriptors, "target 27c6:5125 enumeration/attach is absent from the capture")
    descriptor_devices = {(packet.bus, packet.device) for packet in descriptors}
    require(len(descriptor_devices) == 1,
            "D255_EVIDENCE_VALIDITY=INVALID_VM_USB_TOPOLOGY_CHANGE")
    descriptor_episodes = 1
    for previous, current in zip(descriptors, descriptors[1:]):
        if current.timestamp - previous.timestamp > 2.0:
            descriptor_episodes += 1
    require(descriptor_episodes == 1,
            "D255_EVIDENCE_VALIDITY=INVALID_VM_USB_TOPOLOGY_CHANGE")
    descriptor = descriptors[0]
    require(descriptor.timestamp >= capture_started["timestamp"],
            "D255_BOOTSTRAP_EVIDENCE_VALIDITY=INVALID_DEVICE_ALREADY_ATTACHED")
    require(attach_begin["timestamp"] <= descriptor.timestamp <= attach_end["timestamp"],
            "target enumeration is not bounded by the single VM USB attach markers")

    frames = split_frames(packets)
    selected, firmware, target_specific = select_device(frames, usb_device)
    require(selected in descriptor_devices,
            "A8 device identity does not match the enumerated 27c6:5125 device")
    target_frames = [row for row in frames if (row.bus, row.device) == selected]
    a8_proofs = [frame for frame in target_frames
                 if frame.direction == "IN" and (parsed := parse_a0(frame))
                 and parsed[0] == 0xA8 and EXPECTED_FIRMWARE.encode() in parsed[1]]
    require(a8_proofs, "A8 APP12509 proof is absent")
    require(descriptor.timestamp <= a8_proofs[0].timestamp <= attach_end["timestamp"]
            < passive_settled["timestamp"],
            "descriptor -> A8_APP12509_PROVEN within VM_USB_ATTACH -> PASSIVE_BOOTSTRAP ordering invalid")

    full_phase_names = (
        "OEM_SESSION_BEGIN", "OEM_WAITING_NO_FINGER", "CANCEL_NO_FINGER_BEGIN",
        "CANCEL_NO_FINGER_END", "REENTRY_BEGIN", "REENTRY_WAITING_NO_FINGER",
        "REENTRY_CANCEL_BEGIN", "REENTRY_CANCEL_END", "REENTRY_END",
    )
    if full_run:
        oem_session_begin = one_marker(markers, "OEM_SESSION_BEGIN")
        arm_marker = one_marker(markers, "OEM_WAITING_NO_FINGER")
        cancel_begin = one_marker(markers, "CANCEL_NO_FINGER_BEGIN")
        cancel_end = one_marker(markers, "CANCEL_NO_FINGER_END")
        reentry_begin = one_marker(markers, "REENTRY_BEGIN")
        reentry_waiting = one_marker(markers, "REENTRY_WAITING_NO_FINGER")
        reentry_cancel_begin = one_marker(markers, "REENTRY_CANCEL_BEGIN")
        reentry_cancel_end = one_marker(markers, "REENTRY_CANCEL_END")
        reentry_end = one_marker(markers, "REENTRY_END")
        require(ui_terminal["timestamp"] <= oem_session_begin["timestamp"]
                < arm_marker["timestamp"], "Hello UI/OEM waiting marker order invalid")
        require(arm_marker["timestamp"] < cancel_begin["timestamp"] < cancel_end["timestamp"],
                "cancel marker order invalid")
        marker_key = lambda row: (row["timestamp"], row["line"])
        require(marker_key(cancel_end) < marker_key(reentry_begin)
                < marker_key(reentry_waiting) < marker_key(reentry_cancel_begin)
                < marker_key(reentry_cancel_end) < marker_key(reentry_end),
                "re-entry marker order invalid")
        require(marker_key(reentry_end) < marker_key(operator_phases_complete),
                "operator completion marker precedes re-entry end")
    else:
        require(not any(one_marker(markers, name, required=False) for name in full_phase_names),
                "partial-bootstrap run contains forbidden cancel/re-entry markers")
        oem_session_begin = arm_marker = cancel_begin = cancel_end = None
        reentry_begin = reentry_waiting = reentry_cancel_begin = None
        reentry_cancel_end = reentry_end = None

    decoded = [(frame, parse_a0(frame)) for frame in target_frames]
    if full_run:
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
    else:
        last_arm = None
        cancel_events = []
        cancel_out = []
        reentry_out = []

    oem_deltas, oem_log_states, oem_log_window_reconstructible = oem_log_deltas(inputs)
    if full_run:
        oem_events, oem_fdt = parse_oem_logs(
            oem_deltas, clock, cancel_begin["timestamp"], reentry_begin["timestamp"],
            reentry_end["timestamp"])
    else:
        terminal_time = ui_terminal["timestamp"]
        oem_events, oem_fdt = parse_oem_logs(
            oem_deltas, clock, terminal_time, terminal_time, terminal_time)
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
    tls_alert = bool(full_run and any(
        frame.outer == 0xB0 and len(frame.raw) >= 9 and frame.raw[4] == 21
        for frame in target_frames
        if cancel_begin["timestamp"] <= frame.timestamp < reentry_begin["timestamp"]))
    critical_labels = {"HOST_CANCEL", "D0_EXIT", "D0_ENTRY", "DEVICE_CLOSE",
                       "DEVICE_RESET", "SET_MODE"}
    critical_events = [row for row in oem_events if row["event"] in critical_labels]
    timestamped_count = sum(row["timestamp_utc"] is not None for row in oem_events)
    untimed_count = len(oem_events) - timestamped_count
    formats = sorted({row["timestamp_source"] for row in oem_events
                      if row["timestamp_source"] != "NONE"})
    oem_log_present = bool(oem_log_states)
    cache_source_count = sum(row.role == "cache_before" for row in inputs)
    cache_present = cache_source_count > 0
    if not oem_log_present:
        oem_time_correlation = "UNAVAILABLE_NO_OEM_LOG"
    elif not oem_log_window_reconstructible or not clock.stable_offset:
        oem_time_correlation = "AMBIGUOUS"
    elif any(row["time_correlation_quality"] == "AMBIGUOUS" for row in critical_events):
        oem_time_correlation = "AMBIGUOUS"
    elif any(row["time_correlation_quality"] == "UNAVAILABLE" for row in critical_events):
        oem_time_correlation = "UNAVAILABLE"
    elif critical_events:
        oem_time_correlation = "EXACT_ANCHORED"
    else:
        oem_time_correlation = "UNAVAILABLE"
    critical_time_unresolved = bool(
        not oem_log_present or
        (critical_events and oem_time_correlation != "EXACT_ANCHORED") or
        not oem_log_window_reconstructible or not clock.stable_offset)
    window_log_events = [row for row in oem_events if row["time_window"] == "CANCEL"]
    reentry_log_events = [row for row in oem_events if row["time_window"] == "REENTRY"]
    labels = {row["event"] for row in window_log_events}
    reentry_labels = {row["event"] for row in reentry_log_events}
    if critical_time_unresolved:
        oem_device_close = "unknown"
        oem_d0exit = "unknown"
        oem_d0entry = "unknown"
        device_reset = "unknown"
    else:
        oem_device_close = "DEVICE_CLOSE" in labels
        oem_d0exit = "D0_EXIT" in labels
        oem_d0entry = "D0_ENTRY" in reentry_labels
        device_reset = "DEVICE_RESET" in labels
    usb_close = ("unknown" if critical_time_unresolved
                 else bool(oem_device_close or oem_d0exit))
    idle = "0x70" in cancel_controls
    rearm = "0x32" in cancel_controls or "0x32" in reentry_controls
    host_cancel = bool(full_run and not critical_time_unresolved and "HOST_CANCEL" in labels)
    device_cancel = False
    cancel_is_host_only = ("unknown" if critical_time_unresolved
                           else bool(host_cancel and not cancel_controls))
    arm_state = "PRIOR_ARM_STATUS_UNKNOWN" if full_run else "NOT_EVALUATED_PARTIAL_RUN"
    operator_start = (arm_marker["timestamp"] if full_run else ui_check_begin["timestamp"])
    operator_end = (reentry_cancel_end["timestamp"] if full_run else ui_terminal["timestamp"])
    finger_irq_count = sum(
        packet.bus == selected[0] and packet.device == selected[1]
        and packet.endpoint == 0x82 and packet.payload[:2] == b"\x02\x00"
        and operator_start <= packet.timestamp <= operator_end
        for packet in packets)
    post_irq_cmd22_frames = [
        frame for frame, parsed in decoded
        if frame.direction == "OUT" and parsed and parsed[0] == 0x22
        and parsed[1] == b"\x01\x00" and operator_start <= frame.timestamp <= operator_end]
    post_irq_cmd22_count = len(post_irq_cmd22_frames)
    finger_image_path_count = sum(
        frame.direction == "IN" and frame.outer == 0xB0 and len(frame.raw) >= 1024
        and operator_start <= frame.timestamp <= operator_end
        and any(0 <= frame.timestamp - command.timestamp <= 2.0
                for command in post_irq_cmd22_frames)
        for frame in target_frames)
    finger_interaction_detected = bool(
        finger_irq_count or post_irq_cmd22_count or finger_image_path_count)
    reentry_window = ([(frame, parsed) for frame, parsed in decoded if parsed
                       and reentry_begin["timestamp"] <= frame.timestamp <= reentry_end["timestamp"]]
                      if full_run else [])
    reentry_proven = False
    new_fdt_arm_accepted = False
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
        if request_parsed[0] == 0x32 and any(
            response.direction == "IN" and response_parsed[0] == 0xB0
            and response_parsed[1] in (b"\x32\x01", b"\x32\x07")
            for response, response_parsed in later
        ):
            new_fdt_arm_accepted = True
            reentry_proven = True
    if not full_run:
        restore_evidence_class = "NO_RESTORE_EVIDENCE"
    elif critical_time_unresolved:
        restore_evidence_class = "INCONCLUSIVE_OEM_TIME_CORRELATION"
    elif device_cancel:
        restore_evidence_class = "EXPLICIT_DEVICE_CANCEL_COMMAND_OBSERVED"
    elif new_fdt_arm_accepted:
        restore_evidence_class = "REENTRY_ACCEPTS_NEW_ARM_PRIOR_ARM_STATUS_UNKNOWN"
    elif host_cancel and oem_d0exit and oem_d0entry:
        restore_evidence_class = "HOST_CANCEL_WITH_D0EXIT_REENTRY"
    elif host_cancel and oem_device_close:
        restore_evidence_class = "HOST_CANCEL_WITH_DEVICE_CLOSE"
    elif host_cancel:
        restore_evidence_class = "HOST_CANCEL_ONLY"
    else:
        restore_evidence_class = "NO_RESTORE_EVIDENCE"
    reentry_class = ("REENTRY_WITHOUT_FINGER" if reentry_proven and not finger_interaction_detected
                     else "REENTRY_INVALID_FINGER_INTERACTION" if finger_interaction_detected
                     else "REENTRY_NOT_PROVEN")
    device_fdt_disarm_proven = False
    prior_arm_lifetime = ("UNKNOWN_OR_NOT_DIRECTLY_OBSERVED" if full_run
                          else "NOT_EVALUATED_PARTIAL_RUN")
    restore_closed = False

    sanitized_oem_events = [{key: value for key, value in row.items() if key != "_timestamp"}
                            for row in oem_events]
    log_rotated_or_truncated = any(
        row["change"] in {"MISSING_BEFORE", "MISSING_AFTER", "TRUNCATED", "REPLACED_OR_ROTATED"}
        for row in oem_log_states)

    result = {
        "schema": "D255_SANITIZED_WINDOWS_EVIDENCE_V4",
        "execution_mode": "OFFLINE_POSTPROCESS_ONLY",
        "artifact_provenance": {
            "MANIFEST": "RECOVERED_ARTIFACT" if recovery_mode else "ORIGINAL_ARTIFACT",
            "WIRE_PCAP": "ORIGINAL_ARTIFACT",
            "OPERATOR_MARKERS": "ORIGINAL_ARTIFACT",
            "RUN_CLOCK_END": (
                "ORIGINAL_ARTIFACT" if any(row.role == "clock_end" for row in inputs)
                else "NOT_RECOVERABLE"),
            "GUEST_TOPOLOGY_AFTER_CAPTURE": (
                "ORIGINAL_ARTIFACT" if after_capture_topology else "NOT_RECOVERABLE"),
            "CACHE_AFTER": (
                "ORIGINAL_ARTIFACT" if any(row.role == "cache_after" for row in inputs)
                else "NOT_RECOVERABLE"),
            "OEM_LOG_AFTER": (
                "ORIGINAL_ARTIFACT" if any(row.role == "oem_log_after" for row in inputs)
                else "NOT_RECOVERABLE"),
            "POST_CAPTURE_STATE_SNAPSHOT": (
                "ORIGINAL_ARTIFACT" if not recovery_mode
                else "NOT_RECOVERABLE_RETROACTIVELY"),
        },
        "input_hashes": {"manifest_sha256": manifest_hash.lower(), "wire_sha256": wire[0].sha256},
        "run_classification": {
            "D255_RUN_RESULT": run_result,
            "POSTATTACH_HELLO_UI_RESULT": ui_result,
            "BOOTSTRAP_EVIDENCE_PRESERVED": True,
            "RESTORE_EVIDENCE_ACQUIRED": full_run,
            "RESTORE_CLOSED": False,
        },
        "target": {
            "usb_bus": selected[0], "usb_device": selected[1],
            "CAPTURE_FIRMWARE": firmware,
            "D255_EVIDENCE_TARGET_SPECIFIC": target_specific,
        },
        "vm_boundary": {
            "WINDOWS_EXECUTION_ENVIRONMENT": "VIRTUAL_MACHINE",
            "GOODIX_PRESENT_IN_GUEST_BEFORE_CAPTURE": False,
            "CAPTURE_STARTED_BEFORE_VM_USB_ATTACH": True,
            "VM_USB_ATTACH_COUNT": 1,
            "AUTOMATIC_DETACH_REATTACH_ALLOWED": False,
            "GUEST_GOODIX_27C6_5125_PRESENCE_PROOF": True,
            "TARGET_ENUMERATION_IN_CAPTURE": True,
            "A8_APP12509_PROVEN": target_specific,
            "derived_marker_order": [
                "CAPTURE_STARTED", "VM_USB_ATTACH_BEGIN", "TARGET_DESCRIPTOR_27C6_5125",
                "A8_APP12509_PROVEN", "VM_USB_ATTACH_END",
                "GUEST_27C6_5125_PRESENT",
                "PASSIVE_BOOTSTRAP_SETTLED", "HELLO_SETUP_UI_CHECK_BEGIN",
                ui_terminal_name,
            ],
            "D255_BOOTSTRAP_EVIDENCE_VALIDITY": "VALID_COLD_ATTACH",
            "D255_EVIDENCE_VALIDITY": (
                "INVALID_FINGER_INTERACTION" if finger_interaction_detected
                else run_result if not full_run else "VALID_ZERO_FINGER"),
        },
        "ui_gate": {
            "ACCOUNT_PREREQUISITES_CHECKED": True,
            "SENSOR_DEPENDENT_UI_AVAILABILITY_BEFORE_ATTACH": "UNKNOWN_BEFORE_ATTACH",
            "PREATTACH_FINGERPRINT_UI_REQUIRED": False,
            "HELLO_SETUP_UI_RESULT": ui_result,
            "TERMINAL_MARKER": ui_terminal_name,
        },
        "zero_finger": {
            "FINGER_DOWN_IRQ_COUNT_IN_OPERATOR_WINDOWS": finger_irq_count,
            "POST_IRQ2_0x22_COUNT_IN_OPERATOR_WINDOWS": post_irq_cmd22_count,
            "FINGER_IMAGE_PATH_COUNT_IN_OPERATOR_WINDOWS": finger_image_path_count,
            "FINGER_INTERACTION_DETECTED": finger_interaction_detected,
        },
        "seed_correlation": {
            "FIRST_FDT36_SEED": first_seed.hex() if first_seed else None,
            "CACHE_FDT12_MATCH": cache_match,
            "OEM_LOG_FDT12_MATCH": log_match,
            "SEED_SOURCE_CLASS": seed_class,
            "CAUSALITY_PROVEN": False,
            "CAUSALITY_LIMIT": "Equality alone does not prove timing or dataflow causality.",
        },
        "evidence_sources": {
            "OEM_LOG_STATUS": "PRESENT" if oem_log_present else "ABSENT",
            "OEM_LOG_SOURCE_COUNT": len(oem_log_states),
            "GOODIX_CACHE_STATUS": "PRESENT" if cache_present else "ABSENT",
            "GOODIX_CACHE_SOURCE_COUNT": cache_source_count,
        },
        "cache_candidates": cache_rows,
        "oem_log_events": sanitized_oem_events,
        "oem_log_state": {
            "sources": oem_log_states,
            "LOG_ROTATED_OR_TRUNCATED": log_rotated_or_truncated,
            "LOG_UNCHANGED": bool(oem_log_states and all(
                row["change"] == "UNCHANGED" for row in oem_log_states)),
            "LOG_GREW": any(row["change"] == "GREW" for row in oem_log_states),
            "WINDOW_RECONSTRUCTIBLE": oem_log_window_reconstructible,
        },
        "oem_log_time": {
            "OEM_LOG_TIMESTAMP_FORMATS": formats,
            "OEM_LOG_TIMESTAMPED_EVENT_COUNT": timestamped_count,
            "OEM_LOG_UNTIMED_EVENT_COUNT": untimed_count,
            "OEM_LOG_TIME_CORRELATION": oem_time_correlation,
            "CLOCK_ANCHOR_TIMEZONE_ID": clock.timezone_id,
            "CLOCK_ANCHOR_OFFSET_MINUTES": clock.offset_minutes,
            "CLOCK_OFFSET_STABLE": clock.stable_offset,
        },
        "restore_cancel": {
            "CANCEL_NO_FINGER_DEVICE_COMMANDS": cancel_controls,
            "CANCEL_NO_FINGER_LAST_FDT_STATE": (
                f"0x{last_arm[1][0]:02x}_ARMED" if last_arm else "NOT_EVALUATED_PARTIAL_RUN"),
            "USB_CLOSE_AFTER_CANCEL": usb_close,
            "TLS_CLOSE_AFTER_CANCEL": tls_alert,
            "DEVICE_RESET_AFTER_CANCEL": device_reset,
            "IDLE_COMMAND_AFTER_CANCEL": idle,
            "FDT_REARM_AFTER_CANCEL": rearm,
            "REENTRY_COMMAND_SEQUENCE": reentry_controls,
            "RESTORE_MODEL": restore_evidence_class,
            "RESTORE_CLOSED": restore_closed,
            "DEVICE_SIDE_CANCEL_COMMAND": device_cancel,
            "CANCEL_IS_HOST_ONLY": cancel_is_host_only,
            "ARM_STATE_AFTER_CANCEL": arm_state,
            "DETERMINISTIC_REENTRY_PROVEN": reentry_proven,
            "REENTRY_PROOF_CLASS": reentry_class,
            "HOST_CANCEL_EVENT_PROVEN": host_cancel,
            "CANCEL_WIRE_COMMAND_SEQUENCE": cancel_controls,
            "OEM_DEVICE_CLOSE_AFTER_CANCEL": oem_device_close,
            "OEM_D0EXIT_AFTER_CANCEL": oem_d0exit,
            "OEM_D0ENTRY_ON_REENTRY": oem_d0entry,
            "OEM_CANCEL_REENTRY_PROVEN": reentry_proven,
            "NEW_FDT_ARM_ACCEPTED_ON_REENTRY": new_fdt_arm_accepted,
            "DEVICE_SIDE_CANCEL_COMMAND_PROVEN": device_cancel,
            "DEVICE_FDT_DISARM_PROVEN": device_fdt_disarm_proven,
            "PRIOR_ARM_LIFETIME_AFTER_CANCEL": prior_arm_lifetime,
            "RESTORE_EVIDENCE_CLASS": restore_evidence_class,
            "RESTORE_EVIDENCE_ACQUIRED": full_run,
            "RESTORE_CLOSURE_DECISION": "AI_PM_REVIEW_REQUIRED",
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
            "real_capture_count": 0,
            "real_hardware_action_count": 0,
            "raw_pcap_modified": False,
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
        f"MANIFEST_ARTIFACT_CLASS={result['artifact_provenance']['MANIFEST']}",
        f"POST_CAPTURE_STATE_SNAPSHOT={result['artifact_provenance']['POST_CAPTURE_STATE_SNAPSHOT']}",
        "D255_BOOTSTRAP_EVIDENCE_VALIDITY=VALID_COLD_ATTACH",
        f"D255_RUN_RESULT={run_result}",
        "BOOTSTRAP_EVIDENCE_PRESERVED=true",
        f"RESTORE_EVIDENCE_ACQUIRED={str(full_run).lower()}",
        f"D255_EVIDENCE_VALIDITY={'INVALID_FINGER_INTERACTION' if finger_interaction_detected else run_result if not full_run else 'VALID_ZERO_FINGER'}",
        f"FINGER_DOWN_IRQ_COUNT_IN_OPERATOR_WINDOWS={finger_irq_count}",
        f"POST_IRQ2_0x22_COUNT_IN_OPERATOR_WINDOWS={post_irq_cmd22_count}",
        f"FINGER_IMAGE_PATH_COUNT_IN_OPERATOR_WINDOWS={finger_image_path_count}",
        f"FINGER_INTERACTION_DETECTED={str(finger_interaction_detected).lower()}",
        f"FIRST_FDT36_SEED={result['seed_correlation']['FIRST_FDT36_SEED']}",
        f"CACHE_FDT12_MATCH={str(cache_match).lower()}",
        f"OEM_LOG_FDT12_MATCH={str(log_match).lower()}",
        f"SEED_SOURCE_CLASS={seed_class}",
        f"OEM_LOG_STATUS={'PRESENT' if oem_log_present else 'ABSENT'}",
        f"OEM_LOG_SOURCE_COUNT={len(oem_log_states)}",
        f"GOODIX_CACHE_STATUS={'PRESENT' if cache_present else 'ABSENT'}",
        f"GOODIX_CACHE_SOURCE_COUNT={cache_source_count}",
        f"OEM_LOG_TIMESTAMP_FORMATS={','.join(formats) if formats else 'NONE'}",
        f"OEM_LOG_TIMESTAMPED_EVENT_COUNT={timestamped_count}",
        f"OEM_LOG_UNTIMED_EVENT_COUNT={untimed_count}",
        f"OEM_LOG_TIME_CORRELATION={oem_time_correlation}",
        f"LOG_ROTATED_OR_TRUNCATED={str(log_rotated_or_truncated).lower()}",
        f"LOG_UNCHANGED={str(result['oem_log_state']['LOG_UNCHANGED']).lower()}",
        f"LOG_GREW={str(result['oem_log_state']['LOG_GREW']).lower()}",
        f"RESTORE_MODEL={restore_evidence_class}",
        f"RESTORE_EVIDENCE_CLASS={restore_evidence_class}",
        f"RESTORE_CLOSED={str(restore_closed).lower()}",
        "RESTORE_CLOSURE_DECISION=AI_PM_REVIEW_REQUIRED",
        f"OEM_CANCEL_REENTRY_PROVEN={str(reentry_proven).lower()}",
        f"NEW_FDT_ARM_ACCEPTED_ON_REENTRY={str(new_fdt_arm_accepted).lower()}",
        f"DEVICE_FDT_DISARM_PROVEN={str(device_fdt_disarm_proven).lower()}",
        f"PRIOR_ARM_LIFETIME_AFTER_CANCEL={prior_arm_lifetime}",
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


def _b0(payload: bytes) -> bytes:
    tag = (0x100 - ((0xB0 + len(payload) + sum(payload)) & 0xFF)) & 0xFF
    return b"\xb0" + len(payload).to_bytes(2, "little") + bytes((tag,)) + payload


def _usbpcap_packet(timestamp: float, packet_index: int, payload: bytes, direction: str,
                    bus: int = 1, device: int = 5, physical: int | None = None,
                    endpoint: int | None = None, transfer: int = 3) -> bytes:
    endpoint = endpoint if endpoint is not None else (0x81 if direction == "IN" else 0x01)
    info = 1 if direction == "IN" else 0
    if physical and len(payload) < physical:
        payload = payload + bytes(physical - len(payload))
    header = struct.pack("<HQIH BHHBBI", 27, packet_index + 1, 0, 9, info,
                         bus, device, endpoint, transfer, len(payload))
    raw = header + payload
    ticks = int(timestamp * 1_000_000)
    body = struct.pack("<IIIII", 0, ticks >> 32, ticks & 0xFFFFFFFF, len(raw), len(raw)) + raw
    return _block(EPB, body)


def create_synthetic_fixture(directory: Path, *, cache_size: int = CACHE_SIZE,
                             crc_valid: bool = True, seed_match: bool = True,
                             firmware: bool = True, cancel_marker: bool = True,
                             cancel_before_arm: bool = False, reentry: bool = True,
                             unknown_control: bool = False,
                             secret_marker: str = "SYNTHETIC_SECRET_NEVER_EXPORT",
                             oem_timestamp_format: str = "goodix",
                             log_change: str = "growth",
                             base_timestamp: float | None = None,
                             clock_offset_minutes: int = 120,
                             end_clock_offset_minutes: int | None = None,
                             goodix_month_day: tuple[int, int] | None = None,
                             attach_before_capture: bool = False,
                             second_attach: bool = False,
                             enumeration: bool = True,
                             finger_irq: bool = False,
                             cmd22: bool = False,
                             image_path: bool = False,
                             ui_result: str = "READY_WAITING_FOR_FINGER",
                             guest_before_count: int = 0,
                             guest_after_count: int = 1,
                             include_oem_log: bool = True,
                             include_cache: bool = True) -> tuple[Path, str]:
    require(not directory.exists(), "synthetic fixture output collision")
    raw = directory / "raw"
    (raw / "cache_before").mkdir(parents=True)
    (raw / "cache_after").mkdir(parents=True)
    (raw / "oem_logs_before").mkdir(parents=True)
    (raw / "oem_logs_after").mkdir(parents=True)
    require(oem_timestamp_format in {"goodix", "iso"}, "unsupported synthetic OEM timestamp format")
    require(log_change in {"growth", "unchanged", "truncate", "replace"},
            "unsupported synthetic log change")
    require(ui_result in {"READY_WAITING_FOR_FINGER", "UI_UNAVAILABLE",
                          "NEW_PIN_REQUIRED", "UNEXPECTED_PREREQUISITE"},
            "unsupported synthetic Hello UI result")
    full_run = ui_result == "READY_WAITING_FOR_FINGER"
    base = (base_timestamp if base_timestamp is not None else
            dt.datetime(2026, 8, 22, 6, 14, 6, tzinfo=dt.timezone.utc).timestamp())
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
    if include_cache:
        cache_path = raw / "cache_after" / "candidate.bin"
        cache_path.write_bytes(cache)
        (raw / "cache_before" / "candidate.bin").write_bytes(cache)
    metadata = ([{"full_path": r"C:\ProgramData\Goodix\goodix.dat",
                  "raw_copy": "raw/cache_after/candidate.bin"}] if include_cache else [])
    (directory / "cache_after_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    local_zone = dt.timezone(dt.timedelta(minutes=clock_offset_minutes))

    def stamp(seconds: float) -> str:
        value = dt.datetime.fromtimestamp(base + seconds, dt.timezone.utc)
        if oem_timestamp_format == "iso":
            return value.isoformat()
        local = value.astimezone(local_zone)
        month, day = goodix_month_day or (local.month, local.day)
        return (f"[{month:02d}{day:02d}-{local.hour:02d}:{local.minute:02d}:"
                f"{local.second:02d}:{local.microsecond // 1000:03d}]")

    log_lines = [
        f"{stamp(1.3)} read 13520-13520 bytes from base file",
        f"{stamp(1.4)} check crc :Crchost:",
        f"{stamp(1.5)} get file otp::" + otp.hex(),
        f"{stamp(1.6)} base data sent::0x" + cache_seed.hex(),
        f"{stamp(2.0)} gf_update_all_base",
        f"{stamp(3.0)} base_is_valid:1",
    ]
    if full_run:
        log_lines.extend([
            f"{stamp(4.1)} gfOnCancel " + secret_marker,
            f"{stamp(4.13)} DeviceD0Exit",
            f"{stamp(4.9)} DeviceD0Entry",
        ])
    before_log = b"D255 synthetic pre-existing log prefix\n"
    appended_log = ("\n".join(log_lines) + "\n").encode()
    if log_change == "growth":
        after_log = before_log + appended_log
    elif log_change == "unchanged":
        after_log = before_log
    elif log_change == "truncate":
        after_log = b"short\n"
    else:
        after_log = b"D255 replacement log header\n" + appended_log
    if include_oem_log:
        before_log_path = raw / "oem_logs_before" / "oem_000.log"
        after_log_path = raw / "oem_logs_after" / "oem_000.log"
        before_log_path.write_bytes(before_log)
        after_log_path.write_bytes(after_log)

    def clock_document(timestamp: float, offset_minutes: int, phase: str) -> dict:
        utc_value = dt.datetime.fromtimestamp(timestamp, dt.timezone.utc)
        zone = dt.timezone(dt.timedelta(minutes=offset_minutes))
        local_value = utc_value.astimezone(zone)
        return {
            "schema": "D255_WINDOWS_RUN_CLOCK_V1",
            "phase": phase,
            "utc_iso": utc_value.isoformat(),
            "local_iso_with_offset": local_value.isoformat(),
            "utc_offset_minutes": offset_minutes,
            "windows_timezone_id": "W. Europe Standard Time",
            "year": local_value.year,
            "month": local_value.month,
            "day": local_value.day,
            "tick_source": "SYNTHETIC",
            "environment_tick_count": 123456,
        }

    start_clock_timestamp = base + 0.1
    end_offset = (clock_offset_minutes if end_clock_offset_minutes is None
                  else end_clock_offset_minutes)
    (directory / "run_clock.json").write_text(
        json.dumps(clock_document(start_clock_timestamp, clock_offset_minutes,
                                  "BEFORE_CAPTURE"), indent=2) + "\n", encoding="utf-8")
    (directory / "run_clock_end.json").write_text(
        json.dumps(clock_document(base + 8.0, end_offset, "AFTER_CAPTURE"), indent=2) + "\n",
        encoding="utf-8")

    def topology_document(stage: str, count: int) -> dict:
        return {
            "schema": "D255_GUEST_PNP_TOPOLOGY_V1",
            "stage": stage,
            "timestamp_utc": dt.datetime.fromtimestamp(base, dt.timezone.utc).isoformat(),
            "target_vid_pid": "27c6:5125",
            "target_present_count": count,
            "devices": [],
        }

    for filename, stage, count in (
        ("guest_topology_before_attach.json", "before_attach", guest_before_count),
        ("guest_topology_after_attach.json", "after_attach", guest_after_count),
        ("guest_topology_after_capture.json", "after_capture", guest_after_count),
    ):
        (directory / filename).write_text(
            json.dumps(topology_document(stage, count), indent=2) + "\n", encoding="utf-8")

    packets: list[tuple[float, bytes, str, int | None]] = []
    packets.append((base + 1, _a0(0xA8, b""), "OUT", 64))
    fw_body = (EXPECTED_FIRMWARE.encode() + b"\0") if firmware else b"OTHER_APP_00000\0"
    packets.append((base + 1.1, _a0(0xA8, fw_body), "IN", None))
    packets.append((base + 1.2, _a0(0xA6, otp), "IN", None))
    packets.append((base + 2, _a0(0x36, b"\x09\x01" + seed), "OUT", 64))
    if full_run and not cancel_before_arm:
        packets.append((base + 3, _a0(0x32, b"\x08\x01" + seed + b"\x00\x00"), "OUT", 64))
    if unknown_control:
        packets.append((base + 4.3, _a0(0x66, b"\x00"), "OUT", 64))
    if cmd22 or image_path:
        packets.append((base + 3.9, _a0(0x22, b"\x01\x00"), "OUT", 64))
    if image_path:
        packets.append((base + 3.95, _b0(bytes(1500)), "IN", None))
    if full_run and reentry:
        packets.append((base + 4.9, _a0(0xA8, b""), "OUT", 64))
        packets.append((base + 5.0, _a0(0xA8, fw_body), "IN", None))
        packets.append((base + 5.1, _a0(0x32, b"\x08\x01" + seed + b"\x01\x00"), "OUT", 64))
        packets.append((base + 5.2, _a0(0xB0, b"\x32\x01"), "IN", None))
    pcap = _block(SHB, b"\x4d\x3c\x2b\x1a" + struct.pack("<HHq", 1, 0, -1))
    pcap += _block(IDB, struct.pack("<HHI", USBPCAP_LINKTYPE, 0, 65535))
    packet_rows: list[tuple[float, bytes, str, int | None, int, int, int | None, int]] = []
    if enumeration:
        descriptor = (b"\x12\x01\x00\x02\x00\x00\x00\x40" + TARGET_VID_LE + TARGET_PID_LE
                      + b"\x00\x01\x01\x02\x03\x01")
        descriptor_time = base + (0.2 if attach_before_capture else 0.75)
        packet_rows.append((descriptor_time, descriptor, "IN", None, 1, 5, 0x80, 2))
        if second_attach:
            packet_rows.append((base + 3.0, descriptor, "IN", None, 1, 5, 0x80, 2))
    if finger_irq:
        packet_rows.append((base + 3.8, b"\x02\x00", "IN", None, 1, 5, 0x82, 1))
    packet_rows.extend((timestamp, payload, direction, physical, 1, 5, None, 3)
                       for timestamp, payload, direction, physical in packets)
    for index, row in enumerate(sorted(packet_rows, key=lambda item: item[0])):
        timestamp, payload, direction, physical, bus, device, endpoint, transfer = row
        pcap += _usbpcap_packet(timestamp, index, payload, direction, bus=bus, device=device,
                               physical=physical, endpoint=endpoint, transfer=transfer)
    wire_path = raw / "wire.pcapng"
    wire_path.write_bytes(pcap)

    marker_rows = [
        (start_clock_timestamp, "CLOCK_ANCHOR"),
        (base + 0.2, "VM_GUEST_READY"),
        (base + 0.3, "GUEST_TOPOLOGY_BEFORE"),
        (base + 0.4, "ACCOUNT_PREREQUISITES_CHECKED"),
        (base + 0.45, "CAPTURE_PROCESS_STARTED"),
        (base + 0.5, "CAPTURE_STARTED"),
        (base + 0.6, "VM_USB_ATTACH_BEGIN"),
        (base + 1.3, "VM_USB_ATTACH_END"),
        (base + 1.4, "GUEST_27C6_5125_PRESENT"),
        (base + 2.3, "CAPTURE_OUTPUT_MATERIALIZED"),
        (base + 2.4, "PASSIVE_BOOTSTRAP_SETTLED"),
        (base + 2.5, "HELLO_SETUP_UI_CHECK_BEGIN"),
    ]
    terminal_marker = {
        "READY_WAITING_FOR_FINGER": "HELLO_SETUP_UI_READY",
        "UI_UNAVAILABLE": "HELLO_SETUP_UI_UNAVAILABLE",
        "NEW_PIN_REQUIRED": "HELLO_SETUP_NEW_PIN_REQUIRED",
        "UNEXPECTED_PREREQUISITE": "HELLO_SETUP_UNEXPECTED_PREREQUISITE",
    }[ui_result]
    marker_rows.append((base + 2.6, terminal_marker))
    if full_run:
        marker_rows.extend([(base + 2.7, "OEM_SESSION_BEGIN"),
                            (base + 2.8 if cancel_before_arm else base + 3.5,
                             "OEM_WAITING_NO_FINGER")])
        if cancel_marker:
            marker_rows.extend([(base + 4, "CANCEL_NO_FINGER_BEGIN"),
                                (base + 4.5, "CANCEL_NO_FINGER_END")])
        marker_rows.extend([(base + 4.8, "REENTRY_BEGIN"),
                            (base + 5.3, "REENTRY_WAITING_NO_FINGER"),
                            (base + 5.35, "REENTRY_CANCEL_BEGIN"),
                            (base + 5.4, "REENTRY_CANCEL_END"),
                            (base + 5.5, "REENTRY_END")])
    marker_rows.append((base + 5.6 if full_run else base + 2.7,
                        "OPERATOR_PHASES_COMPLETE"))
    marker_text = "timestamp_utc\tevent\tdetail\n" + "".join(
        f"{dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()}\t{name}\tsynthetic\n"
        for ts, name in sorted(marker_rows)
    )
    marker_path = directory / "operator_markers.tsv"
    marker_path.write_text(marker_text, encoding="utf-8")

    roles = {
        "raw/wire.pcapng": "wire", "operator_markers.tsv": "markers",
        "run_clock.json": "clock_anchor", "run_clock_end.json": "clock_end",
        "guest_topology_before_attach.json": "guest_topology_before",
        "guest_topology_after_attach.json": "guest_topology_after_attach",
        "guest_topology_after_capture.json": "guest_topology_after_capture",
        "cache_after_metadata.json": "metadata",
    }
    if include_oem_log:
        roles.update({
            "raw/oem_logs_before/oem_000.log": "oem_log_before",
            "raw/oem_logs_after/oem_000.log": "oem_log_after",
        })
    if include_cache:
        roles.update({
            "raw/cache_before/candidate.bin": "cache_before",
            "raw/cache_after/candidate.bin": "cache_after",
        })
    files = []
    for relative, role in roles.items():
        path = directory / relative
        files.append({"path": relative, "role": role, "size": path.stat().st_size,
                      "sha256": sha256_file(path)})
    manifest = {"schema": "D255_WINDOWS_EVIDENCE_INPUT_MANIFEST_V3", "files": files}
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
