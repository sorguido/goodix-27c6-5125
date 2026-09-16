#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reproduce the bounded D258 target host-gate audit without hardware access."""

from __future__ import annotations

import argparse
from datetime import datetime
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
from core.fdt_lifecycle import COMMAND_TIMEOUT_MS, COMMAND_TIMEOUT_POLICY


DLL = Path("analysis/D230/work/GoodixExport/gfusb.dll")
DISASM = Path("analysis/D230/work/GoodixExport/gfusb_static_refs/gfusb_disasm.txt")
EXPECTED_DLL_SHA256 = "904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def elapsed_ms(later: str, earlier: str) -> float:
    left = datetime.fromisoformat(later.replace("Z", "+00:00"))
    right = datetime.fromisoformat(earlier.replace("Z", "+00:00"))
    return round((left - right).total_seconds() * 1000, 3)


def callgraph() -> dict[str, object]:
    return {
        "schema": "D258_HOST_GATE_CALLGRAPH_V1",
        "target_module": "gfusb.dll",
        "orchestrator": {
            "OWNER_MODULE": "gfusb.dll",
            "OWNER_FUNCTION_OR_OFFSET": "gf_update_all_base 0x180068adc..0x18006987d",
            "INPUT": "loaded target base/cache state plus sensor callbacks",
            "OUTPUT": "base update/reuse result consumed by caller 0x180068940",
            "NEXT_STAGE_BRANCH": "success -> ChicagoHUSetMode(3,1,1) final 0x32",
            "EVIDENCE_CLASS": "TARGET_OEM_STATIC_HASH_GATED",
        },
        "sequence": [
            "0x1800676f8 FDT stage0 (500 ms)",
            "0x180067874 NAV acquire/store via mode5 (500 ms)",
            "0x1800676f8 FDT stage1 (500 ms)",
            "0x180059488 ChipRegRead(0x0082,2,500 ms)",
            "0x180067914 baseline image via mode2 (2000 ms)",
            "0x1800676f8 FDT stage2 (500 ms)",
            "0x180023fdc NAV classifier wrapper mode=1",
            "0x180023fa8 image classifier wrapper mode=0",
            "0x180068abe final ChicagoHUSetMode(3,1,1)",
        ],
        "gates": {
            "0x50": {
                "OWNER_MODULE": "gfusb.dll",
                "OWNER_FUNCTION_OR_OFFSET": "acquire 0x180067874; consume 0x180069377 -> 0x180023fdc -> 0x180022654",
                "INPUT": "A0/0x50 dynamic NAV body (2409 bytes) plus cached NAV base and runtime classifier configuration",
                "OUTPUT": "stored NAV buffer, then classifier enum 0..3 after stage2",
                "NEXT_STAGE_BRANCH": "acquisition success always permits stage1; post-stage2 enum selects keep/update NAV base, not stage2 admission",
                "EVIDENCE_CLASS": "TARGET_OEM_STATIC_HASH_GATED_PLUS_D255_TARGET_CAPTURE",
            },
            "0x82": {
                "OWNER_MODULE": "gfusb.dll",
                "OWNER_FUNCTION_OR_OFFSET": "gf_update_all_base 0x180068e26..0x180068ffe",
                "INPUT": "ChipRegRead register 0x0082 quantity 2; unsigned raw FDT base0/base1 words",
                "OUTPUT": "threshold = zero_extend(response[1]); response[0] ignored on this path",
                "NEXT_STAGE_BRANCH": "all abs(base0[i]-base1[i]) <= threshold -> baseline image; violation -> cached-base fallback or rebuild loop",
                "EVIDENCE_CLASS": "TARGET_OEM_STATIC_HASH_GATED_PLUS_D255_TARGET_CAPTURE",
            },
            "0x20": {
                "OWNER_MODULE": "gfusb.dll",
                "OWNER_FUNCTION_OR_OFFSET": "acquire 0x180067914; consume 0x180069531 -> 0x180023fa8 -> 0x180022654",
                "INPUT": "decrypted baseline image plus cached image base and runtime classifier configuration",
                "OUTPUT": "classifier enum 0..3 after stage2",
                "NEXT_STAGE_BRANCH": "acquisition success permits stage2; post-stage2 enum selects keep/update image base",
                "EVIDENCE_CLASS": "TARGET_OEM_STATIC_HASH_GATED; D255 B0 PLAINTEXT_UNAVAILABLE",
            },
        },
    }


