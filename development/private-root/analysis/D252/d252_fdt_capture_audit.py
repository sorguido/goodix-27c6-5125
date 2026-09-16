#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reproduce the D252 target-capture FDT precondition audit offline.

This tool only reads repository artifacts.  It has no USB, network, secret,
firmware execution, or device mutation path.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path


EXPECTED_CAPTURE_SHA256 = "50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b"
EXPECTED_36_INDICES = (142, 154, 172)
EXPECTED_32_INDICES = (178, 220, 251)
EXPECTED_FINAL_TABLE = bytes.fromhex("80ac80bd80a380b180a680b2")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_census(repo: Path):
    path = repo / "analysis/D230/tools/offline_census.py"
    spec = importlib.util.spec_from_file_location("d230_offline_census", path)
    require(spec is not None and spec.loader is not None, "cannot load D230 parser")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def a0_inner(frame: dict) -> tuple[int, bytes]:
    raw = frame["raw"]
    require(len(raw) >= 8 and raw[0] == 0xA0, "not an A0 frame")
    inner_len = int.from_bytes(raw[5:7], "little")
    inner = raw[7 : 7 + inner_len]
    require(len(inner) == inner_len, "short A0 inner frame")
    require(((raw[4] & 0xFE) + raw[5] + raw[6] + sum(inner)) & 0xFF == 0xAA,
            "bad A0 checksum")
    return raw[4], inner[:-1]


