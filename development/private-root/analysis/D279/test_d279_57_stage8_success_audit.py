#!/usr/bin/env python3

import json
import subprocess
import sys
import unittest
from pathlib import Path

from analysis.D279 import d279_57_stage8_success_audit as audit_module


ROOT = Path(__file__).resolve().parents[2]


class Stage8SuccessAuditTest(unittest.TestCase):
    def test_canonical_evidence_passes(self) -> None:
        result = audit_module.audit()
        self.assertEqual(result["result"], "PASS_STAGE8_EARLY_TERMINAL")
        self.assertEqual(result["production_path"]["completed_stage_count"], 8)
        self.assertEqual(result["production_path"]["inter_stage_rearm_count"], 7)
        self.assertEqual(result["production_path"]["command_32_count"], 8)
        self.assertFalse(result["non_claims"]["post_close_reusability_proven"])

    def test_cli_is_deterministic_and_matches_api(self) -> None:
        command = [sys.executable, str(Path(audit_module.__file__))]
        first = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
        second = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(json.loads(first.stdout), audit_module.audit())


if __name__ == "__main__":
    unittest.main()
