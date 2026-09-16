"""D233 production-shaped USB/TLS backend, offline tested and source sealed.

The real libusb ABI and OpenSSL-backed TLS implementation are present for
review, but shipped D233 source cannot initialize libusb.  D234 requires an
explicit source edit removing ``_d233_usb_source_seal`` plus a separate human
risk decision and authorization.  There is no runtime enablement switch.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import hmac
import json
import os
import signal
import ssl
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence

from poc.goodix5125.tools.binding_reference.runtime import (
    derive_validator_from_canonical_pe,
    verify_canonical_pe,
)

from .goodix5125_d232_offline import (
    AbortClass,
    ContractError,
    DurableReportPublisher,
    EXACT_PHASE_ORDER,
    FORBIDDEN_CONTROLS,
    PHASE_TIMEOUT_MS,
    PHASE_RESPONSE_POLICIES,
    PSK_LENGTH,
    ReplayAbort,
    SecretBuffer,
    TARGET_PID,
    TARGET_VID,
    TLS_IDENTITY,
    TLS_SUITE,
    TargetMaterial,
    PreflightSnapshot,
    _run_exact_oem_core,
    build_b0,
    parse_a0,
    parse_b0,
    validate_tls_client_hello_record,
)


D233_LIVE_CAPABILITY = 0
USB_INTERFACE = 0
USB_EP_OUT = 0x01
USB_EP_IN = 0x81
USB_MAX_PACKET = 64
USB_MAX_FRAME = 65539
TLS_RECORD_PACING_MS = 10
TLS_CIPHER_NAME = "PSK-AES128-GCM-SHA256"
TARGET_CONFIG90_PATH = Path("/var/lib/goodix-5125-poc/target-config-90.bin")
TARGET_CONFIG90_SHA256 = "e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82"
PRODUCTION_CANDIDATE_SCHEMA = "d233-production-candidate-run-report-v1"
INJECTED_OFFLINE_MODE = "injected_offline_test"


class D233LiveUnavailable(RuntimeError):
    """The D233 source seal prevented any real USB initialization."""


class UsbFailure(RuntimeError):
    pass


class UsbTimeout(UsbFailure):
    pass


class UsbAmbiguousCompletion(UsbFailure):
    pass


def _d233_usb_source_seal() -> None:
    """Unconditional shipped-source barrier; D234 must delete this call."""
    raise D233LiveUnavailable("D233 USB source is hard-disabled")


@dataclass(frozen=True)
class UsbIdentity:
    vid: int
    pid: int
    bus: int
    address: int
    port_path: tuple[int, ...]


class UsbApi(Protocol):
    def init(self) -> object: ...
    def open_exact(self, context: object, vid: int, pid: int) -> object | None: ...
    def identity(self, handle: object) -> UsbIdentity: ...
    def claim_interface(self, handle: object, interface: int) -> None: ...
    def bulk_out(self, handle: object, endpoint: int, data: bytes, timeout_ms: int) -> int: ...
    def bulk_in(self, handle: object, endpoint: int, maximum: int, timeout_ms: int) -> bytes: ...
    def release_interface(self, handle: object, interface: int) -> None: ...
    def close(self, handle: object) -> None: ...
    def exit(self, context: object) -> None: ...


class _LibusbDeviceDescriptor(ctypes.Structure):
    _fields_ = (
        ("bLength", ctypes.c_uint8),
        ("bDescriptorType", ctypes.c_uint8),
        ("bcdUSB", ctypes.c_uint16),
        ("bDeviceClass", ctypes.c_uint8),
        ("bDeviceSubClass", ctypes.c_uint8),
        ("bDeviceProtocol", ctypes.c_uint8),
        ("bMaxPacketSize0", ctypes.c_uint8),
        ("idVendor", ctypes.c_uint16),
        ("idProduct", ctypes.c_uint16),
        ("bcdDevice", ctypes.c_uint16),
        ("iManufacturer", ctypes.c_uint8),
        ("iProduct", ctypes.c_uint8),
        ("iSerialNumber", ctypes.c_uint8),
        ("bNumConfigurations", ctypes.c_uint8),
    )


class LibusbSystemApi:
    """Minimal clean-room libusb-1.0 ABI binding; no detach or wildcard API."""

    LIBUSB_ERROR_TIMEOUT = -7

    def __init__(self, library: str | None = None):
        name = library or ctypes.util.find_library("usb-1.0")
        if not name:
            raise UsbFailure("libusb-1.0 runtime unavailable")
        self._lib = ctypes.CDLL(name)
        void_p = ctypes.c_void_p
        self._lib.libusb_init.argtypes = (ctypes.POINTER(void_p),)
        self._lib.libusb_init.restype = ctypes.c_int
        self._lib.libusb_exit.argtypes = (void_p,)
        self._lib.libusb_open_device_with_vid_pid.argtypes = (void_p, ctypes.c_uint16, ctypes.c_uint16)
        self._lib.libusb_open_device_with_vid_pid.restype = void_p
        self._lib.libusb_get_device.argtypes = (void_p,)
        self._lib.libusb_get_device.restype = void_p
        self._lib.libusb_get_device_descriptor.argtypes = (void_p, ctypes.POINTER(_LibusbDeviceDescriptor))
        self._lib.libusb_get_device_descriptor.restype = ctypes.c_int
        self._lib.libusb_get_bus_number.argtypes = (void_p,)
        self._lib.libusb_get_bus_number.restype = ctypes.c_uint8
        self._lib.libusb_get_device_address.argtypes = (void_p,)
        self._lib.libusb_get_device_address.restype = ctypes.c_uint8
        self._lib.libusb_get_port_numbers.argtypes = (void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_int)
        self._lib.libusb_get_port_numbers.restype = ctypes.c_int
        self._lib.libusb_claim_interface.argtypes = (void_p, ctypes.c_int)
        self._lib.libusb_claim_interface.restype = ctypes.c_int
        self._lib.libusb_release_interface.argtypes = (void_p, ctypes.c_int)
        self._lib.libusb_release_interface.restype = ctypes.c_int
        self._lib.libusb_bulk_transfer.argtypes = (
            void_p,
            ctypes.c_ubyte,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_uint,
        )
        self._lib.libusb_bulk_transfer.restype = ctypes.c_int
        self._lib.libusb_close.argtypes = (void_p,)

    @staticmethod
    def _check(result: int, operation: str) -> None:
        if result == LibusbSystemApi.LIBUSB_ERROR_TIMEOUT:
            raise UsbTimeout(operation)
        if result != 0:
            raise UsbFailure(f"{operation} failed ({result})")

    def init(self) -> object:
        _d233_usb_source_seal()
        context = ctypes.c_void_p()
        self._check(self._lib.libusb_init(ctypes.byref(context)), "libusb_init")
        return context

    def open_exact(self, context: object, vid: int, pid: int) -> object | None:
        _d233_usb_source_seal()
        if (vid, pid) != (TARGET_VID, TARGET_PID):
            raise UsbFailure("non-target USB identity")
        return self._lib.libusb_open_device_with_vid_pid(context, vid, pid) or None

    def identity(self, handle: object) -> UsbIdentity:
        _d233_usb_source_seal()
        device = self._lib.libusb_get_device(handle)
        if not device:
            raise UsbFailure("libusb device identity unavailable")
        descriptor = _LibusbDeviceDescriptor()
        self._check(self._lib.libusb_get_device_descriptor(device, ctypes.byref(descriptor)), "descriptor")
        ports = (ctypes.c_uint8 * 8)()
        port_count = self._lib.libusb_get_port_numbers(device, ports, len(ports))
        if port_count < 0:
            self._check(port_count, "port path")
        return UsbIdentity(
            descriptor.idVendor,
            descriptor.idProduct,
            self._lib.libusb_get_bus_number(device),
            self._lib.libusb_get_device_address(device),
            tuple(ports[:port_count]),
        )

    def claim_interface(self, handle: object, interface: int) -> None:
        _d233_usb_source_seal()
        if interface != USB_INTERFACE:
            raise UsbFailure("wrong interface")
        self._check(self._lib.libusb_claim_interface(handle, interface), "claim interface")

    def bulk_out(self, handle: object, endpoint: int, data: bytes, timeout_ms: int) -> int:
        _d233_usb_source_seal()
        if endpoint != USB_EP_OUT or not data or timeout_ms <= 0:
            raise UsbFailure("invalid bulk OUT contract")
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        transferred = ctypes.c_int()
        self._check(
            self._lib.libusb_bulk_transfer(handle, endpoint, buffer, len(data), ctypes.byref(transferred), timeout_ms),
            "bulk OUT",
        )
        return transferred.value

    def bulk_in(self, handle: object, endpoint: int, maximum: int, timeout_ms: int) -> bytes:
        _d233_usb_source_seal()
        if endpoint != USB_EP_IN or maximum <= 0 or timeout_ms <= 0:
            raise UsbFailure("invalid bulk IN contract")
        buffer = (ctypes.c_ubyte * maximum)()
        transferred = ctypes.c_int()
        self._check(
            self._lib.libusb_bulk_transfer(handle, endpoint, buffer, maximum, ctypes.byref(transferred), timeout_ms),
            "bulk IN",
        )
        return bytes(buffer[: transferred.value])

    def release_interface(self, handle: object, interface: int) -> None:
        _d233_usb_source_seal()
        self._check(self._lib.libusb_release_interface(handle, interface), "release interface")

    def close(self, handle: object) -> None:
        _d233_usb_source_seal()
        self._lib.libusb_close(handle)

    def exit(self, context: object) -> None:
        _d233_usb_source_seal()
        self._lib.libusb_exit(context)


class ProductionUsbTransport:
    """Exact-target, no-retry framed transport with injected libusb seam."""

    def __init__(self, api: UsbApi, *, expected_identity: UsbIdentity | None = None):
        self._api = api
        self._expected_identity = expected_identity
        self._context: object | None = None
        self._handle: object | None = None
        self._baseline: UsbIdentity | None = None
        self._claimed = False
        self._closed = False
        self._rx = bytearray()
        self._rx_completion_ids: list[int] = []
        self._completion_counter = 0
        self.last_frame_completion_ids: tuple[int, ...] = ()
        self.usb_open_count = 0
        self.release_count = 0
        self.close_count = 0
        self.exit_count = 0
        self.command_count = 0
        self.bulk_out_submit_count = 0
        self.bulk_out_complete_count = 0
        self.bulk_out_logical_chunk_lengths: list[int] = []
        self.bulk_out_wire_chunk_lengths: list[int] = []
        self.bulk_in_call_count = 0
        self.bulk_in_timeout_count = 0
        self.bulk_in_error_count = 0
        self.bulk_in_nonzero_count = 0

    def transport_open(self) -> None:
        if self._context is not None or self._closed:
            raise UsbFailure("transport open is single-use")
        self._context = self._api.init()
        self._handle = self._api.open_exact(self._context, TARGET_VID, TARGET_PID)
        if self._handle is None:
            raise UsbFailure("exact target absent")
        self.usb_open_count = 1
        identity = self._api.identity(self._handle)
        if (identity.vid, identity.pid) != (TARGET_VID, TARGET_PID):
            raise UsbFailure("wrong VID/PID after open")
        if self._expected_identity is not None and identity != self._expected_identity:
            raise UsbFailure("target identity mismatch")
        self._baseline = identity
        self._api.claim_interface(self._handle, USB_INTERFACE)
        self._claimed = True

    def _require_open(self) -> object:
        if self._handle is None or not self._claimed or self._closed:
            raise UsbFailure("transport not open and claimed")
        return self._handle

    def revalidate_identity(self) -> None:
        handle = self._require_open()
        if self._api.identity(handle) != self._baseline:
            raise UsbFailure("unexpected re-enumeration or identity change")

    @staticmethod
    def _remaining(deadline: float) -> int:
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            raise UsbTimeout("transport deadline")
        return remaining

    def write_frame(self, frame: bytes, timeout_ms: int) -> None:
        handle = self._require_open()
        frame = bytes(frame)
        if not frame or len(frame) > USB_MAX_FRAME:
            raise UsbFailure("frame length outside contract")
        if len(frame) < 4 or frame[0] not in (0xA0, 0xB0):
            raise UsbFailure("unclassified A0/B0 wrapper")
        declared_total = 4 + int.from_bytes(frame[1:3], "little")
        if declared_total != len(frame):
            raise UsbFailure("A0/B0 declared length mismatch")
        if frame[3] != (frame[0] + frame[1] + frame[2]) & 0xFF:
            raise UsbFailure("malformed A0/B0 tag")
        deadline = time.monotonic() + timeout_ms / 1000
        for offset in range(0, len(frame), USB_MAX_PACKET):
            chunk = frame[offset : offset + USB_MAX_PACKET]
            # D239/D241 live evidence proves short final submissions for this
            # A0 path.  Preserve D242's fixed endpoint-sized staging only for
            # B0/TLS, whose physical transport contract remains an offline
            # result awaiting live confirmation.
            wire_chunk = (
                chunk.ljust(USB_MAX_PACKET, b"\x00")
                if frame[0] == 0xB0
                else chunk
            )
            self.bulk_out_submit_count += 1
            self.bulk_out_logical_chunk_lengths.append(len(chunk))
            self.bulk_out_wire_chunk_lengths.append(len(wire_chunk))
            transferred = self._api.bulk_out(
                handle, USB_EP_OUT, wire_chunk, self._remaining(deadline)
            )
            if transferred != len(wire_chunk):
                raise UsbAmbiguousCompletion("partial bulk OUT")
            self.bulk_out_complete_count += 1
        self.command_count += 1

    def _bulk_in(self, handle: object, maximum: int, timeout_ms: int) -> bytes:
        self.bulk_in_call_count += 1
        try:
            part = self._api.bulk_in(handle, USB_EP_IN, maximum, timeout_ms)
        except UsbTimeout:
            self.bulk_in_timeout_count += 1
            raise
        except UsbFailure:
            self.bulk_in_error_count += 1
            raise
        if part:
            self.bulk_in_nonzero_count += 1
        return part

    def read_frame(self, timeout_ms: int) -> bytes:
        handle = self._require_open()
        deadline = time.monotonic() + timeout_ms / 1000
        while len(self._rx) < 4:
            part = self._bulk_in(handle, USB_MAX_PACKET, self._remaining(deadline))
            if not part:
                raise UsbAmbiguousCompletion("zero-length bulk IN")
            self._rx.extend(part)
            self._completion_counter += 1
            self._rx_completion_ids.extend([self._completion_counter] * len(part))
        if self._rx[0] not in (0xA0, 0xB0):
            raise UsbFailure("malformed A0/B0 magic")
        total = 4 + int.from_bytes(self._rx[1:3], "little")
        if total < 4 or total > USB_MAX_FRAME:
            raise UsbFailure("malformed A0/B0 length")
        while len(self._rx) < total:
            part = self._bulk_in(
                handle, min(4096, total - len(self._rx)), self._remaining(deadline)
            )
            if not part:
                raise UsbAmbiguousCompletion("short bulk IN")
            self._rx.extend(part)
            self._completion_counter += 1
            self._rx_completion_ids.extend([self._completion_counter] * len(part))
        frame = bytes(self._rx[:total])
        completion_ids = tuple(dict.fromkeys(self._rx_completion_ids[:total]))
        del self._rx[:total]
        del self._rx_completion_ids[:total]
        self.last_frame_completion_ids = completion_ids
        if frame[3] != (frame[0] + frame[1] + frame[2]) & 0xFF:
            raise UsbFailure("malformed A0/B0 tag")
        return frame

    def cleanup(self) -> None:
        if self._closed:
            return
        self._closed = True
        first_error: Exception | None = None
        if self._claimed and self._handle is not None:
            try:
                self._api.release_interface(self._handle, USB_INTERFACE)
                self.release_count += 1
            except Exception as exc:  # cleanup continues deterministically
                first_error = exc
            self._claimed = False
        if self._handle is not None:
            try:
                self._api.close(self._handle)
                self.close_count += 1
            except Exception as exc:
                first_error = first_error or exc
            self._handle = None
        if self._context is not None:
            try:
                self._api.exit(self._context)
                self.exit_count += 1
            except Exception as exc:
                first_error = first_error or exc
            self._context = None
        if first_error is not None:
            raise UsbFailure("USB cleanup failure") from first_error


def _split_tls_records(stream: bytes) -> tuple[bytes, ...]:
    records: list[bytes] = []
    cursor = 0
    while cursor < len(stream):
        if len(stream) - cursor < 5:
            raise ContractError("partial TLS record emitted")
        length = int.from_bytes(stream[cursor + 3 : cursor + 5], "big")
        end = cursor + 5 + length
        if end > len(stream):
            raise ContractError("partial TLS record emitted")
        records.append(stream[cursor:end])
        cursor = end
    return tuple(records)


_TLS_CONTENT_TYPE_NAMES = {
    0x14: "change_cipher_spec",
    0x15: "alert",
    0x16: "handshake",
    0x17: "application_data",
}
_TLS_HANDSHAKE_TYPE_NAMES = {
    0x01: "client_hello",
    0x02: "server_hello",
    0x0C: "server_key_exchange",
    0x0E: "server_hello_done",
    0x10: "client_key_exchange",
    0x14: "finished",
}


def _redacted_tls_record(
    record: bytes,
    *,
    record_index: int,
    direction: str,
    state_before: str,
    state_after: str,
    handshake_type_verified: bool,
) -> dict[str, object]:
    """Return header-only TLS observability; never retain record payload bytes."""
    record = bytes(record)
    if len(record) < 5:
        raise ContractError("partial TLS record in trace")
    declared = int.from_bytes(record[3:5], "big")
    if len(record) != 5 + declared:
        raise ContractError("TLS record length mismatch in trace")
    content_type = record[0]
    result: dict[str, object] = {
        "record_index": record_index,
        "direction": direction,
        "tls_content_type": _TLS_CONTENT_TYPE_NAMES.get(
            content_type, f"unknown_0x{content_type:02x}"
        ),
        "tls_version": f"0x{record[1]:02x}{record[2]:02x}",
        "record_length": declared,
        "handshake_type_if_verified": "not_verified",
        "handshake_state_before": state_before,
        "handshake_state_after": state_after,
        "observation_basis": "tls_record_header_observed",
    }
    handshake_length = (
        int.from_bytes(record[6:9], "big")
        if content_type == 0x16 and declared >= 4
        else -1
    )
    if (
        handshake_type_verified
        and content_type == 0x16
        and handshake_length >= 0
        and 4 + handshake_length <= declared
    ):
        handshake_type = record[5]
        result["handshake_type_if_verified"] = _TLS_HANDSHAKE_TYPE_NAMES.get(
            handshake_type, f"unknown_0x{handshake_type:02x}"
        )
    if content_type == 0x15 and declared == 2:
        result["alert_level"] = record[5]
        result["alert_description"] = record[6]
    return result


class Tls12PskServer:
    """One-shot OpenSSL TLS 1.2 PSK server over MemoryBIO."""

    def __init__(self, secret: SecretBuffer):
        self._owned = bytearray(secret.view())
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
        self.handshake_count = 0
        self.want_read_count = 0
        self.want_write_count = 0
        self.fatal_error_observed = False
        self.complete = False
        self.closed = False

    def feed(self, tls_bytes: bytes) -> None:
        if self.complete or self.closed:
            raise ReplayAbort(AbortClass.EXTRA_OR_REORDERED)
        self._input.write(bytes(tls_bytes))

    def advance(self) -> None:
        if self.closed:
            raise ReplayAbort(AbortClass.INTERNAL)
        if self.complete:
            raise ReplayAbort(AbortClass.EXTRA_OR_REORDERED)
        if self.handshake_count == 0:
            self.handshake_count = 1
        try:
            self._ssl.do_handshake()
            if self._ssl.version() != "TLSv1.2":
                raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
            cipher = self._ssl.cipher()
            if cipher is None or cipher[0] != TLS_CIPHER_NAME:
                raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
            self.complete = True
        except ssl.SSLWantReadError:
            self.want_read_count += 1
            return
        except ssl.SSLWantWriteError:
            self.want_write_count += 1
            return
        except ssl.SSLError as exc:
            self.fatal_error_observed = True
            reason = (getattr(exc, "reason", "") or "").upper()
            if (
                "BAD_RECORD_MAC" in reason
                or "DECRYPT" in reason
                or reason == "RECORD_LAYER_FAILURE"
            ):
                raise ReplayAbort(AbortClass.BAD_RECORD_MAC) from exc
            if "ALERT" in reason:
                raise ReplayAbort(AbortClass.TLS_ALERT) from exc
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA) from exc

    def drain(self) -> tuple[bytes, ...]:
        output = bytearray()
        while self._output.pending:
            output.extend(self._output.read())
        return _split_tls_records(bytes(output)) if output else ()

    def close(self) -> None:
        if not self.closed:
            for index in range(len(self._owned)):
                self._owned[index] = 0
            self.closed = True

    @property
    def is_zeroized(self) -> bool:
        return self.closed and not any(self._owned)


class B0TlsBridge:
    """Moves fragmented device TLS input and whole OpenSSL records via B0."""

    def __init__(
        self,
        engine: Tls12PskServer,
        transport: ProductionUsbTransport,
        *,
        pacer: Callable[[float], None] = time.sleep,
        pacing_ms: int = TLS_RECORD_PACING_MS,
    ):
        self.engine = engine
        self.transport = transport
        self.pump_count = 0
        self.first_tls_record_handoff_count = 0
        self.input_record_count = 0
        self.output_record_count = 0
        self.trace: list[dict[str, object]] = []
        self._record_index = 0
        self._input_trace_buffer = bytearray()
        self._input_encrypted = False
        self._output_encrypted = False
        self._pacer = pacer
        self.pacing_ms = pacing_ms
        self.pacing_count = 0

    @staticmethod
    def _remaining(deadline: float) -> int:
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            raise ReplayAbort(AbortClass.TLS_TIMEOUT)
        return remaining

    def _state(self) -> str:
        if getattr(self.engine, "complete", False):
            return "cryptographic_handshake_complete"
        if getattr(self.engine, "handshake_count", 0):
            return "handshake_in_progress"
        return "awaiting_first_tls_record"

    def _trace_input(self, payload: bytes, before: str, after: str, *, first_record: bool) -> None:
        self._input_trace_buffer.extend(payload)
        while len(self._input_trace_buffer) >= 5:
            total = 5 + int.from_bytes(self._input_trace_buffer[3:5], "big")
            if len(self._input_trace_buffer) < total:
                break
            record = bytes(self._input_trace_buffer[:total])
            del self._input_trace_buffer[:total]
            self._record_index += 1
            verified = first_record and self.input_record_count == 0
            self.trace.append(
                _redacted_tls_record(
                    record,
                    record_index=self._record_index,
                    direction="device_to_host",
                    state_before=before,
                    state_after=after,
                    handshake_type_verified=verified or not self._input_encrypted,
                )
            )
            self.input_record_count += 1
            if record[0] == 0x14:
                self._input_encrypted = True

    def accept_b0(
        self,
        frame: bytes,
        timeout_ms: int,
        *,
        first_record: bool = False,
        deadline: float | None = None,
    ) -> None:
        if timeout_ms <= 0:
            raise ReplayAbort(AbortClass.TLS_TIMEOUT)
        deadline = time.monotonic() + timeout_ms / 1000 if deadline is None else deadline
        if first_record:
            if self.first_tls_record_handoff_count:
                raise ReplayAbort(AbortClass.EXTRA_OR_REORDERED)
            self.first_tls_record_handoff_count = 1

        try:
            payload = parse_b0(frame)
        except ContractError as exc:
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA) from exc
        if first_record:
            validate_tls_client_hello_record(payload)
        before = self._state()
        self.engine.feed(payload)
        self.engine.advance()
        after = self._state()
        self._trace_input(payload, before, after, first_record=first_record)
        for record in self.engine.drain():
            self._record_index += 1
            self.trace.append(
                _redacted_tls_record(
                    record,
                    record_index=self._record_index,
                    direction="host_to_device",
                    state_before=after,
                    state_after=after,
                    handshake_type_verified=not self._output_encrypted,
                )
            )
            self.transport.write_frame(build_b0(record), self._remaining(deadline))
            self.output_record_count += 1
            if self.pacing_ms:
                self._pacer(self.pacing_ms / 1000)
                self.pacing_count += 1
            if record[0] == 0x14:
                self._output_encrypted = True
        self.pump_count += 1


class RuntimePskE4Binder:
    """Derives a validator from the loaded PSK and compares E4 in constant time."""

    E4_PREFIX = bytes.fromhex("00030002bb20000000")

    def __init__(self, derive_validator: Callable[[memoryview], bytes | bytearray]):
        self._derive = derive_validator
        self.compare_count = 0

    @classmethod
    def from_canonical_pe(cls, pe_path: Path) -> "RuntimePskE4Binder":
        """Bind E4 to the recovered D190 reference; no cached validator exists."""
        canonical = Path(pe_path)
        return cls(lambda secret: derive_validator_from_canonical_pe(canonical, secret))

    def validate(self, secret: SecretBuffer, responses: tuple[bytes, ...]) -> None:
        if len(responses) != 2:
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
        try:
            typed = parse_a0(responses[1])
        except ContractError as exc:
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA) from exc
        if typed.control != 0xE4 or not typed.body.startswith(self.E4_PREFIX):
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
        actual = typed.body[len(self.E4_PREFIX) :]
        if len(actual) != 32:
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
        derived = self._derive(secret.view())
        expected = derived if isinstance(derived, bytearray) else bytearray(derived)
        try:
            if len(expected) != 32 or not hmac.compare_digest(expected, actual):
                raise ReplayAbort(AbortClass.SECRET_BOUNDARY)
            self.compare_count += 1
        finally:
            for index in range(len(expected)):
                expected[index] = 0


def _redacted_protocol_observation(
    phase: str,
    responses: tuple[bytes, ...],
    completion_ids: tuple[tuple[int, ...], ...],
) -> dict[str, object]:
    """Describe response framing without retaining payload or secret bytes."""
    policy = PHASE_RESPONSE_POLICIES[phase]
    result: dict[str, object] = {
        "phase": phase,
        "request_control": f"0x{policy.request_control:02x}",
        "first_in_wrapper": "none",
        "first_in_control": "none",
        "ack_echo": "none",
        "ack_status": "none",
        "ack_body_length": 0,
        "response_control": "none",
        "response_body_length": 0,
        "ordering_classification": "no_complete_frame",
        "completion_classification": "none",
    }
    parsed: list[tuple[str, int | None, bytes | None]] = []
    for index, frame in enumerate(responses):
        if frame[:1] == b"\xa0":
            try:
                typed = parse_a0(frame)
            except ContractError:
                parsed.append(("malformed_a0", None, None))
            else:
                parsed.append(("A0", typed.control, typed.body))
        elif frame[:1] == b"\xb0":
            try:
                body = parse_b0(frame)
            except ContractError:
                parsed.append(("malformed_b0", None, None))
            else:
                parsed.append(("B0", None, body))
        else:
            parsed.append(("unknown", None, None))
        if index == 0:
            result["first_in_wrapper"] = parsed[-1][0]
            if parsed[-1][1] is not None:
                result["first_in_control"] = f"0x{parsed[-1][1]:02x}"

    if completion_ids:
        flattened = [item for group in completion_ids for item in group]
        if any(len(group) > 1 for group in completion_ids):
            result["completion_classification"] = "frame_fragmented_across_usb_completions"
        elif len(completion_ids) > 1 and set(completion_ids[0]).intersection(completion_ids[1]):
            result["completion_classification"] = "ack_and_response_same_usb_completion"
        elif len(completion_ids) > 1:
            result["completion_classification"] = "ack_and_response_separate_usb_completions"
        elif flattened:
            result["completion_classification"] = "single_frame_usb_completion"

    if parsed and parsed[0][0] == "A0" and parsed[0][1] == 0xB0:
        ack_body = parsed[0][2] or b""
        result["ack_body_length"] = len(ack_body)
        if len(ack_body) >= 1:
            result["ack_echo"] = f"0x{ack_body[0]:02x}"
        if len(ack_body) >= 2:
            result["ack_status"] = f"0x{ack_body[1]:02x}"

    if len(parsed) >= 2 and parsed[1][0] == "A0":
        control, body = parsed[1][1], parsed[1][2] or b""
        result["response_control"] = f"0x{control:02x}"
        result["response_body_length"] = len(body)
    elif parsed and parsed[0][0] == "B0":
        result["response_control"] = "B0/TLS"
        result["response_body_length"] = len(parsed[0][2] or b"")

    if policy.response_kind == "b0_tls_client_hello":
        result["ordering_classification"] = (
            "direct_b0_tls" if parsed and parsed[0][0] == "B0" else "unexpected_for_d1"
        )
    elif policy.response_kind == "ack_only":
        result["ordering_classification"] = (
            "ack_only"
            if len(parsed) == 1 and parsed[0][0] == "A0" and parsed[0][1] == 0xB0
            else "unexpected_for_ack_only"
        )
    elif len(parsed) == 2:
        first, second = parsed
        if first[0] == "A0" and first[1] == 0xB0 and second[0] == "A0" and second[1] == policy.request_control:
            result["ordering_classification"] = "ack_then_same_control_response"
        elif first[0] == "A0" and first[1] == policy.request_control and second[0] == "A0" and second[1] == 0xB0:
            result["ordering_classification"] = "same_control_response_before_ack"
        else:
            result["ordering_classification"] = "unexpected_two_frame_order"
    elif responses:
        result["ordering_classification"] = "unexpected_frame_count_or_shape"
    return result


class ProductionReplayBackend:
    """D232 backend contract implemented by exact USB framing and real TLS."""

    RESPONSE_COUNTS = {
        "E4": 2, "A2_1": 2, "CHIP_82": 2, "OTP_A6": 2, "A2_2": 2,
        "MODE_70": 1, "DAC_220": 1, "DAC_236": 1, "DAC_238": 1,
        "DAC_23A": 1, "CONFIG_90": 2, "D1": 1,
    }

    def __init__(
        self,
        transport: ProductionUsbTransport,
        secret: SecretBuffer,
        binder: RuntimePskE4Binder,
        *,
        tls_factory: Callable[[SecretBuffer], Tls12PskServer] = Tls12PskServer,
        tls_pacer: Callable[[float], None] = time.sleep,
    ):
        self.transport = transport
        self.secret = secret
        self.binder = binder
        self.tls_factory = tls_factory
        self.tls_pacer = tls_pacer
        self.exchange_count = 0
        self.tls_handshake_count = 0
        self.cleanup_count = 0
        self._phase_index = 0
        self._opened = False
        self.last_attempted_phase = "not_reached"
        self.last_failure_domain = "none"
        self.protocol_observations: list[dict[str, object]] = []
        self.first_tls_record_handoff_count = 0
        self.tls_secret_object_identity_verified = False
        self.tls_failure_class = "none"
        self.tls_trace_redacted: list[dict[str, object]] = []
        self._pending_first_b0: bytes | None = None
        self._pending_first_b0_consumed = False
        self.server_flight_b0_frame_count = 0
        self.server_flight_tls_record_count = 0
        self.server_flight_usb_bulk_out_count = 0
        self.server_flight_chunk_size_buckets: dict[str, int] = {}
        self.server_flight_pacing_count = 0
        self.post_server_flight_bulk_in_call_count = 0
        self.post_server_flight_bulk_in_timeout_count = 0
        self.post_server_flight_bulk_in_error_count = 0
        self.post_server_flight_nonzero_rx_count = 0
        self.openssl_want_read_count = 0
        self.openssl_want_write_count = 0
        self.openssl_fatal_error_observed = False

    @property
    def usb_open_count(self) -> int:
        return self.transport.usb_open_count

    def exchange(self, phase_id: str, request: bytes, timeout_ms: int) -> tuple[bytes, ...]:
        if self._phase_index >= len(EXACT_PHASE_ORDER) - 1 or phase_id != EXACT_PHASE_ORDER[self._phase_index]:
            raise ReplayAbort(AbortClass.EXTRA_OR_REORDERED)
        self.last_attempted_phase = phase_id
        self.last_failure_domain = "none"
        responses: list[bytes] = []
        completion_ids: list[tuple[int, ...]] = []
        try:
            parsed = parse_a0(request, checksum_seed_control=0xD0 if phase_id == "D1" else None)
            if parsed.control in FORBIDDEN_CONTROLS:
                raise ReplayAbort(AbortClass.EXTRA_OR_REORDERED)
            if not self._opened:
                self.transport.transport_open()
                self._opened = True
            self.transport.revalidate_identity()
            self.transport.write_frame(request, timeout_ms)
            self.exchange_count += 1
            for _ in range(self.RESPONSE_COUNTS[phase_id]):
                responses.append(self.transport.read_frame(timeout_ms))
                completion_ids.append(self.transport.last_frame_completion_ids)
            self.transport.revalidate_identity()
            if phase_id == "D1":
                if self._pending_first_b0 is not None or len(responses) != 1:
                    raise ReplayAbort(AbortClass.EXTRA_OR_REORDERED)
                try:
                    parse_b0(responses[0])
                except ContractError:
                    # The shared response validator owns the D1 protocol
                    # classification; transport framing errors remain visible
                    # there as unexpected D1 data, not as a USB I/O failure.
                    pass
                else:
                    self._pending_first_b0 = bytes(responses[0])
            if phase_id == "E4":
                try:
                    self.binder.validate(self.secret, tuple(responses))
                except ReplayAbort:
                    self.last_failure_domain = "e4_binding"
                    raise
        except UsbTimeout as exc:
            self.last_failure_domain = "usb_transport"
            raise ReplayAbort(AbortClass.TIMEOUT) from exc
        except UsbAmbiguousCompletion as exc:
            self.last_failure_domain = "usb_transport"
            raise ReplayAbort(AbortClass.AMBIGUOUS) from exc
        except (UsbFailure, ContractError) as exc:
            self.last_failure_domain = "usb_transport"
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA) from exc
        finally:
            self.protocol_observations.append(
                _redacted_protocol_observation(
                    phase_id, tuple(responses), tuple(completion_ids)
                )
            )
        self._phase_index += 1
        return tuple(responses)

    def tls_handshake(self, client_hello: bytes, secret: SecretBuffer, timeout_ms: int) -> None:
        self.last_attempted_phase = "TLS"
        self.last_failure_domain = "none"
        if secret is not self.secret or self._phase_index != len(EXACT_PHASE_ORDER) - 1:
            raise ReplayAbort(AbortClass.EXTRA_OR_REORDERED)
        if self.tls_handshake_count:
            raise ReplayAbort(AbortClass.EXTRA_OR_REORDERED)
        if self._pending_first_b0 is None or self._pending_first_b0_consumed:
            raise ReplayAbort(AbortClass.EXTRA_OR_REORDERED)
        pending_payload = parse_b0(self._pending_first_b0)
        if pending_payload != bytes(client_hello):
            raise ReplayAbort(AbortClass.EXTRA_OR_REORDERED)
        self.tls_handshake_count = 1
        engine = self.tls_factory(secret)
        self.tls_secret_object_identity_verified = secret is self.secret
        bridge = B0TlsBridge(engine, self.transport, pacer=self.tls_pacer)
        deadline = time.monotonic() + timeout_ms / 1000
        flight_out_start = self.transport.bulk_out_submit_count
        flight_chunk_start = len(self.transport.bulk_out_wire_chunk_lengths)
        try:
            first_b0 = self._pending_first_b0
            self._pending_first_b0 = None
            self._pending_first_b0_consumed = True
            self.first_tls_record_handoff_count += 1
            bridge.accept_b0(
                first_b0,
                timeout_ms,
                first_record=True,
                deadline=deadline,
            )
            self.server_flight_b0_frame_count = bridge.output_record_count
            self.server_flight_tls_record_count = bridge.output_record_count
            self.server_flight_usb_bulk_out_count = (
                self.transport.bulk_out_submit_count - flight_out_start
            )
            flight_chunks = self.transport.bulk_out_wire_chunk_lengths[
                flight_chunk_start:
            ]
            self.server_flight_chunk_size_buckets = {
                str(size): flight_chunks.count(size) for size in sorted(set(flight_chunks))
            }
            self.server_flight_pacing_count = bridge.pacing_count
            post_in_start = self.transport.bulk_in_call_count
            post_timeout_start = self.transport.bulk_in_timeout_count
            post_error_start = self.transport.bulk_in_error_count
            post_nonzero_start = self.transport.bulk_in_nonzero_count
            while not engine.complete:
                remaining = int((deadline - time.monotonic()) * 1000)
                if remaining <= 0:
                    raise ReplayAbort(AbortClass.TLS_TIMEOUT)
                bridge.accept_b0(
                    self.transport.read_frame(remaining),
                    remaining,
                    deadline=deadline,
                )
            self.tls_failure_class = "none"
        except UsbTimeout as exc:
            self.last_failure_domain = "usb_transport"
            self.tls_failure_class = self._timeout_failure_class(bridge)
            raise ReplayAbort(AbortClass.TLS_TIMEOUT) from exc
        except UsbAmbiguousCompletion as exc:
            self.last_failure_domain = "usb_transport"
            raise ReplayAbort(AbortClass.AMBIGUOUS) from exc
        except UsbFailure as exc:
            self.last_failure_domain = "usb_transport"
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA) from exc
        except ReplayAbort as exc:
            self.last_failure_domain = "tls_engine"
            if exc.abort_class == AbortClass.TLS_TIMEOUT:
                self.tls_failure_class = self._timeout_failure_class(bridge)
            raise
        finally:
            if "post_in_start" in locals():
                self.post_server_flight_bulk_in_call_count = (
                    self.transport.bulk_in_call_count - post_in_start
                )
                self.post_server_flight_bulk_in_timeout_count = (
                    self.transport.bulk_in_timeout_count - post_timeout_start
                )
                self.post_server_flight_bulk_in_error_count = (
                    self.transport.bulk_in_error_count - post_error_start
                )
                self.post_server_flight_nonzero_rx_count = (
                    self.transport.bulk_in_nonzero_count - post_nonzero_start
                )
            self.openssl_want_read_count = int(getattr(engine, "want_read_count", 0))
            self.openssl_want_write_count = int(getattr(engine, "want_write_count", 0))
            self.openssl_fatal_error_observed = bool(
                getattr(engine, "fatal_error_observed", False)
            )
            self.tls_trace_redacted = list(bridge.trace)
            engine.close()

    def _timeout_failure_class(self, bridge: B0TlsBridge) -> str:
        if not self.first_tls_record_handoff_count:
            return "TLS_HANDSHAKE_TIMEOUT_BEFORE_FIRST_TLS_RECORD"
        if bridge.output_record_count:
            return "TLS_HANDSHAKE_TIMEOUT_AFTER_SERVER_FLIGHT"
        if bridge.input_record_count:
            return "TLS_HANDSHAKE_TIMEOUT_AFTER_CLIENTHELLO"
        return "TLS_HANDSHAKE_TIMEOUT_STATE_UNRESOLVED"

    def cleanup(self) -> None:
        self.cleanup_count += 1
        if self.cleanup_count != 1:
            raise ReplayAbort(AbortClass.INTERNAL)
        try:
            self.transport.cleanup()
        except UsbFailure as exc:
            raise ReplayAbort(AbortClass.INTERNAL) from exc


class OsFacade(Protocol):
    def euid(self) -> int: ...
    def sudo_uid(self) -> int | None: ...
    def process_count(self) -> int: ...
    def thread_count(self) -> int: ...
    def external_holders(self, device_path: Path) -> tuple[int, ...]: ...
    def fprintd_active(self) -> bool: ...
    def stop_fprintd(self) -> None: ...
    def start_fprintd(self) -> None: ...
    def block_signals(self, signals: frozenset[int]) -> object: ...
    def restore_signals(self, previous: object) -> None: ...
    def claim_single_use_marker(self, path: Path) -> None: ...
    def report_path_ready(self, path: Path) -> bool: ...


class SystemOsFacade:
    """Future D234 OS facade; D233 entrypoints never construct or call it."""

    def euid(self) -> int:
        return os.geteuid()

    def sudo_uid(self) -> int | None:
        raw = os.environ.get("SUDO_UID")
        return int(raw) if raw is not None and raw.isdecimal() else None

    def process_count(self) -> int:
        return 1

    def thread_count(self) -> int:
        return len(os.listdir("/proc/self/task"))

    def external_holders(self, device_path: Path) -> tuple[int, ...]:
        holders: list[int] = []
        target = os.path.realpath(device_path)
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal() or int(entry.name) == os.getpid():
                continue
            fd_dir = entry / "fd"
            try:
                for fd in fd_dir.iterdir():
                    try:
                        if os.path.realpath(fd) == target:
                            holders.append(int(entry.name))
                            break
                    except OSError:
                        continue
            except OSError:
                continue
        return tuple(sorted(holders))

    def fprintd_active(self) -> bool:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", "fprintd.service"],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0

    def stop_fprintd(self) -> None:
        subprocess.run(["systemctl", "stop", "fprintd.service"], check=True)

    def start_fprintd(self) -> None:
        subprocess.run(["systemctl", "start", "fprintd.service"], check=True)

    def block_signals(self, signals: frozenset[int]) -> object:
        return signal.pthread_sigmask(signal.SIG_BLOCK, signals)

    def restore_signals(self, previous: object) -> None:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)

    def claim_single_use_marker(self, path: Path) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path, flags, 0o600)
        try:
            os.write(fd, b"D234 single-use marker\n")
            os.fsync(fd)
        finally:
            os.close(fd)

    def report_path_ready(self, path: Path) -> bool:
        if not path.is_absolute() or os.path.lexists(path):
            return False
        parent = path.parent
        try:
            status = os.lstat(parent)
        except OSError:
            return False
        return (
            stat.S_ISDIR(status.st_mode)
            and not stat.S_ISLNK(status.st_mode)
            and status.st_uid == 0
            and stat.S_IMODE(status.st_mode) == 0o700
            and os.access(parent, os.W_OK)
        )


class ProductionOsPreflight:
    """Exactly-restored, injected OS preflight transaction."""

    BLOCKED_SIGNALS = frozenset((signal.SIGINT, signal.SIGTERM, signal.SIGHUP))

    def __init__(self, facade: OsFacade, *, operator_uid: int, device_path: Path, marker: Path, report: Path):
        self.facade = facade
        self.operator_uid = operator_uid
        self.device_path = device_path
        self.marker = marker
        self.report = report
        self._signals: object | None = None
        self._fprintd_was_active = False
        self._fprintd_stopped = False
        self._restored = False
        self.restore_count = 0
        self.fprintd_initial_state = "unknown"
        self.fprintd_restore_status = "not_started"
        self.signal_restore_status = "not_started"

    def prepare(self) -> PreflightSnapshot:
        if self.facade.euid() != 0 or self.facade.sudo_uid() != self.operator_uid:
            raise ReplayAbort(AbortClass.PREFLIGHT)
        marker_absent = not os.path.lexists(self.marker)
        report_ready = self.facade.report_path_ready(self.report)
        holders = self.facade.external_holders(self.device_path)
        processes = self.facade.process_count()
        threads = self.facade.thread_count()
        if not marker_absent or not report_ready or holders or processes != 1 or threads != 1:
            raise ReplayAbort(AbortClass.PREFLIGHT)
        try:
            self.facade.claim_single_use_marker(self.marker)
        except OSError as exc:
            raise ReplayAbort(AbortClass.PREFLIGHT) from exc
        self._fprintd_was_active = self.facade.fprintd_active()
        self.fprintd_initial_state = "active" if self._fprintd_was_active else "inactive"
        self._signals = self.facade.block_signals(self.BLOCKED_SIGNALS)
        self.signal_restore_status = "pending"
        if self._fprintd_was_active:
            try:
                self.facade.stop_fprintd()
                self._fprintd_stopped = True
                self.fprintd_restore_status = "pending"
            except BaseException as exc:
                self.fprintd_restore_status = "stop_failed"
                raise ReplayAbort(AbortClass.PREFLIGHT) from exc
        else:
            self.fprintd_restore_status = "not_required"
        return PreflightSnapshot(
            euid=0,
            sudo_uid=self.operator_uid,
            operator_uid=self.operator_uid,
            single_use_marker_absent=True,
            process_count=1,
            thread_count=1,
            external_holder_count=0,
            fprintd_state_captured=True,
            usb_identity_expected=True,
            vid=TARGET_VID,
            pid=TARGET_PID,
            serial_or_path_stable=True,
            signals_blocked_before_transport=True,
            report_path_ready=True,
            restore_plan_present=True,
        )

    def restore(self) -> None:
        if self._restored:
            return
        self.restore_count += 1
        first_error: BaseException | None = None
        try:
            if self._fprintd_stopped:
                try:
                    self.facade.start_fprintd()
                    self._fprintd_stopped = False
                    self.fprintd_restore_status = "restored"
                except BaseException as exc:
                    self.fprintd_restore_status = "failed"
                    first_error = exc
        finally:
            if self._signals is not None:
                try:
                    self.facade.restore_signals(self._signals)
                    self.signal_restore_status = "restored"
                except BaseException as exc:
                    self.signal_restore_status = "failed"
                    first_error = first_error or exc
                finally:
                    self._signals = None
            self._restored = True
        if first_error is not None:
            raise first_error


class _InMemoryReportCapture:
    """Captures the shared D232 core result without publishing its schema."""

    def __init__(self) -> None:
        self.report: dict[str, object] | None = None
        self.publish_count = 0

    def publish(self, report: Mapping[str, object]) -> None:
        if self.publish_count:
            raise ContractError("internal report captured more than once")
        self.report = dict(report)
        self.publish_count = 1


def _candidate_report(
    core: Mapping[str, object] | None,
    *,
    preflight_tx: ProductionOsPreflight,
    backend: ProductionReplayBackend | None,
    reached_phase: str,
    abort_class: str,
    secret_zeroized: bool,
    target_identity_status: str,
    runtime_binding_status: str,
) -> dict[str, object]:
    values = dict(core or {})
    return {
        "schema": PRODUCTION_CANDIDATE_SCHEMA,
        "execution_mode": INJECTED_OFFLINE_MODE,
        "source_seal_state": "sealed",
        "live_authorization": "no",
        "result": values.get("result", "abort"),
        "terminal_state": values.get("terminal_state", "STOP"),
        "reached_phase": values.get("reached_phase", reached_phase),
        "abort_class": values.get("abort_class", abort_class),
        "unexpected_data": (
            values.get("abort_class", abort_class) == AbortClass.UNEXPECTED_DATA.value
        ),
        "command_count": values.get("command_count", 0),
        "usb_open_count": values.get("usb_open_count", 0),
        "tls_handshake_count": values.get("tls_handshake_count", 0),
        "cleanup_count": values.get("cleanup_count", 0),
        "report_publish_count": 0,
        "fprintd_initial_state": preflight_tx.fprintd_initial_state,
        "fprintd_restore_status": preflight_tx.fprintd_restore_status,
        "signal_restore_status": preflight_tx.signal_restore_status,
        "secret_zeroized": values.get("secret_zeroized", secret_zeroized),
        "contains_secret": False,
        "contains_raw_config90": False,
        "runtime_psk_e4_binding_status": runtime_binding_status,
        "target_identity_status": target_identity_status,
        "same_validated_psk_used_by_tls": bool(
            backend is not None
            and backend.binder.compare_count == 1
            and backend.tls_handshake_count == 1
            and backend.tls_secret_object_identity_verified
        ),
        "first_tls_record_handoff_count": (
            backend.first_tls_record_handoff_count if backend is not None else 0
        ),
        "tls_failure_class": (
            backend.tls_failure_class if backend is not None else "none"
        ),
        "tls_handshake_timeout_ms": PHASE_TIMEOUT_MS["TLS"],
        "tls_trace_redacted": (
            list(backend.tls_trace_redacted) if backend is not None else []
        ),
        "server_flight_b0_frame_count": (
            backend.server_flight_b0_frame_count if backend is not None else 0
        ),
        "server_flight_tls_record_count": (
            backend.server_flight_tls_record_count if backend is not None else 0
        ),
        "server_flight_usb_bulk_out_count": (
            backend.server_flight_usb_bulk_out_count if backend is not None else 0
        ),
        "server_flight_chunk_size_buckets": (
            dict(backend.server_flight_chunk_size_buckets)
            if backend is not None else {}
        ),
        "server_flight_pacing_ms": TLS_RECORD_PACING_MS,
        "server_flight_pacing_count": (
            backend.server_flight_pacing_count if backend is not None else 0
        ),
        "post_server_flight_bulk_in_call_count": (
            backend.post_server_flight_bulk_in_call_count if backend is not None else 0
        ),
        "post_server_flight_bulk_in_timeout_count": (
            backend.post_server_flight_bulk_in_timeout_count if backend is not None else 0
        ),
        "post_server_flight_bulk_in_error_count": (
            backend.post_server_flight_bulk_in_error_count if backend is not None else 0
        ),
        "post_server_flight_nonzero_rx_count": (
            backend.post_server_flight_nonzero_rx_count if backend is not None else 0
        ),
        "post_server_flight_first_rx_class": (
            "POST_FLIGHT_NONZERO_DATA_RECEIVED"
            if backend is not None and backend.post_server_flight_nonzero_rx_count
            else "POST_FLIGHT_BULK_IN_ERROR"
            if backend is not None and backend.post_server_flight_bulk_in_error_count
            else "POST_FLIGHT_BULK_IN_ATTEMPTED_NO_DATA"
            if backend is not None and backend.post_server_flight_bulk_in_call_count
            else "NO_POST_FLIGHT_BULK_IN_ATTEMPT"
        ),
        "openssl_handshake_call_count": (
            backend.tls_handshake_count if backend is not None else 0
        ),
        "openssl_want_read_count": (
            backend.openssl_want_read_count if backend is not None else 0
        ),
        "openssl_want_write_count": (
            backend.openssl_want_write_count if backend is not None else 0
        ),
        "openssl_fatal_error_observed": (
            backend.openssl_fatal_error_observed if backend is not None else False
        ),
        "attempted_phase": (
            backend.last_attempted_phase if backend is not None else "not_reached"
        ),
        "backend_failure_domain": (
            backend.last_failure_domain if backend is not None else "none"
        ),
        "protocol_observations": (
            list(backend.protocol_observations) if backend is not None else []
        ),
        "automatic_invasive_recovery": "forbidden",
    }


def run_production_candidate_offline(
    *,
    preflight_tx: ProductionOsPreflight,
    material_loader: Callable[[], TargetMaterial],
    secret_loader: Callable[[], SecretBuffer],
    canonical_pe_path: Path,
    backend_factory: Callable[[SecretBuffer, RuntimePskE4Binder], ProductionReplayBackend],
    checkpoint_publisher: DurableReportPublisher,
    final_publisher: DurableReportPublisher,
) -> dict[str, object]:
    """Production-shaped D234 seam, callable in D233 only with injected facades.

    The shared exact-OEM core is unchanged. Its synthetic report is captured in
    memory and translated; it can never reach either durable candidate path.
    A pre-restore checkpoint preserves the historical causal order:
    stop traffic -> cleanup/zeroize -> durable checkpoint -> restore -> final.
    """
    snapshot = None
    material = None
    secret = None
    backend = None
    core = None
    reached_phase = "PREFLIGHT"
    abort_class = AbortClass.INTERNAL.value
    target_status = "not_checked"
    binding_status = "not_reached"
    checkpoint_ok = False
    try:
        snapshot = preflight_tx.prepare()
        reached_phase = "PROTECTED_INPUT_GATE"
        material = material_loader()
        if not isinstance(material, TargetMaterial):
            raise ContractError("material loader returned wrong type")
        reached_phase = "PE_REFERENCE_GATE"
        pe_status = os.lstat(canonical_pe_path)
        if stat.S_ISLNK(pe_status.st_mode) or not stat.S_ISREG(pe_status.st_mode):
            raise ContractError("canonical PE must be a regular non-symlink")
        verify_canonical_pe(canonical_pe_path)
        reached_phase = "SECRET_LOAD_GATE"
        loaded_secret = secret_loader()
        if not isinstance(loaded_secret, SecretBuffer):
            raise ContractError("secret loader returned wrong type")
        secret = loaded_secret
        binder = RuntimePskE4Binder.from_canonical_pe(canonical_pe_path)
        backend = backend_factory(secret, binder)
        if not isinstance(backend, ProductionReplayBackend):
            raise ContractError("backend factory returned wrong type")
        target_status = "injected_exact_target"
        capture = _InMemoryReportCapture()
        core = _run_exact_oem_core(
            preflight=snapshot,
            material=material,
            secret=secret,
            backend=backend,
            publisher=capture,
        )
        if capture.publish_count != 1 or capture.report != core:
            raise ContractError("shared core report capture failed")
        binding_status = (
            "match"
            if backend.binder.compare_count == 1
            else "mismatch"
            if core.get("abort_class") == AbortClass.SECRET_BOUNDARY.value
            else "not_reached"
        )
    except ReplayAbort as exc:
        abort_class = exc.abort_class.value
    except (ContractError, OSError, ValueError):
        abort_class = (
            AbortClass.SECRET_BOUNDARY.value
            if reached_phase == "SECRET_LOAD_GATE"
            else AbortClass.CONFIG_MISMATCH.value
            if reached_phase == "PROTECTED_INPUT_GATE"
            else AbortClass.PREFLIGHT.value
            if reached_phase == "PREFLIGHT"
            else AbortClass.INTERNAL.value
        )
        if reached_phase == "PE_REFERENCE_GATE":
            binding_status = "reference_failed"
    except BaseException:
        abort_class = AbortClass.INTERNAL.value
    finally:
        if core is None:
            if backend is not None and backend.cleanup_count == 0:
                try:
                    backend.cleanup()
                except ReplayAbort:
                    abort_class = AbortClass.INTERNAL.value
            if secret is not None:
                secret.close()
        report = _candidate_report(
            core,
            preflight_tx=preflight_tx,
            backend=backend,
            reached_phase=reached_phase,
            abort_class=abort_class,
            secret_zeroized=secret is None or secret.is_zeroized,
            target_identity_status=target_status,
            runtime_binding_status=binding_status,
        )
        try:
            checkpoint = dict(report)
            checkpoint["report_publish_count"] = 1
            checkpoint_publisher.publish(checkpoint)
            checkpoint_ok = True
        except (ContractError, OSError):
            report.update(
                result="abort",
                terminal_state="STOP",
                abort_class=AbortClass.INTERNAL.value,
            )
        try:
            preflight_tx.restore()
        except BaseException:
            report.update(
                result="abort",
                terminal_state="STOP",
                abort_class=AbortClass.INTERNAL.value,
            )
        report["fprintd_restore_status"] = preflight_tx.fprintd_restore_status
        report["signal_restore_status"] = preflight_tx.signal_restore_status
        report["report_publish_count"] = int(checkpoint_ok) + 1
        final_publisher.publish(report)
    return report


def run_reviewed_backend_offline(
    *,
    preflight: PreflightSnapshot,
    material: TargetMaterial,
    secret: SecretBuffer,
    backend: ProductionReplayBackend,
    publisher: DurableReportPublisher,
) -> dict[str, object]:
    """Integration seam used only with injected USB in D233 offline tests."""
    return _run_exact_oem_core(
        preflight=preflight, material=material, secret=secret, backend=backend, publisher=publisher
    )


def request_live_mode(*_args: object, **_kwargs: object) -> None:
    raise D233LiveUnavailable("D233 live capability is source-sealed")


def d233_offline_entrypoint(
    argv: Sequence[str] = (),
    environ: Mapping[str, str] | None = None,
    config: Mapping[str, object] | None = None,
    backend_name: str | None = None,
) -> dict[str, object]:
    """Only shipped application entrypoint; never imports material or USB API."""
    env = {} if environ is None else dict(environ)
    if argv or env or config or backend_name is not None:
        request_live_mode()
    return {
        "d233_live_capability": D233_LIVE_CAPABILITY,
        "live_hard_disabled": True,
        "live_runtime_enablement_exists": False,
        "usb_open_count": 0,
    }


if __name__ == "__main__":
    print(json.dumps(d233_offline_entrypoint(), sort_keys=True))
