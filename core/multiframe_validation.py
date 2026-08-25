# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline, bounded model of the target-observed multi-frame lifecycle.

This module deliberately has no USB or TLS implementation.  Its channel has a
single ``read_next`` method so that a future integration cannot accidentally
introduce a second physical reader.  D273 keeps live integration hard-disabled:
the table dataflow is now modelled, but a complete second target cycle and the
target timeout policy are not locally observed.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from core.post_d4 import (
    build_fdt_down,
    build_fdt_up,
    build_finger_image,
    build_nav_baseline,
    build_set_image,
)


class MultiFrameError(RuntimeError):
    """Fail-closed lifecycle error; callers must not retry or recover."""


#: Every ACK observed in the target post-arm multi-frame cycle carries status
#: 0x01 (D263 primary evidence: 0x32, 0x22, 0x34, 0x20, 0x50, 0x32).  The
#: permissive cold-start set (0x01, 0x07) is target-observed only for the
#: pre-TLS bring-up phases and must not leak into this seam.  Exactly one
#: status is accepted here; anything else fails closed.
EXPECTED_ACK_STATUS = 0x01


class InputKind(Enum):
    ACK = "ACK"
    IRQ = "IRQ"
    IMAGE = "IMAGE"
    NAV_RESPONSE = "NAV_RESPONSE"


@dataclass(frozen=True)
class DerivedFdtTable:
    """A 12-byte table tied to the IRQ and cycle that produced it."""

    value: bytes
    source_irq: int
    cycle: int

    def validate(self, expected_irq: int, expected_cycle: int) -> None:
        if len(self.value) != 12:
            raise MultiFrameError("fdt_table_length")
        if self.source_irq != expected_irq:
            raise MultiFrameError("fdt_table_source_irq")
        if self.cycle != expected_cycle:
            raise MultiFrameError("fdt_table_stale_cycle")


@dataclass(frozen=True)
class Input:
    kind: InputKind
    control: int | None = None
    status: int | None = None
    irq: int | None = None
    raster: tuple[int, ...] | None = None
    derived_fdt_table: DerivedFdtTable | None = None
    outer_length: int | None = None
    inner_length: int | None = None


class SingleReaderChannel(Protocol):
    """One owner for all A0 and decrypted-B0 application messages."""

    def write(self, frame: bytes, timeout_ms: int) -> None: ...

    def read_next(self, timeout_ms: int) -> Input: ...


MetricSink = Callable[[str, list[int]], dict[str, object]]


@dataclass(frozen=True)
class TimeoutPolicy:
    """Bounded offline candidate values, not a target-authorized live policy."""

    command_ms: int = 2_000
    image_ms: int = 5_000
    irq_ms: int = 15_000
    nav_ms: int = 2_000


@dataclass(frozen=True)
class MultiFrameContract:
    roles: tuple[str, ...]
    initial_up_table: DerivedFdtTable
    rearm_timestamps16: tuple[int, ...]
    timeouts: TimeoutPolicy = TimeoutPolicy()

    def validate(self) -> None:
        if not 2 <= len(self.roles) <= 8:
            raise MultiFrameError("sample_count_out_of_bounds")
        if len(set(self.roles)) != len(self.roles):
            raise MultiFrameError("sample_roles_not_unique")
        if any(not role or len(role) > 16 for role in self.roles):
            raise MultiFrameError("invalid_sample_role")
        try:
            self.initial_up_table.validate(0x0002, 0)
        except MultiFrameError as error:
            raise MultiFrameError("up_table_source_unresolved") from error
        if len(self.rearm_timestamps16) != len(self.roles) - 1:
            raise MultiFrameError("rearm_timestamp_count")
        if any(not 0 <= value <= 0xFFFF for value in self.rearm_timestamps16):
            raise MultiFrameError("rearm_timestamp_out_of_range")
        values = vars(self.timeouts).values()
        if any(not 1 <= value <= 30_000 for value in values):
            raise MultiFrameError("timeout_policy_out_of_bounds")


