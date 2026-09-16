#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate D282/02 per-trial evidence and emit a non-biometric TSV/env."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


MATCH_MARKER = "GOODIX_SIGFM_MATCH_AUDIT "
EXTRACT_MARKER = "GOODIX_SIGFM_EXTRACT_AUDIT "
EPOCH_MARKER = "GOODIX_D282_EPOCH_AUDIT "


def fields_after(line: str, marker: str) -> dict[str, str]:
    payload = line.split(marker, 1)[1]
    result: dict[str, str] = {}
    for token in payload.split():
        key, value = token.split("=", 1)
        if key in result:
            raise ValueError(f"duplicate field {key}")
        result[key] = value
    return result


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        key, value = line.split("=", 1)
        if key in result:
            raise ValueError(f"{path}: duplicate key {key}")
        result[key] = value
    return result


def require_int(value: str, name: str, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"{name}: not an integer") from error
    if parsed < minimum:
        raise ValueError(f"{name}: below {minimum}")
    return parsed


def parse_trial(private: Path, trial: int) -> dict[str, str | int]:
    stem = f"trial-{trial:02d}"
    meta = read_env(private / f"{stem}.meta")
    raw_lines = (private / f"{stem}.raw").read_text().splitlines()
    journal_lines = (private / f"{stem}.journal.raw").read_text().splitlines()
    expected = {
        "TRIAL": str(trial),
        "GLOBAL_ORDER": str(trial),
        "BLOCK": "A" if trial <= 2 else "B",
        "BLOCK_POSITION": str(1 if trial % 2 else 2),
        "PHYSICAL_FINGER": "RIGHT_INDEX",
    }
    for key, value in expected.items():
        if meta.get(key) != value:
            raise ValueError(f"{stem}: {key} expected {value}")
    daemon_pid = meta.get("DAEMON_PID", "")
    invocation_id = meta.get("DAEMON_INVOCATION_ID", "")
    if not re.fullmatch(r"[1-9][0-9]*", daemon_pid):
        raise ValueError(f"{stem}: invalid daemon pid")
    if not re.fullmatch(r"[0-9a-f]{32}", invocation_id):
        raise ValueError(f"{stem}: invalid daemon invocation id")

    client = [line for line in raw_lines if line.startswith("Verify result:")]
    retries = [line for line in raw_lines if "verify-retry-" in line]
    if retries or len(client) != 1:
        raise ValueError(f"{stem}: retry or non-unique client result")
    if client[0] == "Verify result: verify-match (done)":
        client_result, expected_rc = "match", 0
    elif client[0] == "Verify result: verify-no-match (done)":
        client_result, expected_rc = "no_match", 1
    else:
        raise ValueError(f"{stem}: unexpected client result")
    action_rc = require_int(meta.get("ACTION_RETURN_CODE", ""), "return code")
    if action_rc != expected_rc:
        raise ValueError(f"{stem}: client result/return code mismatch")

    match = [fields_after(line, MATCH_MARKER) for line in journal_lines
             if MATCH_MARKER in line]
    starts = [item for item in match if item.get("event") == "start"]
    comparisons = [item for item in match if item.get("event") == "comparison"]
    outcomes = [item for item in match if item.get("event") == "outcome"]
    errors = [item for item in match if item.get("event") == "error"]
    if len(starts) != 1 or len(outcomes) != 1 or errors or not comparisons:
        raise ValueError(f"{stem}: incomplete matcher telemetry")
    template_samples = require_int(starts[0]["template_samples"],
                                   "template samples", 1)
    threshold = require_int(starts[0]["threshold"], "threshold", 1)
    if template_samples != 8 or threshold != 40:
        raise ValueError(f"{stem}: algorithm parameter drift")
    scores: list[int] = []
    for index, comparison in enumerate(comparisons, 1):
        if require_int(comparison["sample"], "sample", 1) != index:
            raise ValueError(f"{stem}: non-contiguous comparisons")
        if require_int(comparison["threshold"], "threshold", 1) != threshold:
            raise ValueError(f"{stem}: comparison threshold drift")
        scores.append(require_int(comparison["score"], "score"))
    outcome = outcomes[0]
    if outcome.get("result") != client_result:
        raise ValueError(f"{stem}: matcher/client outcome mismatch")
    if require_int(outcome["comparisons"], "comparisons", 1) != len(scores):
        raise ValueError(f"{stem}: outcome comparison count mismatch")
    if require_int(outcome["threshold"], "threshold", 1) != threshold:
        raise ValueError(f"{stem}: outcome threshold drift")
    matched_sample = require_int(outcome["matched_sample"], "matched sample")
    if client_result == "match":
        if matched_sample != len(scores) or scores[-1] < threshold:
            raise ValueError(f"{stem}: incoherent match telemetry")
    elif matched_sample != 0 or len(scores) != template_samples or any(
            score >= threshold for score in scores):
        raise ValueError(f"{stem}: incoherent no-match telemetry")

    extracts = [fields_after(line, EXTRACT_MARKER) for line in journal_lines
                if EXTRACT_MARKER in line]
    if len(extracts) != 1:
        raise ValueError(f"{stem}: expected one probe extraction")
    keypoints = require_int(extracts[0]["keypoints"], "keypoints", 1)

    epochs = [fields_after(line, EPOCH_MARKER) for line in journal_lines
              if EPOCH_MARKER in line]
    if len(epochs) != 1 or epochs[0].get("action") != "FPI_DEVICE_ACTION_VERIFY":
        raise ValueError(f"{stem}: expected one VERIFY epoch")
    epoch = epochs[0]
    required_epoch = {
        "attempts": "1", "rejected": "0", "consumed": "1", "tls": "1",
        "first_image": "1", "secure_retry": "0", "post_retry": "0",
        "reopen": "0", "reset": "0", "clear_halt": "0", "persistent": "0",
        "outstanding": "0", "drained": "1", "context_closed": "1",
    }
    for key, value in required_epoch.items():
        if epoch.get(key) != value:
            raise ValueError(f"{stem}: epoch {key} expected {value}")

    return {
        "trial": trial,
        "block": expected["BLOCK"],
        "block_position": expected["BLOCK_POSITION"],
        "global_order": trial,
        "physical_finger": "RIGHT_INDEX",
        "daemon_pid": daemon_pid,
        "daemon_invocation_id": invocation_id,
        "result": client_result,
        "action_return_code": action_rc,
        "probe_keypoints": keypoints,
        "threshold": threshold,
        "template_samples": template_samples,
        "comparison_count": len(scores),
        "max_score": max(scores),
        "scores_by_enrolled_sample": ",".join(
            f"{index}:{score}" for index, score in enumerate(scores, 1)),
        "real_submit": require_int(epoch["real_submit"], "real submit", 1),
    }


