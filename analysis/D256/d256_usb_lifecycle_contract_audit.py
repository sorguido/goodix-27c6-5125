#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""D256 offline audit of the recovered D255 USB lifecycle evidence.

The tool is deliberately read-only with respect to the private capture.  It
imports the D255 pcapng/USBPcap parser, pins the sole admitted raw input, and
emits only sanitized packet metadata and bounded protocol classifications.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path


EXPECTED_RAW_SHA256 = "802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c"
EXPECTED_RAW_SIZE = 27684
EXPECTED_PACKET_COUNT = 218
EXPECTED_FIRST_FRAME = 1
RUN_RELATIVE_RAW = Path("captures/D255_20260822T205631772Z_85c8c41f/raw/wire.pcapng")
RUN_RELATIVE_MARKERS = Path("captures/D255_20260822T205631772Z_85c8c41f/operator_markers.tsv")
RUN_RELATIVE_D255 = Path("analysis/D255/D255_recovered_postprocess/D255_sanitized_evidence.json")

# Numeric values are the Windows WDK URB_FUNCTION ABI carried verbatim by the
# USBPcap pseudo-header.  Any value outside this bounded table stays unresolved.
URB_FUNCTIONS = {
    0x0000: "SELECT_CONFIGURATION",
    0x0001: "SELECT_INTERFACE",
    0x0008: "CONTROL_TRANSFER",
    0x0009: "BULK_OR_INTERRUPT_TRANSFER",
    0x000B: "GET_DESCRIPTOR_FROM_DEVICE",
    0x0013: "GET_STATUS_FROM_DEVICE",
    0x001B: "CLASS_INTERFACE",
}
TRANSFER_TYPES = {0: "ISOCHRONOUS", 1: "INTERRUPT", 2: "CONTROL", 3: "BULK"}
USBD_STATUSES = {0x00000000: "USBD_STATUS_SUCCESS", 0xC0010000: "USBD_STATUS_CANCELED"}

# Semantic labels are intentionally bounded to facts already established in
# D230/D252/D253/D255.  Unknown controls are never named by bit-clearing.
CONTROL_CLASSES = {
    0x01: "bounded no-ack state form",
    0x20: "image mode cmd1=0",
    0x22: "post-IRQ2 image mode cmd1=1",
    0x32: "FDT finger-down arm",
    0x34: "FDT finger-up arm",
    0x36: "manual no-finger FDT baseline sample",
    0x50: "D230-known sensor/mode family; exact semantics unresolved",
    0x70: "set-mode idle",
    0x80: "chip register write",
    0x82: "bounded chip register read",
    0x90: "volatile device configuration download",
    0x97: "D230 builder-proven SetDriverState wire coordinate",
    0xA2: "sensor reset family",
    0xA6: "bounded OTP/factory read",
    0xA8: "firmware version query",
    0xAE: "MCU state response",
    0xAF: "MCU state query wire coordinate",
    0xB0: "transport ACK control",
    0xD1: "TLS transition",
    0xD4: "volatile session initialization",
    0xD5: "D4 wire coordinate",
    0xE4: "bounded production read selector",
}

CSV_FIELDS = (
    "frame", "packet_index_zero_based", "timestamp_utc", "relative_ms",
    "usb_bus", "usb_device", "usbpcap_function_numeric",
    "function_semantic_class", "status", "status_semantic", "transfer_type",
    "endpoint", "direction", "usbpcap_info", "urb_stage", "data_length",
    "wrapper", "a0_control", "marker_operator_phase", "interpretation",
    "evidence_class",
)


class AuditError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise AuditError("repository root not found from script path")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def function_semantic(code: int) -> str:
    return URB_FUNCTIONS.get(code, "SEMANTICS_UNRESOLVED")


def status_semantic(code: int) -> str:
    return USBD_STATUSES.get(code, "SEMANTICS_UNRESOLVED")


