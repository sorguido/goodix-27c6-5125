# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Read-only, fail-closed provider for the target-observed Goodix FDT cache.

The provider accepts one explicit path and one explicit 64-byte target OTP
identity.  It never searches host paths, writes the cache, or synthesizes a
fallback seed.  The layout and little-endian CRC storage are the exact form
verified against the D255 APP12509 cache.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path

from src.goodix5125_cleanroom import crc32_mpeg2


CACHE_SIZE = 13_520
OTP_SIZE = 64
FDT12_SIZE = 12
NAV_SIZE = 3_200
IMAGE_SIZE = 10_240
CRC_SIZE = 4

OTP_OFFSET = 0
FDT12_OFFSET = OTP_OFFSET + OTP_SIZE
NAV_OFFSET = FDT12_OFFSET + FDT12_SIZE
IMAGE_OFFSET = NAV_OFFSET + NAV_SIZE
CRC_OFFSET = IMAGE_OFFSET + IMAGE_SIZE

if CRC_OFFSET + CRC_SIZE != CACHE_SIZE:  # pragma: no cover - import invariant
    raise RuntimeError("Goodix cache layout constants are inconsistent")


SEED_PROVIDER_PASS = "PASS"
SEED_PROVIDER_FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True)
class SeedProvenance:
    """Non-secret provenance for one explicit cache input."""

    explicit_source_path: str
    file_size: int | None
    file_sha256: str | None
    layout: str
    crc_algorithm: str
    crc_byte_order: str
    crc_valid: bool
    otp_binding: str
    otp_sha256: str | None
    fdt12_sha256: str | None
    read_only: bool = True

    def redacted(self) -> dict[str, object]:
        """Return provenance suitable for reports without path or raw fields."""
        return {
            "file_size": self.file_size,
            "file_sha256": self.file_sha256,
            "layout": self.layout,
            "crc_algorithm": self.crc_algorithm,
            "crc_byte_order": self.crc_byte_order,
            "crc_valid": self.crc_valid,
            "otp_binding": self.otp_binding,
            "otp_identity_reference": "EXPLICIT_CALLER_INPUT_REDACTED",
            "fdt12_sha256": self.fdt12_sha256,
            "read_only": self.read_only,
            "source_path": "EXPLICIT_INPUT_PATH_REDACTED",
        }


@dataclass(frozen=True)
class SeedProviderResult:
    status: str
    fdt12: bytes | None
    provenance: SeedProvenance
    failure_reason: str | None

    @property
    def ok(self) -> bool:
        return self.status == SEED_PROVIDER_PASS and self.fdt12 is not None

    def require_seed(self) -> bytes:
        if not self.ok:
            raise SeedProviderFailure(self.failure_reason or "SEED_PROVIDER_FAIL_CLOSED")
        return bytes(self.fdt12)


class SeedProviderFailure(ValueError):
    """Raised only when a caller explicitly requires a failed result."""


def _provenance(
    source: Path,
    *,
    size: int | None = None,
    file_sha256: str | None = None,
    crc_valid: bool = False,
    otp_binding: str = "NOT_CHECKED",
    otp_sha256: str | None = None,
    fdt12_sha256: str | None = None,
) -> SeedProvenance:
    return SeedProvenance(
        explicit_source_path=os.fspath(source),
        file_size=size,
        file_sha256=file_sha256,
        layout="OTP64+FDT12+NAV3200+IMAGE10240+CRC32_MPEG2_LE4",
        crc_algorithm="CRC-32/MPEG-2",
        crc_byte_order="little",
        crc_valid=crc_valid,
        otp_binding=otp_binding,
        otp_sha256=otp_sha256,
        fdt12_sha256=fdt12_sha256,
    )


def _failure(
    source: Path,
    reason: str,
    **provenance_fields: object,
) -> SeedProviderResult:
    return SeedProviderResult(
        status=SEED_PROVIDER_FAIL_CLOSED,
        fdt12=None,
        provenance=_provenance(source, **provenance_fields),
        failure_reason=reason,
    )


