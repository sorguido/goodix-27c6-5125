# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline-only closure for the D267/04 image-specific 0x88 policy."""

from __future__ import annotations

import unittest

from core.post_d4 import (
    ChecksumMismatch,
    ImageCrcError,
    ImageDecodeDiagnostic,
    LengthMismatch,
    UnexpectedControl,
    UnexpectedEvent,
    _checksum,
    parse_image_payload,
    parse_payload,
)
from src.goodix5125_cleanroom import encode_synthetic_record


def _payload(control: int, data: bytes, trailer: int | None = None) -> bytes:
    declared = len(data) + 1
    check = _checksum(control, data) if trailer is None else trailer
    return bytes((control, declared & 0xFF, declared >> 8)) + data + bytes((check,))


def _record() -> bytes:
    raster = tuple((index * 41 + index // 64 * 7) & 0xFFF for index in range(5120))
    return encode_synthetic_record(raster)


def _image(*, control: int = 0x20, prefix0: int = 1, trailer: int | None = None,
           record: bytes | None = None) -> bytes:
    image_record = _record() if record is None else record
    return _payload(
        control,
        bytes((prefix0, 0, 0, 0, 0)) + image_record,
        trailer,
    )


def _diagnostic(payload: bytes) -> tuple[tuple[int, ...], dict[str, object]]:
    observation = ImageDecodeDiagnostic()
    raster = parse_image_payload(payload, diagnostic=observation)
    return raster, observation.sanitized_dict()


class D267ImageNoCheckTests(unittest.TestCase):
    def test_additive_valid_image_is_unchanged(self) -> None:
        raster, diagnostic = _diagnostic(_image())
        self.assertEqual(len(raster), 5120)
        self.assertEqual(diagnostic["payload_checksum_policy"], "ADDITIVE_VERIFIED")
        self.assertTrue(diagnostic["payload_checksum_match"])

    def test_non_0x88_additive_mismatch_remains_strict(self) -> None:
        valid = _image()
        wrong = (valid[-1] + 1) & 0xFF
        if wrong == 0x88:
            wrong = (wrong + 1) & 0xFF
        with self.assertRaisesRegex(ChecksumMismatch, "payload_checksum"):
            parse_image_payload(valid[:-1] + bytes((wrong,)))

    def test_0x88_bypasses_only_additive_image_gate(self) -> None:
        ordinary, _ = _diagnostic(_image())
        marked, diagnostic = _diagnostic(_image(trailer=0x88))
        self.assertEqual(marked, ordinary)
        self.assertEqual(diagnostic["payload_checksum_policy"], "NO_CHECK_0X88_ACCEPTED")
        self.assertFalse(diagnostic["payload_checksum_match"])

    def test_0x88_does_not_bypass_record_crc(self) -> None:
        damaged = bytearray(_record())
        damaged[2049] ^= 0x20
        observation = ImageDecodeDiagnostic()
        with self.assertRaisesRegex(ImageCrcError, "image_crc"):
            parse_image_payload(
                _image(record=bytes(damaged), trailer=0x88), diagnostic=observation
            )
        diagnostic = observation.sanitized_dict()
        self.assertEqual(diagnostic["payload_checksum_policy"], "NO_CHECK_0X88_ACCEPTED")
        self.assertFalse(diagnostic["image_record_crc_match"])

    def test_0x88_non_image_major_gets_no_acceptance(self) -> None:
        observation = ImageDecodeDiagnostic()
        with self.assertRaisesRegex(UnexpectedControl, "not_image"):
            parse_image_payload(_image(control=0x30, trailer=0x88), diagnostic=observation)
        self.assertEqual(observation.payload_checksum_policy, "NOT_REACHED")

    def test_0x88_pov_remains_non_image(self) -> None:
        observation = ImageDecodeDiagnostic()
        with self.assertRaisesRegex(UnexpectedEvent, "pov_notification_not_image"):
            parse_image_payload(_image(prefix0=0xAA, trailer=0x88), diagnostic=observation)
        self.assertEqual(observation.payload_checksum_policy, "NOT_REACHED")

    def test_0x88_declared_length_mismatch_fails_before_policy(self) -> None:
        malformed = bytearray(_image(trailer=0x88))
        malformed[1:3] = (7689).to_bytes(2, "little")
        observation = ImageDecodeDiagnostic()
        with self.assertRaisesRegex(LengthMismatch, "payload_length"):
            parse_image_payload(bytes(malformed), diagnostic=observation)
        self.assertEqual(observation.payload_checksum_policy, "NOT_REACHED")

    def test_0x88_wrong_record_length_fails_before_policy(self) -> None:
        observation = ImageDecodeDiagnostic()
        with self.assertRaisesRegex(LengthMismatch, "image_payload_data_length"):
            parse_image_payload(
                _image(record=_record()[:-1], trailer=0x88), diagnostic=observation
            )
        self.assertEqual(observation.payload_checksum_policy, "NOT_REACHED")

    def test_generic_parse_payload_remains_strict_for_0x88(self) -> None:
        candidate = _payload(0x20, b"not-an-image", trailer=0x88)
        self.assertNotEqual(_checksum(candidate[0], candidate[3:-1]), 0x88)
        with self.assertRaisesRegex(ChecksumMismatch, "payload_checksum"):
            parse_payload(candidate)

    def test_ordinary_7693_fixture_and_0x88_have_same_80x64_raster(self) -> None:
        ordinary = _image()
        marked = ordinary[:-1] + b"\x88"
        self.assertEqual(len(ordinary), 7693)
        ordinary_raster = parse_image_payload(ordinary)
        marked_raster = parse_image_payload(marked)
        self.assertEqual((len(ordinary_raster) // 64, 64), (80, 64))
        self.assertEqual(marked_raster, ordinary_raster)


if __name__ == "__main__":
    unittest.main()
