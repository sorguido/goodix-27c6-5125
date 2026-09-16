# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Offline tests for D263/05 Phase 2 support primitives (lifecycle + transport).

Synthetic data only. No USB, no secret, no live. Verifies the minimal
transitions and the 0x22 physical policy added in step 05.
"""

from __future__ import annotations

import unittest

from core.fdt_lifecycle import (
    COMMAND_TIMEOUT_MS,
    FdtLifecycle,
    FdtLifecycleState,
    InvalidTransition,
    PERSISTENT_COMMAND_FAMILIES,
    SAFE_DEVICE_COMMANDS,
    SPECIAL_RECOVERY_COMMANDS,
)
from core.post_d4 import build_finger_image
from core.runtime_transport import (
    fdt_a0_policy,
    operational_fdt_a0_policy,
    SubmissionMode,
)


class FdtLifecycleSupportPrimitives(unittest.TestCase):
    def _armed(self) -> FdtLifecycle:
        lc = FdtLifecycle()
        lc.observe_af_state(False)  # fresh_path = True
        lc.begin_bootstrap()
        for stage in range(3):
            lc.manual_sample_attempt(stage)
            lc.manual_sample_completed(stage)
        lc.bootstrap_completed()
        lc.arm_fdt()
        self.assertEqual(lc.state, FdtLifecycleState.FDT_ARMED_WAIT)
        return lc

    def test_valid_terminal_transition(self) -> None:
        lc = self._armed()
        lc.post_irq2_image_command()
        lc.first_image_received()
        lc.cancel_pending_receive()
        lc.terminal_stop()
        self.assertEqual(lc.state, FdtLifecycleState.TERMINAL_STOPPED)
        self.assertEqual(lc.device_command_trace[-2:], (0x32, 0x22))
        self.assertEqual(lc.device_command_trace.count(0x36), 3)
        self.assertNotIn(0x34, lc.device_command_trace)
        self.assertNotIn(0x20, lc.device_command_trace)

    def test_0x22_one_shot_second_rejected(self) -> None:
        lc = self._armed()
        lc.post_irq2_image_command()
        with self.assertRaises(InvalidTransition):
            lc.post_irq2_image_command()
        self.assertEqual(lc.state, FdtLifecycleState.FAILED_CLOSED)

    def test_first_image_received_twice_rejected(self) -> None:
        lc = self._armed()
        lc.post_irq2_image_command()
        lc.first_image_received()
        with self.assertRaises(InvalidTransition):
            lc.first_image_received()

    def test_post_irq2_requires_armed_wait(self) -> None:
        lc = FdtLifecycle()
        with self.assertRaises(InvalidTransition):
            lc.post_irq2_image_command()

    def test_cancel_accepts_first_image_received(self) -> None:
        lc = self._armed()
        lc.post_irq2_image_command()
        lc.first_image_received()
        transition = lc.cancel_pending_receive()
        self.assertEqual(lc.state, FdtLifecycleState.HOST_WAIT_CANCELED)
        self.assertEqual(transition.device_commands, ())

    def test_prohibited_commands_unreachable(self) -> None:
        for forbidden in (0x34, 0xA2, 0x70):
            self.assertNotIn(forbidden, SAFE_DEVICE_COMMANDS)
        self.assertTrue(
            SAFE_DEVICE_COMMANDS.isdisjoint(PERSISTENT_COMMAND_FAMILIES)
        )
        self.assertTrue(
            SAFE_DEVICE_COMMANDS.isdisjoint(SPECIAL_RECOVERY_COMMANDS)
        )

    def test_command_timeout_ms_has_0x22(self) -> None:
        self.assertEqual(COMMAND_TIMEOUT_MS.get(0x22), 2000)


class Transport0x22Policy(unittest.TestCase):
    def test_abstract_policy_not_live_proven(self) -> None:
        policy = fdt_a0_policy(0x22, 2000)
        self.assertEqual(policy.mode, SubmissionMode.ABSTRACT_LOGICAL_ONLY)
        self.assertIn("ABSTRACT_OFFLINE", policy.name)
        self.assertNotIn("LIVE_PROVEN", policy.name)

    def test_abstract_materialize_no_invented_tail(self) -> None:
        frame = build_finger_image()
        chunks = fdt_a0_policy(0x22, 2000).materialize(frame)
        self.assertEqual(chunks, (frame,))

    def test_operational_policy_deterministic_zero_tail(self) -> None:
        frame = build_finger_image()
        chunks = operational_fdt_a0_policy(0x22, 2000).materialize(frame)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 64)
        self.assertEqual(chunks[0][: len(frame)], frame)
        self.assertEqual(chunks[0][len(frame):], b"\x00" * (64 - len(frame)))

    def test_prohibited_0x34_0xA2_rejected(self) -> None:
        for control in (0x34, 0xA2, 0x70):
            with self.assertRaises(ValueError):
                fdt_a0_policy(control, 2000)
            with self.assertRaises(ValueError):
                operational_fdt_a0_policy(control, 2000)

    def test_0x22_allowed_in_both_policies(self) -> None:
        self.assertIsNotNone(fdt_a0_policy(0x22, 2000))
        self.assertIsNotNone(operational_fdt_a0_policy(0x22, 2000))


if __name__ == "__main__":
    unittest.main()
