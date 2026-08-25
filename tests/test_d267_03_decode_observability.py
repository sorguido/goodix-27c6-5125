# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic-only tests for D267/03 sanitized decode observability."""

from __future__ import annotations

import unittest

from core.post_d4 import (
    ChecksumMismatch,
    ImageCrcError,
    ImageDecodeDiagnostic,
    LengthMismatch,
    TruncatedFrame,
    UnexpectedControl,
    UnexpectedEvent,
    _checksum,
    parse_image_payload,
)
from src.goodix5125_cleanroom import encode_synthetic_record


def _payload(control: int, data: bytes, checksum: int | None = None) -> bytes:
    declared = len(data) + 1
    trailer = _checksum(control, data) if checksum is None else checksum
    return bytes((control, declared & 0xFF, declared >> 8)) + data + bytes((trailer,))


def _record() -> bytes:
    raster = tuple((index * 37 + index // 80 * 11) & 0xFFF for index in range(5120))
    return encode_synthetic_record(raster)


def _image_payload(*, control: int = 0x20, prefix0: int = 0x01) -> bytes:
    return _payload(control, bytes((prefix0, 0, 0, 0, 0)) + _record())


def _observe(payload: bytes) -> tuple[tuple[int, ...] | None, dict[str, object], Exception | None]:
    diagnostic = ImageDecodeDiagnostic()
    try:
        raster = parse_image_payload(payload, diagnostic=diagnostic)
        return raster, diagnostic.sanitized_dict(), None
    except Exception as error:  # the matrix asserts the exact bounded class
        return None, diagnostic.sanitized_dict(), error


class D267DecodeObservabilityTests(unittest.TestCase):
    def test_valid_frame_reports_success_without_sensitive_material(self) -> None:
        raster, diagnostic, error = _observe(_image_payload())
        self.assertIsNone(error)
        self.assertEqual(len(raster or ()), 5120)
        self.assertEqual(
            diagnostic,
            {
                "decode_stage": "successful_raster_decode",
                "plaintext_length": 7693,
                "declared_payload_length": 7690,
                "control_or_major_class": "MAJOR_0X2",
                "is_pov_notification": False,
                "payload_trailer_class": "COMPUTED_ADDITIVE_CHECKSUM",
                "payload_checksum_match": True,
                "image_record_length": 7684,
                "image_record_crc_match": True,
                "exception_class": None,
                "raster_shape_if_success": (80, 64),
            },
        )

    def test_truncated_plaintext_is_distinct(self) -> None:
        _raster, diagnostic, error = _observe(b"\x20\x01")
        self.assertIsInstance(error, TruncatedFrame)
        self.assertEqual(diagnostic["decode_stage"], "plaintext_envelope")
        self.assertEqual(diagnostic["plaintext_length"], 2)
        self.assertEqual(diagnostic["exception_class"], "TruncatedFrame")

    def test_declared_length_mismatch_is_distinct(self) -> None:
        malformed = bytearray(_image_payload())
        malformed[1:3] = (7689).to_bytes(2, "little")
        _raster, diagnostic, error = _observe(bytes(malformed))
        self.assertIsInstance(error, LengthMismatch)
        self.assertEqual(diagnostic["decode_stage"], "declared_length")
        self.assertEqual(diagnostic["declared_payload_length"], 7689)
        self.assertIsNone(diagnostic["payload_checksum_match"])

    def test_unexpected_control_major_is_distinct(self) -> None:
        _raster, diagnostic, error = _observe(_image_payload(control=0x30))
        self.assertIsInstance(error, UnexpectedControl)
        self.assertEqual(diagnostic["decode_stage"], "control_major")
        self.assertEqual(diagnostic["control_or_major_class"], "MAJOR_0X3")
        self.assertTrue(diagnostic["payload_checksum_match"])

    def test_pov_notification_is_distinct(self) -> None:
        _raster, diagnostic, error = _observe(_image_payload(prefix0=0xAA))
        self.assertIsInstance(error, UnexpectedEvent)
        self.assertEqual(diagnostic["decode_stage"], "pov_notification")
        self.assertTrue(diagnostic["is_pov_notification"])

    def test_normal_checksum_mismatch_is_distinct(self) -> None:
        malformed = bytearray(_image_payload())
        malformed[-1] ^= 0x01
        self.assertNotEqual(malformed[-1], 0x88)
        _raster, diagnostic, error = _observe(bytes(malformed))
        self.assertIsInstance(error, ChecksumMismatch)
        self.assertEqual(diagnostic["decode_stage"], "payload_checksum")
        self.assertEqual(diagnostic["payload_trailer_class"], "OTHER")
        self.assertFalse(diagnostic["payload_checksum_match"])

    def test_0x88_is_visible_but_remains_rejected(self) -> None:
        valid = _image_payload()
        self.assertNotEqual(valid[-1], 0x88)
        _raster, diagnostic, error = _observe(valid[:-1] + b"\x88")
        self.assertIsInstance(error, ChecksumMismatch)
        self.assertEqual(diagnostic["decode_stage"], "payload_checksum")
        self.assertEqual(diagnostic["payload_trailer_class"], "0X88")
        self.assertFalse(diagnostic["payload_checksum_match"])

    def test_wrong_image_record_length_is_distinct(self) -> None:
        malformed = _payload(0x20, b"\x01\x00\x00\x00\x00" + _record()[:-1])
        _raster, diagnostic, error = _observe(malformed)
        self.assertIsInstance(error, LengthMismatch)
        self.assertEqual(diagnostic["decode_stage"], "image_record_length")
        self.assertEqual(diagnostic["image_record_length"], 7683)
        self.assertTrue(diagnostic["payload_checksum_match"])

    def test_bad_image_record_crc_is_distinct(self) -> None:
        record = bytearray(_record())
        record[4097] ^= 0x04
        malformed = _payload(0x20, b"\x01\x00\x00\x00\x00" + bytes(record))
        _raster, diagnostic, error = _observe(malformed)
        self.assertIsInstance(error, ImageCrcError)
        self.assertEqual(diagnostic["decode_stage"], "image_record_crc")
        self.assertEqual(diagnostic["image_record_length"], 7684)
        self.assertFalse(diagnostic["image_record_crc_match"])
        self.assertEqual(diagnostic["exception_class"], "ImageCrcError")


if __name__ == "__main__":
    unittest.main()
