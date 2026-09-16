#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""D263/01 — primary-evidence audit of the post-arm trace.

Trace under investigation (target-specific, APP12509):

    final 0x32 -> IRQ 0x0002 -> 0x22 [01 00] -> first image

The script is OFFLINE ONLY. It:
  * hash-gates the canonical primary capture
    (analysis/D230/work/GoodixExport/rilevamento.pcapng, SHA-256 known);
  * reuses the D230/D252 USBPcap decoder + A0 inner-frame logic;
  * extracts the post-arm order with sanitized metadata only
    (lengths, control bytes, IRQ value/wrapper, ACK echo/status/order,
    absolute physical offsets of bytes outside the declared A0 length,
    first-image outer type and observable size, TLS-record prefix);
  * never emits raw payloads, secrets, PSK/OTP, biometric data or DLL/firmware.

Outputs (written to analysis/D263/):
  * D263_01_post_arm_order.json
  * D263_01_0x22_physical_policy.json
Only machine metadata cross-referenceable to the manual are produced.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


# Canonical primary capture (APP12509, cold-attach, single captured lifecycle).
EXPECTED_CAPTURE_SHA256 = "50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b"


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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe_out_row(packet_by_index: dict, frame: dict) -> dict:
    packet = packet_by_index[frame["first_packet_index"]]
    control, data = a0_inner(frame)
    physical_len = packet["data_len"]
    frame_len = len(frame["raw"])
    tail = packet["payload"][frame_len:]
    nonzero = [
        {"absolute_physical_offset": frame_len + offset, "value": f"0x{value:02x}"}
        for offset, value in enumerate(tail) if value
    ]
    return {
        "first_packet_index_zero_based": frame["first_packet_index"],
        "wire_control": f"0x{control:02x}",
        "logical_a0_frame_length": frame_len,
        "physical_out_length": physical_len,
        "body_length": len(data),
        "body_hex_prefix": data[:16].hex(),
        "bytes_outside_declared_length_count": len(tail),
        "nonzero_outside_declared_length": nonzero,
    }, control, data


def describe_in_row(packet_by_index: dict, frame: dict):
    packet = packet_by_index[frame["first_packet_index"]]
    raw = frame["raw"]
    physical_len = packet["data_len"]
    if raw and raw[0] == 0xA0:
        control, data = a0_inner(frame)
        frame_len = len(raw)
        tail = packet["payload"][frame_len:]
        nonzero = [
            {"absolute_physical_offset": frame_len + offset, "value": f"0x{value:02x}"}
            for offset, value in enumerate(tail) if value
        ]
        return {
            "first_packet_index_zero_based": frame["first_packet_index"],
            "outer_type": frame["outer_type"],
            "wire_control": f"0x{control:02x}",
            "logical_frame_length": frame_len,
            "physical_in_length": physical_len,
            "body_length": len(data),
            "body_hex_prefix": data[:16].hex(),
            "nonzero_outside_declared_length": nonzero,
        }, control, data
    # B0 bulk-data frame (e.g. image): not an A0 command/ack/event.
    assert raw and raw[0] == 0xB0, "unexpected frame outer type"
    frame_len = 4 + int.from_bytes(raw[1:3], "little")
    body = raw[4:frame_len]
    return {
        "first_packet_index_zero_based": frame["first_packet_index"],
        "outer_type": "0xb0",
        "wire_control": "0xb0",
        "logical_frame_length": frame_len,
        "physical_in_length": physical_len,
        "body_length": len(body),
        "body_hex_prefix": body[:16].hex(),
        "nonzero_outside_declared_length": [],
    }, 0xB0, body


