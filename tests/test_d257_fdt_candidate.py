# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from core.fdt_lifecycle import (
    EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE,
    FIRST_FDT36_COMMAND_TIMEOUT_MS,
    ExactFreshFdtBootstrapMachine,
    FdtLifecycle,
    FdtLifecycleState,
    FreshFdtBootstrapMachine,
    PERSISTENT_COMMAND_FAMILIES,
    SAFE_DEVICE_COMMANDS,
    SPECIAL_RECOVERY_COMMANDS,
)
from core.fdt_seed import (
    CACHE_SIZE,
    SEED_PROVIDER_FAIL_CLOSED,
    SEED_PROVIDER_PASS,
    provide_fdt12,
)
from core.post_d4 import (
    FIRST_IMAGE_RECEIVED,
    PLAIN,
    TLS,
    FirstImageMachine,
    InvalidTransition,
    UnexpectedAck,
    _checksum,
    parse_outer,
    parse_payload,
)
from src.goodix5125_cleanroom import crc32_mpeg2, encode_synthetic_record
from analysis.D257 import d257_offline_replay as D257_REPLAY


REPO = Path(__file__).resolve().parents[1]


def payload(control: int, data: bytes) -> bytes:
    size = len(data) + 1
    return bytes((control, size & 0xFF, size >> 8)) + data + bytes((_checksum(control, data),))


def outer(body: bytes) -> bytes:
    lo, hi = len(body) & 0xFF, len(body) >> 8
    return bytes((PLAIN, lo, hi, (PLAIN + lo + hi) & 0xFF)) + body


def ack(echo: int) -> bytes:
    return outer(payload(0xB0, bytes((echo, 1))))


def nav_response() -> bytes:
    data = b"\x50\x01" + bytes(2407)
    body = bytes((0x50, 0x6A, 0x09)) + data + b"\x88"
    return outer(body)


def fdt_delta_response() -> bytes:
    return outer(payload(0x82, b"\x80\x1d"))


def baseline_b0_shape() -> bytes:
    body = bytes(7722)
    return bytes((TLS, 0x2A, 0x1E, (TLS + 0x2A + 0x1E) & 0xFF)) + body


def af_response(*, pov: bool = False) -> bytes:
    flags = 0x03 if pov else 0x02
    return outer(payload(0xAE, bytes((0, flags)) + bytes(14)))


def irq100(raw_words: tuple[int, ...]) -> bytes:
    raw = b"".join(word.to_bytes(2, "little") for word in raw_words)
    return payload(0x36, b"\x00\x01\x00\x00" + raw)


def irq2() -> bytes:
    return payload(0x32, b"\x02\x00\x3f\x00" + bytes(12))


