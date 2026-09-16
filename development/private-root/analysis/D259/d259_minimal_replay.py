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
from core.post_d4 import TLS, parse_outer
from core.tls_b0 import B0ApplicationConsumer, TLS_CIPHER_NAME, TLS_IDENTITY, Tls12PskServerSession


D245_LIVE_TLS = Path("analysis/D245/D245_operator_live_stdout.json")
SYNTHETIC_SECRET = bytes(range(1, 33))
SYNTHETIC_PLAINTEXT_BYTES = 7693
TARGET_B0_OUTER_BYTES = 7726
SEALED_RUNTIME = Path("src/goodix5125_d233_backend.py")
SEALED_RUNTIME_SHA256 = "e537f33d47d49d47b0fc451c80b08fbafdc185e884d519cb603e22baf458c982"
SEALED_ENTRYPOINT = Path("src/goodix5125_d235_entrypoint.py")
SEALED_ENTRYPOINT_SHA256 = "d87b11d0f2de608f05c232fa83d4e03ce4d248fe37839808f42f6ea577143b69"
LIVE_LAUNCHERS = {
    "operator_kit/d245-live-tls-once.sh": "77e19d158c252021a51be28b0292c54d95660db5016443af0a944b6145013ea0",
    "operator_kit/d246-live-d4-once.sh": "e86bc07fdfacb282e37ff065e52cc7250ee8cb29d7bfd6e821a8ed6d1f666c48",
    "operator_kit/d251-live-af-once.sh": "e33baf629221f4aa55a73c7feae6f26e0e1084cdc2d26df63bb362b571307280",
}


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


def _application_b0(client, client_out, plaintext: bytes) -> bytes:
    require(client.write(plaintext) == len(plaintext), "synthetic TLS short write")
    tls_record = client_out.read()
    require(tls_record[:1] == b"\x17", "synthetic TLS application record missing")
    size = len(tls_record)
    return bytes((TLS, size & 0xFF, size >> 8, (TLS + (size & 0xFF) + (size >> 8)) & 0xFF)) + tls_record


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

    b0 = _application_b0(client, client_out, bytes(SYNTHETIC_PLAINTEXT_BYTES))
    require(len(b0) == TARGET_B0_OUTER_BYTES, "synthetic B0 target shape changed")
    return server, client, client_out, b0


