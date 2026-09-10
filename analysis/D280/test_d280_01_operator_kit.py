#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Hardware-free structural checks for the D280/01 operator boundary."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/d280_ephemeral_template_reuse.c"
RUNNER = ROOT / "operator_kit/d280-01-ephemeral-template-reuse/run-d280-01.sh"
README = ROOT / "operator_kit/d280-01-ephemeral-template-reuse/README_IT.md"


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

    def test_runner_consumes_grant_and_never_exports_template(self) -> None:
        consume = self.runner.index('mkdir -m 0700 "$claim"')
        execute = self.runner.index('"$runtime/d280_ephemeral_template_reuse" --run-once')
        self.assertLess(consume, execute)
        export = self.runner.index("export_results ()")
        self.assertIn("BIOMETRIC_TEMPLATE_STILL_PRESENT", self.runner[export:])
        self.assertIn("for name in operator.log summary.env", self.runner[export:])
        self.assertIn("TEMPLATE_FILE_PRESENT_AFTER_RUN=$template_present_after_run",
                      self.runner)
        self.assertIn("RUNTIME_ARTIFACT_BUNDLE_HASH_MISMATCH", self.runner)

    def test_documented_residual_storage_risk_and_human_gate(self) -> None:
        readme = README.read_text(encoding="utf-8")
        normalized = " ".join(readme.split())
        self.assertIn("non garantisce la cancellazione fisica", normalized)
        self.assertIn("Human Gate", normalized)
        self.assertIn("non autorizza la run", normalized)
        self.assertIn("non avvia questo percorso live", normalized)


if __name__ == "__main__":
    unittest.main()