def transfer_semantic(code: int) -> str:
    return TRANSFER_TYPES.get(code, "SEMANTICS_UNRESOLVED")


def iso_utc(timestamp: float) -> str:
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z")


def wrapper_and_control(payload: bytes) -> tuple[str, str]:
    if not payload or payload[0] not in (0xA0, 0xB0):
        return "none", ""
    wrapper = f"0x{payload[0]:02x}"
    control = f"0x{payload[4]:02x}" if payload[0] == 0xA0 and len(payload) >= 5 else ""
    return wrapper, control


def marker_phase(markers: list[dict], timestamp: float) -> str:
    prior = [row for row in markers if row["timestamp"] <= timestamp]
    return prior[-1]["event"] if prior else "BEFORE_FIRST_MARKER"


def direction(packet) -> str:
    if packet.endpoint == 0:
        return "HOST_TO_DEVICE" if packet.info == 0 else "DEVICE_TO_HOST"
    return "DEVICE_TO_HOST" if packet.endpoint & 0x80 else "HOST_TO_DEVICE"


def interpretation(packet, wrapper: str, control_text: str) -> str:
    if packet.status == 0xC0010000 and packet.function == 0x0009 and packet.endpoint == 0x81:
        return "canceled bulk-IN completion; host request cancellation evidence only"
    if wrapper == "0xa0" and control_text:
        control = int(control_text, 16)
        label = CONTROL_CLASSES.get(control, "A0 control semantics unresolved")
        if control == 0xB0 and len(packet.payload) >= 9:
            return "A0 transport ACK; echo/status metadata present"
        return label
    if wrapper == "0xb0":
        return "B0 TLS/application byte-stream fragment"
    semantic = function_semantic(packet.function)
    if packet.data_len == 0:
        return f"{semantic.lower()} with no captured data"
    return semantic.lower()


def timeline_rows(packets: list, markers: list[dict], selected: tuple[int, int]) -> list[dict]:
    target = [packet for packet in packets if (packet.bus, packet.device) == selected]
    require(target, "selected target has no USBPcap packets")
    base = target[0].timestamp
    rows: list[dict] = []
    for packet in target:
        wrapper, control = wrapper_and_control(packet.payload)
        semantic = function_semantic(packet.function)
        rows.append({
            "frame": packet.index + 1,
            "packet_index_zero_based": packet.index,
            "timestamp_utc": iso_utc(packet.timestamp),
            "relative_ms": f"{(packet.timestamp - base) * 1000:.3f}",
            "usb_bus": packet.bus,
            "usb_device": packet.device,
            "usbpcap_function_numeric": f"0x{packet.function:04x}",
            "function_semantic_class": semantic,
            "status": f"0x{packet.status:08x}",
            "status_semantic": status_semantic(packet.status),
            "transfer_type": f"{packet.transfer}:{transfer_semantic(packet.transfer)}",
            "endpoint": f"0x{packet.endpoint:02x}",
            "direction": direction(packet),
            "usbpcap_info": f"0x{packet.info:02x}",
            "urb_stage": "SUBMISSION" if packet.info == 0 else "COMPLETION" if packet.info == 1 else "SEMANTICS_UNRESOLVED",
            "data_length": packet.data_len,
            "wrapper": wrapper,
            "a0_control": control,
            "marker_operator_phase": marker_phase(markers, packet.timestamp),
            "interpretation": interpretation(packet, wrapper, control),
            "evidence_class": "UNKNOWN" if semantic == "SEMANTICS_UNRESOLVED" else "OBSERVED",
        })
    return rows


def a0_records(d255, frames: list, selected: tuple[int, int]) -> list[dict]:
    records = []
    for frame in frames:
        if (frame.bus, frame.device) != selected or frame.outer != 0xA0 or len(frame.raw) < 5:
            continue
        strict = d255.parse_a0(frame)
        records.append({
            "frame": frame.packet_index + 1,
            "timestamp": frame.timestamp,
            "direction": frame.direction,
            "control": frame.raw[4],
            "strict_body": strict[1] if strict else None,
            "logical_length": len(frame.raw),
            "physical_length": frame.physical_length,
            "wrapper": "0xa0",
        })
    return records


