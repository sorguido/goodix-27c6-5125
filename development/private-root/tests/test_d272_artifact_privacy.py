# SPDX-License-Identifier: GPL-2.0-or-later
import json
from pathlib import Path
import re
import unittest
import zipfile


REPO = Path(__file__).resolve().parents[1]
D272 = REPO / "analysis/D272"
BUNDLE = D272 / "D272_01_sigfm_target_validation_prelive_offline_bundle.zip"


class D272ArtifactPrivacyTests(unittest.TestCase):
    def test_json_is_parseable_and_has_no_large_embedded_blob(self):
        long_blob = re.compile(r"(?i)(?:[0-9a-f]{2}){129}|[A-Za-z0-9+/]{512,}={0,2}")
        for path in D272.glob("*.json"):
            document = json.loads(path.read_text(encoding="utf-8"))
            serialized = json.dumps(document, sort_keys=True)
            self.assertIsNone(long_blob.search(serialized), path)

    def test_no_sensitive_file_type_in_step_directory(self):
        forbidden = {".pcap", ".pcapng", ".png", ".pgm", ".raw", ".fp3", ".key"}
        for path in D272.iterdir():
            self.assertNotIn(path.suffix.lower(), forbidden, path)

    def test_bundle_members_are_sanitized_when_bundle_exists(self):
        if not BUNDLE.exists():
            self.skipTest("bundle generated only at final packaging stage")
        with zipfile.ZipFile(BUNDLE) as archive:
            names = archive.namelist()
        self.assertTrue(names)
        for name in names:
            lowered = name.lower()
            self.assertFalse(any(
                token in lowered for token in
                ("capture", ".pcap", ".png", ".pgm", ".raw", ".fp3", "secret", "psk")
            ), name)


if __name__ == "__main__":
    unittest.main()
