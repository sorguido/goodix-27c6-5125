#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline consistency and xref checks for D278/08."""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
D278 = ROOT / "analysis" / "D278"
AUDIT = D278 / "D278_08_project8_e4_indirect_edge_audit.md"
GRAPH = D278 / "D278_08_project8_e4_failure_graph.md"
EDGES = D278 / "D278_08_project8_e4_edges.csv"
DISASM = (
    ROOT
    / "analysis"
    / "D230"
    / "work"
    / "GoodixExport"
    / "gfusb_static_refs"
    / "gfusb_disasm.txt"
)
DLL = ROOT / "analysis" / "D230" / "work" / "GoodixExport" / "gfusb.dll"

SCHEMA = [
    "edge_id",
    "source_va",
    "target_va",
    "edge_kind",
    "project_condition",
    "assignment_site",
    "slot_or_table",
    "branch_condition",
    "success_or_failure",
    "return_value",
    "wire_effect",
    "persistent_effect_risk",
    "evidence_class",
    "notes",
]
EVIDENCE = {"OBSERVED", "VERIFIED", "INFERRED", "HYPOTHESIZED", "UNKNOWN"}
VA = re.compile(r"^0x[0-9a-f]+$")

REQUIRED_MARKERS = {
    "OUTCOME": "READY",
    "EXECUTABLE_CLOSURE": "ANALYSIS_ONLY",
    "CANONICAL_DOCUMENTATION": "UPDATED",
    "D278_08_BASELINE": "4c73dcdaad5df9f9a429626109a4be2a3b1a8b19",
    "OEM_A8_FAILURE_POLICY": "RESOLVED",
    "OEM_USES_A2_SENSOR_ONLY_AS_PRE_A8_FAILURE_RECOVERY": "false",
    "A2_PRE_A8_RECOVERY_LIVE_JUSTIFIED": "false",
    "A8_RETRY_BOUND_RUNTIME_VALUE": "UNKNOWN_CONFIG_BYTE_AT_OFFSET_0x45A",
    "PROJECT8_E4_SENDER_RESOLVED": "true",
    "PROJECT8_E4_INDIRECT_EDGE_RESOLVED": "true",
    "PROJECT8_E4_FAILURE_RETURN_PROPAGATION_RESOLVED": "true",
    "PROJECT8_E4_RETRY_BOUND_RESOLVED": "true",
    "PROJECT8_E4_PRE_FAILURE_PERSISTENT_WRITE_REACHABLE": "true",
    "PROJECT8_E4_POST_FAILURE_PERSISTENT_WRITE_REACHABLE": "true",
    "PROJECT8_E4_FAILURE_PATH_FACTORY_PRESERVING": "false",
    "OEM_E4_FAILURE_POLICY": "RESOLVED",
    "OEM_PRE_D1_FAILURE_RECOVERY": "RESOLVED",
    "LINUX_SAFE_E4_RECOVERY_CANDIDATE": "false",
    "REAL_USB_ACCESS": "false",
    "LIVE_EXECUTION_PERFORMED": "false",
    "CURRENT_LIVE_AUTHORIZED": "false",
    "READY_FOR_LIVE": "false",
    "RETRY_AUTHORIZED": "false",
}

# Each tuple is an instruction address and its direct target. Whitespace and
# objdump decoration are deliberately ignored; both tokens must occur nearby.
XREFS = [
    ("18006ac4c", "180064a18"),
    ("18006ac9e", "18006ad70"),
    ("18006ad78", "18006adc0"),
    ("18006ae04", "18003c348"),
    ("18003c499", "18003b514"),
    ("18003b780", "18003cc90"),
    ("18003ce0c", "18003c7f4"),
    ("18003c94c", "18005c148"),
    ("18003c9a1", "18005c148"),
    ("18003c5eb", "18003cfd8"),
    ("18003c6fb", "18003b514"),
    ("18003d6fd", "18003d8e0"),
    ("18003da2a", "18005c148"),
    ("18003dabf", "18005c148"),
    ("180065bb7", "18005c148"),
    ("180065ca4", "18000f938"),
    ("180065ced", "180059d00"),
    ("180065e3d", "18006bb3c"),
    ("180065e93", "18006bb3c"),
]

