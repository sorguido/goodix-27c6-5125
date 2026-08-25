# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 liushicong (Rockytkg)
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Bounded, offline-only post-D4 protocol core.

Command/framing and capture sequencing are adapted from Rockytkg commit
227eba219fa9e3fbac5bd59aca79f624f67cd11b after comparison with local 12509
evidence.  The image codec is reused directly from the independently validated
local implementation; this module provides no USB, TLS, secret, retry,
reconnect, firmware, provisioning, or persistence implementation.  A caller
may attach the offline lifecycle observer introduced in D257.
"""

from dataclasses import dataclass
from typing import Iterable, Protocol

from src.goodix5125_cleanroom import decode_record as _decode_local_record


PLAIN, TLS = 0xA0, 0xB0
ALLOWED_COMMANDS = frozenset({0xAF, 0x20, 0x22, 0x32, 0x34, 0x36, 0x50, 0x82, 0xD2})
FIRST_IMAGE_RECEIVED = "FIRST_IMAGE_RECEIVED"
STOP_AFTER_AF = "STOP_AFTER_AF"
ACK_FORBIDDEN = "FORBIDDEN"
ACK_OPTIONAL = "OPTIONAL_IF_PRESENT"
ACK_POLICIES = {
    0xAF: ACK_FORBIDDEN,
    0x32: ACK_OPTIONAL,
    0x20: ACK_OPTIONAL,
    0x22: ACK_OPTIONAL,
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


def build_nav_baseline() -> bytes:
    """Build the target-observed inter-stage NAV baseline request."""
    return build_command(0x50, b"\x01\x00")


def build_read_fdt_delta() -> bytes:
    """Read two bytes from target-observed sensor register 0x0082."""
    return build_command(0x82, b"\x00\x82\x00\x02\x00")


def build_set_image() -> bytes:
    """Build the target-observed baseline/no-finger image-mode variant."""
    return build_command(0x20, b"\x01\x00")


def parse_nav_baseline_response(frame: bytes) -> bytes:
    """Validate the bounded target 0x50 response envelope.

    The D255 response uses the OEM no-check marker ``0x88`` rather than the
    additive checksum used by ordinary A0 payloads.  This parser is deliberately
    limited to the one observed 0x50 shape; it is not a general checksum bypass.
    The returned 2409 bytes remain dynamic input to a separate host semantic
    gate.
    """
    kind, payload = parse_outer(frame)
    if kind != PLAIN:
        raise UnexpectedControl("nav_response_not_plaintext")
    if len(payload) < 4:
        raise TruncatedFrame("nav_response_header_truncated")
    control, lo, hi = payload[:3]
    declared = lo | hi << 8
    if control != 0x50:
        raise UnexpectedControl(f"nav_response:0x{control:02x}")
    if declared != 2410 or len(payload) != declared + 3:
        raise LengthMismatch(f"nav_response_length:{declared}:{len(payload) - 3}")
    if payload[-1] != 0x88:
        raise ChecksumMismatch("nav_response_no_check_marker")
    data = payload[3:-1]
    if len(data) != 2409 or data[:2] != b"\x50\x01":
        raise LengthMismatch("nav_response_target_shape")
    return data


def parse_fdt_delta_response(frame: bytes) -> bytes:
    """Validate the two-byte response to the inter-stage 0x82 read."""
    kind, payload = parse_outer(frame)
    if kind != PLAIN:
        raise UnexpectedControl("fdt_delta_response_not_plaintext")
    control, data = parse_payload(payload)
    if control != 0x82:
        raise UnexpectedControl(f"fdt_delta_response:0x{control:02x}")
    if len(data) != 2:
        raise LengthMismatch(f"fdt_delta_response_length:{len(data)}")
    return data


def parse_baseline_image_b0_shape(frame: bytes) -> None:
    """Validate only the target-observed encrypted baseline-image B0 shape.

    Semantic image/no-finger validation requires the decrypted application
    payload and is intentionally a separate gate.  Accepting this envelope
    alone must never authorize the next manual FDT stage.
    """
    kind, body = parse_outer(frame)
    if kind != TLS:
        raise UnexpectedControl("baseline_image_response_not_b0")
    if len(frame) != 7726 or len(body) != 7722:
        raise LengthMismatch(f"baseline_image_b0_length:{len(frame)}")


def build_finger_image() -> bytes:
    """Build the target post-IRQ2 image-mode variant (cmd0=2, cmd1=1)."""
    return build_command(0x22, b"\x01\x00")


def build_cached_image() -> bytes:
    return build_command(0xD2, b"\x00\x00")


@dataclass(frozen=True)
class FdtEvent:
    irq: int
    touch_flags: int | None
    raw_base: bytes | None


@dataclass
class ImageDecodeDiagnostic:
    """Sanitized, metadata-only observability for one image decode attempt.

    This record deliberately contains no payload bytes, plaintext hashes,
    image bytes, raster samples, or other biometric material.  It observes the
    image-specific acceptance path.
    """

    decode_stage: str = "plaintext_envelope"
    plaintext_length: int = 0
    declared_payload_length: int | None = None
    control_or_major_class: str | None = None
    is_pov_notification: bool | None = None
    payload_trailer_class: str | None = None
    payload_checksum_match: bool | None = None
    payload_checksum_policy: str = "NOT_REACHED"
    image_record_length: int | None = None
    image_record_crc_match: bool | None = None
    exception_class: str | None = None
    raster_shape_if_success: tuple[int, int] | None = None

    def sanitized_dict(self) -> dict[str, object]:
        return {
            "decode_stage": self.decode_stage,
            "plaintext_length": self.plaintext_length,
            "declared_payload_length": self.declared_payload_length,
            "control_or_major_class": self.control_or_major_class,
            "is_pov_notification": self.is_pov_notification,
            "payload_trailer_class": self.payload_trailer_class,
            "payload_checksum_match": self.payload_checksum_match,
            "payload_checksum_policy": self.payload_checksum_policy,
            "image_record_length": self.image_record_length,
            "image_record_crc_match": self.image_record_crc_match,
            "exception_class": self.exception_class,
            "raster_shape_if_success": self.raster_shape_if_success,
        }


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


def parse_image_payload(
    payload: bytes, *, diagnostic: ImageDecodeDiagnostic | None = None
) -> tuple[int, ...]:
    """Validate one type-12 image payload and return the canonical 80x64 raster.

    When supplied, ``diagnostic`` is populated only with bounded metadata.  The
    generic :func:`parse_payload` remains strict.  This image-only parser first
    validates framing, image classification, record length and the POV marker;
    only then does a trailing ``0x88`` select the OEM no-check policy for the
    additive payload checksum.  The image-record CRC remains mandatory.
    """

    observation = diagnostic or ImageDecodeDiagnostic()
    observation.plaintext_length = len(payload)
    try:
        if len(payload) < 4:
            raise TruncatedFrame("payload_header_truncated")

        control, lo, hi = payload[:3]
        observation.control_or_major_class = f"MAJOR_0X{control >> 4:X}"
        declared = lo | hi << 8
        observation.declared_payload_length = declared
        if declared < 1 or len(payload) != declared + 3:
            observation.decode_stage = "declared_length"
            raise LengthMismatch(f"payload_length:{declared}:{len(payload) - 3}")
        data, trailer = payload[3:-1], payload[-1]

        observation.decode_stage = "control_major"
        if control >> 4 != 2:
            raise UnexpectedControl(f"not_image:0x{control:02x}")

        observation.decode_stage = "image_record_length"
        observation.image_record_length = max(0, len(data) - 5)
        if len(data) != 5 + 7684:
            raise LengthMismatch(f"image_payload_data_length:{len(data)}")

        observation.decode_stage = "pov_notification"
        observation.is_pov_notification = data[0] == 0xAA
        if observation.is_pov_notification:
            raise UnexpectedEvent("pov_notification_not_image")

        observation.decode_stage = "payload_checksum"
        expected_checksum = _checksum(control, data)
        observation.payload_checksum_match = trailer == expected_checksum
        observation.payload_trailer_class = (
            "0X88"
            if trailer == 0x88
            else (
                "COMPUTED_ADDITIVE_CHECKSUM"
                if observation.payload_checksum_match
                else "OTHER"
            )
        )
        if trailer == 0x88:
            observation.payload_checksum_policy = "NO_CHECK_0X88_ACCEPTED"
        elif observation.payload_checksum_match:
            observation.payload_checksum_policy = "ADDITIVE_VERIFIED"
        else:
            raise ChecksumMismatch("payload_checksum")

        observation.decode_stage = "image_record_crc"
        try:
            raster = decode_image_record(data[5:])
        except ImageCrcError:
            observation.image_record_crc_match = False
            raise
        observation.image_record_crc_match = True
        observation.decode_stage = "successful_raster_decode"
        observation.raster_shape_if_success = (len(raster) // 64, 64)
        return raster
    except Exception as error:
        observation.exception_class = type(error).__name__
        raise


class Transport(Protocol):
    def exchange(self, request: bytes) -> Iterable[bytes]:
        ...


class FdtLifecycleObserver(Protocol):
    def observe_af_state(self, pov_valid: bool) -> object:
        ...

    def arm_fdt(self) -> object:
        ...

    def post_irq2_image_command(self) -> object:
        ...

    def first_image_received(self) -> object:
        ...

    def fail_closed(self, reason: str) -> None:
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

    def __init__(self, transport: Transport, lifecycle: FdtLifecycleObserver | None = None):
        self.transport = transport
        self.lifecycle = lifecycle
        self.phase = "POST_D4"
        self.path: str | None = None
        self.image: tuple[int, ...] | None = None
        self.image_command_attempt_count = 0

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
        if self.lifecycle is not None:
            self.lifecycle.observe_af_state(state.pov_valid)
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
        try:
            if self.lifecycle is not None:
                self.lifecycle.arm_fdt()
            self._send_async(build_fdt_down(table12, ts16), 0x32)
            self.phase = "WAIT_FDT_DOWN"
        except Exception:
            if self.lifecycle is not None:
                self.lifecycle.fail_closed("initial_fdt_arm_failed")
                self.phase = "FDT_ARM_FAILED"
            raise

    def receive_payload(self, payload: bytes) -> tuple[int, ...] | None:
        if self.phase == "WAIT_FDT_DOWN":
            try:
                event = parse_fdt_event(payload)
                if event.irq != 2:
                    raise UnexpectedEvent(f"fdt_order:0x{event.irq:x}")
            except Exception:
                if self.lifecycle is not None:
                    self.lifecycle.fail_closed("fdt_event_validation_failed")
                    self.phase = "FDT_EVENT_FAILED"
                raise
            if self.image_command_attempt_count:
                raise InvalidTransition("post_irq2_image_command_already_attempted")
            self.image_command_attempt_count = 1
            self.phase = "IMAGE_COMMAND_ATTEMPTED"
            try:
                # Target packet 227 proves cmd0=2/cmd1=1 (wire 0x22) after
                # finger-down. Wire 0x20 remains a separate baseline builder.
                if self.lifecycle is not None:
                    self.lifecycle.post_irq2_image_command()
                self._send_async(build_finger_image(), 0x22)
                self.phase = "WAIT_IMAGE"
            except Exception:
                if self.lifecycle is not None:
                    self.lifecycle.fail_closed("post_irq2_image_command_failed")
                self.phase = "IMAGE_COMMAND_FAILED"
                raise
            return None
        if self.phase == "WAIT_IMAGE":
            try:
                self.image = parse_image_payload(payload)
                if self.lifecycle is not None and self.path == "FRESH_FDT":
                    self.lifecycle.first_image_received()
            except Exception:
                if self.lifecycle is not None:
                    self.lifecycle.fail_closed("first_image_validation_failed")
                    self.phase = "IMAGE_VALIDATION_FAILED"
                raise
            self.phase = FIRST_IMAGE_RECEIVED
            return self.image
        raise InvalidTransition(f"payload_in_phase:{self.phase}")

    def eof(self) -> None:
        if self.phase != FIRST_IMAGE_RECEIVED:
            raise StreamEnded(f"machine_eof:{self.phase}")
