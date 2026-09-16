#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared offline pcapng/USBPcap and Goodix A0 helpers."""
from __future__ import annotations

import os
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator

SHB = 0x0A0D0D0A
IDB = 1
EPB = 6
USBPCAP_LINKTYPE = 249
USBPCAP_MIN_HEADER = 27
BULK = 3
HOST_TO_DEVICE = 0
DEVICE_TO_HOST = 1
EP_OUT = 0x01
EP_IN = 0x81
A0 = 0xA0
B0 = 0xB0


class ExtractError(RuntimeError):
    pass


@dataclass(frozen=True)
class UsbPayload:
    packet_index: int
    bus: int
    device: int
    endpoint: int
    info: int
    payload: bytes


@dataclass(frozen=True)
class GoodixFrame:
    first_packet: int
    last_packet: int
    bus: int
    device: int
    endpoint: int
    raw: bytes


def _u32(data: bytes, offset: int, endian: str) -> int:
    return struct.unpack_from(endian + "I", data, offset)[0]


def iter_pcapng(path: Path) -> Iterator[tuple[int, int, bytes]]:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ExtractError(f"cannot read capture: {error}") from error
    if len(data) < 12:
        raise ExtractError("capture is too short to be pcapng")

    offset = 0
    endian = "<"
    interfaces: list[int] = []
    packet_index = 0
    saw_shb = False
    while offset + 12 <= len(data):
        if data[offset:offset + 4] == struct.pack("<I", SHB):
            bom = data[offset + 8:offset + 12]
            if bom == b"\x4d\x3c\x2b\x1a":
                endian = "<"
            elif bom == b"\x1a\x2b\x3c\x4d":
                endian = ">"
            else:
                raise ExtractError(
                    f"invalid pcapng byte-order magic at {offset:#x}"
                )
            block_type = SHB
            saw_shb = True
            interfaces = []
        else:
            if not saw_shb:
                raise ExtractError(
                    "pcapng does not start with a Section Header Block"
                )
            block_type = _u32(data, offset, endian)

        block_length = _u32(data, offset + 4, endian)
        if (block_length < 12 or block_length % 4 or
                offset + block_length > len(data)):
            raise ExtractError(f"invalid/truncated pcapng block at {offset:#x}")
        if _u32(data, offset + block_length - 4, endian) != block_length:
            raise ExtractError(
                f"pcapng trailing length mismatch at {offset:#x}"
            )
        body = data[offset + 8:offset + block_length - 4]
        if block_type == IDB:
            if len(body) < 8:
                raise ExtractError(f"short IDB at {offset:#x}")
            interfaces.append(struct.unpack_from(endian + "H", body, 0)[0])
        elif block_type == EPB:
            if len(body) < 20:
                raise ExtractError(f"short EPB at {offset:#x}")
            interface_id, _, _, captured, original = struct.unpack_from(
                endian + "IIIII", body, 0
            )
            if interface_id >= len(interfaces):
                raise ExtractError(f"unknown interface at packet {packet_index}")
            if captured > original or 20 + captured > len(body):
                raise ExtractError(
                    f"invalid captured length at packet {packet_index}"
                )
            yield packet_index, interfaces[interface_id], body[20:20 + captured]
            packet_index += 1
        offset += block_length

    if not saw_shb:
        raise ExtractError("no pcapng Section Header Block found")
    if offset != len(data):
        raise ExtractError(f"unexpected trailing bytes after {offset:#x}")


def _decode_usbpcap(packet_index: int, linktype: int,
                    raw: bytes) -> UsbPayload | None:
    if linktype != USBPCAP_LINKTYPE or len(raw) < USBPCAP_MIN_HEADER:
        return None
    header_length = struct.unpack_from("<H", raw, 0)[0]
    if header_length < USBPCAP_MIN_HEADER or header_length > len(raw):
        return None
    info = raw[16]
    bus = struct.unpack_from("<H", raw, 17)[0]
    device = struct.unpack_from("<H", raw, 19)[0]
    endpoint = raw[21]
    transfer = raw[22]
    data_length = struct.unpack_from("<I", raw, 23)[0]
    if header_length + data_length > len(raw) or transfer != BULK:
        return None
    return UsbPayload(
        packet_index, bus, device, endpoint, info,
        raw[header_length:header_length + data_length],
    )


def iter_bulk_payloads(path: Path, *, device_to_host: bool) -> Iterator[UsbPayload]:
    wanted_endpoint = EP_IN if device_to_host else EP_OUT
    wanted_info = DEVICE_TO_HOST if device_to_host else HOST_TO_DEVICE
    decoded_usbpcap = False
    for packet_index, linktype, raw in iter_pcapng(path):
        packet = _decode_usbpcap(packet_index, linktype, raw)
        if packet is None:
            continue
        decoded_usbpcap = True
        if (packet.endpoint == wanted_endpoint and packet.info == wanted_info and
                packet.payload):
            yield packet
    if not decoded_usbpcap:
        raise ExtractError("no decodable USBPcap bulk packets found")


@dataclass
class _PendingFrame:
    first_packet: int
    last_packet: int
    bus: int
    device: int
    endpoint: int
    expected: int | None
    data: bytearray


