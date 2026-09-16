#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Hash-gated, sanitizing D254 audit of public external FDT evidence.

The inputs stay outside the project repository.  This program reads a pinned
public Git checkout, its WBDI text log, and the public Issue #63 USBPcap.  It
emits only control-flow metadata, small FDT tables, hashes, line references and
counts; it never exports OTP, PSK, TLS contents, images, or raw packet dumps.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
import subprocess
from collections import Counter
from pathlib import Path


SOURCE_A_COMMIT = "d39e34f240270bb13c3977a7fa99973c346fa81f"
SOURCE_A_TREE = "165cc7ffc3380b8fdd106e069e5a874c48b11077"
WBDI_SHA256 = "050d6cbb8e676bf085b77e6376a2b8db972e614683e32cea8834cdd60f8c6ba1"
ISSUE63_ZIP_SHA256 = "61e1d5354cb9617cd602b8ee465aa6693381d00899a7f50af3d10ee89b86bc3c"
ISSUE63_PCAP_SHA256 = "5b2e9649b8acdbf93bbb19275feb32203dacc50d727ef2222d58162fbd1b63d0"

PRIORITY_FILES = (
    "README.md",
    "fp/fork-goodixtls/libfprint/drivers/goodixtls/goodix5125.c",
    "fp/fork-goodixtls/libfprint/drivers/goodixtls/goodix5125.h",
    "fp/fork-goodixtls/libfprint/drivers/goodixtls/goodix.c",
    "fp/fork-goodixtls/libfprint/drivers/goodixtls/goodix5xx.c",
    "fp/fork-goodixtls/libfprint/drivers/goodixtls/goodix_proto.c",
    "fp/goodix-fp-dump/exp5125_realpsk.py",
    "fp/goodix-fp-dump/exp5125_v2.py",
    "fp/goodix-fp-dump/exp5125_v3.py",
    "fp/goodix-fp-dump/fdt_seed_probe.py",
    "wbdi_utf8.log",
)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, stderr=subprocess.DEVNULL
    ).strip()


def line_ref(lines: list[str], text: str, start: int = 1) -> int:
    for index in range(start - 1, len(lines)):
        if text in lines[index]:
            return index + 1
    raise AssertionError(f"missing WBDI marker: {text}")


def learned_table(raw_hex: str) -> str:
    raw = bytes.fromhex(raw_hex)
    require(len(raw) == 12, "FDT raw baseline is not 12 bytes")
    out = bytearray()
    for offset in range(0, 12, 2):
        word = int.from_bytes(raw[offset : offset + 2], "little")
        value = word >> 1
        out += bytes((0x80, value & 0xFF))
    return out.hex()


