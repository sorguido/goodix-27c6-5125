# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Goodix 27c6:5125 project contributors
"""Bounded APP12509 cold-start contract for the canonical GPL runtime.

This is a fresh implementation from target-observed protocol facts.  It does
not import or patch the sealed historical USB runtime.  A8 is a read-only
firmware discriminator; A2 and 0x70 occur only in their live-proven cold-start
positions and are never exposed as recovery operations.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Protocol

from core.post_d4 import PLAIN, parse_outer, parse_payload
from core.runtime_transport import PhysicalSubmissionPolicy, RuntimeTransport, SubmissionMode


TARGET_FIRMWARE = b"GF_ST411SEC_APP_12509\x00"
TARGET_CONFIG90_LENGTH = 224
TARGET_CONFIG90_SHA256 = "e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82"
ALLOWED_ACK_STATUSES = frozenset((0x01, 0x07))
E4_RESPONSE_PREFIX = bytes.fromhex("00030002bb20000000")

PHASE_TIMEOUT_MS = {
    "A8": 1000,
    "E4": 1000,
    "A2_1": 1000,
    "CHIP_82": 500,
    "OTP_A6": 750,
    "A2_2": 1000,
    "MODE_70": 500,
    "DAC_220": 250,
    "DAC_236": 250,
    "DAC_238": 250,
    "DAC_23A": 250,
    "CONFIG_90": 1000,
}

PHASE_ORDER = tuple(PHASE_TIMEOUT_MS)
PHASE_CONTROLS = {
    "A8": 0xA8,
    "E4": 0xE4,
    "A2_1": 0xA2,
    "CHIP_82": 0x82,
    "OTP_A6": 0xA6,
    "A2_2": 0xA2,
    "MODE_70": 0x70,
    "DAC_220": 0x80,
    "DAC_236": 0x80,
    "DAC_238": 0x80,
    "DAC_23A": 0x80,
    "CONFIG_90": 0x90,
}
TYPED_RESPONSE_PHASES = frozenset(("A8", "E4", "A2_1", "CHIP_82", "OTP_A6", "A2_2", "CONFIG_90"))


class ColdStartFailure(RuntimeError):
    """A cold-start gate failed; the caller must perform host-only cleanup."""


class E4SecretBoundary(Protocol):
    """The same object later handed to TLS validates the E4 response."""

    def validate_e4(self, response_body: bytes) -> bool:
        ...


@dataclass(frozen=True)
class DacEntry:
    register: int
    value: bytes
    config_offset: int


@dataclass(frozen=True)
class ColdStartMaterial:
    config90: bytes
    dac: tuple[DacEntry, ...]
    a2_response_sha256: str
    chip82_response_sha256: str
    otp_a6_response_sha256: str

    def validate(self) -> None:
        if len(self.config90) != TARGET_CONFIG90_LENGTH:
            raise ColdStartFailure("config90_length_mismatch")
        if hashlib.sha256(self.config90).hexdigest() != TARGET_CONFIG90_SHA256:
            raise ColdStartFailure("config90_hash_mismatch")
        expected = (0x0220, 0x0236, 0x0238, 0x023A)
        if tuple(row.register for row in self.dac) != expected:
            raise ColdStartFailure("dac_register_order_mismatch")
        for row in self.dac:
            if len(row.value) != 2:
                raise ColdStartFailure("dac_value_length_mismatch")
            correlated = row.register.to_bytes(2, "little") + row.value
            if self.config90[row.config_offset:row.config_offset + 4] != correlated:
                raise ColdStartFailure("dac_config90_correlation_mismatch")
        if any(len(value) != 64 for value in (
            self.a2_response_sha256,
            self.chip82_response_sha256,
            self.otp_a6_response_sha256,
        )):
            raise ColdStartFailure("cold_response_hash_invalid")


@dataclass(frozen=True)
class ColdStartResult:
    firmware: str
    otp64: bytes
    phase_trace: tuple[str, ...]
    command_trace: tuple[int, ...]
    e4_validated: bool


def _checksum(control: int, body: bytes, *, seed: int | None = None) -> int:
    declared = len(body) + 1
    source = control if seed is None else seed
    return (0xAA - source - (declared & 0xFF) - (declared >> 8) - sum(body)) & 0xFF


def build_cold_a0(control: int, body: bytes) -> bytes:
    if control not in frozenset(PHASE_CONTROLS.values()):
        raise ColdStartFailure(f"cold_control_not_allowlisted:0x{control:02x}")
    body = bytes(body)
    declared = len(body) + 1
    payload = bytes((control, declared & 0xFF, declared >> 8)) + body
    payload += bytes((_checksum(control, body),))
    size = len(payload)
    return bytes((PLAIN, size & 0xFF, size >> 8, (PLAIN + (size & 0xFF) + (size >> 8)) & 0xFF)) + payload


def _phase_policy(phase: str) -> PhysicalSubmissionPolicy:
    return PhysicalSubmissionPolicy(
        name=f"COLD_START_{phase}_D241_SHORT_FINAL",
        mode=SubmissionMode.SHORT_FINAL,
        timeout_ms=PHASE_TIMEOUT_MS[phase],
    )


def _request_frames(material: ColdStartMaterial) -> dict[str, bytes]:
    material.validate()
    values = {row.register: row.value for row in material.dac}
    return {
        "A8": bytes.fromhex("a00600a6a803000000ff"),
        "E4": build_cold_a0(0xE4, bytes.fromhex("030002bb00000000")),
        "A2_1": build_cold_a0(0xA2, bytes.fromhex("0114")),
        "CHIP_82": build_cold_a0(0x82, bytes.fromhex("0000000400")),
        "OTP_A6": build_cold_a0(0xA6, bytes.fromhex("0000")),
        "A2_2": build_cold_a0(0xA2, bytes.fromhex("0114")),
        "MODE_70": build_cold_a0(0x70, bytes.fromhex("1400")),
        "DAC_220": build_cold_a0(0x80, bytes.fromhex("200202") + values[0x0220]),
        "DAC_236": build_cold_a0(0x80, bytes.fromhex("360202") + values[0x0236]),
        "DAC_238": build_cold_a0(0x80, bytes.fromhex("380202") + values[0x0238]),
        "DAC_23A": build_cold_a0(0x80, bytes.fromhex("3a0202") + values[0x023A]),
        "CONFIG_90": build_cold_a0(0x90, material.config90),
    }


def _parse_ack(frame: bytes, echo: int) -> int:
    kind, payload = parse_outer(frame)
    control, data = parse_payload(payload)
    if kind != PLAIN or control != 0xB0 or len(data) != 2 or data[0] != echo:
        raise ColdStartFailure(f"cold_ack_shape_mismatch:0x{echo:02x}")
    if data[1] not in ALLOWED_ACK_STATUSES:
        raise ColdStartFailure(f"cold_ack_status_rejected:0x{echo:02x}:0x{data[1]:02x}")
    return data[1]


def _parse_typed(frame: bytes, expected_control: int) -> bytes:
    kind, payload = parse_outer(frame)
    control, body = parse_payload(payload)
    if kind != PLAIN or control != expected_control:
        raise ColdStartFailure(f"cold_typed_response_mismatch:0x{expected_control:02x}")
    return body


class ColdStartMachine:
    """Execute A8→E4→pre-D1 exactly once on an already-open transport."""

    def __init__(self, transport: RuntimeTransport, secret_boundary: E4SecretBoundary) -> None:
        self.transport = transport
        self.secret_boundary = secret_boundary
        self.phase_trace: list[str] = []
        self.command_trace: list[int] = []
        self.retry_count = 0
        self.e4_validation_count = 0

    def run(self, material: ColdStartMaterial) -> ColdStartResult:
        frames = _request_frames(material)
        otp64: bytes | None = None
        for phase in PHASE_ORDER:
            if phase in self.phase_trace:
                raise ColdStartFailure(f"cold_phase_retry_forbidden:{phase}")
            control = PHASE_CONTROLS[phase]
            policy = _phase_policy(phase)
            request = frames[phase]
            if b"".join(policy.materialize(request)) != request:
                raise ColdStartFailure(f"cold_short_final_contract_mismatch:{phase}")
            self.transport.submit(request, policy)
            self.phase_trace.append(phase)
            self.command_trace.append(control)
            _parse_ack(self.transport.receive(policy.timeout_ms), control)
            if phase not in TYPED_RESPONSE_PHASES:
                continue
            body = _parse_typed(self.transport.receive(policy.timeout_ms), control)
            if phase == "A8" and body != TARGET_FIRMWARE:
                raise ColdStartFailure("a8_target_firmware_mismatch")
            if phase == "E4":
                if len(body) != len(E4_RESPONSE_PREFIX) + 32 or not body.startswith(E4_RESPONSE_PREFIX):
                    raise ColdStartFailure("e4_response_shape_mismatch")
                if not self.secret_boundary.validate_e4(body):
                    raise ColdStartFailure("e4_secret_binding_mismatch")
                self.e4_validation_count = 1
            elif phase in ("A2_1", "A2_2"):
                if len(body) != 3 or hashlib.sha256(body).hexdigest() != material.a2_response_sha256:
                    raise ColdStartFailure("a2_response_identity_mismatch")
            elif phase == "CHIP_82":
                if len(body) != 4 or hashlib.sha256(body).hexdigest() != material.chip82_response_sha256:
                    raise ColdStartFailure("chip82_identity_mismatch")
            elif phase == "OTP_A6":
                if len(body) != 64 or hashlib.sha256(body).hexdigest() != material.otp_a6_response_sha256:
                    raise ColdStartFailure("otp_a6_identity_mismatch")
                otp64 = bytes(body)
            elif phase == "CONFIG_90" and body != b"\x01\x00":
                raise ColdStartFailure("config90_response_mismatch")
        if otp64 is None or self.e4_validation_count != 1:
            raise ColdStartFailure("cold_start_incomplete")
        return ColdStartResult(
            firmware=TARGET_FIRMWARE.rstrip(b"\x00").decode("ascii"),
            otp64=otp64,
            phase_trace=tuple(self.phase_trace),
            command_trace=tuple(self.command_trace),
            e4_validated=True,
        )