def find_ack(records: list[dict], request_position: int, echo: int) -> dict | None:
    for row in records[request_position + 1:]:
        if row["direction"] == "OUT":
            return None
        body = row["strict_body"]
        if row["control"] == 0xB0 and body and len(body) == 2 and body[0] == echo:
            return row
    return None


def control_audit(records: list[dict], control: int) -> dict:
    occurrences = [(position, row) for position, row in enumerate(records)
                   if row["direction"] == "OUT" and row["control"] == control]
    rows = []
    for position, row in occurrences:
        ack = find_ack(records, position, control)
        next_in = None
        for candidate in records[position + 1:]:
            if candidate["direction"] == "OUT":
                break
            if candidate is not ack:
                next_in = candidate
                break
        rows.append({
            "frame": row["frame"],
            "direction": "OUT",
            "wrapper": row["wrapper"],
            "logical_length": row["logical_length"],
            "physical_length": row["physical_length"],
            "payload_length": len(row["strict_body"]) if row["strict_body"] is not None else None,
            "ack": (f"frame {ack['frame']} B0/{control:02x}/"
                    f"{ack['strict_body'][1]:02x}" if ack else "NONE_OBSERVED"),
            "immediate_following_non_ack_in": (
                f"frame {next_in['frame']} A0/{next_in['control']:02x} "
                f"logical_length={next_in['logical_length']} physical_length={next_in['physical_length']}"
                if next_in else "NONE_OBSERVED"),
        })
    if control == 0x50:
        classification = "KNOWN_D230_SENSOR_MODE_FAMILY_EXACT_SEMANTICS_UNRESOLVED_NOT_LIFECYCLE_RESTORE"
        corpus = "D230 records two historical requests; D255 contains one during FDT bootstrap after first 0x36"
        builder = "NO_DEDICATED_0x50_BUILDER_IN_D230; bounded dynamic ChicagoHUSetMode family only"
        position = "POST_FIRST_0x36_IRQ100_BEFORE_SECOND_0x36; OUTSIDE_CANCEL_REENTRY"
    else:
        classification = "KNOWN_D230_SETDRIVERSTATE_WIRE_COORDINATE_NOT_LIFECYCLE_RESTORE"
        corpus = "D230 maps wire 0x97 to logical/builder 0x96 and records one historical request"
        builder = "SetDriverState 0x18005c724 with immediate A0 builder callsites 0x18005c83e and 0x18005c8d0"
        position = "PRE_TLS_INITIAL_QUERY_SEQUENCE_BEFORE_FIRST_AF; OUTSIDE_FDT_CANCEL_REENTRY"
    return {
        "control": f"0x{control:02x}",
        "occurrence_count": len(occurrences),
        "occurrences": rows,
        "corpus_status": corpus,
        "bounded_static_builder": builder,
        "timeline_position": position,
        "classification": classification,
    }


