#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Replay the D259 minimal device contract with D255 wire facts by reference."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import ssl
import sys


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("repository root not found")


REPO = find_repo_root(Path(__file__))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from analysis.D257 import d257_exact_bootstrap_audit as d257_audit
from analysis.D257 import d257_offline_replay as d257_replay
from analysis.D259 import d259_post_classifier_audit
from core.fdt_lifecycle import (
    COMMAND_TIMEOUT_MS,
    EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE,
    ExactFreshFdtBootstrapMachine,
    FdtLifecycle,
)
from core.fdt_seed import provide_fdt12
from core.post_d4 import TLS
from core.tls_b0 import B0ApplicationConsumer, TLS_CIPHER_NAME, TLS_IDENTITY, Tls12PskServerSession


D245_LIVE_TLS = Path("analysis/D245/D245_operator_live_stdout.json")
SYNTHETIC_SECRET = bytes(range(1, 33))
SYNTHETIC_PLAINTEXT_BYTES = 7693
TARGET_B0_OUTER_BYTES = 7726


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ScriptedTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[bytes] = []
        self.timeouts: list[int | None] = []

    def exchange(self, request: bytes, *, timeout_ms: int | None = None):
        self.requests.append(request)
        self.timeouts.append(timeout_ms)
        require(bool(self.responses), "unexpected offline exchange")
        return self.responses.pop(0)


def _client():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers(TLS_CIPHER_NAME)
    context.options |= ssl.OP_NO_TICKET
    context.set_psk_client_callback(lambda _hint: (TLS_IDENTITY, SYNTHETIC_SECRET))
    incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
    tls = context.wrap_bio(incoming, outgoing, server_side=False)
    return tls, incoming, outgoing


def synthetic_active_tls_and_b0():
    server = Tls12PskServerSession(SYNTHETIC_SECRET)
    client, client_in, client_out = _client()
    client_done = False
    for _ in range(100):
        try:
            client.do_handshake()
            client_done = True
        except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
            pass
        outgoing = client_out.read()
        if outgoing:
            server.feed_handshake_bytes(outgoing)
            server.advance_handshake()
        for record in server.drain_encrypted_output():
            client_in.write(record)
        if client_done and server.handshake_complete:
            break
    else:
        server.close()
        raise RuntimeError("synthetic TLS handshake did not converge")

    plaintext = bytes(SYNTHETIC_PLAINTEXT_BYTES)
    require(client.write(plaintext) == len(plaintext), "synthetic TLS short write")
    tls_record = client_out.read()
    require(tls_record[:1] == b"\x17", "synthetic TLS application record missing")
    size = len(tls_record)
    b0 = bytes((TLS, size & 0xFF, size >> 8, (TLS + (size & 0xFF) + (size >> 8)) & 0xFF)) + tls_record
    require(len(b0) == TARGET_B0_OUTER_BYTES, "synthetic B0 target shape changed")
    return server, b0


