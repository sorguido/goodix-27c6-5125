# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Protected material and secret boundaries for the D261 operational path.

Construction and metadata preflight never read the secret.  Protected-content
materialization requires an opaque CLI-intent capability.  A distinct live-I/O
capability is minted only after that content has been validated and the
single-use marker has been claimed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import errno
import json
import os
from pathlib import Path
import stat
from typing import Final

from core.cold_start import (
    ColdStartMaterial,
    DacEntry,
    E4_RESPONSE_PREFIX,
    TARGET_CONFIG90_LENGTH,
    TARGET_CONFIG90_SHA256,
)
from poc.goodix5125.tools.binding_reference.runtime import derive_validator_from_canonical_pe
from core.live_capability import (
    CapabilityFailure, CliIntentCapability, D261_LIVE_AUTHORIZATION_FLAG,
    FutureIntentCapability, FutureLiveIoCapability, FutureMarkerClaimCapability,
    LiveIoCapability, MarkerClaimCapability, _issue_d261_intent_after_exact_flag,
    _issue_d261_live_io_after_marker, _issue_d261_marker_after_durable_claim,
    require_d261_intent, require_known_live_io_capability,
    require_known_material_intent,
)


PROTECTED_ROOT: Final = Path("/var/lib/goodix-5125-poc")
SECRET_PATH: Final = PROTECTED_ROOT / "transport-material.bin"
MATERIAL_MANIFEST_PATH: Final = PROTECTED_ROOT / "target-material-manifest.json"
CONFIG90_PATH: Final = PROTECTED_ROOT / "target-config-90.bin"
CANONICAL_GFUSB_PATH: Final = Path("analysis/D230/work/GoodixExport/gfusb.dll")
SECRET_RECORD_LENGTH: Final = 88
SECRET_RECORD_SHA256: Final = "eb47bbed40e079ca780cd9cd4b2324520a67584ad3d576674914152fd6080a75"
MATERIAL_MANIFEST_SHA256: Final = "1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15"
CANONICAL_GFUSB_SHA256: Final = "904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2"


class ProtectedRuntimeFailure(RuntimeError):
    pass


def _issue_cli_intent_after_exact_main_flag(explicit_authorization: str) -> CliIntentCapability:
    """Private factory used only by the supported ``main()`` live branch."""

    try:
        return _issue_d261_intent_after_exact_flag(explicit_authorization)
    except CapabilityFailure as exc:
        raise ProtectedRuntimeFailure(str(exc)) from exc


def require_cli_intent(token: CliIntentCapability | None) -> None:
    try:
        require_d261_intent(token)
    except CapabilityFailure as exc:
        raise ProtectedRuntimeFailure(str(exc)) from exc


def _issue_marker_claim_capability(
    cli_intent: CliIntentCapability | None,
) -> MarkerClaimCapability:
    """Private factory called by the marker writer after fsync succeeds."""

    require_cli_intent(cli_intent)
    return _issue_d261_marker_after_durable_claim(cli_intent)


def issue_live_io_capability_after_marker(
    cli_intent: CliIntentCapability | None,
    *,
    marker_claim: MarkerClaimCapability | None,
) -> LiveIoCapability:
    """Mint the live-I/O capability immediately after a successful marker claim."""

    try:
        return _issue_d261_live_io_after_marker(cli_intent, marker_claim)
    except CapabilityFailure as exc:
        raise ProtectedRuntimeFailure(str(exc)) from exc


def _cli_intent_authorized(token: CliIntentCapability) -> bool:
    try:
        require_d261_intent(token)
        return True
    except CapabilityFailure:
        return False


