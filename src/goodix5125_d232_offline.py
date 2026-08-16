"""D232 exact-OEM-replay model: synthetic transport only, live impossible.

This clean-room module implements framing, material gates, a monotonic replay
state machine, secret lifetime handling and durable redacted reports.  It has
no hardware transport, device enumeration, driver control or live entrypoint.
Enabling a future live backend requires an explicit source change and review.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence


D232_LIVE_CAPABILITY = 0
TARGET_MATERIAL_MANIFEST_SHA256 = (
    "1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15"
)
TARGET_CONFIG90_LENGTH = 224
TARGET_CONFIG90_SHA256 = "e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82"
ROOT_UID = 0
ROOT_ONLY_MODE = 0o600
TARGET_VID = 0x27C6
TARGET_PID = 0x5125
PSK_LENGTH = 32
TLS_SUITE = 0x00A8
TLS_IDENTITY = "Client_identity"
TLS12_CLIENT_HELLO_RECORD_VERSIONS = frozenset(
    (b"\x03\x01", b"\x03\x02", b"\x03\x03")
)

EXACT_PHASE_ORDER = (
    "E4",
    "A2_1",
    "CHIP_82",
    "OTP_A6",
    "A2_2",
    "MODE_70",
    "DAC_220",
    "DAC_236",
    "DAC_238",
    "DAC_23A",
    "CONFIG_90",
    "D1",
    "TLS",
)

FORBIDDEN_CONTROLS = frozenset((0xD4, 0xE0, 0xA4, 0xF0, 0xF4))
PHASE_TIMEOUT_MS = {
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
    "D1": 1000,
    "TLS": 3000,
}


class ReplayError(RuntimeError):
    """Base class for a fail-closed D232 result."""


class ContractError(ReplayError):
    """The immutable replay/material contract was violated."""


class LiveCapabilityUnavailable(ReplayError):
    """D232 has no live capability."""


class AbortClass(str, Enum):
    PREFLIGHT = "preflight_failed"
    TIMEOUT = "timeout"
    AMBIGUOUS = "ambiguous_completion"
    UNEXPECTED_ACK = "unexpected_ack"
    UNEXPECTED_DATA = "unexpected_data"
    UNEXPECTED_IRQ = "unexpected_irq"
    WRONG_CHIPID = "wrong_chipid"
    OTP_MALFORMED = "otp_shape_or_hash_mismatch"
    CONFIG_MISMATCH = "config_mismatch"
    BAD_RECORD_MAC = "tls_bad_record_mac"
    TLS_ALERT = "tls_alert"
    TLS_TIMEOUT = "tls_timeout"
    EXTRA_OR_REORDERED = "extra_or_reordered_command"
    SECRET_BOUNDARY = "secret_boundary_failure"
    INTERNAL = "internal_fail_closed"


class ReplayAbort(ReplayError):
    def __init__(self, abort_class: AbortClass):
        super().__init__(abort_class.value)
        self.abort_class = abort_class


@dataclass(frozen=True)
class A0Frame:
    control: int
    body: bytes


def build_a0(control: int, body: bytes, *, checksum_seed_control: int | None = None) -> bytes:
    """Build one exact A0 frame; the optional seed models PID-5125 pre-OR use."""
    if not 0 <= control <= 0xFF:
        raise ContractError("A0 control outside byte")
    if control in FORBIDDEN_CONTROLS:
        raise ContractError("forbidden control")
    body = bytes(body)
    inner_len = len(body) + 1
    if inner_len > 0xFFFF:
        raise ContractError("A0 body too large")
    seed = control if checksum_seed_control is None else checksum_seed_control
    if not 0 <= seed <= 0xFF:
        raise ContractError("checksum seed outside byte")
    lo, hi = inner_len & 0xFF, inner_len >> 8
    checksum = (0xAA - seed - lo - hi - sum(body)) & 0xFF
    payload = bytes((control, lo, hi)) + body + bytes((checksum,))
    outer_len = len(payload)
    outer_lo, outer_hi = outer_len & 0xFF, outer_len >> 8
    tag = (0xA0 + outer_lo + outer_hi) & 0xFF
    return bytes((0xA0, outer_lo, outer_hi, tag)) + payload


def parse_a0(frame: bytes, *, checksum_seed_control: int | None = None) -> A0Frame:
    frame = bytes(frame)
    if len(frame) < 8 or frame[0] != 0xA0:
        raise ContractError("not an A0 frame")
    outer_len = int.from_bytes(frame[1:3], "little")
    if len(frame) != 4 + outer_len:
        raise ContractError("A0 outer length mismatch")
    if frame[3] != (0xA0 + frame[1] + frame[2]) & 0xFF:
        raise ContractError("A0 outer tag mismatch")
    control = frame[4]
    inner_len = int.from_bytes(frame[5:7], "little")
    if outer_len != 3 + inner_len or inner_len < 1:
        raise ContractError("A0 inner length mismatch")
    inner = frame[7:]
    body, checksum = inner[:-1], inner[-1]
    seed = control if checksum_seed_control is None else checksum_seed_control
    if (seed + frame[5] + frame[6] + sum(body) + checksum) & 0xFF != 0xAA:
        raise ContractError("A0 inner checksum mismatch")
    return A0Frame(control, body)


def build_b0(tls_record: bytes) -> bytes:
    tls_record = bytes(tls_record)
    if len(tls_record) > 0xFFFF:
        raise ContractError("TLS record too large")
    lo, hi = len(tls_record) & 0xFF, len(tls_record) >> 8
    return bytes((0xB0, lo, hi, (0xB0 + lo + hi) & 0xFF)) + tls_record


def parse_b0(frame: bytes) -> bytes:
    frame = bytes(frame)
    if len(frame) < 4 or frame[0] != 0xB0:
        raise ContractError("not a B0 frame")
    length = int.from_bytes(frame[1:3], "little")
    if len(frame) != 4 + length:
        raise ContractError("B0 length mismatch")
    if frame[3] != (0xB0 + frame[1] + frame[2]) & 0xFF:
        raise ContractError("B0 tag mismatch")
    return frame[4:]


def validate_tls_client_hello_record(record: bytes) -> None:
    """Validate one complete TLS 1.2 ClientHello record without consuming it.

    A TLS 1.2 ClientHello can legitimately use a legacy record-layer version
    from TLS 1.0 through TLS 1.2 while advertising TLS 1.2 in the handshake
    body. Clients may also offer the required ``0x00a8`` together with the
    signaling cipher-suite value or other suites. The previous exact-``0303``
    record and exact-one-suite checks rejected interoperable forms before the
    already-read B0 could reach OpenSSL; the server context remains restricted
    to ``0x00a8``.
    """
    record = bytes(record)
    if (
        len(record) < 9
        or record[0] != 0x16
        or record[1:3] not in TLS12_CLIENT_HELLO_RECORD_VERSIONS
    ):
        raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
    if int.from_bytes(record[3:5], "big") != len(record) - 5:
        raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
    if record[5] != 0x01:
        raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
    if int.from_bytes(record[6:9], "big") != len(record) - 9:
        raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
    body = record[9:]
    if len(body) < 38 or body[:2] != b"\x03\x03":
        raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
    cursor = 34
    session_length = body[cursor]
    cursor += 1 + session_length
    if cursor + 2 > len(body):
        raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
    suites_length = int.from_bytes(body[cursor:cursor + 2], "big")
    cursor += 2
    if (
        suites_length < 2
        or suites_length % 2
        or cursor + suites_length > len(body)
    ):
        raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
    suites = tuple(
        int.from_bytes(body[index:index + 2], "big")
        for index in range(cursor, cursor + suites_length, 2)
    )
    if TLS_SUITE not in suites:
        raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
    cursor += suites_length
    if cursor >= len(body):
        raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
    compression_length = body[cursor]
    cursor += 1
    if compression_length != 1 or body[cursor:cursor + 1] != b"\x00":
        raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
    cursor += compression_length
    if cursor != len(body):
        if cursor + 2 > len(body):
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
        extensions_length = int.from_bytes(body[cursor:cursor + 2], "big")
        if cursor + 2 + extensions_length != len(body):
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA)


@dataclass(frozen=True)
class ProtectedFilePolicy:
    owner_uid: int = ROOT_UID
    mode: int = ROOT_ONLY_MODE


ROOT_ONLY_POLICY = ProtectedFilePolicy()


def _open_protected_regular(path: Path, policy: ProtectedFilePolicy) -> int:
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise ContractError("protected file unavailable") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ContractError("protected path is not a regular non-symlink file")
    if before.st_uid != policy.owner_uid:
        raise ContractError("protected file owner mismatch")
    if stat.S_IMODE(before.st_mode) != policy.mode:
        raise ContractError("protected file mode mismatch")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ContractError("protected file open failed") from exc
    try:
        after = os.fstat(fd)
        if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
            raise ContractError("protected file changed during open")
        if after.st_uid != policy.owner_uid or stat.S_IMODE(after.st_mode) != policy.mode:
            raise ContractError("protected file metadata changed during open")
        return fd
    except Exception:
        os.close(fd)
        raise


def _read_exact_protected(path: Path, length: int, policy: ProtectedFilePolicy) -> bytearray:
    fd = _open_protected_regular(path, policy)
    buffer = bytearray(length + 1)
    try:
        if os.fstat(fd).st_size != length:
            raise ContractError("protected file length mismatch")
        count = 0
        while count < length + 1:
            chunk = os.read(fd, length + 1 - count)
            if not chunk:
                break
            buffer[count:count + len(chunk)] = chunk
            count += len(chunk)
        if count != length:
            raise ContractError("protected file length mismatch")
        del buffer[length:]
        return buffer
    except Exception:
        for index in range(len(buffer)):
            buffer[index] = 0
        raise
    finally:
        os.close(fd)


def _read_bounded_protected(path: Path, maximum: int, policy: ProtectedFilePolicy) -> bytearray:
    fd = _open_protected_regular(path, policy)
    buffer = bytearray()
    try:
        size = os.fstat(fd).st_size
        if size < 1 or size > maximum:
            raise ContractError("protected file size outside bound")
        while len(buffer) < size:
            chunk = os.read(fd, min(4096, size - len(buffer)))
            if not chunk:
                raise ContractError("protected file short read")
            buffer.extend(chunk)
        if os.read(fd, 1):
            raise ContractError("protected file grew during read")
        return buffer
    except Exception:
        for index in range(len(buffer)):
            buffer[index] = 0
        raise
    finally:
        os.close(fd)


class SecretBuffer:
    """Owned mutable 32-byte secret with explicit, idempotent zeroization."""

    def __init__(self, owned: bytearray):
        if len(owned) != PSK_LENGTH:
            raise ContractError("secret must be exactly 32 bytes")
        self._owned = owned
        self._closed = False

    @classmethod
    def synthetic(cls, value: bytes) -> "SecretBuffer":
        return cls(bytearray(value))

    def view(self) -> memoryview:
        if self._closed:
            raise ContractError("secret already zeroized")
        return memoryview(self._owned).toreadonly()

    def close(self) -> None:
        if not self._closed:
            for index in range(len(self._owned)):
                self._owned[index] = 0
            self._closed = True

    @property
    def is_zeroized(self) -> bool:
        return self._closed and not any(self._owned)


def load_root_psk(
    path: Path = Path("/var/lib/goodix-5125-poc/transport-material.bin"),
) -> SecretBuffer:
    """Load the canonical hash-pinned 88-byte G5125POC v1 secret."""
    record = bytearray(_read_exact_protected(path, 88, ROOT_ONLY_POLICY))
    try:
        if bytes(record[:8]) != b"G5125POC":
            raise ContractError("canonical transport store magic mismatch")
        if hashlib.sha256(record).hexdigest() != (
            "eb47bbed40e079ca780cd9cd4b2324520a67584ad3d576674914152fd6080a75"
        ):
            raise ContractError("canonical transport store hash mismatch")
        secret = bytearray(record[24:56])
        if len(secret) != PSK_LENGTH:
            raise ContractError("canonical transport secret length mismatch")
        return SecretBuffer(secret)
    finally:
        for index in range(len(record)):
            record[index] = 0


@dataclass(frozen=True)
class TargetMaterial:
    e4_validator_sha256: str
    a2_response_sha256: str
    chip82_response_sha256: str
    otp_a6_response_sha256: str
    dac: tuple[tuple[int, bytes, int], ...]
    config90: bytes
    config90_sha256: str


def _config90_finalizer(config: bytes) -> bytes:
    if len(config) != TARGET_CONFIG90_LENGTH:
        raise ContractError("0x90 body length mismatch")
    total = 0xA5A5
    for offset in range(0, 222, 2):
        total = (total + int.from_bytes(config[offset:offset + 2], "little")) & 0xFFFF
    return ((-total) & 0xFFFF).to_bytes(2, "little")


def _load_target_material(
    manifest_path: Path,
    config_path: Path,
    *,
    expected_manifest_sha256: str,
    file_policy: ProtectedFilePolicy,
) -> TargetMaterial:
    manifest_buffer = _read_bounded_protected(manifest_path, 16384, file_policy)
    try:
        manifest_bytes = bytes(manifest_buffer)
        if hashlib.sha256(manifest_bytes).hexdigest() != expected_manifest_sha256:
            raise ContractError("target material manifest hash mismatch")
        try:
            manifest = json.loads(manifest_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError("invalid target material manifest") from exc
    finally:
        for index in range(len(manifest_buffer)):
            manifest_buffer[index] = 0
    if manifest.get("schema") != "d232-target-material-v1":
        raise ContractError("target material schema mismatch")
    config_meta = manifest.get("config90", {})
    length = config_meta.get("body_length")
    if length != TARGET_CONFIG90_LENGTH:
        raise ContractError("manifest 0x90 length mismatch")
    config_buffer = _read_exact_protected(config_path, length, file_policy)
    try:
        config = bytes(config_buffer)
    finally:
        for index in range(len(config_buffer)):
            config_buffer[index] = 0
    if hashlib.sha256(config).hexdigest() != config_meta.get("body_sha256"):
        raise ContractError("0x90 body hash mismatch")
    if config[-2:] != _config90_finalizer(config):
        raise ContractError("0x90 finalizer mismatch")
    expected_registers = (0x0220, 0x0236, 0x0238, 0x023A)
    dac_rows = manifest.get("dac")
    if not isinstance(dac_rows, list) or len(dac_rows) != 4:
        raise ContractError("DAC manifest shape mismatch")
    dac: list[tuple[int, bytes, int]] = []
    for index, (row, register) in enumerate(zip(dac_rows, expected_registers), 1):
        if row.get("order") != index or int(row.get("register"), 0) != register:
            raise ContractError("DAC register/order mismatch")
        try:
            value = bytes.fromhex(row["value_le_hex"])
            offset = int(row["config_tuple_offset"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError("DAC metadata malformed") from exc
        if len(value) != 2:
            raise ContractError("DAC value length mismatch")
        if config[offset:offset + 4] != register.to_bytes(2, "little") + value:
            raise ContractError("DAC/config correlation mismatch")
        dac.append((register, value, offset))
    return TargetMaterial(
        e4_validator_sha256=manifest["e4"]["validator_sha256"],
        a2_response_sha256=manifest["a2"]["response_body_sha256"],
        chip82_response_sha256=manifest["chip82"]["response_body_sha256"],
        otp_a6_response_sha256=manifest["otp_a6"]["response_body_sha256"],
        dac=tuple(dac),
        config90=config,
        config90_sha256=config_meta["body_sha256"],
    )


def load_root_target_material(
    manifest_path: Path,
    config_path: Path = Path("/var/lib/goodix-5125-poc/target-config-90.bin"),
) -> TargetMaterial:
    """Future D233 boundary. D232 tests call only the private synthetic seam."""
    return _load_target_material(
        manifest_path,
        config_path,
        expected_manifest_sha256=TARGET_MATERIAL_MANIFEST_SHA256,
        file_policy=ROOT_ONLY_POLICY,
    )


@dataclass(frozen=True)
class PreflightSnapshot:
    euid: int
    sudo_uid: int
    operator_uid: int
    single_use_marker_absent: bool
    process_count: int
    thread_count: int
    external_holder_count: int
    fprintd_state_captured: bool
    usb_identity_expected: bool
    vid: int
    pid: int
    serial_or_path_stable: bool
    signals_blocked_before_transport: bool
    report_path_ready: bool
    restore_plan_present: bool
    unexpected_reenumeration: bool = False


def validate_future_live_preflight(snapshot: PreflightSnapshot) -> None:
    """Validate supplied evidence only; this function performs no system scan."""
    checks = (
        snapshot.euid == ROOT_UID,
        snapshot.sudo_uid == snapshot.operator_uid,
        snapshot.single_use_marker_absent,
        snapshot.process_count == 1,
        snapshot.thread_count == 1,
        snapshot.external_holder_count == 0,
        snapshot.fprintd_state_captured,
        snapshot.usb_identity_expected,
        snapshot.vid == TARGET_VID,
        snapshot.pid == TARGET_PID,
        snapshot.serial_or_path_stable,
        snapshot.signals_blocked_before_transport,
        snapshot.report_path_ready,
        snapshot.restore_plan_present,
        not snapshot.unexpected_reenumeration,
    )
    if not all(checks):
        raise ReplayAbort(AbortClass.PREFLIGHT)


@dataclass(frozen=True)
class ScriptedExchange:
    phase_id: str
    expected_request: bytes
    responses: tuple[bytes, ...] = ()
    outcome: str = "ok"


class ScriptedSyntheticBackend:
    """Exact scripted oracle. No system or device transport exists here."""

    def __init__(
        self,
        script: Sequence[ScriptedExchange],
        *,
        tls_outcome: str = "ok",
        tls_suite: int = TLS_SUITE,
        tls_identity: str = TLS_IDENTITY,
    ):
        self._script = tuple(script)
        self._index = 0
        self._tls_outcome = tls_outcome
        self._tls_suite = tls_suite
        self._tls_identity = tls_identity
        self.exchange_count = 0
        self.tls_handshake_count = 0
        self.cleanup_count = 0

    def exchange(self, phase_id: str, request: bytes, timeout_ms: int) -> tuple[bytes, ...]:
        if timeout_ms <= 0 or self.cleanup_count:
            raise ReplayAbort(AbortClass.INTERNAL)
        if self._index >= len(self._script):
            raise ReplayAbort(AbortClass.EXTRA_OR_REORDERED)
        step = self._script[self._index]
        self._index += 1
        self.exchange_count += 1
        if step.phase_id != phase_id or step.expected_request != bytes(request):
            raise ReplayAbort(AbortClass.EXTRA_OR_REORDERED)
        if step.outcome == "timeout":
            raise ReplayAbort(AbortClass.TIMEOUT)
        if step.outcome == "ambiguous":
            raise ReplayAbort(AbortClass.AMBIGUOUS)
        if step.outcome != "ok":
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
        return tuple(bytes(response) for response in step.responses)

    def tls_handshake(self, client_hello: bytes, secret: SecretBuffer, timeout_ms: int) -> None:
        if self._index != len(self._script) or timeout_ms <= 0:
            raise ReplayAbort(AbortClass.EXTRA_OR_REORDERED)
        validate_tls_client_hello_record(client_hello)
        if len(secret.view()) != PSK_LENGTH:
            raise ReplayAbort(AbortClass.SECRET_BOUNDARY)
        if self._tls_suite != TLS_SUITE or self._tls_identity != TLS_IDENTITY:
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
        self.tls_handshake_count += 1
        outcomes = {
            "bad_record_mac": AbortClass.BAD_RECORD_MAC,
            "alert": AbortClass.TLS_ALERT,
            "timeout": AbortClass.TLS_TIMEOUT,
        }
        if self._tls_outcome in outcomes:
            raise ReplayAbort(outcomes[self._tls_outcome])
        if self._tls_outcome != "ok":
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA)

    def cleanup(self) -> None:
        self.cleanup_count += 1
        if self.cleanup_count != 1:
            raise ReplayAbort(AbortClass.INTERNAL)


class DurableReportPublisher:
    """Atomic mode-0600 JSON publication with exactly-once ownership."""

    def __init__(self, path: Path):
        self.path = path
        self.publish_count = 0

    def publish(self, report: Mapping[str, object]) -> None:
        if self.publish_count:
            raise ContractError("report publication attempted more than once")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(self.path) and self.path.is_symlink():
            raise ContractError("report path is a symlink")
        payload = (json.dumps(dict(report), sort_keys=True, separators=(",", ":")) + "\n").encode()
        fd, temporary_name = tempfile.mkstemp(prefix=".d232-report-", dir=self.path.parent)
        temporary = Path(temporary_name)
        try:
            os.fchmod(fd, 0o600)
            offset = 0
            while offset < len(payload):
                offset += os.write(fd, payload[offset:])
            os.fsync(fd)
            os.close(fd)
            fd = -1
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            self.publish_count = 1
        finally:
            if fd >= 0:
                os.close(fd)
            if temporary.exists():
                temporary.unlink()


@dataclass(frozen=True)
class PhaseResponsePolicy:
    """Exact logical response contract for one pre-D1 request.

    ACK status is a transport/session success value, not an opcode result body.
    The recovered OEM capture proves 0x01 across every ACK-bearing phase; D236
    proves 0x07 for two different controls (E4 and A2) in the same live path.
    Both values are therefore admitted explicitly, while every other value and
    every non-canonical frame shape remains fail-closed.
    """

    request_control: int
    allowed_ack_statuses: frozenset[int]
    response_kind: str


_PROVEN_SUCCESS_ACK_STATUSES = frozenset((0x01, 0x07))

PHASE_RESPONSE_POLICIES: Mapping[str, PhaseResponsePolicy] = {
    "E4": PhaseResponsePolicy(0xE4, _PROVEN_SUCCESS_ACK_STATUSES, "ack_then_typed"),
    "A2_1": PhaseResponsePolicy(0xA2, _PROVEN_SUCCESS_ACK_STATUSES, "ack_then_typed"),
    "CHIP_82": PhaseResponsePolicy(0x82, _PROVEN_SUCCESS_ACK_STATUSES, "ack_then_typed"),
    "OTP_A6": PhaseResponsePolicy(0xA6, _PROVEN_SUCCESS_ACK_STATUSES, "ack_then_typed"),
    "A2_2": PhaseResponsePolicy(0xA2, _PROVEN_SUCCESS_ACK_STATUSES, "ack_then_typed"),
    "MODE_70": PhaseResponsePolicy(0x70, _PROVEN_SUCCESS_ACK_STATUSES, "ack_only"),
    "DAC_220": PhaseResponsePolicy(0x80, _PROVEN_SUCCESS_ACK_STATUSES, "ack_only"),
    "DAC_236": PhaseResponsePolicy(0x80, _PROVEN_SUCCESS_ACK_STATUSES, "ack_only"),
    "DAC_238": PhaseResponsePolicy(0x80, _PROVEN_SUCCESS_ACK_STATUSES, "ack_only"),
    "DAC_23A": PhaseResponsePolicy(0x80, _PROVEN_SUCCESS_ACK_STATUSES, "ack_only"),
    "CONFIG_90": PhaseResponsePolicy(0x90, _PROVEN_SUCCESS_ACK_STATUSES, "ack_then_typed"),
    "D1": PhaseResponsePolicy(0xD1, frozenset(), "b0_tls_client_hello"),
}


def _ack(control: int, status: int = 0x01) -> bytes:
    if status not in _PROVEN_SUCCESS_ACK_STATUSES:
        raise ContractError("synthetic ACK status is not proven successful")
    return build_a0(0xB0, bytes((control, status)))


def expected_request_frames(material: TargetMaterial) -> dict[str, bytes]:
    if len(material.config90) != TARGET_CONFIG90_LENGTH:
        raise ContractError("0x90 body length mismatch")
    if hashlib.sha256(material.config90).hexdigest() != material.config90_sha256:
        raise ContractError("0x90 body hash mismatch")
    if material.config90[-2:] != _config90_finalizer(material.config90):
        raise ContractError("0x90 finalizer mismatch")
    expected_registers = (0x0220, 0x0236, 0x0238, 0x023A)
    if tuple(row[0] for row in material.dac) != expected_registers:
        raise ContractError("DAC register/order mismatch")
    for register, value, offset in material.dac:
        if len(value) != 2 or material.config90[offset:offset + 4] != register.to_bytes(2, "little") + value:
            raise ContractError("DAC/config correlation mismatch")
    values = {register: value for register, value, _offset in material.dac}
    frames = {
        "E4": build_a0(0xE4, bytes.fromhex("030002bb00000000")),
        "A2_1": build_a0(0xA2, bytes.fromhex("0114")),
        "CHIP_82": build_a0(0x82, bytes.fromhex("0000000400")),
        "OTP_A6": build_a0(0xA6, bytes.fromhex("0000")),
        "A2_2": build_a0(0xA2, bytes.fromhex("0114")),
        "MODE_70": build_a0(0x70, bytes.fromhex("1400")),
        "DAC_220": build_a0(0x80, bytes.fromhex("2002") + b"\x02" + values[0x0220]),
        "DAC_236": build_a0(0x80, bytes.fromhex("3602") + b"\x02" + values[0x0236]),
        "DAC_238": build_a0(0x80, bytes.fromhex("3802") + b"\x02" + values[0x0238]),
        "DAC_23A": build_a0(0x80, bytes.fromhex("3a02") + b"\x02" + values[0x023A]),
        "CONFIG_90": build_a0(0x90, material.config90),
        "D1": build_a0(0xD1, b"\x00\x00", checksum_seed_control=0xD0),
    }
    if tuple(frames) != EXACT_PHASE_ORDER[:-1]:
        raise ContractError("request phase order changed")
    return frames


@dataclass(frozen=True)
class SyntheticResponseBodies:
    e4_validator: bytes
    a2_irq: bytes
    chip82: bytes
    otp_a6: bytes
    tls_client_hello_record: bytes


def happy_synthetic_script(
    material: TargetMaterial,
    responses: SyntheticResponseBodies,
    *,
    ack_status: int = 0x01,
) -> tuple[ScriptedExchange, ...]:
    if hashlib.sha256(responses.e4_validator).hexdigest() != material.e4_validator_sha256:
        raise ContractError("synthetic E4 oracle does not match manifest")
    pins = (
        (responses.a2_irq, material.a2_response_sha256),
        (responses.chip82, material.chip82_response_sha256),
        (responses.otp_a6, material.otp_a6_response_sha256),
    )
    if any(hashlib.sha256(body).hexdigest() != digest for body, digest in pins):
        raise ContractError("synthetic response oracle does not match manifest")
    frames = expected_request_frames(material)
    typed_e4 = bytes.fromhex("00030002bb20000000") + responses.e4_validator
    response_map = {
        "E4": (_ack(0xE4, ack_status), build_a0(0xE4, typed_e4)),
        "A2_1": (_ack(0xA2, ack_status), build_a0(0xA2, responses.a2_irq)),
        "CHIP_82": (_ack(0x82, ack_status), build_a0(0x82, responses.chip82)),
        "OTP_A6": (_ack(0xA6, ack_status), build_a0(0xA6, responses.otp_a6)),
        "A2_2": (_ack(0xA2, ack_status), build_a0(0xA2, responses.a2_irq)),
        "MODE_70": (_ack(0x70, ack_status),),
        "DAC_220": (_ack(0x80, ack_status),),
        "DAC_236": (_ack(0x80, ack_status),),
        "DAC_238": (_ack(0x80, ack_status),),
        "DAC_23A": (_ack(0x80, ack_status),),
        "CONFIG_90": (_ack(0x90, ack_status), build_a0(0x90, b"\x01\x00")),
        "D1": (build_b0(responses.tls_client_hello_record),),
    }
    return tuple(
        ScriptedExchange(phase, frames[phase], response_map[phase])
        for phase in EXACT_PHASE_ORDER[:-1]
    )


def _expect_ack(frame: bytes, policy: PhaseResponsePolicy) -> None:
    try:
        parsed = parse_a0(frame)
    except ContractError as exc:
        raise ReplayAbort(AbortClass.UNEXPECTED_ACK) from exc
    if (
        parsed.control != 0xB0
        or len(parsed.body) != 2
        or parsed.body[0] != policy.request_control
        or parsed.body[1] not in policy.allowed_ack_statuses
    ):
        raise ReplayAbort(AbortClass.UNEXPECTED_ACK)


def _expect_typed(frame: bytes, control: int) -> bytes:
    try:
        parsed = parse_a0(frame)
    except ContractError as exc:
        raise ReplayAbort(AbortClass.UNEXPECTED_DATA) from exc
    if parsed.control != control:
        raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
    return parsed.body


def _validate_responses(phase: str, responses: tuple[bytes, ...], material: TargetMaterial) -> bytes | None:
    try:
        policy = PHASE_RESPONSE_POLICIES[phase]
    except KeyError as exc:
        raise ReplayAbort(AbortClass.EXTRA_OR_REORDERED) from exc
    if policy.response_kind == "b0_tls_client_hello":
        if len(responses) != 1:
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
        try:
            record = parse_b0(responses[0])
        except ContractError as exc:
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA) from exc
        validate_tls_client_hello_record(record)
        return record
    expected_count = 2 if policy.response_kind == "ack_then_typed" else 1
    if len(responses) != expected_count:
        raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
    control = policy.request_control
    _expect_ack(responses[0], policy)
    if expected_count == 1:
        return None
    body = _expect_typed(responses[1], control)
    if phase == "E4":
        prefix = bytes.fromhex("00030002bb20000000")
        if len(body) != 41 or not body.startswith(prefix):
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
        if hashlib.sha256(body[len(prefix):]).hexdigest() != material.e4_validator_sha256:
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
    elif phase.startswith("A2"):
        if len(body) != 3 or hashlib.sha256(body).hexdigest() != material.a2_response_sha256:
            raise ReplayAbort(AbortClass.UNEXPECTED_IRQ)
    elif phase == "CHIP_82":
        if len(body) != 4 or hashlib.sha256(body).hexdigest() != material.chip82_response_sha256:
            raise ReplayAbort(AbortClass.WRONG_CHIPID)
    elif phase == "OTP_A6":
        if len(body) != 64 or hashlib.sha256(body).hexdigest() != material.otp_a6_response_sha256:
            raise ReplayAbort(AbortClass.OTP_MALFORMED)
    elif phase == "CONFIG_90" and body != b"\x01\x00":
        raise ReplayAbort(AbortClass.CONFIG_MISMATCH)
    return None


SUCCESS_STATE = {
    "E4": "E4_MATCH",
    "A2_1": "A2_1_OK",
    "CHIP_82": "CHIPID_OK",
    "OTP_A6": "OTP_OK",
    "A2_2": "A2_2_OK",
    "MODE_70": "MODE_IDLE_OK",
    "DAC_220": "DAC_1_OK",
    "DAC_236": "DAC_2_OK",
    "DAC_238": "DAC_3_OK",
    "DAC_23A": "DAC_4_OK",
    "CONFIG_90": "CONFIG_OK",
    "D1": "D1_SENT_CLIENT_HELLO_OK",
    "TLS": "TLS_HANDSHAKE_OK",
}


class ExactOemReplayStateMachine:
    """Single-shot, no-retry state machine restricted to a synthetic backend."""

    def run(
        self,
        *,
        preflight: PreflightSnapshot,
        material: TargetMaterial,
        secret: SecretBuffer,
        backend: ScriptedSyntheticBackend,
        publisher: DurableReportPublisher,
    ) -> dict[str, object]:
        report: dict[str, object] = {
            "schema": "d232-synthetic-run-report-v1",
            "result": "abort",
            "terminal_state": "STOP",
            "reached_phase": "START",
            "abort_class": AbortClass.INTERNAL.value,
            "command_count": 0,
            "usb_open_count": 0,
            "tls_handshake_count": 0,
            "cleanup_count": 0,
            "restore_status": "not_executed_offline",
            "live_capability": D232_LIVE_CAPABILITY,
            "contains_secret": False,
            "contains_raw_config90": False,
            "report_publish_count": 1,
        }
        if type(backend) is not ScriptedSyntheticBackend:
            secret.close()
            report.update(
                reached_phase="BACKEND_TYPE_GATE",
                abort_class=AbortClass.PREFLIGHT.value,
                secret_zeroized=secret.is_zeroized,
                cleanup_status="no_resources_acquired",
            )
            publisher.publish(report)
            return report
        return _run_exact_oem_core(
            preflight=preflight,
            material=material,
            secret=secret,
            backend=backend,
            publisher=publisher,
        )


def _run_exact_oem_core(
    *,
    preflight: PreflightSnapshot,
    material: TargetMaterial,
    secret: SecretBuffer,
    backend: object,
    publisher: DurableReportPublisher,
) -> dict[str, object]:
    """Shared reviewed core for the D232 oracle and source-sealed D233 adapter."""
    report: dict[str, object] = {
        "schema": "d232-synthetic-run-report-v1",
        "result": "abort",
        "terminal_state": "STOP",
        "reached_phase": "START",
        "abort_class": AbortClass.INTERNAL.value,
        "command_count": 0,
        "usb_open_count": 0,
        "tls_handshake_count": 0,
        "cleanup_count": 0,
        "restore_status": "not_executed_offline",
        "live_capability": D232_LIVE_CAPABILITY,
        "contains_secret": False,
        "contains_raw_config90": False,
        "report_publish_count": 1,
    }
    client_hello: bytes | None = None
    try:
        validate_future_live_preflight(preflight)
        report["reached_phase"] = "IDENTITY_REVALIDATED"
        frames = expected_request_frames(material)
        for phase in EXACT_PHASE_ORDER[:-1]:
            responses = backend.exchange(phase, frames[phase], PHASE_TIMEOUT_MS[phase])
            client_hello = _validate_responses(phase, responses, material)
            report["reached_phase"] = SUCCESS_STATE[phase]
        if client_hello is None:
            raise ReplayAbort(AbortClass.UNEXPECTED_DATA)
        backend.tls_handshake(client_hello, secret, PHASE_TIMEOUT_MS["TLS"])
        report.update(
            result="pass",
            terminal_state="CLOSE",
            reached_phase=SUCCESS_STATE["TLS"],
            abort_class="none",
        )
    except ReplayAbort as exc:
        report["abort_class"] = exc.abort_class.value
    except (ContractError, KeyError, TypeError, ValueError):
        report["abort_class"] = AbortClass.INTERNAL.value
    finally:
        try:
            backend.cleanup()
        except ReplayAbort:
            report.update(result="abort", terminal_state="STOP", abort_class=AbortClass.INTERNAL.value)
        secret.close()
        report["command_count"] = backend.exchange_count
        report["usb_open_count"] = getattr(backend, "usb_open_count", 0)
        report["tls_handshake_count"] = backend.tls_handshake_count
        report["cleanup_count"] = backend.cleanup_count
        report["secret_zeroized"] = secret.is_zeroized
        publisher.publish(report)
    return report


def _pre_run_failure_report(
    *, backend: ScriptedSyntheticBackend, publisher: DurableReportPublisher, abort_class: AbortClass
) -> dict[str, object]:
    """Publish a durable result when a protected-input gate fails before START."""
    report: dict[str, object] = {
        "schema": "d232-synthetic-run-report-v1",
        "result": "abort",
        "terminal_state": "STOP",
        "reached_phase": "PROTECTED_INPUT_GATE",
        "abort_class": abort_class.value,
        "command_count": 0,
        "usb_open_count": 0,
        "tls_handshake_count": 0,
        "cleanup_count": 0,
        "restore_status": "not_executed_offline",
        "live_capability": D232_LIVE_CAPABILITY,
        "contains_secret": False,
        "contains_raw_config90": False,
        "report_publish_count": 1,
        "secret_zeroized": True,
    }
    try:
        backend.cleanup()
    except ReplayAbort:
        report["abort_class"] = AbortClass.INTERNAL.value
    report["cleanup_count"] = backend.cleanup_count
    publisher.publish(report)
    return report


def run_synthetic_from_protected_paths(
    *,
    preflight: PreflightSnapshot,
    manifest_path: Path,
    config_path: Path,
    psk_path: Path,
    expected_manifest_sha256: str,
    file_policy: ProtectedFilePolicy,
    backend: ScriptedSyntheticBackend,
    publisher: DurableReportPublisher,
) -> dict[str, object]:
    """Offline input-boundary integration seam; never uses the real root store."""
    try:
        material = _load_target_material(
            manifest_path,
            config_path,
            expected_manifest_sha256=expected_manifest_sha256,
            file_policy=file_policy,
        )
    except ContractError:
        return _pre_run_failure_report(
            backend=backend,
            publisher=publisher,
            abort_class=AbortClass.CONFIG_MISMATCH,
        )
    try:
        secret = SecretBuffer(_read_exact_protected(psk_path, PSK_LENGTH, file_policy))
    except ContractError:
        return _pre_run_failure_report(
            backend=backend,
            publisher=publisher,
            abort_class=AbortClass.SECRET_BOUNDARY,
        )
    return ExactOemReplayStateMachine().run(
        preflight=preflight,
        material=material,
        secret=secret,
        backend=backend,
        publisher=publisher,
    )


def request_live_mode(*_args: object, **_kwargs: object) -> None:
    """Unconditional compile/source gate: no runtime input can enable live."""
    raise LiveCapabilityUnavailable("D232 live capability is compiled out")


def d232_offline_entrypoint(
    argv: Sequence[str] = (), environ: Mapping[str, str] | None = None
) -> dict[str, object]:
    """Safe capability query; it never constructs a backend or reads material."""
    env = {} if environ is None else dict(environ)
    if argv or any("LIVE" in key.upper() for key in env):
        request_live_mode()
    return {
        "d232_live_capability": D232_LIVE_CAPABILITY,
        "live_hard_disabled": True,
        "live_runtime_enablement_exists": False,
        "usb_open_count": 0,
    }
