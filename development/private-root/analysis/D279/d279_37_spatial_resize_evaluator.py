#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Aggregate-only evaluator for the pinned libfprint spatial-resize hypothesis."""

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


class EvaluatorError(RuntimeError):
    """Invalid input, runner protocol, or aggregate contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvaluatorError(message)


def cleanse(buffer: bytearray) -> None:
    buffer[:] = b"\x00" * len(buffer)


@dataclass(frozen=True)
class Frame:
    role: str
    raster: Sequence[int]


class ResizeCountRunner(Protocol):
    def count(self, pixels: bytearray, width: int, height: int, factor: int) -> int:
        ...


ScaleRaster = Callable[[Sequence[int], str], bytearray]


class ExactLibfprintResizeNbisPipe:
    """Long-lived native-frame pipe; resize and NBIS both remain in C."""

    def __init__(self, executable: Path):
        require(executable.is_file(), "RESIZE_NBIS_EXECUTABLE_NOT_REGULAR")
        self._process = subprocess.Popen(
            [str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=None, bufsize=0,
        )
        self.closed = False

    def count(self, pixels: bytearray, width: int, height: int, factor: int) -> int:
        require(not self.closed, "RESIZE_NBIS_PIPE_CLOSED")
        require(self._process.stdin is not None and self._process.stdout is not None,
                "RESIZE_NBIS_PIPE_UNAVAILABLE")
        require(type(pixels) is bytearray and len(pixels) == width * height,
                "RESIZE_NBIS_IMAGE_LENGTH")
        require((width, height) in ((80, 64), (64, 80)),
                "RESIZE_NBIS_IMAGE_SHAPE")
        require(factor in SPATIAL_FACTORS, "RESIZE_NBIS_FACTOR")
        header = struct.pack("<4sHHII", b"NBR1", width, height, len(pixels), factor)
        try:
            self._process.stdin.write(header)
            self._process.stdin.write(pixels)
            self._process.stdin.flush()
            response = self._process.stdout.readline()
        except (BrokenPipeError, OSError) as error:
            raise EvaluatorError("RESIZE_NBIS_PIPE_IO_FAILURE") from error
        expected_prefix = f"NBISR {factor} ".encode()
        require(response.startswith(expected_prefix), "RESIZE_NBIS_PIPE_RESPONSE")
        try:
            count = int(response[len(expected_prefix):].strip())
        except ValueError as error:
            raise EvaluatorError("RESIZE_NBIS_PIPE_COUNT") from error
        require(count >= 0, "RESIZE_NBIS_NEGATIVE_COUNT")
        return count

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self._process.stdin is not None:
            self._process.stdin.close()
        try:
            status = self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Offline host-process safety bound only; there is no device path.
            self._process.terminate()
            try:
                status = self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                status = self._process.wait(timeout=2)
        require(status == 0, f"RESIZE_NBIS_PIPE_EXIT_{status}")

    def __enter__(self) -> "ExactLibfprintResizeNbisPipe":
        require(not self.closed, "RESIZE_NBIS_PIPE_CLOSED")
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()


def _aggregate(counts: list[int]) -> dict:
    require(bool(counts), "EMPTY_ROLE_GROUP")
    return {
        "frame_count": len(counts),
        "frames_with_minutiae": sum(value > 0 for value in counts),
        "frames_with_at_least_10_minutiae": sum(value >= 10 for value in counts),
        "minimum": min(counts),
        "median": statistics.median(counts),
        "maximum": max(counts),
    }


def evaluate(
    frames: Iterable[Frame],
    runner: ResizeCountRunner,
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
            counts = {role: [] for role in ROLES}
            for frame in owned_frames:
                pixels = scale_raster(frame.raster, intensity_scale)
                try:
                    require(type(pixels) is bytearray and len(pixels) == PIXELS,
                            "SCALE_RASTER_CONTRACT")
                    count = runner.count(pixels, WIDTH, HEIGHT, spatial_factor)
                    require(type(count) is int and count >= 0, "NBIS_COUNT_RESULT")
                    counts[frame.role].append(count)
                finally:
                    if type(pixels) is bytearray:
                        cleanse(pixels)
            variants.append(
                {
                    "variant": f"{intensity_scale}/identity/normal/spatial_x{spatial_factor}",
                    "intensity_scale": intensity_scale,
                    "orientation": "identity",
                    "polarity": "normal",
                    "spatial_factor": spatial_factor,
                    "groups": {role: _aggregate(counts[role]) for role in ROLES},
                }
            )
    require(len(variants) == 9, "VARIANT_MATRIX_SIZE")
    return {
        "schema": "D279_37_EXACT_LIBFPRINT_RESIZE_NBIS_AGGREGATE_V1",
        "resize": "FEDORA44_LIBFPRINT_1_94_100_FPI_IMAGE_RESIZE_PIXMAN_BILINEAR",
        "nbis": "FEDORA44_LIBFPRINT_1_94_100_G_LFSPARMS_V2_PPMM_0_FLAGS_0",
        "factor_1_control_bypasses_interpolation": True,
        "orientation": "identity",
        "polarity": "normal",
        "variant_count": len(variants),
        "frame_roles": {
            role: sum(frame.role == role for frame in owned_frames) for role in ROLES
        },
        "per_frame_counts_exported": False,
        "raster_exported": False,
        "template_exported": False,
        "variants": variants,
    }


def evaluate_target_attempt(
    rasters: Sequence[Sequence[int]],
    runner: ResizeCountRunner,
    scale_raster: ScaleRaster,
) -> dict:
    require(len(rasters) == 43, "TARGET_RASTER_COUNT")
    return evaluate(
        (Frame(role, raster)
         for role, raster in zip(TARGET_RASTER_ROLES, rasters)),
        runner,
        scale_raster,
    )
