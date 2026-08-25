# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline, bounded model of the target-observed multi-frame lifecycle.

This module deliberately has no USB or TLS implementation.  Its channel has a
single ``read_next`` method so that a future integration cannot accidentally
introduce a second physical reader.  D272 keeps that integration hard-disabled:
the source/freshness contract for the 0x34 table is not target-closed.
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


class InputKind(Enum):
    ACK = "ACK"
    IRQ = "IRQ"
    IMAGE = "IMAGE"
    NAV_RESPONSE = "NAV_RESPONSE"


@dataclass(frozen=True)
class Input:
    kind: InputKind
    control: int | None = None
    status: int | None = None
    irq: int | None = None
    raster: tuple[int, ...] | None = None


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
    up_table12: bytes
    down_table12: bytes
    rearm_timestamp16: int
    timeouts: TimeoutPolicy = TimeoutPolicy()

    def validate(self) -> None:
        if not 2 <= len(self.roles) <= 8:
            raise MultiFrameError("sample_count_out_of_bounds")
        if len(set(self.roles)) != len(self.roles):
            raise MultiFrameError("sample_roles_not_unique")
        if any(not role or len(role) > 16 for role in self.roles):
            raise MultiFrameError("invalid_sample_role")
        if len(self.up_table12) != 12:
            raise MultiFrameError("up_table_source_unresolved")
        if len(self.down_table12) != 12:
            raise MultiFrameError("down_table_invalid")
        if not 0 <= self.rearm_timestamp16 <= 0xFFFF:
            raise MultiFrameError("rearm_timestamp_out_of_range")
        values = vars(self.timeouts).values()
        if any(not 1 <= value <= 30_000 for value in values):
            raise MultiFrameError("timeout_policy_out_of_bounds")


class BoundedMultiFrameRunner:
    """Execute the audited ordering against an injected offline channel.

    There are no loops other than the explicit sample bound, and no retry,
    reopen, reconnect, or recovery branch.  The last image is terminal: no
    further sensor-reaching command is emitted.
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
        if ack.control != control or ack.status not in (0x01, 0x07):
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

        for role in contract.roles[1:]:
            # Exact target-observed order.  The 0x50 stage is not optional.
            self._command_ack(build_fdt_up(contract.up_table12), 0x34, t.command_ms)
            irq_up = self._read(InputKind.IRQ, t.irq_ms)
            if irq_up.irq != 0x0200:
                raise MultiFrameError("expected_irq_0x0200")

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
            if nav.control != 0x50:
                raise MultiFrameError("nav_response_invalid")

            self._command_ack(
                build_fdt_down(contract.down_table12, contract.rearm_timestamp16),
                0x32,
                t.command_ms,
            )
            irq_down = self._read(InputKind.IRQ, t.irq_ms)
            if irq_down.irq != 0x0002:
                raise MultiFrameError("expected_irq_0x0002")

            self._command_ack(build_finger_image(), 0x22, t.command_ms)
            image = self._read(InputKind.IMAGE, t.image_ms)
            if image.raster is None:
                raise MultiFrameError("finger_image_missing")
            metrics.append(self._consume(role, image.raster))

        return tuple(metrics)