def synthetic_raster() -> tuple[int, ...]:
    return tuple((index * 29 + index // 80 * 7) & 0xFFF for index in range(5120))


def image_payload() -> bytes:
    record = encode_synthetic_record(synthetic_raster())
    return payload(0x20, b"\x01\x00\x00\x00\x00" + record)


def cache_bytes(otp: bytes, seed: bytes) -> bytes:
    body = otp + seed + bytes(3200) + bytes(10240)
    if len(body) != CACHE_SIZE - 4:
        raise AssertionError("synthetic cache layout")
    return body + crc32_mpeg2(body).to_bytes(4, "little")


class ScriptedTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.timeouts = []

    def exchange(self, request, *, timeout_ms=None):
        self.requests.append(request)
        self.timeouts.append(timeout_ms)
        if not self.responses:
            raise AssertionError("unexpected transport exchange")
        return self.responses.pop(0)


class D257SeedProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "explicit-cache.bin"
        self.otp = bytes((index * 5 + 3) & 0xFF for index in range(64))
        self.seed = bytes((index * 11 + 1) & 0xFF for index in range(12))

    def write_cache(self, data: bytes | None = None) -> bytes:
        content = cache_bytes(self.otp, self.seed) if data is None else data
        self.path.write_bytes(content)
        return content

    def test_happy_path_layout_crc_otp_and_read_only_extraction(self):
        before = self.write_cache()
        before_stat = self.path.stat()
        result = provide_fdt12(self.path, self.otp)
        after_stat = self.path.stat()
        self.assertEqual(result.status, SEED_PROVIDER_PASS)
        self.assertEqual(result.require_seed(), self.seed)
        self.assertEqual(result.provenance.file_sha256, hashlib.sha256(before).hexdigest())
        self.assertTrue(result.provenance.crc_valid)
        self.assertEqual(result.provenance.crc_byte_order, "little")
        self.assertEqual(result.provenance.otp_binding, "MATCH")
        self.assertTrue(result.provenance.read_only)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(before_stat.st_mtime_ns, after_stat.st_mtime_ns)

    def test_crc_failure_is_fail_closed(self):
        damaged = bytearray(self.write_cache())
        damaged[100] ^= 0x80
        self.path.write_bytes(damaged)
        result = provide_fdt12(self.path, self.otp)
        self.assertEqual(result.status, SEED_PROVIDER_FAIL_CLOSED)
        self.assertEqual(result.failure_reason, "CACHE_CRC_MISMATCH")
        self.assertIsNone(result.fdt12)

    def test_otp_binding_failure_is_fail_closed(self):
        self.write_cache()
        result = provide_fdt12(self.path, bytes(reversed(self.otp)))
        self.assertEqual(result.failure_reason, "CACHE_OTP_BINDING_MISMATCH")
        self.assertIsNone(result.fdt12)

    def test_size_layout_and_absent_seed_fail_closed(self):
        self.write_cache(bytes(CACHE_SIZE - 1))
        self.assertEqual(provide_fdt12(self.path, self.otp).failure_reason, "CACHE_SIZE_MISMATCH")
        self.write_cache(cache_bytes(self.otp, bytes(12)))
        result = provide_fdt12(self.path, self.otp)
        self.assertEqual(result.failure_reason, "CACHE_FDT12_ABSENT")
        self.assertIsNone(result.fdt12)

    def test_no_hardcoded_d255_seed_or_fallback(self):
        evidence = json.loads((REPO / "analysis/D255/D255_recovered_postprocess/D255_sanitized_evidence.json").read_text())
        d255_seed = evidence["seed_correlation"]["FIRST_FDT36_SEED"]
        provider_source = (REPO / "core/fdt_seed.py").read_text(encoding="utf-8")
        self.assertNotIn(d255_seed.lower(), provider_source.lower())
        result = provide_fdt12(Path(self.temp.name) / "missing.bin", self.otp)
        self.assertEqual(result.status, SEED_PROVIDER_FAIL_CLOSED)
        self.assertIsNone(result.fdt12)


class D257LifecycleTests(unittest.TestCase):
    def make_seed_result(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "cache.bin"
        otp = bytes(range(64))
        path.write_bytes(cache_bytes(otp, bytes(range(1, 13))))
        return provide_fdt12(path, otp)

    def test_fresh_bootstrap_cancel_reentry_terminal_contract(self):
        transport = ScriptedTransport((
            [ack(0x36)], [ack(0x36)], [ack(0x36)], [ack(0x32)], [ack(0x32)],
        ))
        lifecycle = FdtLifecycle()
        lifecycle.observe_af_state(False)
        candidate = FreshFdtBootstrapMachine(transport, lifecycle)
        candidate.begin(self.make_seed_result())
        raw_sets = (
            (0x015E, 0x017E, 0x0146, 0x016E, 0x014E, 0x016C),
            (0x015C, 0x017C, 0x0148, 0x0170, 0x0150, 0x016E),
            (0x015A, 0x017A, 0x014A, 0x0172, 0x0152, 0x0170),
        )
        for words in raw_sets:
            candidate.manual_sample(irq100(words))
        candidate.arm(0x1234)
        candidate.cancel_pending_receive()
        candidate.reenter_and_arm(0x2345)
        candidate.terminal_cancel_and_stop()

        self.assertEqual(lifecycle.state, FdtLifecycleState.TERMINAL_STOPPED)
        self.assertEqual(candidate.manual_attempt_count, 3)
        self.assertEqual(candidate.arm_attempt_count, 2)
        self.assertEqual(lifecycle.device_command_trace, (0x36, 0x36, 0x36, 0x32, 0x32))
        self.assertFalse(set(lifecycle.device_command_trace) & SPECIAL_RECOVERY_COMMANDS)
        self.assertFalse(set(lifecycle.device_command_trace) & PERSISTENT_COMMAND_FAMILIES)
        self.assertEqual(lifecycle.retry_count, 0)
        self.assertEqual(lifecycle.persistent_write_family_count, 0)
        cancel_rows = [row for row in lifecycle.transitions if "CANCEL" in row.event]
        self.assertEqual(len(cancel_rows), 2)
        self.assertTrue(all(not row.device_commands for row in cancel_rows))
        stop = lifecycle.transitions[-1]
        self.assertEqual(stop.event, "TERMINAL_STOP")
        self.assertEqual(stop.device_commands, ())

        boundary = lifecycle.request_full_cold_start()
        self.assertEqual(boundary.target, FdtLifecycleState.FULL_COLD_START_REQUIRED.value)
        self.assertEqual(boundary.device_commands, ())
        self.assertNotEqual(boundary.event, "BEGIN_SESSION_REENTRY")

    def test_invalid_transition_fails_closed(self):
        lifecycle = FdtLifecycle()
        with self.assertRaises(InvalidTransition):
            lifecycle.cancel_pending_receive()
        self.assertEqual(lifecycle.state, FdtLifecycleState.FAILED_CLOSED)
        transition_count = len(lifecycle.transitions)
        with self.assertRaises(InvalidTransition):
            lifecycle.arm_fdt()
        self.assertEqual(len(lifecycle.transitions), transition_count)

    def test_invalid_seed_stops_before_transport(self):
        transport = ScriptedTransport(())
        lifecycle = FdtLifecycle()
        lifecycle.observe_af_state(False)
        candidate = FreshFdtBootstrapMachine(transport, lifecycle)
        missing = provide_fdt12(REPO / "does-not-exist", bytes(64))
        with self.assertRaises(InvalidTransition):
            candidate.begin(missing)
        self.assertEqual(lifecycle.state, FdtLifecycleState.FAILED_CLOSED)
        self.assertEqual(transport.requests, [])

    def test_failed_manual_stage_cannot_retry(self):
        transport = ScriptedTransport(([ack(0x32)],))
        lifecycle = FdtLifecycle()
        lifecycle.observe_af_state(False)
        candidate = FreshFdtBootstrapMachine(transport, lifecycle)
        candidate.begin(self.make_seed_result())
        event = irq100((0x015E, 0x017E, 0x0146, 0x016E, 0x014E, 0x016C))

        with self.assertRaises(UnexpectedAck):
            candidate.manual_sample(event)
        self.assertEqual(lifecycle.state, FdtLifecycleState.FAILED_CLOSED)
        self.assertEqual(candidate.manual_attempt_count, 1)
        self.assertEqual(len(transport.requests), 1)

        with self.assertRaises(InvalidTransition):
            candidate.manual_sample(event)
        self.assertEqual(candidate.manual_attempt_count, 1)
        self.assertEqual(len(transport.requests), 1)

    def test_target_irq2_0x22_exactly_once_and_first_image(self):
        transport = ScriptedTransport(([af_response()], [ack(0x32)], [ack(0x22)]))
        lifecycle = FdtLifecycle()
        machine = FirstImageMachine(transport, lifecycle=lifecycle)
        self.assertFalse(machine.query_state(1).pov_valid)
        machine.begin_capture(bytes(range(12)), 2)
        self.assertIsNone(machine.receive_payload(irq2()))
        image = machine.receive_payload(image_payload())
        self.assertEqual(image, synthetic_raster())
        self.assertEqual(machine.phase, FIRST_IMAGE_RECEIVED)
        self.assertEqual(lifecycle.state, FdtLifecycleState.FIRST_IMAGE_RECEIVED)
        controls = [parse_payload(parse_outer(request)[1])[0] for request in transport.requests]
        self.assertEqual(controls, [0xAF, 0x32, 0x22])
        self.assertEqual(controls.count(0x22), 1)
        self.assertEqual(lifecycle.device_command_trace, (0x32, 0x22))

    def test_exact_bootstrap_happy_path_requires_all_observed_interstages(self):
        transport = ScriptedTransport((
            [ack(0x36)],
            [ack(0x50), nav_response()],
            [ack(0x36)],
            [ack(0x82), fdt_delta_response()],
            [ack(0x20), baseline_b0_shape()],
            [ack(0x36)],
            [ack(0x32)],
        ))
        lifecycle = FdtLifecycle()
        lifecycle.observe_af_state(False)
        candidate = ExactFreshFdtBootstrapMachine(
            transport,
            lifecycle,
            nav_semantic_gate=lambda data: len(data) == 2409,
            delta_semantic_gate=lambda data: data == b"\x80\x1d",
            decrypt_baseline_b0=lambda _frame: image_payload(),
            baseline_semantic_gate=lambda pixels: pixels == synthetic_raster(),
        )
        candidate.begin(self.make_seed_result())
        raw_sets = (
            (0x015E, 0x017E, 0x0146, 0x016E, 0x014E, 0x016C),
            (0x015C, 0x017C, 0x0148, 0x0170, 0x0150, 0x016E),
            (0x015A, 0x017A, 0x014A, 0x0172, 0x0152, 0x0170),
        )
        candidate.manual_sample(irq100(raw_sets[0]))
        candidate.nav_interstage()
        candidate.manual_sample(irq100(raw_sets[1]))
        candidate.delta_and_baseline_interstage()
        candidate.manual_sample(irq100(raw_sets[2]))
        candidate.arm(0x1234)

        self.assertEqual(lifecycle.device_command_trace, EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE)
        self.assertEqual(candidate.first_0x36_attempt_count, 1)
        self.assertEqual(candidate.first_0x36_timeout_ms, FIRST_FDT36_COMMAND_TIMEOUT_MS)
        self.assertEqual(transport.timeouts, [FIRST_FDT36_COMMAND_TIMEOUT_MS] * 7)
        self.assertTrue(candidate.nav_gate_passed)
        self.assertTrue(candidate.delta_gate_passed)
        self.assertTrue(candidate.baseline_gate_passed)
        self.assertEqual(lifecycle.retry_count, 0)
        self.assertEqual(lifecycle.persistent_write_family_count, 0)

    def test_exact_first_0x36_failure_is_single_shot_and_fail_closed(self):
        transport = ScriptedTransport(([ack(0x32)],))
        lifecycle = FdtLifecycle()
        lifecycle.observe_af_state(False)
        candidate = ExactFreshFdtBootstrapMachine(transport, lifecycle)
        candidate.begin(self.make_seed_result())
        event = irq100((0x015E, 0x017E, 0x0146, 0x016E, 0x014E, 0x016C))

        with self.assertRaises(UnexpectedAck):
            candidate.manual_sample(event)
        self.assertEqual(candidate.first_0x36_attempt_count, 1)
        self.assertEqual(lifecycle.retry_count, 0)
        self.assertEqual(lifecycle.state, FdtLifecycleState.FAILED_CLOSED)
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(transport.timeouts, [FIRST_FDT36_COMMAND_TIMEOUT_MS])
        with self.assertRaises(InvalidTransition):
            candidate.manual_sample(event)
        self.assertEqual(candidate.first_0x36_attempt_count, 1)
        self.assertEqual(len(transport.requests), 1)

    def test_lifecycle_allowlist_excludes_recovery_and_persistence(self):
        self.assertFalse(SAFE_DEVICE_COMMANDS & SPECIAL_RECOVERY_COMMANDS)
        self.assertFalse(SAFE_DEVICE_COMMANDS & PERSISTENT_COMMAND_FAMILIES)


class D257IntegrationReplayTests(unittest.TestCase):
    def test_real_private_replay_is_redacted_and_provenance_separated(self):
        result = D257_REPLAY.run(REPO)
        self.assertEqual(result["closure"]["PROJECTED_FDT_SUBSEQUENCE_REPLAY"], "PASS_HISTORICAL")
        self.assertEqual(
            result["closure"]["EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY"],
            "BLOCKED_DYNAMIC_HOST_GATES_NOT_DERIVABLE_FROM_D255_RAW",
        )
        self.assertFalse(result["closure"]["FDT_OFFLINE_CANDIDATE_CLOSED"])
        self.assertFalse(result["closure"]["SEED_FRESHNESS_IS_SOLE_LIVE_BLOCKER"])
        self.assertEqual(result["closure"]["IRQ2_0x22_PATH"], "PASS_EXACTLY_ONCE")
        self.assertTrue(result["freshness_audit"][
            "current_corpus_exhausted_for_seed_freshness_generalization"])
        self.assertFalse(result["provenance_separation"]["same_single_run_claimed"])
        rendered = json.dumps(result, sort_keys=True).lower()
        d255_evidence = json.loads(
            (REPO / "analysis/D255/D255_recovered_postprocess/D255_sanitized_evidence.json").read_text()
        )
        self.assertNotIn(d255_evidence["seed_correlation"]["FIRST_FDT36_SEED"].lower(), rendered)
        _run, _wire, _frames, otp, _cache = D257_REPLAY._load_d255(REPO)
        self.assertNotIn(otp.hex(), rendered)
        self.assertEqual(result["safety"]["REAL_USB_OPEN_COUNT"], 0)
        self.assertEqual(result["safety"]["REAL_HARDWARE_ACTION_COUNT"], 0)

    def test_exact_raw_timeline_and_temporal_provenance_are_programmatic(self):
        result = D257_REPLAY.run(REPO)
        exact = result["exact_bootstrap_audit"]
        self.assertEqual(
            exact["timeline"]["out_control_trace"][1:],
            ["0x36", "0x50", "0x36", "0x82", "0x20", "0x36", "0x32"],
        )
        temporal = exact["temporal_provenance"]
        self.assertFalse(temporal["SAME_ATTACH_SEED_GENERATION_REQUIRED"])
        self.assertTrue(temporal["PERSISTED_PRE_ATTACH_CACHE_REUSE_PROVEN"])
        self.assertFalse(temporal["GENERAL_CACHE_TTL_PROVEN"])
        self.assertAlmostEqual(temporal["CACHE_MTIME_TO_ATTACH_BEGIN_SECONDS"], 1626.1975757, places=6)
        self.assertAlmostEqual(temporal["CACHE_MTIME_TO_FIRST_0x36_SECONDS"], 1635.6222, places=6)

        blocked = next(row for row in result["scenarios"]
                       if row["name"] == "EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY")
        self.assertEqual(blocked["first_0x36_attempt_count"], 1)
        self.assertEqual(blocked["requests_executed_before_fail_closed"], ["0x36", "0x50"])
        self.assertEqual(blocked["automatic_retry_count"], 0)


if __name__ == "__main__":
    unittest.main()
