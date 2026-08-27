# SPDX-License-Identifier: GPL-2.0-or-later
"""D275 production-coordinator offline bridge through the second image."""

import unittest
from unittest import mock

from analysis.D260.d260_offline_rehearsal import _ack, _nav_response, synthetic_seed
from core.persistent_runtime import PersistentRuntimeCoordinator, TerminalBoundary
from core.post_d4 import PLAIN, TLS
from core.tls_b0 import Tls12PskServerSession
from src.goodix5125_cleanroom import encode_synthetic_record
from tests.test_d263_phase2_public_run import (
    _build_event_frames,
    _build_receive_frames,
    _fake_tls_factory,
    _make_coordinator,
    outer,
    payload,
)


def event(irq: int, table: bytes) -> bytes:
    return outer(PLAIN, payload(0x3F, irq.to_bytes(2, "little") + b"\0\0" + table))


def image_b0() -> bytes:
    record = encode_synthetic_record((0,) * 5120)
    return outer(TLS, payload(0x20, b"\x01\0\0\0\0" + record))


class D275ProductionMultiframeTests(unittest.TestCase):
    def run_path(self, mutate=None):
        coord, transport, events = _make_coordinator(record_submissions=True)
        frames = _build_receive_frames(first_image=True)
        frames.extend([
            _ack(0x34), _ack(0x20), image_b0(), _ack(0x50), _nav_response(),
            _ack(0x32), _ack(0x22), image_b0(),
        ])
        event_frames = _build_event_frames(first_image=False) + [
            event(2, bytes(range(12))),
            event(0x200, bytes(range(12, 24))),
            event(2, bytes(range(24, 36))),
        ]
        if mutate:
            mutate(frames, event_frames)
        transport._receive = frames
        events._frames = event_frames
        with mock.patch.object(Tls12PskServerSession, "from_boundary", _fake_tls_factory):
            result = coord.run(
                seed_result=synthetic_seed(), ts16=0x4242,
                terminal_mode=TerminalBoundary.STOP_AFTER_SECOND_IMAGE,
            )
        return coord, transport, result

    def test_public_runtime_retains_session_and_stops_after_second_b0(self):
        coord, transport, result = self.run_path()
        self.assertTrue(result.second_image_received)
        self.assertEqual(
            list(result.command_trace)[-6:], [0x22, 0x34, 0x20, 0x50, 0x32, 0x22]
        )
        audit = coord.audit()
        self.assertEqual(audit["usb_transport_session_count"], 1)
        self.assertEqual(transport.open_count, 1)
        self.assertEqual(audit["tls_server_session_object_count"], 1)
        self.assertEqual(audit["tls_server_handshake_count"], 1)
        self.assertEqual(audit["secret_boundary_handoff_count"], 1)
        self.assertEqual(audit["retry_count"], 0)
        self.assertEqual(audit["transport_cleanup_count"], 1)
        self.assertEqual(audit["persistent_device_write_count"], 0)
        self.assertFalse(transport._receive)
        self.assertFalse(coord.event_source._frames)

    def test_ack07_fails_closed_without_retry(self):
        def mutate(frames, _events):
            frames[-8] = outer(PLAIN, payload(0xB0, b"\x34\x07"))
        with self.assertRaisesRegex(Exception, "lifecycle_ack01_required:0x34"):
            self.run_path(mutate)

    def test_stale_or_cross_cycle_table_fails_before_rearm(self):
        def mutate(_frames, events):
            events[-2] = event(0x200, b"short")
        with self.assertRaisesRegex(Exception, "down_table_missing"):
            self.run_path(mutate)

    def test_b0_before_second_irq_is_not_promoted(self):
        def mutate(_frames, events):
            events[-1] = image_b0()
        with self.assertRaisesRegex(Exception, "expected_irq_0x0002"):
            self.run_path(mutate)


if __name__ == "__main__":
    unittest.main()
