#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Correct-role aggregate evaluator for pinned NBIS quality support."""

from __future__ import annotations

import statistics
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Protocol, Sequence


WIDTH = 80
HEIGHT = 64
PIXELS = WIDTH * HEIGHT
ROLES = ("baseline", "primary", "auxiliary")
TARGET_RASTER_ROLES = (
    "baseline",
) + tuple(role for _cycle in range(21) for role in ("primary", "auxiliary"))
INTENSITY_SCALES = ("fixed_12bit", "frame_minmax", "robust_p01_p99")
SPATIAL_FACTORS = (1, 2, 3)
METRIC_NAMES = (
    "minutiae_total",
    "minutiae_reliability_ge_025",
    "minutiae_reliability_ge_050",
    "quality_blocks_total",
    "quality_blocks_level_0",
    "quality_blocks_level_1",
    "quality_blocks_level_2",
    "quality_blocks_level_3",
    "quality_blocks_level_4",
    "quality_blocks_ab",
    "quality_blocks_a",
    "quality_blocks_ab_per_mille",
    "quality_blocks_a_per_mille",
    "minutiae_ab_fraction_per_mille",
    "minutiae_a_fraction_per_mille",
)


class QualityEvaluatorError(RuntimeError):
    """Invalid input, native helper response, or aggregate contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise QualityEvaluatorError(message)


def cleanse(buffer: bytearray) -> None:
    buffer[:] = b"\x00" * len(buffer)


def _per_mille(numerator: int, denominator: int) -> int:
    if denominator == 0:
        return 0
    return (numerator * 1000 + denominator // 2) // denominator


@dataclass(frozen=True)
class Frame:
    role: str
    raster: Sequence[int]


@dataclass(frozen=True)
class NbisQualityMetrics:
    minutiae_total: int
    minutiae_reliability_ge_025: int
    minutiae_reliability_ge_050: int
    quality_levels: tuple[int, int, int, int, int]
    map_width: int
    map_height: int

    def as_aggregate_inputs(self) -> dict[str, int]:
        require(self.minutiae_total >= 0, "NEGATIVE_MINUTIAE_TOTAL")
        require(0 <= self.minutiae_reliability_ge_050 <=
                self.minutiae_reliability_ge_025 <= self.minutiae_total,
                "MINUTIAE_RELIABILITY_ORDER")
        require(self.map_width > 0 and self.map_height > 0,
                "QUALITY_MAP_DIMENSIONS")
        require(len(self.quality_levels) == 5 and
                all(value >= 0 for value in self.quality_levels),
                "QUALITY_MAP_LEVELS")
        quality_total = self.map_width * self.map_height
        require(sum(self.quality_levels) == quality_total,
                "QUALITY_MAP_LEVEL_SUM")
        quality_ab = self.quality_levels[3] + self.quality_levels[4]
        quality_a = self.quality_levels[4]
        return {
            "minutiae_total": self.minutiae_total,
            "minutiae_reliability_ge_025": self.minutiae_reliability_ge_025,
            "minutiae_reliability_ge_050": self.minutiae_reliability_ge_050,
            "quality_blocks_total": quality_total,
            **{
                f"quality_blocks_level_{level}": value
                for level, value in enumerate(self.quality_levels)
            },
            "quality_blocks_ab": quality_ab,
            "quality_blocks_a": quality_a,
            "quality_blocks_ab_per_mille": _per_mille(quality_ab, quality_total),
            "quality_blocks_a_per_mille": _per_mille(quality_a, quality_total),
            "minutiae_ab_fraction_per_mille": _per_mille(
                self.minutiae_reliability_ge_025, self.minutiae_total
            ),
            "minutiae_a_fraction_per_mille": _per_mille(
                self.minutiae_reliability_ge_050, self.minutiae_total
            ),
        }


class QualityRunner(Protocol):
    def measure(
        self, pixels: bytearray, width: int, height: int, factor: int
    ) -> NbisQualityMetrics:
        ...


ScaleRaster = Callable[[Sequence[int], str], bytearray]


class ExactLibfprintResizeNbisQualityPipe:
    """Long-lived image pipe with no path, capture, secret, or USB interface."""

    def __init__(self, executable: Path):
        require(executable.is_file(), "RESIZE_QUALITY_EXECUTABLE_NOT_REGULAR")
        self._process = subprocess.Popen(
            [str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=None, bufsize=0,
        )
        self.closed = False

    def measure(
        self, pixels: bytearray, width: int, height: int, factor: int
    ) -> NbisQualityMetrics:
        require(not self.closed, "RESIZE_QUALITY_PIPE_CLOSED")
        require(self._process.stdin is not None and self._process.stdout is not None,
                "RESIZE_QUALITY_PIPE_UNAVAILABLE")
        require(type(pixels) is bytearray and len(pixels) == width * height,
                "RESIZE_QUALITY_IMAGE_LENGTH")
        require((width, height) in ((80, 64), (64, 80)),
                "RESIZE_QUALITY_IMAGE_SHAPE")
        require(factor in SPATIAL_FACTORS, "RESIZE_QUALITY_FACTOR")
        header = struct.pack("<4sHHII", b"NBQ1", width, height, len(pixels), factor)
        try:
            self._process.stdin.write(header)
            self._process.stdin.write(pixels)
            self._process.stdin.flush()
            response = self._process.stdout.readline()
        except (BrokenPipeError, OSError) as error:
            raise QualityEvaluatorError("RESIZE_QUALITY_PIPE_IO_FAILURE") from error
        fields = response.decode("ascii", errors="strict").split()
        require(len(fields) == 12 and fields[0] == "NBISQ",
                "RESIZE_QUALITY_PIPE_RESPONSE")
        try:
            values = [int(value) for value in fields[1:]]
        except ValueError as error:
            raise QualityEvaluatorError("RESIZE_QUALITY_PIPE_INTEGER") from error
        require(values[0] == factor, "RESIZE_QUALITY_PIPE_FACTOR")
        metrics = NbisQualityMetrics(
            minutiae_total=values[1],
            minutiae_reliability_ge_025=values[2],
            minutiae_reliability_ge_050=values[3],
            quality_levels=tuple(values[4:9]),
            map_width=values[9],
            map_height=values[10],
        )
        metrics.as_aggregate_inputs()
        return metrics

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self._process.stdin is not None:
            self._process.stdin.close()
        try:
            status = self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Offline host-process safety bound; no device path exists.
            self._process.terminate()
            try:
                status = self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                status = self._process.wait(timeout=2)
        require(status == 0, f"RESIZE_QUALITY_PIPE_EXIT_{status}")

    def __enter__(self) -> "ExactLibfprintResizeNbisQualityPipe":
        require(not self.closed, "RESIZE_QUALITY_PIPE_CLOSED")
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()


def _aggregate(values: list[int]) -> dict:
    require(bool(values), "EMPTY_METRIC_GROUP")
    return {
        "frames_nonzero": sum(value > 0 for value in values),
        "minimum": min(values),
        "median": statistics.median(values),
        "maximum": max(values),
    }


def _aggregate_group(frames: list[NbisQualityMetrics]) -> dict:
    require(bool(frames), "EMPTY_ROLE_GROUP")
    expanded = [frame.as_aggregate_inputs() for frame in frames]
    return {
        "frame_count": len(frames),
        "metrics": {
            name: _aggregate([frame[name] for frame in expanded])
            for name in METRIC_NAMES
        },
    }


def evaluate(
    frames: Iterable[Frame],
    runner: QualityRunner,
    scale_raster: ScaleRaster,
) -> dict:
    owned_frames = tuple(frames)
    require(bool(owned_frames), "EMPTY_FRAME_SET")
    require(all(frame.role in ROLES for frame in owned_frames), "FRAME_ROLE")
    require(all(any(frame.role == role for frame in owned_frames) for role in ROLES),
            "MISSING_ROLE_GROUP")
    variants = []

    for intensity_scale in INTENSITY_SCALES:
        for spatial_factor in SPATIAL_FACTORS:
            measured = {role: [] for role in ROLES}
            for frame in owned_frames:
                pixels = scale_raster(frame.raster, intensity_scale)
                try:
                    require(type(pixels) is bytearray and len(pixels) == PIXELS,
                            "SCALE_RASTER_CONTRACT")
                    metrics = runner.measure(
                        pixels, WIDTH, HEIGHT, spatial_factor
                    )
                    metrics.as_aggregate_inputs()
                    measured[frame.role].append(metrics)
                finally:
                    if type(pixels) is bytearray:
                        cleanse(pixels)
            variants.append({
                "variant": (
                    f"{intensity_scale}/identity/normal/"
                    f"spatial_x{spatial_factor}"
                ),
                "intensity_scale": intensity_scale,
                "orientation": "identity",
                "polarity": "normal",
                "spatial_factor": spatial_factor,
                "groups": {
                    role: _aggregate_group(measured[role]) for role in ROLES
                },
            })

    require(len(variants) == 9, "VARIANT_MATRIX_SIZE")
    return {
        "schema": "D279_39_EXACT_NBIS_QUALITY_AGGREGATE_V1",
        "resize": "FEDORA44_LIBFPRINT_1_94_100_FPI_IMAGE_RESIZE_PIXMAN_BILINEAR",
        "nbis": "FEDORA44_LIBFPRINT_1_94_100_G_LFSPARMS_V2_PPMM_0_FLAGS_0",
        "ppmm_zero_reliability_scope": (
            "QUALITY_MAP_TIER_ONLY_NOT_PHYSICAL_GRAYSCALE_RELIABILITY"
        ),
        "target_raster_role_order": "baseline,(primary,auxiliary)*21",
        "variant_count": len(variants),
        "frame_roles": {
            role: sum(frame.role == role for frame in owned_frames) for role in ROLES
        },
        "per_frame_metrics_exported": False,
        "quality_maps_exported": False,
        "raster_exported": False,
        "template_exported": False,
        "variants": variants,
    }


def evaluate_target_attempt(
    rasters: Sequence[Sequence[int]],
    runner: QualityRunner,
    scale_raster: ScaleRaster,
) -> dict:
    require(len(rasters) == 43, "TARGET_RASTER_COUNT")
    return evaluate(
        (Frame(role, raster)
         for role, raster in zip(TARGET_RASTER_ROLES, rasters)),
        runner,
        scale_raster,
    )
