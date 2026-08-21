# SPDX-License-Identifier: GPL-2.0-or-later
"""Derive redacted AF boundary facts from the canonical local USBPcap."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from analysis.D242.d242_capture_forensics import packets
from core.post_d4 import parse_af_response


CAPTURE = REPOSITORY / "analysis/D230/work/GoodixExport/rilevamento.pcapng"


def frame_total(data: bytes) -> int:
    return 4 + int.from_bytes(data[1:3], "little")


def inner_control(data: bytes) -> int | None:
    return data[4] if len(data) >= 5 and data[0] == 0xA0 else None


def milliseconds(later: dict[str, object], earlier: dict[str, object]) -> float:
    return round(
        (int(later["ticks"]) - int(earlier["ticks"]))
        * 1000
        / int(later["ts_resolution"]),
        3,
    )


def next_matching(items, start: int, predicate):
    return next(item for item in items if int(item["index"]) > start and predicate(item))


def derive() -> dict[str, object]:
    items = packets(CAPTURE)
    af_outs = [
        item
        for item in items
        if item["endpoint"] == 0x01
        and item["info"] == 0
        and inner_control(bytes(item["payload"])) == 0xAF
    ]
    ae_ins = [
        item
        for item in items
        if item["endpoint"] == 0x81
        and item["info"] == 1
        and inner_control(bytes(item["payload"])) == 0xAE
    ]
    d4 = next(
        item
        for item in items
        if item["endpoint"] == 0x01
        and item["info"] == 0
        and inner_control(bytes(item["payload"])) == 0xD4
    )
    d4_ack = next_matching(
        items,
        int(d4["index"]),
        lambda item: item["endpoint"] == 0x81
        and item["info"] == 1
        and bytes(item["payload"])[4:9] == bytes.fromhex("b00300d401"),
    )
    af = next(item for item in af_outs if int(item["index"]) > int(d4_ack["index"]))
    af_completion = next_matching(
        items,
        int(af["index"]),
        lambda item: item["irp_id"] == af["irp_id"] and item["info"] == 1,
    )
    ae = next(item for item in ae_ins if int(item["index"]) > int(af_completion["index"]))

    af_wire = bytes(af["payload"])
    ae_wire = bytes(ae["payload"])
    logical_af_length = frame_total(af_wire)
    state = parse_af_response(ae_wire[: frame_total(ae_wire)])
    between = [
        item
        for item in items
        if int(af["index"]) < int(item["index"]) < int(ae["index"])
        and item["endpoint"] == 0x81
        and item["info"] == 1
        and bytes(item["payload"])
    ]

    return {
        "schema": "d250-af-capture-audit-v1",
        "capture_sha256": hashlib.sha256(CAPTURE.read_bytes()).hexdigest(),
        "capture_historical_classification": "D175_PRIMARY_LOCAL_TARGET_EVIDENCE",
        "all_capture_af_occurrences": len(af_outs),
        "all_capture_direct_ae_occurrences": len(ae_ins),
        "all_af_submissions_fixed_64": all(len(bytes(item["payload"])) == 64 for item in af_outs),
        "all_af_tails_zero": all(
            bytes(item["payload"])[frame_total(bytes(item["payload"])) :] == bytes(64 - frame_total(bytes(item["payload"])))
            for item in af_outs
        ),
        "post_d4_boundary": {
            "d4_out_packet_index_zero_based": d4["index"],
            "d4_ack_packet_index_zero_based": d4_ack["index"],
            "af_out_packet_index_zero_based": af["index"],
            "af_out_completion_packet_index_zero_based": af_completion["index"],
            "ae_in_packet_index_zero_based": ae["index"],
            "endpoint_out": "0x01",
            "endpoint_in": "0x81",
            "af_logical_frame_length": logical_af_length,
            "af_physical_submission_length": len(af_wire),
            "af_submission_tail": "OPAQUE_51_BYTES_WITH_6_NONZERO_BYTES_AT_TAIL_OFFSETS_27_TO_32",
            "af_submission_tail_identical_across_all_five_occurrences": len(
                {
                    bytes(item["payload"])[frame_total(bytes(item["payload"])) :]
                    for item in af_outs
                }
            ) == 1,
            "candidate_tail_policy": "DETERMINISTIC_ZERO_51_BYTES_DO_NOT_REPLAY_OPAQUE_HOST_STAGING",
            "candidate_tail_equivalence_status": "NOT_LIVE_PROVEN_FOR_AF;SAFETY_BOUNDED_BY_DECLARED_A0_LENGTH_AND_D4_ZERO_TAIL_PRECEDENT",
            "af_completion_status": "SUCCESS",
            "af_completion_event_payload_length": len(bytes(af_completion["payload"])),
            "af_completion_length_interpretation": "successful completion paired with the 64-byte submission; completion event carries no duplicate OUT payload",
            "ae_logical_frame_length": frame_total(ae_wire),
            "ae_usb_completion_payload_length": len(ae_wire),
            "ae_state_body_length": len(state.raw),
            "intervening_nonempty_in_frame_count": len(between),
            "af_ack_observed": False,
            "d4_ack_to_af_out_ms": milliseconds(af, d4_ack),
            "af_out_to_completion_ms": milliseconds(af_completion, af),
            "af_completion_to_ae_in_ms": milliseconds(ae, af_completion),
            "state_version": state.raw[0],
            "state_flags": state.raw[1],
            "pov_valid": state.pov_valid,
            "tls_connected": state.tls_connected,
            "locked": state.locked,
            "unknown_flag_bits": state.unknown_flag_bits,
        },
        "redaction": {
            "raw_capture_in_output": False,
            "raw_tls_in_output": False,
            "secret_in_output": False,
            "biometric_payload_in_output": False,
        },
    }


def main() -> int:
    print(json.dumps(derive(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
