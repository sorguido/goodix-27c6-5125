#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import importlib.util
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


MODULE_PATH = Path(__file__).with_name("d279_33_attempt02_in_memory_composer.py")
SPEC = importlib.util.spec_from_file_location("d279_33_composer_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
COMPOSER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = COMPOSER
SPEC.loader.exec_module(COMPOSER)


PSK = bytearray(range(32))


@dataclass(frozen=True)
class Record:
    content_type: int
    version: bytes
    fragment: bytes


def encrypted_record(key: bytes | bytearray, fixed_iv: bytes | bytearray,
                     sequence: int, content_type: int, plaintext: bytes) -> Record:
    explicit = sequence.to_bytes(8, "big")
    aad = (explicit + bytes((content_type,)) + b"\x03\x03" +
           len(plaintext).to_bytes(2, "big"))
    fragment = explicit + AESGCM(bytes(key)).encrypt(
        bytes(fixed_iv) + explicit, plaintext, aad
    )
    return Record(content_type, b"\x03\x03", fragment)


def synthetic_session(applications: list[bytes], *, bad_server_finished: bool = False):
    client_random, server_random = b"C" * 32, b"S" * 32
    transcript = (
        b"\x01\x00\x00\x03CH!" + b"\x02\x00\x00\x03SH!" +
        b"\x0e\x00\x00\x00" + b"\x10\x00\x00\x02\x00\x00"
    )
    with COMPOSER.D32.derive_session_keys(
        PSK, client_random, server_random, session_hash=None
    ) as keys:
        client_plain = COMPOSER.D32.finished_message(
            keys, b"client finished", transcript
        )
        server_plain = COMPOSER.D32.finished_message(
            keys, b"server finished", transcript + client_plain
        )
        if bad_server_finished:
            server_plain[-1] ^= 1
        client_finished = encrypted_record(
            keys.client_write_key, keys.client_fixed_iv, 0, 0x16,
            bytes(client_plain),
        )
        server_finished = encrypted_record(
            keys.server_write_key, keys.server_fixed_iv, 0, 0x16,
            bytes(server_plain),
        )
        app_records = tuple(
            encrypted_record(keys.client_write_key, keys.client_fixed_iv,
                             sequence, 0x17, plaintext)
            for sequence, plaintext in enumerate(applications, start=1)
        )
        COMPOSER.D32.cleanse(client_plain)
        COMPOSER.D32.cleanse(server_plain)
    return COMPOSER.NonEmsSession(
        client_random, server_random, transcript,
        client_finished, server_finished, app_records,
    )


def synthetic_image_payload() -> bytes:
    from src.goodix5125_cleanroom import encode_synthetic_record

    record = encode_synthetic_record(tuple([0x321] * 5120))
    data = b"\x00\x00\x00\x00\x00" + record
    declared = len(data) + 1
    return bytes((0x20, declared & 0xFF, declared >> 8)) + data + b"\x88"


class Attempt02ComposerTests(unittest.TestCase):
    def test_real_capture_profile_requires_no_psk_or_decryption(self) -> None:
        session = COMPOSER.extract_target_session()
        self.assertEqual(len(session.client_random), 32)
        self.assertEqual(len(session.server_random), 32)
        self.assertEqual(len(session.application_records), 43)
        self.assertEqual(session.client_finished.direction, "device_to_host")
        self.assertEqual(session.server_finished.direction, "host_to_device")
        self.assertTrue(all(len(record.fragment) == 7717
                            for record in session.application_records))

    def test_classic_finished_application_and_canonical_image_decode(self) -> None:
        payload = synthetic_image_payload()
        session = synthetic_session([payload, payload])
        result = COMPOSER.decrypt_non_ems_session(
            session, bytearray(PSK), expected_application_count=2,
            expected_plaintext_length=7693, decode_images=True,
        )
        self.assertEqual([bytes(item) for item in result.plaintexts],
                         [payload, payload])
        self.assertEqual(len(result.rasters), 2)
        self.assertEqual(result.rasters[0].tolist(), [0x321] * 5120)
        result.close()
        result.close()
        self.assertTrue(result.closed)
        self.assertTrue(all(not any(item) for item in result.plaintexts))
        self.assertTrue(all(not any(item) for item in result.rasters))

    def test_server_finished_mismatch_fails_closed(self) -> None:
        session = synthetic_session([b"X" * 9], bad_server_finished=True)
        with self.assertRaisesRegex(
            COMPOSER.D32.TlsPskError, "TLS_FINISHED_VERIFY_FAILED"
        ):
            COMPOSER.decrypt_non_ems_session(
                session, bytearray(PSK), expected_application_count=1,
                expected_plaintext_length=9, decode_images=False,
            )

    def test_requires_mutable_caller_owned_psk(self) -> None:
        session = synthetic_session([b"X"])
        with self.assertRaisesRegex(
            COMPOSER.ComposerError, "CALLER_OWNED_MUTABLE_PSK_REQUIRED"
        ):
            COMPOSER.decrypt_non_ems_session(
                session, bytes(PSK), expected_application_count=1,
                expected_plaintext_length=1, decode_images=False,
            )


if __name__ == "__main__":
    unittest.main()