def runtime_adapter_evidence(repo: Path) -> dict[str, object]:
    runtime = repo / SEALED_RUNTIME
    entrypoint = repo / SEALED_ENTRYPOINT
    require(sha256_file(runtime) == SEALED_RUNTIME_SHA256, "sealed runtime changed")
    require(sha256_file(entrypoint) == SEALED_ENTRYPOINT_SHA256, "sealed entrypoint changed")
    for relative, expected in LIVE_LAUNCHERS.items():
        require(sha256_file(repo / relative) == expected, f"live launcher changed: {relative}")
    source = runtime.read_text(encoding="utf-8")
    local_create = "engine = self.tls_factory(secret)" in source
    unconditional_close = "            engine.close()" in source
    retained_member = "self._tls_engine = engine" in source or "self.tls_engine = engine" in source
    require(local_create and unconditional_close and not retained_member,
            "sealed TLS lifetime evidence changed")
    return {
        "schema": "D259_TLS_RUNTIME_ADAPTER_EVIDENCE_V2",
        "execution_mode": "OFFLINE_ONLY",
        "LIVE_TLS_ROLE": "SERVER",
        "SEALED_RUNTIME_TLS_ENGINE": "Tls12PskServer_OVER_SSLObject_MemoryBIO",
        "SEALED_RUNTIME_CREATES_ENGINE_AS_LOCAL": local_create,
        "SEALED_RUNTIME_CLOSES_ENGINE_IN_TLS_HANDSHAKE_FINALLY": unconditional_close,
        "SEALED_RUNTIME_RETAINS_POST_HANDSHAKE_ENGINE": retained_member,
        "CORE_ADAPTER_ACCEPTS_ESTABLISHED_SSL_OBJECT_AND_INPUT_BIO": True,
        "CORE_ADAPTER_CREATES_SECOND_SSL_CONTEXT": False,
        "CORE_ADAPTER_CREATES_SECOND_SSL_OBJECT": False,
        "CORE_ADAPTER_PROVISIONS_PSK": False,
        "LIVE_TLS_TO_B0_ADAPTER_STATUS": "UNIMPLEMENTED",
        "BLOCKER": "SEALED_D245_RUNTIME_CLOSES_AND_DOES_NOT_EXPOSE_THE_HANDSHAKED_ENGINE",
        "SRC_SEALED_UNCHANGED": True,
        "LIVE_LAUNCHERS_UNCHANGED": True,
        "sealed_hashes": {
            str(SEALED_RUNTIME): sha256_file(runtime),
            str(SEALED_ENTRYPOINT): sha256_file(entrypoint),
            **{relative: sha256_file(repo / relative) for relative in LIVE_LAUNCHERS},
        },
    }


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
    server, client, client_out, synthetic_b0 = synthetic_active_tls_and_b0()
    application_session = server.application_session
    require(application_session.uses_ssl_object(server._ssl), "adapter did not retain same SSLObject")
    consumer = B0ApplicationConsumer(application_session)
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
        machine.delta_and_baseline_interstage(consumer)
        require(consumer.consumption_count == 1, "B0 was not consumed immediately after 0x20")
        require(machine.manual_stage == 2, "B0 consumption occurred after stage2")
        continuity_b0 = _application_b0(client, client_out, b"post-b0-sequence-continuity")
        _kind, continuity_record = parse_outer(continuity_b0)
        continuity_plaintext = application_session.consume_application_record(continuity_record)
        require(bytes(continuity_plaintext) == b"post-b0-sequence-continuity",
                "post-B0 same-session continuity plaintext mismatch")
        for index in range(len(continuity_plaintext)):
            continuity_plaintext[index] = 0
        continuity_zeroized = not any(continuity_plaintext)
        machine.manual_sample(manual_events[2].raw[4:])
        machine.finalize_minimal_device_contract()
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
    adapter = runtime_adapter_evidence(repo)
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
            "b0_consumed_before_stage2": machine.baseline_b0_consumed_at_manual_stage == 2,
            "plaintext_mutable_buffer_best_effort_zeroized": consumer.consumption_count == 1,
            "openssl_internal_copy_zeroization": "NOT_PROVEN",
            "python_immutable_temp_copy_zeroization": "NOT_PROVEN",
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
            "LIVE_TLS_ROLE": "SERVER",
            "LIVE_TLS_TO_B0_ADAPTER_STATUS": adapter["LIVE_TLS_TO_B0_ADAPTER_STATUS"],
            "TLS_SERVER_SESSION_OBJECT_COUNT": server.server_session_object_count,
            "TLS_CLIENT_SESSION_OBJECT_COUNT": 1,
            "TLS_SERVER_HANDSHAKE_COUNT": server.handshake_count,
            "TLS_APPLICATION_RECORD_CONSUMPTION_COUNT": consumer.consumption_count,
            "SECOND_SERVER_SESSION_CREATED": False,
            "SECOND_PSK_PROVISIONING": server.psk_context_provisioning_count != 1,
            "SAME_TLS_SESSION_B0_CONSUMPTION": "PASS_OFFLINE_ARCHITECTURAL",
            "POST_B0_TLS_SESSION_CONTINUITY": (
                "PASS_OFFLINE_ARCHITECTURAL" if continuity_zeroized else "FAIL"
            ),
            "PLAINTEXT_MUTABLE_BUFFER_BEST_EFFORT_ZEROIZED": True,
            "OPENSSL_INTERNAL_COPY_ZEROIZATION": "NOT_PROVEN",
            "PYTHON_IMMUTABLE_TEMP_COPY_ZEROIZATION": "NOT_PROVEN",
            "FUTURE_LINUX_RUNTIME_B0_CONSUMPTION_CAPABILITY": False,
            "B0_CONSUMPTION_CAPABILITY_EVIDENCE": "SAME_SYNTHETIC_SSLObject_HANDSHAKE_TO_TWO_APPLICATION_RECORDS",
        },
        "runtime_adapter_evidence": adapter,
        "closure": {
            **decisions,
            "B0_CONSUMED_BEFORE_STAGE2": machine.baseline_b0_consumed_at_manual_stage == 2,
            "SRC_SEALED_UNCHANGED": adapter["SRC_SEALED_UNCHANGED"],
            "LIVE_LAUNCHERS_UNCHANGED": adapter["LIVE_LAUNCHERS_UNCHANGED"],
            "FDT_OFFLINE_CANDIDATE_CLOSED": False,
            "MINIMAL_DEVICE_LIVE_CONTRACT_CLOSED": False,
            "FACTORY_PRESERVING_MINIMAL_CANDIDATE_CLOSED": False,
            "READY_FOR_FDT_LIVE_REVIEW": False,
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
    adapter_output = output.parent / "D259_tls_runtime_adapter_evidence.json"
    adapter_output.write_text(
        json.dumps(result["runtime_adapter_evidence"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    same_session = {
        "schema": "D259_SAME_SESSION_TLS_TEST_RESULT_V2",
        "execution_mode": "OFFLINE_ONLY",
        **result["tls_closure"],
        "B0_CONSUMED_BEFORE_STAGE2": result["closure"]["B0_CONSUMED_BEFORE_STAGE2"],
    }
    (output.parent / "D259_same_session_tls_test_result.json").write_text(
        json.dumps(same_session, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