def require_live_io_capability(token: LiveIoCapability | None) -> None:
    """Fail before any live resource is opened when the capability is absent."""

    try:
        require_known_live_io_capability(token)
    except CapabilityFailure as exc:
        raise ProtectedRuntimeFailure(str(exc)) from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def protected_metadata(
    path: Path,
    expected_size: int | None,
    *,
    expected_uid: int = 0,
) -> dict[str, object]:
    """Inspect ownership/mode/shape without opening or hashing file content."""

    result: dict[str, object] = {
        "path": os.fspath(path),
        "exists": False,
        "regular": False,
        "symlink": False,
        "uid": None,
        "mode": None,
        "size": None,
        "expected_size": expected_size,
        "metadata_pass": False,
        "content_read": False,
        "status": "ABSENT",
        "errno": None,
    }
    try:
        value = path.lstat()
    except OSError as exc:
        result["errno"] = exc.errno
        if exc.errno in (errno.EACCES, errno.EPERM):
            result["status"] = "INACCESSIBLE_UNPRIVILEGED"
        elif exc.errno == errno.ENOENT:
            result["status"] = "ABSENT"
        else:
            result["status"] = f"ERROR_{exc.errno if exc.errno is not None else 'UNKNOWN'}"
        return result
    result.update(
        exists=True,
        regular=stat.S_ISREG(value.st_mode),
        symlink=stat.S_ISLNK(value.st_mode),
        uid=value.st_uid,
        mode=oct(stat.S_IMODE(value.st_mode)),
        size=value.st_size,
    )
    result["metadata_pass"] = bool(
        result["regular"]
        and not result["symlink"]
        and value.st_uid == expected_uid
        and stat.S_IMODE(value.st_mode) == 0o600
        and (expected_size is None or value.st_size == expected_size)
    )
    result["status"] = "PASS_METADATA" if result["metadata_pass"] else "ERROR_METADATA_UNSAFE"
    return result


def protected_directory_metadata(
    path: Path,
    expected_mode: int = 0o700,
    *,
    expected_uid: int = 0,
) -> dict[str, object]:
    """Classify a protected directory without following symlinks or mutating it."""

    result: dict[str, object] = {
        "path": os.fspath(path),
        "exists": False,
        "directory": False,
        "symlink": False,
        "uid": None,
        "mode": None,
        "metadata_pass": False,
        "content_read": False,
        "status": "ABSENT",
        "errno": None,
    }
    try:
        value = path.lstat()
    except OSError as exc:
        result["errno"] = exc.errno
        if exc.errno in (errno.EACCES, errno.EPERM):
            result["status"] = "INACCESSIBLE_UNPRIVILEGED"
        elif exc.errno == errno.ENOENT:
            result["status"] = "ABSENT"
        else:
            result["status"] = f"ERROR_{exc.errno if exc.errno is not None else 'UNKNOWN'}"
        return result
    result.update(
        exists=True,
        directory=stat.S_ISDIR(value.st_mode),
        symlink=stat.S_ISLNK(value.st_mode),
        uid=value.st_uid,
        mode=oct(stat.S_IMODE(value.st_mode)),
    )
    result["metadata_pass"] = bool(
        result["directory"]
        and not result["symlink"]
        and value.st_uid == expected_uid
        and stat.S_IMODE(value.st_mode) == expected_mode
    )
    result["status"] = "PASS_METADATA" if result["metadata_pass"] else "ERROR_METADATA_UNSAFE"
    return result


def _read_protected(path: Path, expected_size: int | None = None) -> bytes:
    metadata = protected_metadata(path, expected_size)
    if not metadata["metadata_pass"]:
        raise ProtectedRuntimeFailure(f"protected_metadata_invalid:{path}")
    data = path.read_bytes()
    if expected_size is not None and len(data) != expected_size:
        raise ProtectedRuntimeFailure(f"protected_size_changed:{path}")
    return data


