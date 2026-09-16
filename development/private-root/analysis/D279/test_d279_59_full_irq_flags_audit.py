#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "analysis/D279/d279_59_full_irq_flags_audit.py"


def load_module():
    spec = importlib.util.spec_from_file_location("d279_59_audit", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FullIrqFlagsAuditTest(unittest.TestCase):
    def test_authentic_full_matrix_and_contexts(self) -> None:
        result = load_module().analyze(ROOT)
        rows = result["d279_10_attempt02_irq_matrix"]
        self.assertEqual(len(rows), 65)
        self.assertEqual(Counter(row["phase"] for row in rows), Counter({
            "bootstrap_fdt_manual": 3,
            "first_cycle_finger_down": 1,
            "first_cycle_finger_up": 1,
            "repeated_cycle_finger_down": 19,
            "repeated_cycle_contact_sample": 19,
            "repeated_cycle_finger_up": 19,
            "terminal_cycle_finger_down": 1,
            "terminal_cycle_contact_sample": 1,
            "terminal_cycle_finger_up": 1,
        }))
        self.assertTrue(all(not row["reserved_bits_set"] for row in rows))
        self.assertFalse(result["payload_exported"])
        static = result["static_touchflag_semantics"]
        self.assertEqual(static["oem_authority"]["status"],
                         "VERIFIED_STATICALLY")
        self.assertEqual(static["oem_authority"]["handler"],
                         "0x180029314-0x1800296d6")
        self.assertEqual(static["oem_authority"]["channel_count"], 6)
        self.assertTrue(static["policy_consequence"]
                        ["all_low_six_bits_are_independently_interpreted"])
        self.assertFalse(static["policy_consequence"]
                         ["all_physical_subsets_observed"])
        self.assertEqual(static["rockytkg_corroboration"]["role"],
                         "SEMANTIC_CORROBORATION_NOT_TARGET_USB_TRANSCRIPT_AUTHORITY")

    def test_cli_output_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="d279-59-") as tmp:
            first = Path(tmp) / "first.json"
            second = Path(tmp) / "second.json"
            corpus = Path(tmp) / "corpus.tsv"
            for output in (first, second):
                subprocess.run([sys.executable, str(SCRIPT), "--output", str(output)],
                               cwd=ROOT, check=True)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(json.loads(first.read_text())["schema"],
                             "D279_59_FULL_IRQ_FLAGS_AUDIT_V1")
            subprocess.run([sys.executable, str(SCRIPT), "--output", str(first),
                            "--policy-corpus", str(corpus)], cwd=ROOT, check=True)
            lines = corpus.read_text().splitlines()
            self.assertEqual(len(lines), 67)
            self.assertEqual(lines[-1],
                             "D279_57_LIVE_4DE9C34\trearm_finger_down\t0x32\t0x0002\t0x002f")


if __name__ == "__main__":
    unittest.main()
