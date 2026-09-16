#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exact aggregate-only replay of the Rockytkg dynamic enrollment policy."""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path
from typing import Sequence


WIDTH = 80
HEIGHT = 64
PIXELS = WIDTH * HEIGHT
MIN_DISTINCT = 3
MAX_STAGES = 8
DUPLICATE_STREAK_TO_CONVERGE = 2
MAD_THRESHOLD = 8.0
# For integer 8-bit rasters, sum / 5120 < 8.0 is exactly sum < 40960.
DUPLICATE_SUM_EXCLUSIVE_LIMIT = int(MAD_THRESHOLD * PIXELS)


class DynamicPolicyError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DynamicPolicyError(message)


def cleanse(buffer: bytearray | None) -> None:
    if buffer is not None:
        buffer[:] = b"\x00" * len(buffer)


class R2Pipe:
    """Owned subprocess exposing only the production pure R2 transform."""

    def __init__(self, executable: Path):
        require(executable.is_file() and not executable.is_symlink(),
                "R2_HELPER_NOT_REGULAR")
        self._process = subprocess.Popen(
            [str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0,
        )

    @staticmethod
    def _encode(samples: Sequence[int]) -> bytearray:
        require(len(samples) == PIXELS, "R2_INPUT_SAMPLE_COUNT")
        require(all(type(value) is int and 0 <= value <= 4095 for value in samples),
                "R2_INPUT_SAMPLE_RANGE")
        encoded = bytearray(PIXELS * 2)
        for index, value in enumerate(samples):
            struct.pack_into("<H", encoded, index * 2, value)
        return encoded

    @staticmethod
    def _read_exact(stream, length: int) -> bytes:
        result = bytearray()
        while len(result) < length:
            chunk = stream.read(length - len(result))
            if not chunk:
                raise DynamicPolicyError("R2_HELPER_SHORT_OUTPUT")
            result.extend(chunk)
        return bytes(result)

    def preprocess(self, baseline: Sequence[int], frame: Sequence[int]) -> bytearray:
        require(self._process.poll() is None, "R2_HELPER_NOT_RUNNING")
        baseline_bytes = self._encode(baseline)
        frame_bytes = self._encode(frame)
        try:
            assert self._process.stdin is not None
            assert self._process.stdout is not None
            self._process.stdin.write(b"D56R" + struct.pack("<I", PIXELS * 2))
            self._process.stdin.write(baseline_bytes)
            self._process.stdin.write(frame_bytes)
            self._process.stdin.flush()
            header = self._read_exact(self._process.stdout, 8)
            require(header[:4] == b"D56O" and
                    struct.unpack("<I", header[4:])[0] == PIXELS,
                    "R2_HELPER_RESPONSE_HEADER")
            return bytearray(self._read_exact(self._process.stdout, PIXELS))
        finally:
            cleanse(baseline_bytes)
            cleanse(frame_bytes)

    def close(self) -> None:
        if self._process.poll() is None:
            assert self._process.stdin is not None
            self._process.stdin.close()
        stderr = self._process.stderr.read() if self._process.stderr else b""
        status = self._process.wait(timeout=5)
        require(status == 0, f"R2_HELPER_EXIT_{status}")
        require(stderr == b"", "R2_HELPER_STDERR_NOT_EMPTY")

    def __enter__(self) -> "R2Pipe":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is None:
            self.close()
        elif self._process.poll() is None:
            self._process.kill()
            self._process.wait(timeout=5)


def _is_duplicate(frame: bytearray, accepted: Sequence[bytearray]) -> bool:
    for previous in accepted:
        difference_sum = sum(abs(left - right)
                             for left, right in zip(frame, previous))
        if difference_sum < DUPLICATE_SUM_EXCLUSIVE_LIMIT:
            return True
    return False


def replay_dynamic_policy(frames: Sequence[bytearray]) -> dict:
    """Replay the exact default Rockytkg state transition on ordered R2 frames."""

    require(len(frames) > 0, "NO_ENROLLMENT_FRAMES")
    require(all(type(frame) is bytearray and len(frame) == PIXELS
                for frame in frames), "ENROLLMENT_FRAME_SHAPE")
    accepted: list[bytearray] = []
    per_stage = []
    duplicate_reject_count = 0
    duplicate_streak = 0
    convergence_stage = None
    final_selected_stage_count = None
    terminal_reason = "INPUT_EXHAUSTED_WITHOUT_COMPLETION"
    try:
        for stage_index, frame in enumerate(frames, start=1):
            duplicate = bool(accepted) and _is_duplicate(frame, accepted)
            if duplicate:
                duplicate_streak += 1
                if (len(accepted) >= MIN_DISTINCT and
                        len(accepted) < MAX_STAGES and
                        duplicate_streak >= DUPLICATE_STREAK_TO_CONVERGE):
                    classification = "CONVERGE"
                    convergence_stage = stage_index
                    final_selected_stage_count = len(accepted) + 1
                    terminal_reason = "DUPLICATE_STREAK_CONVERGENCE"
                else:
                    classification = "DUPLICATE"
                    duplicate_reject_count += 1
            else:
                duplicate_streak = 0
                accepted.append(bytearray(frame))
                classification = "ACCEPT"
                if len(accepted) == MAX_STAGES:
                    final_selected_stage_count = MAX_STAGES
                    terminal_reason = "MAX_STAGE_REACHED"
            per_stage.append({
                "stage_index": stage_index,
                "classification": classification,
            })
            if final_selected_stage_count is not None:
                break

        return {
            "schema": "D279_56_ROCKYTKG_DYNAMIC_ENROLLMENT_REPLAY_V1",
            "policy": {
                "minimum_distinct_samples": MIN_DISTINCT,
                "maximum_delivered_stages": MAX_STAGES,
                "duplicate_streak_to_converge": DUPLICATE_STREAK_TO_CONVERGE,
                "mad_duplicate_threshold": "8.0_EXCLUSIVE",
            },
            "input_primary_stage_count": len(frames),
            "evaluated_stage_count": len(per_stage),
            "distinct_sample_accept_count": len(accepted),
            "first_possible_convergence_stage": convergence_stage,
            "final_selected_stage_count": final_selected_stage_count,
            "duplicate_reject_count": duplicate_reject_count,
            "max_stage_reached": terminal_reason == "MAX_STAGE_REACHED",
            "terminal_reason": terminal_reason,
            "per_stage": per_stage,
            "numeric_per_stage_mad_exported": False,
            "raster_or_biometric_feature_exported": False,
        }
    finally:
        for frame in accepted:
            cleanse(frame)


def evaluate_target_attempt(rasters: Sequence[Sequence[int]], r2: R2Pipe) -> dict:
    require(len(rasters) == 43, "TARGET_RASTER_COUNT")
    require(all(len(raster) == PIXELS for raster in rasters),
            "TARGET_RASTER_LENGTH")
    require(all(type(value) is int and 0 <= value <= 4095
                for raster in rasters for value in raster),
            "TARGET_RASTER_RANGE")
    baseline = rasters[0]
    primary_rasters = rasters[1::2]
    require(len(primary_rasters) == 21, "TARGET_PRIMARY_RASTER_COUNT")
    processed: list[bytearray] = []
    try:
        for raster in primary_rasters:
            processed.append(r2.preprocess(baseline, raster))
        result = replay_dynamic_policy(processed)
        result.update({
            "target_raster_role_order": "baseline,(primary,auxiliary)*21",
            "preprocessing": "ROCKYTKG_R2_D279_49_PRODUCTION_COMPONENT",
            "baseline_semantics":
                "ATTEMPT02_B0_EXPERIMENTAL_REFERENCE_NOT_PROVEN_ROCKY_NO_FINGER_EQUIVALENT",
            "auxiliary_rasters_used": False,
            "dataset_single_session_same_finger": True,
            "production_policy_validated": False,
        })
        return result
    finally:
        for frame in processed:
            cleanse(frame)