def audit(repo: Path) -> dict[str, object]:
    dll = repo / DLL
    disasm_path = repo / DISASM
    require(sha256_file(dll) == EXPECTED_DLL_SHA256, "gfusb.dll hash gate failed")
    disasm = disasm_path.read_text(encoding="utf-8", errors="replace")
    anchors = (
        "180068adc:", "180068cf2:", "call   0x180067874",
        "180068e35:", "mov    cx,0x82", "call   0x180059488",
        "180068e52:", "BYTE PTR [rsp+rax*1+0x50]",
        "180068f1f:", "180068f2c:", "180068f83:",
        "18006904a:", "mov    dx,0x7d0", "call   0x180067914",
        "18006914d:", "180069377:", "call   0x180023fdc",
        "180069531:", "call   0x180023fa8", "180068abe:",
    )
    missing = [anchor for anchor in anchors if anchor not in disasm]
    require(not missing, f"static anchors missing: {missing}")

    exact = d257.audit(repo)
    rows = exact["timeline"]["rows"]
    by_class = {str(row["event_class"]): row for row in rows}
    first_irq = next(row for row in rows if row["event_class"] == "IRQ_0x0100_TOUCH_0")
    latencies = {
        "0x36_stage0_request_to_irq_ms": elapsed_ms(
            first_irq["timestamp_utc"],
            by_class["FDT36_STAGE_0_REQUEST"]["timestamp_utc"],
        ),
        "0x50_request_to_nav_ms": elapsed_ms(
            by_class["INTERSTAGE_NAV_0x50_RESPONSE"]["timestamp_utc"],
            by_class["INTERSTAGE_NAV_0x50_REQUEST"]["timestamp_utc"],
        ),
        "0x82_request_to_response_ms": elapsed_ms(
            by_class["INTERSTAGE_FDT_DELTA_0x82_RESPONSE"]["timestamp_utc"],
            by_class["INTERSTAGE_FDT_DELTA_0x82_REQUEST"]["timestamp_utc"],
        ),
        "0x20_request_to_b0_ms": elapsed_ms(
            by_class["INTERSTAGE_BASELINE_IMAGE_B0_RESPONSE"]["timestamp_utc"],
            by_class["INTERSTAGE_BASELINE_IMAGE_0x20_REQUEST"]["timestamp_utc"],
        ),
        "0x32_request_to_ack_ms": elapsed_ms(
            by_class["ACK_0x32_STATUS_01"]["timestamp_utc"],
            by_class["FIRST_POST_BOOTSTRAP_FDT32_REQUEST"]["timestamp_utc"],
        ),
    }
    return {
        "schema": "D258_HOST_GATE_AUDIT_V1",
        "execution_mode": "OFFLINE_ONLY",
        "target": {
            "gfusb_sha256": sha256_file(dll),
            "d255_capture_sha256": exact["timeline"]["capture_sha256"],
            "bootstrap_sequence_hash_gated": exact["timeline"]["out_control_trace"][1:]
            == ["0x36", "0x50", "0x36", "0x82", "0x20", "0x36", "0x32"],
            "static_anchor_count": len(anchors),
        },
        "callgraph": callgraph(),
        "decisions": {
            "GATE_0x50_STATUS": "PARTIAL_STORE_ROLE_CLOSED_POST_SAMPLE_CLASSIFIER_UNRESOLVED",
            "GATE_0x50_CLASS": "STORE_THEN_POST_SAMPLE_SEMANTIC_CLASSIFIER",
            "GATE_0x50_PREDICATE": "NONE_BEFORE_STAGE1; POST_STAGE2_CLASSIFIER_0x180022654_UNREPRODUCED",
            "GATE_0x82_STATUS": "CLOSED_NATIVE_PREDICATE_IMPLEMENTED",
            "GATE_0x82_PREDICATE": "forall i: abs(uint16(base0[i])-uint16(base1[i])) <= uint8(response[1])",
            "GATE_0x82_RESPONSE_ROLE": "response[0] ignored; response[1] unsigned threshold",
            "GATE_0x20_STATUS": "PARTIAL_ACQUISITION_ROLE_CLOSED_POST_SAMPLE_CLASSIFIER_UNRESOLVED",
            "GATE_0x20_PREDICATE": "POST_STAGE2_CLASSIFIER_0x180022654_UNREPRODUCED",
            "D255_B0_DECRYPTION_STATUS": "INPUT_UNAVAILABLE_WITHOUT_PRIVILEGE",
            "CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x50_GATE": True,
            "MISSING_FOR_0x50_GATE": "target runtime classifier configuration/state for 0x180022654 and an exact validated ABI/model",
            "CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x82_GATE": True,
            "MISSING_FOR_0x82_GATE": "NONE",
            "CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x20_GATE": True,
            "MISSING_FOR_0x20_GATE": "D255 decrypted B0 application body plus target runtime classifier configuration/state for 0x180022654",
        },
        "timeouts": {
            "COMMAND_TIMEOUT_POLICY": COMMAND_TIMEOUT_POLICY,
            "TIMEOUT_0x36_MS": COMMAND_TIMEOUT_MS[0x36],
            "TIMEOUT_0x50_MS": COMMAND_TIMEOUT_MS[0x50],
            "TIMEOUT_0x82_MS": COMMAND_TIMEOUT_MS[0x82],
            "TIMEOUT_0x20_MS": COMMAND_TIMEOUT_MS[0x20],
            "TIMEOUT_0x32_MS": COMMAND_TIMEOUT_MS[0x32],
            "d255_observed_latencies": latencies,
            "static_basis": "gf_update_all_base: 0x36/0x50/0x82=500 ms, 0x20=2000 ms; ChicagoHUSetMode final 0x32 ACK=100 ms",
            "automatic_retry_count": 0,
        },
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
    parser.add_argument("--callgraph-output", type=Path)
    args = parser.parse_args()
    result = audit(args.repo_root.resolve())
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else args.repo_root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.callgraph_output:
        output = (args.callgraph_output if args.callgraph_output.is_absolute()
                  else args.repo_root / args.callgraph_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result["callgraph"], indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
