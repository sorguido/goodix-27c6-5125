#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Corrective evidence-metadata tests for D273 (offline, no USB, no secrets).

Verifies the two corrective findings:

1. Rocky provenance in the D273 evidence matrix equals the canonical commit
   read programmatically from Rockytkg/PROVENANCE.md (no second hard-coded
   normative source).
2. The regenerated capture census preserves the exact wire control and no
   longer fabricates a universal logical_control via wire & 0xfe masking:
     - an odd control such as D1 wire 0xd1 is NOT published as logical 0xd0;
     - packet 249 stays classified A0_0X50_NAV_RESPONSE with exact data;
     - the NAV classifier matches the exact wire control 0x50 only (no parity
       mask); a synthetic wire 0x51 is NOT classified as A0_0X50_NAV_RESPONSE;
     - a source guard fails closed if the residual `wire_control & 0xfe`
       pattern reappears in the D273 audit script;
     - ACK echo/status are preserved (observed echo used as logical control);
     - the census regeneration is deterministic;
     - no B0 plaintext/raster/payload content is serialized.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "analysis/D273/d273_01_offline_capture_audit.py"
PROVENANCE = ROOT / "Rockytkg/PROVENANCE.md"
MATRIX = ROOT / "analysis/D273/D273_01_multiframe_evidence_matrix.json"

FAILED = []


def _fail(name: str, detail: str) -> None:
    FAILED.append((name, detail))
    print(f"FAIL {name}: {detail}")


def _pass(name: str) -> None:
    print(f"PASS {name}")


def canonical_rocky_commit() -> str:
    text = PROVENANCE.read_text(encoding="utf-8")
    match = re.search(r"Preserved upstream commit:\s*`([0-9a-f]+)`", text)
    if not match:
        raise RuntimeError("canonical_rocky_commit_not_found_in_provenance")
    return match.group(1)


def generate_census() -> str:
    handle = tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, dir=str(ROOT / "analysis/D273")
    )
    handle.close()
    path = Path(handle.name)
    try:
        subprocess.run(
            [sys.executable, str(AUDIT), "--output", str(path)],
            check=True,
            cwd=str(ROOT),
        )
        return path.read_text(encoding="utf-8")
    finally:
        path.unlink(missing_ok=True)


def _load_audit_module():
    import importlib.util as _iu

    spec = _iu.spec_from_file_location("d273_audit_corrective", AUDIT)
    if spec is None or spec.loader is None:
        raise RuntimeError("audit_module_import_failed")
    module = _iu.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _synthetic_nav_frame(wire_control: int) -> dict:
    raw = bytearray(10)
    raw[0] = 0xA0
    raw[4] = wire_control
    # inner length 2410 (0x096A) avoids the FDT_IRQ branch (length == 17)
    raw[5] = 0x6A
    raw[6] = 0x09
    return {
        "raw": bytes(raw),
        "outer_type": "0xa0",
        "expected_len": 2417,
        "first_packet_index": 999,
    }


def test_nav_classifier_synthetic_positive() -> None:
    name = "nav_classifier_wire_0x50_positive"
    module = _load_audit_module()
    meta = module._frame_metadata(_synthetic_nav_frame(0x50), "device_to_host")
    if meta.get("classification") != "A0_0X50_NAV_RESPONSE":
        _fail(name, f"classification={meta.get('classification')}")
        return
    _pass(name)


def test_nav_classifier_synthetic_negative() -> None:
    name = "nav_classifier_wire_0x51_not_nav"
    module = _load_audit_module()
    meta = module._frame_metadata(_synthetic_nav_frame(0x51), "device_to_host")
    if meta.get("classification") == "A0_0X50_NAV_RESPONSE":
        _fail(name, "wire 0x51 falsely classified as A0_0X50_NAV_RESPONSE")
        return
    if meta.get("classification") != "A0_COMMAND_OR_RESPONSE":
        _fail(name, f"unexpected non-NAV classification {meta.get('classification')}")
        return
    _pass(name)


def test_source_guard_no_mask() -> None:
    name = "audit_source_guard_no_wire_control_mask"
    text = AUDIT.read_text(encoding="utf-8")
    for pattern in ("wire_control & 0xfe", "wire_control & 0xFE"):
        if pattern in text:
            _fail(name, f"residual mask pattern present: {pattern}")
            return
    _pass(name)


def test_rocky_provenance() -> None:
    name = "rocky_provenance_aligned_to_canonical"
    canonical = canonical_rocky_commit()
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    recorded = matrix["sources"]["rocky_snapshot_commit"]
    if recorded == canonical:
        _pass(name)
    else:
        _fail(name, f"recorded={recorded} canonical={canonical}")


def test_no_generic_wire_to_logical_mask(census: dict) -> None:
    name = "no_generic_wire_to_logical_mask"
    for capture in census["captures"]:
        for frame in capture["frames"]:
            if frame["classification"] == "B0_TLS_RECORD_CONTENT_OMITTED":
                continue
            wire = frame.get("wire_control")
            logical = frame.get("logical_control")
            if wire is None:
                continue
            wire_int = int(wire, 16)
            if frame["classification"] == "A0_COMMAND_ACK":
                # ACK logical control must equal the observed echo, never a mask.
                if logical != frame.get("ack_echo"):
                    _fail(name, f"ack logical != echo at {frame['packet_index']}")
                    return
                continue
            # Every non-ACK frame must NOT expose a masked logical_control.
            masked = f"0x{wire_int & 0xfe:02x}"
            if logical == masked and logical != wire:
                _fail(
                    name,
                    f"fabricated mask at packet {frame['packet_index']} "
                    f"wire={wire} logical={logical}",
                )
                return
    _pass(name)


