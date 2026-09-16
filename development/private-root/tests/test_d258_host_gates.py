# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
from pathlib import Path
import tempfile
import unittest

from analysis.D258 import d258_host_gate_audit as AUDIT
from analysis.D258 import d258_offline_replay as REPLAY
from core.fdt_lifecycle import (
    COMMAND_TIMEOUT_MS,
    COMMAND_TIMEOUT_POLICY,
    ExactFreshFdtBootstrapMachine,
    FdtLifecycle,
    PERSISTENT_COMMAND_FAMILIES,
    SAFE_DEVICE_COMMANDS,
    SPECIAL_RECOVERY_COMMANDS,
    fdt_delta_threshold,
    fdt_raw_delta_within_threshold,
)
from core.fdt_seed import CACHE_SIZE, provide_fdt12
from core.post_d4 import (
    ChecksumMismatch,
    InvalidTransition,
    LengthMismatch,
    PLAIN,
    TLS,
    UnexpectedEvent,
    _checksum,
    parse_nav_baseline_response,
)
from src.goodix5125_cleanroom import crc32_mpeg2, encode_synthetic_record


REPO = Path(__file__).resolve().parents[1]


def payload(control: int, data: bytes) -> bytes:
    size = len(data) + 1
    return bytes((control, size & 0xFF, size >> 8)) + data + bytes((_checksum(control, data),))


def outer(body: bytes) -> bytes:
    lo, hi = len(body) & 0xFF, len(body) >> 8
    return bytes((PLAIN, lo, hi, (PLAIN + lo + hi) & 0xFF)) + body


def ack(echo: int) -> bytes:
    return outer(payload(0xB0, bytes((echo, 1))))


def nav_response(*, marker: int = 0x88) -> bytes:
    data = b"\x50\x01" + bytes(2407)
    body = bytes((0x50, 0x6A, 0x09)) + data + bytes((marker,))
    return outer(body)


def delta_response(data: bytes = b"\x80\x1d") -> bytes:
    return outer(payload(0x82, data))


def baseline_b0(size: int = 7726) -> bytes:
    body_size = size - 4
    lo, hi = body_size & 0xFF, body_size >> 8
    return bytes((TLS, lo, hi, (TLS + lo + hi) & 0xFF)) + bytes(body_size)


def irq100(words: tuple[int, ...]) -> bytes:
    raw = b"".join(word.to_bytes(2, "little") for word in words)
    return payload(0x36, b"\x00\x01\x00\x00" + raw)