def table_from_irq100(data: bytes) -> bytes:
    require(data[:4] == bytes.fromhex("00010000"), "not IRQ 0x0100/touch=0")
    raw = data[4:16]
    require(len(raw) == 12, "bad IRQ baseline width")
    words = [int.from_bytes(raw[i : i + 2], "little") for i in range(0, 12, 2)]
    require(all(((word >> 1) & 0xFF) not in (0, 0xFF) for word in words),
            "baseline validator would reject word")
    return b"".join((((word >> 1) << 8) | 0x80).to_bytes(2, "little") for word in words)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(repo: Path) -> dict:
    census = load_census(repo)
    capture = repo / "analysis/D230/work/GoodixExport/rilevamento.pcapng"
    capture_hash = sha256(capture)
    require(capture_hash == EXPECTED_CAPTURE_SHA256, "unexpected target capture hash")

    packets = [census.decode_usbpcap(p) for p in census.iter_pcapng_packets(capture)]
    packet_by_index = {p["packet_index"]: p for p in packets}
    out_frames = census.split_bulk_frames(packets, 0x01, 0)
    in_frames = census.split_bulk_frames(packets, 0x81, 1)
    out_by_index = {f["first_packet_index"]: f for f in out_frames}
    in_by_index = {f["first_packet_index"]: f for f in in_frames}

    def out_row(index: int, expected_control: int) -> tuple[dict, bytes, bytes]:
        frame = out_by_index[index]
        control, data = a0_inner(frame)
        require(control == expected_control, f"packet {index}: wrong control")
        packet = packet_by_index[index]
        require(packet["data_len"] == 64, f"packet {index}: physical OUT is not 64")
        tail = packet["payload"][len(frame["raw"]) :]
        nonzero = [
            {"physical_offset_zero_based": len(frame["raw"]) + offset, "value": f"0x{value:02x}"}
            for offset, value in enumerate(tail) if value
        ]
        return {
            "packet_index_zero_based": index,
            "wire_control": f"0x{control:02x}",
            "logical_frame_length": len(frame["raw"]),
            "physical_submission_length": packet["data_len"],
            "physical_tail_nonzero_bytes": nonzero,
        }, data, tail

    fdt36 = []
    learned_tables: list[bytes] = []
    for request_index, ack_index, event_index in ((142, 145, 147), (154, 157, 159), (172, 175, 177)):
        row, data, tail = out_row(request_index, 0x36)
        require(len(data) == 14 and data[:2] == b"\x09\x01", "bad 0x36 request shape")
        require(tail == bytes(18) + bytes.fromhex("cbf2e2befb7f") + bytes(18),
                "unexpected 0x36 opaque physical tail profile")
        ack_control, ack_data = a0_inner(in_by_index[ack_index])
        require(ack_control == 0xB0 and ack_data == b"\x36\x01", "bad 0x36 ACK")
        event_control, event_data = a0_inner(in_by_index[event_index])
        require(event_control == 0x36, "bad 0x36 event control")
        learned = table_from_irq100(event_data)
        learned_tables.append(learned)
        row.update({
            "input_table_hex": data[2:].hex(),
            "ack_packet_index_zero_based": ack_index,
            "ack_echo": "0x36",
            "ack_status": "0x01",
            "irq_packet_index_zero_based": event_index,
            "irq": "0x0100",
            "touch_flag": 0,
            "learned_table_hex": learned.hex(),
            "request_to_ack_ms": round(
                (packet_by_index[ack_index]["timestamp_ticks"] - packet_by_index[request_index]["timestamp_ticks"]) / 1000,
                3,
            ),
            "request_to_irq_ms": round(
                (packet_by_index[event_index]["timestamp_ticks"] - packet_by_index[request_index]["timestamp_ticks"]) / 1000,
                3,
            ),
        })
        fdt36.append(row)

    require(learned_tables[0] == bytes.fromhex("80ad80be80a380b180a680b2"),
            "unexpected first learned table")
    require(learned_tables[1] == bytes.fromhex("80ad80bd80a380b180a680b2"),
            "unexpected second learned table")
    require(learned_tables[2] == EXPECTED_FINAL_TABLE, "unexpected final learned table")
    require(a0_inner(out_by_index[154])[1][2:] == learned_tables[0],
            "first learned table is not fed to next 0x36")
    require(a0_inner(out_by_index[172])[1][2:] == learned_tables[1],
            "second learned table is not fed to next 0x36")

    fdt32 = []
    for request_index, ack_index in ((178, 181), (220, 223), (251, 253)):
        row, data, tail = out_row(request_index, 0x32)
        require(len(data) == 16 and data[:2] == b"\x08\x01", "bad 0x32 request shape")
        require(tail == bytes(40), "0x32 physical tail is not all zero")
        require(data[2:14] == EXPECTED_FINAL_TABLE, "0x32 does not use final learned table")
        ack_control, ack_data = a0_inner(in_by_index[ack_index])
        require(ack_control == 0xB0 and ack_data == b"\x32\x01", "bad 0x32 ACK")
        row.update({
            "table_hex": data[2:14].hex(),
            "timestamp_le_hex": data[14:16].hex(),
            "ack_packet_index_zero_based": ack_index,
            "ack_echo": "0x32",
            "ack_status": "0x01",
            "request_to_ack_ms": round(
                (packet_by_index[ack_index]["timestamp_ticks"] - packet_by_index[request_index]["timestamp_ticks"]) / 1000,
                3,
            ),
        })
        fdt32.append(row)

    event_control, event_data = a0_inner(in_by_index[225])
    require(event_control == 0x32 and event_data[:4] == bytes.fromhex("02003f00"),
            "expected finger-down IRQ after second 0x32")
    next_control, next_data = a0_inner(out_by_index[227])
    require(next_control == 0x22 and next_data == b"\x01\x00",
            "post-IRQ target command is not exact 0x22/0100")
    require(227 == min(i for i in out_by_index if i > 220), "unexpected OUT before post-IRQ command")

    up_row, up_data, _up_tail = out_row(233, 0x34)
    require(len(up_data) == 14 and up_data[:2] == b"\x0a\x01", "bad 0x34 request shape")
    up_ack_control, up_ack_data = a0_inner(in_by_index[235])
    require(up_ack_control == 0xB0 and up_ack_data == b"\x34\x01", "bad 0x34 ACK")
    up_event_control, up_event_data = a0_inner(in_by_index[237])
    require(up_event_control == 0x34 and up_event_data[:2] == b"\x00\x02",
            "0x34 does not lead to target IRQ 0x0200")

    post_fdt_controls = [frame["raw"][4] for index, frame in out_by_index.items()
                         if index > 178 and len(frame["raw"]) >= 5 and frame["raw"][0] == 0xA0]
    require(0xA2 not in post_fdt_controls and 0x70 not in post_fdt_controls,
            "target capture unexpectedly has A2/0x70 post-FDT restore")

    disasm_path = repo / "analysis/D230/work/GoodixExport/gfusb_static_refs/gfusb_disasm.txt"
    on_cancel_lines = []
    for line in disasm_path.read_text(errors="replace").splitlines():
        match = re.match(r"\s*([0-9a-f]+):", line)
        if match and 0x18001FA90 <= int(match.group(1), 16) < 0x18001FD32:
            on_cancel_lines.append(line)
    require(on_cancel_lines, "gfOnCancel function slice not found")
    require(not any("call   0x18005c148" in line or "call   0x18005cc04" in line
                    for line in on_cancel_lines),
            "gfOnCancel directly calls an A0 builder")

    # Exact sequence non-occurrence checks are intentionally narrow.  They do
    # not claim the dynamic values cannot originate elsewhere in absent code.
    config90 = out_by_index[103]["raw"]
    dll = repo / "analysis/D230/work/GoodixExport/gfusb.dll"
    app = repo / "analysis/D230/work/app/GF_ST411SEC_APP_12509_mapped_code.bin"
    all_tables = (bytes.fromhex("adadbdbda3a3b1b1a6a6b2b2"), *learned_tables)
    require(not any(table in config90 for table in all_tables),
            "an observed FDT table is unexpectedly in config 0x90")
    require(not any(table in dll.read_bytes() for table in all_tables),
            "an observed FDT table is unexpectedly embedded in gfusb.dll")
    require(not any(table in app.read_bytes() for table in all_tables),
            "an observed FDT table is unexpectedly embedded in APP12509")

    return {
        "schema": "D252_FDT_CAPTURE_AUDIT_V1",
        "execution_mode": "OFFLINE_ONLY",
        "primary_capture": {
            "path": "analysis/D230/work/GoodixExport/rilevamento.pcapng",
            "sha256": capture_hash,
            "packet_indices": "zero_based",
        },
        "fdt36_requests": fdt36,
        "fdt32_requests": fdt32,
        "causal_checks": {
            "irq100_transform_exact_for_all_three_samples": True,
            "learned_table_chained_between_0x36_requests": True,
            "final_learned_table_used_by_all_0x32_requests": True,
            "second_0x32_finger_down_irq_packet": 225,
            "next_out_packet": 227,
            "next_out_wire_control": "0x22",
            "next_out_data_hex": "0100",
            "previous_D249_0x20_assumption_matches_target_occurrence": False,
        },
        "narrow_exact_sequence_checks": {
            "all_observed_seed_and_learned_tables_absent_from_config90_frame_103": True,
            "all_observed_seed_and_learned_tables_absent_as_literals_from_gfusb_dll": True,
            "all_observed_seed_and_learned_tables_absent_as_literals_from_app12509": True,
        },
        "restore_checks": {
            "target_0x34_packet": up_row["packet_index_zero_based"],
            "target_0x34_data_prefix": "0a01",
            "target_0x34_following_irq": "0x0200",
            "a2_or_0x70_observed_after_first_fdt_arm": False,
            "gfOnCancel_direct_a0_builder_call": False,
            "deterministic_device_restore_proven": False,
        },
        "safety": {
            "usb_open_count": 0,
            "command_count": 0,
            "persistent_write_family_count": 0,
            "network_access": 0,
        },
        "result": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve() if args.repo else Path(__file__).resolve().parents[2]
    print(json.dumps(audit(repo), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
