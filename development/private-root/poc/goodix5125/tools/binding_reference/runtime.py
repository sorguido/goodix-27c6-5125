"""Minimal runtime-facing D190 API; canonical PE is read but never executed."""

from __future__ import annotations

from pathlib import Path

from .crypto_reference import bind_validator
from .pe_parser import extract_seeds


def verify_canonical_pe(pe_path: Path) -> None:
    """Hash/pattern preflight that discards both extracted seeds immediately."""
    first = second = None
    try:
        first, second = extract_seeds(Path(pe_path))
    finally:
        for seed in (first, second):
            if seed is not None:
                seed[:] = bytes(len(seed))


def derive_validator_from_canonical_pe(
    pe_path: Path, secret32: bytes | memoryview
) -> bytearray:
    if len(secret32) != 32:
        raise ValueError("secret must be exactly 32 bytes")
    first = second = None
    try:
        first, second = extract_seeds(Path(pe_path))
        result = bind_validator(secret32, bytes(first), bytes(second))
        if len(result) != 32:
            result[:] = bytes(len(result))
            raise ValueError("validator length mismatch")
        return result
    finally:
        for seed in (first, second):
            if seed is not None:
                seed[:] = bytes(len(seed))
