#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Sanitized, offline-only D273 census of local target USB captures.

The output contains framing/control metadata only.  It never serializes B0
contents, plaintext, raster data, or hashes derived from biometric payloads.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PARSER = ROOT / "analysis/D230/tools/offline_census.py"
CAPTURES = (
    (
        ROOT / "analysis/D230/work/GoodixExport/rilevamento.pcapng",
        "50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b",
        "positive_oem_reference",
    ),
    (
        ROOT / "captures/D255_20260822T205631772Z_85c8c41f/raw/wire.pcapng",
        "802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c",
        "zero_finger_oem_reference",
    ),
)


def _load_parser():
    spec = importlib.util.spec_from_file_location("d230_offline_census", PARSER)
    if spec is None or spec.loader is None:
        raise RuntimeError("d230_parser_import_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frame_metadata(frame: dict, direction: str) -> dict:
    raw = frame["raw"]
    result = {
        "packet_index": frame["first_packet_index"],
        "direction": direction,
        "outer_wrapper": frame["outer_type"],
        "physical_length": len(raw),
        "declared_outer_length": frame["expected_len"],
    }
    if frame["outer_type"] == "0xb0":
        result["classification"] = "B0_TLS_RECORD_CONTENT_OMITTED"
        return result
    if frame["outer_type"] != "0xa0" or len(raw) < 8:
        result["classification"] = "UNKNOWN_FRAMING"
        return result
    wire_control = raw[4]
    inner_length = int.from_bytes(raw[5:7], "little")
    result.update(
        {
            "wire_control": f"0x{wire_control:02x}",
            "logical_control": f"0x{wire_control & 0xfe:02x}",
            "declared_inner_length": inner_length,
        }
    )
    if wire_control == 0xB0 and inner_length == 3:
        result.update(
            {
                "classification": "A0_COMMAND_ACK",
                "ack_echo": f"0x{raw[7]:02x}",
                "ack_status": f"0x{raw[8]:02x}",
            }
        )
    elif direction == "device_to_host" and inner_length == 17:
        result.update(
            {
                "classification": "A0_FDT_IRQ",
                "irq": f"0x{int.from_bytes(raw[7:9], 'little'):04x}",
            }
        )
    elif direction == "device_to_host" and (wire_control & 0xFE) == 0x50:
        result["classification"] = "A0_0X50_NAV_RESPONSE"
    else:
        result["classification"] = "A0_COMMAND_OR_RESPONSE"
    return result


def _audit_capture(parser, path: Path, expected_hash: str, role: str) -> dict:
    actual_hash = _sha256(path)
    if actual_hash != expected_hash:
        raise RuntimeError(f"capture_hash_mismatch:{path}")
    packets = [parser.decode_usbpcap(item) for item in parser.iter_pcapng_packets(path)]
    out_frames = parser.split_bulk_frames(packets, 0x01, 0)
    in_frames = parser.split_bulk_frames(packets, 0x81, 1)
    frames = [
        *(_frame_metadata(frame, "host_to_device") for frame in out_frames),
        *(_frame_metadata(frame, "device_to_host") for frame in in_frames),
    ]
    frames.sort(key=lambda item: item["packet_index"])
    positive_images = [
        item
        for item in frames
        if item["classification"] == "B0_TLS_RECORD_CONTENT_OMITTED"
        and item["physical_length"] == 7726
    ]
    irq2 = [item for item in frames if item.get("irq") == "0x0002"]
    return {
        "source": str(path.relative_to(ROOT)),
        "sha256": actual_hash,
        "role": role,
        "packet_count": len(packets),
        "host_to_device_frame_count": len(out_frames),
        "device_to_host_frame_count": len(in_frames),
        "positive_image_record_count": len(positive_images),
        "irq_0x0002_count": len(irq2),
        "frames": frames,
    }


def main() -> None:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--output", type=Path)
    args = argument_parser.parse_args()
    parser = _load_parser()
    captures = [_audit_capture(parser, *entry) for entry in CAPTURES]
    positive = captures[0]
    by_index = {item["packet_index"]: item for item in positive["frames"]}
    expected = {
        220: ("A0_COMMAND_OR_RESPONSE", "0x32"),
        223: ("A0_COMMAND_ACK", "0x32"),
        225: ("A0_FDT_IRQ", None),
        227: ("A0_COMMAND_OR_RESPONSE", "0x22"),
        229: ("A0_COMMAND_ACK", "0x22"),
        231: ("B0_TLS_RECORD_CONTENT_OMITTED", None),
        233: ("A0_COMMAND_OR_RESPONSE", "0x34"),
        235: ("A0_COMMAND_ACK", "0x34"),
        237: ("A0_FDT_IRQ", None),
        238: ("A0_COMMAND_OR_RESPONSE", "0x20"),
        241: ("A0_COMMAND_ACK", "0x20"),
        243: ("B0_TLS_RECORD_CONTENT_OMITTED", None),
        244: ("A0_COMMAND_OR_RESPONSE", "0x50"),
        247: ("A0_COMMAND_ACK", "0x50"),
        249: ("A0_0X50_NAV_RESPONSE", "0x50"),
        251: ("A0_COMMAND_OR_RESPONSE", "0x32"),
        253: ("A0_COMMAND_ACK", "0x32"),
    }
    for index, (classification, control) in expected.items():
        item = by_index[index]
        if item["classification"] != classification:
            raise RuntimeError(f"classification_mismatch:{index}")
        observed_control = item.get("ack_echo", item.get("logical_control"))
        if control is not None and observed_control != control:
            raise RuntimeError(f"control_mismatch:{index}")
    result = {
        "artifact": "D273_01_capture_census",
        "offline_only": True,
        "privacy": "FRAMING_METADATA_ONLY_NO_B0_CONTENT_NO_PLAINTEXT_NO_RASTER",
        "captures": captures,
        "positive_sequence_count": 1,
        "post_0x50_packet_249": by_index[249],
        "second_cycle_after_packet_251_observed": False,
    }
    serialized = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized)
    print(
        json.dumps(
            {
                "capture_count": len(captures),
                "positive_sequence_count": 1,
                "packet_249": "A0_0X50_NAV_RESPONSE",
                "second_cycle_observed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
