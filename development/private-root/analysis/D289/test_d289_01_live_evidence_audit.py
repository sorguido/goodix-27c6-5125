# SPDX-License-Identifier: GPL-2.0-or-later
import importlib.util
import unittest
from pathlib import Path


AUDITOR = Path(__file__).with_name("d289_01_live_evidence_audit.py")
SPEC = importlib.util.spec_from_file_location("d289_01_live_evidence_audit", AUDITOR)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class D289LiveEvidenceAuditTests(unittest.TestCase):
    def test_hash_pinned_capture_passes(self):
        result = MODULE.audit()
        self.assertEqual(result["result"], "PASS_MATCH")
        self.assertEqual(result["real_kde_locked_session_unlock"], "PROVEN")
        self.assertEqual(result["action_attempt_count"], 1)
        self.assertEqual(result["contact_count"], 1)
        self.assertEqual(result["retry_count"], 0)
        self.assertFalse(result["rerun_required"])


if __name__ == "__main__":
    unittest.main()
