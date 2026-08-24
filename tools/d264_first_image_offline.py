#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""D264/02 operator-facing, synthetic-only terminal-boundary rehearsal.

This entrypoint has deliberately no live mode.  It validates the operator's
boundary choice before importing the synthetic fixture and then drives the
public persistent coordinator.  Pixel data remains inside the fixture and is
never included in the JSON result.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from unittest import mock


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("repository root not found")


REPO = find_repo_root(Path(__file__))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.persistent_runtime import FIRST_IMAGE_IRQ2_TIMEOUT_MS, TerminalBoundary


BOUNDARY_NAMES = tuple(boundary.value for boundary in TerminalBoundary)


def rehearse(boundary: TerminalBoundary) -> dict[str, object]:
    # Reuse the already-reviewed D263 synthetic transport/TLS fixture rather
    # than introducing a parallel protocol or lifecycle implementation.
    from tests.test_d263_phase2_public_run import (
        Tls12PskServerSession,
        _build_event_frames,
        _build_receive_frames,
        _fake_tls_factory,
        _make_coordinator,
        synthetic_seed,
    )

    first_image = boundary is TerminalBoundary.STOP_AFTER_FIRST_IMAGE
    coordinator, transport, event_source = _make_coordinator(
        operational_physical_policy=first_image,
        record_submissions=True,
    )
    transport._receive = _build_receive_frames(first_image=first_image)
    event_source._frames = _build_event_frames(first_image=first_image)
    with mock.patch.object(Tls12PskServerSession, "from_boundary", _fake_tls_factory):
        result = coordinator.run(
            seed_result=synthetic_seed(),
            ts16=0x4242,
            terminal_mode=boundary,
        )
    audit = coordinator.audit()
    return {
        "schema": "D264_02_OFFLINE_OPERATOR_REHEARSAL_V1",
        "status": "PASS_OFFLINE",
        "execution_mode": "SYNTHETIC_OFFLINE_ONLY",
        "terminal_boundary": boundary.value,
        "default_boundary": TerminalBoundary.STOP_AFTER_FDT_ARM_ACK.value,
        "explicit_first_image_opt_in": first_image,
        "first_image_irq2_timeout_ms": FIRST_IMAGE_IRQ2_TIMEOUT_MS,
        "first_image_irq2_deadline": "ABSOLUTE_NON_RENEWABLE_SINGLE_WAIT",
        "physical_0x22_policy": "FIXED64_ZERO_TAIL" if first_image else "NOT_REACHED",
        "first_image_received": result.first_image_received,
        "first_image_validation": result.first_image_validation,
        "image_dimensions": list(result.first_image_raster_shape) if result.first_image_raster_shape else None,
        "command_trace": [f"0x{opcode:02x}" for opcode in result.command_trace],
        "runtime_audit": audit,
        "REAL_USB_OPEN_COUNT": 0,
        "REAL_TLS_HANDSHAKE_COUNT": 0,
        "REAL_SENSOR_COMMAND_COUNT": 0,
        "REAL_SECRET_MATERIALIZATION_COUNT": 0,
        "READY_FOR_LIVE": False,
        "LIVE_AUTHORIZED": False,
        "BASELINE_APPROVED": False,
        "biometric_payload_persisted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--terminal-boundary",
        choices=BOUNDARY_NAMES,
        default=TerminalBoundary.STOP_AFTER_FDT_ARM_ACK.value,
        help="first-image requires the explicit stop_after_first_image value",
    )
    args = parser.parse_args(argv)
    report = rehearse(TerminalBoundary(args.terminal_boundary))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
