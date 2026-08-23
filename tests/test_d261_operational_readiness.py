# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline-only executable closure for the D261 operational candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from analysis.D261.d261_offline_rehearsal import (
    NEGATIVE_SCENARIOS,
    REPO,
    SEALED_HASHES,
    run_scenario,
)
from core.protected_runtime import (
    D261_LIVE_AUTHORIZATION_FLAG,
    ProtectedRuntimeFailure,
    issue_live_authorization_after_marker,
)
from core.runtime_transport import PhysicalSubmissionPolicy, SubmissionMode, operational_fdt_a0_policy
from core.usb_runtime import CtypesLibusbBackend, LibusbRuntimeTransport, UsbIdentity
from tools.d261_live_fdt_arm_once import (
    LIVE_CRITICAL_PATHS,
    dry_run,
    load_fileset,
    verify_approved_git_baseline,
    OperationalFailure,
)


def _json(relative: str) -> dict:
    return json.loads((REPO / relative).read_text(encoding="utf-8"))


class D261OperationalReadinessTests(unittest.TestCase):
    def test_real_adapter_applies_pre_and_per_chunk_post_pacing(self) -> None:
        class Backend:
            open_count = claim_count = release_count = close_count = 0

            def open_exact(self, vid: int, pid: int, interface: int) -> UsbIdentity:
                self.open_count = self.claim_count = 1
                return UsbIdentity(vid, pid, 1, 2, (3,))

            def revalidate_identity(self) -> UsbIdentity:
                return UsbIdentity(0x27C6, 0x5125, 1, 2, (3,))

            def bulk_out(self, endpoint: int, data: bytes, timeout_ms: int) -> int:
                return len(data)

            def bulk_in(self, endpoint: int, maximum: int, timeout_ms: int) -> bytes:
                raise AssertionError("no IN expected")

            def close(self) -> None:
                self.release_count = self.close_count = 1

        sleeps: list[float] = []
        transport = LibusbRuntimeTransport(Backend(), sleeper=sleeps.append)
        transport.open()
        transport.submit(bytes(70), PhysicalSubmissionPolicy(
            "pacing", SubmissionMode.FIXED64_ZERO_TAIL, timeout_ms=100,
            pre_submit_pacing_ms=20, post_submit_pacing_ms=10,
        ))
        transport.close()
        self.assertEqual(sleeps, [0.02, 0.01, 0.01])

    def test_per_command_physical_tail_decision_is_exact(self) -> None:
        decision = _json("analysis/D261/D261_physical_policy_decision.json")
        self.assertEqual(decision["FDT_A0_PHYSICAL_LENGTH"], 64)
        self.assertEqual(decision["FDT_A0_TAIL_POLICY"], "ZERO_FILL_OUTSIDE_DECLARED_LOGICAL_FRAME")
        self.assertFalse(decision["FDT_A0_RESIDUE_REPLAY"])
        for control in (0x36, 0x50, 0x82, 0x20, 0x32):
            logical = bytes(range({0x36: 22, 0x50: 10, 0x82: 13, 0x20: 10, 0x32: 24}[control]))
            policy = operational_fdt_a0_policy(control, 100)
            physical = policy.materialize(logical)
            self.assertEqual(policy.mode, SubmissionMode.FIXED64_ZERO_TAIL)
            self.assertEqual(len(physical), 1)
            self.assertEqual(len(physical[0]), 64)
            self.assertEqual(physical[0][:len(logical)], logical)
            self.assertFalse(any(physical[0][len(logical):]))

    def test_tail_audit_preserves_evidence_boundary(self) -> None:
        audit = _json("analysis/D261/D261_fdt_physical_tail_audit.json")
        self.assertEqual(audit["exact_trace"], ["0x36", "0x50", "0x36", "0x82", "0x20", "0x36", "0x32"])
        self.assertEqual(audit["cross_command_common_nonzero_offsets_physical_zero_based"], [40, 41, 42, 43, 44, 45])
        self.assertTrue(audit["per_command"]["0x32"]["primary_zero_tail_proof"])
        for control in ("0x36", "0x50", "0x82", "0x20"):
            self.assertFalse(audit["per_command"][control]["primary_zero_tail_proof"])
            self.assertEqual(audit["per_command"][control]["device_acceptance_status"], "UNPROVEN_LIVE_HYPOTHESIS")

    def test_full_fake_runtime_reaches_only_fdt_arm_ack(self) -> None:
        result = run_scenario(REPO, "happy")
        self.assertTrue(result["passed"])
        self.assertEqual(result["result"]["stop_boundary"], "STOP_AFTER_FDT_ARM_ACK")
        self.assertEqual(result["audit"]["cold_start_command_trace"], [
            "0xa8", "0xe4", "0xa2", "0x82", "0xa6", "0xa2", "0x70",
            "0x80", "0x80", "0x80", "0x80", "0x90",
        ])
        self.assertEqual(result["audit"]["exact_fdt_command_trace"], [
            "0x36", "0x50", "0x36", "0x82", "0x20", "0x36", "0x32",
        ])
        self.assertEqual(result["audit"]["retry_count"], 0)
        self.assertEqual(result["audit"]["persistent_device_write_count"], 0)
        self.assertEqual(result["usb"]["open_count"], 1)
        self.assertEqual(result["usb"]["release_count"], 1)
        self.assertEqual(result["usb"]["close_count"], 1)
        self.assertEqual(result["usb"]["queued_frame_count_at_end"], 0)

    def test_runtime_negatives_abort_without_retry(self) -> None:
        for scenario in (
            "wrong_vid_pid",
            "identity_changes_after_open",
            "interface_claim_failure",
            "live_otp_cache_mismatch",
            "e4_mismatch",
            "unexpected_extra_frame_after_final_0x32",
        ):
            with self.subTest(scenario=scenario):
                result = run_scenario(REPO, scenario)
                self.assertFalse(result["passed"])
                self.assertEqual(result["audit"]["retry_count"], 0)
                self.assertEqual(result["audit"]["persistent_device_write_count"], 0)

    def test_declared_negative_matrix_is_complete_and_contained(self) -> None:
        matrix = _json("analysis/D261/D261_failure_containment_matrix.json")
        self.assertEqual(matrix["status"], "PASS")
        rows = {row["scenario"]: row for row in matrix["rows"]}
        self.assertEqual(set(rows), set(NEGATIVE_SCENARIOS))
        for row in rows.values():
            self.assertTrue(row["contained"])
            self.assertTrue(row["NO_AUTOMATIC_RETRY"])
            self.assertEqual(row["persistent_write_count"], 0)
            self.assertEqual(row["cache_write_count"], 0)

    def test_concrete_usb_backend_is_sealed_without_capability(self) -> None:
        backend = CtypesLibusbBackend()
        with self.assertRaisesRegex(ProtectedRuntimeFailure, "live_resource_open_not_authorized"):
            backend.open_exact(0x27C6, 0x5125, 0)
        self.assertIsNone(backend._lib)
        self.assertEqual(backend.open_count, 0)

    def test_live_authorization_requires_flag_and_marker(self) -> None:
        with self.assertRaisesRegex(ProtectedRuntimeFailure, "explicit_live_authorization_required"):
            issue_live_authorization_after_marker("wrong", marker_claimed=True)
        with self.assertRaisesRegex(ProtectedRuntimeFailure, "single_use_marker_required"):
            issue_live_authorization_after_marker(D261_LIVE_AUTHORIZATION_FLAG, marker_claimed=False)

    def test_default_entrypoint_is_hard_disabled_and_cwd_independent(self) -> None:
        tool = REPO / "tools/d261_live_fdt_arm_once.py"
        with tempfile.TemporaryDirectory(prefix="d261-cwd-") as directory:
            completed = subprocess.run(
                (sys.executable, str(tool)), cwd=directory, check=False,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
        self.assertEqual(completed.returncode, 2)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "HARD_DISABLED_DEFAULT")
        self.assertEqual(report["LIVE_CAPABILITY_DEFAULT"], 0)
        self.assertFalse(report["LIVE_PATH_REACHABLE_WITHOUT_EXPLICIT_FLAG"])

    def test_preflight_dry_run_is_side_effect_free(self) -> None:
        report = dry_run(REPO)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["D261_operational_worktree_mismatches"], [])
        for key in (
            "REAL_USB_OPEN_COUNT", "REAL_SECRET_READ_COUNT",
            "REAL_SINGLE_USE_MARKER_CREATE_COUNT", "FPRINTD_MUTATION_COUNT",
        ):
            self.assertEqual(report[key], 0)

    def test_fileset_cannot_omit_hardcoded_live_critical_paths(self) -> None:
        fileset = load_fileset()
        self.assertEqual(tuple(row["path"] for row in fileset["files"]), LIVE_CRITICAL_PATHS)
        self.assertEqual(fileset["approval_status"], "PENDING_USER_AI_PM_REVIEW")
        with self.assertRaises(OperationalFailure):
            verify_approved_git_baseline(REPO, "0" * 40, fileset)

    def test_sealed_historical_artifacts_are_byte_identical(self) -> None:
        for relative, expected in SEALED_HASHES.items():
            with self.subTest(path=relative):
                actual = hashlib.sha256((REPO / relative).read_bytes()).hexdigest()
                self.assertEqual(actual, expected)

    def test_rehearsal_asserts_zero_real_side_effects(self) -> None:
        report = _json("analysis/D261/D261_full_offline_operational_rehearsal.json")
        self.assertEqual(report["status"], "PASS")
        for key in (
            "REAL_USB_OPEN_COUNT", "REAL_SECRET_READ_COUNT", "REAL_TLS_TARGET_HANDSHAKE_COUNT",
            "REAL_COMMAND_SEND_COUNT", "FPRINTD_MUTATION_COUNT", "REAL_SINGLE_USE_MARKER_CREATE_COUNT",
        ):
            self.assertEqual(report[key], 0)


if __name__ == "__main__":
    unittest.main()
