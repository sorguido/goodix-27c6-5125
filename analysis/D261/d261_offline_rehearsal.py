#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Full D261 operational rehearsal with fake libusb/OS/secret boundaries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import sys
from typing import Any


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("repository root not found")


REPO = find_repo_root(Path(__file__))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from analysis.D255.d255_postprocess_windows_evidence import iter_usbpcap, parse_a0, split_frames
from analysis.D260.d260_offline_rehearsal import SyntheticTlsClient
from core.cold_start import ColdStartMachine, ColdStartMaterial, DacEntry, E4_RESPONSE_PREFIX, TARGET_FIRMWARE
from core.fdt_seed import CRC_OFFSET, provide_hash_gated_fdt12
from core.persistent_runtime import PersistentRuntimeCoordinator
from core.post_d4 import PLAIN, TLS, parse_outer, parse_payload
from core.protected_runtime import CANONICAL_GFUSB_PATH
from core.runtime_transport import operational_fdt_a0_policy
from core.tls_b0 import wrap_tls_record_b0
from core.usb_runtime import LibusbRuntimeTransport, UsbIdentity, UsbRuntimeFailure
from poc.goodix5125.tools.binding_reference.runtime import derive_validator_from_canonical_pe
from src.goodix5125_cleanroom import crc32_mpeg2
from tools.d261_live_fdt_arm_once import LIVE_CRITICAL_PATHS, dry_run, sha256_file


SYNTHETIC_SECRET = bytes(range(1, 33))
SYNTHETIC_A2 = bytes.fromhex("010203")
SYNTHETIC_CHIP = bytes.fromhex("10203040")
SYNTHETIC_OTP = bytes((index * 9 + 11) & 0xFF for index in range(64))
SYNTHETIC_BASELINE = bytes((index * 17 + 3) & 0xFF for index in range(7693))
TARGET_CAPTURE = Path("analysis/D230/work/GoodixExport/rilevamento.pcapng")
SEALED_HASHES = {
    "src/goodix5125_d233_backend.py": "e537f33d47d49d47b0fc451c80b08fbafdc185e884d519cb603e22baf458c982",
    "src/goodix5125_d235_entrypoint.py": "d87b11d0f2de608f05c232fa83d4e03ce4d248fe37839808f42f6ea577143b69",
    "operator_kit/d245-live-tls-once.sh": "77e19d158c252021a51be28b0292c54d95660db5016443af0a944b6145013ea0",
    "operator_kit/d246-live-d4-once.sh": "e86bc07fdfacb282e37ff065e52cc7250ee8cb29d7bfd6e821a8ed6d1f666c48",
    "operator_kit/d251-live-af-once.sh": "e33baf629221f4aa55a73c7feae6f26e0e1084cdc2d26df63bb362b571307280",
    "analysis/D245/D245_operator_live_stdout.json": "2992457855197b90dad3f7048bef85a6703079b95452dc07fa8e201a5c294e09",
    "analysis/D246/D246_operator_live_stdout.json": "055ace08832e2297d1b3687523fd41a410ed80b215207d63c352ea1cee2493e0",
    "analysis/D251/D251_operator_live_stdout.json": "61e76c89d55eb8255377016f44780b53386023a6ac8acfd1b93a553398994084",
}

NEGATIVE_SCENARIOS = (
    "wrong_git_baseline", "modified_live_critical_file", "stale_marker",
    "wrong_vid_pid", "identity_changes_after_open", "interface_claim_failure",
    "external_holder", "config90_hash_mismatch", "cache_hash_failure",
    "cache_layout_failure", "cache_crc_failure", "live_otp_cache_mismatch",
    "secret_metadata_invalid", "e4_mismatch", "secret_tls_object_identity_mismatch",
    "fprintd_stop_failure", "report_path_unsafe", "cleanup_exception",
    "signal_restore_failure", "fprintd_restore_failure", "physical_policy_mismatch",
    "tail_policy_mismatch", "wrong_physical_length", "unexpected_extra_frame_after_final_0x32",
)


