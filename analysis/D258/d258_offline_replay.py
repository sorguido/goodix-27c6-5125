#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run D258 projected and exact-candidate scenarios against private D255 by reference."""

from __future__ import annotations

import argparse
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

from analysis.D257 import d257_offline_replay as d257_replay
from analysis.D258 import d258_host_gate_audit
from core.fdt_lifecycle import (
    COMMAND_TIMEOUT_MS,
    EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE,
    ExactFreshFdtBootstrapMachine,
    FdtLifecycle,
)
from core.fdt_seed import provide_fdt12
from core.post_d4 import InvalidTransition


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


class ScriptedTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[bytes] = []
        self.timeouts: list[int | None] = []

    def exchange(self, request: bytes, *, timeout_ms: int | None = None):
        self.requests.append(request)
        self.timeouts.append(timeout_ms)
        require(bool(self.responses), "unexpected offline exchange")
        return self.responses.pop(0)


def exact_blocked(repo: Path, audit: dict[str, object]) -> dict[str, object]:
    _run, _wire, target_frames, otp, cache = d257_replay._load_d255(repo)
    by_frame = {frame.packet_index + 1: frame for frame in target_frames}
    rows = audit["callgraph"]  # force the hash-gated static audit to be consumed
    require(bool(rows), "D258 callgraph unavailable")
    timeline = d258_host_gate_audit.d257.audit(repo)["timeline"]["rows"]

    def frames_for(prefix: str):
        return [by_frame[int(row["frame"])] for row in timeline
                if str(row["event_class"]).startswith(prefix)]

    requests = frames_for("FDT36_STAGE_")
    nav_request = frames_for("INTERSTAGE_NAV_0x50_REQUEST")[0]
    delta_request = frames_for("INTERSTAGE_FDT_DELTA_0x82_REQUEST")[0]
    image_request = frames_for("INTERSTAGE_BASELINE_IMAGE_0x20_REQUEST")[0]
    acks36 = frames_for("ACK_0x36_STATUS_01")
    events36 = frames_for("IRQ_0x0100_TOUCH_0")
    nav_ack = frames_for("ACK_0x50_STATUS_01")[0]
    nav_response = frames_for("INTERSTAGE_NAV_0x50_RESPONSE")[0]
    delta_ack = frames_for("ACK_0x82_STATUS_01")[0]
    delta_response = frames_for("INTERSTAGE_FDT_DELTA_0x82_RESPONSE")[0]
    image_ack = frames_for("ACK_0x20_STATUS_01")[0]
    image_response = frames_for("INTERSTAGE_BASELINE_IMAGE_B0_RESPONSE")[0]
    require(len(requests) == len(acks36) == len(events36) == 3, "D255 manual census changed")

    transport = ScriptedTransport((
        [acks36[0].raw],
        [nav_ack.raw, nav_response.raw],
        [acks36[1].raw],
        [delta_ack.raw, delta_response.raw],
        [image_ack.raw, image_response.raw],
        [acks36[2].raw],
    ))
    provider = provide_fdt12(cache.path, otp)
    require(provider.ok, "D255 seed provider failed")
    lifecycle = FdtLifecycle()
    lifecycle.observe_af_state(False)
    machine = ExactFreshFdtBootstrapMachine(transport, lifecycle)
    machine.begin(provider)
    machine.manual_sample(events36[0].raw[4:])
    machine.nav_interstage()
    machine.manual_sample(events36[1].raw[4:])
    machine.delta_and_baseline_interstage()
    machine.manual_sample(events36[2].raw[4:])
    try:
        machine.finalize_host_base_decisions()
    except InvalidTransition as error:
        require(str(error) == "nav_post_sample_classifier_unavailable",
                "unexpected exact replay blocker")
    else:
        raise RuntimeError("unresolved post-sample classifier was bypassed")

    expected_requests = [
        requests[0].raw, nav_request.raw, requests[1].raw,
        delta_request.raw, image_request.raw, requests[2].raw,
    ]
    require(transport.requests == expected_requests, "pre-blocker requests are not D255 wire-exact")
    expected_timeouts = [
        COMMAND_TIMEOUT_MS[0x36], COMMAND_TIMEOUT_MS[0x50],
        COMMAND_TIMEOUT_MS[0x36], COMMAND_TIMEOUT_MS[0x82],
        COMMAND_TIMEOUT_MS[0x20], COMMAND_TIMEOUT_MS[0x36],
    ]
    require(transport.timeouts == expected_timeouts, "command-specific timeout policy changed")
    require(machine.delta_threshold == 0x1D, "D255 0x82 threshold interpretation changed")
    require(lifecycle.retry_count == 0, "automatic retry occurred")
    return {
        "name": "EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY",
        "status": "BLOCKED_AFTER_STAGE2_AT_UNREPRODUCED_POST_SAMPLE_HOST_CLASSIFIERS",
        "target_trace": [f"0x{value:02x}" for value in EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE],
        "wire_exact_requests_before_blocker": ["0x36", "0x50", "0x36", "0x82", "0x20", "0x36"],
        "first_0x36_attempt_count": machine.first_0x36_attempt_count,
        "manual_stage_count": machine.manual_stage,
        "nav_dynamic_state_stored": machine.nav_dynamic_state is not None,
        "delta_native_predicate_passed": machine.delta_gate_passed,
        "second_delta_native_predicate_passed": machine.second_delta_gate_passed,
        "delta_threshold_unsigned": machine.delta_threshold,
        "baseline_b0_envelope_stored": machine.baseline_b0 is not None,
        "host_decisions_finalized": machine.host_decisions_finalized,
        "final_0x32_sent": False,
        "timeouts_ms": transport.timeouts,
        "automatic_retry_count": lifecycle.retry_count,
        "persistent_write_family_count": lifecycle.persistent_write_family_count,
        "a2_reentry_injection": 0,
        "0x70_reentry_injection": 0,
        "raw_dynamic_payload_exported": False,
        "lifecycle": lifecycle.audit(),
    }


