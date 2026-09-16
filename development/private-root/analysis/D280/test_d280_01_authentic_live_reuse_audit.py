#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Regression tests bound to the authentic, hash-pinned D280/01 evidence."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("d280_01_authentic_live_reuse_audit.py")
RESULT = Path(__file__).with_name("D280_01_AUTHENTIC_LIVE_REUSE_audit.json")
SPEC = importlib.util.spec_from_file_location("d280_01_live_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
AUDITOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDITOR)


class D28001AuthenticLiveAuditTests(unittest.TestCase):
    def test_only_old_error_terminal_predicate_failed(self) -> None:
        audit = AUDITOR.build_audit()
        self.assertEqual(
            audit["original_gate"]["failing_predicates"],
            ["post_tls.terminal"],
        )
        self.assertFalse(audit["original_gate"]["pass"])
        self.assertTrue(audit["corrected_contract_re_evaluation"]["pass"])
        self.assertEqual(
            audit["corrected_contract_re_evaluation"]["failing_predicates"],
            [],
        )
        self.assertTrue(all(item["pass"] for item in audit["common_audit_predicates"]))

    def test_authentic_reuse_claims_are_all_supported(self) -> None:
        audit = AUDITOR.build_audit()
        self.assertTrue(
            audit["biometric_execution"]["all_listed_claims_verified_live"]
        )
        self.assertEqual(
            audit["biometric_execution"]["original_executable_return_code"], 1
        )
        self.assertFalse(
            audit["biometric_execution"]["original_aggregate_pass_marker"]
        )
        self.assertEqual(audit["safety"]["operator_retry_count"], 0)
        self.assertFalse(audit["safety"]["sensor_side_persistence_absence_proven"])

    def test_hash_pin_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary)
            for name in AUDITOR.EXPECTED_HASHES:
                (copied / name).write_bytes((AUDITOR.EVIDENCE / name).read_bytes())
            with (copied / "operator.log").open("ab") as stream:
                stream.write(b"MUTATED=true\n")
            with self.assertRaisesRegex(ValueError, "evidence hash mismatch"):
                AUDITOR.build_audit(copied)

    def test_committed_result_matches_deterministic_auditor(self) -> None:
        audit = AUDITOR.build_audit()
        result = json.loads(RESULT.read_text(encoding="utf-8"))
        self.assertEqual(result["baseline_live_sha"], audit["baseline_live_sha"])
        self.assertEqual(
            result["old_contract"]["failing_predicates"],
            audit["original_gate"]["failing_predicates"],
        )
        self.assertEqual(
            result["corrected_contract"]["pass"],
            audit["corrected_contract_re_evaluation"]["pass"],
        )
        self.assertEqual(
            result["verified_live_claims"],
            audit["biometric_execution"]["claims_verified_live"],
        )


if __name__ == "__main__":
    unittest.main()
