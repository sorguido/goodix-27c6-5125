#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Composer offline bounded per ATTEMPT02 TLS -> raster canonici.

Il modulo non offre CLI, non apre secret e non conosce il layout production.
La sola lettura file implementata dal parser sottostante riguarda la capture
privata hash-gated. La PSK deve essere fornita dal chiamante come ``bytearray``;
il chiamante ne conserva ownership e responsabilita' di azzeramento.

I plaintext e i raster owned dal risultato vengono azzerati da ``close()``.
Come per D279/32, non viene dichiarata la zeroizzazione delle copie temporanee
interne create dal runtime Python o dalla libreria crittografica.
"""

from __future__ import annotations

import importlib.util
import sys
from array import array
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
D31_PATH = Path(__file__).with_name(
    "d279_31_attempt02_tls_reconstruction_feasibility.py"
)
D32_PATH = Path(__file__).with_name("d279_32_tls12_psk_decrypt.py")


class ComposerError(RuntimeError):
    """Profilo, autenticazione o immagine fuori dal contratto bounded."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ComposerError(message)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"{name}_NOT_LOADABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


D31 = _load_module("d279_33_d31", D31_PATH)
D32 = _load_module("d279_33_d32", D32_PATH)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from core.post_d4 import parse_image_payload  # noqa: E402


@dataclass(frozen=True)
class NonEmsSession:
    client_random: bytes
    server_random: bytes
    handshake_transcript: bytes
    client_finished: object
    server_finished: object
    application_records: tuple[object, ...]


@dataclass
class DecryptedAttempt:
    """Owned plaintext/raster buffers with explicit best-effort cleansing."""

    plaintexts: list[bytearray]
    rasters: list[array]
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        for plaintext in self.plaintexts:
            D32.cleanse(plaintext)
        for raster in self.rasters:
            for index in range(len(raster)):
                raster[index] = 0
        self.closed = True

    def __enter__(self) -> "DecryptedAttempt":
        require(not self.closed, "DECRYPTED_ATTEMPT_CLOSED")
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()


def extract_target_session(capture: Path = D31.CAPTURE) -> NonEmsSession:
    """Extract the exact hash-gated ATTEMPT02 record profile without a PSK."""

    audit = D31.analyze(capture)
    handshake = audit["handshake"]
    require(not handshake["client_hello"]["extended_master_secret_offered"],
            "TARGET_CLIENT_OFFERED_EMS")
    require(not handshake["server_hello"]["extended_master_secret_selected"],
            "TARGET_SERVER_SELECTED_EMS")

    packets = D31.D274.parse_usbpcap_bytes(capture.read_bytes())
    frames, firmware_ok = D31.D274._target_frames(packets, include_incomplete=False)
    require(firmware_ok, "APP12509_NOT_OBSERVED")
    records = tuple(D31.parse_single_tls_record(frame)
                    for frame in frames if frame.outer == 0xB0)
    require(len(records) == 51, "TARGET_TLS_RECORD_COUNT")

    client_hello, server_hello, server_done, client_key = records[:4]
    client_body = D31.parse_handshake(client_hello, 0x01)
    server_body = D31.parse_handshake(server_hello, 0x02)
    D31.parse_handshake(server_done, 0x0E)
    D31.parse_handshake(client_key, 0x10)
    require(client_body[:2] == b"\x03\x03" and len(client_body) >= 34,
            "TARGET_CLIENT_HELLO_RANDOM")
    require(server_body[:2] == b"\x03\x03" and len(server_body) >= 34,
            "TARGET_SERVER_HELLO_RANDOM")

    transcript = b"".join(record.fragment for record in records[:4])
    require(records[4].content_type == 0x14 and records[4].fragment == b"\x01",
            "TARGET_CLIENT_CCS")
    require(records[6].content_type == 0x14 and records[6].fragment == b"\x01",
            "TARGET_SERVER_CCS")
    return NonEmsSession(
        client_random=client_body[2:34],
        server_random=server_body[2:34],
        handshake_transcript=transcript,
        client_finished=records[5],
        server_finished=records[7],
        application_records=records[8:],
    )


def decrypt_non_ems_session(
    session: NonEmsSession,
    psk: bytearray,
    *,
    expected_application_count: int,
    expected_plaintext_length: int,
    decode_images: bool,
) -> DecryptedAttempt:
    """Authenticate and decrypt one classic TLS 1.2 PSK session.

    This generic seam exists for synthetic tests. It has no file or protected
    material loader. The target wrapper below fixes the OEM counts and enables
    canonical image decoding.
    """

    require(type(psk) is bytearray, "CALLER_OWNED_MUTABLE_PSK_REQUIRED")
    require(len(session.application_records) == expected_application_count,
            "APPLICATION_RECORD_COUNT")
    require(session.client_finished.content_type == 0x16,
            "CLIENT_FINISHED_CONTENT_TYPE")
    require(session.server_finished.content_type == 0x16,
            "SERVER_FINISHED_CONTENT_TYPE")

    plaintexts: list[bytearray] = []
    rasters: list[array] = []
    client_finished_plaintext = None
    server_finished_plaintext = None
    result = DecryptedAttempt(plaintexts, rasters)
    try:
        with D32.derive_session_keys(
            psk, session.client_random, session.server_random,
            session_hash=None,
        ) as keys:
            client_finished_plaintext = D32.decrypt_aes128_gcm_record(
                keys.client_write_key, keys.client_fixed_iv, 0,
                session.client_finished.content_type,
                session.client_finished.version,
                session.client_finished.fragment,
            )
            D32.verify_finished(
                keys, b"client finished", session.handshake_transcript,
                client_finished_plaintext,
            )

            server_finished_plaintext = D32.decrypt_aes128_gcm_record(
                keys.server_write_key, keys.server_fixed_iv, 0,
                session.server_finished.content_type,
                session.server_finished.version,
                session.server_finished.fragment,
            )
            D32.verify_finished(
                keys, b"server finished",
                session.handshake_transcript + client_finished_plaintext,
                server_finished_plaintext,
            )

            for sequence, record in enumerate(session.application_records, start=1):
                require(record.content_type == 0x17,
                        "APPLICATION_RECORD_CONTENT_TYPE")
                plaintext = D32.decrypt_aes128_gcm_record(
                    keys.client_write_key, keys.client_fixed_iv, sequence,
                    record.content_type, record.version, record.fragment,
                )
                plaintexts.append(plaintext)
                require(len(plaintext) == expected_plaintext_length,
                        "APPLICATION_PLAINTEXT_LENGTH")
                if decode_images:
                    rasters.append(array("H", parse_image_payload(plaintext)))
        return result
    except Exception:
        result.close()
        raise
    finally:
        D32.cleanse(client_finished_plaintext)
        D32.cleanse(server_finished_plaintext)


def decrypt_target_attempt(
    psk: bytearray, capture: Path = D31.CAPTURE
) -> DecryptedAttempt:
    """Compose the exact ATTEMPT02 profile; does not load or cleanse ``psk``."""

    session = extract_target_session(capture)
    require(len(session.application_records) == 43,
            "TARGET_APPLICATION_RECORD_COUNT")
    require(all(record.direction == "device_to_host"
                for record in session.application_records),
            "TARGET_APPLICATION_DIRECTION")
    require(all(len(record.fragment) == 7717
                for record in session.application_records),
            "TARGET_APPLICATION_CIPHERTEXT_LENGTH")
    return decrypt_non_ems_session(
        session,
        psk,
        expected_application_count=43,
        expected_plaintext_length=7693,
        decode_images=True,
    )

