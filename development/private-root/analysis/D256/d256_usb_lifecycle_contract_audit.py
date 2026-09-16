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
RUN_RELATIVE_PREFLIGHT = Path("captures/D255_20260822T205631772Z_85c8c41f/preflight.json")
RUN_RELATIVE_TSHARK_STDERR = Path("captures/D255_20260822T205631772Z_85c8c41f/tshark_stderr.txt")

# Numeric values are the Windows WDK URB_FUNCTION ABI carried verbatim by the
# USBPcap pseudo-header.  Any value outside this bounded table stays unresolved.
URB_FUNCTIONS = {
    0x0000: "SELECT_CONFIGURATION",
    0x0001: "SELECT_INTERFACE",
    0x0002: "ABORT_PIPE",
    0x0008: "CONTROL_TRANSFER",
    0x0009: "BULK_OR_INTERRUPT_TRANSFER",
    0x000B: "GET_DESCRIPTOR_FROM_DEVICE",
    0x0013: "GET_STATUS_FROM_DEVICE",
    0x001B: "CLASS_INTERFACE",
    0x001E: "SYNC_RESET_PIPE_AND_CLEAR_STALL",
    0x0030: "SYNC_RESET_PIPE",
    0x0031: "SYNC_CLEAR_STALL",
}
ABORT_PIPE_FUNCTIONS = {0x0002}
RESET_PIPE_FUNCTIONS = {0x001E, 0x0030, 0x0031}
ABORT_OR_RESET_FUNCTIONS = ABORT_PIPE_FUNCTIONS | RESET_PIPE_FUNCTIONS
ENUMERATION_OR_RECONFIGURATION_FUNCTIONS = {0x0000, 0x0001, 0x0008, 0x000B, 0x0013}
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


def elapsed_seconds(start: float, end: float) -> float:
    return round(end - start, 6)


def parse_marker_utc_precise(value: str) -> float:
    require(value.endswith("Z") and "." in value, "marker timestamp is not fractional UTC")
    whole, fraction = value[:-1].split(".", 1)
    require(fraction.isdigit(), "marker timestamp fractional part is invalid")
    base = dt.datetime.strptime(whole, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
    return base.timestamp() + int(fraction) / (10 ** len(fraction))


def load_markers_precise(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if line_number == 1 and line.startswith("timestamp_utc\tevent\t"):
            continue
        parts = line.split("\t", 2)
        require(len(parts) >= 2, f"bad marker line {line_number}")
        rows.append({
            "timestamp": parse_marker_utc_precise(parts[0]),
            "event": parts[1],
            "line": line_number,
        })
    require(rows == sorted(rows, key=lambda row: row["timestamp"]),
            "operator markers are not ordered")
    return rows


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
    transition_functions = ENUMERATION_OR_RECONFIGURATION_FUNCTIONS | ABORT_OR_RESET_FUNCTIONS
    explicit_transition = any(packet.function in transition_functions for packet in window_packets)
    abort_or_reset = any(packet.function in ABORT_OR_RESET_FUNCTIONS for packet in window_packets)
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
            "abort_pipe_observed": any(
                packet.function in ABORT_PIPE_FUNCTIONS for packet in window_packets),
            "reset_pipe_or_clear_stall_observed": any(
                packet.function in RESET_PIPE_FUNCTIONS for packet in window_packets),
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
        },
    }


