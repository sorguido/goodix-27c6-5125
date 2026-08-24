# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Offline integration tests for D263/06 PersistentRuntime first-image path.

Uses SYNTHETIC TLS and synthetic transports (no OpenSSL PSK, no USB, no live).
The production code path (IRQ2 -> one 0x22 -> retained TLS first B0 ->
canonical codec -> FIRST_IMAGE_RECEIVED -> host/TLS/USB cleanup -> stop) is
exercised end-to-end; the synthetic TLS adapter is a stand-in for the real
Tls12PskServerSession validated by test_d259 in an OpenSSL-PSK environment.
"""

from __future__ import annotations

import unittest

from core.fdt_lifecycle import FdtLifecycle, FdtLifecycleState, InvalidTransition
from core.persistent_runtime import (
    FIRST_IMAGE_IRQ2_TIMEOUT_MS,
    PersistentRuntimeCoordinator,
    RuntimeFailure,
)
from core.post_d4 import PLAIN, TLS, _checksum
from src.goodix5125_cleanroom import encode_synthetic_record


def payload(control: int, data: bytes) -> bytes:
    size = len(data) + 1
    return bytes((control, size & 0xFF, size >> 8)) + data + bytes((_checksum(control, data),))


def outer(kind: int, body: bytes) -> bytes:
    lo, hi = len(body) & 0xFF, len(body) >> 8
    return bytes((kind, lo, hi, (kind + lo + hi) & 0xFF)) + body


def ack(echo: int) -> bytes:
    return outer(PLAIN, payload(0xB0, bytes((echo, 1))))


def irq2(irq: int = 2) -> bytes:
    return outer(PLAIN, payload(0x3F, irq.to_bytes(2, "little") + b"\x00" * 12))


class FakeBoundary:
    handoff_count = 1

    def __init__(self, secret: bytes) -> None:
        self._secret = secret
        self.closed = False

    def handoff(self) -> memoryview:
        return memoryview(bytearray(self._secret))

    def close(self) -> None:
        self.closed = True

    @property
    def zeroized(self) -> bool:
        return self.closed


class FakeApplicationSession:
    """Synthetic retained TLS application session (decrypt = identity)."""

    handshake_complete = True

    def __init__(self) -> None:
        self.application_record_count = 0
        self.last_plaintext: bytearray | None = None

    def consume_application_record(self, record: bytes) -> bytearray:
        # synthetic decryption: the "encrypted" body is the plaintext itself
        self.application_record_count += 1
        self.last_plaintext = bytearray(record)
        return self.last_plaintext


class FakeTlsSession:
    def __init__(self, app: FakeApplicationSession) -> None:
        self.application_session = app
        self.server_session_object_count = 1
        self.handshake_count = 1
        self.psk_context_provisioning_count = 1
        self.closed = False
        self.secret_zeroized = False

    def close(self) -> None:
        self.closed = True
        self.secret_zeroized = True


class ScriptedTransport:
    def __init__(self, receive_frames):
        self._receive = list(receive_frames)
        self.requests: list[bytes] = []
        self.open_count = 0

    def open(self) -> None:
        self.open_count += 1

    def submit(self, request: bytes, policy) -> None:
        self.requests.append(request)

    def receive(self, timeout_ms: int) -> bytes:
        if not self._receive:
            raise AssertionError("unexpected_receive")
        return self._receive.pop(0)

    def close(self) -> None:
        pass


class ScriptedEventSource:
    def __init__(self, frame=None, raises=None):
        self._frame = frame
        self._raises = raises

    def wait_event(self, timeout_ms: int) -> bytes:
        if self._raises is not None:
            raise self._raises
        return self._frame


def _armed_lifecycle() -> FdtLifecycle:
    lc = FdtLifecycle()
    lc.observe_af_state(False)
    lc.begin_bootstrap()
    for stage in range(3):
        lc.manual_sample_attempt(stage)
        lc.manual_sample_completed(stage)
    lc.bootstrap_completed()
    lc.arm_fdt()
    return lc


def _build_coordinator(lc, transport, event_source) -> PersistentRuntimeCoordinator:
    app = FakeApplicationSession()
    coord = PersistentRuntimeCoordinator(transport, event_source, FakeBoundary(b"secret-32-bytes-xxxxxxxxxxxxxx"))
    coord.tls_session = FakeTlsSession(app)
    coord.lifecycle = lc
    coord._fake_app = app
    return coord


class FirstImageTerminalTests(unittest.TestCase):
    def test_irq2_deadline_covers_primary_trace_delta(self) -> None:
        # D264: APP12509 primary trace ACK32 -> IRQ2 = 7.108212 s.
        self.assertEqual(FIRST_IMAGE_IRQ2_TIMEOUT_MS, 15_000)
        self.assertGreater(FIRST_IMAGE_IRQ2_TIMEOUT_MS, 7_108.212)

    def _image_b0(self, image_a0: bytes) -> bytes:
        return outer(TLS, image_a0)

    def test_happy_path_decode_and_terminal_stop(self) -> None:
        lc = _armed_lifecycle()
        record = encode_synthetic_record((0,) * 5120)
        image_payload = payload(0x20, b"\x01\x00\x00\x00\x00" + record)
        transport = ScriptedTransport([ack(0x22), outer(TLS, image_payload)])
        coord = _build_coordinator(lc, transport, ScriptedEventSource(irq2()))

        result = coord._run_first_image_terminal()

        self.assertEqual(result["first_image_validation"], "SUCCESS")
        self.assertEqual(result["first_image_raster_shape"], (80, 64))
        self.assertEqual(result["terminal_cleanup_completed"], True)
        self.assertEqual(result["image_command_attempt_count"], 1)
        self.assertEqual(lc.state, FdtLifecycleState.TERMINAL_STOPPED)
        self.assertEqual(lc.device_command_trace[-2:], (0x32, 0x22))
        self.assertEqual(lc.device_command_trace.count(0x36), 3)
        for forbidden in (0x34, 0x20, 0xA2, 0x70):
            self.assertNotIn(forbidden, lc.device_command_trace)
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(transport.requests[0][4], 0x22)
        # one retained session/one application record (no reopen, no 2nd session)
        self.assertEqual(coord._fake_app.application_record_count, 1)
        self.assertEqual(coord.tls_session.server_session_object_count, 1)
        self.assertEqual(coord.tls_session.handshake_count, 1)
        self.assertEqual(coord.tls_session.psk_context_provisioning_count, 1)
        self.assertFalse(result["first_image_bytes_persisted"])

    def test_wrong_irq_fails_closed(self) -> None:
        lc = _armed_lifecycle()
        transport = ScriptedTransport([ack(0x22), ack(0x22)])
        coord = _build_coordinator(lc, transport, ScriptedEventSource(irq2(0x100)))
        with self.assertRaises(RuntimeFailure):
            coord._run_first_image_terminal()
        self.assertNotEqual(lc.state, FdtLifecycleState.TERMINAL_STOPPED)

    def test_event_timeout_fails_closed(self) -> None:
        lc = _armed_lifecycle()
        transport = ScriptedTransport([])
        coord = _build_coordinator(lc, transport, ScriptedEventSource(raises=TimeoutError("irq2 timeout")))
        with self.assertRaises(Exception):
            coord._run_first_image_terminal()

    def test_wrong_ack_fails_closed(self) -> None:
        lc = _armed_lifecycle()
        transport = ScriptedTransport([ack(0x20), ack(0x22)])
        coord = _build_coordinator(lc, transport, ScriptedEventSource(irq2()))
        with self.assertRaises(RuntimeFailure):
            coord._run_first_image_terminal()

    def test_malformed_b0_fails_closed(self) -> None:
        lc = _armed_lifecycle()
        transport = ScriptedTransport([ack(0x22), outer(TLS, b"\x17\x03\x03" + b"\x00" * 20)])
        coord = _build_coordinator(lc, transport, ScriptedEventSource(irq2()))
        with self.assertRaises(RuntimeFailure):
            coord._run_first_image_terminal()

    def test_crc_image_failure_wipes_and_fails_closed(self) -> None:
        lc = _armed_lifecycle()
        bad_payload = payload(0x20, b"\x01\x00\x00\x00\x00" + b"\x00" * 7684)
        transport = ScriptedTransport([ack(0x22), outer(TLS, bad_payload)])
        coord = _build_coordinator(lc, transport, ScriptedEventSource(irq2()))
        with self.assertRaises(RuntimeFailure):
            coord._run_first_image_terminal()
        # plaintext wiped even on decode failure
        self.assertFalse(any(coord._fake_app.last_plaintext or b""))

    def test_second_command_prevention(self) -> None:
        lc = _armed_lifecycle()
        record = encode_synthetic_record((0,) * 5120)
        image_payload = payload(0x20, b"\x01\x00\x00\x00\x00" + record)
        transport = ScriptedTransport([ack(0x22), outer(TLS, image_payload)])
        coord = _build_coordinator(lc, transport, ScriptedEventSource(irq2()))
        coord._run_first_image_terminal()
        # a second post-arm attempt must be rejected (one-shot 0x22 / no re-arm)
        with self.assertRaises(Exception):
            coord._run_first_image_terminal()
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(lc.state, FdtLifecycleState.FAILED_CLOSED)

    def test_no_sensitive_pixels_persisted(self) -> None:
        lc = _armed_lifecycle()
        transport = ScriptedTransport([ack(0x22), ack(0x22)])
        coord = _build_coordinator(lc, transport, ScriptedEventSource(irq2()))
        with self.assertRaises(RuntimeFailure):
            coord._run_first_image_terminal()
        self.assertFalse(any(coord._fake_app.last_plaintext or b""))


if __name__ == "__main__":
    unittest.main()
