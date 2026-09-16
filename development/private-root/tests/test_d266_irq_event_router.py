# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Offline concrete-router regression closure for D266/01."""

from __future__ import annotations

import unittest

from core.fdt_lifecycle import FdtLifecycle, FdtLifecycleState
from core.persistent_runtime import PersistentRuntimeCoordinator
from core.post_d4 import PLAIN, TLS, _checksum, parse_outer, parse_payload
from core.usb_runtime import SharedFrameRouter, UsbRuntimeFailure, _RouterEventSource
from src.goodix5125_cleanroom import encode_synthetic_record


def _payload(control: int, data: bytes) -> bytes:
    size = len(data) + 1
    return bytes((control, size & 0xFF, size >> 8)) + data + bytes((_checksum(control, data),))


def _outer(kind: int, body: bytes) -> bytes:
    lo, hi = len(body) & 0xFF, len(body) >> 8
    return bytes((kind, lo, hi, (kind + lo + hi) & 0xFF)) + body


def _a0(control: int, data: bytes) -> bytes:
    return _outer(PLAIN, _payload(control, data))


def _ack(echo: int) -> bytes:
    return _a0(0xB0, bytes((echo, 1)))


def _event(control: int, irq: int) -> bytes:
    return _a0(control, irq.to_bytes(2, "little") + bytes(14))


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class _BulkInFixture:
    """Synthetic bulk-IN only; it cannot open a real USB device."""

    def __init__(
        self,
        completions: list[bytes],
        *,
        clock: _Clock | None = None,
        advance: float = 0.0,
    ) -> None:
        self.completions = list(completions)
        self.clock = clock
        self.advance = advance
        self.timeout_arguments: list[int] = []
        self.bulk_in_call_count = 0
        self.router: SharedFrameRouter | None = None
        self.reentrant = False

    def bulk_in(self, endpoint: int, maximum: int, timeout_ms: int) -> bytes:
        self.bulk_in_call_count += 1
        self.timeout_arguments.append(timeout_ms)
        if self.reentrant and self.router is not None:
            self.router.receive_command(timeout_ms)
        if self.clock is not None:
            self.clock.value += self.advance
        if not self.completions:
            raise TimeoutError("synthetic_bulk_in_timeout")
        return self.completions.pop(0)


class SharedFrameRouterClassificationTests(unittest.TestCase):
    def test_irq100_and_irq2_are_delivered_once_as_events(self) -> None:
        irq100 = _event(0x36, 0x100)
        irq2 = _event(0x32, 2)
        router = SharedFrameRouter(_BulkInFixture([irq100 + irq2]))

        self.assertEqual(router.receive_event(100), irq100)
        self.assertEqual(router.receive_event(100), irq2)
        self.assertEqual(router.event_delivery_count, 2)
        self.assertEqual(router.command_delivery_count, 0)
        self.assertEqual(router.queued_frame_count, 0)

    def test_irq2_is_not_delivered_to_command_view(self) -> None:
        irq2 = _event(0x32, 2)
        ack = _ack(0x32)
        router = SharedFrameRouter(_BulkInFixture([irq2 + ack]))

        self.assertEqual(router.receive_command(100), ack)
        self.assertEqual(router.receive_event(100), irq2)
        self.assertEqual(router.queued_frame_count, 0)

    def test_ack_response_and_non_event_a0_remain_command_side(self) -> None:
        ack = _ack(0x50)
        response = _a0(0x50, b"\x50\x01" + bytes(8))
        unsupported_parser_irq = _event(0x3F, 0x80)
        irq2 = _event(0x32, 2)
        router = SharedFrameRouter(_BulkInFixture([
            ack + response + unsupported_parser_irq + irq2
        ]))

        self.assertEqual(router.receive_event(100), irq2)
        self.assertEqual(router.receive_command(100), ack)
        self.assertEqual(router.receive_command(100), response)
        self.assertEqual(router.receive_command(100), unsupported_parser_irq)
        self.assertEqual(router.event_delivery_count, 1)
        self.assertEqual(router.command_delivery_count, 3)
        self.assertEqual(router.queued_frame_count, 0)

    def test_required_interleavings_preserve_each_view_order(self) -> None:
        ack1 = _ack(0x36)
        response = _a0(0xAE, bytes(16))
        ack2 = _ack(0x32)
        irq100 = _event(0x36, 0x100)
        irq2 = _event(0x32, 2)
        irq200 = _event(0x34, 0x200)
        cases = (
            ("command_event", ack1 + irq2, ("command", "event"), (ack1, irq2)),
            ("event_command", irq2 + ack1, ("event", "command"), (irq2, ack1)),
            (
                "command_irq2_command",
                ack1 + irq2 + response,
                ("command", "event", "command"),
                (ack1, irq2, response),
            ),
            (
                "irq100_command_irq2",
                irq100 + ack2 + irq2 + irq200,
                ("event", "command", "event", "event"),
                (irq100, ack2, irq2, irq200),
            ),
        )
        for name, completion, views, expected in cases:
            with self.subTest(name=name):
                router = SharedFrameRouter(_BulkInFixture([completion]))
                actual = []
                for view in views:
                    receive = router.receive_event if view == "event" else router.receive_command
                    actual.append(receive(100))
                self.assertEqual(tuple(actual), expected)
                self.assertEqual(router.queued_frame_count, 0)
                self.assertEqual(router.physical_in_read_count, 1)

    def test_absolute_deadline_is_not_renewed_by_other_view_frames(self) -> None:
        clock = _Clock()
        backend = _BulkInFixture(
            [_event(0x36, 0x100), _event(0x32, 2), _event(0x34, 0x200)],
            clock=clock,
            advance=0.04,
        )
        router = SharedFrameRouter(backend, monotonic=clock)

        with self.assertRaisesRegex(TimeoutError, "shared_reader_phase_deadline_expired"):
            router.receive_command(100)
        self.assertEqual(backend.timeout_arguments[0], 100)
        self.assertTrue(all(b < a for a, b in zip(
            backend.timeout_arguments, backend.timeout_arguments[1:]
        )))
        self.assertGreaterEqual(clock.value, 0.1)

    def test_concurrent_physical_in_reader_remains_forbidden(self) -> None:
        backend = _BulkInFixture([_ack(0x36)])
        backend.reentrant = True
        router = SharedFrameRouter(backend)
        backend.router = router

        with self.assertRaisesRegex(
            UsbRuntimeFailure, "concurrent_physical_in_reader_forbidden"
        ):
            router.receive_command(100)


