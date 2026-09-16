#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("d279_38_target_role_order_audit.py")
SPEC = importlib.util.spec_from_file_location("d279_38_role_audit_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


class TargetRoleOrderAuditTests(unittest.TestCase):
    def test_pure_classifier_requires_alternating_pairs(self) -> None:
        fingerprint = tuple(range(100, 143))
        primary = fingerprint[1::2]
        roles = AUDIT.classify_roles(fingerprint, primary)
        self.assertEqual(
            roles,
            ("baseline",) + ("primary", "auxiliary") * 21,
        )
        with self.assertRaisesRegex(
            AUDIT.RoleOrderAuditError, "CYCLE_1_PRIMARY_ORDER"
        ):
            AUDIT.classify_roles(fingerprint, fingerprint[2::2])

    def test_authentic_metadata_closes_exact_role_order(self) -> None:
        result = AUDIT.analyze()
        self.assertTrue(
            result["evidence"]["tls_application_to_fingerprint_b0_identity"]
        )
        self.assertTrue(
            result["evidence"]["all_21_primary_auxiliary_pairs_alternate"]
        )
        old = result["superseded_contiguous_partition"]
        self.assertEqual(
            old["old_primary_labeled_records"],
            {"actual_primary": 11, "actual_auxiliary": 10},
        )
        self.assertEqual(
            old["old_auxiliary_labeled_records"],
            {"actual_primary": 10, "actual_auxiliary": 11},
        )
        self.assertFalse(old["role_specific_d279_35_and_d279_37_aggregates_valid"])


if __name__ == "__main__":
    unittest.main()