class RealSecretBoundary:
    """Canonical root store → E4 validator → same TLS secret object lineage."""

    def __init__(self, secret_path: Path, canonical_gfusb: Path) -> None:
        self.secret_path = Path(secret_path)
        self.canonical_gfusb = Path(canonical_gfusb)
        self._secret: bytearray | None = None
        self.materialize_count = 0
        self.handoff_count = 0
        self.e4_validation_count = 0
        self.close_count = 0
        self.secret_log_count = 0

    def metadata(self) -> dict[str, object]:
        return protected_metadata(self.secret_path, SECRET_RECORD_LENGTH)

    def materialize(self, cli_intent: object) -> None:
        try:
            require_known_material_intent(cli_intent)
        except CapabilityFailure:
            raise ProtectedRuntimeFailure("secret_materialization_not_authorized")
        if self.materialize_count or self._secret is not None:
            raise ProtectedRuntimeFailure("secret_materialization_exactly_once")
        record = bytearray(_read_protected(self.secret_path, SECRET_RECORD_LENGTH))
        try:
            if bytes(record[:8]) != b"G5125POC":
                raise ProtectedRuntimeFailure("secret_record_magic_mismatch")
            if hashlib.sha256(record).hexdigest() != SECRET_RECORD_SHA256:
                raise ProtectedRuntimeFailure("secret_record_hash_mismatch")
            self._secret = bytearray(record[24:56])
            if len(self._secret) != 32:
                raise ProtectedRuntimeFailure("secret_length_mismatch")
            self.materialize_count = 1
        finally:
            record[:] = bytes(len(record))

    def validate_e4(self, response_body: bytes) -> bool:
        if self._secret is None or self.zeroized:
            raise ProtectedRuntimeFailure("e4_before_secret_materialization")
        if self.e4_validation_count:
            raise ProtectedRuntimeFailure("e4_validation_exactly_once")
        if not response_body.startswith(E4_RESPONSE_PREFIX):
            return False
        actual = response_body[len(E4_RESPONSE_PREFIX):]
        expected = derive_validator_from_canonical_pe(
            self.canonical_gfusb, memoryview(self._secret).toreadonly()
        )
        try:
            matched = len(actual) == 32 and hmac.compare_digest(expected, actual)
            self.e4_validation_count = int(matched)
            return matched
        finally:
            expected[:] = bytes(len(expected))

    def handoff(self) -> memoryview:
        if self._secret is None or self.zeroized or self.handoff_count:
            raise ProtectedRuntimeFailure("tls_secret_handoff_forbidden")
        if self.e4_validation_count != 1:
            raise ProtectedRuntimeFailure("tls_handoff_before_e4_validation")
        self.handoff_count = 1
        return memoryview(self._secret).toreadonly()

    def close(self) -> None:
        if self.close_count:
            return
        if self._secret is not None:
            self._secret[:] = bytes(len(self._secret))
        self.close_count = 1

    @property
    def zeroized(self) -> bool:
        return self.close_count == 1 and (self._secret is None or not any(self._secret))


def validate_config90_content(config: bytes) -> None:
    """Shared content gate used by the live loader and synthetic fixtures."""

    if len(config) != TARGET_CONFIG90_LENGTH:
        raise ProtectedRuntimeFailure("config90_size_mismatch")
    if hashlib.sha256(config).hexdigest() != TARGET_CONFIG90_SHA256:
        raise ProtectedRuntimeFailure("config90_hash_mismatch")


def load_cold_start_material(
    manifest_path: Path,
    config90_path: Path,
    cli_intent: object,
) -> ColdStartMaterial:
    try:
        require_known_material_intent(cli_intent)
    except CapabilityFailure:
        raise ProtectedRuntimeFailure("material_load_not_authorized")
    manifest_raw = _read_protected(Path(manifest_path))
    if hashlib.sha256(manifest_raw).hexdigest() != MATERIAL_MANIFEST_SHA256:
        raise ProtectedRuntimeFailure("material_manifest_hash_mismatch")
    try:
        manifest = json.loads(manifest_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtectedRuntimeFailure("material_manifest_invalid") from exc
    config = _read_protected(Path(config90_path), TARGET_CONFIG90_LENGTH)
    validate_config90_content(config)
    config_meta = manifest.get("config90", {})
    if config_meta.get("body_length") != TARGET_CONFIG90_LENGTH or config_meta.get("body_sha256") != TARGET_CONFIG90_SHA256:
        raise ProtectedRuntimeFailure("config90_manifest_mismatch")
    try:
        dac = tuple(
            DacEntry(
                register=int(row["register"], 16),
                value=bytes.fromhex(row["value_le_hex"]),
                config_offset=int(row["config_tuple_offset"]),
            )
            for row in manifest["dac"]
        )
        return ColdStartMaterial(
            config90=config,
            dac=dac,
            a2_response_sha256=str(manifest["a2"]["response_body_sha256"]),
            chip82_response_sha256=str(manifest["chip82"]["response_body_sha256"]),
            otp_a6_response_sha256=str(manifest["otp_a6"]["response_body_sha256"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProtectedRuntimeFailure("material_manifest_shape_mismatch") from exc
