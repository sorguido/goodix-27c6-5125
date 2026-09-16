#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Mechanically derive the bounded D259 post-classifier control-flow proof."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Iterable


DLL = Path("analysis/D230/work/GoodixExport/gfusb.dll")
DISASM = Path("analysis/D230/work/GoodixExport/gfusb_static_refs/gfusb_disasm.txt")
STRINGS = Path("analysis/D230/work/GoodixExport/gfusb_static_refs/gfusb_strings_utf16_off.txt")
D255_CAPTURE = Path("captures/D255_20260822T205631772Z_85c8c41f/raw/wire.pcapng")
EXPECTED_DLL_SHA256 = "904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2"
EXPECTED_D255_CAPTURE_SHA256 = "802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c"

# Extraction coordinates only: semantic rows are derived below from parsed
# instructions, not encoded here.
RANGES = {
    "caller_update_then_final_arm": (0x180068940, 0x180068ADA),
    "gf_update_all_base_initialization": (0x180068ADC, 0x180068B35),
    "post_classifier_switches_and_return": (0x18006935D, 0x18006987C),
    "classifier_result_host_state_helper": (0x1800225E8, 0x180022653),
    "classifier_result_pure_mapper": (0x180021B54, 0x180021C5D),
    "classifier_nav_and_image_wrappers": (0x180023FA8, 0x18002400E),
    "final_0x32_mode3_fdt_table_builder": (0x1800251BA, 0x180025304),
}
FDT_TABLE_GLOBAL = "0x180580818"
RESULT_SLOT = "[rsp+0x44]"
SWITCH_SPECS = {
    "NAV": (0x180069383, "[rsp+0x54]", "[rsp+0x68]", 0x1800693D8,
            0x1800694FA, 0x180069531, "0x18059fa88"),
    "IMAGE": (0x18006953D, "[rsp+0x58]", "[rsp+0x6c]", 0x180069592,
              0x1800696B4, 0x180069727, "0x18059fa78"),
}
CALL_CLASSES = {
    0x18000CED8: "HOST_LOGGING",
    0x18007B1F0: "HOST_RAM_COPY",
    0x1800225E8: "HOST_RESULT_STATE_HELPER",
    0x180021B54: "PURE_RESULT_MAPPER_NO_CALLS",
    0x180023FA8: "HOST_IMAGE_CLASSIFIER_WRAPPER",
    0x180023FDC: "HOST_NAV_CLASSIFIER_WRAPPER",
    0x180022654: "HOST_COMMON_CLASSIFIER",
    0x180067F44: "HOST_CACHE_SAVE_GOODIX_DAT",
    0x18007A320: "HOST_STACK_COOKIE_CHECK",
}
WIRE_FIELDS = (
    "classifier", "return", "case_target", "merge_point",
    "branch_jump_targets", "branch_calls", "gf_update_all_base_result",
    "host_ram_effect", "fdt_table_effect", "final_0x32_payload_effect",
    "additional_usb_commands", "retry_or_rebuild", "recovery_command",
    "cache_write_effect", "final_0x32_reachable", "derivation_mode",
)


@dataclass(frozen=True)
class Instruction:
    address: int
    mnemonic: str
    operands: str
    text: str


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


def parse_disassembly(text: str) -> dict[int, Instruction]:
    result = {}
    for raw in text.splitlines():
        parts = raw.strip().split("\t")
        if len(parts) < 3 or not parts[0].endswith(":"):
            continue
        try:
            address = int(parts[0][:-1], 16)
        except ValueError:
            continue
        rendered = parts[-1].strip()
        pieces = rendered.split(None, 1)
        if not pieces or not re.fullmatch(r"[a-z][a-z0-9]*", pieces[0]):
            continue
        result[address] = Instruction(
            address, pieces[0].lower(), pieces[1].strip() if len(pieces) == 2 else "",
            raw.rstrip(),
        )
    return result


def bounded(rows: dict[int, Instruction], start: int, end: int) -> list[Instruction]:
    return [rows[address] for address in sorted(rows) if start <= address <= end]


def successor(rows: dict[int, Instruction], address: int) -> Instruction:
    candidates = [candidate for candidate in rows if candidate > address]
    require(bool(candidates), f"missing successor after 0x{address:x}")
    return rows[min(candidates)]


def target(row: Instruction) -> int | None:
    if row.mnemonic not in {"call", "jmp", "je", "jne", "jz", "jnz"}:
        return None
    match = re.fullmatch(r"0x([0-9a-f]+)", row.operands)
    return int(match.group(1), 16) if match else None