def parse_wbdi(path: Path) -> dict:
    require(sha256(path) == WBDI_SHA256, "unexpected Source A WBDI hash")
    lines = path.read_text(errors="replace").splitlines()
    require(len(lines) == 1123, "unexpected Source A WBDI line count")

    metadata = {
        "vid_pid": {"value": "27c6:5110", "line": line_ref(lines, "USB\\VID_27C6&PID_5110&REV_0200")},
        "driver_version": {"value": "1.1.124.12", "line": line_ref(lines, "driver version:1.1.124.12")},
        "firmware": {"value": "GF_ST411SEC_APP_12117", "line": line_ref(lines, "got evk version: GF_ST411SEC_APP_12117")},
        "chipid": {"value": "0x2504", "line": line_ref(lines, "Get Chip ID: 0x2504")},
        "sensor_type": {"value": 12, "line": line_ref(lines, "sensorType:12, col:80, row:64")},
    }

    update_begin = line_ref(lines, "[gf_update_all_base:05336] Goodix>>> enter")
    update_end = line_ref(lines, "[gf_update_all_base:05563] Goodix>>> exit, ren = 1", update_begin)
    seeds: list[tuple[int, str]] = []
    raw_rows: list[tuple[int, str]] = []
    get_indices: list[tuple[int, int]] = []
    for line_no in range(update_begin, update_end + 1):
        line = lines[line_no - 1]
        match = re.search(r"gf_get_fdtbase (\d)(?:\s|$)", line)
        if match and "finshed" not in line:
            get_indices.append((line_no, int(match.group(1))))
        if "base data sent::0x" in line:
            value = line.split("base data sent::0x", 1)[1].strip()
            if len(value) == 24:
                seeds.append((line_no, value))
        if "received fdt base::0x" in line:
            value = line.split("received fdt base::0x", 1)[1].strip()
            if len(value) == 24:
                raw_rows.append((line_no, value))

    require([value for _, value in get_indices] == [0, 1, 2], "WBDI pass indices changed")
    require(len(seeds) == len(raw_rows) == 3, "WBDI successful FDT pass count changed")
    passes = []
    for position, ((seed_line, seed), (raw_line, raw)) in enumerate(zip(seeds, raw_rows)):
        learned = learned_table(raw)
        if position < 2:
            require(learned == seeds[position + 1][1], "WBDI FDT chaining changed")
        passes.append({
            "pass_index": get_indices[position][1],
            "index_line": get_indices[position][0],
            "seed_line": seed_line,
            "seed_table_hex": seed,
            "irq100_raw_line": raw_line,
            "irq100_raw_table_hex": raw,
            "learned_table_hex": learned,
            "relation_to_next": "feeds_next_manual_pass" if position < 2 else "feeds_final_fdt_down",
        })

    final_down_line = line_ref(lines, "base data sent::0x80af80bf80a480b880a880b7", update_end)
    require(passes[-1]["learned_table_hex"] == "80af80bf80a480b880a880b7", "WBDI final table changed")

    base_read = line_ref(lines, "read 13520-13520 bytes from base file")
    base_crc = line_ref(lines, "check crc :Crchost:")
    base_otp = line_ref(lines, "get file otp::")
    base_loaded = line_ref(lines, "get nav base and image base from from file")
    imagebase_exists = line_ref(lines, "imagebase exist: 1")
    base_save = line_ref(lines, "write 13520-13520 bytes to base file", update_begin)
    nav_line = line_ref(lines, "[gf_update_all_base:05369] Goodix>>> gf_get_navbase", update_begin)
    read_reg_line = line_ref(lines, "[gf_update_all_base:05400] Goodix>>> fdt_delta", update_begin)
    image_line = line_ref(lines, "[gf_get_oneframe:05262] Goodix>>> enter", update_begin)
    nav_validation_line = line_ref(lines, "Nav_isTouchedByFinger: void", update_begin)
    image_validation_line = line_ref(lines, "Image_isTouchedByFinger: void", update_begin)
    runtime_validity = []
    for line_no, line in enumerate(lines, 1):
        if "gf_check_baseisvalid:05639" in line and "base_is_valid:" in line:
            runtime_validity.append({"line": line_no, "value": int(line.rsplit("base_is_valid:", 1)[1])})
    require(runtime_validity == [{"line": 845, "value": 0}, {"line": 1099, "value": 1}],
            "WBDI runtime base-valid checks changed")
    runtime_refresh_save = line_ref(lines, "write 13520-13520 bytes to base file", base_save + 1)

    return {
        "sha256": WBDI_SHA256,
        "line_count": len(lines),
        "classification": "CROSS_FAMILY_OEM_LIFECYCLE_EVIDENCE_5110_APP12117",
        "target_specific_12509_proof": False,
        "metadata": metadata,
        "base_file": {
            "read_bytes": 13520,
            "read_line": base_read,
            "crc_check_line": base_crc,
            "otp_binding_line": base_otp,
            "nav_and_image_load_line": base_loaded,
            "existing_imagebase_line": imagebase_exists,
            "save_line": base_save,
            "initial_nav_validation_line": nav_validation_line,
            "initial_image_validation_line": image_validation_line,
            "runtime_base_valid_checks": runtime_validity,
            "runtime_refresh_save_line_after_invalid_check": runtime_refresh_save,
            "observed_layout_inference": "OTP64+FDT12+NAV3200+IMAGE10240+CRC4=13520",
            "role": "CRC_AND_OTP_BOUND_HOST_CACHE_READ_THEN_REFRESHED_DURING_THIS_SUCCESSFUL_INIT",
            "regeneration_model": "INITIAL_UPDATE_ALL_BASE_REFRESHES_EXISTING_CACHE; LATER BASE_IS_VALID_0 REFRESHES/SAVES; LATER BASE_IS_VALID_1 RETURNS WITHOUT ANOTHER SAVE",
        },
        "fdt_manual_passes": passes,
        "successful_pass_count": len(passes),
        "pass_model": "STAGED_FIXED_THREE_PASS_OBSERVED_IN_ONE_SUCCESSFUL_INIT; NOT_A_RETRY_LOOP_IN_THE_OBSERVED_PATH",
        "initial_seed_source": "BASEFILE_FDT12_STRONGLY_INFERRED_FROM_13520_BYTE_LAYOUT_AND_PRECEDING_LOAD; DIRECT_FIELD_COPY_NOT_LOGGED",
        "loop_stop_criterion": "ORCHESTRATOR_COMPLETES_NAMED_STAGES_0_1_2; NO_CONVERGENCE_PREDICATE_OR_RETRY_OBSERVED",
        "lifecycle": [
            {"stage": "base_file_crc_otp_nav_image_load", "line": base_read},
            {"stage": "fdt_manual_0", "line": passes[0]["seed_line"]},
            {"stage": "nav", "line": nav_line},
            {"stage": "fdt_manual_1", "line": passes[1]["seed_line"]},
            {"stage": "read_reg_fdt_delta", "line": read_reg_line},
            {"stage": "baseline_image_0x20", "line": image_line},
            {"stage": "fdt_manual_2", "line": passes[2]["seed_line"]},
            {"stage": "nav_image_touch_validation", "line": nav_validation_line},
            {"stage": "base_file_save", "line": base_save},
            {"stage": "fdt_down_0x32", "line": final_down_line},
        ],
    }


