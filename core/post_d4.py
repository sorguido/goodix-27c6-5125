# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 liushicong (Rockytkg)
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Bounded post-D4 protocol subset, adapted from Rocky at 227eba2.

This module deliberately has no USB implementation, secret handling, retry,
device lifecycle, firmware, provisioning, or persistence API.
"""
from dataclasses import dataclass
from typing import Iterable, Protocol

PLAIN, TLS = 0xA0, 0xB0
ALLOWED_COMMANDS = frozenset({0xAF, 0x36, 0x32, 0x34, 0x20, 0xD2})

class ProtocolError(ValueError): pass
class TruncatedFrame(ProtocolError): pass
class LengthMismatch(ProtocolError): pass
class ChecksumMismatch(ProtocolError): pass
class UnexpectedControl(ProtocolError): pass
class UnexpectedAck(ProtocolError): pass
class ImageCrcError(ProtocolError): pass
class StreamEnded(ProtocolError): pass

def _checksum(control: int, data: bytes) -> int:
    n = len(data) + 1
    return (0xAA - ((control & 0xFE) + n + (n >> 8) + sum(data))) & 0xFF

def build_command(control: int, data: bytes) -> bytes:
    if control not in ALLOWED_COMMANDS:
        raise UnexpectedControl(f"command_not_allowlisted:0x{control:02x}")
    n = len(data) + 1
    payload = bytes((control, n & 0xff, n >> 8)) + data + bytes((_checksum(control, data),))
    return bytes((PLAIN, len(payload) & 0xff, len(payload) >> 8,
                  (PLAIN + len(payload)) & 0xff)) + payload

def parse_outer(frame: bytes) -> tuple[int, bytes]:
    if len(frame) < 4: raise TruncatedFrame("outer_header_truncated")
    kind, lo, hi, check = frame[:4]
    if kind not in (PLAIN, TLS): raise UnexpectedControl(f"outer_control:0x{kind:02x}")
    if check != ((kind + lo + hi) & 0xff): raise ChecksumMismatch("outer_checksum")
    declared = lo | hi << 8
    if len(frame) != declared + 4: raise LengthMismatch(f"outer_length:{declared}:{len(frame)-4}")
    return kind, frame[4:]

def parse_payload(payload: bytes) -> tuple[int, bytes]:
    if len(payload) < 4: raise TruncatedFrame("payload_header_truncated")
    control, lo, hi = payload[:3]; declared = lo | hi << 8
    if declared < 1 or len(payload) != declared + 3:
        raise LengthMismatch(f"payload_length:{declared}:{len(payload)-3}")
    data, check = payload[3:-1], payload[-1]
    if check != 0x88 and check != _checksum(control, data):
        raise ChecksumMismatch("payload_checksum")
    return control, data

def build_af(ts16: int) -> bytes:
    if not 0 <= ts16 <= 0xffff: raise ValueError("ts16_range")
    return build_command(0xAF, bytes((0x55, ts16 & 0xff, ts16 >> 8, 0, 0)))

@dataclass(frozen=True)
class McuState:
    raw: bytes
    pov_valid: bool
    tls_connected: bool
    locked: bool
    unknown_flag_bits: int

def parse_af_response(frame: bytes) -> McuState:
    kind, payload = parse_outer(frame)
    if kind != PLAIN: raise UnexpectedControl("af_not_plaintext")
    control, data = parse_payload(payload)
    if control == 0xB0: raise UnexpectedAck("af_ack_not_in_local_contract")
    if control != 0xAE: raise UnexpectedControl(f"af_response:0x{control:02x}")
    if len(data) != 16: raise LengthMismatch(f"af_state_length:{len(data)}")
    flags = data[1]
    return McuState(data, bool(flags & 1), bool(flags & 2), bool(flags & 8), flags & ~0x0b)

def build_fdt_manual(table12: bytes) -> bytes:
    if len(table12) != 12: raise LengthMismatch("fdt_table_length")
    return build_command(0x36, b"\x09\x01" + table12)
def build_fdt_down(table12: bytes, ts16: int) -> bytes:
    if len(table12) != 12: raise LengthMismatch("fdt_table_length")
    return build_command(0x32, b"\x08\x01" + table12 + ts16.to_bytes(2, "little"))
def build_fdt_up(table12: bytes) -> bytes:
    if len(table12) != 12: raise LengthMismatch("fdt_table_length")
    return build_command(0x34, b"\x0a\x01" + table12)
def build_set_image() -> bytes: return build_command(0x20, b"\x01\x00")
def build_cached_image() -> bytes: return build_command(0xD2, b"\x00\x00")

@dataclass(frozen=True)
class FdtEvent:
    irq: int
    touch_flags: int | None
    raw_base: bytes | None

def parse_fdt_event(payload: bytes) -> FdtEvent:
    control, data = parse_payload(payload)
    if control >> 4 != 3: raise UnexpectedControl(f"not_fdt:0x{control:02x}")
    if len(data) < 2: raise TruncatedFrame("fdt_irq_truncated")
    irq = int.from_bytes(data[:2], "little")
    if irq not in {2, 0x100, 0x200, 0x80, 0x82, 0x800}:
        raise UnexpectedControl(f"unknown_fdt_irq:0x{irq:x}")
    return FdtEvent(irq, int.from_bytes(data[2:4], "little") if len(data)>=4 else None,
                    data[4:16] if len(data)>=16 else None)

class MixedDemux:
    """Demux validated A0 frames and decrypted B0 application byte streams."""
    def __init__(self, max_payload: int = 8192): self._tls = bytearray(); self.max_payload=max_payload
    def feed_outer(self, frame: bytes, decrypted_tls: bytes | None = None) -> list[bytes]:
        kind, body = parse_outer(frame)
        if kind == PLAIN: return [body]
        if decrypted_tls is None: raise ProtocolError("tls_decryptor_required")
        self._tls += decrypted_tls
        if len(self._tls) > self.max_payload: raise LengthMismatch("tls_accumulator_limit")
        out=[]
        while len(self._tls)>=3:
            n=int.from_bytes(self._tls[1:3],"little")+3
            if n > self.max_payload or n < 4: raise LengthMismatch("tls_payload_length")
            if len(self._tls)<n: break
            out.append(bytes(self._tls[:n])); del self._tls[:n]
        return out
    def eof(self) -> None:
        if self._tls: raise StreamEnded("tls_payload_eof")

def crc32_mpeg2(data: bytes) -> int:
    crc=0xffffffff
    for b in data:
        crc ^= b << 24
        for _ in range(8): crc=((crc<<1)^0x04c11db7)&0xffffffff if crc&0x80000000 else (crc<<1)&0xffffffff
    return crc

def decode_image_record(record: bytes) -> tuple[int, ...]:
    if len(record)!=7684: raise LengthMismatch(f"image_record_length:{len(record)}")
    packed=record[:7680]; expected=int.from_bytes(record[7680:],"big")
    if crc32_mpeg2(packed)!=expected: raise ImageCrcError("image_crc")
    linear=[]
    for i in range(0,len(packed),3):
        a,b,c=packed[i:i+3]; linear.extend((a | (b&15)<<8, (b>>4) | c<<4))
    # Existing local, independently validated column-major -> 80x64 transpose.
    return tuple(linear[x*64+y] for y in range(64) for x in range(80))

class Transport(Protocol):
    def exchange(self, request: bytes) -> Iterable[bytes]: ...

class FirstImageMachine:
    def __init__(self, transport: Transport): self.transport=transport; self.phase="POST_D4"
    def query_state(self, ts16: int) -> McuState:
        frames=list(self.transport.exchange(build_af(ts16)))
        if len(frames)!=1: raise UnexpectedAck(f"af_frame_count:{len(frames)}")
        state=parse_af_response(frames[0]); self.phase="AF_OK"; return state
    def arm_no_touch_boundary(self, table12: bytes, ts16: int) -> None:
        if self.phase!="AF_OK": raise ProtocolError("phase_order")
        # Offline construction only; live arming/cleanup semantics remain unclosed.
        build_fdt_manual(table12); build_fdt_down(table12,ts16); self.phase="FDT_BUILT"