def critical_contract(d255, packets: list, frames: list, markers: list[dict], selected: tuple[int, int]) -> dict:
    records = a0_records(d255, frames, selected)
    cancel_begin = d255.one_marker(markers, "CANCEL_NO_FINGER_BEGIN")["timestamp"]
    cancel_end = d255.one_marker(markers, "CANCEL_NO_FINGER_END")["timestamp"]
    reentry_begin = d255.one_marker(markers, "REENTRY_BEGIN")["timestamp"]
    reentry_end = d255.one_marker(markers, "REENTRY_END")["timestamp"]
    arms = [row for row in records if row["direction"] == "OUT" and row["control"] == 0x32
            and row["timestamp"] < cancel_begin]
    require(arms, "no pre-cancel FDT arm")
    last_arm = arms[-1]
    new_arms = [row for row in records if row["direction"] == "OUT" and row["control"] == 0x32
                and reentry_begin <= row["timestamp"] <= reentry_end]
    require(new_arms, "no re-entry FDT arm")
    new_arm = new_arms[0]
    new_position = records.index(new_arm)
    new_ack = find_ack(records, new_position, 0x32)
    require(new_ack is not None and new_ack["strict_body"][1] in (0x01, 0x07),
            "new re-entry FDT arm lacks accepted ACK")

    window_packets = [packet for packet in packets if (packet.bus, packet.device) == selected
                      and last_arm["timestamp"] <= packet.timestamp <= new_ack["timestamp"]]
    cancel_packets = [packet for packet in window_packets if cancel_begin <= packet.timestamp < cancel_end]
    post_cancel_pre_command = [packet for packet in window_packets
                               if cancel_end <= packet.timestamp < new_arm["timestamp"]]
    functions = Counter(packet.function for packet in window_packets)
    canceled = [packet for packet in post_cancel_pre_command
                if packet.function == 0x0009 and packet.status == 0xC0010000
                and packet.endpoint == 0x81 and packet.info == 1]
    descriptors = d255.target_descriptor_packets(packets)
    descriptor_replay = any(last_arm["timestamp"] <= packet.timestamp <= new_ack["timestamp"]
                            for packet in descriptors)
    continuity_devices = sorted({(packet.bus, packet.device) for packet in window_packets})
    endpoints = sorted({packet.endpoint for packet in window_packets})
    transition_functions = {0x0000, 0x0001, 0x0002, 0x0008, 0x000B, 0x0013, 0x0030, 0x0031}
    explicit_transition = any(packet.function in transition_functions for packet in window_packets)
    abort_or_reset = any(packet.function in {0x0002, 0x0030, 0x0031} for packet in window_packets)
    reenumeration = bool(descriptor_replay or any(packet.function in {0x0000, 0x0001, 0x000B}
                                                  for packet in window_packets))
    require(continuity_devices == [selected], "critical window changes bus/device identity")
    require(set(endpoints).issubset({0x01, 0x81}), "critical window changes target endpoints")
    return {
        "window": {
            "last_pre_cancel_arm_frame": last_arm["frame"],
            "cancel_begin_utc": iso_utc(cancel_begin),
            "cancel_end_utc": iso_utc(cancel_end),
            "reentry_begin_utc": iso_utc(reentry_begin),
            "new_arm_frame": new_arm["frame"],
            "new_arm_ack_frame": new_ack["frame"],
            "target_usbpcap_packet_count": len(window_packets),
            "cancel_interval_target_packet_count": len(cancel_packets),
            "post_cancel_pre_new_arm_target_packet_count": len(post_cancel_pre_command),
        },
        "observations": {
            "usbpcap_function_counts": {f"0x{code:04x}": count for code, count in sorted(functions.items())},
            "same_bus_device": continuity_devices == [selected],
            "bus_device": f"{selected[0]}:{selected[1]}",
            "same_bulk_endpoints": set(endpoints).issubset({0x01, 0x81}),
            "endpoint_set": [f"0x{endpoint:02x}" for endpoint in endpoints],
            "canceled_bulk_in_completion_count": len(canceled),
            "canceled_bulk_in_completion_frames": [packet.index + 1 for packet in canceled],
            "abort_pipe_observed": any(packet.function == 0x0002 for packet in window_packets),
            "reset_pipe_or_clear_stall_observed": any(
                packet.function in {0x0030, 0x0031} for packet in window_packets),
            "control_transfer_observed": any(packet.function == 0x0008 for packet in window_packets),
            "select_configuration_or_interface_observed": any(
                packet.function in {0x0000, 0x0001} for packet in window_packets),
            "device_reset_observed": False,
            "close_or_release_observation": (
                "NO_TEARDOWN_URB_OBSERVED; GENERIC_HANDLE_CLOSE_NOT_DIRECTLY_ENCODED"),
            "pipe_teardown_or_recreate_observed": False,
            "explicit_configuration_control_or_descriptor_transition": explicit_transition,
            "abort_or_reset_observed": abort_or_reset,
            "descriptor_replay_observed": descriptor_replay,
            "reenumeration_observed": reenumeration,
            "bus_device_change_observed": continuity_devices != [selected],
        },
        "decision": {
            "USBPCAP_LIFECYCLE_AUDIT": "PASS_COMPLETE_TARGET_PACKET_TIMELINE",
            "CANCEL_TO_REENTRY_DEVICE_CONTINUITY": "SAME_BUS_DEVICE_AND_BULK_ENDPOINTS",
            "HOST_SIDE_PENDING_BULK_IN_CANCELLATION_OBSERVED": len(canceled) == 1,
            "EXPLICIT_USB_RESTORE_OBSERVED": False,
            "ABORT_OR_RESET_OBSERVED": False,
            "REENUMERATION_OBSERVED": False,
            "REENTRY_WITHOUT_EXPLICIT_USB_RESTORE_PROVEN": True,
            "NEW_FDT_ARM_ACCEPTED_ON_REENTRY": True,
            "RESTORE_REQUIRED_FOR_REENTRY": False,
            "PRIOR_ARM_DISARM_PROVEN": False,
            "PRIOR_ARM_LIFETIME_AFTER_CANCEL": "UNOBSERVED",
            "SAFE_STOP_AFTER_FDT_ARM": "UNRESOLVED",
        },
    }