def jumps(rows: Iterable[Instruction]) -> list[dict[str, str]]:
    return [{
        "source": f"0x{row.address:x}", "kind": row.mnemonic,
        "target": f"0x{target(row):x}" if target(row) is not None else "UNRESOLVED",
    } for row in rows if row.mnemonic.startswith("j")]


def call_rows(rows: Iterable[Instruction]) -> list[dict[str, str]]:
    result = []
    for row in rows:
        if row.mnemonic != "call":
            continue
        destination = target(row)
        result.append({
            "address": f"0x{row.address:x}",
            "target": f"0x{destination:x}" if destination is not None else "INDIRECT",
            "classification": CALL_CLASSES.get(destination, "UNRESOLVED"),
        })
    return result


def walk_to(rows: dict[int, Instruction], start: int, stop: int) -> list[Instruction]:
    current, seen, path = start, set(), []
    while current != stop:
        require(current in rows and current not in seen, f"unresolved case path at 0x{current:x}")
        seen.add(current)
        row = rows[current]
        path.append(row)
        if row.mnemonic == "jmp":
            require(target(row) is not None, f"indirect case jump at 0x{current:x}")
            current = int(target(row))
        else:
            current = successor(rows, current).address
    return path


def derive_switch(rows: dict[int, Instruction], name: str) -> dict[str, object]:
    call, return_slot, switch_slot, start, merge, keep, base_global = SWITCH_SPECS[name]
    region = bounded(rows, start, merge)
    cases, comparisons = {}, []
    for index, row in enumerate(region[:-1]):
        match = re.fullmatch(rf"DWORD PTR {re.escape(switch_slot)},0x([0-9a-f]+)", row.operands)
        if not match:
            continue
        branch = region[index + 1]
        require(branch.mnemonic in {"je", "jz"} and target(branch) is not None,
                f"{name} equality branch unresolved")
        value = int(match.group(1), 16)
        cases[value] = int(target(branch))
        comparisons.append({"compare": f"0x{row.address:x}", "return": value,
                            "jump": f"0x{branch.address:x}",
                            "target": f"0x{target(branch):x}"})
    require(set(cases) == {0, 1, 2, 3}, f"{name} cases not derived")
    default_rows = [row for row in region if row.address < min(cases.values())
                    and row.mnemonic == "jmp" and target(row) == merge]
    require(len(default_rows) == 1, f"{name} default target unresolved")
    keep_match = re.fullmatch(
        rf"DWORD PTR {re.escape(return_slot)},0x([0-9a-f]+)", rows[merge].operands
    )
    require(keep_match is not None, f"{name} merge comparison unresolved")
    keep_value = int(keep_match.group(1), 16)
    keep_jump = successor(rows, merge)
    require(keep_jump.mnemonic in {"je", "jz"} and target(keep_jump) == keep,
            f"{name} keep path unresolved")
    copy_path = walk_to(rows, successor(rows, keep_jump.address).address, keep)
    require(any(item["classification"] == "HOST_RAM_COPY" for item in call_rows(copy_path)),
            f"{name} RAM copy not derived")
    require(any("BYTE PTR [rsp+0x41],0x1" in row.operands for row in copy_path),
            f"{name} dirty write not derived")
    require(any(base_global in row.operands for row in copy_path), f"{name} base global missing")
    derived = []
    labels = [(str(value), cases[value]) for value in sorted(cases)]
    labels.append(("negative_or_other", merge))
    for label, case_target in labels:
        arm = [] if case_target == merge else walk_to(rows, case_target, merge)
        keep_existing = label != "negative_or_other" and int(label) == keep_value
        effect = [] if keep_existing else copy_path
        derived.append({
            "return": label, "case_target": f"0x{case_target:x}",
            "merge_point": f"0x{merge:x}", "case_arm_jump_edges": jumps(arm),
            "case_arm_calls": call_rows(arm), "effect_path_calls": call_rows(effect),
            "host_ram_effect": "KEEP_EXISTING_BASE" if keep_existing else "COPY_ACQUIRED_BASE",
            "dirty_flag_effect": "UNCHANGED_BY_CLASSIFIER" if keep_existing else "SETS_SHARED_DIRTY_FLAG",
        })
    return {
        "classifier": name, "classifier_call": f"0x{call:x}",
        "return_slot": return_slot, "switch_slot": switch_slot,
        "switch_start": f"0x{start:x}", "merge_point": f"0x{merge:x}",
        "compare_jump_derivation": comparisons,
        "default_jump": f"0x{default_rows[0].address:x}",
        "default_target": f"0x{merge:x}",
        "post_merge_keep_jump": f"0x{keep_jump.address:x}",
        "post_merge_keep_target": f"0x{keep:x}", "cases": derived,
        "post_merge_keep_value": keep_value,
    }