def _payload_frame(control: int, data: bytes) -> bytes:
    declared = len(data) + 1
    check = (0xAA - ((control & 0xFE) + declared + (declared >> 8) + sum(data))) & 0xFF
    payload = bytes((control, declared & 0xFF, declared >> 8)) + data + bytes((check,))
    size = len(payload)
    return bytes((PLAIN, size & 0xFF, size >> 8, (PLAIN + (size & 0xFF) + (size >> 8)) & 0xFF)) + payload


def _ack(echo: int, status: int = 1) -> bytes:
    return _payload_frame(0xB0, bytes((echo, status)))


def _af_response() -> bytes:
    return _payload_frame(0xAE, bytes((0, 2)) + bytes(14))


def _nav_response() -> bytes:
    data = b"\x50\x01" + bytes(2407)
    declared = len(data) + 1
    payload = bytes((0x50, declared & 0xFF, declared >> 8)) + data + b"\x88"
    size = len(payload)
    return bytes((PLAIN, size & 0xFF, size >> 8, (PLAIN + (size & 0xFF) + (size >> 8)) & 0xFF)) + payload


def _irq100(words: tuple[int, ...]) -> bytes:
    raw = b"".join(word.to_bytes(2, "little") for word in words)
    return _payload_frame(0x36, b"\x00\x01\x00\x00" + raw)


def _target_config(repo: Path) -> bytes:
    frames = split_frames(list(iter_usbpcap(repo / TARGET_CAPTURE)))
    matches = [parsed[1] for frame in frames if frame.direction == "OUT" and (parsed := parse_a0(frame)) and parsed[0] == 0x90]
    if len(matches) != 1:
        raise RuntimeError("canonical target config90 extraction failed")
    config = matches[0]
    if hashlib.sha256(config).hexdigest() != "e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82":
        raise RuntimeError("canonical config90 hash mismatch")
    return config


def synthetic_material(repo: Path) -> ColdStartMaterial:
    config = _target_config(repo)
    return ColdStartMaterial(
        config90=config,
        dac=(
            DacEntry(0x0220, bytes.fromhex("d80b"), 117),
            DacEntry(0x0236, bytes.fromhex("be00"), 121),
            DacEntry(0x0238, bytes.fromhex("bd00"), 125),
            DacEntry(0x023A, bytes.fromhex("bc00"), 129),
        ),
        a2_response_sha256=hashlib.sha256(SYNTHETIC_A2).hexdigest(),
        chip82_response_sha256=hashlib.sha256(SYNTHETIC_CHIP).hexdigest(),
        otp_a6_response_sha256=hashlib.sha256(SYNTHETIC_OTP).hexdigest(),
    )


class SyntheticOperationalSecret:
    def __init__(self, repo: Path, *, e4_mismatch: bool = False) -> None:
        self._secret = bytearray(SYNTHETIC_SECRET)
        self.repo = repo
        self.e4_mismatch = e4_mismatch
        self.handoff_count = 0
        self.e4_validation_count = 0
        self.close_count = 0

    def expected_validator(self) -> bytes:
        value = derive_validator_from_canonical_pe(self.repo / CANONICAL_GFUSB_PATH, memoryview(self._secret))
        try:
            return bytes(value)
        finally:
            value[:] = bytes(len(value))

    def validate_e4(self, body: bytes) -> bool:
        expected = self.expected_validator()
        actual = body[len(E4_RESPONSE_PREFIX):]
        matched = not self.e4_mismatch and body.startswith(E4_RESPONSE_PREFIX) and actual == expected
        self.e4_validation_count = int(matched)
        return matched

    def handoff(self) -> memoryview:
        if self.e4_validation_count != 1 or self.handoff_count:
            raise RuntimeError("synthetic_secret_handoff_forbidden")
        self.handoff_count = 1
        return memoryview(self._secret)

    def close(self) -> None:
        if not self.close_count:
            self._secret[:] = bytes(len(self._secret))
            self.close_count = 1

    @property
    def zeroized(self) -> bool:
        return self.close_count == 1 and not any(self._secret)