INSTRUCTION_ANCHORS = [
    ("18003c90f", "0x3e8"),
    ("18003c917", "0x1f4"),
    ("18003c938", "41 b1 02"),
    ("18003c93b", "41 b0 0e"),
    ("18003c448", "02"),
    ("18003c59a", "02"),
    ("18003da16", "45 33 c9"),
    ("18003da19", "41 b0 0e"),
]

UTF16_STRINGS = [
    "production_write_key",
    "production_write_mcu",
    "production_check_psk_is_valid",
    "production_read_specific_data",
    "production_read_mcu",
]


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def check_markers(audit: str) -> None:
    for key, value in REQUIRED_MARKERS.items():
        if f"{key}={value}" not in audit:
            fail(f"missing marker {key}={value}")
    for heading in ("### Before E4", "### On E4 success", "### On E4 failure", "### Cleanup"):
        if heading not in audit:
            fail(f"missing persistent-risk subsection {heading}")
    if "EDGE_CLASSIFICATION=DIRECT_CALL" not in audit:
        fail("missing exact edge classification")


def check_csv() -> int:
    with EDGES.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != SCHEMA:
            fail(f"CSV schema mismatch: {reader.fieldnames!r}")
        rows = list(reader)

    if not rows:
        fail("CSV contains no edges")

    ids: set[str] = set()
    signatures: dict[tuple[str, str, str], tuple[str, ...]] = {}
    for number, row in enumerate(rows, start=2):
        edge_id = row["edge_id"]
        if edge_id in ids:
            fail(f"duplicate edge_id {edge_id}")
        ids.add(edge_id)
        for field in ("source_va", "target_va"):
            if not VA.fullmatch(row[field]):
                fail(f"row {number}: non-normalized {field}={row[field]!r}")
        if row["evidence_class"] not in EVIDENCE:
            fail(f"row {number}: invalid evidence_class")
        if row["persistent_effect_risk"] not in {"true", "false", "unresolved"}:
            fail(f"row {number}: invalid persistent_effect_risk")
        signature_key = (row["source_va"], row["target_va"], row["edge_kind"])
        signature_value = tuple(row[name] for name in SCHEMA[4:])
        previous = signatures.setdefault(signature_key, signature_value)
        if previous != signature_value:
            fail(f"inconsistent duplicate edge {signature_key}")
    return len(rows)


def check_disassembly(disasm: str) -> None:
    lines = disasm.splitlines()
    for source, target in XREFS:
        matches = [line.lower() for line in lines if source in line.lower()]
        if not any(target in line for line in matches):
            fail(f"xref 0x{source} -> 0x{target} not found")

    literal_lines = [line.lower() for line in lines if "18003b77b" in line.lower()]
    if not any("03 00 02 bb" in line for line in literal_lines):
        fail("selector literal 0xbb020003 not found at 0x18003b77b")
    for address, encoding in INSTRUCTION_ANCHORS:
        matches = [line.lower() for line in lines if address in line.lower()]
        if not any(encoding in line for line in matches):
            fail(f"instruction anchor 0x{address} / {encoding!r} not found")


def check_string_provenance(dll: bytes) -> None:
    for value in UTF16_STRINGS:
        if value.encode("utf-16le") not in dll:
            fail(f"UTF-16LE provenance string {value!r} not found in gfusb.dll")


def main() -> int:
    for path in (AUDIT, GRAPH, EDGES, DISASM, DLL):
        if not path.is_file():
            fail(f"missing input {path.relative_to(ROOT)}")

    audit = AUDIT.read_text(encoding="utf-8")
    graph = GRAPH.read_text(encoding="utf-8")
    disasm = DISASM.read_text(encoding="utf-8", errors="replace")
    check_markers(audit)
    if "production_write_key" not in audit or "production_write_key" not in graph:
        fail("persistent fallback is absent from audit or graph")
    edge_count = check_csv()
    check_disassembly(disasm)
    check_string_provenance(DLL.read_bytes())
    print(f"PASS: {edge_count} normalized and consistent CSV edges")
    print(
        f"PASS: {len(XREFS)} control-flow xrefs and "
        f"{len(INSTRUCTION_ANCHORS) + 1} dataflow/instruction anchors verified"
    )
    print(f"PASS: {len(UTF16_STRINGS)} UTF-16LE function-name provenance strings verified")
    print(f"PASS: {len(REQUIRED_MARKERS)} closure markers verified")
    print("PASS: D278/08 static verification complete; no USB access performed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