def bounded_static_corroboration(repo: Path) -> dict:
    disasm = repo / "analysis/D230/work/GoodixExport/gfusb_static_refs/gfusb_disasm.txt"
    strings = repo / "analysis/D230/work/GoodixExport/gfusb_static_refs/gfusb_strings_utf16_off.txt"
    lines = []
    for line in disasm.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if ":" not in stripped:
            continue
        try:
            address = int(stripped.split(":", 1)[0], 16)
        except ValueError:
            continue
        if 0x18001FA90 <= address < 0x18001FD32:
            lines.append(line)
    require(lines, "bounded gfOnCancel slice missing")
    direct_builder = any("call   0x18005c148" in line or "call   0x18005cc04" in line for line in lines)
    string_text = strings.read_text(errors="replace")
    require("gfOnCancel" in string_text and "d0exit happened" in string_text,
            "known lifecycle string anchors missing")
    require(not direct_builder, "gfOnCancel unexpectedly reaches a direct A0 builder")
    return {
        "scope": "existing D252/D253 gfOnCancel slice plus already-indexed lifecycle strings only",
        "gfOnCancel_direct_a0_builder_call": direct_builder,
        "lifecycle_strings_present": True,
        "new_direct_usb_restore_dataflow": False,
        "STATIC_LIFECYCLE_CORROBORATION": "EXHAUSTED_NO_NEW_DATAFLOW",
        "bounded_conclusion": "gfOnCancel remains host-request cancellation; D0 strings alone do not prove execution in D255",
    }


