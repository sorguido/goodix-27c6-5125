# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 liushicong (Rockytkg)
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Bounded, offline-only post-D4 protocol core.

Command/framing and capture sequencing are adapted from Rockytkg commit
227eba219fa9e3fbac5bd59aca79f624f67cd11b after comparison with local 12509
evidence.  The image codec is reused directly from the independently validated
local implementation; this module provides no USB, TLS, secret, retry,
reconnect, lifecycle, firmware, provisioning, or persistence implementation.
"""

from dataclasses import dataclass
from typing import Iterable, Protocol

from src.goodix5125_cleanroom import decode_record as _decode_local_record


PLAIN, TLS = 0xA0, 0xB0
ALLOWED_COMMANDS = frozenset({0xAF, 0x36, 0x32, 0x34, 0x20, 0xD2})
FIRST_IMAGE_RECEIVED = "FIRST_IMAGE_RECEIVED"
STOP_AFTER_AF = "STOP_AFTER_AF"
ACK_FORBIDDEN = "FORBIDDEN"
ACK_OPTIONAL = "OPTIONAL_IF_PRESENT"
ACK_POLICIES = {
    0xAF: ACK_FORBIDDEN,
    0x32: ACK_OPTIONAL,
    0x20: ACK_OPTIONAL,
    0xD2: ACK_OPTIONAL,
    0x36: ACK_OPTIONAL,
    0x34: ACK_OPTIONAL,
}


class ProtocolError(ValueError):
    pass


class TruncatedFrame(ProtocolError):
    pass


class LengthMismatch(ProtocolError):
    pass


class ChecksumMismatch(ProtocolError):
    pass


class UnexpectedControl(ProtocolError):
    pass


class UnexpectedAck(ProtocolError):
    pass


class UnexpectedEvent(ProtocolError):
    pass


class InvalidTransition(ProtocolError):
    pass


class ImageCrcError(ProtocolError):
    pass


class StreamEnded(ProtocolError):
    pass


def _checksum(control: int, data: bytes) -> int:
    n = len(data) + 1
    return (0xAA - ((control & 0xFE) + n + (n >> 8) + sum(data))) & 0xFF


def build_command(control: int, data: bytes) -> bytes:
    if control not in ALLOWED_COMMANDS:
        raise UnexpectedControl(f"command_not_allowlisted:0x{control:02x}")
    n = len(data) + 1
    payload = bytes((control, n & 0xFF, n >> 8)) + data
    payload += bytes((_checksum(control, data),))
    return bytes(
        (PLAIN, len(payload) & 0xFF, len(payload) >> 8,
         (PLAIN + len(payload)) & 0xFF)
    ) + payload


def parse_outer(frame: bytes) -> tuple[int, bytes]:
    if len(frame) < 4:
        raise TruncatedFrame("outer_header_truncated")
    kind, lo, hi, check = frame[:4]
    if kind not in (PLAIN, TLS):
        raise UnexpectedControl(f"outer_control:0x{kind:02x}")
    if check != ((kind + lo + hi) & 0xFF):
        raise ChecksumMismatch("outer_checksum")
    declared = lo | hi << 8
    if len(frame) != declared + 4:
        raise LengthMismatch(f"outer_length:{declared}:{len(frame) - 4}")
    return kind, frame[4:]


def parse_payload(payload: bytes) -> tuple[int, bytes]:
    """Parse one command/data payload with mandatory additive checksum.

    D249 has no no-check payload class.  A trailing 0x88 is accepted only when
    it is also the correctly computed checksum; it is never a global bypass.
    """
    if len(payload) < 4:
        raise TruncatedFrame("payload_header_truncated")
    control, lo, hi = payload[:3]
    declared = lo | hi << 8
    if declared < 1 or len(payload) != declared + 3:
        raise LengthMismatch(f"payload_length:{declared}:{len(payload) - 3}")
    data, check = payload[3:-1], payload[-1]
    if check != _checksum(control, data):
        raise ChecksumMismatch("payload_checksum")
    return control, data


def build_af(ts16: int) -> bytes:
    if not 0 <= ts16 <= 0xFFFF:
        raise ValueError("ts16_range")
    return build_command(0xAF, bytes((0x55, ts16 & 0xFF, ts16 >> 8, 0, 0)))


@dataclass(frozen=True)
class McuState:
    raw: bytes
    byte0: int
    flags: int
    pov_valid: bool
    tls_connected: bool
    locked: bool
    unknown_flag_bits: int


def parse_af_response(frame: bytes) -> McuState:
    kind, payload = parse_outer(frame)
    if kind != PLAIN:
        raise UnexpectedControl("af_not_plaintext")
    control, data = parse_payload(payload)
    if control == 0xB0:
        raise UnexpectedAck("af_ack_not_in_local_contract")
    if control != 0xAE:
        raise UnexpectedControl(f"af_response:0x{control:02x}")
    if len(data) != 16:
        raise LengthMismatch(f"af_state_length:{len(data)}")
    byte0 = data[0]
    flags = data[1]
    return McuState(
        data,
        byte0,
        flags,
        bool(flags & 1),
        bool(flags & 2),
        bool(flags & 8),
        flags & ~0x0B,
    )


def build_fdt_manual(table12: bytes) -> bytes:
    if len(table12) != 12:
        raise LengthMismatch("fdt_table_length")
    return build_command(0x36, b"\x09\x01" + table12)


def build_fdt_down(table12: bytes, ts16: int) -> bytes:
    if len(table12) != 12:
        raise LengthMismatch("fdt_table_length")
    if not 0 <= ts16 <= 0xFFFF:
        raise ValueError("ts16_range")
    return build_command(0x32, b"\x08\x01" + table12 + ts16.to_bytes(2, "little"))


def build_fdt_up(table12: bytes) -> bytes:
    if len(table12) != 12:
        raise LengthMismatch("fdt_table_length")
    return build_command(0x34, b"\x0a\x01" + table12)


def build_set_image() -> bytes:
    return build_command(0x20, b"\x01\x00")


def build_cached_image() -> bytes:
    return build_command(0xD2, b"\x00\x00")


@dataclass(frozen=True)
class FdtEvent:
    irq: int
    touch_flags: int | None
    raw_base: bytes | None


def parse_fdt_event(payload: bytes) -> FdtEvent:
    control, data = parse_payload(payload)
    if control >> 4 != 3:
        raise UnexpectedControl(f"not_fdt:0x{control:02x}")
    if len(data) < 2:
        raise TruncatedFrame("fdt_irq_truncated")
    irq = int.from_bytes(data[:2], "little")
    if irq not in {2, 0x100, 0x200, 0x80, 0x82, 0x800}:
        raise UnexpectedEvent(f"unknown_fdt_irq:0x{irq:x}")
    return FdtEvent(
        irq,
        int.from_bytes(data[2:4], "little") if len(data) >= 4 else None,
        data[4:16] if len(data) >= 16 else None,
    )


def parse_ack(frame: bytes, expected_echo: int) -> None:
    kind, payload = parse_outer(frame)
    if kind != PLAIN:
        raise UnexpectedAck("ack_not_plaintext")
    control, data = parse_payload(payload)
    if control != 0xB0 or len(data) != 2:
        raise UnexpectedAck("ack_shape")
    if data[0] != expected_echo or data[1] not in (0x01, 0x07):
        raise UnexpectedAck(
            f"ack_value:echo=0x{data[0]:02x}:status=0x{data[1]:02x}"
        )


class MixedDemux:
    """Demux validated A0 frames and already-decrypted B0 application bytes."""

    def __init__(self, max_payload: int = 8192):
        self._tls = bytearray()
        self.max_payload = max_payload

    def feed_outer(self, frame: bytes, decrypted_tls: bytes | None = None) -> list[bytes]:
        kind, body = parse_outer(frame)
        if kind == PLAIN:
            return [body]
        if decrypted_tls is None:
            raise ProtocolError("tls_decryptor_required")
        self._tls += decrypted_tls
        if len(self._tls) > self.max_payload:
            raise LengthMismatch("tls_accumulator_limit")
        out = []
        while len(self._tls) >= 3:
            total = int.from_bytes(self._tls[1:3], "little") + 3
            if total > self.max_payload or total < 4:
                raise LengthMismatch("tls_payload_length")
            if len(self._tls) < total:
                break
            candidate = bytes(self._tls[:total])
            parse_payload(candidate)
            out.append(candidate)
            del self._tls[:total]
        return out

    def eof(self) -> None:
        if self._tls:
            raise StreamEnded("tls_payload_eof")


def decode_image_record(record: bytes) -> tuple[int, ...]:
    """Reuse the canonical local 7684-byte codec and normalize typed errors."""
    try:
        return _decode_local_record(record)
    except ValueError as error:
        message = str(error)
        if "CRC mismatch" in message:
            raise ImageCrcError("image_crc") from error
        raise LengthMismatch(f"image_record:{message}") from error


def parse_image_payload(payload: bytes) -> tuple[int, ...]:
    """Validate one type-12 image payload and return the canonical 80x64 raster."""
    control, data = parse_payload(payload)
    if control >> 4 != 2:
        raise UnexpectedControl(f"not_image:0x{control:02x}")
    if len(data) != 5 + 7684:
        raise LengthMismatch(f"image_payload_data_length:{len(data)}")
    if data[0] == 0xAA:
        raise UnexpectedEvent("pov_notification_not_image")
    return decode_image_record(data[5:])


class Transport(Protocol):
    def exchange(self, request: bytes) -> Iterable[bytes]:
        ...


class ExactlyOneAfMachine:
    """Terminal AF-only boundary with a pre-submit attempt latch.

    This machine deliberately has no FDT/capture transition.  ``exchange`` is
    invoked at most once and every success terminates at ``STOP_AFTER_AF``.
    """

    def __init__(self, transport: Transport):
        self.transport = transport
        self.phase = "POST_D4"
        self.af_attempt_count = 0
        self.af_send_count = 0
        self.af_response_count = 0
        self.retry_count = 0
        self.persistent_write_family_count = 0
        self.state: McuState | None = None

    def run(self, ts16: int) -> McuState:
        if self.phase != "POST_D4" or self.af_attempt_count:
            raise InvalidTransition(
                f"af_phase:{self.phase}:attempts:{self.af_attempt_count}"
            )
        self.af_attempt_count = 1
        self.phase = "AF_ATTEMPTED"
        try:
            frames = list(self.transport.exchange(build_af(ts16)))
            self.af_send_count = 1
            if len(frames) != 1:
                raise UnexpectedAck(f"af_frame_count:{len(frames)}")
            self.state = parse_af_response(frames[0])
            self.af_response_count = 1
            self.phase = STOP_AFTER_AF
            return self.state
        except Exception:
            self.phase = "STOP_AFTER_AF_FAILURE"
            raise


class FirstImageMachine:
    """Monotonic, single-pass offline AF→FDT/POV→first-image machine."""

    def __init__(self, transport: Transport):
        self.transport = transport
        self.phase = "POST_D4"
        self.path: str | None = None
        self.image: tuple[int, ...] | None = None

    def _require(self, phase: str) -> None:
        if self.phase != phase:
            raise InvalidTransition(f"phase:{self.phase}:expected:{phase}")

    def _send_async(self, request: bytes, echo: int) -> None:
        """Send once; validate zero/one immediate ACK without requiring one.

        Local capture observes ACKs after 0x20/0x32/0x34/0x36, but does not
        establish them as a causal prerequisite for the pushed event/image.
        D2 is not observed locally; Rocky likewise sends these commands
        asynchronously and its receive loop consumes ACKs while waiting.
        """
        if ACK_POLICIES.get(echo) != ACK_OPTIONAL:
            raise UnexpectedAck(f"async_ack_policy:0x{echo:02x}")
        frames = list(self.transport.exchange(request))
        if len(frames) > 1:
            raise UnexpectedAck(f"ack_frame_count:{len(frames)}")
        if frames:
            parse_ack(frames[0], echo)

    def query_state(self, ts16: int) -> McuState:
        self._require("POST_D4")
        frames = list(self.transport.exchange(build_af(ts16)))
        if len(frames) != 1:
            raise UnexpectedAck(f"af_frame_count:{len(frames)}")
        state = parse_af_response(frames[0])
        self.path = "POV" if state.pov_valid else "FRESH_FDT"
        self.phase = "AF_OK"
        return state

    def begin_capture(self, table12: bytes, ts16: int) -> None:
        self._require("AF_OK")
        if self.path == "POV":
            self._send_async(build_cached_image(), 0xD2)
            self.phase = "WAIT_IMAGE"
            return
        if self.path != "FRESH_FDT":
            raise InvalidTransition("capture_path_unset")
        self._send_async(build_fdt_down(table12, ts16), 0x32)
        self.phase = "WAIT_FDT_DOWN"

    def receive_payload(self, payload: bytes) -> tuple[int, ...] | None:
        if self.phase == "WAIT_FDT_DOWN":
            event = parse_fdt_event(payload)
            if event.irq != 2:
                raise UnexpectedEvent(f"fdt_order:0x{event.irq:x}")
            self._send_async(build_set_image(), 0x20)
            self.phase = "WAIT_IMAGE"
            return None
        if self.phase == "WAIT_IMAGE":
            self.image = parse_image_payload(payload)
            self.phase = FIRST_IMAGE_RECEIVED
            return self.image
        raise InvalidTransition(f"payload_in_phase:{self.phase}")

    def eof(self) -> None:
        if self.phase != FIRST_IMAGE_RECEIVED:
            raise StreamEnded(f"machine_eof:{self.phase}")
