#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Primitive bounded per TLS 1.2 pure-PSK AES-128-GCM offline.

Il modulo non apre file, non conosce path production e non offre una CLI che
accetti secret. È destinato a essere composto soltanto dopo review con un
loader protetto separato. I buffer mutabili owned dal modulo vengono azzerati;
le copie interne del runtime Python/OpenSSL non sono dichiarate osservabili o
provabilmente azzerate.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


TLS12_VERSION = b"\x03\x03"
TLS_PSK_AES128_GCM_SHA256 = 0x00A8
AES_KEY_LENGTH = 16
GCM_FIXED_IV_LENGTH = 4
GCM_EXPLICIT_NONCE_LENGTH = 8
GCM_TAG_LENGTH = 16
FINISHED_VERIFY_LENGTH = 12


class TlsPskError(RuntimeError):
    """Input o autenticazione TLS fuori dal contratto bounded."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TlsPskError(message)


def cleanse(buffer: bytearray | None) -> None:
    if buffer is not None:
        buffer[:] = b"\x00" * len(buffer)


def p_hash_sha256(secret: bytes | bytearray, seed: bytes, length: int) -> bytearray:
    require(bool(secret) and length >= 0, "P_HASH_ARGUMENT")
    output = bytearray()
    a = hmac.new(secret, seed, hashlib.sha256).digest()
    while len(output) < length:
        output.extend(hmac.new(secret, a + seed, hashlib.sha256).digest())
        a = hmac.new(secret, a, hashlib.sha256).digest()
    del output[length:]
    return output


def tls12_prf(secret: bytes | bytearray, label: bytes, seed: bytes,
              length: int) -> bytearray:
    require(label in (b"master secret", b"extended master secret",
                      b"key expansion", b"client finished",
                      b"server finished"), "PRF_LABEL_OUT_OF_ALLOWLIST")
    return p_hash_sha256(secret, label + seed, length)


@dataclass
class SessionKeys:
    master_secret: bytearray
    client_write_key: bytearray
    server_write_key: bytearray
    client_fixed_iv: bytearray
    server_fixed_iv: bytearray
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        cleanse(self.master_secret)
        cleanse(self.client_write_key)
        cleanse(self.server_write_key)
        cleanse(self.client_fixed_iv)
        cleanse(self.server_fixed_iv)
        self.closed = True

    def __enter__(self) -> "SessionKeys":
        require(not self.closed, "SESSION_KEYS_CLOSED")
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()


def derive_session_keys(psk: bytes | bytearray, client_random: bytes,
                        server_random: bytes,
                        *, session_hash: bytes | None = None) -> SessionKeys:
    require(len(psk) == 32, "TARGET_PSK_LENGTH")
    require(len(client_random) == 32 and len(server_random) == 32,
            "TLS_RANDOM_LENGTH")
    premaster = bytearray()
    key_block = None
    try:
        premaster.extend(len(psk).to_bytes(2, "big"))
        premaster.extend(b"\x00" * len(psk))
        premaster.extend(len(psk).to_bytes(2, "big"))
        premaster.extend(psk)
        if session_hash is None:
            master = tls12_prf(premaster, b"master secret",
                               client_random + server_random, 48)
        else:
            require(len(session_hash) == hashlib.sha256().digest_size,
                    "EXTENDED_MASTER_SESSION_HASH_LENGTH")
            master = tls12_prf(premaster, b"extended master secret",
                               session_hash, 48)
        key_block = tls12_prf(
            master, b"key expansion", server_random + client_random,
            2 * (AES_KEY_LENGTH + GCM_FIXED_IV_LENGTH),
        )
        return SessionKeys(
            master_secret=master,
            client_write_key=bytearray(key_block[0:16]),
            server_write_key=bytearray(key_block[16:32]),
            client_fixed_iv=bytearray(key_block[32:36]),
            server_fixed_iv=bytearray(key_block[36:40]),
        )
    finally:
        cleanse(premaster)
        cleanse(key_block)


def decrypt_aes128_gcm_record(key: bytes | bytearray,
                              fixed_iv: bytes | bytearray,
                              sequence: int, content_type: int,
                              version: bytes, fragment: bytes) -> bytearray:
    require(len(key) == AES_KEY_LENGTH, "AES_KEY_LENGTH")
    require(len(fixed_iv) == GCM_FIXED_IV_LENGTH, "GCM_FIXED_IV_LENGTH")
    require(0 <= sequence < 1 << 64, "TLS_SEQUENCE_RANGE")
    require(content_type in (0x15, 0x16, 0x17), "TLS_CONTENT_TYPE")
    require(version == TLS12_VERSION, "TLS_RECORD_VERSION")
    require(len(fragment) >= GCM_EXPLICIT_NONCE_LENGTH + GCM_TAG_LENGTH,
            "TLS_GCM_FRAGMENT_LENGTH")
    explicit = fragment[:GCM_EXPLICIT_NONCE_LENGTH]
    ciphertext_and_tag = fragment[GCM_EXPLICIT_NONCE_LENGTH:]
    plaintext_length = len(ciphertext_and_tag) - GCM_TAG_LENGTH
    nonce = bytes(fixed_iv) + explicit
    aad = (sequence.to_bytes(8, "big") + bytes((content_type,)) + version +
           plaintext_length.to_bytes(2, "big"))
    try:
        return bytearray(AESGCM(bytes(key)).decrypt(nonce, ciphertext_and_tag, aad))
    except Exception as exc:
        raise TlsPskError("TLS_GCM_AUTHENTICATION_FAILED") from exc


def finished_message(keys: SessionKeys, label: bytes,
                     handshake_transcript: bytes) -> bytearray:
    require(not keys.closed, "SESSION_KEYS_CLOSED")
    transcript_hash = hashlib.sha256(handshake_transcript).digest()
    verify = tls12_prf(keys.master_secret, label, transcript_hash,
                       FINISHED_VERIFY_LENGTH)
    try:
        return bytearray(b"\x14\x00\x00\x0c") + verify
    finally:
        cleanse(verify)


def verify_finished(keys: SessionKeys, label: bytes,
                    handshake_transcript: bytes,
                    plaintext: bytes | bytearray) -> None:
    expected = finished_message(keys, label, handshake_transcript)
    try:
        require(hmac.compare_digest(expected, plaintext),
                "TLS_FINISHED_VERIFY_FAILED")
    finally:
        cleanse(expected)