class BoundedMultiFrameRunner:
    """Execute the audited ordering against an injected offline channel.

    There are no loops other than the explicit sample bound, and no retry,
    reopen, reconnect, or recovery branch.  The last image is terminal: no
    further sensor-reaching command is emitted.  Every command ACK must echo
    the exact expected control and carry exactly ``EXPECTED_ACK_STATUS``.
    """

    def __init__(self, channel: SingleReaderChannel, metric_sink: MetricSink):
        self._channel = channel
        self._metric_sink = metric_sink

    def _read(self, expected: InputKind, timeout_ms: int) -> Input:
        item = self._channel.read_next(timeout_ms)
        if item.kind is not expected:
            raise MultiFrameError(
                f"unexpected_input:{item.kind.value}:expected:{expected.value}"
            )
        return item

    def _command_ack(self, frame: bytes, control: int, timeout_ms: int) -> None:
        self._channel.write(frame, timeout_ms)
        ack = self._read(InputKind.ACK, timeout_ms)
        if ack.control != control or ack.status != EXPECTED_ACK_STATUS:
            raise MultiFrameError(f"unexpected_ack:0x{control:02x}")

    def _consume(self, role: str, raster: tuple[int, ...]) -> dict[str, object]:
        if len(raster) != 5120 or any(not 0 <= value <= 4095 for value in raster):
            raise MultiFrameError("invalid_raster")
        transient = list(raster)
        try:
            result = self._metric_sink(role, transient)
            if not isinstance(result, dict):
                raise MultiFrameError("metric_sink_contract")
            for key, value in result.items():
                lowered = str(key).lower()
                if any(token in lowered for token in
                       ("pixel", "raster", "image", "template", "feature")):
                    raise MultiFrameError("biometric_material_in_metric_result")
                if isinstance(value, (bytes, bytearray, list, tuple, memoryview)):
                    raise MultiFrameError("non_scalar_metric_result")
            return dict(result)
        finally:
            transient[:] = [0] * len(transient)

    def run(
        self,
        contract: MultiFrameContract,
        first_image: tuple[int, ...],
    ) -> tuple[dict[str, object], ...]:
        contract.validate()
        metrics = [self._consume(contract.roles[0], first_image)]
        t = contract.timeouts
        current_up = contract.initial_up_table

        for cycle, role in enumerate(contract.roles[1:]):
            # Exact target-observed order.  The 0x50 stage is not optional.
            current_up.validate(0x0002, cycle)
            self._command_ack(build_fdt_up(current_up.value), 0x34, t.command_ms)
            irq_up = self._read(InputKind.IRQ, t.irq_ms)
            if irq_up.irq != 0x0200:
                raise MultiFrameError("expected_irq_0x0200")
            if irq_up.derived_fdt_table is None:
                raise MultiFrameError("down_table_missing_from_irq_0x0200")
            irq_up.derived_fdt_table.validate(0x0200, cycle)

            self._command_ack(build_set_image(), 0x20, t.command_ms)
            post_up = self._read(InputKind.IMAGE, t.image_ms)
            if post_up.raster is None:
                raise MultiFrameError("post_up_image_missing")
            # The no-finger image is intentionally validated then discarded.
            transient = list(post_up.raster)
            try:
                if len(transient) != 5120:
                    raise MultiFrameError("post_up_image_invalid")
            finally:
                transient[:] = [0] * len(transient)

            self._command_ack(build_nav_baseline(), 0x50, t.command_ms)
            nav = self._read(InputKind.NAV_RESPONSE, t.nav_ms)
            if (
                nav.control != 0x50
                or nav.outer_length != 2417
                or nav.inner_length != 2410
            ):
                raise MultiFrameError("nav_response_invalid")

            self._command_ack(
                build_fdt_down(
                    irq_up.derived_fdt_table.value,
                    contract.rearm_timestamps16[cycle],
                ),
                0x32,
                t.command_ms,
            )
            irq_down = self._read(InputKind.IRQ, t.irq_ms)
            if irq_down.irq != 0x0002:
                raise MultiFrameError("expected_irq_0x0002")
            if irq_down.derived_fdt_table is None:
                raise MultiFrameError("up_table_missing_from_irq_0x0002")
            irq_down.derived_fdt_table.validate(0x0002, cycle + 1)

            self._command_ack(build_finger_image(), 0x22, t.command_ms)
            image = self._read(InputKind.IMAGE, t.image_ms)
            if image.raster is None:
                raise MultiFrameError("finger_image_missing")
            metrics.append(self._consume(role, image.raster))
            current_up = irq_down.derived_fdt_table

        return tuple(metrics)
