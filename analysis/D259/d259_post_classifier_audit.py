#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reproduce D259 post-classifier wire, recovery, and cache matrices offline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path


DLL = Path("analysis/D230/work/GoodixExport/gfusb.dll")
DISASM = Path("analysis/D230/work/GoodixExport/gfusb_static_refs/gfusb_disasm.txt")
STRINGS = Path("analysis/D230/work/GoodixExport/gfusb_static_refs/gfusb_strings_utf16_off.txt")
D255_CAPTURE = Path("captures/D255_20260822T205631772Z_85c8c41f/raw/wire.pcapng")
EXPECTED_DLL_SHA256 = "904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2"
EXPECTED_D255_CAPTURE_SHA256 = "802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c"

WIRE_FIELDS = (
    "classifier", "return", "gf_update_all_base_result", "host_ram_effect",
    "fdt_table_effect", "final_0x32_payload_effect", "additional_usb_commands",
    "retry_or_rebuild", "recovery_command", "cache_write_effect",
    "final_0x32_reachable", "evidence",
)


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("repository root not found")


REPO = find_repo_root(Path(__file__))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def csv_text(rows: list[dict[str, object]], fields: tuple[str, ...]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def markdown_table(rows: list[dict[str, object]], fields: tuple[str, ...]) -> str:
    lines = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    for row in rows:
        values = [str(row[field]).replace("|", "\\|") for field in fields]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def audit(repo: Path) -> dict[str, object]:
    dll = repo / DLL
    capture = repo / D255_CAPTURE
    require(sha256_file(dll) == EXPECTED_DLL_SHA256, "gfusb.dll hash gate failed")
    require(sha256_file(capture) == EXPECTED_D255_CAPTURE_SHA256,
            "D255 capture hash gate failed")
    disasm = (repo / DISASM).read_text(encoding="utf-8", errors="replace")
    strings = (repo / STRINGS).read_text(encoding="utf-8", errors="replace")

    anchors = (
        "18006898a:", "call   0x180068adc", "18006898f:", "180068abe:",
        "180068b21:", "DWORD PTR [rsp+0x44],0x1",
        "180069377:", "call   0x180023fdc", "1800693d8:", "1800694fa:",
        "180069501:", "0x18059fa88", "18006952c:",
        "180069531:", "call   0x180023fa8", "180069592:", "1800696b4:",
        "1800696bb:", "0x18059fa78", "180069722:",
        "180069727:", "call   0x1800225e8", "1800697d8:",
        "1800697e1:", "call   0x180067f44", "18006981c:", "180069860:",
        "180025046:", "0x180580818", "1800253e2:",
    )
    missing = [anchor for anchor in anchors if anchor not in disasm]
    require(not missing, f"static anchors missing: {missing}")
    require("2415a0 goodix.dat" in strings, "goodix.dat string anchor missing")
    require("4e72c0 gf_savebaseTofile" in strings, "gf_savebaseTofile anchor missing")

    evidence = (
        "gf_update_all_base init/result 0x180068b21,0x18006981c,0x180069860; "
        "caller success branch 0x18006898a..0x180068abe; classifiers/copies "
        "0x180069377..0x18006952c and 0x180069531..0x180069722; "
        "host state 0x180069727..0x180069737; conditional cache call "
        "0x1800697d8..0x1800697e6; independent FDT table global "
        "0x180580818 at 0x180025046/0x1800253e2"
    )
    wire_rows: list[dict[str, object]] = []
    for classifier in ("NAV", "IMAGE"):
        for returned in ("0", "1", "2", "3", "negative_or_other"):
            update = returned != "1"
            wire_rows.append({
                "classifier": classifier,
                "return": returned,
                "gf_update_all_base_result": "1_SUCCESS",
                "host_ram_effect": "KEEP_EXISTING_BASE" if not update else "COPY_ACQUIRED_BASE",
                "fdt_table_effect": "NONE",
                "final_0x32_payload_effect": "NONE",
                "additional_usb_commands": "NONE",
                "retry_or_rebuild": "NONE_FROM_CLASSIFIER_RETURN",
                "recovery_command": "NONE",
                "cache_write_effect": "NO_UPDATE_FROM_THIS_CLASSIFIER" if not update else "SETS_SHARED_DIRTY_FLAG",
                "final_0x32_reachable": "YES",
                "evidence": evidence,
            })

    recovery_rows = [
        {
            "condition": "classifier_return_0_1_2_3_negative_or_other",
            "gf_update_all_base_result": "1_SUCCESS",
            "final_0x32": "REACHABLE",
            "retry_or_rebuild": "NONE",
            "a2_reentry": 0,
            "0x70_reentry": 0,
            "other_recovery_command": "NONE",
            "evidence": "all switch arms converge at 0x1800694fa/0x1800696b4; return remains [rsp+0x44]=1",
        },
        {
            "condition": "earlier_acquisition_or_protocol_failure",
            "gf_update_all_base_result": "0_FAILURE",
            "final_0x32": "NOT_REACHED_BY_CALLER",
            "retry_or_rebuild": "ONLY_EARLIER_DELTA_FALLBACK_OR_LOOP; NOT_CLASSIFIER_CAUSED",
            "a2_reentry": 0,
            "0x70_reentry": 0,
            "other_recovery_command": "NONE_IN_CALLER_BRANCH",
            "evidence": "failure writes [rsp+0x44]=0; caller 0x18006898f branches away from 0x180068abe",
        },
    ]
    recovery_fields = tuple(recovery_rows[0])

    cache_rows = [
        {
            "phase": "before_final_0x32",
            "condition": "either_classifier_return_not_equal_1_or_classifier_disabled_copy_path",
            "oem_effect": "gf_savebaseTofile/goodix.dat called conditionally",
            "linux_first_live_policy": "DISABLED",
            "required_for_final_0x32": False,
            "required_for_device_progress": False,
            "host_cache_write_count_in_minimal_candidate": 0,
            "evidence": "dirty byte 0x18006952c/0x180069722/0x1800697d3; call 0x1800697e1; caller arm later at 0x180068abe",
        },
        {
            "phase": "after_final_0x32",
            "condition": "gf_update_all_base caller path",
            "oem_effect": "NONE_OBSERVED",
            "linux_first_live_policy": "DISABLED",
            "required_for_final_0x32": False,
            "required_for_device_progress": False,
            "host_cache_write_count_in_minimal_candidate": 0,
            "evidence": "cache call is inside gf_update_all_base before return; caller issues final 0x32 afterwards",
        },
    ]
    cache_fields = tuple(cache_rows[0])

    return {
        "schema": "D259_POST_CLASSIFIER_AUDIT_V1",
        "execution_mode": "OFFLINE_ONLY",
        "hash_gates": {
            "gfusb_sha256": sha256_file(dll),
            "d255_capture_sha256": sha256_file(capture),
            "static_anchor_count": len(anchors),
        },
        "wire_rows": wire_rows,
        "wire_fields": WIRE_FIELDS,
        "recovery_rows": recovery_rows,
        "recovery_fields": recovery_fields,
        "cache_rows": cache_rows,
        "cache_fields": cache_fields,
        "decisions": {
            "CLASSIFIER_REQUIRED_FOR_FIRST_FDT_ARM": False,
            "CLASSIFIER_REQUIRED_FOR_FACTORY_PRESERVATION": False,
            "CLASSIFIER_REQUIRED_FOR_OEM_HOST_FIDELITY": True,
            "CLASSIFIER_FDT_TABLE_EFFECT": "NONE",
            "CLASSIFIER_FINAL_0x32_PAYLOAD_EFFECT": "NONE",
            "CLASSIFIER_ADDITIONAL_DEVICE_COMMANDS": "NONE",
            "CLASSIFIER_RETRY_OR_REBUILD_EFFECT": "NONE",
            "CLASSIFIER_ERROR_RECOVERY_COMMANDS": "NONE",
            "CAUSAL_OBSERVABILITY_FROM_MCU": "NONE_FOR_MINIMAL_DEVICE_CONTRACT",
            "OEM_CACHE_WRITE_BEFORE_FINAL_0x32": "CONDITIONAL",
            "OEM_CACHE_WRITE_AFTER_FINAL_0x32": False,
            "OEM_CACHE_WRITE_REQUIRED_FOR_FINAL_0x32": False,
            "OEM_CACHE_WRITE_REQUIRED_FOR_DEVICE_PROGRESS": False,
            "LINUX_FIRST_LIVE_CACHE_WRITE_POLICY": "DISABLED",
        },
        "safety": {
            "REAL_USB_OPEN_COUNT": 0,
            "REAL_CAPTURE_COUNT": 0,
            "REAL_HARDWARE_ACTION_COUNT": 0,
            "REAL_COMMAND_SEND_COUNT": 0,
            "PERSISTENT_WRITE_FAMILY_COUNT": 0,
        },
    }


def write_outputs(repo: Path, output_dir: Path) -> dict[str, object]:
    result = audit(repo)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "D259_post_classifier_wire_effect_matrix.csv").write_text(
        csv_text(result["wire_rows"], tuple(result["wire_fields"])), encoding="utf-8")
    (output_dir / "D259_post_classifier_wire_effect_matrix.md").write_text(
        "# D259 post-classifier wire-effect matrix\n\n" +
        markdown_table(result["wire_rows"], tuple(result["wire_fields"])), encoding="utf-8")
    (output_dir / "D259_error_recovery_matrix.csv").write_text(
        csv_text(result["recovery_rows"], tuple(result["recovery_fields"])), encoding="utf-8")
    (output_dir / "D259_error_recovery_matrix.md").write_text(
        "# D259 classifier/error recovery matrix\n\n" +
        markdown_table(result["recovery_rows"], tuple(result["recovery_fields"])), encoding="utf-8")
    (output_dir / "D259_cache_effect_matrix.csv").write_text(
        csv_text(result["cache_rows"], tuple(result["cache_fields"])), encoding="utf-8")
    (output_dir / "D259_cache_effect_matrix.md").write_text(
        "# D259 cache-effect matrix\n\n" +
        markdown_table(result["cache_rows"], tuple(result["cache_fields"])), encoding="utf-8")
    (output_dir / "D259_post_classifier_audit.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--output-dir", type=Path, default=Path("analysis/D259"))
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output_dir = args.output_dir if args.output_dir.is_absolute() else repo / args.output_dir
    write_outputs(repo, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