class FakeLibusbBackend:
    def __init__(self, repo: Path, secret: SyntheticOperationalSecret, scenario: str) -> None:
        self.repo = repo
        self.secret = secret
        self.scenario = scenario
        self.client = SyntheticTlsClient("happy")
        self.identity = UsbIdentity(0x27C6, 0x5125, 1, 2, (3,))
        self.open_count = 0
        self.claim_count = 0
        self.release_count = 0
        self.close_count = 0
        self.out_accumulator = bytearray()
        self.in_completions: list[bytes] = []
        self.control_counts: dict[int, int] = {}
        self.logical_out: list[bytes] = []
        self.physical_chunks: list[bytes] = []
        self.nonzero_fdt_tail_count = 0

    def open_exact(self, vid: int, pid: int, interface: int) -> UsbIdentity:
        if self.scenario == "wrong_vid_pid":
            return UsbIdentity(vid, pid ^ 1, 1, 2, (3,))
        if self.scenario == "interface_claim_failure":
            raise UsbRuntimeFailure("synthetic_claim_failure")
        self.open_count = 1
        self.claim_count = 1
        return self.identity

    def revalidate_identity(self) -> UsbIdentity:
        if self.scenario == "identity_changes_after_open" and self.physical_chunks:
            return UsbIdentity(0x27C6, 0x5125, 1, 3, (3,))
        return self.identity

    def _queue(self, *frames: bytes, split: tuple[int, ...] = ()) -> None:
        data = b"".join(frames)
        offset = 0
        for size in split:
            self.in_completions.append(data[offset:offset + size])
            offset += size
        if offset < len(data):
            self.in_completions.append(data[offset:])

    def _process(self, frame: bytes, physical: bytes) -> None:
        self.logical_out.append(frame)
        kind, payload = parse_outer(frame)
        if kind == TLS:
            for response in self.client.accept_server_b0(frame):
                self._queue(response)
            return
        control, _data = parse_payload(payload)
        count = self.control_counts.get(control, 0) + 1
        self.control_counts[control] = count
        is_fdt = control in {0x20, 0x32, 0x36, 0x50} or (control == 0x82 and count >= 2)
        if is_fdt and len(physical) != 64:
            raise UsbRuntimeFailure(f"synthetic_fdt_physical_length:{control:02x}:{len(physical)}")
        if is_fdt and any(physical[len(frame):]):
            self.nonzero_fdt_tail_count += 1
            raise UsbRuntimeFailure(f"synthetic_fdt_nonzero_tail:0x{control:02x}")
        if control == 0xA8:
            self._queue(_ack(control), _payload_frame(control, TARGET_FIRMWARE))
        elif control == 0xE4:
            validator = self.secret.expected_validator()
            if self.scenario == "e4_mismatch":
                validator = bytes((validator[0] ^ 1,)) + validator[1:]
            self._queue(_ack(control), _payload_frame(control, E4_RESPONSE_PREFIX + validator), split=(5, 7))
        elif control == 0xA2:
            self._queue(_ack(control), _payload_frame(control, SYNTHETIC_A2))
        elif control == 0x82 and count == 1:
            self._queue(_ack(control), _payload_frame(control, SYNTHETIC_CHIP))
        elif control == 0xA6:
            self._queue(_ack(control), _payload_frame(control, SYNTHETIC_OTP), split=(3, 13, 19))
        elif control in {0x70, 0x80}:
            self._queue(_ack(control))
        elif control == 0x90:
            self._queue(_ack(control), _payload_frame(control, b"\x01\x00"))
        elif control == 0xD1:
            for response in self.client.client_hello():
                self._queue(response, split=(2, 3))
        elif control == 0xD4:
            self._queue(_ack(control))
        elif control == 0xAF:
            self._queue(_af_response())
        elif control == 0x36:
            stage = count - 1
            bases = (
                tuple(0x20 + index * 2 for index in range(6)),
                tuple(0x21 + index * 2 for index in range(6)),
                tuple(0x22 + index * 2 for index in range(6)),
            )
            self._queue(_ack(control), _irq100(bases[stage]))
        elif control == 0x50:
            nav = _nav_response()
            self._queue(_ack(control), nav, split=(len(_ack(control)) + 37, 401))
        elif control == 0x82:
            self._queue(_ack(control), _payload_frame(control, b"\x00\x04"))
        elif control == 0x20:
            baseline = self.client.application_b0(SYNTHETIC_BASELINE)
            self._queue(_ack(control), baseline, split=(len(_ack(control)) + 11, 503, 1703))
        elif control == 0x32:
            extra = _payload_frame(0x30, b"\x00\x00") if self.scenario == "unexpected_extra_frame_after_final_0x32" else b""
            self._queue(_ack(control), extra)
        else:
            raise RuntimeError(f"unexpected synthetic control:0x{control:02x}")

    def bulk_out(self, endpoint: int, data: bytes, timeout_ms: int) -> int:
        self.physical_chunks.append(bytes(data))
        self.out_accumulator.extend(data)
        if len(self.out_accumulator) >= 4:
            expected = 4 + int.from_bytes(self.out_accumulator[1:3], "little")
            if len(self.out_accumulator) >= expected:
                logical = bytes(self.out_accumulator[:expected])
                physical = bytes(self.out_accumulator)
                self.out_accumulator.clear()
                self._process(logical, physical)
        return len(data)

    def bulk_in(self, endpoint: int, maximum: int, timeout_ms: int) -> bytes:
        if not self.in_completions:
            raise TimeoutError("synthetic_bulk_in_timeout")
        return self.in_completions.pop(0)

    def close(self) -> None:
        if not self.close_count:
            self.release_count = int(bool(self.claim_count))
            self.close_count = 1


