# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import unittest

from goodix_orchestrator.qualification import (
    _report_base,
    _review_disposition_hint_count,
    _review_prompt,
)


class QualificationContractTests(unittest.TestCase):
    def test_real_review_prompt_is_disposition_neutral(self) -> None:
        prompt = _review_prompt(
            {"measured_test": {"status": "FAIL"}},
            phase="DRILL-1A",
            next_task_id=None,
        )
        self.assertEqual(_review_disposition_hint_count(prompt), 0)
        self.assertIn('"phase_id":"DRILL-1A"', prompt)
        self.assertIn('"continuation_task_id":null', prompt)
        self.assertNotIn("should produce CORRECTIVE", prompt)
        self.assertNotIn("If all measured criteria pass", prompt)

    def test_negative_counters_are_classified_as_path_observations(self) -> None:
        report = _report_base()
        self.assertFalse(report["OS_NEGATIVE_CAPABILITY_ISOLATION_PROVEN"])
        self.assertEqual(
            report["NEGATIVE_CAPABILITY_EVIDENCE_CLASS"],
            "QUALIFICATION_PATH_NOT_OS_PROOF",
        )
        self.assertEqual(report["UNSANDBOXED_TASK_CODE_EXECUTION_COUNT"], 0)


if __name__ == "__main__":
    unittest.main()