def source_file_license(relative: str, text: str) -> tuple[str, str]:
    if "SPDX-License-Identifier: LGPL-2.1-or-later" in text:
        return "LGPL-2.1-or-later", "PER_FILE_SPDX"
    if "GNU Lesser General Public" in text and "version 2.1" in text:
        return "LGPL-2.1-or-later", "PER_FILE_LICENSE_HEADER"
    if relative.startswith("fp/goodix-fp-dump/") and relative != "fp/goodix-fp-dump/LICENSE":
        return "MIT", "DIRECTORY_LICENSE_ONLY; NO_PER_FILE_HEADER"
    if relative == "README.md":
        return "LGPL-2.1 (repository claim)", "README_SCOPE_CLAIM; NO_ROOT_LICENSE_FILE"
    return "NO_EXPLICIT_FILE_LICENSE", "EVIDENCE_ONLY_NO_CODE_REUSE"


def parse_source_a(root: Path) -> dict:
    require(git(root, "rev-parse", "HEAD") == SOURCE_A_COMMIT, "Source A commit mismatch")
    require(git(root, "rev-parse", "HEAD^{tree}") == SOURCE_A_TREE, "Source A tree mismatch")
    rows = []
    for relative in PRIORITY_FILES:
        path = root / relative
        require(path.is_file(), f"missing Source A priority file: {relative}")
        text = path.read_text(errors="replace")
        license_id, basis = source_file_license(relative, text)
        rows.append({
            "path": relative,
            "sha256": sha256(path),
            "license": license_id,
            "license_basis": basis,
            "reuse_status": "EVIDENCE_ONLY_NO_CODE_REUSE",
        })

    c = (root / "fp/fork-goodixtls/libfprint/drivers/goodixtls/goodix5125.c").read_text()
    h = (root / "fp/fork-goodixtls/libfprint/drivers/goodixtls/goodix5125.h").read_text()
    readme = (root / "README.md").read_text()
    require('GOODIX_5125_FIRMWARE_VERSION ("GF_ST411SEC_APP_12509")' in h, "Source A firmware assertion changed")
    seed = "b3b3c3c3a8a8b5b5a8a8b7b7"
    seed_match = re.search(r"fdt_switch_state_mode\[\].*?=\s*\{(.*?)\};", h, re.S)
    require(seed_match is not None, "Source A seed array missing")
    seed_bytes = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", seed_match.group(1)))
    require(seed_bytes == b"\x09\x01" + bytes.fromhex(seed), "Source A seed constant changed")
    require(c.count("goodix_send_mcu_switch_to_fdt_mode (dev") == 2, "Source A FDT step count changed")
    require("goodix_send_nav_0" in c and "goodix_send_read_sensor_register" in c, "Source A NAV/read-reg path changed")
    require("goodix_tls_read_image_timeout" in c, "Source A image path changed")
    require("0x22" not in c, "Source A unexpectedly gained explicit 0x22")
    require("goodix_reset_state (dev);" in c and "goodix_shutdown_tls" in c, "Source A host cleanup changed")
    require("Device activation" in readme and "Finger detection" in readme, "Source A README status changed")

    return {
        "url": "https://github.com/yanxinwu946/goodix-5125-linux",
        "commit": SOURCE_A_COMMIT,
        "tree": SOURCE_A_TREE,
        "file_provenance": rows,
        "claimed_12509": True,
        "fdt_initial_seed_hex": seed,
        "fdt_seed_provenance": "COMMENT_ASSERTION_EMPIRICALLY_LIVE_VERIFIED_AND_AVAIL5125_INHERITANCE; NO_SOURCE_A_WIRE_CAPTURE",
        "scan_path": "QUERY_MCU->0x36_STATIC->NAV->0x36_DERIVED->READ_REG->FOUR_DAC_WRITES->0x20_IMAGE",
        "manual_fdt_step_count": 2,
        "uses_fdt_down_0x32": False,
        "uses_fdt_up_0x34": False,
        "uses_post_irq2_0x22": False,
        "uses_image_0x20": True,
        "device_side_cancel": False,
        "deactivate_behavior": "HOST_TRANSFER_STATE_RESET_AND_TLS_SESSION_PRESERVED; NO_DEVICE_MODE_RESTORE_COMMAND",
        "plaintext_psk_dependency": "REQUIRED_32_BYTE_DEVICE_SPECIFIC_SECRET_LOADED_FROM_DISK",
        "readme_code_discrepancy": "README_CLAIMS_FINGER_DETECTION/PAM_FLOW; CODE_BYPASSES_0x32_IRQ_DETECTION_AND_BLOCKS_ON_0x20_AFTER_TWO_MANUAL_STEPS",
        "implementation_status": "EXPERIMENTAL_THIRD_PARTY_CODE_WITH_LIVE_CLAIMS; NOT_CAPTURE_PROVEN",
        "wbdi": parse_wbdi(root / "wbdi_utf8.log"),
    }