def test_odd_control_not_falsely_derived(census: dict) -> None:
    name = "odd_control_d1_not_falsely_derived_as_d0"
    found = False
    for frame in census["captures"][0]["frames"]:
        if frame.get("wire_control") == "0xd1":
            found = True
            logical = frame.get("logical_control")
            if logical == "0xd0":
                _fail(name, "D1 wire 0xd1 published as logical 0xd0")
                return
            if logical not in (None, "NOT_DERIVED"):
                _fail(name, f"D1 logical unexpectedly {logical}")
                return
    if not found:
        _fail(name, "D1 wire 0xd1 frame not present in positive capture")
        return
    _pass(name)


def test_packet_249(census: dict) -> None:
    name = "packet_249_nav_classification_preserved"
    p249 = census["post_0x50_packet_249"]
    expected = {
        "outer_wrapper": "0xa0",
        "wire_control": "0x50",
        "physical_length": 2417,
        "declared_inner_length": 2410,
    }
    for key, value in expected.items():
        if p249.get(key) != value:
            _fail(name, f"{key}={p249.get(key)} expected {value}")
            return
    if p249.get("classification") != "A0_0X50_NAV_RESPONSE":
        _fail(name, f"classification={p249.get('classification')}")
        return
    _pass(name)


def test_ack_echo_status_preserved(census: dict) -> None:
    name = "ack_echo_status_preserved"
    acks = [
        frame
        for capture in census["captures"]
        for frame in capture["frames"]
        if frame["classification"] == "A0_COMMAND_ACK"
    ]
    if not acks:
        _fail(name, "no ACK frames found")
        return
    for ack in acks:
        if "ack_echo" not in ack or "ack_status" not in ack:
            _fail(name, f"ack missing echo/status at {ack['packet_index']}")
            return
    _pass(name)


def test_no_payload_serialized(census: dict) -> None:
    name = "no_b0_plaintext_raster_payload_serialized"
    forbidden = {"content", "plaintext", "raster", "payload", "image"}
    for capture in census["captures"]:
        for frame in capture["frames"]:
            extra = forbidden & set(frame.keys())
            if extra:
                _fail(name, f"forbidden key {extra} at {frame['packet_index']}")
                return
            if frame["classification"] == "B0_TLS_RECORD_CONTENT_OMITTED":
                allowed = {
                    "packet_index",
                    "direction",
                    "outer_wrapper",
                    "physical_length",
                    "declared_outer_length",
                    "classification",
                }
                if not set(frame.keys()) <= allowed:
                    _fail(name, f"b0 extra keys {set(frame.keys()) - allowed}")
                    return
    _pass(name)


def test_determinism() -> None:
    name = "capture_census_deterministic"
    first = generate_census()
    second = generate_census()
    if first == second:
        _pass(name)
    else:
        _fail(name, "census byte content differs across regenerations")
    return first


def main() -> int:
    import argparse

    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--json", type=Path)
    args = argument_parser.parse_args()

    test_rocky_provenance()
    census_text = test_determinism()
    census = json.loads(census_text)
    test_no_generic_wire_to_logical_mask(census)
    test_odd_control_not_falsely_derived(census)
    test_packet_249(census)
    test_ack_echo_status_preserved(census)
    test_no_payload_serialized(census)
    test_nav_classifier_synthetic_positive()
    test_nav_classifier_synthetic_negative()
    test_source_guard_no_mask()
    print()
    if FAILED:
        print(f"{len(FAILED)} corrective check(s) FAILED")
        status = "FAIL"
    else:
        print("ALL CORRECTIVE CHECKS PASSED")
        status = "PASS"
    if args.json:
        payload = {
            "artifact": "D273_01_evidence_metadata_corrective_test_results",
            "execution_mode": "OFFLINE_ONLY_NO_USB_NO_SECRET",
            "status": status,
            "checks": [
                {
                    "name": name,
                    "status": "PASS" if not any(n == name for n, _ in FAILED) else "FAIL",
                }
                for name in (
                    "rocky_provenance_aligned_to_canonical",
                    "capture_census_deterministic",
                    "no_generic_wire_to_logical_mask",
                    "odd_control_d1_not_falsely_derived_as_d0",
                    "packet_249_nav_classification_preserved",
                    "ack_echo_status_preserved",
                    "no_b0_plaintext_raster_payload_serialized",
                    "nav_classifier_wire_0x50_positive",
                    "nav_classifier_wire_0x51_not_nav",
                    "audit_source_guard_no_wire_control_mask",
                )
            ],
            "real_usb_open_count": 0,
            "real_command_send_count": 0,
            "real_secret_materialization_count": 0,
            "real_fprintd_mutation_count": 0,
            "real_biometric_capture_count": 0,
            "persistent_device_write_count": 0,
        }
        args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