def csv_text(rows: list[dict[str, object]], fields: tuple[str, ...]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader(); writer.writerows(rows)
    return output.getvalue()


def markdown_table(rows: list[dict[str, object]], fields: tuple[str, ...]) -> str:
    lines = ["| " + " | ".join(fields) + " |",
             "| " + " | ".join("---" for _ in fields) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row[field]).replace("|", "\\|") for field in fields) + " |")
    return "\n".join(lines) + "\n"


def audit(repo: Path) -> dict[str, object]:
    dll, capture, disasm_path = repo / DLL, repo / D255_CAPTURE, repo / DISASM
    require(sha256_file(dll) == EXPECTED_DLL_SHA256, "gfusb.dll hash gate failed")
    require(sha256_file(capture) == EXPECTED_D255_CAPTURE_SHA256, "D255 capture hash gate failed")
    rows = parse_disassembly(disasm_path.read_text(encoding="utf-8", errors="replace"))
    strings = (repo / STRINGS).read_text(encoding="utf-8", errors="replace")
    require("2415a0 goodix.dat" in strings and "4e72c0 gf_savebaseTofile" in strings,
            "host cache provenance anchors missing")
    extracts = {label: bounded(rows, *limits) for label, limits in RANGES.items()}
    require(all(extracts.values()), "bounded extraction range empty")
    switches = {name: derive_switch(rows, name) for name in SWITCH_SPECS}
    wrapper_calls = call_rows(extracts["classifier_nav_and_image_wrappers"])
    require(wrapper_calls and all(call["classification"] == "HOST_COMMON_CLASSIFIER"
                                  for call in wrapper_calls),
            "classifier wrapper call graph changed")
    helper_calls = call_rows(extracts["classifier_result_host_state_helper"])
    require(len(helper_calls) == 1
            and helper_calls[0]["classification"] == "PURE_RESULT_MAPPER_NO_CALLS",
            "classifier result helper call graph changed")
    require(not call_rows(extracts["classifier_result_pure_mapper"]),
            "classifier pure result mapper gained a call")

    post = extracts["post_classifier_switches_and_return"]
    result_writes = [row for row in post if row.mnemonic == "mov"
                     and row.operands.startswith(f"DWORD PTR {RESULT_SLOT},")]
    require(not result_writes, "classifier region changes result flag")
    require(any(row.operands == f"DWORD PTR {RESULT_SLOT},0x1"
                for row in extracts["gf_update_all_base_initialization"]),
            "success initialization missing")
    return_reads = [row for row in post if row.operands == f"eax,DWORD PTR {RESULT_SLOT}"]
    require({row.address for row in return_reads} >= {0x18006981C, 0x180069860},
            "return reads missing")

    caller = extracts["caller_update_then_final_arm"]
    indexed = {row.address: row for row in caller}
    require(target(indexed[0x18006898A]) == 0x180068ADC, "caller target changed")
    require(indexed[0x180068991].mnemonic == "jne"
            and target(indexed[0x180068991]) == 0x180068A40, "success branch changed")
    require(indexed[0x180068AB7].operands == "r8b,0x1"
            and indexed[0x180068ABA].operands == "dl,0x1"
            and indexed[0x180068ABC].operands == "cl,0x3"
            and indexed[0x180068ABE].mnemonic == "call", "final SetMode(3,1,1) changed")

    classifier_region = bounded(rows, 0x180069377, 0x1800697E6)
    require(not any(FDT_TABLE_GLOBAL in row.operands for row in classifier_region),
            "classifier region references FDT table")
    builder_refs = [row for row in extracts["final_0x32_mode3_fdt_table_builder"]
                    if FDT_TABLE_GLOBAL in row.operands]
    require([row.address for row in builder_refs] == [0x1800252C0],
            "mode-3 FDT table builder read changed")
    post_calls = call_rows(bounded(rows, 0x1800693D8, 0x1800697E6))
    unresolved = [row for row in post_calls if row["classification"] == "UNRESOLVED"]
    require(not unresolved, f"unresolved post-classifier calls: {unresolved}")
    forward_only = all(target(row) is None or int(target(row)) >= row.address
                       for row in classifier_region if row.mnemonic.startswith("j"))
    require(forward_only, "backward classifier control-flow edge found")

    wire_rows = []
    for switch in switches.values():
        for case in switch["cases"]:
            case_calls = (*case["case_arm_calls"], *case["effect_path_calls"])
            wire_rows.append({
                "classifier": switch["classifier"], "return": case["return"],
                "case_target": case["case_target"], "merge_point": case["merge_point"],
                "branch_jump_targets": ";".join(edge["target"] for edge in case["case_arm_jump_edges"]) or "FALLTHROUGH_TO_MERGE",
                "branch_calls": ";".join(f"{call['address']}->{call['target']}:{call['classification']}" for call in case_calls) or "NONE",
                "gf_update_all_base_result": "1_SUCCESS_UNCHANGED",
                "host_ram_effect": case["host_ram_effect"], "fdt_table_effect": "NONE",
                "final_0x32_payload_effect": "NONE", "additional_usb_commands": "NONE",
                "retry_or_rebuild": "NONE_FROM_FORWARD_ONLY_CFG", "recovery_command": "NONE",
                "cache_write_effect": case["dirty_flag_effect"],
                "final_0x32_reachable": "YES_VIA_CALLER_NONZERO_BRANCH",
                "derivation_mode": "PARSED_DISASSEMBLY_CFG",
            })

    recovery_rows = [{
        "condition": "all_mechanically_enumerated_NAV_and_IMAGE_returns",
        "gf_update_all_base_result": "1_SUCCESS_UNCHANGED",
        "final_0x32": "REACHABLE_VIA_CALLER_JNE_0x180068a40",
        "retry_or_rebuild": "NONE_FORWARD_ONLY_POST_CLASSIFIER_CFG",
        "a2_reentry": 0, "0x70_reentry": 0, "other_recovery_command": "NONE",
        "derivation": "parsed_switch_edges+no_result_write+classified_call_targets",
    }]
    cache_rows = [{
        "phase": "before_final_0x32", "condition": "parsed_dirty_flag_nonzero",
        "oem_effect": "HOST_CACHE_SAVE_GOODIX_DAT_CONDITIONAL",
        "linux_first_live_policy": "DISABLED", "required_for_final_0x32": False,
        "required_for_device_progress": False, "host_cache_write_count_in_minimal_candidate": 0,
        "derivation": "0x1800697d8 test -> 0x1800697e1 host cache call; caller arm later",
    }]
    cfg = {
        "schema": "D259_POST_CLASSIFIER_CFG_V2",
        "derivation_mode": "BOUNDED_PARSED_OBJDUMP_TEXT_HASH_GATED",
        "ranges": {label: {
            "start": f"0x{limits[0]:x}", "end": f"0x{limits[1]:x}",
            "instruction_count": len(extracts[label]), "jump_edges": jumps(extracts[label]),
            "calls": call_rows(extracts[label]),
        } for label, limits in RANGES.items()},
        "switches": switches,
        "result_flag": {"slot": RESULT_SLOT, "initialized_success_at": "0x180068b21",
                        "post_classifier_writes": [],
                        "return_reads": [f"0x{row.address:x}" for row in return_reads]},
        "caller": {"gf_update_all_base_call": "0x18006898a->0x180068adc",
                   "success_branch": "0x180068991 jne 0x180068a40",
                   "final_call": "0x180068abe INDIRECT ChicagoHUSetMode(3,1,1)"},
        "fdt_table": {"global": FDT_TABLE_GLOBAL, "classifier_region_references": [],
                      "final_mode3_builder_reads": [f"0x{row.address:x}" for row in builder_refs]},
        "post_classifier_calls": post_calls, "unresolved_post_classifier_calls": unresolved,
        "device_or_usb_calls": [], "post_classifier_cfg_forward_only": forward_only,
    }
    return {
        "schema": "D259_POST_CLASSIFIER_AUDIT_V2", "execution_mode": "OFFLINE_ONLY",
        "hash_gates": {"gfusb_sha256": sha256_file(dll),
                       "d255_capture_sha256": sha256_file(capture),
                       "disassembly_sha256": sha256_file(disasm_path)},
        "cfg": cfg, "excerpt_ranges": {key: [row.text for row in value] for key, value in extracts.items()},
        "wire_rows": wire_rows, "wire_fields": WIRE_FIELDS,
        "recovery_rows": recovery_rows, "recovery_fields": tuple(recovery_rows[0]),
        "cache_rows": cache_rows, "cache_fields": tuple(cache_rows[0]),
        "decisions": {
            "POST_CLASSIFIER_BRANCH_PROOF": "PASS_MECHANICALLY_DERIVED",
            "BRANCH_MATRIX_DERIVATION_MODE": "PARSED_DISASSEMBLY_CFG",
            "NAV_RETURN_CFG_PROVEN": True, "IMAGE_RETURN_CFG_PROVEN": True,
            "CLASS_A_CLASSIFIER_HOST_ONLY_FOR_FIRST_ARM": True,
            "CLASSIFIER_CHANGES_GF_UPDATE_ALL_BASE_SUCCESS": False,
            "CLASSIFIER_CHANGES_FDT_TABLE": False,
            "CLASSIFIER_CHANGES_FINAL_0x32_PAYLOAD": False,
            "CLASSIFIER_EMITS_ADDITIONAL_DEVICE_COMMAND": False,
            "CLASSIFIER_CAUSES_RETRY_OR_REBUILD": False,
            "CLASSIFIER_CAUSES_RECOVERY": False, "CLASSIFIER_BLOCKS_FINAL_0x32": False,
            "CLASSIFIER_CHANGES_HOST_BASE_RAM": True,
            "CLASSIFIER_CHANGES_HOST_CACHE_DIRTY_STATE": True,
            "OEM_CACHE_WRITE_CONDITIONAL": True,
            "OEM_CACHE_WRITE_BEFORE_FINAL_0x32": "CONDITIONAL",
            "OEM_CACHE_WRITE_AFTER_FINAL_0x32": False,
            "OEM_CACHE_WRITE_REQUIRED_FOR_FINAL_0x32": False,
            "OEM_CACHE_WRITE_REQUIRED_FOR_DEVICE_PROGRESS": False,
            "LINUX_FIRST_LIVE_CACHE_WRITE_POLICY": "DISABLED",
        },
        "safety": {"REAL_USB_OPEN_COUNT": 0, "REAL_CAPTURE_COUNT": 0,
                   "REAL_HARDWARE_ACTION_COUNT": 0, "REAL_COMMAND_SEND_COUNT": 0,
                   "PERSISTENT_WRITE_FAMILY_COUNT": 0},
    }


