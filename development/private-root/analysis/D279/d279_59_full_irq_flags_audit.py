#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Produce a payload-free IRQ/control/flags corpus from authentic APP12509 PCAPs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
D274_PATH = ROOT / (
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/"
    "d274_03_postprocess_second_cycle.py"
)
OEM_VERIFY_PATH = ROOT / "analysis/D279/d279_59_verify_oem_touchflags.py"
CAPTURES = (
    ("D255_ZERO_FINGER", "captures/D255_20260822T205631772Z_85c8c41f/raw/wire.pcapng",
     "802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c"),
    ("D274_03_MULTIFRAME", "captures/D274_03/D27403_20260826T201852Z/raw/wire.pcapng",
     "5f11d06763d34531c72283a189a47d9bcd7c666a5fa3c043ec1371eddf107998"),
    ("D279_10_ATTEMPT01", "captures/D279_10/D27910_20260905_ATTEMPT01/raw/wire.pcapng",
     "557ff136e5a1d383f7413ca24d731eeae32d2b377e61003846b034ecda991743"),
    ("D279_10_ATTEMPT02", "captures/D279_10/D27910_20260905_ATTEMPT02/raw/wire.pcapng",
     "3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab"),
    ("D279_54_IDENTIFY", "captures/D279_54/D27954_20260908_ATTEMPT01/raw/wire.pcapng",
     "6875b2d784d11cd4b3a8b68bd02af249f4b318883441a26068ef894767985c9b"),
)


