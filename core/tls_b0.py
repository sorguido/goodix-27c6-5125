# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Reusable TLS-session consumption for Goodix B0 application records.

The FDT bootstrap may ignore the semantic image carried after ``0x20``, but it
must not remove the encrypted B0 record from the transport without feeding the
active TLS session.  This module owns that narrow contract.  It exposes no USB,
secret-store, persistence, image decode, classifier, retry, or device command.
"""

from __future__ import annotations

from dataclasses import dataclass
import hmac
import ssl
from typing import Protocol

from core.post_d4 import TLS, parse_outer


TLS_CIPHER_NAME = "PSK-AES128-GCM-SHA256"
TLS_IDENTITY = "Client_identity"


class TlsB0ConsumptionError(RuntimeError):
    """The B0 record was not authenticated and consumed by active TLS."""


class ActiveTlsApplicationSession(Protocol):
    @property
    def handshake_complete(self) -> bool:
        ...

    def consume_application_record(self, tls_record: bytes) -> bytearray:
        """Authenticate/decrypt one or more TLS records and return plaintext."""


@dataclass(frozen=True)
class B0ConsumptionResult:
    tls_record_consumed: bool
    authenticated: bool
    decrypted: bool
    plaintext_length: int
    plaintext_zeroized: bool

    @property
    def accepted(self) -> bool:
        return (
            self.tls_record_consumed
            and self.authenticated
            and self.decrypted
            and self.plaintext_zeroized
        )


def _split_tls_records(data: bytes) -> tuple[bytes, ...]:
    records: list[bytes] = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < 5:
            raise TlsB0ConsumptionError("partial_tls_record")
        size = 5 + int.from_bytes(data[offset + 3:offset + 5], "big")
        if size < 5 or offset + size > len(data):
            raise TlsB0ConsumptionError("tls_record_length")
        records.append(data[offset:offset + size])
        offset += size
    return tuple(records)


class Tls12PskServerSession:
    """OpenSSL MemoryBIO TLS 1.2 PSK session retained after handshake.

    Tests use synthetic PSK material.  Production callers must supply the same
    already-authorized secret boundary used by the live-proven Linux handshake;
    this class never reads or discovers a secret itself.
    """

    def __init__(self, secret: bytes | bytearray | memoryview):
        if not secret:
            raise ValueError("empty_psk")
        self._owned = bytearray(secret)
        self._input = ssl.MemoryBIO()
        self._output = ssl.MemoryBIO()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers(TLS_CIPHER_NAME)
        context.options |= ssl.OP_NO_TICKET
        context.num_tickets = 0

        def psk(identity: str | None) -> bytes:
            if identity is None or not hmac.compare_digest(identity, TLS_IDENTITY):
                return b""
            return bytes(self._owned)

        context.set_psk_server_callback(psk)
        self._ssl = context.wrap_bio(self._input, self._output, server_side=True)
        self._handshake_complete = False
        self.closed = False
        self.application_record_count = 0

    @property
    def handshake_complete(self) -> bool:
        return self._handshake_complete and not self.closed

    def feed_handshake_bytes(self, data: bytes) -> None:
        if self.closed or self._handshake_complete:
            raise TlsB0ConsumptionError("handshake_feed_wrong_state")
        self._input.write(data)

    def advance_handshake(self) -> None:
        if self.closed or self._handshake_complete:
            raise TlsB0ConsumptionError("handshake_advance_wrong_state")
        try:
            self._ssl.do_handshake()
        except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
            return
        except ssl.SSLError as error:
            raise TlsB0ConsumptionError("tls_handshake_failed") from error
        if self._ssl.version() != "TLSv1.2":
            raise TlsB0ConsumptionError("unexpected_tls_version")
        cipher = self._ssl.cipher()
        if cipher is None or cipher[0] != TLS_CIPHER_NAME:
            raise TlsB0ConsumptionError("unexpected_tls_cipher")
        self._handshake_complete = True

    def drain_encrypted_output(self) -> tuple[bytes, ...]:
        output = bytearray()
        while self._output.pending:
            output.extend(self._output.read())
        return _split_tls_records(bytes(output)) if output else ()

    def consume_application_record(self, tls_record: bytes) -> bytearray:
        if not self.handshake_complete:
            raise TlsB0ConsumptionError("active_tls_session_required")
        plaintext = bytearray()
        try:
            self._input.write(tls_record)
            while True:
                try:
                    chunk = self._ssl.read(65536)
                except ssl.SSLWantReadError:
                    break
                if not chunk:
                    break
                plaintext.extend(chunk)
        except ssl.SSLError as error:
            for index in range(len(plaintext)):
                plaintext[index] = 0
            raise TlsB0ConsumptionError("tls_record_authentication_failed") from error
        if not plaintext:
            raise TlsB0ConsumptionError("tls_application_plaintext_missing")
        self.application_record_count += 1
        return plaintext

    def close(self) -> None:
        if self.closed:
            return
        for index in range(len(self._owned)):
            self._owned[index] = 0
        self.closed = True

    @property
    def secret_zeroized(self) -> bool:
        return self.closed and not any(self._owned)


class B0ApplicationConsumer:
    """Consume, authenticate, decrypt, promptly zeroize, and discard one B0."""

    def __init__(self, session: ActiveTlsApplicationSession):
        self.session = session
        self.consumption_count = 0
        self.plaintext_byte_count = 0

    def consume(self, frame: bytes) -> B0ConsumptionResult:
        kind, tls_record = parse_outer(frame)
        if kind != TLS:
            raise TlsB0ConsumptionError("baseline_record_not_b0")
        if not self.session.handshake_complete:
            raise TlsB0ConsumptionError("active_tls_session_required")
        plaintext = self.session.consume_application_record(tls_record)
        length = len(plaintext)
        for index in range(length):
            plaintext[index] = 0
        zeroized = not any(plaintext)
        self.consumption_count += 1
        self.plaintext_byte_count += length
        return B0ConsumptionResult(
            tls_record_consumed=True,
            authenticated=True,
            decrypted=True,
            plaintext_length=length,
            plaintext_zeroized=zeroized,
        )