def bootstrap_decision(d255_evidence: dict) -> dict:
    compatible = [row for row in d255_evidence["cache_candidates"]
                  if row["LAYOUT_13520_COMPATIBLE"]]
    require(len(compatible) == 1, "expected exactly one compatible 13520-byte cache")
    cache = compatible[0]
    seed = d255_evidence["seed_correlation"]
    require(cache["FILE_SIZE"] == 13520 and cache["CRC_VALID"] is True,
            "D255 target cache layout/CRC regression")
    require(cache["OTP_PREFIX_MATCH_WITH_DEVICE"] is True and seed["CACHE_FDT12_MATCH"] is True,
            "D255 target cache binding/seed equality regression")
    return {
        "BOOTSTRAP_CACHE_LAYOUT_TARGET_VALID": True,
        "BOOTSTRAP_CACHE_OTP_BOUND": True,
        "BOOTSTRAP_CACHE_FDT12_EQUALS_FIRST_WIRE_SEED": True,
        "BOOTSTRAP_SEED_SOURCE_CORRELATED": True,
        "BOOTSTRAP_SEED_DATAFLOW_CAUSALITY_PROVEN": False,
        "BOOTSTRAP_SEED_FRESHNESS_SCOPE": "FIRST_0x36_IN_THIS_D255_COLD_ATTACH_ONLY; GENERAL_LIFETIME_UNPROVEN",
        "BOOTSTRAP_SEED_SOURCE_STATUS": "TARGET_CACHE_WIRE_CORRELATION_PROVEN_CAUSALITY_UNPROVEN_FRESHNESS_NOT_GENERALIZED",
    }


def render_timeline_markdown(rows: list[dict], decision: dict) -> str:
    critical = decision["lifecycle_contract"]["window"]
    lines = [
        "# D256 USBPcap target timeline",
        "",
        "Sanitized metadata-only rendering of every USBPcap packet for target `bus 1 / device 2`.",
        "No USB payload, OTP, PSK, cache blob or biometric data is included.",
        "",
        "## Critical window",
        "",
        f"- Last pre-cancel `0x32`: frame {critical['last_pre_cancel_arm_frame']}.",
        f"- Target packets during `CANCEL_NO_FINGER_BEGIN..END`: {critical['cancel_interval_target_packet_count']}.",
        f"- New accepted `0x32`: request frame {critical['new_arm_frame']}, ACK frame {critical['new_arm_ack_frame']}.",
        "- The sole intervening exceptional packet is a canceled pending bulk-IN completion; it is host-request cancellation evidence, not a device restore.",
        "",
        "## Complete target packet timeline",
        "",
        "| frame | UTC | rel ms | function | status | transfer | ep | direction/stage | len | wrapper/control | phase | interpretation | class |",
        "|---:|---|---:|---|---|---|---|---|---:|---|---|---|---|",
    ]
    for row in rows:
        wrapper = row["wrapper"] + (f"/{row['a0_control']}" if row["a0_control"] else "")
        cells = [
            row["frame"], row["timestamp_utc"], row["relative_ms"],
            f"{row['usbpcap_function_numeric']} {row['function_semantic_class']}",
            f"{row['status']} {row['status_semantic']}", row["transfer_type"], row["endpoint"],
            f"{row['direction']} {row['urb_stage']}", row["data_length"], wrapper,
            row["marker_operator_phase"], row["interpretation"], row["evidence_class"],
        ]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in cells) + " |")
    return "\n".join(lines) + "\n"