def reassemble_frames(payloads: Iterable[UsbPayload]) -> Iterator[GoodixFrame]:
    pending: dict[tuple[int, int, int, int], _PendingFrame] = {}
    for packet in payloads:
        key = (packet.bus, packet.device, packet.endpoint, packet.info)
        current = pending.get(key)
        cursor = 0
        while cursor < len(packet.payload):
            if current is None:
                if packet.payload[cursor] not in (A0, B0):
                    break
                current = _PendingFrame(
                    packet.packet_index, packet.packet_index,
                    packet.bus, packet.device, packet.endpoint,
                    None, bytearray(),
                )
                pending[key] = current

            current.last_packet = packet.packet_index
            if current.expected is None:
                needed = 4 - len(current.data)
                take = min(needed, len(packet.payload) - cursor)
                current.data.extend(packet.payload[cursor:cursor + take])
                cursor += take
                if len(current.data) < 4:
                    continue
                frame_length = 4 + int.from_bytes(current.data[1:3], "little")
                minimum = 8 if current.data[0] == A0 else 4
                if frame_length < minimum or frame_length > 65539:
                    del pending[key]
                    current = None
                    break
                current.expected = frame_length

            needed = current.expected - len(current.data)
            take = min(needed, len(packet.payload) - cursor)
            current.data.extend(packet.payload[cursor:cursor + take])
            cursor += take
            if len(current.data) == current.expected:
                yield GoodixFrame(
                    current.first_packet, current.last_packet,
                    current.bus, current.device, current.endpoint,
                    bytes(current.data),
                )
                del pending[key]
                current = None


def parse_a0(raw: bytes) -> tuple[int, int, bytes]:
    if len(raw) < 8 or raw[0] != A0:
        raise ExtractError("not A0")
    payload_length = int.from_bytes(raw[1:3], "little")
    if payload_length + 4 != len(raw):
        raise ExtractError("A0 outer length mismatch")
    tag = (raw[0] + (payload_length & 0xff) +
           ((payload_length >> 8) & 0xff)) & 0xff
    if raw[3] != tag:
        raise ExtractError("A0 outer tag mismatch")
    wire_control = raw[4]
    logical_control = wire_control & 0xfe
    inner_length = int.from_bytes(raw[5:7], "little")
    if inner_length == 0 or inner_length + 3 != payload_length:
        raise ExtractError("A0 inner length mismatch")
    body = raw[7:7 + inner_length - 1]
    if len(body) != inner_length - 1:
        raise ExtractError("A0 body truncated")
    checksum = (logical_control + len(body) + 1 + sum(body) + raw[-1]) & 0xff
    if checksum != 0xaa:
        raise ExtractError("A0 inner checksum mismatch")
    return wire_control, logical_control, body


def atomic_write_new_0600(
        path: Path, data: bytes,
        *, write_func: Callable[[int, bytes | memoryview], int] = os.write) -> None:
    """Publish complete bytes under a new name, never replacing an old file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ExtractError(f"refusing to overwrite existing output: {path}")
    fd, temporary = tempfile.mkstemp(
        prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    linked = False
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        offset = 0
        while offset < len(view):
            written = write_func(fd, view[offset:])
            if written <= 0:
                raise OSError("short write made no progress")
            offset += written
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.link(temporary, path, follow_symlinks=False)
        linked = True
        os.unlink(temporary)
        temporary = ""
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_CLOEXEC", 0)
        directory_fd = os.open(path.parent, directory_flags)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except (OSError, ValueError) as error:
        if linked:
            # A linked output is complete and fsynced, never partial.  Leave it
            # in place if only the parent-directory fsync failed.
            raise ExtractError(f"output published but directory sync failed: {error}") from error
        raise ExtractError(f"cannot write output atomically: {error}") from error
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def synthetic_a0_frame(control: int, body: bytes, *, wire_control: int | None = None,
                       corrupt_checksum: bool = False) -> bytes:
    wire = control if wire_control is None else wire_control
    logical = wire & 0xfe
    inner_length = len(body) + 1
    payload_length = len(body) + 4
    tag = (A0 + (payload_length & 0xff) +
           ((payload_length >> 8) & 0xff)) & 0xff
    checksum = (0xaa - (logical + len(body) + 1 + sum(body))) & 0xff
    if corrupt_checksum:
        checksum ^= 1
    return bytes((A0, payload_length & 0xff, payload_length >> 8, tag,
                  wire, inner_length & 0xff, inner_length >> 8)) + body + bytes((checksum,))


def _synthetic_usbpcap(payload: bytes, packet_id: int, *, device_to_host: bool,
                       bus: int = 1, device: int = 2) -> bytes:
    header = bytearray(USBPCAP_MIN_HEADER)
    struct.pack_into("<H", header, 0, USBPCAP_MIN_HEADER)
    struct.pack_into("<Q", header, 2, packet_id)
    struct.pack_into("<I", header, 10, 0)
    struct.pack_into("<H", header, 14, 0)
    header[16] = DEVICE_TO_HOST if device_to_host else HOST_TO_DEVICE
    struct.pack_into("<H", header, 17, bus)
    struct.pack_into("<H", header, 19, device)
    header[21] = EP_IN if device_to_host else EP_OUT
    header[22] = BULK
    struct.pack_into("<I", header, 23, len(payload))
    return bytes(header) + payload


def _synthetic_block(block_type: int, body: bytes) -> bytes:
    body += b"\0" * ((-len(body)) % 4)
    total = 12 + len(body)
    return struct.pack("<II", block_type, total) + body + struct.pack("<I", total)


def synthetic_pcapng(chunks: Iterable[tuple[bytes, bool]]) -> bytes:
    shb = struct.pack("<I", 0x1A2B3C4D) + struct.pack("<HHq", 1, 0, -1)
    idb = struct.pack("<HHI", USBPCAP_LINKTYPE, 0, 65535)
    output = bytearray(_synthetic_block(SHB, shb) + _synthetic_block(IDB, idb))
    for packet_id, (chunk, device_to_host) in enumerate(chunks, 1):
        packet = _synthetic_usbpcap(
            chunk, packet_id, device_to_host=device_to_host
        )
        body = struct.pack(
            "<IIIII", 0, 0, packet_id, len(packet), len(packet)
        ) + packet
        output += _synthetic_block(EPB, body)
    return bytes(output)
