# SPDX-License-Identifier: GPL-2.0-or-later
"""D275 production-coordinator offline bridge through the second image."""

import unittest
from unittest import mock

from analysis.D260.d260_offline_rehearsal import _ack, _nav_response, synthetic_seed
from core.fdt_lifecycle import (
    table_from_irq2_up_payload,
    table_from_irq200_down_payload,
)
from core.persistent_runtime import PersistentRuntimeCoordinator, TerminalBoundary
from core.post_d4 import PLAIN, TLS, parse_outer, parse_payload
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


def event(irq: int, table: bytes, *, touch_flags: int) -> bytes:
    return outer(
        PLAIN,
        payload(
            0x3F,
            irq.to_bytes(2, "little")
            + touch_flags.to_bytes(2, "little")
            + table,
        ),
    )


def image_b0() -> bytes:
    record = encode_synthetic_record((0,) * 5120)
    return outer(TLS, payload(0x20, b"\x01\0\0\0\0" + record))


class D275ProductionMultiframeTests(unittest.TestCase):
    FIRST_IRQ2_RAW = bytes.fromhex("ef00f000df00c800f400d100")
    FIRST_UP_OEM = bytes.fromhex("80948095808c808180978085")
    IRQ200_RAW = bytes.fromhex("5a017c01470162014d016501")
    DOWN_OEM = bytes.fromhex("80ad80be80a380b180a680b2")
    SECOND_IRQ2_RAW = bytes.fromhex("bc00f200cb00d500c100e800")
    SECOND_UP_OEM = bytes.fromhex("807b809680828087807d8091")

    def run_path(self, mutate=None):
        coord, transport, events = _make_coordinator(record_submissions=True)
        frames = _build_receive_frames(first_image=True)
        frames.extend([
            _ack(0x34), _ack(0x20), image_b0(), _ack(0x50), _nav_response(),
            _ack(0x32), _ack(0x22), image_b0(),
        ])
        event_frames = _build_event_frames(first_image=False) + [
            event(2, self.FIRST_IRQ2_RAW, touch_flags=0x003F),
            event(0x200, self.IRQ200_RAW, touch_flags=0),
            event(2, self.SECOND_IRQ2_RAW, touch_flags=0x003F),
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
        command_data = []
        for frame, _policy in transport.submissions:
            kind, command_payload = parse_outer(frame)
            if kind == PLAIN:
                command_data.append(parse_payload(command_payload))
        self.assertIn((0x34, b"\x0a\x01" + self.FIRST_UP_OEM), command_data)
        self.assertIn((0x32, b"\x08\x01" + self.DOWN_OEM + b"\x42\x42"), command_data)

    def test_ack07_fails_closed_without_retry(self):
        def mutate(frames, _events):
            frames[-8] = outer(PLAIN, payload(0xB0, b"\x34\x07"))
        with self.assertRaisesRegex(Exception, "lifecycle_ack01_required:0x34"):
            self.run_path(mutate)

    def test_stale_or_cross_cycle_table_fails_before_rearm(self):
        def mutate(_frames, events):
            events[-2] = event(0x200, b"short", touch_flags=0)
        with self.assertRaisesRegex(Exception, "fdt_table_derivation_failed"):
            self.run_path(mutate)

    def test_b0_before_second_irq_is_not_promoted(self):
        def mutate(_frames, events):
            events[-1] = image_b0()
        with self.assertRaisesRegex(Exception, "expected_irq_0x0002"):
            self.run_path(mutate)

    def test_exact_oem_fdt_derivation_fixtures(self):
        d263_irq2 = event(
            2,
            bytes.fromhex("d500ee00c800ba00c500d200"),
            touch_flags=0x003F,
        )
        _kind, d263_payload = parse_outer(d263_irq2)
        self.assertEqual(
            table_from_irq2_up_payload(d263_payload),
            bytes.fromhex("808780948081807a807f8086"),
        )

        d274_irq2 = event(2, self.FIRST_IRQ2_RAW, touch_flags=0x003F)
        _kind, d274_payload = parse_outer(d274_irq2)
        self.assertEqual(table_from_irq2_up_payload(d274_payload), self.FIRST_UP_OEM)
        self.assertNotEqual(table_from_irq2_up_payload(d274_payload), self.FIRST_IRQ2_RAW)

        d274_irq200 = event(0x200, self.IRQ200_RAW, touch_flags=0)
        _kind, d274_down_payload = parse_outer(d274_irq200)
        self.assertEqual(table_from_irq200_down_payload(d274_down_payload), self.DOWN_OEM)
        self.assertNotEqual(table_from_irq200_down_payload(d274_down_payload), self.IRQ200_RAW)

    def test_unproven_touch_context_fails_closed_before_0x34(self):
        def mutate(_frames, events):
            events[-3] = event(2, self.FIRST_IRQ2_RAW, touch_flags=0)
        with self.assertRaisesRegex(Exception, "first_irq2_up_table_derivation_failed"):
            self.run_path(mutate)

    def test_irq0200_timeout_preserves_first_image_milestones(self):
        coord, transport, events = _make_coordinator(record_submissions=True)
        transport._receive = _build_receive_frames(first_image=True) + [_ack(0x34)]
        events._frames = _build_event_frames(first_image=False) + [
            event(2, self.FIRST_IRQ2_RAW, touch_flags=0x003F)
        ]
        with mock.patch.object(Tls12PskServerSession, "from_boundary", _fake_tls_factory):
            with self.assertRaisesRegex(TimeoutError, "synthetic_event_queue_empty"):
                coord.run(
                    seed_result=synthetic_seed(),
                    ts16=0x4242,
                    terminal_mode=TerminalBoundary.STOP_AFTER_SECOND_IMAGE,
                )

        audit = coord.audit()
        self.assertEqual(audit["runtime_state"], "FAILED_CLOSED")
        self.assertTrue(audit["first_image_received"])
        self.assertEqual(audit["first_image_irq2_observed_count"], 1)
        self.assertEqual(audit["first_image_ack_validation_count"], 1)
        self.assertEqual(audit["first_image_b0_count"], 1)
        self.assertEqual(audit["first_image_raster_decode_count"], 1)
        self.assertEqual(audit["raster_decode_count"], 1)
        self.assertEqual(audit["retry_count"], 0)
        self.assertEqual(audit["persistent_device_write_count"], 0)
        self.assertEqual(audit["usb_transport_session_count"], 1)
        self.assertEqual(audit["tls_server_session_object_count"], 1)
        self.assertEqual(audit["tls_server_handshake_count"], 1)
        self.assertEqual(audit["transport_cleanup_count"], 1)
        self.assertEqual(audit["exact_fdt_command_trace"][-2:], ["0x22", "0x34"])
        self.assertNotIn("0x20", audit["exact_fdt_command_trace"][-2:])


if __name__ == "__main__":
    unittest.main()
