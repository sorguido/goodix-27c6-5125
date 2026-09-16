#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract per-reader A2, chip82 and OTP A6 response digests offline."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from _goodix5125_usbpcap import (
    A0, ExtractError, atomic_write_new_0600, iter_bulk_payloads, parse_a0,
    reassemble_frames, synthetic_a0_frame, synthetic_pcapng,
)

SCHEMA = "goodix-5125-device-response-pins-v1"
TARGETS = {
    0xA2: ("a2", 3),
    0x82: ("chip82", 4),
    0xA6: ("otp_a6", 64),
}


@dataclass(frozen=True)
class Candidate:
    first_packet: int
    last_packet: int
    control: int
    body: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


def find_candidates(path: Path) -> dict[str, list[Candidate]]:
    result = {name: [] for name, _ in TARGETS.values()}
    payloads = iter_bulk_payloads(path, device_to_host=True)
    for frame in reassemble_frames(payloads):
        if frame.raw[0] != A0:
            continue
        try:
            wire_control, logical_control, body = parse_a0(frame.raw)
        except ExtractError:
            continue
        target = TARGETS.get(logical_control)
        if target is None:
            continue
        name, expected_length = target
        # Typed runtime responses use the exact even control, not its odd wire
        # variant used by host commands such as CONFIG90.
        if wire_control != logical_control or len(body) != expected_length:
            continue
        result[name].append(Candidate(
            frame.first_packet, frame.last_packet, wire_control, body
        ))
    return result


def choose(candidates: dict[str, list[Candidate]]) -> dict[str, tuple[str, int]]:
    chosen: dict[str, tuple[str, int]] = {}
    for control, (name, expected_length) in TARGETS.items():
        values = candidates[name]
        if not values:
            raise ExtractError(
                f"no valid {expected_length}-byte A0/0x{control:02x} {name} response found"
            )
        groups: dict[bytes, list[Candidate]] = {}
        for candidate in values:
            groups.setdefault(candidate.body, []).append(candidate)
        if len(groups) != 1:
            counts = ", ".join(
                f"{hashlib.sha256(body).hexdigest()[:12]}… "
                f"({len(group)} occurrence(s))"
                for body, group in sorted(groups.items())
            )
            raise ExtractError(f"multiple distinct valid {name} responses found: {counts}")
        body, group = next(iter(groups.items()))
        chosen[name] = hashlib.sha256(body).hexdigest(), len(group)
    return chosen


def extract(pcap: Path, output: Path) -> dict[str, object]:
    selected = choose(find_candidates(pcap))
    document: dict[str, object] = {
        "schema": SCHEMA,
        "a2_response_sha256": selected["a2"][0],
        "chip82_response_sha256": selected["chip82"][0],
        "otp_a6_response_sha256": selected["otp_a6"][0],
        "a2_occurrence_count": selected["a2"][1],
        "chip82_occurrence_count": selected["chip82"][1],
        "otp_a6_occurrence_count": selected["otp_a6"][1],
    }
    encoded = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("ascii")
    atomic_write_new_0600(output, encoded)
    return document


def _capture(path: Path, frames: list[tuple[bytes, bool]],
             fragments: tuple[int, ...] = ()) -> None:
    chunks: list[tuple[bytes, bool]] = []
    for frame, device_to_host in frames:
        if not fragments:
            chunks.append((frame, device_to_host))
            continue
        cursor = 0
        for width in fragments:
            if cursor >= len(frame):
                break
            chunks.append((frame[cursor:cursor + width], device_to_host))
            cursor += width
        if cursor < len(frame):
            chunks.append((frame[cursor:], device_to_host))
    path.write_bytes(synthetic_pcapng(chunks))


def _valid_frames(*, a2: bytes = b"\x01\x02\x03",
                  chip82: bytes = b"\x10\x20\x30\x40",
                  otp: bytes = bytes(range(64))) -> list[tuple[bytes, bool]]:
    return [
        (synthetic_a0_frame(0xA2, a2), True),
        (synthetic_a0_frame(0x82, chip82), True),
        (synthetic_a0_frame(0xA6, otp), True),
    ]


def _assert_fails(path: Path, expected: str) -> None:
    try:
        choose(find_candidates(path))
    except ExtractError as error:
        assert expected in str(error), (expected, str(error))
    else:
        raise AssertionError(f"capture unexpectedly accepted; wanted {expected}")


