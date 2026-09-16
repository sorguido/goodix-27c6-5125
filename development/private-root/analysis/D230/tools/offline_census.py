#!/usr/bin/env python3
"""Offline-only census helpers for the D230 static audit.

The program reads a USBPcap pcapng file and an existing objdump listing.  It
has no USB, network, subprocess, firmware-execution, or device-access code.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import struct
from collections import Counter, defaultdict
from pathlib import Path


EPB = 0x00000006
IDB = 0x00000001
SHB = 0x0A0D0D0A


def iter_pcapng_packets(path: Path):
    data = path.read_bytes()
    endian = "<"
    interfaces: list[dict[str, int]] = []
    off = 0
    packet_index = 0
    while off + 12 <= len(data):
        block_type = struct.unpack_from(endian + "I", data, off)[0]
        if block_type == SHB:
            bom = data[off + 8 : off + 12]
            if bom == b"\x4d\x3c\x2b\x1a":
                endian = "<"
            elif bom == b"\x1a\x2b\x3c\x4d":
                endian = ">"
            block_type = SHB
        block_len = struct.unpack_from(endian + "I", data, off + 4)[0]
        if block_len < 12 or off + block_len > len(data):
            raise ValueError(f"invalid pcapng block at {off:#x}")
        if struct.unpack_from(endian + "I", data, off + block_len - 4)[0] != block_len:
            raise ValueError(f"pcapng trailing length mismatch at {off:#x}")
        body = data[off + 8 : off + block_len - 4]
        if block_type == IDB:
            linktype, _reserved, snaplen = struct.unpack_from(endian + "HHI", body, 0)
            interfaces.append({"linktype": linktype, "snaplen": snaplen, "tsresol": 6})
        elif block_type == EPB:
            interface_id, ts_hi, ts_lo, captured_len, original_len = struct.unpack_from(
                endian + "IIIII", body, 0
            )
            raw = body[20 : 20 + captured_len]
            yield {
                "packet_index": packet_index,
                "interface_id": interface_id,
                "timestamp_ticks": (ts_hi << 32) | ts_lo,
                "captured_len": captured_len,
                "original_len": original_len,
                "raw": raw,
                "linktype": interfaces[interface_id]["linktype"],
            }
            packet_index += 1
        off += block_len


def decode_usbpcap(packet: dict) -> dict:
    raw = packet["raw"]
    if len(raw) < 27:
        return {**packet, "decode_error": "short USBPcap header"}
    header_len = struct.unpack_from("<H", raw, 0)[0]
    if header_len < 27 or header_len > len(raw):
        return {**packet, "decode_error": f"invalid USBPcap header length {header_len}"}
    irp_id = struct.unpack_from("<Q", raw, 2)[0]
    status = struct.unpack_from("<I", raw, 10)[0]
    function = struct.unpack_from("<H", raw, 14)[0]
    info = raw[16]
    bus = struct.unpack_from("<H", raw, 17)[0]
    device = struct.unpack_from("<H", raw, 19)[0]
    endpoint = raw[21]
    transfer = raw[22]
    data_len = struct.unpack_from("<I", raw, 23)[0]
    payload = raw[header_len : header_len + data_len]
    return {
        **packet,
        "header_len": header_len,
        "irp_id": f"0x{irp_id:016x}",
        "status": f"0x{status:08x}",
        "function": function,
        "info": info,
        "bus": bus,
        "device": device,
        "endpoint": endpoint,
        "transfer": transfer,
        "data_len": data_len,
        "payload": payload,
    }


def split_bulk_frames(packets: list[dict], endpoint: int, info: int) -> list[dict]:
    frames: list[dict] = []
    pending: dict | None = None
    for packet in packets:
        if packet.get("transfer") != 3 or packet.get("endpoint") != endpoint:
            continue
        if packet.get("info") != info or not packet.get("payload"):
            continue
        payload = packet["payload"]
        if pending is not None:
            pending["raw"].extend(payload)
            pending["packet_indices"].append(packet["packet_index"])
            if len(pending["raw"]) >= pending["expected_len"]:
                pending["raw"] = bytes(pending["raw"][: pending["expected_len"]])
                frames.append(pending)
                pending = None
            continue
        if payload[0] not in (0xA0, 0xB0) or len(payload) < 4:
            frames.append(
                {
                    "packet_indices": [packet["packet_index"]],
                    "first_packet_index": packet["packet_index"],
                    "outer_type": f"0x{payload[0]:02x}",
                    "expected_len": len(payload),
                    "raw": bytes(payload),
                    "unframed": True,
                }
            )
            continue
        expected = 4 + int.from_bytes(payload[1:3], "little")
        frame = {
            "packet_indices": [packet["packet_index"]],
            "first_packet_index": packet["packet_index"],
            "outer_type": f"0x{payload[0]:02x}",
            "expected_len": expected,
            "raw": bytearray(payload[:expected]),
            "unframed": False,
        }
        if len(frame["raw"]) >= expected:
            frame["raw"] = bytes(frame["raw"][:expected])
            frames.append(frame)
        else:
            pending = frame
    if pending is not None:
        pending["truncated"] = True
        pending["raw"] = bytes(pending["raw"])
        frames.append(pending)
    return frames


def describe_a0(frame: dict) -> dict:
    raw: bytes = frame["raw"]
    result = {k: v for k, v in frame.items() if k != "raw"}
    result["frame_length"] = len(raw)
    result["raw_sha256_omitted"] = True
    if len(raw) < 8 or raw[0] != 0xA0:
        return result
    control = raw[4]
    logical = control & 0xFE
    inner_len = int.from_bytes(raw[5:7], "little")
    inner = raw[7 : 7 + inner_len]
    result.update(
        {
            "wire_control": f"0x{control:02x}",
            "logical_control": f"0x{logical:02x}",
            "inner_length": inner_len,
            "payload_length": max(0, inner_len - 1),
            "payload_prefix_hex": inner[: min(len(inner), 16)].hex(),
            "payload_suffix_hex": inner[-min(len(inner), 8) :].hex() if inner else "",
        }
    )
    addresses = []
    for i in range(max(0, len(inner) - 3)):
        value = int.from_bytes(inner[i : i + 4], "little")
        if 0x08000000 <= value <= 0x080FFFFF:
            addresses.append({"offset": i, "value": f"0x{value:08x}"})
    result["candidate_flash_addresses"] = addresses
    return result


DISASM_RE = re.compile(r"^\s*([0-9a-f]+):\s+.*?\s{2,}(.+)$")


def pe_function_ranges(dll_path: Path) -> list[tuple[int, int]]:
    data = dll_path.read_bytes()
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    coff_off = pe_off + 4
    section_count = struct.unpack_from("<H", data, coff_off + 2)[0]
    optional_size = struct.unpack_from("<H", data, coff_off + 16)[0]
    optional_off = coff_off + 20
    image_base = struct.unpack_from("<Q", data, optional_off + 24)[0]
    exception_rva, exception_size = struct.unpack_from("<II", data, optional_off + 112 + 3 * 8)
    section_off = optional_off + optional_size
    sections = []
    for index in range(section_count):
        entry = section_off + index * 40
        name = data[entry : entry + 8].rstrip(b"\0").decode(errors="replace")
        virtual_size, virtual_address, raw_size, raw_off = struct.unpack_from("<IIII", data, entry + 8)
        sections.append((name, virtual_address, max(virtual_size, raw_size), raw_off))
    exception_off = None
    for _name, virtual_address, size, raw_off in sections:
        if virtual_address <= exception_rva < virtual_address + size:
            exception_off = raw_off + exception_rva - virtual_address
            break
    if exception_off is None:
        raise ValueError("PE exception directory not mapped")
    ranges = []
    for off in range(exception_off, exception_off + exception_size, 12):
        begin, end, _unwind = struct.unpack_from("<III", data, off)
        if begin and end > begin:
            ranges.append((image_base + begin, image_base + end))
    return sorted(ranges)


def load_utf16_string_map(path: Path) -> dict[int, str]:
    result: dict[int, str] = {}
    for line in path.read_text(errors="replace").splitlines():
        match = re.match(r"\s*([0-9a-f]+)\s+(.+)$", line)
        if match:
            file_off = int(match.group(1), 16)
            result[0x180001000 + file_off] = match.group(2)
    return result


def builder_callsites(disasm_path: Path, dll_path: Path, strings_path: Path) -> list[dict]:
    lines = disasm_path.read_text(errors="replace").splitlines()
    insns: list[tuple[int, str, int]] = []
    for line_no, line in enumerate(lines, 1):
        match = DISASM_RE.match(line)
        if match:
            insns.append((int(match.group(1), 16), match.group(2), line_no))
    ranges = pe_function_ranges(dll_path)
    string_map = load_utf16_string_map(strings_path)
    targets = {0x18005C148: "A0_generic", 0x18005CC04: "A0_no_ack", 0x18005C344: "B0_TLS"}
    callsites: list[dict] = []
    for index, (address, text, line_no) in enumerate(insns):
        matched = None
        for target, kind in targets.items():
            if re.search(rf"\bcall\s+0x{target:x}\b", text):
                matched = (target, kind)
                break
        if not matched:
            continue
        function_start, function_end = next(
            ((start, end) for start, end in ranges if start <= address < end), (address, address + 1)
        )
        function_insns = [item for item in insns if function_start <= item[0] < function_end]
        referenced_strings = []
        for _fn_address, fn_insn, _fn_line in function_insns:
            ref = re.search(r"#\s+(0x[0-9a-f]+)", fn_insn)
            if ref and int(ref.group(1), 16) in string_map:
                value = string_map[int(ref.group(1), 16)]
                if value not in referenced_strings:
                    referenced_strings.append(value)
        context = insns[max(0, index - 32) : index]
        constants: dict[str, str] = {}
        stack_args: dict[str, str] = {}
        for insn_address, insn, _ in context:
            mov = re.search(
                r"\bmov\s+(r9b|r8b|r9d|r8d|edx|ecx),0x([0-9a-f]+)\b", insn
            )
            if mov:
                constants[mov.group(1)] = f"0x{int(mov.group(2), 16):x}"
            xor = re.search(r"\bxor\s+(r9d|r8d|edx|ecx),\1\b", insn)
            if xor:
                constants[xor.group(1)] = "0x0"
            stack = re.search(
                r"\bmov\s+(?:BYTE|WORD|DWORD|QWORD) PTR \[rsp\+0x([0-9a-f]+)\],0x([0-9a-f]+)",
                insn,
            )
            if stack:
                stack_args[f"rsp+0x{stack.group(1)}"] = f"0x{int(stack.group(2), 16):x}"
        r8_command = constants.get("r8b") or constants.get("r8d", "dynamic")
        r9_subcommand = constants.get("r9b") or constants.get("r9d", "dynamic")
        computed_opcode = "dynamic"
        if r8_command != "dynamic" and r9_subcommand != "dynamic":
            computed_opcode = f"0x{(int(r8_command, 0) << 4) | (int(r9_subcommand, 0) << 1):02x}"
        callsites.append(
            {
                "callsite": f"0x{address:011x}",
                "function_start": f"0x{function_start:011x}",
                "function_end": f"0x{function_end:011x}",
                "disasm_line": line_no,
                "transport_kind": matched[1],
                "r8_command": r8_command,
                "r9_subcommand": r9_subcommand,
                "computed_opcode": computed_opcode,
                "rcx": constants.get("ecx", "dynamic"),
                "rdx": constants.get("edx", "dynamic"),
                "stack_constants": stack_args,
                "referenced_strings": referenced_strings[:12],
            }
        )
    return callsites


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pcap", type=Path, required=True)
    parser.add_argument("--disasm", type=Path, required=True)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--strings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packets = [decode_usbpcap(packet) for packet in iter_pcapng_packets(args.pcap)]
    out_frames = [describe_a0(frame) for frame in split_bulk_frames(packets, 0x01, 0)]
    in_frames = [describe_a0(frame) for frame in split_bulk_frames(packets, 0x81, 1)]
    calls = builder_callsites(args.disasm, args.dll, args.strings)
    transfer_counts = Counter(
        (packet.get("transfer"), packet.get("endpoint"), packet.get("info")) for packet in packets
    )
    output = {
        "packet_count": len(packets),
        "transfer_counts": [
            {"transfer": key[0], "endpoint": key[1], "info": key[2], "count": value}
            for key, value in sorted(transfer_counts.items(), key=lambda item: str(item[0]))
        ],
        "host_to_device_frames": out_frames,
        "device_to_host_frames": in_frames,
        "builder_callsites": calls,
        "builder_callsite_count": len(calls),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"packets": len(packets), "out_frames": len(out_frames), "in_frames": len(in_frames), "builder_callsites": len(calls)}))


if __name__ == "__main__":
    main()
