#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Audit metadata-only della fattibilità di ricostruzione TLS ATTEMPT02.

Legge la capture privata hash-gated e verifica esclusivamente struttura,
direzioni, handshake e conteggi dei record. Non accetta PSK, non decifra record
e non esporta random, nonce, ciphertext, plaintext, raster o hash biometrici.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ATTEMPT_ID = "D27910_20260905_ATTEMPT02"
CAPTURE_SHA256 = "3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab"
CAPTURE = ROOT / "captures" / "D279_10" / ATTEMPT_ID / "raw" / "wire.pcapng"
D274_PATH = ROOT / (
    "analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/"
    "d274_03_postprocess_second_cycle.py"
)


class FeasibilityError(RuntimeError):
    """Capture assente, incoerente o insufficiente per il contratto."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FeasibilityError(message)


def _load_d274():
    spec = importlib.util.spec_from_file_location("d279_31_d274", D274_PATH)
    require(spec is not None and spec.loader is not None, "D274_MODULE_NOT_LOADABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


D274 = _load_d274()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class TlsRecord:
    frame_index: int
    direction: str
    content_type: int
    version: bytes
    fragment: bytes


def parse_single_tls_record(frame) -> TlsRecord:
    require(frame.outer == 0xB0 and not frame.truncated, "NOT_COMPLETE_B0")
    wrapped = frame.raw[4:]
    require(len(wrapped) >= 5, "TLS_RECORD_HEADER_TRUNCATED")
    declared = int.from_bytes(wrapped[3:5], "big")
    require(len(wrapped) == 5 + declared, "B0_NOT_EXACTLY_ONE_TLS_RECORD")
    require(wrapped[1:3] == b"\x03\x03", "TLS_RECORD_VERSION_NOT_1_2")
    return TlsRecord(
        frame_index=frame.packet_index,
        direction=frame.direction,
        content_type=wrapped[0],
        version=wrapped[1:3],
        fragment=wrapped[5:],
    )


def parse_handshake(record: TlsRecord, expected_type: int) -> bytes:
    require(record.content_type == 0x16, "NOT_HANDSHAKE_RECORD")
    require(len(record.fragment) >= 4, "HANDSHAKE_HEADER_TRUNCATED")
    require(record.fragment[0] == expected_type, "UNEXPECTED_HANDSHAKE_TYPE")
    declared = int.from_bytes(record.fragment[1:4], "big")
    require(len(record.fragment) == 4 + declared, "HANDSHAKE_LENGTH_MISMATCH")
    return record.fragment[4:]


def hello_extension_types(body: bytes, cursor: int) -> tuple[int, ...]:
    if cursor == len(body):
        return ()
    require(cursor + 2 <= len(body), "HELLO_EXTENSION_VECTOR")
    total = int.from_bytes(body[cursor:cursor + 2], "big")
    cursor += 2
    end = cursor + total
    require(end == len(body), "HELLO_EXTENSION_VECTOR")
    result = []
    while cursor < end:
        require(cursor + 4 <= end, "HELLO_EXTENSION_HEADER")
        extension_type = int.from_bytes(body[cursor:cursor + 2], "big")
        length = int.from_bytes(body[cursor + 2:cursor + 4], "big")
        cursor += 4
        require(cursor + length <= end, "HELLO_EXTENSION_LENGTH")
        result.append(extension_type)
        cursor += length
    return tuple(result)


def client_hello_metadata(record: TlsRecord) -> dict:
    body = parse_handshake(record, 0x01)
    require(len(body) >= 35 and body[:2] == b"\x03\x03", "CLIENT_HELLO_SHAPE")
    cursor = 34
    session_length = body[cursor]
    cursor += 1 + session_length
    require(cursor + 2 <= len(body), "CLIENT_HELLO_SESSION_VECTOR")
    suites_length = int.from_bytes(body[cursor:cursor + 2], "big")
    cursor += 2
    require(suites_length >= 2 and suites_length % 2 == 0,
            "CLIENT_HELLO_CIPHER_VECTOR")
    require(cursor + suites_length <= len(body), "CLIENT_HELLO_CIPHER_VECTOR")
    suites = [int.from_bytes(body[index:index + 2], "big")
              for index in range(cursor, cursor + suites_length, 2)]
    cursor += suites_length
    require(cursor < len(body), "CLIENT_HELLO_COMPRESSION_VECTOR")
    compression_length = body[cursor]
    cursor += 1
    require(cursor + compression_length <= len(body),
            "CLIENT_HELLO_COMPRESSION_VECTOR")
    cursor += compression_length
    extensions = hello_extension_types(body, cursor)
    return {
        "tls12_version": True,
        "client_random_present": True,
        "offered_cipher_0x00a8": 0x00A8 in suites,
        "cipher_suite_count": len(suites),
        "extended_master_secret_offered": 0x0017 in extensions,
    }


def server_hello_metadata(record: TlsRecord) -> dict:
    body = parse_handshake(record, 0x02)
    require(len(body) >= 38 and body[:2] == b"\x03\x03", "SERVER_HELLO_SHAPE")
    session_length = body[34]
    cursor = 35 + session_length
    require(cursor + 3 <= len(body), "SERVER_HELLO_SESSION_VECTOR")
    selected = int.from_bytes(body[cursor:cursor + 2], "big")
    cursor += 3
    extensions = hello_extension_types(body, cursor)
    return {
        "tls12_version": True,
        "server_random_present": True,
        "selected_cipher": f"0x{selected:04x}",
        "selected_cipher_is_psk_aes128_gcm_sha256": selected == 0x00A8,
        "extended_master_secret_selected": 0x0017 in extensions,
    }


def client_key_exchange_metadata(record: TlsRecord) -> dict:
    body = parse_handshake(record, 0x10)
    require(len(body) >= 2, "CLIENT_KEY_EXCHANGE_SHAPE")
    identity_length = int.from_bytes(body[:2], "big")
    require(len(body) == 2 + identity_length, "CLIENT_KEY_EXCHANGE_IDENTITY_LENGTH")
    identity = body[2:]
    return {
        "psk_identity_present": True,
        "psk_identity_is_expected_client_identity": identity == b"Client_identity",
        "psk_identity_value_exported": False,
    }


def analyze(capture: Path = CAPTURE) -> dict:
    require(sha256_file(capture) == CAPTURE_SHA256, "CAPTURE_SHA256_MISMATCH")
    packets = D274.parse_usbpcap_bytes(capture.read_bytes())
    frames, firmware_ok = D274._target_frames(packets, include_incomplete=False)
    require(firmware_ok, "APP12509_NOT_OBSERVED")
    records = [parse_single_tls_record(frame) for frame in frames if frame.outer == 0xB0]
    require(len(records) == 51, "B0_TLS_RECORD_COUNT")

    client_hello = records[0]
    server_hello = records[1]
    server_done = records[2]
    client_key = records[3]
    client_ccs = records[4]
    client_finished = records[5]
    server_ccs = records[6]
    server_finished = records[7]
    application = records[8:]

    require(client_hello.direction == "device_to_host", "CLIENT_HELLO_DIRECTION")
    require(server_hello.direction == "host_to_device", "SERVER_HELLO_DIRECTION")
    require(server_done.direction == "host_to_device", "SERVER_DONE_DIRECTION")
    require(client_key.direction == "device_to_host", "CLIENT_KEY_DIRECTION")
    parse_handshake(server_done, 0x0E)
    client_meta = client_hello_metadata(client_hello)
    server_meta = server_hello_metadata(server_hello)
    key_meta = client_key_exchange_metadata(client_key)
    require(client_meta["offered_cipher_0x00a8"], "CIPHER_0X00A8_NOT_OFFERED")
    require(server_meta["selected_cipher_is_psk_aes128_gcm_sha256"],
            "CIPHER_0X00A8_NOT_SELECTED")
    require(key_meta["psk_identity_is_expected_client_identity"],
            "UNEXPECTED_PSK_IDENTITY")

    require(client_ccs.direction == "device_to_host" and
            client_ccs.content_type == 0x14 and client_ccs.fragment == b"\x01",
            "CLIENT_CCS_SHAPE")
    require(server_ccs.direction == "host_to_device" and
            server_ccs.content_type == 0x14 and server_ccs.fragment == b"\x01",
            "SERVER_CCS_SHAPE")
    require(client_finished.direction == "device_to_host" and
            client_finished.content_type == 0x16 and len(client_finished.fragment) == 40,
            "CLIENT_ENCRYPTED_FINISHED_SHAPE")
    require(server_finished.direction == "host_to_device" and
            server_finished.content_type == 0x16 and len(server_finished.fragment) == 40,
            "SERVER_ENCRYPTED_FINISHED_SHAPE")

    require(len(application) == 43, "APPLICATION_RECORD_COUNT")
    require(all(record.direction == "device_to_host" for record in application),
            "APPLICATION_RECORD_DIRECTION")
    require(all(record.content_type == 0x17 for record in application),
            "APPLICATION_RECORD_TYPE")
    require(all(len(record.fragment) == 7717 for record in application),
            "APPLICATION_RECORD_LENGTH")
    fingerprint_frames = [frame for frame in frames
                          if frame.outer == 0xB0 and
                          D274.classify_b0(frame) == "FINGERPRINT_B0"]
    require([record.frame_index for record in application] ==
            [frame.packet_index for frame in fingerprint_frames],
            "APPLICATION_TO_FINGERPRINT_B0_IDENTITY")

    return {
        "schema": "D279_31_ATTEMPT02_TLS_RECONSTRUCTION_FEASIBILITY_V1",
        "attempt_id": ATTEMPT_ID,
        "capture_sha256": CAPTURE_SHA256,
        "target_firmware": "GF_ST411SEC_APP_12509",
        "source_integrity": {
            "pcapng_packet_count": len(packets),
            "target_frame_count": len(frames),
            "b0_tls_record_count": len(records),
            "all_b0_wrap_exactly_one_tls_record": True,
        },
        "handshake": {
            "client_hello": client_meta,
            "server_hello": server_meta,
            "server_hello_done_present": True,
            "client_key_exchange": key_meta,
            "client_change_cipher_spec_present": True,
            "client_encrypted_finished_present": True,
            "server_change_cipher_spec_present": True,
            "server_encrypted_finished_present": True,
            "complete_from_client_hello_through_both_finished": True,
        },
        "application_records": {
            "device_to_host_count": len(application),
            "host_to_device_count": 0,
            "all_tls_application_data": True,
            "all_ciphertext_fragment_length": 7717,
            "fingerprint_shape_b0_identity_count": len(fingerprint_frames),
            "baseline_primary_auxiliary_decomposition": "1_PLUS_21_PLUS_21",
        },
        "record_sequence_assignment": {
            "client_encrypted_finished_sequence": 0,
            "client_application_sequence_first": 1,
            "client_application_sequence_last": 43,
            "server_encrypted_finished_sequence": 0,
            "record_gap_detected": False,
        },
        "passive_reconstruction": {
            "cipher": "TLS_PSK_WITH_AES_128_GCM_SHA256_0x00a8",
            "client_random_available_in_capture": True,
            "server_random_available_in_capture": True,
            "explicit_record_nonce_available_in_capture": True,
            "record_type_version_length_and_sequence_available": True,
            "protected_psk_required": True,
            "other_missing_cryptographic_input": False,
            "feasibility": "FEASIBLE_WITH_AUTHORIZED_TARGET_PSK",
            "psk_accessed": False,
            "records_decrypted": 0,
        },
        "privacy": {
            "ciphertext_exported": False,
            "handshake_random_exported": False,
            "record_nonce_exported": False,
            "plaintext_exported": False,
            "raster_exported": False,
            "template_exported": False,
            "biometric_hash_exported": False,
            "secret_exported": False,
        },
        "next_gate": "HUMAN_GATE_AUTHORIZED_PROTECTED_PSK_READ_FOR_IN_MEMORY_OFFLINE_EVALUATION",
        "live_or_usb_action_required": False,
        "live_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, default=CAPTURE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = analyze(args.capture)
        serialized = json.dumps(result, indent=2) + "\n"
        if args.output is None:
            print(serialized, end="")
        else:
            require(not args.output.exists(), "OUTPUT_COLLISION")
            args.output.write_text(serialized, encoding="utf-8")
            print(json.dumps({"feasibility": result["passive_reconstruction"]["feasibility"]}))
        return 0
    except (FeasibilityError, OSError, ValueError) as exc:
        print(json.dumps({"feasibility": "FAIL_CLOSED", "failure_class": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
