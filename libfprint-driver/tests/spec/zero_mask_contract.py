# SPDX-License-Identifier: LGPL-2.1-or-later
"""Partial specification only; this module is never used by the driver.

Entry assumes an acquired primary and completed first-34/36 OUTs and ACKs.
It models the zero branch's local effects and the unresolved rearm barrier.
No input can manufacture that barrier. In particular, a passing test does NOT
mean that enrollment recovery is implemented or that firmware events have a
stage identifier. See docs/ENROLLMENT_ZERO_MASK_CONTRACT.md.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WireIRQ:
    """Only observed IRQ fields: control and the sixteen-byte A0 body.

    Outer framing/checksum remain the real parser's responsibility. There is
    deliberately no stage, principal, request ID or device generation here.
    """

    control: int
    body: bytes


class ZeroMaskContract:
    """One host-owned contact; optional release provenance is not proved.

    candidate_down is a proposal, never an emitted command's table. Even one
    observed release does not prove that a duplicate cannot arrive later.
    This model deliberately has no successful rearm transition.
    """

    FENCED = frozenset(("DONE", "CANCELLED", "FAILED"))

    def __init__(self, generation: int, contact: int, principal: str,
                 terminal: bool = False):
        if generation <= 0 or not 2 <= contact <= 20:
            raise ValueError("positive host generation and repeated contact 2..20 required")
        self.generation = generation
        self.contact = contact
        self.contacts = contact  # Primary was counted before entering this branch.
        self.principal = principal  # Opaque test metadata, never read from the wire.
        self.terminal = terminal
        self.state = "WAIT_ZERO"
        self.candidate_down = None
        self.release_seen = False
        self.next_requested = False
        self.primary_pending = True
        self.deliveries = []
        self.effects = []
        self.commands = []
        self.auxiliary_count = 0
        self.retries = 0
        self.failure_reason = None

    def _fence(self, state):
        self.state = state
        self.primary_pending = False
        self.next_requested = False
        self.candidate_down = None

    def _fail(self, reason):
        self.failure_reason = reason
        self._fence("FAILED")
        self.effects.append(("failure", reason))
        return "FAILED"

    @staticmethod
    def _fields(frame):
        if (not isinstance(frame, WireIRQ) or not isinstance(frame.body, bytes) or
                type(frame.control) is not int or not 0 <= frame.control <= 255):
            raise ValueError("shape")
        if len(frame.body) != 16:
            raise ValueError("body-length")
        irq = int.from_bytes(frame.body[:2], "little")
        flags = int.from_bytes(frame.body[2:4], "little")
        words = [int.from_bytes(frame.body[i:i + 2], "little")
                 for i in range(4, 16, 2)]
        # Deliberately conservative local policy: retain the Linux range bound
        # and reject the OEM helper's invalid 0/ff components, without wrapping.
        values = [word >> 1 for word in words]
        if any(value < 1 or value > 254 for value in values):
            raise ValueError("raw-range")
        table = bytes(byte for value in values for byte in (0x80, value))
        return irq, flags, table

    def receive(self, frame, callback_generation=None):
        """Host callback generation fences callbacks, not firmware provenance."""
        generation = (self.generation if callback_generation is None
                      else callback_generation)
        if generation != self.generation:
            return "IGNORED_OLD_CALLBACK"
        if self.state in self.FENCED:
            return "IGNORED_FENCED"
        try:
            irq, flags, table = self._fields(frame)
        except ValueError as error:
            return self._fail(str(error))
        if irq == 0x0002:
            return self._fail("early-next-contact")
        if self.state == "WAIT_ZERO":
            if (frame.control, irq, flags) != (0x36, 0x0100, 0):
                return self._fail("expected-zero-sample")
            self.candidate_down = table
            self.effects.append(("down", "0100", table))
            self.state = "ZERO_OPEN"
            return "ZERO_ACCEPTED"
        if (frame.control, irq, flags) != (0x34, 0x0200, 0):
            return self._fail("expected-optional-release")
        if self.release_seen:
            return self._fail("duplicate-release")
        self.release_seen = True
        self.candidate_down = table
        self.effects.append(("down", "0200", table))
        # This is a host-window attribution only. It is NOT evidence of the
        # physical source contact, and does not authorize a subsequent 32.
        return "OPTIONAL_RELEASE"

    def deliver_primary(self):
        if self.state in self.FENCED:
            return "IGNORED_FENCED"
        if self.state != "ZERO_OPEN" or not self.primary_pending:
            return self._fail("primary-delivery-order")
        self.primary_pending = False
        self.deliveries.append((self.principal, self.contact))
        # Proposed logical libfprint mapping only; asynchronous extraction and
        # completion-hold ordering are outside this specification model.
        self.effects.extend((("sample", self.principal, self.contact),
                             ("finger_off", self.contact)))
        # Models the ordinary quality decision to finish, not guaranteed
        # biometric acceptance of the primary and not physical finger absence.
        if self.terminal:
            self._fence("DONE")
        return "DELIVERED"

    def request_next(self):
        if self.state in self.FENCED:
            return "IGNORED_FENCED"
        if self.state != "ZERO_OPEN":
            return self._fail("next-request-before-zero")
        if self.contact >= 20:
            return self._fail("contact-limit")
        self.next_requested = True
        return "BLOCKED_UNPROVEN"

    def attempt_rearm(self):
        if self.state in self.FENCED:
            return "IGNORED_FENCED"
        if (self.state != "ZERO_OPEN" or self.primary_pending or
                not self.next_requested):
            return "BLOCKED_PRECONDITION"
        # No setter/token/timeout/ACK is allowed to turn an unproved device
        # fence into a true precondition. Positive rearm remains unmodelled.
        return "BLOCKED_UNPROVEN"

    def observe_host_quiet(self, kind):
        if kind not in ("timeout", "drain", "ack", "empty_batch", "generation_change"):
            raise ValueError("unknown host observation")
        if self.state in self.FENCED:
            return "IGNORED_FENCED"
        return "BLOCKED_UNPROVEN"

    def auxiliary_b0(self):
        if self.state in self.FENCED:
            return "IGNORED_FENCED"
        return self._fail("unsolicited-auxiliary")

    def cancel(self):
        if self.state in self.FENCED:
            return "IGNORED_FENCED"
        self._fence("CANCELLED")
        self.effects.append(("cancel",))
        return "CANCELLED"