def selftest() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        basic = root / "basic.pcapng"
        _capture(basic, _valid_frames())
        selected = choose(find_candidates(basic))
        assert all(selected[name][1] == 1 for name in ("a2", "chip82", "otp_a6"))

        fragmented = root / "fragmented.pcapng"
        _capture(fragmented, _valid_frames(), fragments=(2, 3, 7))
        assert choose(find_candidates(fragmented)) == selected

        duplicate = root / "duplicate.pcapng"
        _capture(duplicate, _valid_frames() + _valid_frames())
        duplicates = choose(find_candidates(duplicate))
        assert all(duplicates[name][1] == 2 for name in duplicates)

        for name, control, replacement in (
            ("a2", 0xA2, b"\x09\x08\x07"),
            ("chip82", 0x82, b"\x09\x08\x07\x06"),
            ("otp_a6", 0xA6, bytes(reversed(range(64)))),
        ):
            ambiguous = root / f"ambiguous-{name}.pcapng"
            frames = _valid_frames() + [(synthetic_a0_frame(control, replacement), True)]
            _capture(ambiguous, frames)
            _assert_fails(ambiguous, f"multiple distinct valid {name}")

        missing = root / "missing.pcapng"
        _capture(missing, _valid_frames()[:-1])
        _assert_fails(missing, "no valid 64-byte")

        bad_checksum = root / "bad-checksum.pcapng"
        frames = _valid_frames()[:-1] + [
            (synthetic_a0_frame(0xA6, bytes(range(64)), corrupt_checksum=True), True)
        ]
        _capture(bad_checksum, frames)
        _assert_fails(bad_checksum, "no valid 64-byte")

        bad_length = root / "bad-length.pcapng"
        frames = _valid_frames()[:-1] + [
            (synthetic_a0_frame(0xA6, bytes(range(63))), True)
        ]
        _capture(bad_length, frames)
        _assert_fails(bad_length, "no valid 64-byte")

        wrong_direction = root / "wrong-direction.pcapng"
        frames = _valid_frames()[:-1] + [
            (synthetic_a0_frame(0xA6, bytes(range(64))), False)
        ]
        _capture(wrong_direction, frames)
        _assert_fails(wrong_direction, "no valid 64-byte")

        output = root / "device-response-pins.json"
        captured_stdout = io.StringIO()
        with contextlib.redirect_stdout(captured_stdout):
            document = extract(fragmented, output)
        assert captured_stdout.getvalue() == ""
        assert output.stat().st_mode & 0o777 == 0o600
        assert json.loads(output.read_text(encoding="ascii")) == document
        assert not any(item.suffix == ".tmp" for item in root.iterdir())
        before = output.read_bytes()
        try:
            extract(fragmented, output)
        except ExtractError as error:
            assert "refusing to overwrite" in str(error)
        else:
            raise AssertionError("existing response output was overwritten")
        assert output.read_bytes() == before
        for raw_body in (b"\x01\x02\x03", b"\x10\x20\x30\x40", bytes(range(64))):
            assert raw_body.hex() not in output.read_text(encoding="ascii")

    print("GOODIX_DEVICE_RESPONSES_SELFTEST=PASS")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extract Goodix 27c6:5125 A2/chip82/OTP response digests from an "
            "offline Windows USBPcap pcapng capture."
        )
    )
    parser.add_argument("--pcap", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    if arguments.self_test:
        selftest()
        return 0
    if arguments.pcap is None or arguments.output is None:
        print(
            "ERROR: --pcap and --output are required unless --self-test is used",
            file=sys.stderr,
        )
        return 2
    try:
        report = extract(arguments.pcap, arguments.output)
    except ExtractError as error:
        print(f"GOODIX_DEVICE_RESPONSES_EXTRACTION=FAIL: {error}", file=sys.stderr)
        return 1
    if arguments.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("GOODIX_DEVICE_RESPONSES_EXTRACTION=PASS")
        print(f"output={arguments.output}")
        print(f"a2_response_sha256={report['a2_response_sha256']}")
        print(f"chip82_response_sha256={report['chip82_response_sha256']}")
        print(f"otp_a6_response_sha256={report['otp_a6_response_sha256']}")
        print(f"a2_occurrence_count={report['a2_occurrence_count']}")
        print(f"chip82_occurrence_count={report['chip82_occurrence_count']}")
        print(f"otp_a6_occurrence_count={report['otp_a6_occurrence_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
