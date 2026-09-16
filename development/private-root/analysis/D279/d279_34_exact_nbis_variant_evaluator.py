#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline in-memory NBIS variant evaluator with aggregate-only results.

The exact NBIS adapter is a caller-supplied executable built from the pinned
Fedora 44/libfprint 1.94.100 tree. This module has no capture, PSK, USB,
production-driver or image-file path. Transformed 8-bit images cross only a
binary stdin pipe and are cleansed from the Python-owned mutable buffer after
each count.
"""

from __future__ import annotations

import statistics
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol, Sequence


WIDTH = 80
HEIGHT = 64
PIXELS = WIDTH * HEIGHT
ROLES = ("baseline", "primary", "auxiliary")
TARGET_RASTER_ROLES = (
    "baseline",
) + tuple(role for _cycle in range(21) for role in ("primary", "auxiliary"))
SCALES = ("fixed_12bit", "frame_minmax", "robust_p01_p99")
ORIENTATIONS = (
    "identity", "hflip", "vflip", "rot180",
    "transpose", "transpose_hflip", "transpose_vflip", "transpose_rot180",
)
POLARITIES = ("normal", "inverted")


class EvaluatorError(RuntimeError):
    """Invalid raster, runner protocol or aggregate contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvaluatorError(message)


def cleanse(buffer: bytearray) -> None:
    buffer[:] = b"\x00" * len(buffer)


@dataclass(frozen=True)
class Frame:
    role: str
    raster: Sequence[int]


class CountRunner(Protocol):
    def count(self, pixels: bytearray, width: int, height: int) -> int:
        ...