class _CommandTransport:
    def __init__(self, frames: list[bytes]) -> None:
        self.frames = list(frames)
        self.requests: list[bytes] = []

    def submit(self, request: bytes, policy: object) -> None:
        self.requests.append(request)

    def receive(self, timeout_ms: int) -> bytes:
        if not self.frames:
            raise TimeoutError("synthetic_command_timeout")
        return self.frames.pop(0)


class _Boundary:
    handoff_count = 1

    def close(self) -> None:
        pass

    @property
    def zeroized(self) -> bool:
        return True


class _ApplicationSession:
    handshake_complete = True

    def consume_application_record(self, record: bytes) -> bytearray:
        return bytearray(record)


class _TlsSession:
    def __init__(self) -> None:
        self.application_session = _ApplicationSession()


def _armed_lifecycle() -> FdtLifecycle:
    lifecycle = FdtLifecycle()
    lifecycle.observe_af_state(False)
    lifecycle.begin_bootstrap()
    for stage in range(3):
        lifecycle.manual_sample_attempt(stage)
        lifecycle.manual_sample_completed(stage)
    lifecycle.bootstrap_completed()
    lifecycle.arm_fdt()
    return lifecycle


def _first_image_b0() -> bytes:
    record = encode_synthetic_record((0,) * 5120)
    image = _payload(0x20, b"\x01\x00\x00\x00\x00" + record)
    return _outer(TLS, image)


class ConcreteRouterFirstImageSeamTests(unittest.TestCase):
    def _coordinator(
        self, backend: _BulkInFixture, command_frames: list[bytes]
    ) -> tuple[PersistentRuntimeCoordinator, _CommandTransport, SharedFrameRouter]:
        router = SharedFrameRouter(backend)
        transport = _CommandTransport(command_frames)
        coordinator = PersistentRuntimeCoordinator(
            transport, _RouterEventSource(router), _Boundary()
        )
        coordinator.tls_session = _TlsSession()
        coordinator.lifecycle = _armed_lifecycle()
        return coordinator, transport, router

    def test_synthetic_bulk_in_irq2_reaches_exactly_one_0x22_attempt(self) -> None:
        backend = _BulkInFixture([_event(0x32, 2)])
        coordinator, transport, router = self._coordinator(
            backend, [_ack(0x22), _first_image_b0()]
        )

        result = coordinator._run_first_image_terminal()

        self.assertEqual(result["image_command_attempt_count"], 1)
        self.assertEqual(result["first_image_validation"], "SUCCESS")
        self.assertEqual(coordinator.lifecycle.state, FdtLifecycleState.TERMINAL_STOPPED)
        self.assertEqual(len(transport.requests), 1)
        kind, payload = parse_outer(transport.requests[0])
        control, data = parse_payload(payload)
        self.assertEqual((kind, control, data), (PLAIN, 0x22, b"\x01\x00"))
        self.assertEqual(router.event_delivery_count, 1)
        self.assertEqual(router.command_delivery_count, 0)
        self.assertEqual(router.queued_frame_count, 0)
        self.assertEqual(coordinator.retry_count, 0)
        self.assertEqual(coordinator.lifecycle.persistent_write_family_count, 0)

    def test_no_irq2_times_out_before_any_0x22_attempt(self) -> None:
        backend = _BulkInFixture([])
        coordinator, transport, router = self._coordinator(backend, [])

        with self.assertRaisesRegex(TimeoutError, "synthetic_bulk_in_timeout"):
            coordinator._run_first_image_terminal()

        self.assertEqual(transport.requests, [])
        self.assertEqual(coordinator.lifecycle.image_command_attempt_count, 0)
        self.assertEqual(coordinator.retry_count, 0)
        self.assertEqual(coordinator.lifecycle.persistent_write_family_count, 0)
        self.assertEqual(router.event_delivery_count, 0)
        self.assertEqual(router.queued_frame_count, 0)


if __name__ == "__main__":
    unittest.main()