class AuditError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_d274():
    spec = importlib.util.spec_from_file_location("d279_59_d274", D274_PATH)
    require(spec is not None and spec.loader is not None, "D274_PARSER_NOT_LOADABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_oem_verifier():
    spec = importlib.util.spec_from_file_location("d279_59_oem", OEM_VERIFY_PATH)
    require(spec is not None and spec.loader is not None,
            "D279_59_OEM_VERIFIER_NOT_LOADABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def phase_for(label: str, frame: int, irq: int, d279_starts: list[int]) -> tuple[str, int | None]:
    if label != "D279_10_ATTEMPT02":
        return ("capture_bootstrap" if irq == 0x0100 else "capture_action", None)
    if not d279_starts or frame < d279_starts[0]:
        return "bootstrap_fdt_manual", None
    cycle = max(index for index, start in enumerate(d279_starts, 1) if start <= frame)
    if irq == 0x0002:
        phase = "first_cycle_finger_down" if cycle == 1 else (
            "terminal_cycle_finger_down" if cycle == 21 else "repeated_cycle_finger_down"
        )
    elif irq == 0x0100:
        phase = "terminal_cycle_contact_sample" if cycle == 21 else "repeated_cycle_contact_sample"
    elif irq == 0x0200:
        phase = "first_cycle_finger_up" if cycle == 1 else (
            "terminal_cycle_finger_up" if cycle == 21 else "repeated_cycle_finger_up"
        )
    else:
        phase = "other_irq"
    return phase, cycle


def analyze(root: Path = ROOT) -> dict:
    d274 = load_d274()
    captures = []
    full_matrix = []
    global_counts: Counter[tuple[int, int, int]] = Counter()
    for label, relative, expected_sha in CAPTURES:
        path = root / relative
        require(path.is_file(), f"MISSING_{label}")
        actual_sha = sha256(path)
        require(actual_sha == expected_sha, f"SHA256_MISMATCH_{label}")
        packets = d274.parse_usbpcap_bytes(path.read_bytes())
        frames, firmware_ok = d274._target_frames(packets, include_incomplete=False)
        require(firmware_ok, f"APP12509_NOT_OBSERVED_{label}")
        irq_rows = []
        d279_starts: list[int] = []
        if label == "D279_10_ATTEMPT02":
            for frame in frames:
                if frame.direction != "device_to_host" or frame.outer != 0xA0:
                    continue
                try:
                    control, body = d274.parse_a0(frame)
                except Exception:
                    continue
                if control == 0x32 and len(body) == 16 and int.from_bytes(body[:2], "little") == 2:
                    d279_starts.append(frame.packet_index)
            require(len(d279_starts) == 21, "D279_10_IRQ2_CYCLE_COUNT")
        for frame in frames:
            if frame.direction != "device_to_host" or frame.outer != 0xA0:
                continue
            try:
                control, body = d274.parse_a0(frame)
            except Exception:
                continue
            if control not in (0x32, 0x34, 0x36) or len(body) != 16:
                continue
            irq = int.from_bytes(body[:2], "little")
            flags = int.from_bytes(body[2:4], "little")
            if irq not in (0x0002, 0x0100, 0x0200):
                continue
            phase, cycle = phase_for(label, frame.packet_index, irq, d279_starts)
            row = {
                "capture": label,
                "phase": phase,
                "cycle": cycle,
                "frame": frame.packet_index,
                "control": f"0x{control:02x}",
                "irq": f"0x{irq:04x}",
                "flags": f"0x{flags:04x}",
                "active_channel_count": (flags & 0x003F).bit_count(),
                "reserved_bits_set": bool(flags & ~0x003F),
                "raw_source": "A0_BODY_4_15_PRESENT_12_BYTES_NOT_EXPORTED",
            }
            irq_rows.append(row)
            global_counts[(control, irq, flags)] += 1
            if label == "D279_10_ATTEMPT02":
                full_matrix.append(row)
        captures.append({
            "label": label,
            "path": relative,
            "sha256": actual_sha,
            "irq_event_count": len(irq_rows),
            "distinct_counts": [
                {"control": f"0x{control:02x}", "irq": f"0x{irq:04x}",
                 "flags": f"0x{flags:04x}", "count": count}
                for (control, irq, flags), count in sorted(Counter(
                    (int(row["control"], 16), int(row["irq"], 16), int(row["flags"], 16))
                    for row in irq_rows
                ).items())
            ],
        })
    require(len(full_matrix) == 65, "D279_10_FULL_IRQ_MATRIX_COUNT")
    require(Counter((row["control"], row["irq"], row["flags"]) for row in full_matrix) == Counter({
        ("0x32", "0x0002", "0x003f"): 21,
        ("0x34", "0x0200", "0x0000"): 21,
        ("0x36", "0x0100", "0x003f"): 20,
        ("0x36", "0x0100", "0x0000"): 3,
    }), "D279_10_DISTINCT_MATRIX")
    return {
        "schema": "D279_59_FULL_IRQ_FLAGS_AUDIT_V1",
        "scope": "AUTHENTIC_APP12509_METADATA_ONLY",
        "captures": captures,
        "d279_10_attempt02_irq_matrix": full_matrix,
        "global_distinct_counts": [
            {"control": f"0x{control:02x}", "irq": f"0x{irq:04x}",
             "flags": f"0x{flags:04x}", "count": count}
            for (control, irq, flags), count in sorted(global_counts.items())
        ],
        "static_touchflag_semantics": load_oem_verifier().verify(root),
        "production_policy": {
            "touch_mask": "0x003f",
            "finger_down": "NONZERO_SUBSET_OF_SIX_CHANNEL_BITS",
            "enrollment_contact_sample": "NONZERO_SUBSET_OF_SIX_CHANNEL_BITS",
            "bootstrap_baseline_sample": "EXACT_ZERO",
            "finger_up": "EXACT_ZERO",
            "reserved_high_bits": "FAIL_CLOSED",
            "partial_mask_derivation": "INACTIVE_CHANNEL_USES_DELTA_MINUS_TWO_FALLBACK",
        },
        "linux_live_regression_evidence": [
            {"commit": "d94c7af192bb3f0d0cb4ed7b411d099d73902e3b",
             "expected": "IRQ0100 flags 0x0000", "observed": "IRQ0100 flags 0x003f"},
            {"commit": "4de9c342b4d2d59aa37cf333638f3f88350547ea",
             "expected": "IRQ2 flags 0x003f", "observed": "IRQ2 flags 0x002f"},
        ],
        "payload_exported": False,
        "biometric_material_exported": False,
        "secret_material_exported": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--policy-corpus", type=Path)
    args = parser.parse_args()
    result = analyze()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.policy_corpus:
        lines = ["source\tphase\tcontrol\tirq\tflags"]
        lines.extend(
            "\t".join((row["capture"], row["phase"], row["control"],
                       row["irq"], row["flags"]))
            for row in result["d279_10_attempt02_irq_matrix"]
        )
        lines.append("D279_57_LIVE_4DE9C34\trearm_finger_down\t0x32\t0x0002\t0x002f")
        args.policy_corpus.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
