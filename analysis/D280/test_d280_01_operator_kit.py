#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Hardware-free structural checks for the D280/01 operator boundary."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/d280_ephemeral_template_reuse.c"
RUNNER = ROOT / "operator_kit/d280-01-ephemeral-template-reuse/run-d280-01.sh"
README = ROOT / "operator_kit/d280-01-ephemeral-template-reuse/README_IT.md"
LIVE_AUDIT = ROOT / "analysis/D279/D279_57_STAGE8_SUCCESS_audit.json"


class D28001OperatorKitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = TOOL.read_text(encoding="utf-8")
        self.runner = RUNNER.read_text(encoding="utf-8")

    def test_exact_two_action_surface(self) -> None:
        self.assertEqual(self.tool.count("fp_device_enroll_sync ("), 1)
        self.assertEqual(self.tool.count("fp_device_identify_sync ("), 1)
        self.assertEqual(self.tool.count("fp_print_serialize ("), 1)
        self.assertEqual(self.tool.count("fp_print_deserialize ("), 1)
        for forbidden in (
            "fp_device_verify_sync", "fp_device_capture_sync",
            "fp_device_delete_print_sync", "fp_device_clear_storage_sync",
            "fp_device_list_prints_sync",
        ):
            self.assertNotIn(forbidden, self.tool)
        self.assertIn("ACTION_ATTEMPT_MAX=2", self.tool)
        self.assertIn("OPERATOR_RETRY_COUNT=0", self.tool)

    def test_gate_precedes_context_and_binds_template_path(self) -> None:
        main = self.tool.index("main (int argc")
        gate = self.tool.index("live_gate_valid (&reason)", main)
        run = self.tool.index("return run_once ();", gate)
        self.assertLess(gate, run)
        self.assertEqual(self.tool.count("context = fp_context_new ()"), 1)
        gate_body = self.tool[
            self.tool.index("live_gate_valid (const gchar **reason)"):main
        ]
        self.assertIn("D280_01_TEMPLATE_PATH", gate_body)
        self.assertIn("compiled_baseline_unapproved", gate_body)

    def test_template_is_restricted_and_removed_before_identify(self) -> None:
        create = self.tool.index("O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW")
        write = self.tool.index("persist_template (template_path")
        clear_print = self.tool.index("g_clear_object (&enrolled_print)", write)
        close1 = self.tool.index("fp_device_close_sync", clear_print)
        load = self.tool.index("load_template (template_path", close1)
        unlink = self.tool.index("unlink (template_path)", load)
        identify = self.tool.index("fp_device_identify_sync", unlink)
        self.assertLess(create, write)
        self.assertLess(write, clear_print)
        self.assertLess(clear_print, close1)
        self.assertLess(close1, load)
        self.assertLess(load, unlink)
        self.assertLess(unlink, identify)
        self.assertIn("st.st_uid != 0", self.tool)
        self.assertGreaterEqual(self.tool.count("(st.st_mode & 0777) != 0600"), 2)
        self.assertIn("fstatfs (fd, &filesystem)", self.tool)
        self.assertIn("TMPFS_MAGIC", self.tool)
        self.assertIn('/run/goodix-d280-01/', self.tool)
        self.assertIn("FP3_PARTIAL_WRITE_CLEANUP_REMOVED=false", self.tool)

    def test_second_epoch_requires_first_audit(self) -> None:
        audit = self.tool.index("epoch1_pass = enroll_audit_pass")
        stop = self.tool.index("if (!epoch1_pass || !template_created)", audit)
        open2 = self.tool.index('g_print ("OPEN_ATTEMPT_COUNT=2', stop)
        self.assertLess(audit, stop)
        self.assertLess(stop, open2)
        driver = (ROOT / "libfprint-driver/goodix_fpimage_device.c").read_text(
            encoding="utf-8")
        self.assertIn("GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION",
                      driver)
        self.assertIn("single_acquisition_terminal_count == 1u", self.tool)
        self.assertIn("rearm_0x32_count == 0u", self.tool)

    def test_live_derived_identify_success_uses_stop_not_error_terminal(self) -> None:
        gate_start = self.tool.index("identify_audit_pass (")
        gate_end = self.tool.index("static void\nprint_epoch_audit", gate_start)
        gate = self.tool[gate_start:gate_end]
        self.assertIn("!audit->post_tls.terminal", gate)
        self.assertNotIn("\n         audit->post_tls.terminal &&", gate)
        self.assertIn("audit->post_tls.backend_drained", gate)
        self.assertIn("audit->post_tls.terminal_cleanup_completed", gate)
        for diagnostic in (
            "POST_TLS_ERROR_TERMINAL", "POST_TLS_BACKEND_DRAINED",
            "POST_TLS_CLEANUP_COMPLETED", "SECOND_IMAGE_PIPELINE_COUNT",
            "THIRD_CYCLE_COMMAND_COUNT", "TLS_PROJECT_SECRET_ZEROIZED",
            "RUNTIME_OWNER_FREE_COUNT",
        ):
            self.assertIn(diagnostic, self.tool)

    def test_runner_consumes_grant_and_never_exports_template(self) -> None:
        consume = self.runner.index('mkdir -m 0700 "$claim"')
        execute = self.runner.index('"$runtime/d280_ephemeral_template_reuse" --run-once')
        self.assertLess(consume, execute)
        export = self.runner.index("export_results ()")
        self.assertIn("BIOMETRIC_RAM_STATE_STILL_PRESENT", self.runner[export:])
        self.assertIn("BIOMETRIC_TEMPLATE_STILL_PRESENT", self.runner[export:])
        self.assertIn("for name in operator.log summary.env", self.runner[export:])
        self.assertIn("TEMPLATE_FILE_PRESENT_AFTER_RUN=$template_present_after_run",
                      self.runner)
        self.assertIn(
            "TEMPLATE_RAM_DIRECTORY_PRESENT_AFTER_RUN=$template_directory_present_after_run",
            self.runner,
        )
        self.assertIn("RUNTIME_ARTIFACT_BUNDLE_HASH_MISMATCH", self.runner)

    def test_live_enrollment_tls_contract_matches_d280_gate(self) -> None:
        audit = json.loads(LIVE_AUDIT.read_text(encoding="utf-8"))
        self.assertEqual(audit["production_path"]["tls_handshake_count"], 1)
        self.assertEqual(
            audit["production_path"]["tls_terminal_completion_count"], 0)
        self.assertTrue(audit["safety"]["tls_secret_zeroized"])
        self.assertIn("audit->tls.handshake_count == 1u", self.tool)
        self.assertIn("audit->tls.terminal_completion_count == 0u", self.tool)
        self.assertNotIn("audit->tls.terminal_completion_count == 1u", self.tool)

    def test_runner_requires_ram_only_template_storage(self) -> None:
        self.assertIn("verify_tmpfs_directory /run", self.runner)
        self.assertIn("filesystem == tmpfs", self.runner)
        self.assertIn("/run/goodix-d280-01", self.runner)
        self.assertNotIn(
            "/var/tmp/goodix-d280-01-results/*/template.fp3", self.runner)

    def test_runtime_summary_uses_observed_counters_across_failures(self) -> None:
        scenarios = {
            "before_first_open": (0, 0, 0, 0, 0, 0, 0, 0),
            "during_enroll": (1, 1, 0, 1, 1, 0, 1, 1),
            "epoch1_audit_failed": (1, 1, 0, 1, 1, 0, 1, 1),
            "reopen_not_executed": (1, 1, 0, 1, 1, 0, 1, 1),
            "reopen_no_identify": (1, 1, 0, 2, 2, 1, 2, 2),
            "identify_started_failed": (2, 1, 1, 2, 2, 1, 2, 2),
            "full_pass": (2, 1, 1, 2, 2, 1, 2, 2),
        }
        keys = (
            "ACTION_ATTEMPT_COUNT", "ENROLL_ACTION_ATTEMPT_COUNT",
            "IDENTIFY_ACTION_ATTEMPT_COUNT", "OPEN_ATTEMPT_COUNT",
            "OPEN_SUCCESS_COUNT", "REOPEN_COUNT", "CLOSE_ATTEMPT_COUNT",
            "CLOSE_SUCCESS_COUNT",
        )
        for name, counts in scenarios.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                log = Path(temp) / "operator.log"
                lines = ["D280_01_RUNTIME_COUNTERS_BEGIN=true"]
                lines.extend(
                    f"D280_01_OBSERVED_{key}={value}"
                    for key, value in zip(keys, counts, strict=True)
                )
                lines.append("D280_01_RUNTIME_COUNTERS_END=true")
                log.write_text("\n".join(lines) + "\n", encoding="utf-8")
                completed = subprocess.run(
                    [str(RUNNER), "--summarize-runtime-log", str(log)],
                    check=False, text=True, capture_output=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                summary = dict(
                    line.split("=", 1)
                    for line in completed.stdout.splitlines() if "=" in line
                )
                self.assertEqual(summary["RUNTIME_COUNTERS_COMPLETE"], "true")
                for key, value in zip(keys, counts, strict=True):
                    self.assertEqual(summary[key], str(value))
        self.assertNotIn('echo "REOPEN_COUNT=1"', self.runner)

    def test_runtime_summary_fails_closed_on_missing_counter(self) -> None:
        invalid_blocks = {
            "missing": "D280_01_RUNTIME_COUNTERS_BEGIN=true\n"
                       "D280_01_RUNTIME_COUNTERS_END=true\n",
            "noncanonical_decimal": (
                "D280_01_RUNTIME_COUNTERS_BEGIN=true\n"
                "D280_01_OBSERVED_ACTION_ATTEMPT_COUNT=08\n"
                "D280_01_RUNTIME_COUNTERS_END=true\n"
            ),
            "duplicate": (
                "D280_01_RUNTIME_COUNTERS_BEGIN=true\n"
                "D280_01_OBSERVED_ACTION_ATTEMPT_COUNT=0\n"
                "D280_01_OBSERVED_ACTION_ATTEMPT_COUNT=0\n"
                "D280_01_RUNTIME_COUNTERS_END=true\n"
            ),
            "inconsistent": (
                "D280_01_RUNTIME_COUNTERS_BEGIN=true\n"
                "D280_01_OBSERVED_ACTION_ATTEMPT_COUNT=2\n"
                "D280_01_OBSERVED_ENROLL_ACTION_ATTEMPT_COUNT=0\n"
                "D280_01_OBSERVED_IDENTIFY_ACTION_ATTEMPT_COUNT=0\n"
                "D280_01_OBSERVED_OPEN_ATTEMPT_COUNT=2\n"
                "D280_01_OBSERVED_OPEN_SUCCESS_COUNT=2\n"
                "D280_01_OBSERVED_REOPEN_COUNT=1\n"
                "D280_01_OBSERVED_CLOSE_ATTEMPT_COUNT=2\n"
                "D280_01_OBSERVED_CLOSE_SUCCESS_COUNT=2\n"
                "D280_01_RUNTIME_COUNTERS_END=true\n"
            ),
        }
        for name, block in invalid_blocks.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                log = Path(temp) / "operator.log"
                log.write_text(block, encoding="utf-8")
                completed = subprocess.run(
                    [str(RUNNER), "--summarize-runtime-log", str(log)],
                    check=False, text=True, capture_output=True,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn(
                    "RUNTIME_COUNTERS_COMPLETE=false", completed.stdout)
                self.assertIn("ACTION_ATTEMPT_COUNT=UNKNOWN", completed.stdout)

    def test_documented_residual_storage_risk_and_human_gate(self) -> None:
        readme = README.read_text(encoding="utf-8")
        normalized = " ".join(readme.split())
        self.assertIn("tmpfs", normalized)
        self.assertIn("Human Gate", normalized)
        self.assertIn("non autorizza la run", normalized)
        self.assertIn("non avvia questo percorso live", normalized)


if __name__ == "__main__":
    unittest.main()