def image_payload() -> bytes:
    pixels = tuple((index * 17 + index // 80) & 0xFFF for index in range(5120))
    return payload(0x20, b"\x01\x00\x00\x00\x00" + encode_synthetic_record(pixels))


def seed_result(directory: Path):
    otp = bytes(range(64))
    seed = bytes(range(1, 13))
    body = otp + seed + bytes(3200) + bytes(10240)
    data = body + crc32_mpeg2(body).to_bytes(4, "little")
    assert len(data) == CACHE_SIZE
    path = directory / "cache.bin"
    path.write_bytes(data)
    return provide_fdt12(path, otp)


class ScriptedTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.timeouts = []

    def exchange(self, request, *, timeout_ms=None):
        self.requests.append(request)
        self.timeouts.append(timeout_ms)
        if not self.responses:
            raise AssertionError("unexpected exchange")
        return self.responses.pop(0)


class D258GateTests(unittest.TestCase):
    def test_hash_gated_static_audit_and_exact_census(self):
        result = AUDIT.audit(REPO)
        self.assertTrue(result["target"]["bootstrap_sequence_hash_gated"])
        self.assertEqual(result["target"]["gfusb_sha256"], AUDIT.EXPECTED_DLL_SHA256)
        self.assertEqual(result["decisions"]["GATE_0x82_STATUS"], "CLOSED_NATIVE_PREDICATE_IMPLEMENTED")

    def test_nav_parser_and_wrong_response_fail_closed(self):
        self.assertEqual(len(parse_nav_baseline_response(nav_response())), 2409)
        with self.assertRaises(ChecksumMismatch):
            parse_nav_baseline_response(nav_response(marker=0x00))

    def test_native_delta_parser_and_predicate(self):
        self.assertEqual(fdt_delta_threshold(b"\x80\x1d"), 29)
        self.assertTrue(fdt_raw_delta_within_threshold((100, 200), (129, 171), 29))
        self.assertFalse(fdt_raw_delta_within_threshold((100,), (130,), 29))
        with self.assertRaises(LengthMismatch):
            fdt_delta_threshold(b"\x1d")

    def _machine(self, responses, **kwargs):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        transport = ScriptedTransport(responses)
        lifecycle = FdtLifecycle()
        lifecycle.observe_af_state(False)
        machine = ExactFreshFdtBootstrapMachine(transport, lifecycle, **kwargs)
        machine.begin(seed_result(Path(temporary.name)))
        return machine, transport, lifecycle

    def _through_stage2(self, **kwargs):
        responses = (
            [ack(0x36)], [ack(0x50), nav_response()], [ack(0x36)],
            [ack(0x82), delta_response()], [ack(0x20), baseline_b0()], [ack(0x36)],
        )
        machine, transport, lifecycle = self._machine(responses, **kwargs)
        samples = ((348, 382, 327, 356, 333, 357),
                   (347, 381, 328, 356, 334, 358),
                   (346, 380, 327, 356, 333, 357))
        machine.manual_sample(irq100(samples[0]))
        machine.nav_interstage()
        machine.manual_sample(irq100(samples[1]))
        machine.delta_and_baseline_interstage()
        machine.manual_sample(irq100(samples[2]))
        return machine, transport, lifecycle

    def test_store_then_post_sample_order_and_missing_gate_fail_closed(self):
        machine, _transport, lifecycle = self._through_stage2()
        self.assertIsNotNone(machine.nav_dynamic_state)
        self.assertIsNotNone(machine.baseline_b0)
        self.assertTrue(machine.delta_gate_passed)
        with self.assertRaisesRegex(InvalidTransition, "nav_post_sample_classifier_unavailable"):
            machine.finalize_host_base_decisions()
        self.assertEqual(lifecycle.state.value, "FAILED_CLOSED")

    def test_wrong_delta_rejects_before_baseline(self):
        responses = (
            [ack(0x36)], [ack(0x50), nav_response()], [ack(0x36)],
            [ack(0x82), delta_response(b"\x80\x00")],
        )
        machine, transport, lifecycle = self._machine(responses)
        machine.manual_sample(irq100((100, 100, 100, 100, 100, 100)))
        machine.nav_interstage()
        machine.manual_sample(irq100((101, 100, 100, 100, 100, 100)))
        with self.assertRaises(UnexpectedEvent):
            machine.delta_and_baseline_interstage()
        self.assertEqual(len(transport.requests), 4)
        self.assertEqual(lifecycle.state.value, "FAILED_CLOSED")

    def test_invalid_baseline_envelope_fails_closed(self):
        responses = (
            [ack(0x36)], [ack(0x50), nav_response()], [ack(0x36)],
            [ack(0x82), delta_response()], [ack(0x20), baseline_b0(7725)],
        )
        machine, _transport, lifecycle = self._machine(responses)
        sample = irq100((100, 100, 100, 100, 100, 100))
        machine.manual_sample(sample)
        machine.nav_interstage()
        machine.manual_sample(sample)
        with self.assertRaises(LengthMismatch):
            machine.delta_and_baseline_interstage()
        self.assertEqual(lifecycle.state.value, "FAILED_CLOSED")

    def test_classifier_and_decryption_failure_are_fail_closed(self):
        machine, _transport, lifecycle = self._through_stage2(
            nav_semantic_gate=lambda _data: True,
            decrypt_baseline_b0=lambda _frame: (_ for _ in ()).throw(ValueError("decrypt")),
            baseline_semantic_gate=lambda _pixels: True,
        )
        with self.assertRaises(ValueError):
            machine.finalize_host_base_decisions()
        self.assertEqual(lifecycle.state.value, "FAILED_CLOSED")

    def test_second_native_delta_rejects_after_stage2(self):
        machine, _transport, lifecycle = self._through_stage2(
            nav_semantic_gate=lambda _data: True,
            decrypt_baseline_b0=lambda _frame: image_payload(),
            baseline_semantic_gate=lambda _pixels: True,
        )
        machine.raw_fdt_samples[2] = tuple(value + 30 for value in machine.raw_fdt_samples[1])
        with self.assertRaisesRegex(UnexpectedEvent, "second_fdt_delta_threshold_rejected"):
            machine.finalize_host_base_decisions()
        self.assertEqual(lifecycle.state.value, "FAILED_CLOSED")

    def test_per_command_timeouts_and_success_fixture(self):
        expected_pixels = tuple((index * 17 + index // 80) & 0xFFF for index in range(5120))
        machine, transport, lifecycle = self._through_stage2(
            nav_semantic_gate=lambda data: len(data) == 2409,
            decrypt_baseline_b0=lambda _frame: image_payload(),
            baseline_semantic_gate=lambda pixels: pixels == expected_pixels,
        )
        machine.finalize_host_base_decisions()
        transport.responses.append([ack(0x32)])
        machine.arm(0x1234)
        self.assertEqual(COMMAND_TIMEOUT_POLICY, "PER_COMMAND_EVIDENCE_BOUNDED")
        self.assertTrue(machine.second_delta_gate_passed)
        self.assertEqual(transport.timeouts, [500, 500, 500, 500, 2000, 500, 100])
        self.assertEqual(lifecycle.retry_count, 0)

    def test_no_recovery_persistence_or_target_dynamic_blob_literal(self):
        self.assertFalse(SAFE_DEVICE_COMMANDS & SPECIAL_RECOVERY_COMMANDS)
        self.assertFalse(SAFE_DEVICE_COMMANDS & PERSISTENT_COMMAND_FAMILIES)
        source = (REPO / "core/fdt_lifecycle.py").read_bytes()
        _run, _wire, frames, _otp, _cache = REPLAY.d257_replay._load_d255(REPO)
        dynamic = next(frame.raw for frame in frames
                       if frame.direction == "IN" and len(frame.raw) == 2417)
        self.assertNotIn(dynamic, source)
        self.assertNotIn(hashlib.sha256(dynamic).hexdigest().encode(), source)

    def test_projected_and_exact_replays_remain_distinct(self):
        result = REPLAY.run(REPO)
        self.assertEqual(result["closure"]["PROJECTED_FDT_SUBSEQUENCE_REPLAY"], "PASS_HISTORICAL")
        self.assertEqual(result["closure"]["EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY"], "BLOCKED")
        self.assertEqual(result["safety"]["REAL_USB_OPEN_COUNT"], 0)


if __name__ == "__main__":
    unittest.main()
