# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Offline-testable transport, event, and secret boundaries for D260.

Logical Goodix framing is deliberately separate from physical USB submission.
This module contains no USB implementation and performs no I/O by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class SubmissionMode(str, Enum):
    SHORT_FINAL = "SHORT_FINAL"
    FIXED64_ZERO_TAIL = "FIXED64_ZERO_TAIL"
    ABSTRACT_LOGICAL_ONLY = "ABSTRACT_LOGICAL_ONLY"


@dataclass(frozen=True)
class PhysicalSubmissionPolicy:
    name: str
    mode: SubmissionMode
    timeout_ms: int
    pre_submit_pacing_ms: int = 0
    post_submit_pacing_ms: int = 0
    chunk_size: int = 64

    def materialize(self, logical_frame: bytes) -> tuple[bytes, ...]:
        """Return physical chunks without performing transport I/O."""

        if not logical_frame:
            raise ValueError("empty_logical_frame")
        chunks = tuple(
            logical_frame[offset:offset + self.chunk_size]
            for offset in range(0, len(logical_frame), self.chunk_size)
        )
        if self.mode in (SubmissionMode.SHORT_FINAL, SubmissionMode.ABSTRACT_LOGICAL_ONLY):
            return chunks
        return tuple(chunk.ljust(self.chunk_size, b"\x00") for chunk in chunks)


D1_A0_POLICY = PhysicalSubmissionPolicy(
    "D1_A0_D241_SHORT_FINAL",
    SubmissionMode.SHORT_FINAL,
    timeout_ms=3000,
)
D4_A0_POLICY = PhysicalSubmissionPolicy(
    "D4_A0_FIXED64_ZERO_TAIL_POST_TLS_20MS",
    SubmissionMode.FIXED64_ZERO_TAIL,
    timeout_ms=200,
    pre_submit_pacing_ms=20,
)
AF_A0_POLICY = PhysicalSubmissionPolicy(
    "AF_A0_FIXED64_ZERO_TAIL_D251",
    SubmissionMode.FIXED64_ZERO_TAIL,
    timeout_ms=500,
)
B0_TLS_POLICY = PhysicalSubmissionPolicy(
    "B0_TLS_FIXED64_STAGING_D242_D245",
    SubmissionMode.FIXED64_ZERO_TAIL,
    timeout_ms=3000,
    post_submit_pacing_ms=10,
)


def fdt_a0_policy(control: int, timeout_ms: int) -> PhysicalSubmissionPolicy:
    """Represent an exact logical FDT command with deferred physical tail.

    D255 proves the Windows submission corpus, but it does not establish a
    Linux-safe value for opaque bytes outside the declared A0 length.  D260
    therefore keeps this axis abstract instead of inventing padding.
    """

    if control not in {0x20, 0x32, 0x36, 0x50, 0x82}:
        raise ValueError(f"unsupported_fdt_control:0x{control:02x}")
    return PhysicalSubmissionPolicy(
        f"FDT_A0_0x{control:02X}_ABSTRACT_OFFLINE",
        SubmissionMode.ABSTRACT_LOGICAL_ONLY,
        timeout_ms=timeout_ms,
    )


def operational_fdt_a0_policy(control: int, timeout_ms: int) -> PhysicalSubmissionPolicy:
    """Return the D261 deterministic physical candidate for one FDT A0.

    D255 proves physical length 64 for every command in the exact fresh-FDT
    trace.  Its only bytes outside the declared frame that are nonzero occupy
    the same absolute staging offsets across unrelated commands; D254 observes
    different values at those offsets.  D261 therefore never replays that
    residue and zero-fills the complete tail.  Device acceptance remains a
    future per-command live hypothesis.
    """

    if control not in {0x20, 0x32, 0x36, 0x50, 0x82}:
        raise ValueError(f"unsupported_fdt_control:0x{control:02x}")
    return PhysicalSubmissionPolicy(
        f"FDT_A0_0x{control:02X}_FIXED64_ZERO_TAIL_D261_CANDIDATE",
        SubmissionMode.FIXED64_ZERO_TAIL,
        timeout_ms=timeout_ms,
    )


class RuntimeTransport(Protocol):
    """One logical transport session; a future adapter may own real USB."""

    session_count: int
    cleanup_count: int

    def open(self) -> None:
        ...

    def submit(self, logical_frame: bytes, policy: PhysicalSubmissionPolicy) -> None:
        ...

    def receive(self, timeout_ms: int) -> bytes:
        ...

    def close(self) -> None:
        ...


class EventSource(Protocol):
    """Receive asynchronous A0 events independently of command ACKs."""

    def wait_event(self, timeout_ms: int) -> bytes:
        ...


class ValidatedSecretBoundary(Protocol):
    """One already-validated secret source, never a discovery mechanism."""

    handoff_count: int

    def handoff(self) -> memoryview:
        ...

    def close(self) -> None:
        ...

    @property
    def zeroized(self) -> bool:
        ...
