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


def redacted_tail_facts(af_outs: list[dict[str, object]]) -> dict[str, object]:
    tails = [
        bytes(item["payload"])[frame_total(bytes(item["payload"])) :]
        for item in af_outs
    ]
    lengths = [len(tail) for tail in tails]
    nonzero_offsets = [
        [offset for offset, value in enumerate(tail) if value]
        for tail in tails
    ]
    nonzero_counts = [len(offsets) for offsets in nonzero_offsets]
    return {
        "length": lengths[0] if len(set(lengths)) == 1 else None,
        "lengths_identical": len(set(lengths)) == 1,
        "nonzero_byte_count": (
            nonzero_counts[0] if len(set(nonzero_counts)) == 1 else None
        ),
        "nonzero_counts_identical": len(set(nonzero_counts)) == 1,
        "nonzero_offsets_zero_based": (
            nonzero_offsets[0]
            if all(offsets == nonzero_offsets[0] for offsets in nonzero_offsets)
            else None
        ),
        "nonzero_offsets_identical": all(
            offsets == nonzero_offsets[0] for offsets in nonzero_offsets
        ),
        "tails_identical": len(set(tails)) == 1,
        "raw_tail_in_output": False,
    }


def af_response_facts(
    items: list[dict[str, object]], af_outs: list[dict[str, object]]
) -> dict[str, object]:
    ack_indices = []
    direct_ae_indices = []
    for af in af_outs:
        following_in = [
            item
            for item in items
            if int(item["index"]) > int(af["index"])
            and item["endpoint"] == 0x81
            and item["info"] == 1
            and bytes(item["payload"])
        ]
        first = following_in[0]
        wire = bytes(first["payload"])
        if inner_control(wire) == 0xAE:
            direct_ae_indices.append(int(first["index"]))
        for item in following_in:
            candidate = bytes(item["payload"])
            control = inner_control(candidate)
            if control == 0xAE:
                break
            if control == 0xB0 and candidate[7:8] == b"\xaf":
                ack_indices.append(int(item["index"]))
    return {
        "af_ack_observed": bool(ack_indices),
        "af_ack_occurrence_count": len(ack_indices),
        "direct_ae_occurrence_count": len(direct_ae_indices),
    }


def require_expected_capture_facts(report: dict[str, object]) -> None:
    boundary = report["post_d4_boundary"]
    tail = boundary["af_submission_tail_redacted"]
    expected = {
        "all_capture_af_occurrences": 5,
        "all_capture_direct_ae_occurrences": 5,
        "all_af_submissions_fixed_64": True,
        "all_af_tails_zero": False,
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise RuntimeError(f"canonical capture fact changed:{key}")
    tail_expected = {
        "length": 51,
        "lengths_identical": True,
        "nonzero_byte_count": 6,
        "nonzero_counts_identical": True,
        "nonzero_offsets_zero_based": list(range(27, 33)),
        "nonzero_offsets_identical": True,
        "tails_identical": True,
    }
    for key, value in tail_expected.items():
        if tail.get(key) != value:
            raise RuntimeError(f"canonical capture tail fact changed:{key}")
    if boundary.get("af_ack_observed") is not False:
        raise RuntimeError("canonical capture fact changed:af_ack_observed")
    if boundary.get("af_ack_occurrence_count") != 0:
        raise RuntimeError("canonical capture fact changed:af_ack_occurrence_count")


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

    response_facts = af_response_facts(items, af_outs)
    tail_facts = redacted_tail_facts(af_outs)
    report = {
        "schema": "d250-af-capture-audit-v1",
        "capture_sha256": hashlib.sha256(CAPTURE.read_bytes()).hexdigest(),
        "capture_historical_classification": "D175_PRIMARY_LOCAL_TARGET_EVIDENCE",
        "all_capture_af_occurrences": len(af_outs),
        "all_capture_direct_ae_occurrences": response_facts[
            "direct_ae_occurrence_count"
        ],
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
            "af_submission_tail_redacted": tail_facts,
            "af_submission_tail_identical_across_all_five_occurrences": tail_facts[
                "tails_identical"
            ],
            "candidate_tail_policy": "DETERMINISTIC_ZERO_51_BYTES_DO_NOT_REPLAY_OPAQUE_HOST_STAGING",
            "candidate_tail_equivalence_status": "NOT_LIVE_PROVEN_FOR_AF;SAFETY_BOUNDED_BY_DECLARED_A0_LENGTH_AND_D4_ZERO_TAIL_PRECEDENT",
            "af_completion_status": "SUCCESS",
            "af_completion_event_payload_length": len(bytes(af_completion["payload"])),
            "af_completion_length_interpretation": "successful completion paired with the 64-byte submission; completion event carries no duplicate OUT payload",
            "ae_logical_frame_length": frame_total(ae_wire),
            "ae_usb_completion_payload_length": len(ae_wire),
            "ae_state_body_length": len(state.raw),
            "intervening_nonempty_in_frame_count": len(between),
            "af_ack_observed": response_facts["af_ack_observed"],
            "af_ack_occurrence_count": response_facts["af_ack_occurrence_count"],
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
    require_expected_capture_facts(report)
    return report


def main() -> int:
    print(json.dumps(derive(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
