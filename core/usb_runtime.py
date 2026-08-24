# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Production-shaped libusb adapter with one physical IN owner.

The module performs no USB work at import or construction time.  The concrete
ctypes backend initializes libusb only from ``open_exact``.  Tests inject a
fake backend; no detach, reset, reopen, retry, control recovery or wildcard
selection API exists.
"""

from __future__ import annotations

import ctypes
import ctypes.util
from dataclasses import dataclass
import math
import threading
import time
from typing import Callable, Protocol

from core.post_d4 import PLAIN, parse_outer, parse_payload
from core.protected_runtime import LiveIoCapability, require_live_io_capability
from core.runtime_transport import EventSource, PhysicalSubmissionPolicy


TARGET_VID = 0x27C6
TARGET_PID = 0x5125
INTERFACE = 0
EP_OUT = 0x01
EP_IN = 0x81
MAX_IN_COMPLETION = 16_384
MAX_LOGICAL_FRAME = 16_384
MAX_QUEUED_FRAMES = 64


class UsbRuntimeFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class UsbIdentity:
    vid: int
    pid: int
    bus: int
    address: int
    port_path: tuple[int, ...]


class UsbBackend(Protocol):
    open_count: int
    claim_count: int
    release_count: int
    close_count: int

    def open_exact(self, vid: int, pid: int, interface: int) -> UsbIdentity:
        ...

    def revalidate_identity(self) -> UsbIdentity:
        ...

    def bulk_out(self, endpoint: int, data: bytes, timeout_ms: int) -> int:
        ...

    def bulk_in(self, endpoint: int, maximum: int, timeout_ms: int) -> bytes:
        ...

    def close(self) -> None:
        ...


def _is_irq100(frame: bytes) -> bool:
    try:
        kind, payload = parse_outer(frame)
        control, data = parse_payload(payload)
    except Exception:
        return False
    return kind == PLAIN and control == 0x36 and len(data) >= 2 and data[:2] == b"\x00\x01"


class SharedFrameRouter:
    """Own the only physical EP81 read path and expose two queue views."""

    def __init__(
        self,
        backend: UsbBackend,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.backend = backend
        self._monotonic = monotonic
        self._partial = bytearray()
        self._frames: list[bytes] = []
        self._read_lock = threading.Lock()
        self.physical_in_read_count = 0
        self.command_delivery_count = 0
        self.event_delivery_count = 0
        self.max_queue_depth = 0

    def _split(self, completion: bytes) -> None:
        if not completion:
            raise TimeoutError("empty_usb_completion")
        self._partial.extend(completion)
        while self._partial:
            if self._partial[0] == 0 and not any(self._partial):
                self._partial.clear()
                break
            if len(self._partial) < 4:
                break
            if self._partial[0] not in (0xA0, 0xB0):
                raise UsbRuntimeFailure(f"unexpected_in_prefix:0x{self._partial[0]:02x}")
            length = 4 + int.from_bytes(self._partial[1:3], "little")
            if length < 4 or length > MAX_LOGICAL_FRAME:
                raise UsbRuntimeFailure(f"in_frame_length_invalid:{length}")
            if len(self._partial) < length:
                break
            frame = bytes(self._partial[:length])
            del self._partial[:length]
            parse_outer(frame)
            self._frames.append(frame)
            if len(self._frames) > MAX_QUEUED_FRAMES:
                raise UsbRuntimeFailure("shared_frame_queue_bound")
            self.max_queue_depth = max(self.max_queue_depth, len(self._frames))

    def _read_once(self, timeout_ms: int) -> None:
        if not self._read_lock.acquire(blocking=False):
            raise UsbRuntimeFailure("concurrent_physical_in_reader_forbidden")
        try:
            completion = self.backend.bulk_in(EP_IN, MAX_IN_COMPLETION, timeout_ms)
            self.physical_in_read_count += 1
            self._split(completion)
        finally:
            self._read_lock.release()

    def _pop(self, *, event: bool, timeout_ms: int) -> bytes:
        if timeout_ms <= 0:
            raise TimeoutError("shared_reader_phase_deadline_expired")
        deadline = self._monotonic() + timeout_ms / 1000.0
        while True:
            for index, frame in enumerate(self._frames):
                if _is_irq100(frame) is event:
                    selected = self._frames.pop(index)
                    if event:
                        self.event_delivery_count += 1
                    else:
                        self.command_delivery_count += 1
                    return selected
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise TimeoutError("shared_reader_phase_deadline_expired")
            self._read_once(max(1, math.ceil(remaining * 1000.0)))

    def receive_command(self, timeout_ms: int) -> bytes:
        return self._pop(event=False, timeout_ms=timeout_ms)

    def receive_event(self, timeout_ms: int) -> bytes:
        return self._pop(event=True, timeout_ms=timeout_ms)

    def assert_no_buffered_frames(self) -> None:
        if self._frames or self._partial:
            raise UsbRuntimeFailure("unexpected_extra_frame_after_terminal_ack")

    @property
    def queued_frame_count(self) -> int:
        return len(self._frames) + int(bool(self._partial))


class _RouterEventSource(EventSource):
    def __init__(self, router: SharedFrameRouter) -> None:
        self.router = router

    def wait_event(self, timeout_ms: int) -> bytes:
        return self.router.receive_event(timeout_ms)


class LibusbRuntimeTransport:
    """RuntimeTransport implementation over a dependency-injected backend."""

    def __init__(
        self,
        backend: UsbBackend,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.backend = backend
        self._sleeper = sleeper
        self.router = SharedFrameRouter(backend, monotonic=monotonic)
        self.event_source = _RouterEventSource(self.router)
        self.session_count = 0
        self.cleanup_count = 0
        self.submission_count = 0
        self.physical_chunk_count = 0
        self.identity: UsbIdentity | None = None
        self._opened = False

    def open(self) -> None:
        if self._opened or self.session_count:
            raise UsbRuntimeFailure("usb_reopen_forbidden")
        identity = self.backend.open_exact(TARGET_VID, TARGET_PID, INTERFACE)
        if (identity.vid, identity.pid) != (TARGET_VID, TARGET_PID):
            raise UsbRuntimeFailure("usb_exact_target_selection_failed")
        self.identity = identity
        self._opened = True
        self.session_count = 1
        self._revalidate()

    def _revalidate(self) -> None:
        if self.identity is None or self.backend.revalidate_identity() != self.identity:
            raise UsbRuntimeFailure("usb_identity_changed_after_open")

    def submit(self, logical_frame: bytes, policy: PhysicalSubmissionPolicy) -> None:
        if not self._opened:
            raise UsbRuntimeFailure("usb_submit_before_open")
        self._revalidate()
        chunks = policy.materialize(logical_frame)
        if policy.pre_submit_pacing_ms:
            self._sleeper(policy.pre_submit_pacing_ms / 1000.0)
        for chunk in chunks:
            completed = self.backend.bulk_out(EP_OUT, chunk, policy.timeout_ms)
            if completed != len(chunk):
                raise UsbRuntimeFailure(f"usb_short_or_ambiguous_out:{completed}:{len(chunk)}")
            self.physical_chunk_count += 1
            if policy.post_submit_pacing_ms:
                self._sleeper(policy.post_submit_pacing_ms / 1000.0)
        self.submission_count += 1
        self._revalidate()

    def receive(self, timeout_ms: int) -> bytes:
        if not self._opened:
            raise UsbRuntimeFailure("usb_receive_before_open")
        return self.router.receive_command(timeout_ms)

    def assert_no_buffered_frames(self) -> None:
        self.router.assert_no_buffered_frames()

    def close(self) -> None:
        if self.cleanup_count:
            return
        self.backend.close()
        self.cleanup_count = 1
        self._opened = False


class _DeviceDescriptor(ctypes.Structure):
    _fields_ = [
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
    ]


class CtypesLibusbBackend:
    """Minimal public-libusb binding; every operation is explicit and one-shot."""

    def __init__(
        self,
        live_io_capability: LiveIoCapability | None = None,
        library_name: str | None = None,
        *,
        capability_validator=require_live_io_capability,
    ) -> None:
        self.live_io_capability = live_io_capability
        self.library_name = library_name
        self._capability_validator = capability_validator
        self.open_count = 0
        self.claim_count = 0
        self.release_count = 0
        self.close_count = 0
        self._lib = None
        self._context = ctypes.c_void_p()
        self._handle = ctypes.c_void_p()
        self._device = ctypes.c_void_p()
        self._identity: UsbIdentity | None = None

    def _load(self):
        if self._lib is not None:
            return self._lib
        name = self.library_name or ctypes.util.find_library("usb-1.0")
        if not name:
            raise UsbRuntimeFailure("libusb_1_0_unavailable")
        lib = ctypes.CDLL(name)
        lib.libusb_init.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        lib.libusb_init.restype = ctypes.c_int
        lib.libusb_exit.argtypes = [ctypes.c_void_p]
        lib.libusb_get_device_list.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))]
        lib.libusb_get_device_list.restype = ctypes.c_ssize_t
        lib.libusb_free_device_list.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int]
        lib.libusb_get_device_descriptor.argtypes = [ctypes.c_void_p, ctypes.POINTER(_DeviceDescriptor)]
        lib.libusb_get_device_descriptor.restype = ctypes.c_int
        lib.libusb_get_bus_number.argtypes = [ctypes.c_void_p]
        lib.libusb_get_bus_number.restype = ctypes.c_uint8
        lib.libusb_get_device_address.argtypes = [ctypes.c_void_p]
        lib.libusb_get_device_address.restype = ctypes.c_uint8
        lib.libusb_get_port_numbers.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint8), ctypes.c_int]
        lib.libusb_get_port_numbers.restype = ctypes.c_int
        lib.libusb_ref_device.argtypes = [ctypes.c_void_p]
        lib.libusb_ref_device.restype = ctypes.c_void_p
        lib.libusb_unref_device.argtypes = [ctypes.c_void_p]
        lib.libusb_open.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        lib.libusb_open.restype = ctypes.c_int
        lib.libusb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.libusb_claim_interface.restype = ctypes.c_int
        lib.libusb_release_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.libusb_release_interface.restype = ctypes.c_int
        lib.libusb_close.argtypes = [ctypes.c_void_p]
        lib.libusb_get_device.argtypes = [ctypes.c_void_p]
        lib.libusb_get_device.restype = ctypes.c_void_p
        lib.libusb_bulk_transfer.argtypes = [ctypes.c_void_p, ctypes.c_ubyte, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.c_uint]
        lib.libusb_bulk_transfer.restype = ctypes.c_int
        self._lib = lib
        return lib

    def _identity_of(self, device: ctypes.c_void_p) -> UsbIdentity:
        lib = self._load()
        descriptor = _DeviceDescriptor()
        if lib.libusb_get_device_descriptor(device, ctypes.byref(descriptor)) != 0:
            raise UsbRuntimeFailure("libusb_descriptor_failed")
        ports = (ctypes.c_uint8 * 8)()
        count = lib.libusb_get_port_numbers(device, ports, len(ports))
        if count < 0:
            raise UsbRuntimeFailure("libusb_port_path_failed")
        return UsbIdentity(
            descriptor.idVendor,
            descriptor.idProduct,
            lib.libusb_get_bus_number(device),
            lib.libusb_get_device_address(device),
            tuple(int(ports[index]) for index in range(count)),
        )

    def open_exact(self, vid: int, pid: int, interface: int) -> UsbIdentity:
        self._capability_validator(self.live_io_capability)
        if self.open_count or self._lib is not None:
            raise UsbRuntimeFailure("libusb_open_exactly_once")
        lib = self._load()
        if lib.libusb_init(ctypes.byref(self._context)) != 0:
            raise UsbRuntimeFailure("libusb_init_failed")
        device_list = ctypes.POINTER(ctypes.c_void_p)()
        count = lib.libusb_get_device_list(self._context, ctypes.byref(device_list))
        if count < 0:
            self.close()
            raise UsbRuntimeFailure("libusb_device_list_failed")
        matches: list[ctypes.c_void_p] = []
        try:
            for index in range(count):
                device = device_list[index]
                identity = self._identity_of(device)
                if (identity.vid, identity.pid) == (vid, pid):
                    matches.append(ctypes.c_void_p(lib.libusb_ref_device(device)))
        finally:
            lib.libusb_free_device_list(device_list, 1)
        if len(matches) != 1:
            for device in matches:
                lib.libusb_unref_device(device)
            self.close()
            raise UsbRuntimeFailure(f"exact_target_cardinality:{len(matches)}")
        self._device = matches[0]
        self._identity = self._identity_of(self._device)
        if lib.libusb_open(self._device, ctypes.byref(self._handle)) != 0:
            self.close()
            raise UsbRuntimeFailure("libusb_open_failed")
        self.open_count = 1
        if lib.libusb_claim_interface(self._handle, interface) != 0:
            self.close()
            raise UsbRuntimeFailure("libusb_claim_interface_failed")
        self.claim_count = 1
        return self._identity

    def revalidate_identity(self) -> UsbIdentity:
        if not self._handle or self._identity is None:
            raise UsbRuntimeFailure("libusb_revalidate_without_open")
        current = ctypes.c_void_p(self._load().libusb_get_device(self._handle))
        return self._identity_of(current)

    def _bulk(self, endpoint: int, data: bytes | None, maximum: int, timeout_ms: int) -> tuple[int, bytes]:
        if not self._handle:
            raise UsbRuntimeFailure("libusb_bulk_without_open")
        size = len(data) if data is not None else maximum
        buffer = (ctypes.c_ubyte * size)()
        if data is not None:
            buffer[:] = data
        transferred = ctypes.c_int()
        status = self._load().libusb_bulk_transfer(
            self._handle, endpoint, buffer, size, ctypes.byref(transferred), timeout_ms
        )
        if status != 0:
            if status == -7:
                raise TimeoutError(f"libusb_bulk_timeout:0x{endpoint:02x}")
            raise UsbRuntimeFailure(f"libusb_bulk_failed:0x{endpoint:02x}:{status}")
        return transferred.value, bytes(buffer[:transferred.value])

    def bulk_out(self, endpoint: int, data: bytes, timeout_ms: int) -> int:
        return self._bulk(endpoint, bytes(data), 0, timeout_ms)[0]

    def bulk_in(self, endpoint: int, maximum: int, timeout_ms: int) -> bytes:
        return self._bulk(endpoint, None, maximum, timeout_ms)[1]

    def close(self) -> None:
        if self.close_count:
            return
        lib = self._lib
        if lib is not None:
            if self.claim_count and self._handle:
                lib.libusb_release_interface(self._handle, INTERFACE)
                self.release_count = 1
            if self._handle:
                lib.libusb_close(self._handle)
                self._handle = ctypes.c_void_p()
            if self._device:
                lib.libusb_unref_device(self._device)
                self._device = ctypes.c_void_p()
            if self._context:
                lib.libusb_exit(self._context)
                self._context = ctypes.c_void_p()
        self.close_count = 1
