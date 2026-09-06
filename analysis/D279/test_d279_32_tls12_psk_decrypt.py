#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import hashlib
import importlib.util
import ssl
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("d279_32_tls12_psk_decrypt.py")
SPEC = importlib.util.spec_from_file_location("d279_32_tls_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
TLS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = TLS
SPEC.loader.exec_module(TLS)


SYNTHETIC_PSK = bytes(range(32))


@dataclass(frozen=True)
class Record:
    direction: str
    content_type: int
    version: bytes
    fragment: bytes


def split_records(direction: str, data: bytes) -> list[Record]:
    records = []
    offset = 0
    while offset < len(data):
        if offset + 5 > len(data):
            raise AssertionError("truncated synthetic TLS header")
        length = int.from_bytes(data[offset + 3:offset + 5], "big")
        end = offset + 5 + length
        if end > len(data):
            raise AssertionError("truncated synthetic TLS record")
        records.append(Record(direction, data[offset], data[offset + 1:offset + 3],
                              data[offset + 5:end]))
        offset = end
    return records


def handshake_messages(fragment: bytes) -> list[bytes]:
    messages = []
    offset = 0
    while offset < len(fragment):
        length = int.from_bytes(fragment[offset + 1:offset + 4], "big")
        end = offset + 4 + length
        messages.append(fragment[offset:end])
        offset = end
    if offset != len(fragment):
        raise AssertionError("synthetic handshake split")
    return messages


def openssl_psk_transcript(application: bytes) -> list[Record]:
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    for context in (server_context, client_context):
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers("PSK-AES128-GCM-SHA256")
    client_context.check_hostname = False
    client_context.verify_mode = ssl.CERT_NONE
    server_context.set_psk_server_callback(lambda _identity: SYNTHETIC_PSK)
    client_context.set_psk_client_callback(
        lambda _hint: ("Client_identity", SYNTHETIC_PSK)
    )
    client_in, client_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    server_in, server_out = ssl.MemoryBIO(), ssl.MemoryBIO()
    client = client_context.wrap_bio(client_in, client_out, server_side=False)
    server = server_context.wrap_bio(server_in, server_out, server_side=True)
    records: list[Record] = []
    client_done = server_done = False

    def drain(source: ssl.MemoryBIO, destination: ssl.MemoryBIO,
              direction: str) -> bool:
        moved = False
        while True:
            chunk = source.read()
            if not chunk:
                break
            records.extend(split_records(direction, chunk))
            destination.write(chunk)
            moved = True
        return moved

    for _ in range(100):
        if not client_done:
            try:
                client.do_handshake()
                client_done = True
            except ssl.SSLWantReadError:
                pass
        moved = drain(client_out, server_in, "client")
        if not server_done:
            try:
                server.do_handshake()
                server_done = True
            except ssl.SSLWantReadError:
                pass
        moved = drain(server_out, client_in, "server") or moved
        if client_done and server_done and not moved:
            break
    if not (client_done and server_done):
        raise AssertionError("synthetic OpenSSL handshake did not complete")

    self_before = len(records)
    written = client.write(application)
    if written != len(application):
        raise AssertionError("synthetic application short write")
    drain(client_out, server_in, "client")
    if server.read(len(application)) != application:
        raise AssertionError("synthetic application delivery mismatch")
    if len(records) <= self_before:
        raise AssertionError("synthetic application record absent")
    return records


def transcript_inputs(records: list[Record]):
    pre_client_finished = bytearray()
    server_plaintext_after_client_finished = bytearray()
    client_random = server_random = None
    client_encrypted = []
    server_encrypted = []
    client_cipher_on = server_cipher_on = False
    for record in records:
        cipher_on = client_cipher_on if record.direction == "client" else server_cipher_on
        if record.content_type == 0x14:
            if record.direction == "client":
                client_cipher_on = True
            else:
                server_cipher_on = True
            continue
        if cipher_on:
            (client_encrypted if record.direction == "client" else server_encrypted).append(record)
            continue
        if record.content_type != 0x16:
            continue
        for message in handshake_messages(record.fragment):
            if message[0] == 1:
                client_random = message[6:38]
            elif message[0] == 2:
                server_random = message[6:38]
            if client_cipher_on:
                server_plaintext_after_client_finished.extend(message)
            else:
                pre_client_finished.extend(message)
    if client_random is None or server_random is None:
        raise AssertionError("synthetic random absent")
    return (bytes(pre_client_finished),
            bytes(server_plaintext_after_client_finished),
            client_random, server_random, client_encrypted, server_encrypted)


@unittest.skipUnless(hasattr(ssl.SSLContext, "set_psk_client_callback"),
                     "Python OpenSSL PSK callbacks unavailable")
class Tls12PskDecryptTests(unittest.TestCase):
    def test_prf_matches_independent_openssl_kdf_vector(self) -> None:
        expected = bytes.fromhex(
            "c4f064f337bb25748806723d3168a4f9e7466bf88e71e67e602b303942cd2607"
            "9458799a187cd65a0480b3450e94d171"
        )
        actual = TLS.tls12_prf(
            b"0123456789abcdefghijklmnopqrstuv",
            b"master secret",
            b"C" * 32 + b"S" * 32,
            48,
        )
        self.assertEqual(actual, expected)
        TLS.cleanse(actual)

    def test_independent_openssl_handshake_finished_and_application(self) -> None:
        application = b"D279_32_SYNTHETIC_APPLICATION_DATA"
        records = openssl_psk_transcript(application)
        transcript, server_extra, client_random, server_random, client_records, server_records = (
            transcript_inputs(records)
        )
        self.assertGreaterEqual(len(client_records), 2)
        self.assertGreaterEqual(len(server_records), 1)
        keys = TLS.derive_session_keys(
            SYNTHETIC_PSK, client_random, server_random,
            session_hash=hashlib.sha256(transcript).digest(),
        )
        with keys:
            client_finished = TLS.decrypt_aes128_gcm_record(
                keys.client_write_key, keys.client_fixed_iv, 0,
                client_records[0].content_type, client_records[0].version,
                client_records[0].fragment,
            )
            TLS.verify_finished(keys, b"client finished", transcript, client_finished)
            server_finished = TLS.decrypt_aes128_gcm_record(
                keys.server_write_key, keys.server_fixed_iv, 0,
                server_records[0].content_type, server_records[0].version,
                server_records[0].fragment,
            )
            # Session tickets are sent after the client Finished and before
            # the server Finished by current OpenSSL. They enter the latter
            # transcript after the decrypted client Finished.
            TLS.verify_finished(
                keys, b"server finished",
                transcript + client_finished + server_extra,
                server_finished,
            )
            recovered = TLS.decrypt_aes128_gcm_record(
                keys.client_write_key, keys.client_fixed_iv, 1,
                client_records[1].content_type, client_records[1].version,
                client_records[1].fragment,
            )
            self.assertEqual(recovered, application)
            TLS.cleanse(client_finished)
            TLS.cleanse(server_finished)
            TLS.cleanse(recovered)
        self.assertTrue(keys.closed)
        self.assertFalse(any(keys.master_secret))
        self.assertFalse(any(keys.client_write_key))

    def test_wrong_psk_and_sequence_fail_authentication(self) -> None:
        application = b"SYNTHETIC"
        records = openssl_psk_transcript(application)
        transcript, _, client_random, server_random, client_records, _ = transcript_inputs(records)
        wrong_psk = bytes(reversed(SYNTHETIC_PSK))
        session_hash = hashlib.sha256(transcript).digest()
        with TLS.derive_session_keys(
                wrong_psk, client_random, server_random,
                session_hash=session_hash) as keys:
            with self.assertRaisesRegex(TLS.TlsPskError,
                                        "TLS_GCM_AUTHENTICATION_FAILED"):
                TLS.decrypt_aes128_gcm_record(
                    keys.client_write_key, keys.client_fixed_iv, 0,
                    client_records[0].content_type, client_records[0].version,
                    client_records[0].fragment,
                )
        with TLS.derive_session_keys(
                SYNTHETIC_PSK, client_random, server_random,
                session_hash=session_hash) as keys:
            with self.assertRaisesRegex(TLS.TlsPskError,
                                        "TLS_GCM_AUTHENTICATION_FAILED"):
                TLS.decrypt_aes128_gcm_record(
                    keys.client_write_key, keys.client_fixed_iv, 7,
                    client_records[0].content_type, client_records[0].version,
                    client_records[0].fragment,
                )

    def test_mutable_key_owner_is_cleansed(self) -> None:
        keys = TLS.derive_session_keys(SYNTHETIC_PSK, b"C" * 32, b"S" * 32)
        self.assertTrue(any(keys.master_secret))
        keys.close()
        keys.close()
        self.assertTrue(keys.closed)
        for field in (keys.master_secret, keys.client_write_key,
                      keys.server_write_key, keys.client_fixed_iv,
                      keys.server_fixed_iv):
            self.assertFalse(any(field))


if __name__ == "__main__":
    unittest.main()