def iter_usbpcap(path: Path):
    with path.open("rb") as stream:
        header = stream.read(24)
        require(len(header) == 24, "short pcap header")
        magic, major, minor, _zone, _sig, snaplen, linktype = struct.unpack("<IHHIIII", header)
        require(magic == 0xA1B2C3D4 and (major, minor) == (2, 4), "unsupported pcap format")
        require(snaplen == 65535 and linktype == 249, "not USBPcap linktype 249")
        index = 0
        while True:
            record = stream.read(16)
            if not record:
                break
            require(len(record) == 16, "short pcap record header")
            sec, usec, included, original = struct.unpack("<IIII", record)
            packet = stream.read(included)
            require(len(packet) == included and included == original, "truncated USBPcap record")
            require(len(packet) >= 27, "short USBPcap pseudoheader")
            header_len = struct.unpack_from("<H", packet)[0]
            require(27 <= header_len <= len(packet), "bad USBPcap header length")
            yield {
                "packet_index": index,
                "timestamp_us": sec * 1_000_000 + usec,
                "endpoint": packet[21],
                "transfer": packet[22],
                "payload": packet[header_len:],
            }
            index += 1


def decode_a0(packet: dict, *, strict: bool = True) -> dict | None:
    payload = packet["payload"]
    if len(payload) < 8 or payload[0] != 0xA0:
        return None
    logical = int.from_bytes(payload[1:3], "little") + 4
    require(8 <= logical <= len(payload), "bad A0 logical length")
    raw = payload[:logical]
    inner_len = int.from_bytes(raw[5:7], "little")
    require(7 + inner_len == logical, "bad A0 inner length")
    inner = raw[7 : 7 + inner_len]
    control = raw[4]
    checksum_ok = (((control & 0xFE) + raw[5] + raw[6] + sum(inner)) & 0xFF) == 0xAA
    if not checksum_ok and not strict:
        return None
    require(checksum_ok, "bad A0 checksum")
    tail = payload[logical:]
    return {
        **packet,
        "control": control,
        "body": inner[:-1],
        "logical_length": logical,
        "physical_length": len(payload),
        "tail": tail,
        "tail_nonzero_offsets": [logical + i for i, value in enumerate(tail) if value],
    }