def run(repo: Path) -> dict[str, object]:
    audit = d258_host_gate_audit.audit(repo)
    projected, _context = d257_replay.scenario_d255(repo)
    exact = exact_blocked(repo, audit)
    return {
        "schema": "D258_OFFLINE_REPLAY_V1",
        "execution_mode": "OFFLINE_ONLY",
        "scenarios": [projected, exact],
        "closure": {
            "TARGET_BOOTSTRAP_SEQUENCE_HASH_GATED": True,
            "PROJECTED_FDT_SUBSEQUENCE_REPLAY": "PASS_HISTORICAL",
            "EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY": "BLOCKED",
            "DYNAMIC_HOST_GATES_CLOSED": False,
            "FDT_OFFLINE_CANDIDATE_CLOSED": False,
            "HOST_BUS_LIFECYCLE_READY": True,
            "SEED_FRESHNESS_FACTORY_PRESERVATION_BLOCKER": False,
            "SEED_FRESHNESS_FUNCTIONAL_SUCCESS_RISK": "GENERAL_TTL_UNPROVEN_BOUNDED_RISK",
            "READY_FOR_FDT_LIVE_REVIEW": False,
            "READY_FOR_FDT_LIVE": False,
        },
        "primary_blockers": [
            "POST_STAGE2_NAV_CLASSIFIER_0x180022654_NOT_EXACTLY_REPRODUCIBLE_FROM_TARGET_RUNTIME_STATE",
            "D255_BASELINE_B0_PLAINTEXT_AND_POST_STAGE2_IMAGE_CLASSIFIER_RUNTIME_STATE_UNAVAILABLE",
        ],
        "safety": {
            "REAL_USB_OPEN_COUNT": 0,
            "REAL_CAPTURE_COUNT": 0,
            "REAL_HARDWARE_ACTION_COUNT": 0,
            "REAL_COMMAND_SEND_COUNT": 0,
            "PERSISTENT_WRITE_FAMILY_COUNT": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    rendered = json.dumps(run(repo), indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else repo / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