def provide_fdt12(cache_path: str | os.PathLike[str], expected_otp64: bytes) -> SeedProviderResult:
    """Validate one cache and return only its FDT12 field.

    Expected validation failures are represented as ``FAIL_CLOSED`` results so
    callers can persist a precise reason without catching broad exceptions.
    No failure path returns seed material.
    """

    source = Path(cache_path)
    if not isinstance(expected_otp64, bytes) or len(expected_otp64) != OTP_SIZE:
        return _failure(source, "EXPECTED_OTP64_INVALID")
    otp_sha256 = hashlib.sha256(expected_otp64).hexdigest()

    try:
        if source.is_symlink():
            return _failure(source, "CACHE_SYMLINK_FORBIDDEN", otp_sha256=otp_sha256)
        stat_before = source.stat()
        if not source.is_file():
            return _failure(source, "CACHE_NOT_REGULAR_FILE", otp_sha256=otp_sha256)
        data = source.read_bytes()
        stat_after = source.stat()
    except (OSError, ValueError):
        return _failure(source, "CACHE_READ_FAILED", otp_sha256=otp_sha256)

    digest = hashlib.sha256(data).hexdigest()
    common = {
        "size": len(data),
        "file_sha256": digest,
        "otp_sha256": otp_sha256,
    }
    if (stat_before.st_dev, stat_before.st_ino, stat_before.st_size, stat_before.st_mtime_ns) != (
        stat_after.st_dev,
        stat_after.st_ino,
        stat_after.st_size,
        stat_after.st_mtime_ns,
    ):
        return _failure(source, "CACHE_CHANGED_DURING_READ", **common)
    if len(data) != CACHE_SIZE:
        return _failure(source, "CACHE_SIZE_MISMATCH", **common)

    calculated_crc = crc32_mpeg2(data[:CRC_OFFSET])
    stored_crc = int.from_bytes(data[CRC_OFFSET:], "little")
    if stored_crc != calculated_crc:
        return _failure(source, "CACHE_CRC_MISMATCH", **common)

    cached_otp = data[OTP_OFFSET:FDT12_OFFSET]
    if not hmac.compare_digest(cached_otp, expected_otp64):
        return _failure(
            source,
            "CACHE_OTP_BINDING_MISMATCH",
            crc_valid=True,
            otp_binding="MISMATCH",
            **common,
        )

    fdt12 = data[FDT12_OFFSET:NAV_OFFSET]
    fdt12_sha256 = hashlib.sha256(fdt12).hexdigest()
    if not any(fdt12):
        return _failure(
            source,
            "CACHE_FDT12_ABSENT",
            crc_valid=True,
            otp_binding="MATCH",
            fdt12_sha256=fdt12_sha256,
            **common,
        )

    return SeedProviderResult(
        status=SEED_PROVIDER_PASS,
        fdt12=bytes(fdt12),
        provenance=_provenance(
            source,
            crc_valid=True,
            otp_binding="MATCH",
            fdt12_sha256=fdt12_sha256,
            **common,
        ),
        failure_reason=None,
    )


def provide_hash_gated_fdt12(
    cache_path: str | os.PathLike[str],
    expected_otp64: bytes,
    expected_cache_sha256: str,
) -> SeedProviderResult:
    """Add the D261 canonical-source hash gate without ever writing the cache."""

    source = Path(cache_path)
    result = provide_fdt12(source, expected_otp64)
    if not result.ok:
        return result
    if result.provenance.file_sha256 != expected_cache_sha256:
        return _failure(
            source,
            "CACHE_SOURCE_HASH_MISMATCH",
            size=result.provenance.file_size,
            file_sha256=result.provenance.file_sha256,
            crc_valid=result.provenance.crc_valid,
            otp_binding=result.provenance.otp_binding,
            otp_sha256=result.provenance.otp_sha256,
            fdt12_sha256=result.provenance.fdt12_sha256,
        )
    return result
