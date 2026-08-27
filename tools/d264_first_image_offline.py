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


def rehearse(
    boundary: TerminalBoundary,
    *,
    event_source_wrapper: object | None = None,
) -> dict[str, object]:
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

    first_image = boundary is not TerminalBoundary.STOP_AFTER_FDT_ARM_ACK
    coordinator, transport, raw_event_source = _make_coordinator(
        operational_physical_policy=first_image,
        record_submissions=True,
    )
    event_source = raw_event_source
    if event_source_wrapper is not None:
        event_source = event_source_wrapper(raw_event_source)
        coordinator.event_source = event_source
    if boundary is TerminalBoundary.STOP_AFTER_SECOND_IMAGE:
        from tests.test_d275_01_production_multiframe import event, image_b0
        from analysis.D260.d260_offline_rehearsal import _ack, _nav_response
        transport._receive = _build_receive_frames(first_image=True) + [
            _ack(0x34), _ack(0x20), image_b0(), _ack(0x50), _nav_response(),
            _ack(0x32), _ack(0x22), image_b0(),
        ]
        raw_event_source._frames = _build_event_frames(first_image=False) + [
            event(2, bytes(range(12))), event(0x200, bytes(range(12, 24))),
            event(2, bytes(range(24, 36))),
        ]
    else:
        transport._receive = _build_receive_frames(first_image=first_image)
        raw_event_source._frames = _build_event_frames(first_image=first_image)
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
        "second_image_received": result.second_image_received,
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