def next_frame(frames: list[dict], packet_index: int, *, endpoint: int | None = None) -> dict:
    for frame in frames:
        if frame["packet_index"] > packet_index and (endpoint is None or frame["endpoint"] == endpoint):
            return frame
    raise AssertionError(f"no frame after packet {packet_index}")


def parse_issue63(pcap: Path, zip_path: Path) -> dict:
    require(sha256(zip_path) == ISSUE63_ZIP_SHA256, "unexpected Issue63 ZIP hash")
    require(sha256(pcap) == ISSUE63_PCAP_SHA256, "unexpected Issue63 pcap hash")
    packets = list(iter_usbpcap(pcap))
    require(len(packets) == 752, "Issue63 packet count changed")
    t0 = packets[0]["timestamp_us"]

    descriptors = []
    for packet in packets:
        data = packet["payload"]
        if len(data) == 18 and data[:2] == b"\x12\x01":
            descriptors.append((int.from_bytes(data[8:10], "little"), int.from_bytes(data[10:12], "little")))
    require((0x27C6, 0x5125) in descriptors, "Issue63 device descriptor is not 27c6:5125")

    a0 = [decoded for packet in packets if (decoded := decode_a0(packet, strict=False)) is not None]
    outbound = [frame for frame in a0 if frame["endpoint"] == 0x01]
    inbound = [frame for frame in a0 if frame["endpoint"] == 0x81]
    out_counts = Counter(frame["control"] for frame in outbound)
    in_counts = Counter(frame["control"] for frame in inbound)
    b0_images = [packet for packet in packets
                 if packet["endpoint"] == 0x81 and len(packet["payload"]) == 7726
                 and packet["payload"][:1] == b"\xB0"]

    expected_counts = {0x20: 14, 0x22: 21, 0x32: 37, 0x34: 35, 0x36: 22, 0xAF: 1}
    for control, count in expected_counts.items():
        require(out_counts[control] == count, f"Issue63 0x{control:02x} count changed")
    require(out_counts[0xA8] == out_counts[0x50] == out_counts[0x80] == out_counts[0x82] == 0,
            "Issue63 unexpectedly exposes firmware/NAV/register init")
    require(len(b0_images) == 35, "Issue63 image-sized B0 count changed")

    def next_out_after(index: int) -> dict:
        return next_frame(outbound, index)

    irq2 = [frame for frame in inbound if frame["control"] == 0x32 and frame["body"][:2] == b"\x02\x00"]
    irq100 = [frame for frame in inbound if frame["control"] == 0x36 and frame["body"][:2] == b"\x00\x01"]
    irq200 = [frame for frame in inbound if frame["control"] == 0x34 and frame["body"][:2] == b"\x00\x02"]
    require(len(irq2) == 21 and len(irq100) == 22 and len(irq200) == 13, "Issue63 IRQ census changed")
    require(all(next_out_after(frame["packet_index"])["control"] == 0x22 for frame in irq2),
            "Issue63 post-IRQ2 command is not uniformly 0x22")
    require(all(next_out_after(frame["packet_index"])["body"] == b"\x01\x00" for frame in irq2),
            "Issue63 post-IRQ2 body changed")
    post_irq100 = Counter(next_out_after(frame["packet_index"])["control"] for frame in irq100)
    require(post_irq100 == Counter({0x20: 14, 0x32: 8}),
            "Issue63 post-IRQ100 lifecycle changed")

    manual = []
    for request in [frame for frame in outbound if frame["control"] == 0x36]:
        require(request["body"][:2] == b"\x09\x01" and len(request["body"]) == 14,
                "Issue63 0x36 body changed")
        event = next(frame for frame in irq100 if frame["packet_index"] > request["packet_index"])
        raw = event["body"][4:16]
        require(len(raw) == 12, "Issue63 IRQ100 raw table width changed")
        manual.append({
            "request_packet": request["packet_index"],
            "relative_ms": round((request["timestamp_us"] - t0) / 1000, 3),
            "input_table_hex": request["body"][2:].hex(),
            "irq100_packet": event["packet_index"],
            "learned_table_hex": learned_table(raw.hex()),
            "physical_out_length": request["physical_length"],
            "logical_a0_length": request["logical_length"],
            "tail_nonzero_offsets": request["tail_nonzero_offsets"],
        })

    def physical_residue(frame: dict) -> tuple[tuple[int, ...], str]:
        offsets = tuple(frame["tail_nonzero_offsets"])
        return offsets, bytes(frame["payload"][offset] for offset in offsets).hex()

    fdt36_profiles = {physical_residue(frame) for frame in outbound if frame["control"] == 0x36}
    image_profiles = {physical_residue(frame) for frame in outbound if frame["control"] in (0x20, 0x22)}
    expected_profile = {((40, 41, 42, 43, 44, 45), "cbf2ca66f87f")}
    require(fdt36_profiles == image_profiles == expected_profile,
            "Issue63 physical residue profile changed")
    require(all(row["tail_nonzero_offsets"] == [40, 41, 42, 43, 44, 45] for row in manual),
            "Issue63 0x36 nonzero tail offsets changed")

    controls_after_first_fdt = [frame["control"] for frame in outbound
                                if frame["packet_index"] > outbound[0]["packet_index"]]
    require(0xA2 not in controls_after_first_fdt and 0x70 not in controls_after_first_fdt,
            "Issue63 unexpectedly has A2/0x70 restore")

    return {
        "attachment_url": "https://github.com/user-attachments/files/27089978/fingerprint.zip",
        "attachment_sha256": ISSUE63_ZIP_SHA256,
        "pcap_sha256": ISSUE63_PCAP_SHA256,
        "capture_device": "27c6:5125 (USB device descriptor in capture)",
        "firmware": "UNKNOWN (no outbound A8/version query in capture)",
        "packet_count": len(packets),
        "capture_scope": "BEGINS_MID_SESSION_WITH_0x32_AND_CONTAINS_ENROLLMENT_CYCLES; NOT_COLD_START",
        "outbound_control_counts": {f"0x{control:02x}": count for control, count in sorted(out_counts.items())},
        "inbound_control_counts": {f"0x{control:02x}": count for control, count in sorted(in_counts.items())},
        "image_sized_b0_count": len(b0_images),
        "fdt36_count": len(manual),
        "fdt36_occurrences": manual,
        "irq2_count": len(irq2),
        "post_irq2_image_command": "0x22_DATA_0100_FOR_ALL_21_OBSERVED_IRQ2_EVENTS",
        "irq100_count": len(irq100),
        "post_irq100_next_command_counts": {
            f"0x{control:02x}": count for control, count in sorted(post_irq100.items())
        },
        "irq200_count": len(irq200),
        "fdt36_physical_contract": {
            "logical_a0_length": 22,
            "physical_usb_out_length": 64,
            "nonzero_tail_offsets": [40, 41, 42, 43, 44, 45],
            "opaque_tail_hex": "cbf2ca66f87f",
            "same_profile_on_0x20_0x22": fdt36_profiles == image_profiles,
            "zero_tail_observed": False,
        },
        "restore_or_cancel_evidence": "NO_EXPLICIT_DEVICE_RESTORE_OR_CANCEL; POSITIVE_FINGER_CYCLES_ONLY; CAPTURE_ENDS_ON_IRQ200_AFTER_0x34_ACK",
        "a2_or_0x70_after_fdt": False,
        "raw_biometric_or_secret_exported": False,
    }


