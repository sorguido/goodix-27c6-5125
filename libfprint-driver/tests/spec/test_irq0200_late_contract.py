#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""SPEC_ONLY: independent checks of a partial zero-mask release contract.

This suite exercises no driver code. Passing demonstrates the stated model's
invariants and missing rearm proof, not implemented runtime support or firmware
ownership. Run directly with python3 -I -B; no third-party packages are needed.
"""
import dataclasses
import importlib.util
import itertools
from pathlib import Path
import struct
import sys
import unittest


SPEC = importlib.util.spec_from_file_location(
    "goodix_zero_mask_spec", Path(__file__).with_name("zero_mask_contract.py"))
model = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = model
SPEC.loader.exec_module(model)


def irq(control, irq_value, flags=0, words=(0x0100,) * 6):
    """Only observed IRQ fields: deliberately no stage, principal or wire epoch."""
    return model.WireIRQ(control, struct.pack("<HH6H", irq_value, flags, *words))


ZERO = irq(0x36, 0x0100)
UP = irq(0x34, 0x0200, words=(0x0120,) * 6)
DOWN = irq(0x32, 0x0002, flags=1)
TABLE_ZERO = b"\x80\x80" * 6
TABLE_UP = b"\x80\x90" * 6


class LateReleaseContract(unittest.TestCase):
    def fresh(self, contact=2, principal="synthetic-a", terminal=False,
              generation=7):
        return model.ZeroMaskContract(generation, contact, principal, terminal)

    def zero(self, contract):
        self.assertEqual(contract.receive(ZERO), "ZERO_ACCEPTED")
        self.assertEqual(contract.state, "ZERO_OPEN")
        self.assertEqual(contract.candidate_down, TABLE_ZERO)

    def assert_prefix_invariants(self, contract):
        # Observe effects independently of model self-reported delivery counters.
        samples = [entry for entry in contract.effects if entry[0] == "sample"]
        finger_off = [entry for entry in contract.effects if entry[0] == "finger_off"]
        release_updates = [entry for entry in contract.effects
                           if entry[:2] == ("down", "0200")]
        self.assertLessEqual(len(samples), 1)
        self.assertEqual(len(finger_off), len(samples))
        self.assertLessEqual(len(release_updates), 1)
        self.assertEqual(contract.commands, [])
        self.assertEqual(contract.auxiliary_count, 0)
        self.assertEqual(contract.retries, 0)
        self.assertEqual(len(contract.deliveries), len(samples))

    def test_a1_no_late_release_preserves_sample_but_cannot_rearm(self):
        contract = self.fresh()
        self.zero(contract)
        self.assertTrue(contract.primary_pending)
        self.assertEqual(contract.deliver_primary(), "DELIVERED")
        self.assertEqual(contract.request_next(), "BLOCKED_UNPROVEN")
        self.assertEqual(contract.attempt_rearm(), "BLOCKED_UNPROVEN")
        self.assertEqual(contract.effects, [
            ("down", "0100", TABLE_ZERO),
            ("sample", "synthetic-a", 2), ("finger_off", 2)])
        self.assertEqual(contract.state, "ZERO_OPEN")
        self.assertFalse(contract.release_seen)
        self.assertTrue(contract.next_requested)
        self.assertFalse(contract.primary_pending)
        self.assert_prefix_invariants(contract)

    def test_a2_immediate_release_retains_primary_until_delivery(self):
        contract = self.fresh()
        self.zero(contract)
        self.assertEqual(contract.receive(UP), "OPTIONAL_RELEASE")
        self.assertTrue(contract.primary_pending)
        self.assertEqual(contract.deliveries, [])
        self.assertTrue(contract.release_seen)
        self.assertEqual(contract.candidate_down, TABLE_UP)
        self.assertEqual(contract.deliver_primary(), "DELIVERED")
        self.assertEqual(contract.effects, [
            ("down", "0100", TABLE_ZERO), ("down", "0200", TABLE_UP),
            ("sample", "synthetic-a", 2), ("finger_off", 2)])
        self.assert_prefix_invariants(contract)

    def test_a3_late_release_after_delivery_does_not_redeliver(self):
        contract = self.fresh()
        self.zero(contract)
        self.assertEqual(contract.deliver_primary(), "DELIVERED")
        self.assertEqual(contract.receive(UP), "OPTIONAL_RELEASE")
        self.assertEqual(contract.effects, [
            ("down", "0100", TABLE_ZERO),
            ("sample", "synthetic-a", 2), ("finger_off", 2),
            ("down", "0200", TABLE_UP)])
        self.assertEqual(contract.request_next(), "BLOCKED_UNPROVEN")
        self.assertEqual(contract.attempt_rearm(), "BLOCKED_UNPROVEN")
        self.assert_prefix_invariants(contract)

    def test_grouped_and_separate_model_inputs_have_identical_effects(self):
        # Grouping is a model scheduling choice, not a real USB router test.
        # Neither completion of one IN-shaped group nor an empty batch is a
        # device fence. The model only sees the same ordered wire events.
        results = []
        for groups in (((ZERO, UP),), ((ZERO,), (UP,))):
            contract = self.fresh()
            for group in groups:
                for frame in group:
                    contract.receive(frame)
                before = list(contract.effects)
                self.assertEqual(contract.observe_host_quiet("empty_batch"),
                                 "BLOCKED_UNPROVEN")
                self.assertEqual(contract.effects, before)
            contract.deliver_primary()
            contract.request_next()
            self.assertEqual(contract.attempt_rearm(), "BLOCKED_UNPROVEN")
            results.append((contract.effects, contract.deliveries,
                            contract.candidate_down, contract.commands))
            self.assert_prefix_invariants(contract)
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][0], [
            ("down", "0100", TABLE_ZERO), ("down", "0200", TABLE_UP),
            ("sample", "synthetic-a", 2), ("finger_off", 2)])

    def test_a4_queued_request_does_not_bypass_release_or_wire_fence(self):
        contract = self.fresh()
        self.zero(contract)
        self.assertEqual(contract.request_next(), "BLOCKED_UNPROVEN")
        self.assertEqual(contract.attempt_rearm(), "BLOCKED_PRECONDITION")
        self.assertEqual(contract.receive(UP), "OPTIONAL_RELEASE")
        self.assertEqual(contract.attempt_rearm(), "BLOCKED_PRECONDITION")
        self.assertEqual(contract.effects, [
            ("down", "0100", TABLE_ZERO), ("down", "0200", TABLE_UP)])
        self.assertEqual(contract.deliver_primary(), "DELIVERED")
        self.assertEqual(contract.attempt_rearm(), "BLOCKED_UNPROVEN")
        self.assertTrue(contract.next_requested)
        self.assert_prefix_invariants(contract)

    def test_a5_duplicate_release_fails_without_second_release_effect(self):
        contract = self.fresh()
        self.zero(contract)
        self.assertEqual(contract.receive(UP), "OPTIONAL_RELEASE")
        self.assertEqual(contract.receive(UP), "FAILED")
        self.assertEqual(contract.state, "FAILED")
        self.assertEqual(contract.effects, [
            ("down", "0100", TABLE_ZERO), ("down", "0200", TABLE_UP),
            ("failure", "duplicate-release")])
        self.assertIsNone(contract.candidate_down)
        self.assertFalse(contract.primary_pending)
        self.assertFalse(contract.next_requested)
        self.assert_prefix_invariants(contract)

    def test_a6_next_irq2_before_release_closure_fails(self):
        contract = self.fresh()
        self.zero(contract)
        contract.request_next()
        self.assertEqual(contract.receive(DOWN), "FAILED")
        self.assertEqual(contract.effects, [
            ("down", "0100", TABLE_ZERO), ("failure", "early-next-contact")])
        self.assertEqual(contract.deliveries, [])
        self.assertIsNone(contract.candidate_down)
        self.assert_prefix_invariants(contract)

    def test_intermediate_contacts_keep_stage_accounting(self):
        for contact in (2, 4, 7, 19):
            with self.subTest(contact=contact):
                contract = self.fresh(contact=contact)
                self.zero(contract)
                contract.deliver_primary()
                self.assertEqual(contract.request_next(), "BLOCKED_UNPROVEN")
                self.assertEqual(contract.contacts, contact)
                self.assertEqual(contract.deliveries, [("synthetic-a", contact)])
                self.assert_prefix_invariants(contract)

    def test_terminal_delivery_fences_late_events_and_requests(self):
        contract = self.fresh(contact=8, terminal=True)
        self.zero(contract)
        self.assertEqual(contract.deliver_primary(), "DELIVERED")
        self.assertEqual(contract.state, "DONE")
        effects = list(contract.effects)
        for result in (contract.receive(UP), contract.receive(DOWN),
                       contract.request_next(), contract.attempt_rearm(),
                       contract.deliver_primary()):
            self.assertEqual(result, "IGNORED_FENCED")
        self.assertEqual(contract.effects, effects)
        self.assertEqual(contract.deliveries, [("synthetic-a", 8)])
        self.assert_prefix_invariants(contract)

    def test_cancel_fences_pending_and_already_delivered_primary(self):
        for delivered in (False, True):
            with self.subTest(delivered=delivered):
                contract = self.fresh()
                self.zero(contract)
                contract.request_next()
                if delivered:
                    contract.deliver_primary()
                self.assertEqual(contract.cancel(), "CANCELLED")
                effects = list(contract.effects)
                self.assertIsNone(contract.candidate_down)
                self.assertFalse(contract.primary_pending)
                self.assertFalse(contract.next_requested)
                for result in (contract.receive(UP), contract.deliver_primary(),
                               contract.request_next(), contract.attempt_rearm()):
                    self.assertEqual(result, "IGNORED_FENCED")
                self.assertEqual(contract.effects, effects)
                self.assert_prefix_invariants(contract)

    def test_unsolicited_auxiliary_is_not_a_stage(self):
        contract = self.fresh()
        self.zero(contract)
        self.assertEqual(contract.auxiliary_b0(), "FAILED")
        self.assertEqual(contract.deliveries, [])
        self.assertEqual(contract.effects, [
            ("down", "0100", TABLE_ZERO), ("failure", "unsolicited-auxiliary")])
        self.assert_prefix_invariants(contract)

    def test_duplicate_delivery_is_fail_closed(self):
        contract = self.fresh()
        self.zero(contract)
        self.assertEqual(contract.deliver_primary(), "DELIVERED")
        self.assertEqual(contract.deliver_primary(), "FAILED")
        self.assertEqual(contract.deliveries, [("synthetic-a", 2)])
        self.assert_prefix_invariants(contract)

    def test_repeated_requests_never_create_a_rearm_capability(self):
        contract = self.fresh()
        self.zero(contract)
        contract.receive(UP)
        contract.deliver_primary()
        for _ in range(3):
            self.assertEqual(contract.request_next(), "BLOCKED_UNPROVEN")
            self.assertEqual(contract.attempt_rearm(), "BLOCKED_UNPROVEN")
        self.assertEqual(contract.commands, [])  # Stronger than at most one32.
        self.assert_prefix_invariants(contract)

    def test_contact_twenty_cannot_admit_another_contact(self):
        contract = self.fresh(contact=20)
        self.zero(contract)
        contract.deliver_primary()
        self.assertEqual(contract.request_next(), "FAILED")
        self.assertEqual(contract.contacts, 20)
        self.assertEqual(contract.commands, [])
        self.assert_prefix_invariants(contract)

    def test_terminal_contact_twenty_drops_post_delivery_requests(self):
        contract = self.fresh(contact=20, terminal=True)
        self.zero(contract)
        contract.receive(UP)
        self.assertEqual(contract.deliver_primary(), "DELIVERED")
        self.assertEqual(contract.state, "DONE")
        self.assertEqual(contract.contacts, 20)
        self.assertEqual(contract.deliveries, [("synthetic-a", 20)])
        effects = list(contract.effects)
        for _ in range(2):
            self.assertEqual(contract.request_next(), "IGNORED_FENCED")
            self.assertEqual(contract.attempt_rearm(), "IGNORED_FENCED")
        self.assertEqual(contract.receive(UP), "IGNORED_FENCED")
        self.assertEqual(contract.effects, effects)
        self.assertFalse(contract.next_requested)
        self.assertIsNone(contract.candidate_down)
        self.assert_prefix_invariants(contract)

    def test_fresh_action_stage_and_principal_have_no_shared_state(self):
        old = self.fresh()
        self.zero(old)
        old.receive(UP)
        old.request_next()
        old.deliver_primary()
        old.cancel()
        # A fresh contact-3 object is an isolation probe, not an allowed
        # transition out of contact 2 and not proof that a device FIFO cleared.
        for contact, principal, generation in (
                (3, "synthetic-a", 7), (2, "synthetic-a", 8),
                (2, "synthetic-b", 9)):
            with self.subTest(contact=contact, principal=principal):
                new = self.fresh(contact, principal, generation=generation)
                self.assertEqual(new.state, "WAIT_ZERO")
                self.assertIsNone(new.candidate_down)
                self.assertFalse(new.release_seen)
                self.assertFalse(new.next_requested)
                self.assertTrue(new.primary_pending)
                self.assertEqual(new.effects, [])
                self.assertEqual(new.deliveries, [])
                self.zero(new)
                new.deliver_primary()
                self.assertEqual(new.deliveries, [(principal, contact)])
        self.assertEqual(old.deliveries, [("synthetic-a", 2)])
        self.assertEqual(old.state, "CANCELLED")

    def test_old_host_callback_is_distinct_from_old_firmware_bytes(self):
        contract = self.fresh(generation=7)
        self.zero(contract)
        before = list(contract.effects)
        self.assertEqual(contract.receive(UP, callback_generation=6),
                         "IGNORED_OLD_CALLBACK")
        self.assertEqual(contract.effects, before)
        # These same bytes on a current IN cannot carry proof of sensor origin.
        self.assertEqual(contract.receive(UP, callback_generation=7),
                         "OPTIONAL_RELEASE")
        contract.deliver_primary()
        contract.request_next()
        self.assertEqual(contract.attempt_rearm(), "BLOCKED_UNPROVEN")
        self.assert_prefix_invariants(contract)

    def test_observation_collision_has_no_wire_stage_classifier(self):
        fields = tuple(field.name for field in dataclasses.fields(model.WireIRQ))
        self.assertEqual(fields, ("control", "body"))
        # Oracle ownership is deliberately outside the model input. Both
        # histories use the identical current host callback and frame bytes.
        histories = (("previous-stage", (7, UP.control, UP.body)),
                     ("current-stage", (7, UP.control, UP.body)))
        self.assertNotEqual(histories[0][0], histories[1][0])
        self.assertEqual(histories[0][1], histories[1][1])
        outcomes = []
        for _oracle_owner, observation in histories:
            contract = self.fresh()
            self.zero(contract)
            outcomes.append(contract.receive(
                model.WireIRQ(observation[1], observation[2]),
                callback_generation=observation[0]))
            contract.deliver_primary()
            contract.request_next()
            self.assertEqual(contract.attempt_rearm(), "BLOCKED_UNPROVEN")
        self.assertEqual(outcomes, ["OPTIONAL_RELEASE", "OPTIONAL_RELEASE"])

    def test_finite_host_quiet_does_not_prove_no_future_release(self):
        contract = self.fresh()
        self.zero(contract)
        contract.deliver_primary()
        contract.request_next()
        before = (contract.state, contract.candidate_down, list(contract.effects))
        for kind in ("timeout", "drain", "ack", "empty_batch", "generation_change"):
            with self.subTest(kind=kind):
                self.assertEqual(contract.observe_host_quiet(kind),
                                 "BLOCKED_UNPROVEN")
                self.assertEqual((contract.state, contract.candidate_down,
                                  contract.effects), before)
                self.assertEqual(contract.attempt_rearm(), "BLOCKED_UNPROVEN")
        self.assertEqual(contract.receive(UP), "OPTIONAL_RELEASE")
        self.assertEqual(contract.attempt_rearm(), "BLOCKED_UNPROVEN")
        self.assert_prefix_invariants(contract)

    def test_invalid_wire_shapes_and_unowned_release_fail(self):
        cases = ((model.WireIRQ(0x36, ZERO.body[:-1]), "body-length"),
                 (model.WireIRQ(0x36, ZERO.body + b"\x00"), "body-length"),
                 (irq(0x34, 0x0100), "expected-zero-sample"),
                 (irq(0x36, 0x0200), "expected-zero-sample"),
                 (irq(0x36, 0x0100, flags=1), "expected-zero-sample"),
                 (irq(0x36, 0x0100, flags=0x0040), "expected-zero-sample"),
                 (UP, "expected-zero-sample"), (DOWN, "early-next-contact"))
        for frame, reason in cases:
            with self.subTest(frame=frame):
                contract = self.fresh()
                self.assertEqual(contract.receive(frame), "FAILED")
                self.assertEqual(contract.effects, [("failure", reason)])
                self.assert_prefix_invariants(contract)

    def test_fdt_raw_range_rejects_wrapping_and_keeps_exact_snapshot(self):
        for word in (0, 1, 510, 511, 512, 65535):
            with self.subTest(word=word):
                contract = self.fresh()
                self.assertEqual(contract.receive(irq(
                    0x36, 0x0100, words=(word,) + (0x0100,) * 5)), "FAILED")
                self.assertIsNone(contract.candidate_down)
                self.assertEqual(contract.effects, [("failure", "raw-range")])
        contract = self.fresh()
        self.assertEqual(contract.receive(irq(
            0x36, 0x0100, words=(2, 3, 508, 509, 256, 257))), "ZERO_ACCEPTED")
        self.assertEqual(contract.candidate_down,
                         bytes((0x80, 1, 0x80, 1, 0x80, 254,
                                0x80, 254, 0x80, 128, 0x80, 128)))

    def test_invalid_optional_release_has_no_partial_fdt_update(self):
        cases = (
            (irq(0x34, 0x0200, words=(0x0120,) * 5 + (0,)), "raw-range"),
            (irq(0x34, 0x0200, flags=1), "expected-optional-release"),
            (irq(0x34, 0x0200, flags=0x0040), "expected-optional-release"),
        )
        for frame, reason in cases:
            with self.subTest(frame=frame):
                contract = self.fresh()
                self.zero(contract)
                self.assertEqual(contract.receive(frame), "FAILED")
                self.assertEqual(contract.effects, [
                    ("down", "0100", TABLE_ZERO), ("failure", reason)])
                self.assertIsNone(contract.candidate_down)
                self.assertFalse(contract.release_seen)
                self.assertEqual(contract.deliveries, [])
                self.assert_prefix_invariants(contract)

    def test_bounded_interleavings_preserve_every_prefix(self):
        operations = ("release", "release_duplicate", "request", "deliver",
                      "rearm", "cancel")
        for terminal in (False, True):
            for ordering in itertools.permutations(operations):
                contract = self.fresh(terminal=terminal)
                self.zero(contract)
                fenced_effects = None
                for operation in ordering:
                    if operation.startswith("release"):
                        contract.receive(UP)
                    elif operation == "request":
                        contract.request_next()
                    elif operation == "deliver":
                        contract.deliver_primary()
                    elif operation == "rearm":
                        contract.attempt_rearm()
                    else:
                        contract.cancel()
                    self.assert_prefix_invariants(contract)
                    if fenced_effects is not None:
                        self.assertEqual(contract.effects, fenced_effects,
                                         (terminal, ordering, operation))
                    elif contract.state in ("DONE", "FAILED", "CANCELLED"):
                        fenced_effects = list(contract.effects)


if __name__ == "__main__":
    program = unittest.main(exit=False)
    if not program.result.wasSuccessful():
        raise SystemExit(1)
    print("SPEC_ONLY_PASS")
    print("RUNTIME_IMPLEMENTED=0")
    print("REARM_FENCE_PROVEN=0")
