#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reproduce the D253 seed/restore/0x20-vs-0x22 audit offline.

This program only reads pinned repository artifacts.  It has no USB, TLS,
network, privilege, secret, firmware-execution, or device-mutation path.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
from pathlib import Path


CAPTURE_SHA256 = "50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b"
DLL_SHA256 = "904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2"
APP_SHA256 = "8305b1c43ab092d3e55d353c5cd0a01675c1f4d47980557b084decfd53877079"
OPAQUE_TAIL = bytes(18) + bytes.fromhex("cbf2e2befb7f") + bytes(18)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    require(
        ((raw[4] & 0xFE) + raw[5] + raw[6] + sum(inner)) & 0xFF == 0xAA,
        "bad A0 checksum",
    )
    return raw[4], inner[:-1]


def function_slice(disasm: str, begin: int, end: int) -> str:
    lines = []
    for line in disasm.splitlines():
        match = re.match(r"\s*([0-9a-f]+):", line)
        if match and begin <= int(match.group(1), 16) < end:
            lines.append(line)
    require(bool(lines), f"missing disassembly slice {begin:x}..{end:x}")
    return "\n".join(lines)


def audit(repo: Path) -> dict:
    census = load_census(repo)
    corpus = repo / "analysis/D230/work/GoodixExport"
    capture = corpus / "rilevamento.pcapng"
    dll = corpus / "gfusb.dll"
    app = repo / "analysis/D230/work/app/GF_ST411SEC_APP_12509_mapped_code.bin"
    disasm_path = corpus / "gfusb_static_refs/gfusb_disasm.txt"

    hashes = {"capture": sha256(capture), "gfusb_dll": sha256(dll), "app12509": sha256(app)}
    require(hashes["capture"] == CAPTURE_SHA256, "unexpected capture hash")
    require(hashes["gfusb_dll"] == DLL_SHA256, "unexpected gfusb.dll hash")
    require(hashes["app12509"] == APP_SHA256, "unexpected APP12509 hash")

    packets = [census.decode_usbpcap(p) for p in census.iter_pcapng_packets(capture)]
    packet_by_index = {p["packet_index"]: p for p in packets}
    out_frames = census.split_bulk_frames(packets, 0x01, 0)
    in_frames = census.split_bulk_frames(packets, 0x81, 1)
    out_by_index = {f["first_packet_index"]: f for f in out_frames}
    in_by_index = {f["first_packet_index"]: f for f in in_frames}

    decoded_out = []
    for frame in out_frames:
        if frame["raw"] and frame["raw"][0] == 0xA0:
            control = frame["raw"][4]
            try:
                _parsed_control, data = a0_inner(frame)
                require(_parsed_control == control, "OUT control mismatch")
            except AssertionError:
                # Some image/config application records use a distinct inner
                # integrity contract. Their control/index remain useful for
                # ordering, but D253 does not interpret their body.
                data = b""
            decoded_out.append((frame["first_packet_index"], control, data, frame))
    decoded_in = []
    for frame in in_frames:
        if frame["raw"] and frame["raw"][0] == 0xA0:
            control = frame["raw"][4]
            try:
                _parsed_control, data = a0_inner(frame)
                require(_parsed_control == control, "IN control mismatch")
            except AssertionError:
                data = b""
            decoded_in.append((frame["first_packet_index"], control, data, frame))

    def physical_row(index: int, control: int, data: bytes, frame: dict) -> dict:
        packet = packet_by_index[index]
        require(packet["data_len"] == 64, f"packet {index}: OUT is not 64 bytes")
        tail = packet["payload"][len(frame["raw"]) :]
        require(len(tail) == 64 - len(frame["raw"]), f"packet {index}: tail width")
        return {
            "packet_index_zero_based": index,
            "control": f"0x{control:02x}",
            "data_hex": data.hex(),
            "logical_a0_length": len(frame["raw"]),
            "physical_usb_out_length": packet["data_len"],
            "tail_hex": tail.hex(),
            "tail_nonzero": [
                {"physical_offset_zero_based": len(frame["raw"]) + offset,
                 "value": f"0x{value:02x}"}
                for offset, value in enumerate(tail) if value
            ],
        }

    def first_ack(request_index: int, echo: int) -> tuple[int, bytes]:
        for index, control, data, _frame in decoded_in:
            if index > request_index and control == 0xB0 and len(data) == 2 and data[0] == echo:
                return index, data
        raise AssertionError(f"missing ACK for {request_index}/0x{echo:02x}")

    fdt36 = []
    fdt36_tails = []
    fdt36_occurrences = [(i, c, d, f) for i, c, d, f in decoded_out if c == 0x36]
    require([row[0] for row in fdt36_occurrences] == [142, 154, 172], "0x36 census changed")
    learned = {
        147: "80ad80be80a380b180a680b2",
        159: "80ad80bd80a380b180a680b2",
        177: "80ac80bd80a380b180a680b2",
    }
    event_for_request = {142: 147, 154: 159, 172: 177}
    previous_learned = None
    for position, (index, control, data, frame) in enumerate(fdt36_occurrences):
        require(len(data) == 14 and data[:2] == b"\x09\x01", "bad 0x36 body")
        row = physical_row(index, control, data, frame)
        tail = bytes.fromhex(row["tail_hex"])
        fdt36_tails.append(tail)
        ack_index, ack_data = first_ack(index, 0x36)
        event_index = event_for_request[index]
        event_control, event_data = a0_inner(in_by_index[event_index])
        require(event_control == 0x36 and event_data[:4] == b"\x00\x01\x00\x00",
                "bad IRQ100 event")
        if previous_learned is not None:
            require(data[2:].hex() == previous_learned, "learned table not chained")
        previous_learned = learned[event_index]
        row.update({
            "table12_hex": data[2:].hex(),
            "ack_packet_index_zero_based": ack_index,
            "ack_echo": f"0x{ack_data[0]:02x}",
            "ack_status": f"0x{ack_data[1]:02x}",
            "irq_packet_index_zero_based": event_index,
            "irq": "0x0100",
            "learned_table12_hex": learned[event_index],
            "request_to_ack_ms": round((packet_by_index[ack_index]["timestamp_ticks"] -
                                         packet_by_index[index]["timestamp_ticks"]) / 1000, 3),
            "request_to_irq_ms": round((packet_by_index[event_index]["timestamp_ticks"] -
                                         packet_by_index[index]["timestamp_ticks"]) / 1000, 3),
            "relation_to_previous": "initial_seed" if position == 0 else "uses_previous_irq100_result",
            "relation_to_next": "feeds_next_0x36" if position < 2 else "feeds_all_later_0x32",
        })
        fdt36.append(row)
    require(all(tail == OPAQUE_TAIL for tail in fdt36_tails), "0x36 tail profile changed")

    contexts = {
        167: "baseline/no-finger image between manual FDT samples",
        227: "first image command immediately after 0x32 IRQ 0x0002 finger-down",
        238: "baseline/no-finger image immediately after 0x34 IRQ 0x0200 finger-up",
    }
    image_commands = []
    occurrences_20_22 = [(i, c, d, f) for i, c, d, f in decoded_out if c in (0x20, 0x22)]
    require([row[0] for row in occurrences_20_22] == [167, 227, 238], "0x20/0x22 census changed")
    for index, control, data, frame in occurrences_20_22:
        require(data == b"\x01\x00", "image command body differs")
        row = physical_row(index, control, data, frame)
        ack_index, ack_data = first_ack(index, control)
        next_rx = min(f["first_packet_index"] for f in in_frames if f["first_packet_index"] > ack_index)
        next_frame = in_by_index[next_rx]
        require(next_frame["raw"][0] == 0xB0 and len(next_frame["raw"]) == 7726,
                "next RX is not the observed B0/TLS image-sized frame")
        row.update({
            "cmd0": 2,
            "cmd1": (control >> 1) & 0x7,
            "more_bit": control & 1,
            "ack_packet_index_zero_based": ack_index,
            "ack_echo": f"0x{ack_data[0]:02x}",
            "ack_status": f"0x{ack_data[1]:02x}",
            "request_to_ack_ms": round((packet_by_index[ack_index]["timestamp_ticks"] -
                                         packet_by_index[index]["timestamp_ticks"]) / 1000, 3),
            "next_rx_packet_index_zero_based": next_rx,
            "next_rx_outer": "0xb0_tls",
            "next_rx_logical_length": len(next_frame["raw"]),
            "request_to_next_rx_ms": round((packet_by_index[next_rx]["timestamp_ticks"] -
                                             packet_by_index[index]["timestamp_ticks"]) / 1000, 3),
            "target_context": contexts[index],
        })
        image_commands.append(row)
    require(image_commands[0]["tail_hex"] == image_commands[1]["tail_hex"] ==
            image_commands[2]["tail_hex"], "image-command tails differ")
    require(image_commands[1]["cmd1"] == 1 and image_commands[1]["more_bit"] == 0,
            "0x22 decomposition is not cmd1=1/more=0")

    post_first_fdt_controls = [c for i, c, _d, _f in decoded_out if i > 178]
    require(0xA2 not in post_first_fdt_controls and 0x70 not in post_first_fdt_controls,
            "unexpected explicit A2/0x70 restore")
    require(next(i for i, _c, _d, _f in decoded_out if i > 220) == 227,
            "0x22 is not the first OUT after the finger-down arm")

    disasm = disasm_path.read_text(errors="replace")
    set_mode = function_slice(disasm, 0x180024C90, 0x180025C84)
    seed_setter = function_slice(disasm, 0x180028480, 0x180028522)
    irq_writer = function_slice(disasm, 0x180029210, 0x180029313)
    otp_file = function_slice(disasm, 0x180026CE0, 0x1800275E5)
    on_cancel = function_slice(disasm, 0x18001FA90, 0x18001FD32)

    require("0x180580818" in set_mode and "0x180580818" in seed_setter and
            "0x180580818" in irq_writer, "FDT-down global dataflow anchors missing")
    require("0x18007b1f0" in seed_setter, "seed setter memcpy missing")
    require("0x1800290f4" in irq_writer, "IRQ baseline validator missing")
    require("180026c6a:" in disasm and "# 0x180028480" in disasm and "+0x13d68" in disasm,
            "host callback registration for seed setter missing")
    require("b9 40 00 00 00" in set_mode and "rep stos BYTE PTR [rdi],al" in set_mode,
            "64-byte local SetMode buffer clear missing")
    require("shl    ecx,0x4" in set_mode and "[rsp+0x148]" in set_mode,
            "SetMode command-selector construction missing")
    require("0x18007ba10" in otp_file, "OTP file/live comparison missing")
    require(not any(call in on_cancel for call in ("call   0x18005c148", "call   0x18005cc04")),
            "gfOnCancel directly reaches an A0 builder")

    dll_bytes = dll.read_bytes()
    required_utf16 = (
        "goodix.dat", "read %d bytes from %s", "got file OTP:",
        "the same OTP in file and from FP",
        "NOT the same OTP in file(not in file) and from FP, use data from FP",
        "USED OTP:",
    )
    require(all(text.encode("utf-16le") in dll_bytes for text in required_utf16),
            "goodix.dat/OTP evidence strings missing")
    goodix_files = [p.relative_to(repo).as_posix() for p in repo.rglob("*")
                    if p.is_file() and p.name.lower() == "goodix.dat"]
    require(not goodix_files, "raw goodix.dat unexpectedly present")

    first_seed = bytes.fromhex("adadbdbda3a3b1b1a6a6b2b2")
    target_bins = [dll, app, corpus / "AlgoChicago.dll", corpus / "AlgoChicagoT.dll",
                   corpus / "AlgoMilan.dll", corpus / "EngineAdapter.dll"]
    require(not any(first_seed in path.read_bytes() for path in target_bins),
            "first seed unexpectedly found as a target binary literal")

    core = (repo / "core/post_d4.py").read_text()
    require("build_finger_image()" in core and "_send_async(build_finger_image(), 0x22)" in core,
            "current core does not model target IRQ2 -> 0x22")
    require("0x22: ACK_OPTIONAL" in core, "0x22 ACK policy missing")
    tree = ast.parse(core)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    require(not imported_roots.intersection({"usb", "libusb1", "ssl", "socket"}),
            "current offline core gained a real USB/TLS/network import")

    return {
        "schema": "D253_OFFLINE_AUDIT_V1",
        "execution_mode": "OFFLINE_ONLY",
        "source_hashes": hashes,
        "fdt36_complete_census": {
            "occurrence_count": len(fdt36),
            "tail_profile_count": len(set(fdt36_tails)),
            "tail_identical": len(set(fdt36_tails)) == 1,
            "zero_tail_observed": any(not any(tail) for tail in fdt36_tails),
            "occurrences": fdt36,
        },
        "fdt_seed_dataflow": {
            "global": "0x180580818",
            "host_supplied_setter": "0x180028480",
            "setter_callback_slot": "context+0x13d68",
            "setter_registration": "0x180026c6a",
            "irq100_validator": "0x1800290f4",
            "irq100_transform_writer": "0x180029210",
            "ultimate_host_caller_and_input_source_in_available_corpus": "NOT_RESOLVED",
            "fixed_iteration_or_convergence_criterion_in_gfusb": "NOT_FOUND; orchestration is external",
        },
        "physical_contract": {
            "logical_0x36_length": 22,
            "physical_out_length": 64,
            "opaque_nonzero_offsets": [40, 41, 42, 43, 44, 45],
            "opaque_nonzero_hex": "cbf2e2befb7f",
            "set_mode_local_64_byte_buffer_explicitly_zeroed": True,
            "captured_tail_also_shared_by_0x20_0x22": True,
            "tail_class": "TRANSPORT_STAGING_RESIDUE_INFERRED; OUTSIDE_DECLARED_A0",
            "target_0x36_zero_tail_equivalence": "NOT_PROVEN",
        },
        "goodix_dat": {
            "available_for_audit": False,
            "raw_paths": goodix_files,
            "oem_dll_observation": "reads OTP-sized prefix and compares file OTP with sensor OTP",
            "direct_dataflow_to_fdt_down_global": False,
            "fdt_fields_magic_version_timestamp_temperature_freshness_in_oem_path": "NOT_PROVEN",
            "rocky_format": "CORROBORATION_ONLY; not target proof and not parsed by this target audit",
        },
        "post_fdt_restore": {
            "explicit_a2_or_0x70_after_first_0x32": False,
            "gf_on_cancel_direct_a0_builder": False,
            "successful_cycle": "0x32->IRQ2->0x22->B0/TLS image->0x34->IRQ0x200->0x20->B0/TLS image->later 0x32",
            "first_0x32_no_explicit_restore_before_later_activity": True,
            "third_0x32_capture_ends_without_restore": True,
            "usb_close_tls_close_timeout_error_deinit_semantics": "NOT_EXPOSED_BY_AVAILABLE_PRIMARY_EVIDENCE",
        },
        "image_command_differential": image_commands,
        "core_correction": {
            "post_irq2_command": "0x22_DATA_0100",
            "baseline_builder_retained": "0x20_DATA_0100",
            "cmd20_22_relation": "same cmd0=2/body; cmd1 0 versus 1; more=0 for both",
            "post_irq2_attempt_fence": "single-shot terminal on ACK/exchange failure",
            "real_usb_tls_network_backend_reachable": False,
        },
        "safety": {
            "real_usb_open_count": 0,
            "real_tls_handshake_count": 0,
            "real_d4_send_count": 0,
            "real_af_send_count": 0,
            "real_fdt_send_count": 0,
            "real_image_command_count": 0,
            "real_finger_interaction_count": 0,
            "retry_count": 0,
            "persistent_write_family_count": 0,
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