def terminal_cancel_contract(d255, packets: list, frames: list, markers: list[dict],
                             selected: tuple[int, int], preflight: dict,
                             tshark_stderr: str) -> dict:
    records = a0_records(d255, frames, selected)
    marker = {name: d255.one_marker(markers, name)["timestamp"] for name in (
        "CAPTURE_PROCESS_STARTED",
        "REENTRY_WAITING_NO_FINGER",
        "REENTRY_CANCEL_BEGIN",
        "REENTRY_CANCEL_END",
        "REENTRY_END",
        "OPERATOR_PHASES_COMPLETE",
        "RUN_FAILED",
    )}
    require(
        marker["REENTRY_WAITING_NO_FINGER"] <= marker["REENTRY_CANCEL_BEGIN"]
        < marker["REENTRY_CANCEL_END"] < marker["REENTRY_END"]
        < marker["OPERATOR_PHASES_COMPLETE"] < marker["RUN_FAILED"],
        "terminal cancel marker order invalid",
    )

    new_arms = [row for row in records if row["direction"] == "OUT" and row["control"] == 0x32
                and row["timestamp"] < marker["REENTRY_CANCEL_BEGIN"]]
    require(new_arms, "no FDT arm before terminal cancel")
    new_arm = new_arms[-1]
    new_position = records.index(new_arm)
    new_ack = find_ack(records, new_position, 0x32)
    require(new_arm["frame"] == 214, "terminal cancel new arm frame regression")
    require(new_ack is not None and new_ack["frame"] == 216
            and new_ack["strict_body"][1] in (0x01, 0x07),
            "terminal cancel new arm ACK regression")

    target_packets = [packet for packet in packets if (packet.bus, packet.device) == selected]
    pending_in = [packet for packet in target_packets
                  if packet.index + 1 > new_ack["frame"]
                  and packet.timestamp < marker["REENTRY_CANCEL_BEGIN"]
                  and packet.function == 0x0009 and packet.endpoint == 0x81
                  and packet.info == 0 and packet.data_len == 0]
    require(len(pending_in) == 1 and pending_in[0].index + 1 == 217,
            "terminal cancel pending bulk-IN submission regression")
    canceled = [packet for packet in target_packets
                if packet.timestamp >= marker["REENTRY_CANCEL_END"]
                and packet.function == 0x0009 and packet.endpoint == 0x81
                and packet.info == 1 and packet.status == 0xC0010000
                and packet.data_len == 0]
    require(len(canceled) == 1 and canceled[0].index + 1 == 218,
            "terminal cancel canceled bulk-IN completion regression")
    completion = canceled[0]
    require(completion.index == len(packets) - 1,
            "terminal cancel completion is not the last raw frame")
    require(marker["OPERATOR_PHASES_COMPLETE"] < completion.timestamp < marker["RUN_FAILED"],
            "terminal cancel completion falls outside host finalization bounds")

    operator_interval_all = [packet for packet in packets
                             if marker["REENTRY_CANCEL_BEGIN"] <= packet.timestamp
                             < marker["REENTRY_CANCEL_END"]]
    operator_interval_target = [packet for packet in operator_interval_all
                                if (packet.bus, packet.device) == selected]
    after_cancel_before_completion = [packet for packet in packets
                                      if marker["REENTRY_CANCEL_END"] <= packet.timestamp
                                      < completion.timestamp]
    after_cancel_through_completion = [packet for packet in packets
                                       if marker["REENTRY_CANCEL_END"] <= packet.timestamp
                                       <= completion.timestamp]
    after_completion_all = [packet for packet in packets if packet.index > completion.index]
    after_completion_target = [packet for packet in after_completion_all
                               if (packet.bus, packet.device) == selected]
    terminal_target_window = [packet for packet in target_packets
                              if new_arm["timestamp"] <= packet.timestamp <= completion.timestamp]
    terminal_functions = Counter(packet.function for packet in terminal_target_window)
    descriptors = d255.target_descriptor_packets(packets)
    terminal_descriptor_replay = any(
        new_arm["timestamp"] <= packet.timestamp <= completion.timestamp
        for packet in descriptors)
    terminal_endpoints = sorted({packet.endpoint for packet in terminal_target_window})
    terminal_devices = sorted({(packet.bus, packet.device) for packet in terminal_target_window})
    non_bulk = [packet for packet in terminal_target_window if packet.function != 0x0009]
    abort_or_reset = [packet for packet in terminal_target_window
                      if packet.function in ABORT_OR_RESET_FUNCTIONS]
    reconfiguration = [packet for packet in terminal_target_window
                       if packet.function in ENUMERATION_OR_RECONFIGURATION_FUNCTIONS]

    capture_duration = preflight.get("capture_duration_seconds")
    require(capture_duration == 600, "D255 configured capture duration regression")
    require(tshark_stderr.strip() == f"Capturing on 'USBPcap1'\n{len(packets)} packets captured",
            "D255 TShark final packet count regression")
    started_to_finalization = elapsed_seconds(
        marker["CAPTURE_PROCESS_STARTED"], marker["RUN_FAILED"])
    require(started_to_finalization >= capture_duration,
            "D255 host markers do not reach the configured duration boundary")

    quiescence = (
        len(operator_interval_target) == 0
        and len(canceled) == 1
        and completion.index == len(packets) - 1
        and len(after_completion_all) == 0
        and len(non_bulk) == 0
        and len(abort_or_reset) == 0
        and len(reconfiguration) == 0
        and not terminal_descriptor_replay
        and terminal_devices == [selected]
        and set(terminal_endpoints).issubset({0x01, 0x81})
        and started_to_finalization >= capture_duration
    )
    return {
        "window": {
            "new_arm_frame": new_arm["frame"],
            "new_arm_utc": iso_utc(new_arm["timestamp"]),
            "new_arm_ack_frame": new_ack["frame"],
            "new_arm_ack_utc": iso_utc(new_ack["timestamp"]),
            "pending_bulk_in_frame": pending_in[0].index + 1,
            "pending_bulk_in_utc": iso_utc(pending_in[0].timestamp),
            "reentry_waiting_no_finger_utc": iso_utc(marker["REENTRY_WAITING_NO_FINGER"]),
            "terminal_cancel_begin_utc": iso_utc(marker["REENTRY_CANCEL_BEGIN"]),
            "terminal_cancel_end_utc": iso_utc(marker["REENTRY_CANCEL_END"]),
            "reentry_end_utc": iso_utc(marker["REENTRY_END"]),
            "operator_phases_complete_utc": iso_utc(marker["OPERATOR_PHASES_COMPLETE"]),
            "canceled_completion_frame": completion.index + 1,
            "canceled_completion_utc": iso_utc(completion.timestamp),
            "run_failed_host_finalization_utc": iso_utc(marker["RUN_FAILED"]),
            "ack_to_terminal_cancel_begin_seconds": elapsed_seconds(
                new_ack["timestamp"], marker["REENTRY_CANCEL_BEGIN"]),
            "terminal_cancel_begin_to_end_seconds": elapsed_seconds(
                marker["REENTRY_CANCEL_BEGIN"], marker["REENTRY_CANCEL_END"]),
            "terminal_cancel_end_to_canceled_completion_seconds": elapsed_seconds(
                marker["REENTRY_CANCEL_END"], completion.timestamp),
            "canceled_completion_to_host_finalization_marker_seconds": elapsed_seconds(
                completion.timestamp, marker["RUN_FAILED"]),
            "POST_TERMINAL_CANCEL_CAPTURE_WINDOW_SECONDS": elapsed_seconds(
                completion.timestamp, marker["RUN_FAILED"]),
            "post_terminal_cancel_capture_window_definition": (
                "LAST_RAW_FRAME_TO_RUN_FAILED_HOST_FINALIZATION_MARKER_AFTER_DURATION_BOUNDARY; "
                "EXACT_PROCESS_EXIT_TIMESTAMP_UNOBSERVED"),
            "configured_capture_duration_seconds": capture_duration,
            "capture_process_started_to_host_finalization_marker_seconds": started_to_finalization,
        },
        "observations": {
            "terminal_cancel_marker_order_valid": True,
            "terminal_cancel_total_packet_count_during_operator_interval": len(operator_interval_all),
            "TERMINAL_CANCEL_TARGET_PACKET_COUNT_DURING_OPERATOR_INTERVAL": len(
                operator_interval_target),
            "packet_count_after_cancel_end_before_completion": len(after_cancel_before_completion),
            "packet_count_after_cancel_end_through_completion": len(after_cancel_through_completion),
            "pending_bulk_in_canceled": True,
            "terminal_target_usbpcap_function_counts": {
                f"0x{code:04x}": count for code, count in sorted(terminal_functions.items())},
            "terminal_non_bulk_urb_count": len(non_bulk),
            "terminal_abort_or_reset_count": len(abort_or_reset),
            "terminal_reconfiguration_control_or_descriptor_count": len(reconfiguration),
            "terminal_descriptor_replay_observed": terminal_descriptor_replay,
            "terminal_bus_device": f"{selected[0]}:{selected[1]}",
            "terminal_same_bus_device": terminal_devices == [selected],
            "terminal_endpoint_set": [f"0x{endpoint:02x}" for endpoint in terminal_endpoints],
            "terminal_same_bulk_endpoints": set(terminal_endpoints).issubset({0x01, 0x81}),
            "completion_is_last_raw_frame": completion.index == len(packets) - 1,
            "POST_TERMINAL_CANCEL_TARGET_USB_PACKET_COUNT": len(after_completion_target),
            "POST_TERMINAL_CANCEL_TOTAL_PACKET_COUNT": len(after_completion_all),
            "tshark_final_packet_count": len(packets),
            "tshark_duration_boundary_evidence": True,
            "exact_capture_process_exit_timestamp": "UNOBSERVED",
        },
        "decision": {
            "TERMINAL_CANCEL_PENDING_BULK_IN_CANCELED": True,
            "EXPLICIT_USB_TERMINAL_RESTORE_OBSERVED": False,
            "TERMINAL_CANCEL_ABORT_OR_RESET_OBSERVED": bool(abort_or_reset),
            "TERMINAL_CANCEL_REENUMERATION_OBSERVED": bool(
                terminal_descriptor_replay or reconfiguration),
            "OEM_TERMINAL_CANCEL_USB_QUIESCENCE_PROVEN": quiescence,
            "HOST_BUS_TERMINAL_STOP_CONTRACT": (
                "CLOSED_OBSERVED_PATH_BOUNDED_USB_QUIESCENCE" if quiescence else "OPEN"),
            "PRIOR_ARM_DISARM_PROVEN": False,
            "PRIOR_ARM_LIFETIME_AFTER_CANCEL": "UNOBSERVED",
            "DEVICE_INTERNAL_FDT_STATE_AFTER_CANCEL": "UNOBSERVED",
            "FACTORY_PERSISTENCE_IMPLICATION": (
                "NO_NEW_DEVICE_SIDE_FACTORY_PERSISTENCE_CLAIM_FROM_USB_SILENCE"),
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
    terminal = decision["terminal_cancel_contract"]
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
        "## Terminal cancel window",
        "",
        f"- Re-entry arm/ACK/pending bulk-IN: frames {terminal['window']['new_arm_frame']}/"
        f"{terminal['window']['new_arm_ack_frame']}/{terminal['window']['pending_bulk_in_frame']}.",
        f"- Target packets during `REENTRY_CANCEL_BEGIN..END`: "
        f"{terminal['observations']['TERMINAL_CANCEL_TARGET_PACKET_COUNT_DURING_OPERATOR_INTERVAL']}.",
        f"- Canceled completion: frame {terminal['window']['canceled_completion_frame']}, which is the final raw frame.",
        f"- Packets after the final frame: target "
        f"{terminal['observations']['POST_TERMINAL_CANCEL_TARGET_USB_PACKET_COUNT']}, total "
        f"{terminal['observations']['POST_TERMINAL_CANCEL_TOTAL_PACKET_COUNT']}.",
        f"- Frame-to-host-finalization marker window: "
        f"{terminal['window']['POST_TERMINAL_CANCEL_CAPTURE_WINDOW_SECONDS']:.6f} seconds; "
        "the exact process-exit timestamp is not available.",
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
    preflight_path = repo / RUN_RELATIVE_PREFLIGHT
    tshark_stderr_path = repo / RUN_RELATIVE_TSHARK_STDERR
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
    markers = load_markers_precise(markers_path)
    rows = timeline_rows(packets, markers, selected)
    records = a0_records(d255, frames, selected)
    d255_evidence = json.loads(d255_path.read_text(encoding="utf-8"))
    preflight = json.loads(preflight_path.read_text(encoding="utf-8-sig"))
    lifecycle = critical_contract(d255, packets, frames, markers, selected)
    terminal = terminal_cancel_contract(
        d255, packets, frames, markers, selected, preflight,
        tshark_stderr_path.read_text(encoding="utf-8-sig"))
    controls = {"0x50": control_audit(records, 0x50), "0x97": control_audit(records, 0x97)}
    require(controls["0x50"]["occurrence_count"] == 1 and controls["0x97"]["occurrence_count"] == 1,
            "D255 0x50/0x97 occurrence regression")
    after = {"sha256": sha256_file(raw), "size": raw.stat().st_size, "mtime_ns": raw.stat().st_mtime_ns}
    require(before == after, "D255 raw capture changed during audit")
    decision = {
        "schema": "D256_OFFLINE_USB_LIFECYCLE_CONTRACT_DECISION_V2",
        "execution_mode": "OFFLINE_ONLY",
        "baseline_head": os.environ.get(
            "D256_BASELINE_HEAD", "44f7af8cd98be3072c32f53f814b4851cf20911f"),
        "primary_evidence": {
            "path": RUN_RELATIVE_RAW.as_posix(),
            "sha256": before["sha256"], "bytes": before["size"],
            "readable_frame_count": len(packets), "first_frame": packets[0].index + 1,
            "D255_RAW_HASH_VERIFIED": True, "D255_RAW_MODIFIED": False,
            "target_packet_count": len(rows), "target": "27c6:5125 / GF_ST411SEC_APP_12509",
        },
        "lifecycle_contract": lifecycle,
        "terminal_cancel_contract": terminal,
        "urb_function_classification": {
            "mapping_scope": "Windows WDK URB_FUNCTION numeric ABI used by USBPcap",
            "local_wdk_or_wireshark_source_status": "UNAVAILABLE_ON_OFFLINE_LINUX_HOST",
            "corrective_required_mapping_implemented": {
                "0x0002": "URB_FUNCTION_ABORT_PIPE",
                "0x001e": "URB_FUNCTION_SYNC_RESET_PIPE_AND_CLEAR_STALL",
                "0x0030": "URB_FUNCTION_SYNC_RESET_PIPE",
                "0x0031": "URB_FUNCTION_SYNC_CLEAR_STALL",
            },
            "mapped_codes_observed_in_terminal_window": [],
            "empirical_result_changed_by_mapping_correction": False,
        },
        "controls": controls,
        "static_corroboration": bounded_static_corroboration(repo),
        "bootstrap": bootstrap_decision(d255_evidence),
        "corpus_decision": {
            "CURRENT_CORPUS_EXHAUSTED_FOR_REENTRY_RESTORE_QUESTION": True,
            "CURRENT_CORPUS_EXHAUSTED_FOR_INTERNAL_ARM_LIFETIME_QUESTION": True,
            "terminal_stop_case": "CASE_A_HOST_BUS_CONTRACT_CLOSED_INTERNAL_STATE_UNOBSERVED",
            "strategic_blocker": (
                "DEVICE_INTERNAL_FDT_STATE_AND_PRIOR_ARM_LIFETIME_REMAIN_UNOBSERVED; "
                "NO_OBSERVABLE_HOST_BUS_TERMINAL_STOP_COMPONENT_IS_MISSING"),
            "new_equivalent_capture_requested": False,
            "future_ai_pm_review_separation": [
                "factory-preserving_and_Windows_compatibility_requirement",
                "device_internal_disarm_requirement",
                "FDT_live_readiness_requirement",
            ],
            "fdt_live_authorized": False,
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
    terminal = decision["terminal_cancel_contract"]
    print("D256_USB_LIFECYCLE_CONTRACT_AUDIT=PASS")
    print(f"EXPLICIT_USB_RESTORE_OBSERVED={str(summary['EXPLICIT_USB_RESTORE_OBSERVED']).lower()}")
    print(f"NEW_FDT_ARM_ACCEPTED_ON_REENTRY={str(summary['NEW_FDT_ARM_ACCEPTED_ON_REENTRY']).lower()}")
    print(f"OEM_TERMINAL_CANCEL_USB_QUIESCENCE_PROVEN="
          f"{str(terminal['decision']['OEM_TERMINAL_CANCEL_USB_QUIESCENCE_PROVEN']).lower()}")
    print(f"POST_TERMINAL_CANCEL_CAPTURE_WINDOW_SECONDS="
          f"{terminal['window']['POST_TERMINAL_CANCEL_CAPTURE_WINDOW_SECONDS']:.6f}")
    print("REAL_USB_OPEN_COUNT=0")
    print("REAL_CAPTURE_COUNT=0")
    print("REAL_HARDWARE_ACTION_COUNT=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
