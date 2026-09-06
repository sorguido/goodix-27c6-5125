#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Aggregate-only causal comparison of Rockytkg R1/R2 with NBIS and SIGFM."""

from __future__ import annotations

import itertools
import statistics
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

import d279_39_nbis_quality_evaluator as quality


WIDTH = 80
HEIGHT = 64
PIXELS = WIDTH * HEIGHT
ROLES = quality.TARGET_RASTER_ROLES
CHECKPOINTS = (
    "R1_ROCKY_COMMON_NATIVE_80X64",
    "R2_ROCKY_SIGFM_CHAIN_NATIVE_80X64",
)
R0_SUMMARY_SHA256 = "7dfb2feab05a11b01830903c773211d811f5b9a55aac35bd478fd57e4707f90b"
R0_SIGNED_CONTROL = {
    "fingerprint_frames_with_minutiae_nonzero": 34,
    "fingerprint_frames_with_quality_tier_b_or_a_minutiae": 10,
    "fingerprint_frames_with_quality_tier_a_minutiae": 2,
    "bozorth_computable_not_reported_by_r0": True,
    "pairwise_scores_not_reported_by_r0": True,
}


class ComparisonError(RuntimeError):
    """Invalid input, helper response, or aggregate contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ComparisonError(message)


def cleanse(buffer: bytearray) -> None:
    buffer[:] = b"\x00" * len(buffer)


def _read_exact(stream, length: int, label: str) -> bytes:
    chunks = []
    remaining = length
    while remaining:
        chunk = stream.read(remaining)
        require(bool(chunk), label)
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class _Pipe:
    def __init__(self, executable: Path, label: str):
        require(executable.is_file() and not executable.is_symlink(), f"{label}_EXECUTABLE")
        self.label = label
        self.process = subprocess.Popen(
            [str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=None, bufsize=0,
        )
        self.closed = False

    def _write(self, value: bytes | bytearray) -> None:
        require(not self.closed and self.process.stdin is not None, f"{self.label}_PIPE_CLOSED")
        try:
            self.process.stdin.write(value)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise ComparisonError(f"{self.label}_PIPE_WRITE") from error

    def _line(self) -> list[str]:
        require(not self.closed and self.process.stdout is not None, f"{self.label}_PIPE_CLOSED")
        try:
            response = self.process.stdout.readline()
            return response.decode("ascii", errors="strict").split()
        except (OSError, UnicodeError) as error:
            raise ComparisonError(f"{self.label}_PIPE_RESPONSE") from error

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            status = self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                status = self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                status = self.process.wait(timeout=2)
        require(status == 0, f"{self.label}_PIPE_EXIT_{status}")

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()


class RockyPreprocessPipe(_Pipe):
    def __init__(self, executable: Path):
        super().__init__(executable, "ROCKY_IMGPROC")

    @staticmethod
    def _u16le(raster: Sequence[int]) -> bytearray:
        require(len(raster) == PIXELS, "RASTER_LENGTH")
        require(all(type(value) is int and 0 <= value <= 4095 for value in raster),
                "RASTER_RANGE")
        return bytearray(struct.pack(f"<{PIXELS}H", *raster))

    def preprocess(self, raster: Sequence[int], baseline: Sequence[int], checkpoint: str) -> bytearray:
        require(checkpoint in CHECKPOINTS, "CHECKPOINT")
        mode = CHECKPOINTS.index(checkpoint) + 1
        baseline_bytes = self._u16le(baseline)
        raster_bytes = self._u16le(raster)
        try:
            self._write(struct.pack("<4sIII", b"RIP1", mode, len(raster_bytes), 0))
            self._write(baseline_bytes)
            self._write(raster_bytes)
            require(self.process.stdout is not None, "ROCKY_IMGPROC_STDOUT")
            header = _read_exact(self.process.stdout, 12, "ROCKY_IMGPROC_TRUNCATED_HEADER")
            magic, returned_mode, length = struct.unpack("<4sII", header)
            require(magic == b"RIPO" and returned_mode == mode and length == PIXELS,
                    "ROCKY_IMGPROC_RESPONSE")
            return bytearray(_read_exact(
                self.process.stdout, length, "ROCKY_IMGPROC_TRUNCATED_RASTER"
            ))
        finally:
            cleanse(baseline_bytes)
            cleanse(raster_bytes)


@dataclass(frozen=True)
class NbisSample:
    identifier: int
    metrics: quality.NbisQualityMetrics
    bozorth_computable: bool


@dataclass(frozen=True)
class SigfmSample:
    identifier: int
    keypoints: int
    operational_gate_passed: bool


@dataclass(frozen=True)
class PairScore:
    eligible: bool
    score: int


class NbisPairPipe(_Pipe):
    def __init__(self, executable: Path):
        super().__init__(executable, "NBIS_PAIR")
        self.next_identifier = 0

    def extract(self, pixels: bytearray) -> NbisSample:
        require(type(pixels) is bytearray and len(pixels) == PIXELS, "NBIS_INPUT")
        identifier = self.next_identifier
        self.next_identifier += 1
        require(identifier < 128, "NBIS_SAMPLE_LIMIT")
        self._write(struct.pack("<4sIII", b"NBX1", identifier, len(pixels), 0))
        self._write(pixels)
        fields = self._line()
        require(len(fields) == 13 and fields[0] == "NBISX", "NBIS_EXTRACT_RESPONSE")
        try:
            values = [int(value) for value in fields[1:]]
        except ValueError as error:
            raise ComparisonError("NBIS_EXTRACT_INTEGER") from error
        require(values[0] == identifier and values[-1] in (0, 1), "NBIS_EXTRACT_ID")
        metrics = quality.NbisQualityMetrics(
            minutiae_total=values[1],
            minutiae_reliability_ge_025=values[2],
            minutiae_reliability_ge_050=values[3],
            quality_levels=tuple(values[4:9]),
            map_width=values[9], map_height=values[10],
        )
        metrics.as_aggregate_inputs()
        require((metrics.minutiae_total >= 10) == bool(values[11]), "NBIS_COMPUTABLE_FLAG")
        return NbisSample(identifier, metrics, bool(values[11]))

    def match(self, first: NbisSample, second: NbisSample) -> PairScore:
        self._write(struct.pack("<4sIII", b"NBM1", first.identifier, second.identifier, 0))
        fields = self._line()
        require(len(fields) == 5 and fields[0] == "NBISM", "NBIS_MATCH_RESPONSE")
        try:
            values = [int(value) for value in fields[1:]]
        except ValueError as error:
            raise ComparisonError("NBIS_MATCH_INTEGER") from error
        require(values[0:2] == [first.identifier, second.identifier] and values[2] in (0, 1),
                "NBIS_MATCH_ID")
        require(values[3] >= 0, "NBIS_MATCH_SCORE")
        expected = first.bozorth_computable and second.bozorth_computable
        require(bool(values[2]) == expected, "NBIS_MATCH_ELIGIBILITY")
        return PairScore(bool(values[2]), values[3])


class SigfmPairPipe(_Pipe):
    def __init__(self, executable: Path):
        super().__init__(executable, "SIGFM_PAIR")
        self.next_identifier = 0

    def extract(self, pixels: bytearray) -> SigfmSample:
        require(type(pixels) is bytearray and len(pixels) == PIXELS, "SIGFM_INPUT")
        identifier = self.next_identifier
        self.next_identifier += 1
        require(identifier < 128, "SIGFM_SAMPLE_LIMIT")
        self._write(struct.pack("<4sIII", b"SFX1", identifier, len(pixels), 0))
        self._write(pixels)
        fields = self._line()
        require(len(fields) == 4 and fields[0] == "SIGFMX", "SIGFM_EXTRACT_RESPONSE")
        try:
            values = [int(value) for value in fields[1:]]
        except ValueError as error:
            raise ComparisonError("SIGFM_EXTRACT_INTEGER") from error
        require(values[0] == identifier and values[1] >= 0 and values[2] in (0, 1),
                "SIGFM_EXTRACT_VALUES")
        require((values[1] >= 25) == bool(values[2]), "SIGFM_GATE_FLAG")
        return SigfmSample(identifier, values[1], bool(values[2]))

    def match(self, first: SigfmSample, second: SigfmSample) -> PairScore:
        self._write(struct.pack("<4sIII", b"SFM1", first.identifier, second.identifier, 0))
        fields = self._line()
        require(len(fields) == 5 and fields[0] == "SIGFMM", "SIGFM_MATCH_RESPONSE")
        try:
            values = [int(value) for value in fields[1:]]
        except ValueError as error:
            raise ComparisonError("SIGFM_MATCH_INTEGER") from error
        require(values[0:2] == [first.identifier, second.identifier] and values[2] in (0, 1),
                "SIGFM_MATCH_ID")
        require(values[3] >= 0, "SIGFM_MATCH_SCORE")
        expected = first.operational_gate_passed and second.operational_gate_passed
        require(bool(values[2]) == expected, "SIGFM_MATCH_ELIGIBILITY")
        return PairScore(bool(values[2]), values[3])


class PreprocessRunner(Protocol):
    def preprocess(self, raster: Sequence[int], baseline: Sequence[int], checkpoint: str) -> bytearray:
        ...


class NbisRunner(Protocol):
    def extract(self, pixels: bytearray) -> NbisSample:
        ...
    def match(self, first: NbisSample, second: NbisSample) -> PairScore:
        ...


class SigfmRunner(Protocol):
    def extract(self, pixels: bytearray) -> SigfmSample:
        ...
    def match(self, first: SigfmSample, second: SigfmSample) -> PairScore:
        ...


def _distribution(values: list[int]) -> dict:
    if not values:
        return {"count": 0, "nonzero": 0, "minimum": None, "median": None, "maximum": None}
    return {
        "count": len(values), "nonzero": sum(value > 0 for value in values),
        "minimum": min(values), "median": statistics.median(values), "maximum": max(values),
    }


def _pair_sets(samples: Sequence, roles: Sequence[str]) -> dict[str, list[tuple]]:
    primary = [sample for sample, role in zip(samples, roles) if role == "primary"]
    auxiliary = [sample for sample, role in zip(samples, roles) if role == "auxiliary"]
    require(len(primary) == 21 and len(auxiliary) == 21, "PAIR_ROLE_CARDINALITY")
    return {
        "paired_cycle_primary_to_auxiliary": list(zip(primary, auxiliary)),
        "within_primary": list(itertools.combinations(primary, 2)),
        "within_auxiliary": list(itertools.combinations(auxiliary, 2)),
        "all_cross_role_primary_to_auxiliary": list(itertools.product(primary, auxiliary)),
    }


def _pair_aggregate(runner, pairs: list[tuple], threshold: int,
                    cache: dict[tuple[int, int], PairScore]) -> dict:
    results = []
    for first, second in pairs:
        # Neither NBIS/Bozorth nor SIGFM is assumed symmetric here.  Evaluate
        # both directions so that an arbitrary enrollment/probe ordering cannot
        # favour either extractor on this single-session comparison dataset.
        for probe, enrolled in ((first, second), (second, first)):
            key = (probe.identifier, enrolled.identifier)
            if key not in cache:
                cache[key] = runner.match(probe, enrolled)
            results.append(cache[key])
    eligible = [result.score for result in results if result.eligible]
    all_scores = [result.score for result in results]
    return {
        "logical_pair_count": len(pairs),
        "directed_score_count": len(results),
        "feature_eligible_directed_score_count": len(eligible),
        "score_nonzero_directed_count": sum(score > 0 for score in all_scores),
        "score_at_or_above_reference_threshold_directed_count": sum(
            score >= threshold for score in all_scores
        ),
        "reference_threshold_not_target_validated": threshold,
        "all_pair_scores": _distribution(all_scores),
        "feature_eligible_pair_scores": _distribution(eligible),
    }


def _nbis_groups(samples: Sequence[NbisSample]) -> dict:
    return {
        role: {
            **quality._aggregate_group([
                sample.metrics for sample, sample_role in zip(samples, ROLES)
                if sample_role == role
            ]),
            "bozorth_computable_frame_count": sum(
                sample.bozorth_computable for sample, sample_role in zip(samples, ROLES)
                if sample_role == role
            ),
        }
        for role in quality.ROLES
    }


def _sigfm_groups(samples: Sequence[SigfmSample]) -> dict:
    result = {}
    for role in quality.ROLES:
        selected = [sample for sample, sample_role in zip(samples, ROLES) if sample_role == role]
        result[role] = {
            "frame_count": len(selected),
            "frames_with_keypoints_nonzero": sum(sample.keypoints > 0 for sample in selected),
            "frames_passing_fork_operational_gate_ge_25": sum(
                sample.operational_gate_passed for sample in selected
            ),
            "keypoint_count": _distribution([sample.keypoints for sample in selected]),
        }
    return result


def evaluate_target_attempt(rasters: Sequence[Sequence[int]], preprocess: PreprocessRunner,
                            nbis: NbisRunner, sigfm: SigfmRunner) -> dict:
    require(len(rasters) == 43, "TARGET_RASTER_COUNT")
    require(all(len(raster) == PIXELS for raster in rasters), "TARGET_RASTER_LENGTH")
    require(all(type(value) is int and 0 <= value <= 4095
                for raster in rasters for value in raster), "TARGET_RASTER_RANGE")
    baseline = rasters[0]
    checkpoints = []
    for checkpoint in CHECKPOINTS:
        nbis_samples = []
        sigfm_samples = []
        for raster in rasters:
            pixels = preprocess.preprocess(raster, baseline, checkpoint)
            try:
                require(type(pixels) is bytearray and len(pixels) == PIXELS,
                        "PREPROCESS_OUTPUT")
                # Both extractors receive this exact byte sequence before cleansing.
                nbis_samples.append(nbis.extract(pixels))
                sigfm_samples.append(sigfm.extract(pixels))
            finally:
                cleanse(pixels)
        nbis_pairs = _pair_sets(nbis_samples, ROLES)
        sigfm_pairs = _pair_sets(sigfm_samples, ROLES)
        nbis_cache: dict[tuple[int, int], PairScore] = {}
        sigfm_cache: dict[tuple[int, int], PairScore] = {}
        checkpoints.append({
            "checkpoint": checkpoint,
            "native_shape": "80x64",
            "resize_applied": False,
            "same_preprocessed_raster_delivered_to_both_extractors": True,
            "nbis": {
                "groups": _nbis_groups(nbis_samples),
                "same_session_pairs": {
                    name: _pair_aggregate(nbis, pairs, 40, nbis_cache)
                    for name, pairs in nbis_pairs.items()
                },
            },
            "sigfm": {
                "groups": _sigfm_groups(sigfm_samples),
                "same_session_pairs": {
                    name: _pair_aggregate(sigfm, pairs, 20, sigfm_cache)
                    for name, pairs in sigfm_pairs.items()
                },
            },
        })
    return {
        "schema": "D279_48_ROCKY_NBIS_SIGFM_COMPARISON_AGGREGATE_V1",
        "question": "PREPROCESSING_LIMIT_VS_SMALL_AREA_FEATURE_EXTRACTOR_LIMIT",
        "target_raster_role_order": "baseline,(primary,auxiliary)*21",
        "frame_roles": {"baseline": 1, "primary": 21, "auxiliary": 21},
        "baseline_semantics": "ATTEMPT02_B0_EXPERIMENTAL_REFERENCE_NOT_PROVEN_ROCKY_NO_FINGER_EQUIVALENT",
        "rocky_source_commit": "227eba219fa9e3fbac5bd59aca79f624f67cd11b",
        "sigfm_source_commit": "7ebe0c809b4d1df3400e84299a4ec4acdea84590",
        "fixed_parameters": {
            "baseline_offset": 2048, "flatfield_radius": 12,
            "percentile_low": 1, "percentile_high": 99,
            "r2_unsharp_boost": "0.8f", "r2_unsharp_sigma": "1.5f",
        },
        "historical_r0": {"source_summary_sha256": R0_SUMMARY_SHA256, **R0_SIGNED_CONTROL},
        "checkpoint_count": len(checkpoints),
        "checkpoints": checkpoints,
        "decision_classification": "PENDING_AUTHENTIC_AGGREGATE_REVIEW_A_B_C_OR_D",
        "dataset_limitations": {
            "single_session_finger_context_only": True,
            "different_finger_control_available": False,
            "far_frr_or_accuracy_claim_permitted": False,
            "production_threshold_validation_permitted": False,
        },
        "per_frame_metrics_exported": False,
        "rasters_exported": False,
        "minutiae_exported": False,
        "sigfm_keypoints_or_descriptors_exported": False,
        "templates_exported": False,
    }