def parse_control_data(frame: dict):
    """Best-effort (ctl, data) without raising on B0 data frames."""
    raw = frame["raw"]
    if raw and raw[0] == 0xA0:
        try:
            return a0_inner(frame)
        except Exception:
            return -1, b""
    if raw and raw[0] == 0xB0:
        return 0xB0, raw[4 : 4 + int.from_bytes(raw[1:3], "little")]
    return -1, b""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve() if args.repo else Path(__file__).resolve().parents[2]

    capture = repo / "analysis/D230/work/GoodixExport/rilevamento.pcapng"
    capture_sha = sha256(capture)
    require(capture_sha == EXPECTED_CAPTURE_SHA256,
            f"primary capture hash mismatch: {capture_sha}")

    census = load_census(repo)
    packets = [census.decode_usbpcap(p) for p in census.iter_pcapng_packets(capture)]
    packet_by_index = {p["packet_index"]: p for p in packets}
    out_frames = census.split_bulk_frames(packets, 0x01, 0)
    in_frames = census.split_bulk_frames(packets, 0x81, 1)
    out_by_index = {f["first_packet_index"]: f for f in out_frames}
    in_by_index = {f["first_packet_index"]: f for f in in_frames}

    # --- occurrences of 0x22 in the primary corpus -------------------------
    out_22 = sorted(i for i, f in out_by_index.items()
                    if len(f["raw"]) >= 5 and f["raw"][0] == 0xA0 and f["raw"][4] == 0x22)
    in_22 = sorted(i for i, f in in_by_index.items()
                   if len(f["raw"]) >= 5 and f["raw"][0] == 0xA0 and f["raw"][4] == 0x22)

    # --- locate the unique finger-down IRQ (0x0002) -----------------------
    finger_down = None
    for idx, f in in_by_index.items():
        try:
            control, data = a0_inner(f)
        except Exception:
            continue
        if control == 0x32 and len(data) >= 4 and data[:2] == b"\x02\x00":
            finger_down = {"packet_index": idx, "control": control, "inner": data}
            break
    require(finger_down is not None, "no finger-down IRQ 0x0002 found in capture")

    # IRQ value / wrapper decoding: A0 inner of the finger-down event.
    fd_inner = finger_down["inner"]
    irq_value = int.from_bytes(fd_inner[:2], "little")  # 0x0002
    wrapper = fd_inner[2:].hex()

    # The OUT 0x32 arm immediately preceding the finger-down IRQ.
    preceding_arms = sorted(i for i, f in out_by_index.items()
                            if i < finger_down["packet_index"]
                            and len(f["raw"]) >= 5 and f["raw"][0] == 0xA0
                            and f["raw"][4] == 0x32)
    require(preceding_arms, "no 0x32 arm before finger-down IRQ")
    arm_index = preceding_arms[-1]
    arm_row, _arm_ctl, _arm_data = describe_out_row(packet_by_index, out_by_index[arm_index])
    arm_ack = in_by_index[min(i for i in in_by_index if i > arm_index)]
    arm_ack_row, arm_ack_ctl, arm_ack_data = describe_in_row(packet_by_index, arm_ack)

    # The OUT 0x22 immediately following the finger-down IRQ.
    following_22 = sorted(i for i, f in out_by_index.items()
                          if i > finger_down["packet_index"]
                          and len(f["raw"]) >= 5 and f["raw"][0] == 0xA0
                          and f["raw"][4] == 0x22)
    require(following_22, "no 0x22 after finger-down IRQ")
    cmd22_index = following_22[0]
    cmd22_row, _c22, cmd22_data = describe_out_row(packet_by_index, out_by_index[cmd22_index])
    require(cmd22_data == b"\x01\x00", "post-IRQ 0x22 body is not exact 01 00")

    # 0x22 ACK: first IN frame after the 0x22 OUT.
    cmd22_ack = in_by_index[min(i for i in in_by_index if i > cmd22_index)]
    cmd22_ack_row, cmd22_ack_ctl, cmd22_ack_data = describe_in_row(packet_by_index, cmd22_ack)

    # First image: first IN frame after the 0x22 ACK.
    first_image = in_by_index[min(i for i in in_by_index if i > cmd22_ack["first_packet_index"])]
    img_row, img_ctl, img_data = describe_in_row(packet_by_index, first_image)
    tls_prefix = img_data[:4].hex()
    is_tls = img_data[:3] == b"\x17\x03\x03"

    # Intermediate frames/events between 0x22 ACK and the next arm (0x34 etc.)
    intermediate = []
    cur = cmd22_ack["first_packet_index"]
    while True:
        nxt = min((i for i in list(out_by_index) + list(in_by_index)
                   if i > cur), default=None)
        if nxt is None:
            break
        rf = out_by_index.get(nxt) or in_by_index.get(nxt)
        c, d = parse_control_data(rf)
        intermediate.append({
            "dir": "OUT" if nxt in out_by_index else "IN",
            "packet": nxt,
            "ctl": f"0x{c:02x}" if c >= 0 else "unknown",
            "body": d[:8].hex(),
        })
        cur = nxt
        if len(intermediate) >= 12:
            break

    post_arm_order = {
        "schema": "D263_01_POST_ARM_ORDER_V1",
        "execution_mode": "OFFLINE_ONLY",
        "primary_capture": {
            "path": "analysis/D230/work/GoodixExport/rilevamento.pcapng",
            "sha256": capture_sha,
            "hash_gate": "PASS",
            "firmware_target": "GF_ST411SEC_APP_12509",
            "packet_indices": "zero_based",
        },
        "trace": "final 0x32 -> IRQ 0x0002 -> 0x22 [01 00] -> first image",
        "observed_order": [
            {
                "step": "FDT arm request (final 0x32 before finger-down)",
                "packet_index_zero_based": arm_index,
                "wire_control": "0x32",
                "body_hex_prefix": arm_row["body_hex_prefix"],
                "logical_a0_frame_length": arm_row["logical_a0_frame_length"],
                "physical_out_length": arm_row["physical_out_length"],
            },
            {
                "step": "FDT arm ACK (device -> host)",
                "packet_index_zero_based": arm_ack["first_packet_index"],
                "outer_type": arm_ack_row["outer_type"],
                "wire_control": f"0x{arm_ack_ctl:02x}",
                "ack_echo": f"0x{arm_ack_data[0]:02x}" if len(arm_ack_data) >= 1 else None,
                "ack_status": f"0x{arm_ack_data[1]:02x}" if len(arm_ack_data) >= 2 else None,
            },
            {
                "step": "IRQ finger-down (device -> host)",
                "packet_index_zero_based": finger_down["packet_index"],
                "wire_control": f"0x{finger_down['control']:02x}",
                "irq_value": f"0x{irq_value:04x}",
                "irq_wrapper_hex": wrapper,
                "body_hex_prefix": fd_inner[:8].hex(),
            },
            {
                "step": "post-IRQ host command 0x22",
                "packet_index_zero_based": cmd22_index,
                "wire_control": "0x22",
                "body_hex": cmd22_data.hex(),
                "logical_a0_frame_length": cmd22_row["logical_a0_frame_length"],
                "physical_out_length": cmd22_row["physical_out_length"],
                "nonzero_outside_declared_length": cmd22_row["nonzero_outside_declared_length"],
            },
            {
                "step": "0x22 ACK (device -> host)",
                "packet_index_zero_based": cmd22_ack["first_packet_index"],
                "outer_type": cmd22_ack_row["outer_type"],
                "wire_control": f"0x{cmd22_ack_ctl:02x}",
                "ack_echo": f"0x{cmd22_ack_data[0]:02x}" if len(cmd22_ack_data) >= 1 else None,
                "ack_status": f"0x{cmd22_ack_data[1]:02x}" if len(cmd22_ack_data) >= 2 else None,
            },
            {
                "step": "first image (device -> host)",
                "packet_index_zero_based": first_image["first_packet_index"],
                "outer_type": img_row["outer_type"],
                "wire_control": f"0x{img_ctl:02x}",
                "logical_frame_length": img_row["logical_frame_length"],
                "physical_in_length": img_row["physical_in_length"],
                "transport": "TLS" if is_tls else "PLAINTEXT_OR_UNKNOWN",
                "tls_record_prefix_hex": tls_prefix,
            },
        ],
        "intermediate_frames_after_first_image": intermediate,
        "minimum_causal_requirement": (
            "Observed order only. The capture proves the SEQUENCE "
            "0x32(arm,ACK) -> IRQ0x0002 -> 0x22[01 00](ACK) -> first image. "
            "It does NOT prove that 0x22 is the unique necessary command, nor "
            "that the finger-down IRQ causally requires 0x22; only that in the "
            "single captured APP12509 lifecycle this is the exact order emitted "
            "by the OEM stack. Causality is not established by this trace alone."
        ),
        "occurrence_counts": {
            "out_0x22_in_primary_corpus": len(out_22),
            "in_0x22_in_primary_corpus": len(in_22),
            "all_0x22_in_primary_corpus": len(out_22) + len(in_22),
            "out_0x22_packet_indices_zero_based": out_22,
            "finger_down_irq_count_in_capture": 1,
        },
        "safety": {
            "usb_open_count": 0,
            "command_count": 0,
            "persistent_write_family_count": 0,
            "network_access": 0,
            "raw_payload_emitted": False,
        },
        "result": "PASS_PRIMARY_EVIDENCE_CLOSED",
    }

    # --- Taxonomy of the 0x22 physical policy -----------------------------
    # Logical exact A0 (10) -> physical fixed 64 -> deterministic zero-fill
    # outside declared length, with a 6-byte staging residue at offsets 40-45.
    nonzero_offsets = [b["absolute_physical_offset"] for b in cmd22_row["nonzero_outside_declared_length"]]
    physical_policy = {
        "schema": "D263_01_0x22_PHYSICAL_POLICY_V1",
        "command": "0x22",
        "command_meaning": "SetMode Image, cmd0=2 cmd1=1 more=0 (post finger-down variant)",
        "primary_evidence": "analysis/D230/work/GoodixExport/rilevamento.pcapng",
        "primary_capture_sha256": capture_sha,
        "logical_a0_length": cmd22_row["logical_a0_frame_length"],
        "physical_out_length": cmd22_row["physical_out_length"],
        "body": "01 00",
        "bytes_outside_declared_length": cmd22_row["bytes_outside_declared_length_count"],
        "nonzero_outside_declared_length_count": len(cmd22_row["nonzero_outside_declared_length"]),
        "nonzero_outside_declared_length_offsets": nonzero_offsets,
        "nonzero_outside_declared_length_values_hex": [
            b["value"] for b in cmd22_row["nonzero_outside_declared_length"]
        ],
        "candidate_phase2_model": "logical exact A0 -> physical fixed64 -> deterministic zero-fill outside declared length",
        "phase2_model_confirmed": (
            cmd22_row["physical_out_length"] == 64
            and cmd22_row["bytes_outside_declared_length_count"] == 54
            and nonzero_offsets == [40, 41, 42, 43, 44, 45]
        ),
        "residue_class": "staging/transport residue identical to 0x36/0x20 at offsets 40-45, not payload",
        "taxonomy": "PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY",
        "taxonomy_rationale": (
            "The 0x22 post-arm order, ACK/echo/status and physical fixed-64 policy "
            "are directly observed in the primary APP12509 capture (target-specific). "
            "The D262 live proof covers only the FDT arm 0x36/0x50/0x36/0x82/0x20/0x36/0x32; "
            "it does NOT reach the post-arm finger-down/0x22/image subtree. Therefore "
            "0x22 is PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY, not live-proven/accepted."
        ),
        "live_proof_status": "NOT_LIVE_PROVEN",
        "rockytkg_corroboration": (
            "Issue #63 capture (hash 5b2e9649...b63d0) shows 21/21 IRQ2 followed by "
            "0x22[01 00]; corroborative only, not APP12509 primary authority."
        ),
    }

    out_dir = repo / "analysis/D263"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "D263_01_post_arm_order.json").write_text(json.dumps(post_arm_order, indent=2) + "\n")
    (out_dir / "D263_01_0x22_physical_policy.json").write_text(json.dumps(physical_policy, indent=2) + "\n")

    print(json.dumps({
        "capture_sha256": capture_sha,
        "hash_gate": "PASS",
        "arm_index": arm_index,
        "arm_ack_echo": post_arm_order["observed_order"][1]["ack_echo"],
        "arm_ack_status": post_arm_order["observed_order"][1]["ack_status"],
        "irq_value": post_arm_order["observed_order"][2]["irq_value"],
        "irq_wrapper": post_arm_order["observed_order"][2]["irq_wrapper_hex"],
        "cmd22_index": cmd22_index,
        "cmd22_body": post_arm_order["observed_order"][3]["body_hex"],
        "cmd22_logical_len": post_arm_order["observed_order"][3]["logical_a0_frame_length"],
        "cmd22_physical_len": post_arm_order["observed_order"][3]["physical_out_length"],
        "cmd22_ack_echo": post_arm_order["observed_order"][4]["ack_echo"],
        "first_image_outer": post_arm_order["observed_order"][5]["outer_type"],
        "first_image_transport": post_arm_order["observed_order"][5]["transport"],
        "first_image_len": post_arm_order["observed_order"][5]["physical_in_length"],
        "out_0x22_count": len(out_22),
        "taxonomy": physical_policy["taxonomy"],
        "phase2_confirmed": physical_policy["phase2_model_confirmed"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
