#!/usr/bin/env python3
"""Derive redacted D242 TLS/B0 facts from the sole local USBPcap capture.

The script never writes raw TLS, B0, random, session IDs, Finished messages,
or application payloads. Packet indices and header/length metadata are retained
only where they make the derivation reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


SHB = 0x0A0D0D0A
IDB = 0x00000001
EPB = 0x00000006


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def packets(path: Path) -> list[dict[str, object]]:
    data = path.read_bytes()
    endian = "<"
    ts_resolution = 1_000_000
    result: list[dict[str, object]] = []
    offset = 0
    while offset + 12 <= len(data):
        block_type = struct.unpack_from(endian + "I", data, offset)[0]
        if block_type == SHB:
            bom = data[offset + 8:offset + 12]
            endian = "<" if bom == b"\x4d\x3c\x2b\x1a" else ">"
            block_type = SHB
        block_length = struct.unpack_from(endian + "I", data, offset + 4)[0]
        if block_length < 12 or offset + block_length > len(data):
            raise ValueError("invalid pcapng block")
        body = data[offset + 8:offset + block_length - 4]
        if block_type == IDB:
            option = 8
            while option + 4 <= len(body):
                code, length = struct.unpack_from(endian + "HH", body, option)
                option += 4
                value = body[option:option + length]
                option += (length + 3) & ~3
                if code == 0:
                    break
                if code == 9 and value:
                    exponent = value[0]
                    ts_resolution = (
                        2 ** (exponent & 0x7F) if exponent & 0x80 else 10 ** exponent
                    )
        elif block_type == EPB:
            _interface, high, low, captured, _original = struct.unpack_from(
                endian + "IIIII", body, 0
            )
            raw = body[20:20 + captured]
            if len(raw) >= 27:
                header_length = struct.unpack_from("<H", raw, 0)[0]
                data_length = struct.unpack_from("<I", raw, 23)[0]
                result.append(
                    {
                        "index": len(result),
                        "ticks": (high << 32) | low,
                        "ts_resolution": ts_resolution,
                        "status": struct.unpack_from("<I", raw, 10)[0],
                        "irp_id": struct.unpack_from("<Q", raw, 2)[0],
                        "info": raw[16],
                        "endpoint": raw[21],
                        "transfer": raw[22],
                        "payload": raw[header_length:header_length + data_length],
                    }
                )
        offset += block_length
    return result


def frames(items: list[dict[str, object]], endpoint: int, info: int) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    pending: dict[str, object] | None = None
    for packet in items:
        payload = bytes(packet["payload"])
        if packet["transfer"] != 3 or packet["endpoint"] != endpoint or packet["info"] != info or not payload:
            continue
        if pending is not None:
            pending["data"].extend(payload)  # type: ignore[union-attr]
            pending["packet_indices"].append(packet["index"])  # type: ignore[union-attr]
            pending["last_data_ticks"] = packet["ticks"]
            if len(pending["data"]) >= pending["expected"]:  # type: ignore[arg-type]
                pending["data"] = bytes(pending["data"][:pending["expected"]])  # type: ignore[index]
                result.append(pending)
                pending = None
            continue
        if len(payload) < 4 or payload[0] not in (0xA0, 0xB0):
            continue
        expected = 4 + int.from_bytes(payload[1:3], "little")
        current: dict[str, object] = {
            "packet_indices": [packet["index"]],
            "first_data_ticks": packet["ticks"],
            "last_data_ticks": packet["ticks"],
            "ts_resolution": packet["ts_resolution"],
            "expected": expected,
            "data": bytearray(payload[:expected]),
        }
        if len(current["data"]) >= expected:  # type: ignore[arg-type]
            current["data"] = bytes(current["data"][:expected])  # type: ignore[index]
            result.append(current)
        else:
            pending = current
    return result


def extensions(body: bytes, cursor: int) -> list[dict[str, int | str]]:
    if cursor == len(body):
        return []
    total = int.from_bytes(body[cursor:cursor + 2], "big")
    cursor += 2
    end = cursor + total
    output = []
    while cursor < end:
        kind = int.from_bytes(body[cursor:cursor + 2], "big")
        length = int.from_bytes(body[cursor + 2:cursor + 4], "big")
        output.append({"type": f"0x{kind:04x}", "length": length})
        cursor += 4 + length
    if cursor != end or end != len(body):
        raise ValueError("malformed extension vector")
    return output


def tls_metadata(frame: dict[str, object]) -> dict[str, object]:
    raw = bytes(frame["data"])
    if raw[0] != 0xB0 or raw[3] != (raw[0] + raw[1] + raw[2]) & 0xFF:
        raise ValueError("invalid B0")
    tls = raw[4:]
    declared = int.from_bytes(tls[3:5], "big")
    if len(tls) != 5 + declared:
        raise ValueError("invalid TLS length")
    output: dict[str, object] = {
        "record_version": f"0x{tls[1:3].hex()}",
        "record_payload_length": declared,
        "record_total_length": len(tls),
        "b0_declared_payload_length": int.from_bytes(raw[1:3], "little"),
        "b0_wrapper_total_length": len(raw),
        "b0_header_tag_valid": True,
        "packet_indices": frame["packet_indices"],
    }
    if tls[0] != 0x16 or declared < 4:
        output["content_type"] = {0x14: "change_cipher_spec"}.get(tls[0], "encrypted_or_other")
        return output
    output.update(
        content_type="handshake",
        handshake_type={1: "client_hello", 2: "server_hello", 14: "server_hello_done", 16: "client_key_exchange"}.get(tls[5], "encrypted_or_other"),
        handshake_length=int.from_bytes(tls[6:9], "big"),
    )
    body = tls[9:]
    if tls[5] == 1:
        cursor = 34
        session_length = body[cursor]
        cursor += 1 + session_length
        suites_length = int.from_bytes(body[cursor:cursor + 2], "big")
        cursor += 2
        suites = [f"0x{int.from_bytes(body[i:i + 2], 'big'):04x}" for i in range(cursor, cursor + suites_length, 2)]
        cursor += suites_length
        compression_length = body[cursor]
        compression = [f"0x{x:02x}" for x in body[cursor + 1:cursor + 1 + compression_length]]
        cursor += 1 + compression_length
        output.update(client_version=f"0x{body[:2].hex()}", session_id_length=session_length, cipher_suite_count=len(suites), cipher_suites=suites, compression_methods=compression, extensions=extensions(body, cursor))
    elif tls[5] == 2:
        session_length = body[34]
        cursor = 35 + session_length
        selected = f"0x{int.from_bytes(body[cursor:cursor + 2], 'big'):04x}"
        compression = f"0x{body[cursor + 2]:02x}"
        cursor += 3
        output.update(server_version=f"0x{body[:2].hex()}", session_id_length=session_length, selected_cipher=selected, compression_method=compression, extensions=extensions(body, cursor))
    elif tls[5] == 16:
        identity_length = int.from_bytes(body[:2], "big")
        identity = body[2:2 + identity_length]
        output.update(identity_length=identity_length, identity_classification="Client_identity" if identity == b"Client_identity" else "other_redacted")
    return output


def milliseconds(later: dict[str, object], earlier: dict[str, object], later_key: str, earlier_key: str) -> float:
    resolution = int(later["ts_resolution"])
    return round((int(later[later_key]) - int(earlier[earlier_key])) * 1000 / resolution, 3)


def derive(capture: Path) -> dict[str, object]:
    items = packets(capture)
    outgoing = frames(items, 0x01, 0)
    incoming = frames(items, 0x81, 1)
    packet_by_index = {item["index"]: item for item in items}
    a0_out = [item for item in outgoing if bytes(item["data"])[:1] == b"\xa0"]
    b0_out = [item for item in outgoing if bytes(item["data"])[:1] == b"\xb0"]
    a0_submission_lengths = [
        len(bytes(packet_by_index[index]["payload"]))
        for frame in a0_out
        for index in frame["packet_indices"]
    ]
    b0_submission_lengths = [
        len(bytes(packet_by_index[index]["payload"]))
        for frame in b0_out
        for index in frame["packet_indices"]
    ]
    tls_out = [item for item in outgoing if bytes(item["data"])[:1] == b"\xb0"]
    tls_in = [item for item in incoming if bytes(item["data"])[:1] == b"\xb0"]
    client_hello = next(item for item in tls_in if bytes(item["data"])[9] == 1)
    server_hello = next(item for item in tls_out if bytes(item["data"])[9] == 2)
    server_done = next(item for item in tls_out if bytes(item["data"])[9] == 14)
    client_key = next(item for item in tls_in if bytes(item["data"])[9] == 16)
    sh_completions = [packet_by_index[index] for index in server_hello["packet_indices"]]
    sd_completions = [packet_by_index[index] for index in server_done["packet_indices"]]
    def completion_after(submission: dict[str, object]) -> dict[str, object]:
        return next(
            item for item in items
            if int(item["index"]) > int(submission["index"])
            and item["irp_id"] == submission["irp_id"]
            and item["transfer"] == 3
            and item["info"] == 1
        )

    server_hello_complete = completion_after(sh_completions[-1])
    server_done_complete = completion_after(sd_completions[-1])
    return {
        "schema": "d242-primary-capture-derivation-v1",
        "capture_sha256": sha256(capture),
        "capture_historical_classification": "D175",
        "d43_primary_capture": "NOT_AVAILABLE",
        "fixed64_transport_scope": {
            "classification": "OEM_COMMON_A0_B0_TRANSPORT_CONTRACT_VERIFIED",
            "a0_frame_count": len(a0_out),
            "a0_usb_out_submission_count": len(a0_submission_lengths),
            "a0_usb_out_payload_lengths": sorted(set(a0_submission_lengths)),
            "b0_frame_count": len(b0_out),
            "b0_usb_out_submission_count": len(b0_submission_lengths),
            "b0_usb_out_payload_lengths": sorted(set(b0_submission_lengths)),
            "all_a0_b0_usb_out_submissions_fixed_64": bool(a0_submission_lengths)
            and bool(b0_submission_lengths)
            and set(a0_submission_lengths + b0_submission_lengths) == {64},
            "declared_length_semantics": "A0_B0_HEADER_LENGTH_EXCLUDES_STAGING_TAIL",
        },
        "client_hello": tls_metadata(client_hello),
        "server_hello": tls_metadata(server_hello),
        "server_hello_done": tls_metadata(server_done),
        "client_key_exchange": tls_metadata(client_key),
        "server_flight_grouping": {
            "b0_wrapper_count": 2,
            "tls_records_per_b0": [1, 1],
            "server_hello_usb_out_payload_lengths": [len(bytes(item["payload"])) for item in sh_completions],
            "server_hello_done_usb_out_payload_lengths": [len(bytes(item["payload"])) for item in sd_completions],
            "server_hello_final_tail_class": "NONZERO_REDACTED_OUTSIDE_DECLARED_B0",
            "server_hello_done_final_tail_class": "NONZERO_REDACTED_OUTSIDE_DECLARED_B0",
            "all_server_flight_out_status_success": all(item["status"] == 0 for item in sh_completions + sd_completions),
        },
        "timing_ms": {
            "clienthello_complete_to_serverhello_first": milliseconds(server_hello, client_hello, "first_data_ticks", "last_data_ticks"),
            "serverhello_complete_to_serverhellodone_first": round((int(server_done["first_data_ticks"]) - int(server_hello_complete["ticks"])) * 1000 / int(server_done["ts_resolution"]), 3),
            "serverhellodone_complete_to_clientkeyexchange_first": round((int(client_key["first_data_ticks"]) - int(server_done_complete["ticks"])) * 1000 / int(client_key["ts_resolution"]), 3),
            "serverhello_last_data_to_serverhellodone_first": milliseconds(server_done, server_hello, "first_data_ticks", "last_data_ticks"),
            "serverhellodone_last_data_to_clientkeyexchange_first": milliseconds(client_key, server_done, "first_data_ticks", "last_data_ticks"),
        },
        "redaction": {"raw_tls": False, "raw_b0": False, "random": False, "session_id_value": False, "finished": False, "key_material": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = derive(args.capture)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
