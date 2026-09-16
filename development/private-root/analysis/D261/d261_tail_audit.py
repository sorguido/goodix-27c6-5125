#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Derive the D261 per-command FDT physical-tail decision from raw D255."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("repository root not found")


REPO = find_repo_root(Path(__file__))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from analysis.D257 import d257_exact_bootstrap_audit as d257


EXPECTED_CAPTURE_SHA256 = "802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c"
EXPECTED_TRACE = (0x36, 0x50, 0x36, 0x82, 0x20, 0x36, 0x32)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def derive(repo: Path) -> tuple[dict[str, object], dict[str, object]]:
    timeline = d257.exact_timeline(repo)
    if timeline["capture_sha256"] != EXPECTED_CAPTURE_SHA256:
        raise RuntimeError("D255 capture hash gate failed")
    wanted_frames = [
        int(row["frame"])
        for row in timeline["rows"]
        if row["direction"] == "OUT" and row["control"] in {"0x20", "0x32", "0x36", "0x50", "0x82"}
    ]
    _run, _inputs, _wire, target = d257.load_target(repo)
    selected = {frame.packet_index + 1: frame for frame in target if frame.packet_index + 1 in wanted_frames}
    rows: list[dict[str, object]] = []
    controls: list[int] = []
    for frame_number in wanted_frames:
        frame = selected[frame_number]
        parsed = d257._decoded(frame)
        control = parsed[0]
        if control is None:
            raise RuntimeError(f"unparsed FDT OUT frame {frame_number}")
        controls.append(control)
        tail = frame.physical_payload[len(frame.raw):frame.physical_length]
        rows.append({
            "frame": frame_number,
            "control": f"0x{control:02x}",
            "logical_length": len(frame.raw),
            "logical_frame_sha256": sha256(frame.raw),
            "physical_length": frame.physical_length,
            "tail_length": len(tail),
            "tail_sha256": sha256(tail),
            "tail_nonzero_count": sum(value != 0 for value in tail),
            "tail_nonzero_offsets_physical_zero_based": [
                len(frame.raw) + offset for offset, value in enumerate(tail) if value
            ],
            "raw_tail_exported": False,
        })
    if tuple(controls) != EXPECTED_TRACE:
        raise RuntimeError(f"exact FDT trace changed:{controls!r}")

    per_command: dict[str, object] = {}
    for control in (0x36, 0x50, 0x82, 0x20, 0x32):
        key = f"0x{control:02x}"
        command_rows = [row for row in rows if row["control"] == key]
        tails_zero = all(row["tail_nonzero_count"] == 0 for row in command_rows)
        offsets = {tuple(row["tail_nonzero_offsets_physical_zero_based"]) for row in command_rows}
        digests = {str(row["tail_sha256"]) for row in command_rows}
        per_command[key] = {
            "occurrence_count": len(command_rows),
            "logical_lengths": sorted({int(row["logical_length"]) for row in command_rows}),
            "physical_lengths": sorted({int(row["physical_length"]) for row in command_rows}),
            "oem_tail_observed": "ZERO" if tails_zero else "NONZERO",
            "tail_pattern_intra_run": "STABLE" if len(digests) == 1 else "VARIABLE",
            "nonzero_offsets_intra_run": "STABLE" if len(offsets) == 1 else "VARIABLE",
            "staging_residue_evidence": (
                "PRIMARY_ZERO_TAIL_AND_ACK_OBSERVED"
                if control == 0x32
                else "STRONG_SAME_ABSOLUTE_OFFSETS_ACROSS_UNRELATED_COMMANDS_AND_D254_CROSS_CAPTURE_VARIATION"
            ),
            "primary_zero_tail_proof": control == 0x32,
            "deterministic_candidate": {
                "physical_length": 64,
                "tail_policy": "ZERO_FILL_OUTSIDE_DECLARED_LOGICAL_FRAME",
                "residue_replay": False,
            },
            "zero_tail_evidence_class": (
                "PRIMARY_TARGET_OEM_ZERO_TAIL_OBSERVED_AND_ACK_ACCEPTED"
                if control == 0x32
                else "EVIDENCE_SUPPORTED_DETERMINISTIC_CANDIDATE_NOT_LIVE_PROVEN"
            ),
            "zero_tail_candidate": True,
            "device_acceptance_status": (
                "PRIMARY_OEM_PATH_OBSERVED_FOR_0x32_ONLY"
                if control == 0x32
                else "UNPROVEN_LIVE_HYPOTHESIS"
            ),
        }

    nonzero_rows = [row for row in rows if row["tail_nonzero_count"]]
    if {tuple(row["tail_nonzero_offsets_physical_zero_based"]) for row in nonzero_rows} != {(40, 41, 42, 43, 44, 45)}:
        raise RuntimeError("D255 common staging-residue offsets changed")
    audit = {
        "schema": "D261_FDT_PHYSICAL_TAIL_AUDIT_V1",
        "execution_mode": "OFFLINE_ONLY",
        "source": {
            "path": "captures/D255_20260822T205631772Z_85c8c41f/raw/wire.pcapng",
            "sha256": EXPECTED_CAPTURE_SHA256,
            "raw_in_output": False,
        },
        "exact_trace": [f"0x{value:02x}" for value in controls],
        "rows": rows,
        "per_command": per_command,
        "cross_command_common_nonzero_offsets_physical_zero_based": [40, 41, 42, 43, 44, 45],
        "cross_capture_corroboration": {
            "D254_issue63_0x36_same_offsets_different_values": True,
            "D250_AF_fixed64_zero_tail_live_accepted": True,
            "D246_D4_fixed64_zero_tail_live_accepted": True,
            "semantic_tail_content_evidence_found": False,
        },
        "raw_tail_exported": False,
    }
    decision = {
        "schema": "D261_FDT_PHYSICAL_POLICY_DECISION_V1",
        "FDT_A0_PHYSICAL_POLICY_CLOSED": True,
        "FDT_A0_PHYSICAL_LENGTH": 64,
        "FDT_A0_TAIL_POLICY": "ZERO_FILL_OUTSIDE_DECLARED_LOGICAL_FRAME",
        "FDT_A0_RESIDUE_REPLAY": False,
        "FDT_A0_ZERO_TAIL_EVIDENCE_CLASS": "PER_COMMAND_MATRIX_MIXED_PRIMARY_AND_DETERMINISTIC_CANDIDATE",
        "FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE": "UNPROVEN_LIVE_HYPOTHESIS",
        "PRIMARY_FUTURE_LIVE_RISK": "FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND",
        "per_command": per_command,
        **{f"TAIL_POLICY_{key}": value["deterministic_candidate"] for key, value in per_command.items()},
        **{f"{key}_ZERO_TAIL_CANDIDATE": value["zero_tail_candidate"] for key, value in per_command.items()},
    }
    return audit, decision


def generate(repo: Path) -> None:
    output = repo / "analysis/D261"
    output.mkdir(parents=True, exist_ok=True)
    audit, decision = derive(repo)
    (output / "D261_fdt_physical_tail_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "D261_sanitized_tail_matrix.json").write_text(
        json.dumps({"schema": "D261_SANITIZED_TAIL_MATRIX_V1", "rows": audit["rows"]}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "D261_physical_policy_decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    generate(REPO)
    print("D261_FDT_PHYSICAL_TAIL_AUDIT=PASS")