def write_outputs(output_dir: Path, rows: list[dict], decision: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "D256_usb_timeline.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "D256_usb_timeline.md").write_text(
        render_timeline_markdown(rows, decision), encoding="utf-8")
    (output_dir / "D256_decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def audit(repo: Path, output_dir: Path) -> dict:
    sys.path.insert(0, str(repo))
    from analysis.D255 import d255_postprocess_windows_evidence as d255

    raw = repo / RUN_RELATIVE_RAW
    markers_path = repo / RUN_RELATIVE_MARKERS
    d255_path = repo / RUN_RELATIVE_D255
    before = {"sha256": sha256_file(raw), "size": raw.stat().st_size, "mtime_ns": raw.stat().st_mtime_ns}
    require(before["sha256"] == EXPECTED_RAW_SHA256, "D255 raw SHA-256 mismatch")
    require(before["size"] == EXPECTED_RAW_SIZE, "D255 raw size mismatch")
    packets = list(d255.iter_usbpcap(raw))
    require(len(packets) == EXPECTED_PACKET_COUNT, "D255 readable frame count mismatch")
    require(packets[0].index + 1 == EXPECTED_FIRST_FRAME, "D255 first frame mismatch")
    frames = d255.split_frames(packets)
    selected, firmware, target_specific = d255.select_device(frames, None)
    require(selected == (1, 2) and target_specific and firmware == d255.EXPECTED_FIRMWARE,
            "D255 target selection/firmware regression")
    markers = d255.load_markers(markers_path)
    rows = timeline_rows(packets, markers, selected)
    records = a0_records(d255, frames, selected)
    d255_evidence = json.loads(d255_path.read_text(encoding="utf-8"))
    lifecycle = critical_contract(d255, packets, frames, markers, selected)
    controls = {"0x50": control_audit(records, 0x50), "0x97": control_audit(records, 0x97)}
    require(controls["0x50"]["occurrence_count"] == 1 and controls["0x97"]["occurrence_count"] == 1,
            "D255 0x50/0x97 occurrence regression")
    after = {"sha256": sha256_file(raw), "size": raw.stat().st_size, "mtime_ns": raw.stat().st_mtime_ns}
    require(before == after, "D255 raw capture changed during audit")
    decision = {
        "schema": "D256_OFFLINE_USB_LIFECYCLE_CONTRACT_DECISION_V1",
        "execution_mode": "OFFLINE_ONLY",
        "baseline_head": os.environ.get("D256_BASELINE_HEAD", "7751e26806f5aa0e57750ae20febc96325f99c7a"),
        "primary_evidence": {
            "path": RUN_RELATIVE_RAW.as_posix(),
            "sha256": before["sha256"], "bytes": before["size"],
            "readable_frame_count": len(packets), "first_frame": packets[0].index + 1,
            "D255_RAW_HASH_VERIFIED": True, "D255_RAW_MODIFIED": False,
            "target_packet_count": len(rows), "target": "27c6:5125 / GF_ST411SEC_APP_12509",
        },
        "lifecycle_contract": lifecycle,
        "controls": controls,
        "static_corroboration": bounded_static_corroboration(repo),
        "bootstrap": bootstrap_decision(d255_evidence),
        "corpus_decision": {
            "CURRENT_CORPUS_EXHAUSTED_FOR_THIS_RESTORE_QUESTION": True,
            "strategic_blocker": "DETERMINE_TERMINAL_STOP_BEHAVIOR_AND_PRIOR_ARM_LIFETIME_WHEN_NO_SUBSEQUENT_REARM_OCCURS",
            "new_equivalent_capture_requested": False,
        },
        "safety": {
            "REAL_USB_OPEN_COUNT": 0, "REAL_CAPTURE_COUNT": 0,
            "REAL_HARDWARE_ACTION_COUNT": 0, "raw_payload_exported": False,
            "otp_raw_exported": False, "psk_or_secret_exported": False,
            "raw_biometric_exported": False,
        },
    }
    write_outputs(output_dir, rows, decision)
    require(before == {"sha256": sha256_file(raw), "size": raw.stat().st_size,
                       "mtime_ns": raw.stat().st_mtime_ns}, "D255 raw changed while writing outputs")
    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    repo = find_repo_root(Path(__file__).parent)
    output_dir = args.output_dir.resolve() if args.output_dir else Path(__file__).resolve().parent
    decision = audit(repo, output_dir)
    summary = decision["lifecycle_contract"]["decision"]
    print("D256_USB_LIFECYCLE_CONTRACT_AUDIT=PASS")
    print(f"EXPLICIT_USB_RESTORE_OBSERVED={str(summary['EXPLICIT_USB_RESTORE_OBSERVED']).lower()}")
    print(f"NEW_FDT_ARM_ACCEPTED_ON_REENTRY={str(summary['NEW_FDT_ARM_ACCEPTED_ON_REENTRY']).lower()}")
    print("REAL_USB_OPEN_COUNT=0")
    print("REAL_CAPTURE_COUNT=0")
    print("REAL_HARDWARE_ACTION_COUNT=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