def write_outputs(trials: list[dict[str, str | int]], tsv: Path,
                  env: Path) -> None:
    if (trials[0]["daemon_invocation_id"] !=
            trials[1]["daemon_invocation_id"] or
            trials[0]["daemon_pid"] != trials[1]["daemon_pid"] or
            trials[2]["daemon_invocation_id"] !=
            trials[3]["daemon_invocation_id"] or
            trials[2]["daemon_pid"] != trials[3]["daemon_pid"]):
        raise ValueError("trial pair does not share one daemon process")
    if (trials[0]["daemon_invocation_id"] ==
            trials[2]["daemon_invocation_id"]):
        raise ValueError("blocks do not have distinct daemon invocations")
    columns = list(trials[0])
    tsv.write_text("\t".join(columns) + "\n" + "\n".join(
        "\t".join(str(trial[column]) for column in columns)
        for trial in trials) + "\n")
    position_one = sum(trial["result"] == "match" for trial in trials
                       if trial["block_position"] == "1")
    position_two = sum(trial["result"] == "match" for trial in trials
                       if trial["block_position"] == "2")
    env.write_text(
        "D282_02_TRIAL_AUDIT=PASS\n"
        "D282_02_TRIAL_COUNT=4\n"
        "D282_02_BLOCK_COUNT=2\n"
        "D282_02_TRIALS_PER_BLOCK=2\n"
        "D282_02_PHYSICAL_FINGER=RIGHT_INDEX\n"
        "D282_02_TEMPLATE_SAMPLE_COUNT=8\n"
        "D282_02_SIGFM_THRESHOLD=40\n"
        "D282_02_DAEMON_PROCESS_BLOCKS_VERIFIED=true\n"
        f"D282_02_POSITION_1_MATCH_COUNT={position_one}\n"
        f"D282_02_POSITION_2_MATCH_COUNT={position_two}\n"
        "D282_02_STATISTICAL_GENERALIZATION_ALLOWED=false\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("private", type=Path)
    parser.add_argument("tsv", type=Path)
    parser.add_argument("env", type=Path)
    args = parser.parse_args()
    trials = [parse_trial(args.private, trial) for trial in range(1, 5)]
    write_outputs(trials, args.tsv, args.env)


if __name__ == "__main__":
    main()
