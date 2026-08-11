from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goodix5125_cleanroom import (  # noqa: E402
    RECORD_BYTES,
    SAMPLE_COUNT,
    crc32_mpeg2,
    decode_group,
    decode_record,
    encode_group,
    encode_synthetic_record,
    raster_index,
)


class CleanroomCodecTests(unittest.TestCase):
    def test_crc_standard_vector(self):
        self.assertEqual(crc32_mpeg2(b"123456789"), 0x0376E6E7)

    def test_packed_golden_vectors(self):
        vectors = (
            ((0x000, 0x001, 0x002, 0x003), bytes.fromhex("100002000030")),
            ((0xFFF, 0xABC, 0x123, 0x456), bytes.fromhex("cfff23ab4561")),
        )
        for samples, packed in vectors:
            self.assertEqual(encode_group(samples), packed)
            self.assertEqual(decode_group(packed), samples)

    def test_all_values_in_each_packed_position(self):
        sentinels = [0x123, 0x456, 0x789, 0xABC]
        for position in range(4):
            for value in range(4096):
                samples = list(sentinels)
                samples[position] = value
                packed = encode_group(tuple(samples))
                self.assertEqual(decode_group(packed), tuple(samples))

    def test_transpose_is_bijective(self):
        indices = {raster_index(index) for index in range(SAMPLE_COUNT)}
        self.assertEqual(indices, set(range(SAMPLE_COUNT)))

    def test_full_synthetic_record_roundtrip(self):
        raster = tuple(((row * 80 + column) * 37 + row * 11 + column) & 0xFFF
                       for row in range(64) for column in range(80))
        record = encode_synthetic_record(raster)
        self.assertEqual(len(record), RECORD_BYTES)
        self.assertEqual(decode_record(record), raster)

    def test_length_and_corruption_fail_closed(self):
        raster = tuple(index & 0xFFF for index in range(SAMPLE_COUNT))
        record = encode_synthetic_record(raster)
        with self.assertRaises(ValueError):
            decode_record(record[:-1])
        damaged = bytearray(record)
        damaged[4097] ^= 0x04
        with self.assertRaisesRegex(ValueError, "CRC mismatch"):
            decode_record(bytes(damaged))


if __name__ == "__main__":
    unittest.main()