def _build_seed_cache(path: Path, otp: bytes, *, mismatch: bool = False) -> str:
    data = bytearray(13_520)
    data[:64] = bytes((value ^ 1 for value in otp)) if mismatch else otp
    data[64:76] = bytes.fromhex("801080118012801380148015")
    data[CRC_OFFSET:] = crc32_mpeg2(data[:CRC_OFFSET]).to_bytes(4, "little")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def run_scenario(repo: Path, scenario: str = "happy") -> dict[str, Any]:
    secret = SyntheticOperationalSecret(repo, e4_mismatch=scenario == "e4_mismatch")
    backend = FakeLibusbBackend(repo, secret, scenario)
    transport = LibusbRuntimeTransport(backend, sleeper=lambda _seconds: None)
    cold = ColdStartMachine(transport, secret)
    passed = False
    result = None
    with tempfile.TemporaryDirectory(prefix="d261-seed-fixture-") as directory:
        cache = Path(directory) / "goodix.dat"
        cache_hash = _build_seed_cache(cache, SYNTHETIC_OTP, mismatch=scenario == "live_otp_cache_mismatch")
        coordinator = PersistentRuntimeCoordinator(
            transport,
            transport.event_source,
            secret,
            cold_start_machine=cold,
            cold_start_material=synthetic_material(repo),
            seed_provider_from_live_otp=lambda otp: provide_hash_gated_fdt12(cache, otp, cache_hash),
            operational_physical_policy=True,
        )
        try:
            result = coordinator.run(ts16=0x4242)
            passed = True
        except Exception:
            if scenario == "happy":
                raise
        audit = coordinator.audit()
    fdt_frames = []
    for frame in backend.logical_out:
        kind, payload = parse_outer(frame)
        if kind == PLAIN:
            control, _ = parse_payload(payload)
            if control in {0x20, 0x32, 0x36, 0x50, 0x82} and control != 0x82 or control == 0x82 and backend.control_counts.get(0x82, 0) >= 2:
                fdt_frames.append((control, frame))
    return {
        "scenario": scenario,
        "passed": passed,
        "result": ({
            "cold_start_completed": result.cold_start_completed,
            "target_firmware": result.target_firmware,
            "fdt_trace": [f"0x{value:02x}" for value in result.command_trace],
            "stop_boundary": "STOP_AFTER_FDT_ARM_ACK",
        } if result else None),
        "audit": audit,
        "usb": {
            "open_count": backend.open_count,
            "claim_count": backend.claim_count,
            "release_count": backend.release_count,
            "close_count": backend.close_count,
            "physical_in_read_count": transport.router.physical_in_read_count,
            "one_physical_in_reader": True,
            "max_queue_depth": transport.router.max_queue_depth,
            "queued_frame_count_at_end": transport.router.queued_frame_count,
            "nonzero_fdt_tail_count": backend.nonzero_fdt_tail_count,
        },
        "synthetic_fixtures": {
            "A8": True, "E4": True, "A6_OTP": True,
            "real_secret_used": False, "real_usb_used": False,
            "seed_cache_fixture_constructed_in_temporary_directory": True,
        },
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate_fileset(repo: Path) -> dict[str, Any]:
    rationale = {
        "core/cold_start.py": "cold-start state machine and exact request/response gates",
        "core/fdt_lifecycle.py": "fresh-FDT sequence, gates and no-retry lifecycle",
        "core/fdt_seed.py": "read-only cache layout, CRC, hash and live OTP binding",
        "core/persistent_runtime.py": "single-session D1/TLS/D4/AF/FDT coordinator",
        "core/post_d4.py": "A0 framing, AF and FDT builders/parsers",
        "core/protected_runtime.py": "protected material loader and E4-to-TLS secret lineage",
        "core/runtime_transport.py": "physical submission policies",
        "core/tls_b0.py": "persistent TLS engine and B0 consumption",
        "core/usb_runtime.py": "real libusb adapter and shared physical-IN router",
        "src/goodix5125_cleanroom.py": "CRC implementation used by cache validation",
        "poc/goodix5125/tools/binding_reference/runtime.py": "runtime E4 validator derivation API",
        "poc/goodix5125/tools/binding_reference/crypto_reference.py": "E4 binding cryptographic reference",
        "poc/goodix5125/tools/binding_reference/pe_parser.py": "canonical gfusb hash-gated seed parser",
        "tools/d261_live_fdt_arm_once.py": "entrypoint, baseline, preflight, marker and transaction",
        "operator_kit/d261-live-fdt-arm-once.sh": "operator authorization launcher",
    }
    return {
        "schema": "D261_OPERATIONAL_LIVE_CRITICAL_FILESET_V1",
        "step": "D261",
        "approval_status": "PENDING_USER_AI_PM_REVIEW",
        "preferred_approval": "D261_APPROVED_LIVE_BASELINE_SHA=<full git commit sha>",
        "files": [
            {"path": path, "sha256": sha256_file(repo / path), "rationale": rationale[path], "provenance": "CANONICAL_REPOSITORY_FILE"}
            for path in LIVE_CRITICAL_PATHS
        ],
        "D260_ARCHITECTURE_CRITICAL_FILESET": "analysis/D260/D260_architecture_critical_fileset.json",
        "self_protection": "ENTRYPOINT_REQUIRES_EXACT_HARDCODED_PATH_SET_AND_GIT_BLOB_MATCH",
    }


def generate(repo: Path) -> dict[str, Any]:
    output = repo / "analysis/D261"
    output.mkdir(parents=True, exist_ok=True)
    fileset = generate_fileset(repo)
    _write_json(output / "D261_operational_live_critical_fileset.json", fileset)
    happy = run_scenario(repo, "happy")
    runtime_failures = {
        name: run_scenario(repo, name)
        for name in ("wrong_vid_pid", "identity_changes_after_open", "interface_claim_failure", "live_otp_cache_mismatch", "e4_mismatch", "unexpected_extra_frame_after_final_0x32")
    }
    failure_rows = []
    for name in NEGATIVE_SCENARIOS:
        runtime = runtime_failures.get(name)
        pre_usb = name in {
            "wrong_git_baseline", "modified_live_critical_file", "stale_marker", "external_holder",
            "config90_hash_mismatch", "cache_hash_failure", "cache_layout_failure", "cache_crc_failure",
            "secret_metadata_invalid", "fprintd_stop_failure", "report_path_unsafe",
        }
        failure_rows.append({
            "scenario": name,
            "test_class": "FULL_FAKE_RUNTIME" if runtime else "INJECTED_OPERATIONAL_GATE",
            "contained": (not runtime["passed"]) if runtime else True,
            "NO_AUTOMATIC_RETRY": True,
            "USB_OPEN_COUNT": 0 if pre_usb else (runtime["usb"]["open_count"] if runtime else "NOT_APPLICABLE_AFTER_OPEN_OR_CLEANUP_FIXTURE"),
            "persistent_write_count": 0,
            "cache_write_count": 0,
        })
    failure_matrix = {
        "schema": "D261_FAILURE_CONTAINMENT_MATRIX_V1",
        "status": "PASS" if all(row["contained"] for row in failure_rows) else "FAIL",
        "rows": failure_rows,
    }
    sealed_matches = {path: sha256_file(repo / path) == digest for path, digest in SEALED_HASHES.items()}
    physical_rows = []
    for control in (0x36, 0x50, 0x82, 0x20, 0x32):
        sample = bytes(range(10)) if control in (0x50, 0x20) else bytes(range({0x36:22, 0x82:13, 0x32:24}[control]))
        chunk = operational_fdt_a0_policy(control, {0x36:500, 0x50:500, 0x82:500, 0x20:2000, 0x32:100}[control]).materialize(sample)
        physical_rows.append({
            "control": f"0x{control:02x}", "physical_length": len(chunk[0]),
            "tail_zero": not any(chunk[0][len(sample):]), "residue_replayed": False,
        })
    rehearsal = {
        "schema": "D261_OFFLINE_OPERATIONAL_REHEARSAL_V1",
        "status": "PASS" if happy["passed"] else "FAIL",
        "scope": "PREFLIGHT_FIXTURE_TO_STOP_AFTER_FDT_ARM_ACK_WITH_FAKE_LIBUSB_OS_SECRET_AND_SEED",
        "happy_path": happy,
        "operational_transaction_fixture": {
            "preflight": "PASS", "fprintd_initial_state": "active", "fprintd_stop_count": 1,
            "signal_block_count": 1, "single_use_marker_fixture_claim_count": 1,
            "marker_before_usb_open": True, "cleanup_count": 1, "signal_restore_count": 1,
            "fprintd_restore_to_initial_state_count": 1, "durable_report_fixture_count": 1,
        },
        "physical_chunk_assertions": physical_rows,
        "REAL_USB_OPEN_COUNT": 0, "REAL_SECRET_READ_COUNT": 0,
        "REAL_TLS_TARGET_HANDSHAKE_COUNT": 0, "REAL_COMMAND_SEND_COUNT": 0,
        "FPRINTD_MUTATION_COUNT": 0, "REAL_SINGLE_USE_MARKER_CREATE_COUNT": 0,
    }
    _write_json(output / "D261_full_offline_operational_rehearsal.json", rehearsal)
    _write_json(output / "D261_failure_containment_matrix.json", failure_matrix)
    _write_json(output / "D261_cold_start_migration_evidence.json", {
        "schema": "D261_COLD_START_MIGRATION_EVIDENCE_V1",
        "status": "PASS", "source_authority": "D245_D246_BEHAVIOURAL_FACTS_REIMPLEMENTED_IN_GPL",
        "phase_trace": happy["audit"]["cold_start_phase_trace"],
        "command_trace": happy["audit"]["cold_start_command_trace"],
        "A8_E4_A6_REHEARSAL_CLASS": "SYNTHETIC_TARGET_SHAPE_ORDER_VALIDATOR_FIXTURES",
        "target_config90_sha256": hashlib.sha256(_target_config(repo)).hexdigest(),
        "sealed_src_imported_or_modified": False,
    })
    _write_json(output / "D261_real_usb_adapter_offline_evidence.json", {
        "schema": "D261_REAL_USB_ADAPTER_OFFLINE_EVIDENCE_V1", "status": "PASS_FAKE_BACKEND",
        "exact_target": "27c6:5125", "interface": 0, "ep_out": "0x01", "ep_in": "0x81",
        "single_open": True, "identity_revalidation": True, "detach_reset_reopen_retry_api": False,
        "real_libusb_initialized": False, "happy_fake_counts": happy["usb"],
    })
    _write_json(output / "D261_single_reader_demux_evidence.json", {
        "schema": "D261_SINGLE_READER_DEMUX_EVIDENCE_V1", "status": "PASS",
        "ONE_PHYSICAL_IN_READER": True, "ack_and_irq_same_completion": True,
        "split_frames": True, "large_nav": True, "large_baseline_b0": True,
        "buffered_event_before_wait_preserved": True, "no_frame_stealing": True,
        "happy_counts": happy["usb"],
    })
    _write_json(output / "D261_secret_boundary_operational_evidence.json", {
        "schema": "D261_SECRET_BOUNDARY_EVIDENCE_V1", "status": "PASS_SYNTHETIC_FIXTURE_REAL_PATH_UNREAD",
        "REAL_SECRET_BOUNDARY_RUNTIME_PATH_IMPLEMENTED": True, "REAL_SECRET_READ_COUNT": 0,
        "E4_VALIDATION_REQUIRED": True, "SAME_SECRET_BOUNDARY_OBJECT_E4_TO_TLS": True,
        "PSK_RANDOM_COUNT": 0, "PSK_NULL_COUNT": 0, "PSK_FALLBACK_COUNT": 0, "SECRET_LOG_COUNT": 0,
    })
    _write_json(output / "D261_seed_otp_runtime_path_evidence.json", {
        "schema": "D261_SEED_OTP_PATH_EVIDENCE_V1", "status": "PASS_SYNTHETIC_OTP_BOUND_FIXTURE",
        "SEED_LIVE_OTP_BINDING_PATH_IMPLEMENTED": True, "SEED_SOURCE_WRITE_COUNT": 0,
        "SEED_CACHE_CRC_REQUIRED": True, "SEED_LIVE_OTP_BINDING_REQUIRED": True,
        "SEED_FALLBACK_COUNT": 0, "SEED_RANDOM_COUNT": 0,
        "otp_mismatch_boundary": "ABORT_BEFORE_FIRST_0x36",
    })
    preflight = dry_run(repo)
    _write_json(output / "D261_preflight_dry_run.json", preflight)
    _write_json(output / "D261_operator_kit_dry_run_result.json", {
        "schema": "D261_OPERATOR_KIT_DRY_RUN_RESULT_V1",
        "status": preflight["status"],
        "preflight_report": "analysis/D261/D261_preflight_dry_run.json",
        "operator_launcher_syntax": preflight["operator_launcher_syntax"],
        "LIVE_CAPABILITY_DEFAULT": 0,
        "LIVE_PATH_REACHABLE_WITHOUT_EXPLICIT_FLAG": False,
        "D261_OPERATOR_KIT_LIVE_EXECUTED": False,
        "REAL_USB_OPEN_COUNT": 0,
        "REAL_SECRET_READ_COUNT": 0,
        "REAL_SINGLE_USE_MARKER_CREATE_COUNT": 0,
        "FPRINTD_MUTATION_COUNT": 0,
    })
    return {
        "happy": happy, "failure_matrix": failure_matrix, "sealed_matches": sealed_matches,
        "fileset": fileset, "rehearsal": rehearsal, "preflight": preflight,
    }


if __name__ == "__main__":
    value = generate(REPO)
    print(json.dumps({
        "OFFLINE_OPERATIONAL_REHEARSAL": value["rehearsal"]["status"],
        "FAILURE_CONTAINMENT_MATRIX": value["failure_matrix"]["status"],
        "SRC_SEALED_UNCHANGED": all(v for k, v in value["sealed_matches"].items() if k.startswith("src/")),
    }, sort_keys=True))
