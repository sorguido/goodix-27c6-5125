#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Hash-gated D255 exact fresh-bootstrap and temporal-provenance audit.

The private pcapng/cache are read only by reference.  Outputs contain command
payloads, structural response metadata and hashes, never dynamic NAV/image
payloads, OTP, FDT seed bytes or biometric material.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import io
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

from analysis.D255 import d255_postprocess_windows_evidence as d255


D255_RUN = Path("captures/D255_20260822T205631772Z_85c8c41f")
EXPECTED_CAPTURE_SHA256 = "802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c"
EXPECTED_CACHE_SHA256 = "9f5327731cff3046e31d18356a6334c9e1494330f434f3fe75ad0a4c80db09e2"
EXPECTED_OUT_CONTROLS = (0x36, 0x50, 0x36, 0x82, 0x20, 0x36, 0x32)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_text(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def decimal_utc_delta(later: str, earlier: str) -> Decimal:
    """Return an exact decimal-second delta for ISO UTC strings."""
    def parts(value: str) -> tuple[datetime, Decimal]:
        base, fraction = value.removesuffix("Z").split(".")
        return datetime.strptime(base, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc), Decimal(f"0.{fraction}")

    later_base, later_fraction = parts(later)
    earlier_base, earlier_fraction = parts(earlier)
    return Decimal(int((later_base - earlier_base).total_seconds())) + later_fraction - earlier_fraction


def load_target(repo: Path):
    run = repo / D255_RUN
    manifest = run / "recovery_manifest.json"
    manifest_hash = (run / "recovery_manifest.json.sha256").read_text(encoding="ascii").split()[0]
    inputs = d255.load_manifest(run, manifest, manifest_hash)
    wire = next(row for row in inputs if row.role == "wire")
    require(sha256_file(wire.path) == EXPECTED_CAPTURE_SHA256, "D255 raw capture hash gate failed")
    packets = list(d255.iter_usbpcap(wire.path))
    frames = d255.split_frames(packets)
    selected, firmware, target_specific = d255.select_device(frames, None)
    require(target_specific and firmware == d255.EXPECTED_FIRMWARE, "D255 target identity gate failed")
    target = [frame for frame in frames if (frame.bus, frame.device) == selected]
    return run, inputs, wire, target


def _decoded(frame):
    parsed = d255.parse_a0(frame)
    if parsed is not None:
        return parsed[0], parsed[1]
    return None, None


def exact_timeline(repo: Path) -> dict[str, object]:
    run, _inputs, wire, target = load_target(repo)
    fresh_ae_position = None
    for position, frame in enumerate(target):
        control, data = _decoded(frame)
        if frame.direction == "IN" and control == 0xAE and data is not None and len(data) == 16:
            if data[1] & 1:
                continue
            next_out = next(
                (_decoded(candidate)[0] for candidate in target[position + 1:]
                 if candidate.direction == "OUT" and _decoded(candidate)[0] is not None),
                None,
            )
            if next_out == 0x36:
                fresh_ae_position = position
                break
    require(fresh_ae_position is not None, "fresh AF/AE boundary not found")
    af_position = max(
        position for position in range(fresh_ae_position)
        if target[position].direction == "OUT" and _decoded(target[position])[0] == 0xAF
    )

    first_arm_position = next(
        position for position in range(fresh_ae_position + 1, len(target))
        if target[position].direction == "OUT" and _decoded(target[position])[0] == 0x32
    )
    arm_ack_position = next(
        position for position in range(first_arm_position + 1, len(target))
        if target[position].direction == "IN"
        and _decoded(target[position]) == (0xB0, b"\x32\x01")
    )
    segment = target[af_position:arm_ack_position + 1]

    out_controls = tuple(
        control for frame in segment
        if frame.direction == "OUT" and (control := _decoded(frame)[0]) is not None
    )
    require(out_controls == (0xAF, *EXPECTED_OUT_CONTROLS), f"exact bootstrap OUT census changed: {out_controls!r}")

    rows: list[dict[str, object]] = []
    pending: dict[int, int] = {}
    last_request_frame: int | None = None
    manual_stage = 0
    for frame in segment:
        control, data = _decoded(frame)
        wire_control = control
        if wire_control is None and frame.outer == 0xA0 and len(frame.raw) >= 5:
            wire_control = frame.raw[4]
        event_class = ""
        correlation: int | str = ""
        payload_summary = ""
        if frame.direction == "OUT" and control is not None:
            last_request_frame = frame.packet_index + 1
            pending[control] = last_request_frame
            if control == 0xAF:
                event_class = "FRESH_AF_REQUEST"
                payload_summary = "FIXED_QUERY_WITH_TS16_REDACTED"
            elif control == 0x36:
                event_class = f"FDT36_STAGE_{manual_stage}_REQUEST"
                payload_summary = "0901||TABLE12_REDACTED"
                manual_stage += 1
            elif control == 0x50:
                event_class = "INTERSTAGE_NAV_0x50_REQUEST"
                payload_summary = data.hex()
            elif control == 0x82:
                event_class = "INTERSTAGE_FDT_DELTA_0x82_REQUEST"
                payload_summary = data.hex()
            elif control == 0x20:
                event_class = "INTERSTAGE_BASELINE_IMAGE_0x20_REQUEST"
                payload_summary = data.hex()
            elif control == 0x32:
                event_class = "FIRST_POST_BOOTSTRAP_FDT32_REQUEST"
                payload_summary = "0801||FINAL_TABLE12_REDACTED||TS16_REDACTED"
        elif frame.direction == "IN" and control == 0xB0 and data is not None and len(data) == 2:
            echo = data[0]
            require(data[1] == 1 and echo in pending, "uncorrelated exact-bootstrap ACK")
            correlation = pending[echo]
            event_class = f"ACK_0x{echo:02X}_STATUS_01"
            payload_summary = f"echo=0x{echo:02x};status=0x01"
        elif frame.direction == "IN" and control == 0xAE:
            correlation = target[af_position].packet_index + 1
            event_class = "FRESH_AE_RESPONSE"
            payload_summary = "body16;POV_VALID=false"
        elif frame.direction == "IN" and control == 0x36 and data is not None:
            prior = next(row for row in reversed(rows) if str(row["event_class"]).startswith("FDT36_STAGE_"))
            correlation = prior["frame"]
            event_class = "IRQ_0x0100_TOUCH_0"
            payload_summary = "raw_base12=REDACTED;learned_table12=REDACTED"
        elif frame.direction == "IN" and wire_control == 0x50:
            correlation = pending[0x50]
            event_class = "INTERSTAGE_NAV_0x50_RESPONSE"
            payload_summary = f"dynamic_nav_redacted;sha256={hashlib.sha256(frame.raw).hexdigest()}"
        elif frame.direction == "IN" and control == 0x82 and data is not None:
            correlation = pending[0x82]
            event_class = "INTERSTAGE_FDT_DELTA_0x82_RESPONSE"
            payload_summary = f"data={data.hex()}"
        elif frame.direction == "IN" and frame.outer == 0xB0:
            require(last_request_frame == pending.get(0x20), "B0 baseline response not after 0x20")
            correlation = pending[0x20]
            event_class = "INTERSTAGE_BASELINE_IMAGE_B0_RESPONSE"
            payload_summary = f"encrypted_dynamic_redacted;sha256={hashlib.sha256(frame.raw).hexdigest()}"
        else:
            raise RuntimeError(f"unclassified logical frame {frame.packet_index + 1}")
        rows.append({
            "frame": frame.packet_index + 1,
            "timestamp_utc": utc_text(frame.timestamp),
            "direction": frame.direction,
            "outer": f"0x{frame.outer:02x}",
            "control": "" if wire_control is None else f"0x{wire_control:02x}",
            "logical_length": len(frame.raw),
            "physical_length": frame.physical_length,
            "event_class": event_class,
            "response_correlation_request_frame": correlation,
            "payload_summary": payload_summary,
        })

    require(len([row for row in rows if row["event_class"] == "INTERSTAGE_NAV_0x50_REQUEST"]) == 1,
            "0x50 exact census changed")
    require(len([row for row in rows if row["event_class"] == "INTERSTAGE_FDT_DELTA_0x82_REQUEST"]) == 1,
            "inter-stage 0x82 exact census changed")
    require(len([row for row in rows if row["event_class"] == "INTERSTAGE_BASELINE_IMAGE_0x20_REQUEST"]) == 1,
            "0x20 exact census changed")
    return {
        "capture_sha256": sha256_file(wire.path),
        "fresh_af_frame": target[af_position].packet_index + 1,
        "fresh_ae_frame": target[fresh_ae_position].packet_index + 1,
        "first_post_bootstrap_0x32_frame": target[first_arm_position].packet_index + 1,
        "out_control_trace": [f"0x{value:02x}" for value in out_controls],
        "rows": rows,
        "raw_dynamic_payload_exported": False,
    }


def temporal_provenance(repo: Path, timeline: dict[str, object]) -> dict[str, object]:
    run = repo / D255_RUN
    metadata = json.loads((run / "cache_before_metadata.json").read_text(encoding="utf-8-sig"))
    matches = [row for row in metadata if row.get("size") == 13_520 and row.get("sha256") == EXPECTED_CACHE_SHA256]
    require(len(matches) == 1, "canonical D255 goodix.dat metadata changed")
    cache_row = matches[0]
    marker_path = run / "operator_markers.tsv"
    markers = d255.load_markers(marker_path)
    attach = d255.one_marker(markers, "VM_USB_ATTACH_BEGIN")
    require(attach is not None, "attach marker unavailable")
    attach_texts = [line.split("\t", 1)[0] for line in marker_path.read_text(encoding="utf-8-sig").splitlines()
                    if "\tVM_USB_ATTACH_BEGIN\t" in line]
    require(len(attach_texts) == 1, "attach marker text unavailable or ambiguous")
    attach_text = attach_texts[0]
    first_36_row = next(row for row in timeline["rows"] if row["event_class"] == "FDT36_STAGE_0_REQUEST")
    mtime_text = str(cache_row["modification_time_utc"])
    first_36_text = str(first_36_row["timestamp_utc"])
    attach_delta = decimal_utc_delta(attach_text, mtime_text)
    first_delta = decimal_utc_delta(first_36_text, mtime_text)
    require(attach_delta > Decimal(27 * 60) and first_delta > Decimal(27 * 60),
            "D255 pre-attach persisted-cache interval no longer exceeds 27 minutes")
    return {
        "CACHE_MTIME_UTC": mtime_text,
        "VM_ATTACH_BEGIN_UTC": attach_text,
        "FIRST_0x36_UTC": first_36_text,
        "CACHE_MTIME_TO_ATTACH_BEGIN_SECONDS": float(attach_delta),
        "CACHE_MTIME_TO_FIRST_0x36_SECONDS": float(first_delta),
        "MTIME_EQUALS_GENERATION_TIME_PROVEN": False,
        "SAME_ATTACH_SEED_GENERATION_REQUIRED": False,
        "PERSISTED_PRE_ATTACH_CACHE_REUSE_PROVEN": True,
        "GENERAL_CACHE_TTL_PROVEN": False,
        "SEED_FRESHNESS_FACTORY_PRESERVATION_CLASS": "NOT_A_FACTORY_PRESERVATION_BLOCKER_ON_CURRENT_EVIDENCE",
        "SEED_FRESHNESS_FUNCTIONAL_CLASS": "GENERAL_TTL_UNPROVEN_BOUNDED_FUNCTIONAL_SUCCESS_RISK",
    }


def audit(repo: Path) -> dict[str, object]:
    timeline = exact_timeline(repo)
    return {
        "schema": "D257_EXACT_FRESH_BOOTSTRAP_AUDIT_V2",
        "execution_mode": "OFFLINE_ONLY",
        "timeline": timeline,
        "temporal_provenance": temporal_provenance(repo, timeline),
        "interstage": {
            "0x50": {
                "observed": True,
                "request_payload": "0100",
                "builder_callsite": "ChicagoHUSetMode mode=5/type=0; A0 generic call 0x180025a7a",
                "response_shape": "A0/0x50 logical=physical=2417; dynamic NAV data; bounded OEM no-check marker 0x88",
                "host_dataflow": "NAV baseline/validation input; exact target host predicate unresolved",
                "causal_class": "REQUIRED_IN_EXACT_CANDIDATE; CAUSAL_NECESSITY_NOT_EXCLUDED",
            },
            "0x82": {
                "observed": True,
                "request_payload": "0082000200",
                "register": "0x0082",
                "quantity": 2,
                "response": "801d",
                "builder_callsite": "ChipRegRead 0x180059488",
                "host_dataflow": "immediate FDT-delta/read-reg stage; exact decision predicate unresolved",
                "causal_class": "REQUIRED_IN_EXACT_CANDIDATE; CAUSAL_NECESSITY_NOT_EXCLUDED",
            },
            "0x20": {
                "observed": True,
                "request_payload": "0100",
                "response_shape": "B0 logical=physical=7726; encrypted dynamic application/image record",
                "host_dataflow": "baseline/no-finger image validation before third 0x36; exact predicate unavailable from raw",
                "causal_class": "REQUIRED_IN_EXACT_CANDIDATE; CAUSAL_NECESSITY_NOT_EXCLUDED",
            },
            "dynamic_payload_blocker": "NAV_AND_DECRYPTED_BASELINE_HOST_DECISION_GATES_NOT_DERIVABLE_FROM_D255_RAW",
        },
        "safety": {
            "REAL_USB_OPEN_COUNT": 0,
            "REAL_CAPTURE_COUNT": 0,
            "REAL_HARDWARE_ACTION_COUNT": 0,
            "REAL_COMMAND_SEND_COUNT": 0,
            "PERSISTENT_WRITE_FAMILY_COUNT": 0,
        },
    }


def csv_text(rows: list[dict[str, object]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def markdown_text(result: dict[str, object]) -> str:
    timeline = result["timeline"]
    temporal = result["temporal_provenance"]
    lines = [
        "# D257 exact target fresh-bootstrap timeline",
        "",
        f"Raw D255 SHA-256 gate: `{timeline['capture_sha256']}`.",
        "",
        "The full logical-frame census derives the segment from the first fresh AF/AE pair through the ACK of the first subsequent `0x32`; it does not preselect only FDT commands.",
        "",
        "```text",
        "AF/AE fresh -> 0x36/ACK/IRQ100 -> 0x50/ACK/NAV -> 0x36/ACK/IRQ100",
        "-> 0x82/ACK/response -> 0x20/ACK/B0 baseline -> 0x36/ACK/IRQ100 -> 0x32/ACK",
        "```",
        "",
        "Dynamic NAV/image bytes, OTP and FDT table bytes are redacted; request payloads and response structure/correlation remain audit-visible.",
        "",
        "## Temporal provenance",
        "",
        f"- cache mtime: `{temporal['CACHE_MTIME_UTC']}` (not proven to be generation time)",
        f"- VM attach begin: `{temporal['VM_ATTACH_BEGIN_UTC']}`",
        f"- first `0x36`: `{temporal['FIRST_0x36_UTC']}`",
        f"- mtime to attach: `{temporal['CACHE_MTIME_TO_ATTACH_BEGIN_SECONDS']:.7f}` seconds",
        f"- mtime to first `0x36`: `{temporal['CACHE_MTIME_TO_FIRST_0x36_SECONDS']:.7f}` seconds",
        "",
        "D255 therefore proves successful reuse of an OTP-bound, CRC-valid cache that pre-existed the attach by more than 27 minutes. It does not prove a general TTL.",
        "",
        "## Inter-stage decision",
        "",
        "`0x50`, inter-stage `0x82`, and `0x20` are observed and causal necessity is not excluded. They are required in the exact candidate. Their dynamic NAV/FDT-delta/baseline outputs feed host-side gates whose exact target predicates are not derivable from the D255 raw alone, so exact replay remains blocked rather than silently projecting them away.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    result = audit(repo)
    outputs = {
        args.json: json.dumps(result, indent=2, sort_keys=True) + "\n",
        args.csv: csv_text(result["timeline"]["rows"]),
        args.markdown: markdown_text(result),
    }
    for path, content in outputs.items():
        if path is None:
            continue
        destination = path if path.is_absolute() else repo / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8", newline="")
    if not any(outputs):
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