def cell(value: str, evidence_class: str) -> dict:
    return {"value": value, "evidence_class": evidence_class}


def build_matrix(result: dict) -> dict:
    """Build the D254 five-axis comparison without importing raw evidence."""
    issue = result["issue63"]
    wbdi = result["source_a"]["wbdi"]
    source_a = result["source_a"]
    rows = [
        ("initial FDT seed",
         cell("adadbdbda3a3b1b1a6a6b2b2; ultimate source unresolved", "TARGET_CAPTURE"),
         cell("all-zero on first run, otherwise cached current table", "THIRD_PARTY_CODE"),
         cell(source_a["fdt_initial_seed_hex"] + "; static constant", "THIRD_PARTY_CODE"),
         cell("unknown; capture begins already armed", "UNKNOWN"),
         cell(wbdi["fdt_manual_passes"][0]["seed_table_hex"] + "; base-file field strongly inferred", "OEM_LOG_CROSS_FAMILY")),
        ("FDT passes",
         cell("3 successful chained manual samples", "TARGET_CAPTURE"),
         cell("1 successful sample; at most 3 retry attempts", "THIRD_PARTY_CODE"),
         cell("2 manual steps (static then learned)", "THIRD_PARTY_CODE"),
         cell(f"{issue['fdt36_count']} runtime manual samples across enrollment cycles; cold-init count unknown", "THIRD_PARTY_CAPTURE"),
         cell("3 successful named stages 0/1/2; fixed observed orchestration", "OEM_LOG_CROSS_FAMILY")),
        ("NAV interleave",
         cell("not observed between the three target manual samples", "TARGET_CAPTURE"),
         cell("none in FDT sampler", "THIRD_PARTY_CODE"),
         cell("yes, between its two manual steps", "THIRD_PARTY_CODE"),
         cell("not present in captured mid-session scope", "THIRD_PARTY_CAPTURE"),
         cell("yes, between manual stages 0 and 1", "OEM_LOG_CROSS_FAMILY")),
        ("baseline image interleave",
         cell("0x20 no-finger/base-image occurrence before final manual sample", "TARGET_CAPTURE"),
         cell("0x20 after successful FDT sampling", "THIRD_PARTY_CODE"),
         cell("0x20 after second manual step; no third step", "THIRD_PARTY_CODE"),
         cell("14 IRQ100 events lead next to 0x20; 8 lead next to 0x32 re-arm", "THIRD_PARTY_CAPTURE"),
         cell("0x20 baseline image between manual stages 1 and 2", "OEM_LOG_CROSS_FAMILY")),
        ("post-IRQ2 image command",
         cell("0x22 [01 00]", "TARGET_CAPTURE"),
         cell("0x20 [01 00]", "THIRD_PARTY_CODE"),
         cell("0x20 path; no captured IRQ2", "THIRD_PARTY_CODE"),
         cell("0x22 [01 00] after all 21 observed IRQ2 events", "THIRD_PARTY_CAPTURE"),
         cell("0x20 [01 00] in 5110/APP12117 flow", "OEM_LOG_CROSS_FAMILY")),
        ("finger-up lifecycle",
         cell("0x34 -> IRQ200 -> 0x20 base image -> later re-arm", "TARGET_CAPTURE"),
         cell("0x34 -> IRQ200", "THIRD_PARTY_CODE"),
         cell("not implemented in scan path", "THIRD_PARTY_CODE"),
         cell("35 outbound 0x34; 13 observed IRQ200; positive cycles", "THIRD_PARTY_CAPTURE"),
         cell("0x34/IRQ200 present on positive cycles", "OEM_LOG_CROSS_FAMILY")),
        ("explicit device cancel/restore",
         cell("none observed; failure/stop unknown", "TARGET_CAPTURE"),
         cell("host capture_stop flag only", "THIRD_PARTY_CODE"),
         cell("host state/TLS cleanup only; no mode command", "THIRD_PARTY_CODE"),
         cell("none; positive cycles only", "THIRD_PARTY_CAPTURE"),
         cell("none proven for no-finger stop", "OEM_LOG_CROSS_FAMILY")),
        ("physical 0x36 tail",
         cell("64-byte OUT; opaque residue cbf2e2befb7f at offsets 40-45; zero-tail not observed", "TARGET_CAPTURE"),
         cell("64-byte zero-padding in transport implementation", "THIRD_PARTY_CODE"),
         cell("wire physical tail not evidenced", "UNKNOWN"),
         cell("64-byte OUT; opaque residue cbf2ca66f87f at offsets 40-45; zero-tail not observed", "THIRD_PARTY_CAPTURE"),
         cell("physical USB tail unavailable in text log", "UNKNOWN")),
        ("cache/base file",
         cell("OEM goodix.dat path/OTP-prefix check observed in code; exact file unavailable", "TARGET_CAPTURE"),
         cell("OTP64+FDT12+NAV3200+IMAGE10240+CRC4 goodix.dat", "THIRD_PARTY_CODE"),
         cell("no equivalent driver cache lifecycle implemented", "THIRD_PARTY_CODE"),
         cell("not visible in mid-session capture", "UNKNOWN"),
         cell("13520-byte OTP-bound CRC cache, loaded then refreshed/saved", "OEM_LOG_CROSS_FAMILY")),
    ]
    columns = ["local_12509", "rocky_12508", "yanxinwu946_claimed_12509",
               "issue63_5125_unknown_firmware", "wbdi_5110_app12117"]
    return {
        "schema": "D254_FIVE_AXIS_COMPARISON_V1",
        "columns": columns,
        "rows": [{"property": row[0], **dict(zip(columns, row[1:]))} for row in rows],
    }


