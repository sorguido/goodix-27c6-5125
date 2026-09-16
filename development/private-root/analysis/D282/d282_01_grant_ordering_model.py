#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline-only state model for the D282/01 one-shot grant boundary."""

from __future__ import annotations

from dataclasses import dataclass, field


PRECONSUMPTION_REFUSALS = (
    "STAGING_COLLISION",
    "FPRINTD_INITIAL_STATE_UNSAFE",
    "SYSTEM_LIBFPRINT_MISSING",
    "UNIT_SNAPSHOT_FAILED",
    "STORAGE_INVENTORY_FAILED",
    "SELINUX_PRECONDITION_FAILED",
    "TARGET_CARDINALITY_NOT_ONE",
)


@dataclass(frozen=True)
class Outcome:
    refusal: str | None
    grant_consumed: bool
    real_usb_enumeration_attempted: bool
    live_execution_performed: bool
    retry_authorized: bool
    rollback_complete: bool


@dataclass
class GrantRegistry:
    consumed_ids: set[str] = field(default_factory=set)


def simulate(
    registry: GrantRegistry,
    grant_id: str,
    *,
    invalid_grant_reason: str | None = None,
    preconsumption_refusal: str | None = None,
    fail_immediately_after_consumption: bool = False,
) -> Outcome:
    """Evaluate only ordering/telemetry; never performs I/O or live work."""
    if invalid_grant_reason is not None:
        return Outcome(invalid_grant_reason, False, False, False, False, True)
    if preconsumption_refusal is not None:
        if preconsumption_refusal not in PRECONSUMPTION_REFUSALS:
            raise ValueError(preconsumption_refusal)
        return Outcome(preconsumption_refusal, False, False, False, False, True)
    if grant_id in registry.consumed_ids:
        return Outcome("GRANT_ALREADY_CONSUMED", False, False, False, False, True)

    # Models the atomic mkdir claim: from this point the ID is irreversibly used.
    registry.consumed_ids.add(grant_id)
    if fail_immediately_after_consumption:
        return Outcome("POSTCONSUMPTION_STAGING_FAILURE", True, False, False,
                       False, True)

    return Outcome(None, True, True, True, False, True)
