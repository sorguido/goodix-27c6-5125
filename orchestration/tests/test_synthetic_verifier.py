# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from goodix_orchestrator.protocols import TestStatus
from goodix_orchestrator.synthetic_verifier import (
    SyntheticVerificationError,
    SyntheticVerifier,
    VerificationProfile,
)


class SyntheticVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "artifact.txt").write_text("alpha\nbeta\n", encoding="utf-8")
        (self.root / "PROJECT_MANUAL.md").write_text(
            "alpha and beta; O002 synthetic cycle complete\n", encoding="utf-8"
        )
        (self.root / "FINAL_STATUS.md").write_text(
            "O002 synthetic cycle complete\n", encoding="utf-8"
        )
        self.verifier = SyntheticVerifier()

    def test_task_profiles_are_exact_data_only_checks(self) -> None:
        first = self.verifier.verify(self.root, VerificationProfile.TASK_ONE)
        second = self.verifier.verify(self.root, VerificationProfile.TASK_TWO)
        self.assertEqual(first.status, TestStatus.PASS)
        self.assertEqual(second.status, TestStatus.PASS)
        self.assertEqual(first.files_read, ("artifact.txt", "PROJECT_MANUAL.md"))
        self.assertEqual(
            second.files_read,
            ("artifact.txt", "FINAL_STATUS.md", "PROJECT_MANUAL.md"),
        )

    def test_python_payload_in_expected_data_file_is_inert(self) -> None:
        marker = self.root / "payload-executed"
        (self.root / "artifact.txt").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n",
            encoding="utf-8",
        )
        result = self.verifier.verify(self.root, VerificationProfile.TASK_ONE)
        self.assertEqual(result.status, TestStatus.FAIL)
        self.assertFalse(marker.exists())

    def test_unexpected_python_file_is_never_read_or_executed(self) -> None:
        marker = self.root / "unexpected-executed"
        (self.root / "unexpected.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\n",
            encoding="utf-8",
        )
        result = self.verifier.verify(self.root, VerificationProfile.TASK_ONE)
        self.assertNotIn("unexpected.py", result.files_read)
        self.assertFalse(marker.exists())

    def test_host_environment_is_not_exposed_by_execution(self) -> None:
        marker = self.root / "environment-leak"
        payload = (
            "import os\nfrom pathlib import Path\n"
            f"Path({str(marker)!r}).write_text(os.environ['O002_SECRET_SENTINEL'])\n"
        )
        (self.root / "artifact.txt").write_text(payload, encoding="utf-8")
        with patch.dict(os.environ, {"O002_SECRET_SENTINEL": "must-not-leak"}):
            result = self.verifier.verify(self.root, VerificationProfile.TASK_ONE)
        self.assertEqual(result.status, TestStatus.FAIL)
        self.assertFalse(marker.exists())

    def test_expected_file_symlink_escape_is_denied(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside.txt"
        outside.write_text("alpha\nbeta\n", encoding="utf-8")
        self.addCleanup(outside.unlink)
        (self.root / "artifact.txt").unlink()
        (self.root / "artifact.txt").symlink_to(outside)
        with self.assertRaises(SyntheticVerificationError) as caught:
            self.verifier.verify(self.root, VerificationProfile.TASK_ONE)
        self.assertEqual(caught.exception.code, "SYNTHETIC_EXPECTED_FILE_NOT_REGULAR")


if __name__ == "__main__":
    unittest.main()