def write_matrix_csv(matrix: dict, path: Path) -> None:
    columns = matrix["columns"]
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["property", *columns])
        for row in matrix["rows"]:
            writer.writerow([row["property"], *[
                f"{row[column]['value']} [{row[column]['evidence_class']}]"
                for column in columns
            ]])


def audit(source_a: Path, issue63_pcap: Path, issue63_zip: Path) -> dict:
    return {
        "schema": "D254_EXTERNAL_EVIDENCE_AUDIT_V1",
        "execution_mode": "EXTERNAL_PUBLIC_READ_ONLY_AND_OFFLINE_PARSE",
        "source_a": parse_source_a(source_a),
        "issue63": parse_issue63(issue63_pcap, issue63_zip),
        "safety": {
            "local_usb_open_count": 0,
            "local_tls_handshake_count": 0,
            "local_d4_send_count": 0,
            "local_af_send_count": 0,
            "local_fdt_send_count": 0,
            "local_image_command_count": 0,
            "local_finger_interaction_count": 0,
            "local_persistent_write_family_count": 0,
        },
        "result": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-a", type=Path, required=True)
    parser.add_argument("--issue63-pcap", type=Path, required=True)
    parser.add_argument("--issue63-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--matrix-json", type=Path)
    parser.add_argument("--matrix-csv", type=Path)
    args = parser.parse_args()
    result = audit(args.source_a.resolve(), args.issue63_pcap.resolve(), args.issue63_zip.resolve())
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")
    matrix = build_matrix(result)
    if args.matrix_json:
        args.matrix_json.write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n")
    if args.matrix_csv:
        write_matrix_csv(matrix, args.matrix_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