class ExactNbisPipe:
    """Long-lived stdin/stdout adapter; it never accepts image paths."""

    def __init__(self, executable: Path):
        require(executable.is_file(), "NBIS_EXECUTABLE_NOT_REGULAR")
        self._process = subprocess.Popen(
            [str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=None, bufsize=0,
        )
        self.closed = False

    def count(self, pixels: bytearray, width: int, height: int) -> int:
        require(not self.closed, "NBIS_PIPE_CLOSED")
        require(self._process.stdin is not None and self._process.stdout is not None,
                "NBIS_PIPE_UNAVAILABLE")
        require(type(pixels) is bytearray and len(pixels) == width * height,
                "NBIS_PIPE_IMAGE_LENGTH")
        require((width, height) in ((80, 64), (64, 80)),
                "NBIS_PIPE_IMAGE_SHAPE")
        header = struct.pack("<4sHHI", b"NBS1", width, height, len(pixels))
        try:
            self._process.stdin.write(header)
            self._process.stdin.write(pixels)
            self._process.stdin.flush()
            response = self._process.stdout.readline()
        except (BrokenPipeError, OSError) as error:
            raise EvaluatorError("NBIS_PIPE_IO_FAILURE") from error
        require(response.startswith(b"NBIS1 "), "NBIS_PIPE_RESPONSE")
        try:
            count = int(response[6:].strip())
        except ValueError as error:
            raise EvaluatorError("NBIS_PIPE_COUNT") from error
        require(count >= 0, "NBIS_NEGATIVE_COUNT")
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
            # Offline host-process bound only; no device-side inference exists.
            self._process.terminate()
            try:
                status = self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                status = self._process.wait(timeout=2)
        require(status == 0, f"NBIS_PIPE_EXIT_{status}")

    def __enter__(self) -> "ExactNbisPipe":
        require(not self.closed, "NBIS_PIPE_CLOSED")
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()


def scale_raster(raster: Sequence[int], method: str) -> bytearray:
    require(len(raster) == PIXELS, "RASTER_LENGTH")
    require(all(isinstance(value, int) and 0 <= value <= 0xFFF
                for value in raster), "RASTER_SAMPLE_RANGE")
    require(method in SCALES, "SCALE_METHOD")

    if method == "fixed_12bit":
        return bytearray((value * 255 + 2047) // 4095 for value in raster)

    if method == "frame_minmax":
        lower, upper = min(raster), max(raster)
    else:
        ordered = list(raster)
        try:
            ordered.sort()
            lower = ordered[(len(ordered) - 1) // 100]
            upper = ordered[((len(ordered) - 1) * 99) // 100]
        finally:
            for index in range(len(ordered)):
                ordered[index] = 0
    if upper == lower:
        return bytearray(PIXELS)
    span = upper - lower
    return bytearray(
        0 if value <= lower else 255 if value >= upper
        else ((value - lower) * 255 + span // 2) // span
        for value in raster
    )


def orient(pixels: bytearray, orientation: str) -> tuple[bytearray, int, int]:
    require(len(pixels) == PIXELS, "ORIENTATION_INPUT_LENGTH")
    require(orientation in ORIENTATIONS, "ORIENTATION")
    transposed = orientation.startswith("transpose")
    out_width, out_height = (HEIGHT, WIDTH) if transposed else (WIDTH, HEIGHT)
    output = bytearray(PIXELS)

    for source_y in range(HEIGHT):
        for source_x in range(WIDTH):
            if transposed:
                x, y = source_y, source_x
                suffix = orientation[len("transpose"):]
                if suffix in ("_hflip", "_rot180"):
                    x = out_width - 1 - x
                if suffix in ("_vflip", "_rot180"):
                    y = out_height - 1 - y
            else:
                x, y = source_x, source_y
                if orientation in ("hflip", "rot180"):
                    x = out_width - 1 - x
                if orientation in ("vflip", "rot180"):
                    y = out_height - 1 - y
            output[y * out_width + x] = pixels[source_y * WIDTH + source_x]
    return output, out_width, out_height


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


def evaluate(frames: Iterable[Frame], runner: CountRunner) -> dict:
    owned_frames = tuple(frames)
    require(bool(owned_frames), "EMPTY_FRAME_SET")
    require(all(frame.role in ROLES for frame in owned_frames), "FRAME_ROLE")
    require(all(any(frame.role == role for frame in owned_frames) for role in ROLES),
            "MISSING_ROLE_GROUP")
    variants = []

    for scale in SCALES:
        for orientation in ORIENTATIONS:
            for polarity in POLARITIES:
                counts = {role: [] for role in ROLES}
                for frame in owned_frames:
                    scaled = scale_raster(frame.raster, scale)
                    transformed = None
                    try:
                        transformed, width, height = orient(scaled, orientation)
                        if polarity == "inverted":
                            for index, value in enumerate(transformed):
                                transformed[index] = 255 - value
                        count = runner.count(transformed, width, height)
                        require(isinstance(count, int) and count >= 0,
                                "NBIS_COUNT_RESULT")
                        counts[frame.role].append(count)
                    finally:
                        cleanse(scaled)
                        if transformed is not None:
                            cleanse(transformed)
                variants.append({
                    "variant": f"{scale}/{orientation}/{polarity}",
                    "scale": scale,
                    "orientation": orientation,
                    "polarity": polarity,
                    "groups": {role: _aggregate(counts[role]) for role in ROLES},
                })
    require(len(variants) == 48, "VARIANT_MATRIX_SIZE")
    return {
        "schema": "D279_34_EXACT_NBIS_AGGREGATE_V1",
        "nbis": "FEDORA44_LIBFPRINT_1_94_100_G_LFSPARMS_V2_PPMM_0_FLAGS_0",
        "variant_count": len(variants),
        "frame_roles": {
            role: sum(frame.role == role for frame in owned_frames) for role in ROLES
        },
        "per_frame_counts_exported": False,
        "raster_exported": False,
        "template_exported": False,
        "variants": variants,
    }


def evaluate_target_attempt(rasters: Sequence[Sequence[int]],
                            runner: CountRunner) -> dict:
    require(len(rasters) == 43, "TARGET_RASTER_COUNT")
    return evaluate(
        (Frame(role, raster)
         for role, raster in zip(TARGET_RASTER_ROLES, rasters)), runner
    )