def excerpt_text(result: dict[str, object]) -> str:
    gates = result["hash_gates"]
    lines = ["D259 POST-CLASSIFIER BOUNDED DISASSEMBLY EXCERPT",
             "EXECUTION_MODE=OFFLINE_ONLY", f"SOURCE={DISASM}",
             f"GFUSB_DLL_SHA256={gates['gfusb_sha256']}",
             f"DISASSEMBLY_SHA256={gates['disassembly_sha256']}",
             "NOTE=Only hash-gated D258/D259 ranges required for the bounded proof follow."]
    for label, extracted in result["excerpt_ranges"].items():
        start, end = RANGES[label]
        lines.extend(("", f"[{label}] 0x{start:x}..0x{end:x}", *extracted))
    return "\n".join(lines) + "\n"


def write_outputs(repo: Path, output_dir: Path) -> dict[str, object]:
    result = audit(repo)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "D259_post_classifier_disasm_excerpt.txt").write_text(excerpt_text(result), encoding="utf-8")
    (output_dir / "D259_post_classifier_cfg.json").write_text(json.dumps(result["cfg"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for stem, rows_key, fields_key, title in (
        ("D259_post_classifier_wire_effect_matrix", "wire_rows", "wire_fields", "mechanically derived post-classifier wire-effect"),
        ("D259_error_recovery_matrix", "recovery_rows", "recovery_fields", "mechanically derived classifier/error recovery"),
        ("D259_cache_effect_matrix", "cache_rows", "cache_fields", "mechanically derived cache-effect"),
    ):
        fields = tuple(result[fields_key])
        (output_dir / f"{stem}.csv").write_text(csv_text(result[rows_key], fields), encoding="utf-8")
        (output_dir / f"{stem}.md").write_text(f"# D259 {title} matrix\n\n" + markdown_table(result[rows_key], fields), encoding="utf-8")
    serializable = {key: value for key, value in result.items() if key != "excerpt_ranges"}
    (output_dir / "D259_post_classifier_audit.json").write_text(json.dumps(serializable, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--output-dir", type=Path, default=Path("analysis/D259"))
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = args.output_dir if args.output_dir.is_absolute() else repo / args.output_dir
    write_outputs(repo, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
