# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Offline executable-closure tests for the PUBLIC ``PersistentRuntimeCoordinator.run()``.

These tests drive the real public ``run()`` method with synthetic doubles
(scripted transport, scripted event source, fake TLS session) so they are
environment-independent: no OpenSSL-PSK, no libusb, no live hardware.

They prove both terminal boundaries end-to-end, including the ``finally``
cleanup path that the private ``_run_first_image_terminal()`` unit tests do
not reach on their own:

* ``STOP_AFTER_FDT_ARM_ACK`` (default, historical D260/D262): stop after the
  final FDT arm, no IRQ2/0x22/first image.
* ``STOP_AFTER_FIRST_IMAGE`` (opt-in D263): arm -> bounded IRQ2 -> exactly one
  0x22 -> retained-TLS first image -> canonical decode -> host cleanup -> stop.
"""

from __future__ import annotations

import unittest
from unittest import mock

from analysis.D260.d260_offline_rehearsal import (
    _ack,
    _irq100,
    _nav_response,
    _payload_frame,
    synthetic_seed,
)
from core.fdt_lifecycle import FdtLifecycle, FdtLifecycleState
from core.persistent_runtime import (
    PersistentRuntimeCoordinator,
    RuntimeFailure,
    TerminalBoundary,
)
from core.post_d4 import PLAIN, TLS, _checksum
from core.runtime_transport import SubmissionMode
from core.tls_b0 import Tls12PskServerSession, TlsSessionState
from src.goodix5125_cleanroom import encode_synthetic_record


def payload(control: int, data: bytes) -> bytes:
    size = len(data) + 1
    return bytes((control, size & 0xFF, size >> 8)) + data + bytes((_checksum(control, data),))


def outer(kind: int, body: bytes) -> bytes:
    lo, hi = len(body) & 0xFF, len(body) >> 8
    return bytes((kind, lo, hi, (kind + lo + hi) & 0xFF)) + body


class FakeBoundary:
    """Synthetic validated-secret boundary.

    The handoff must occur exactly once. ``handoff()`` therefore starts at
    ``handoff_count = 0`` and performs one real transfer of the secret; a second
    call is detectable and fails the exactly-once invariant, mirroring the
    production boundary used by ``Tls12PskServerSession.from_boundary``.
    """

    def __init__(self, secret: bytes) -> None:
        self._secret = bytearray(secret)
        self.handoff_count = 0
        self.closed = False

    def handoff(self) -> memoryview:
        if self.handoff_count != 0:
            raise RuntimeError("synthetic secret boundary handoff must be exactly-once")
        self.handoff_count += 1
        return memoryview(self._secret)

    def close(self) -> None:
        for index in range(len(self._secret)):
            self._secret[index] = 0
        self.closed = True

    @property
    def zeroized(self) -> bool:
        return not any(self._secret)


class FakeApplicationSession:
    """Synthetic retained TLS application session (decrypt = identity)."""

    handshake_complete = True

    def __init__(self) -> None:
        self.application_record_count = 0
        self.last_plaintext: bytearray | None = None

    def consume_application_record(self, record: bytes) -> bytearray:
        self.application_record_count += 1
        self.last_plaintext = bytearray(record)
        return self.last_plaintext


class FakeTlsSession:
    def __init__(self, app: FakeApplicationSession) -> None:
        self.application_session = app
        self.state = TlsSessionState.APPLICATION_ACTIVE
        self.server_session_object_count = 1
        self.handshake_count = 1
        self.psk_context_provisioning_count = 1
        self.application_record_count = 0
        self.closed = False
        self.handoff_secret = b""

    @property
    def handshake_complete(self) -> bool:
        return True

    def uses_secret_boundary(self, boundary: object) -> bool:
        return True

    def close(self) -> None:
        self.closed = True


def _fake_tls_factory(boundary):
    secret = boundary.handoff()  # exactly one synthetic secret boundary handoff
    session = FakeTlsSession(FakeApplicationSession())
    session.handoff_secret = bytes(secret)
    return session


def irq2(irq: int = 2) -> bytes:
    return outer(PLAIN, payload(0x3F, irq.to_bytes(2, "little") + b"\x00" * 12))


def _stage_words(base: int) -> tuple[int, ...]:
    return tuple(base + 2 * index for index in range(6))


def _build_receive_frames(*, first_image: bool) -> list[bytes]:
    stage0 = _stage_words(0x20)
    stage1 = tuple(value + 1 for value in stage0)
    stage2 = tuple(value + 1 for value in stage1)
    frames = [
        _ack(0xD4),                       # _d4
        _nav_response_off(),              # _af (pov_valid=False)
        _ack(0x36),                       # manual sample stage 0
        _ack(0x50),                       # nav interstage ack
        _nav_response(),                  # nav response
        _ack(0x36),                       # manual sample stage 1
        _ack(0x82),                       # delta interstage ack
        _payload_frame(0x82, bytes((0, 4))),  # delta response (threshold 4)
        _ack(0x20),                       # baseline interstage ack
        outer(TLS, b"\x00" * 7722),       # baseline image B0 (7726 total)
        _ack(0x36),                       # manual sample stage 2
        _ack(0x32),                       # final arm ack
    ]
    if first_image:
        record = encode_synthetic_record((0,) * 5120)
        image_a0 = payload(0x20, b"\x01\x00\x00\x00\x00" + record)
        frames.append(_ack(0x22))            # exactly one 0x22 ACK
        frames.append(outer(TLS, image_a0))  # first image B0
    return frames


def _nav_response_off() -> bytes:
    # AF response with flags=2 -> pov_valid=False (fresh FDT path)
    return _payload_frame(0xAE, bytes((0, 2)) + bytes(14))


def _build_event_frames(*, first_image: bool) -> list[bytes]:
    stage0 = _stage_words(0x20)
    stage1 = tuple(value + 1 for value in stage0)
    stage2 = tuple(value + 1 for value in stage1)
    frames = [_irq100(stage0), _irq100(stage1), _irq100(stage2)]
    if first_image:
        frames.append(irq2(2))
    return frames


class ScriptedTransport:
    def __init__(self, receive_frames, *, record_submissions: bool = False) -> None:
        self._receive = list(receive_frames)
        self._record = record_submissions
        self.submissions: list[tuple[bytes, object]] = []
        self.requests: list[bytes] = []
        self.session_count = 0
        self.cleanup_count = 0
        self.open_count = 0

    def open(self) -> None:
        self.open_count += 1
        self.session_count = 1

    def submit(self, request: bytes, policy) -> None:
        self.requests.append(request)
        if self._record:
            self.submissions.append((request, policy))

    def receive(self, timeout_ms: int) -> bytes:
        if not self._receive:
            raise AssertionError("unexpected_receive")
        return self._receive.pop(0)

    def close(self) -> None:
        if self.cleanup_count:
            return
        self.cleanup_count = 1


class ScriptedEventSource:
    def __init__(self, frames) -> None:
        self._frames = list(frames)
        self.wait_count = 0

    def wait_event(self, timeout_ms: int) -> bytes:
        self.wait_count += 1
        if not self._frames:
            raise TimeoutError("synthetic_event_queue_empty")
        return self._frames.pop(0)


def _make_coordinator(*, operational_physical_policy: bool = False, record_submissions: bool = False):
    # Frames are injected per-test via coord.transport._receive /
    # coord.event_source._frames; record_submissions only toggles capture.
    transport = ScriptedTransport([], record_submissions=record_submissions)
    event_source = ScriptedEventSource([])
    coord = PersistentRuntimeCoordinator(
        transport,
        event_source,
        FakeBoundary(b"secret-32-bytes-xxxxxxxxxxxxxx"),
        operational_physical_policy=operational_physical_policy,
    )
    return coord, transport, event_source


class BackwardCompatArmOnlyTests(unittest.TestCase):
    """Default run() must preserve D260/D262 arm-only semantics."""

    def _run_arm_only(self):
        coord, transport, event_source = _make_coordinator()
        receive = _build_receive_frames(first_image=False)
        event = _build_event_frames(first_image=False)
        coord.transport._receive = receive
        coord.event_source._frames = event
        with mock.patch.object(Tls12PskServerSession, "from_boundary", _fake_tls_factory):
            result = coord.run(seed_result=synthetic_seed(), ts16=0x4242)
        return coord, transport, result

    def test_arm_only_stops_after_arm_no_first_image(self):
        coord, transport, result = self._run_arm_only()
        self.assertEqual(
            list(result.command_trace),
            [0x36, 0x50, 0x36, 0x82, 0x20, 0x36, 0x32],
        )
        self.assertFalse(result.first_image_received)
        self.assertEqual(result.first_image_validation, "NOT_ATTEMPTED")
        self.assertEqual(result.irq2_observed, False)
        self.assertEqual(result.image_command_attempt_count, 0)
        self.assertEqual(coord.lifecycle.state, FdtLifecycleState.FDT_ARMED_WAIT)
        # no 0x22 / first image reached
        self.assertNotIn(0x22, coord.lifecycle.device_command_trace)
        self.assertEqual(coord.state.value, "CLOSED")

    def test_arm_only_cleanup_exactly_once_no_recovery(self):
        coord, transport, result = self._run_arm_only()
        audit = coord.audit()
        self.assertEqual(audit["transport_cleanup_count"], 1)
        self.assertEqual(audit["tls_close_count"], 1)
        self.assertTrue(audit["secret_boundary_zeroized"])
        self.assertEqual(audit["retry_count"], 0)
        self.assertEqual(audit["persistent_device_write_count"], 0)
        self.assertEqual(audit["a2_special_recovery_count"], 0)
        self.assertEqual(audit["0x70_special_recovery_count"], 0)
        self.assertEqual(coord.lifecycle.persistent_write_family_count, 0)

    def test_default_mode_is_arm_only_even_when_operational_true(self):
        coord, transport, event_source = _make_coordinator(operational_physical_policy=True)
        coord.transport._receive = _build_receive_frames(first_image=False)
        coord.event_source._frames = _build_event_frames(first_image=False)
        with mock.patch.object(Tls12PskServerSession, "from_boundary", _fake_tls_factory):
            result = coord.run(seed_result=synthetic_seed(), ts16=0x4242)
        self.assertNotIn(0x22, coord.lifecycle.device_command_trace)
        self.assertFalse(result.first_image_received)


class FirstImageOptInPublicRunTests(unittest.TestCase):
    """Opt-in D263 boundary driven through the public run()."""

    def _run_first_image(self, *, operational_physical_policy: bool = False, malformed: bool = False):
        coord, transport, event_source = _make_coordinator(
            operational_physical_policy=operational_physical_policy, record_submissions=True
        )
        frames = _build_receive_frames(first_image=True)
        if malformed:
            frames[-1] = outer(TLS, b"\x17\x03\x03" + b"\x00" * 20)
        coord.transport._receive = frames
        coord.event_source._frames = _build_event_frames(first_image=True)
        with mock.patch.object(Tls12PskServerSession, "from_boundary", _fake_tls_factory):
            if malformed:
                with self.assertRaises(RuntimeFailure):
                    coord.run(
                        seed_result=synthetic_seed(),
                        ts16=0x4242,
                        terminal_mode=TerminalBoundary.STOP_AFTER_FIRST_IMAGE,
                    )
                return coord, transport, None
            result = coord.run(
                seed_result=synthetic_seed(),
                ts16=0x4242,
                terminal_mode=TerminalBoundary.STOP_AFTER_FIRST_IMAGE,
            )
        return coord, transport, result

    def test_success_path_end_to_end(self):
        coord, transport, result = self._run_first_image()
        self.assertIsNotNone(result)
        # one session / one handshake / one secret handoff
        self.assertEqual(coord.audit()["usb_transport_session_count"], 1)
        self.assertEqual(coord.audit()["tls_server_handshake_count"], 1)
        self.assertEqual(coord.audit()["tls_server_session_object_count"], 1)
        self.assertEqual(coord.audit()["secret_boundary_handoff_count"], 1)
        # exact historical prefix + exactly one 0x22
        trace = list(coord.lifecycle.device_command_trace)
        self.assertEqual(trace[:7], [0x36, 0x50, 0x36, 0x82, 0x20, 0x36, 0x32])
        self.assertEqual(trace[7:], [0x22])
        self.assertEqual(coord.lifecycle.image_command_attempt_count, 1)
        self.assertEqual(result.irq2_observed, True)
        self.assertEqual(result.image_ack, "ACK01_OR_07")
        self.assertTrue(result.first_image_received)
        self.assertEqual(result.first_image_validation, "SUCCESS")
        self.assertEqual(result.first_image_raster_shape, (80, 64))
        self.assertFalse(result.first_image_bytes_persisted)
        self.assertTrue(result.terminal_cleanup_completed)
        self.assertEqual(coord.lifecycle.state, FdtLifecycleState.TERMINAL_STOPPED)
        # no forbidden commands
        for forbidden in (0x34, 0x20, 0xA2, 0x70):
            self.assertNotIn(forbidden, trace[7:])
        # cleanup exactly once
        audit = coord.audit()
        self.assertEqual(audit["transport_cleanup_count"], 1)
        self.assertEqual(audit["tls_close_count"], 1)
        self.assertTrue(audit["secret_boundary_zeroized"])
        self.assertEqual(audit["retry_count"], 0)
        self.assertEqual(audit["persistent_device_write_count"], 0)
        self.assertEqual(audit["a2_special_recovery_count"], 0)
        self.assertEqual(audit["0x70_special_recovery_count"], 0)
        self.assertEqual(coord.state.value, "CLOSED")

    def test_failure_path_fail_closed_cleanup_once(self):
        coord, transport, _ = self._run_first_image(malformed=True)
        self.assertEqual(coord.state.value, "FAILED_CLOSED")
        trace = list(coord.lifecycle.device_command_trace)
        # exactly one 0x22 attempted, no second, no recovery/persistence
        self.assertEqual(trace.count(0x22), 1)
        self.assertEqual(trace.count(0xA2), 0)
        self.assertEqual(trace.count(0x70), 0)
        self.assertNotIn(0x34, trace)
        audit = coord.audit()
        self.assertEqual(audit["transport_cleanup_count"], 1)
        self.assertEqual(audit["tls_close_count"], 1)
        self.assertTrue(audit["secret_boundary_zeroized"])
        self.assertEqual(audit["retry_count"], 0)
        self.assertEqual(audit["persistent_device_write_count"], 0)


class Zero22PolicySelectionTests(unittest.TestCase):
    """0x22 must follow operational_physical_policy, not hard-code abstract."""

    def _policy_mode_for_22(self, operational: bool) -> str:
        coord, transport, event_source = _make_coordinator(
            operational_physical_policy=operational, record_submissions=True
        )
        coord.transport._receive = _build_receive_frames(first_image=True)
        coord.event_source._frames = _build_event_frames(first_image=True)
        with mock.patch.object(Tls12PskServerSession, "from_boundary", _fake_tls_factory):
            coord.run(
                seed_result=synthetic_seed(),
                ts16=0x4242,
                terminal_mode=TerminalBoundary.STOP_AFTER_FIRST_IMAGE,
            )
        for request, policy in transport.submissions:
            if len(request) > 4 and request[4] == 0x22:
                return policy.mode.value
        raise AssertionError("0x22 submission not recorded")

    def test_abstract_when_operational_false(self):
        mode = self._policy_mode_for_22(operational=False)
        self.assertEqual(mode, SubmissionMode.ABSTRACT_LOGICAL_ONLY.value)

    def test_fixed64_when_operational_true(self):
        mode = self._policy_mode_for_22(operational=True)
        self.assertEqual(mode, SubmissionMode.FIXED64_ZERO_TAIL.value)


class SyntheticSecretHandoffExactlyOnceTests(unittest.TestCase):
    """The synthetic secret-boundary handoff must be performed exactly once."""

    def test_factory_performs_exactly_one_real_handoff(self):
        boundary = FakeBoundary(b"secret-32-bytes-xxxxxxxxxxxxxx")
        session = _fake_tls_factory(boundary)
        self.assertEqual(boundary.handoff_count, 1)
        self.assertEqual(session.handoff_secret, b"secret-32-bytes-xxxxxxxxxxxxxx")
        # A second handoff is detectable and must fail the exactly-once invariant.
        with self.assertRaises(RuntimeError):
            boundary.handoff()
        boundary.close()
        self.assertTrue(boundary.zeroized)


class PartialCleanupTests(unittest.TestCase):
    """A cleanup exception must not prevent the remaining host cleanup."""

    def test_tls_close_exception_still_zeroizes_and_closes_transport(self):
        coord, transport, event_source = _make_coordinator(operational_physical_policy=True)
        coord.transport._receive = _build_receive_frames(first_image=True)
        coord.event_source._frames = _build_event_frames(first_image=True)

        def factory(boundary):
            session = _fake_tls_factory(boundary)
            session.close = mock.Mock(side_effect=RuntimeError("synthetic_tls_close_failure"))
            return session

        with mock.patch.object(Tls12PskServerSession, "from_boundary", factory):
            with self.assertRaisesRegex(RuntimeFailure, "host_cleanup_incomplete"):
                coord.run(
                    seed_result=synthetic_seed(), ts16=0x4242,
                    terminal_mode=TerminalBoundary.STOP_AFTER_FIRST_IMAGE,
                )
        self.assertEqual(transport.cleanup_count, 1)
        self.assertTrue(coord.secret_boundary.zeroized)
        self.assertEqual(len(coord.audit()["cleanup_failures"]), 1)
        self.assertEqual(coord.state.value, "FAILED_CLOSED")


if __name__ == "__main__":
    unittest.main()