def run(repo: Path) -> dict[str, object]:
    static = d259_post_classifier_audit.audit(repo)
    exact = d257_audit.audit(repo)
    _run, wire, target_frames, otp, cache = d257_replay._load_d255(repo)
    by_frame = {frame.packet_index + 1: frame for frame in target_frames}
    rows = exact["timeline"]["rows"]

    def frames_for(prefix: str):
        return [by_frame[int(row["frame"])] for row in rows
                if str(row["event_class"]).startswith(prefix)]

    manual_requests = frames_for("FDT36_STAGE_")
    manual_acks = frames_for("ACK_0x36_STATUS_01")
    manual_events = frames_for("IRQ_0x0100_TOUCH_0")
    nav_request = frames_for("INTERSTAGE_NAV_0x50_REQUEST")[0]
    nav_ack = frames_for("ACK_0x50_STATUS_01")[0]
    nav_response = frames_for("INTERSTAGE_NAV_0x50_RESPONSE")[0]
    delta_request = frames_for("INTERSTAGE_FDT_DELTA_0x82_REQUEST")[0]
    delta_ack = frames_for("ACK_0x82_STATUS_01")[0]
    delta_response = frames_for("INTERSTAGE_FDT_DELTA_0x82_RESPONSE")[0]
    image_request = frames_for("INTERSTAGE_BASELINE_IMAGE_0x20_REQUEST")[0]
    image_ack = frames_for("ACK_0x20_STATUS_01")[0]
    target_b0 = frames_for("INTERSTAGE_BASELINE_IMAGE_B0_RESPONSE")[0]
    final_request = frames_for("FIRST_POST_BOOTSTRAP_FDT32_REQUEST")[0]
    final_ack = frames_for("ACK_0x32_STATUS_01")[0]
    require(len(manual_requests) == len(manual_acks) == len(manual_events) == 3,
            "D255 exact manual census changed")
    require(len(target_b0.raw) == TARGET_B0_OUTER_BYTES, "D255 target B0 shape changed")

    target_final_parsed = d257_replay.d255.parse_a0(final_request)
    require(target_final_parsed is not None and target_final_parsed[0] == 0x32,
            "D255 final 0x32 parse failed")
    ts16 = int.from_bytes(target_final_parsed[1][-2:], "little")

    cache_hash_before = sha256_file(cache.path)
    cache_mtime_before = cache.path.stat().st_mtime_ns
    provider = provide_fdt12(cache.path, otp)
    require(provider.ok, "D255 seed provider failed")
    server, synthetic_b0 = synthetic_active_tls_and_b0()
    consumer = B0ApplicationConsumer(server)
    transport = ScriptedTransport((
        [manual_acks[0].raw],
        [nav_ack.raw, nav_response.raw],
        [manual_acks[1].raw],
        [delta_ack.raw, delta_response.raw],
        [image_ack.raw, synthetic_b0],
        [manual_acks[2].raw],
        [final_ack.raw],
    ))
    lifecycle = FdtLifecycle()
    lifecycle.observe_af_state(False)
    machine = ExactFreshFdtBootstrapMachine(transport, lifecycle)
    try:
        machine.begin(provider)
        machine.manual_sample(manual_events[0].raw[4:])
        machine.nav_interstage()
        machine.manual_sample(manual_events[1].raw[4:])
        machine.delta_and_baseline_interstage()
        machine.manual_sample(manual_events[2].raw[4:])
        machine.finalize_minimal_device_contract(consumer)
        machine.arm(ts16)
    finally:
        server.close()

    expected_requests = [
        manual_requests[0].raw, nav_request.raw, manual_requests[1].raw,
        delta_request.raw, image_request.raw, manual_requests[2].raw,
        final_request.raw,
    ]
    require(transport.requests == expected_requests, "D259 requests are not D255 wire-exact")
    require(not transport.responses, "unused D259 replay responses")
    require(tuple(lifecycle.device_command_trace) == EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE,
            "D259 command trace changed")
    require(cache_hash_before == sha256_file(cache.path), "D255 cache content changed")
    require(cache_mtime_before == cache.path.stat().st_mtime_ns, "D255 cache mtime changed")

    d245 = json.loads((repo / D245_LIVE_TLS).read_text(encoding="utf-8"))
    runtime_tls_proven = (
        d245.get("execution_mode") == "live_single_shot"
        and d245.get("result") == "pass"
        and d245.get("tls_handshake_completed") is True
        and d245.get("tls_handshake_count") == 1
        and d245.get("same_validated_psk_used_by_tls") is True
    )
    require(runtime_tls_proven, "D245 live TLS session evidence gate failed")
    decisions = static["decisions"]
    return {
        "schema": "D259_MINIMAL_DEVICE_CONTRACT_REPLAY_V1",
        "execution_mode": "OFFLINE_ONLY",
        "provenance": {
            "d255_capture_sha256": sha256_file(wire.path),
            "d255_cache_sha256": cache_hash_before,
            "d245_live_tls_result_sha256": sha256_file(repo / D245_LIVE_TLS),
            "gfusb_sha256": static["hash_gates"]["gfusb_sha256"],
            "wire_requests_and_non_b0_responses": "PRIVATE_D255_APP12509_CAPTURE_BY_REFERENCE",
            "baseline_b0_fixture": "SYNTHETIC_TLS12_PSK_AES128_GCM_NON_BIOMETRIC_TARGET_SHAPE",
            "historical_d255_b0_plaintext_available": False,
            "historical_d255_b0_ciphertext_decrypted": False,
            "raw_capture_exported": False,
            "raw_cache_exported": False,
            "raw_biometric_exported": False,
            "secret_exported": False,
        },
        "scenario": {
            "status": "PASS_MINIMAL_DEVICE_CONTRACT",
            "target_command_trace": [f"0x{value:02x}" for value in EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE],
            "requests_wire_exact_except_synthetic_b0_is_response_only": True,
            "manual_stage_count": machine.manual_stage,
            "first_0x36_attempt_count": machine.first_0x36_attempt_count,
            "first_0x32_attempt_count": machine.arm_attempt_count,
            "first_0x32_sent_once": machine.arm_attempt_count == 1,
            "delta_native_predicate_passed": machine.delta_gate_passed,
            "second_delta_native_predicate_passed": machine.second_delta_gate_passed,
            "delta_threshold_unsigned": machine.delta_threshold,
            "baseline_b0_outer_bytes": len(synthetic_b0),
            "baseline_b0_tls_consumed": machine.baseline_b0_tls_consumed,
            "baseline_b0_plaintext_zeroized_and_discarded": consumer.consumption_count == 1,
            "semantic_classifier_call_count": machine.semantic_classifier_call_count,
            "raster_decode_count": machine.raster_decode_count,
            "host_cache_write_count": machine.host_cache_write_count,
            "automatic_retry_count": lifecycle.retry_count,
            "persistent_write_family_count": lifecycle.persistent_write_family_count,
            "a2_reentry_injection": lifecycle.device_command_trace.count(0xA2),
            "0x70_reentry_injection": lifecycle.device_command_trace.count(0x70),
            "timeouts_ms": transport.timeouts,
            "expected_timeouts_ms": [COMMAND_TIMEOUT_MS[value] for value in EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE],
            "source_cache_modified": False,
            "synthetic_tls_secret_zeroized": server.secret_zeroized,
            "lifecycle": lifecycle.audit(),
        },
        "tls_closure": {
            "BASELINE_B0_TLS_CONSUMPTION_REQUIRED": True,
            "BASELINE_B0_IMAGE_CLASSIFICATION_REQUIRED": False,
            "BASELINE_B0_RASTER_DECODE_REQUIRED": False,
            "HISTORICAL_D255_B0_PLAINTEXT_AVAILABLE": False,
            "FUTURE_LINUX_RUNTIME_TLS_SESSION_PROVEN": runtime_tls_proven,
            "FUTURE_LINUX_RUNTIME_B0_CONSUMPTION_CAPABILITY": True,
            "B0_CONSUMPTION_CAPABILITY_EVIDENCE": "SYNTHETIC_OPENSSL_TLS12_PSK_POST_HANDSHAKE_APPLICATION_RECORD",
        },
        "closure": {
            **decisions,
            "FDT_OFFLINE_CANDIDATE_CLOSED": True,
            "MINIMAL_DEVICE_LIVE_CONTRACT_CLOSED": True,
            "FACTORY_PRESERVING_MINIMAL_CANDIDATE_CLOSED": True,
            "READY_FOR_FDT_LIVE_REVIEW": True,
            "READY_FOR_FDT_LIVE": False,
        },
        "safety": {
            "REAL_USB_OPEN_COUNT": 0,
            "REAL_CAPTURE_COUNT": 0,
            "REAL_HARDWARE_ACTION_COUNT": 0,
            "REAL_COMMAND_SEND_COUNT": 0,
            "REAL_FINGER_INTERACTION_COUNT": 0,
            "PERSISTENT_WRITE_FAMILY_COUNT": 0,
            "HOST_CACHE_WRITE_COUNT": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--output", type=Path, default=Path("analysis/D259/D259_minimal_replay.json"))
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = args.output if args.output.is_absolute() else repo / args.output
    result = run(repo)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
