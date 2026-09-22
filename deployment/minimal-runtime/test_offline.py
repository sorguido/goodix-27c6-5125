# SPDX-License-Identifier: GPL-2.0-or-later
"""Temporary-filesystem transaction checks; no system bus, USB, root or ELF execution."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("r3_deploy", HERE / "deploy.py")
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class Transactions(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="goodix-r3-files-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.runtime = self.base / "lib64/goodix-27c6-5125"
        self.dropin = self.base / "system/fprintd.service.d/90-goodix-5125-runtime.conf"
        self.runtime.parent.mkdir()
        self.dropin.parent.parent.mkdir()
        output = patch("sys.stdout", new_callable=io.StringIO)
        output.start()
        self.addCleanup(output.stop)
        self.calls = []
        self.failure = None
        self.payload = {name: f"synthetic {name}".encode() for name in d.LIBRARIES}
        self.payload.update({"licenses/test.txt": b"synthetic license", "deploy.py": b"inverse",
                             "uninstall.sh": b"inverse entry"})
        for name, value in (("RUNTIME", self.runtime), ("DROPIN", self.dropin)):
            context = patch.object(d, name, value)
            context.start()
            self.addCleanup(context.stop)
        # Host interfaces are replaced; file publication/removal and integrity checks are real.
        for name, replacement in (("safe_directory", lambda _p: None),
                                  ("no_sensor", lambda: None), ("run", self.command)):
            context = patch.object(d, name, replacement)
            context.start()
            self.addCleanup(context.stop)

    def command(self, *args):
        self.calls.append(args)
        if args == self.failure:
            self.failure = None
            raise RuntimeError("injected host-command failure")
        return ""

    def install(self, active="inactive"):
        d.install(self.payload, "a" * 40, active)

    def test_round_trip_preserves_foreign_files_and_inactive_state(self):
        self.dropin.parent.mkdir()
        sentinel = self.dropin.parent / "vendor-test.conf"
        sentinel.write_bytes(b"preserve")
        self.install()
        self.assertEqual(self.dropin.read_bytes(), d.CONFIG)
        self.assertEqual(d.inspect_owned()["previous_service"], "inactive")
        d.uninstall()
        self.assertFalse(self.runtime.exists())
        self.assertFalse(self.dropin.exists())
        self.assertEqual(sentinel.read_bytes(), b"preserve")
        self.assertNotIn(("systemctl", "start", d.UNIT), self.calls)
        d.uninstall()

    def test_active_state_restored_and_created_directory_removed(self):
        self.install("active")
        self.assertNotIn(("systemctl", "start", d.UNIT), self.calls)
        d.uninstall()
        self.assertFalse(self.dropin.parent.exists())
        self.assertEqual(self.calls[-1], ("systemctl", "start", d.UNIT))
        self.assertFalse(any(call[0] in ("rpm", "git") for call in self.calls))

    def test_identical_install_is_idempotent(self):
        self.install()
        before = (self.runtime / d.STATE).read_bytes()
        self.calls.clear()
        self.install()
        self.assertEqual((self.runtime / d.STATE).read_bytes(), before)
        self.assertFalse(self.calls)

    def test_initial_collision_preserved(self):
        self.dropin.parent.mkdir()
        self.dropin.write_bytes(b"foreign")
        with self.assertRaisesRegex(RuntimeError, "occupied"):
            self.install()
        self.assertEqual(self.dropin.read_bytes(), b"foreign")
        self.assertFalse(self.runtime.exists())
        self.assertFalse(self.calls)

    def test_unowned_runtime_not_adopted(self):
        self.runtime.mkdir()
        (self.runtime / "keep").write_bytes(b"foreign")
        with self.assertRaises(OSError):
            self.install()
        self.assertEqual((self.runtime / "keep").read_bytes(), b"foreign")
        self.assertFalse(self.calls)

    def test_reload_failure_restores_files_and_service(self):
        self.failure = ("systemctl", "daemon-reload")
        with self.assertRaisesRegex(RuntimeError, "injected"):
            self.install("active")
        self.assertFalse(self.runtime.exists())
        self.assertFalse(self.dropin.parent.exists())
        self.assertEqual(self.calls[-1], ("systemctl", "start", d.UNIT))

    def test_failed_vendor_restart_retains_inverse_for_retry(self):
        self.install("active")
        self.failure = ("systemctl", "start", d.UNIT)
        with self.assertRaisesRegex(RuntimeError, "injected"):
            d.uninstall()
        self.assertTrue((self.runtime / "uninstall.sh").exists())
        self.assertFalse(self.dropin.exists())
        d.uninstall()
        self.assertFalse(self.runtime.exists())

    def test_uninstall_does_not_delete_foreign_additions(self):
        self.install()
        (self.runtime / "foreign").write_bytes(b"keep")
        self.calls.clear()
        with self.assertRaisesRegex(RuntimeError, "unowned"):
            d.uninstall()
        self.assertEqual((self.runtime / "foreign").read_bytes(), b"keep")
        self.assertFalse(self.calls)

    def test_dropin_drift_retained(self):
        self.install()
        self.dropin.write_bytes(b"changed externally")
        self.calls.clear()
        with self.assertRaisesRegex(RuntimeError, "drifted"):
            d.uninstall()
        self.assertTrue(self.runtime.exists())
        self.assertFalse(self.calls)

    def test_payload_digest_drift_refused(self):
        self.install()
        (self.runtime / d.LIBRARIES[0]).write_bytes(b"corrupt")
        self.calls.clear()
        with self.assertRaisesRegex(RuntimeError, "drift"):
            self.install()
        self.assertFalse(self.calls)

    def test_collision_during_publish_never_removed(self):
        original_link = d.os.link
        def collide(source, dest):
            Path(dest).write_bytes(b"foreign concurrent file")
            return original_link(source, dest)
        with patch.object(d.os, "link", side_effect=collide):
            with self.assertRaisesRegex(RuntimeError, "concurrent foreign"):
                self.install("active")
        self.assertEqual(self.dropin.read_bytes(), b"foreign concurrent file")
        self.assertTrue((self.runtime / "uninstall.sh").exists())
        self.assertNotIn(("systemctl", "daemon-reload"), self.calls)
        self.assertNotIn(("systemctl", "start", d.UNIT), self.calls)

    def test_created_tree_has_exact_relative_links(self):
        self.install()
        self.assertEqual(d.os.readlink(self.runtime / "libfprint-2.so.2"), "libfprint-2.so.2.0.0")
        state = json.loads((self.runtime / d.STATE).read_text())
        self.assertEqual(state["build_commit"], d.BUILD_COMMIT)
        self.assertEqual(set(state["files"]), set(self.payload))


class InputValidation(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="goodix-r3-input-")
        self.addCleanup(self.temporary.cleanup)
        self.build = Path(self.temporary.name)
        runtime = self.build / "runtime"
        (runtime / "licenses").mkdir(parents=True)
        (self.build / "build-provenance.txt").write_text(
            f"SOURCE_COMMIT={d.BUILD_COMMIT}\nBUILD_MODE=normal\nVM_TYPE=kvm\n")
        for name in d.LIBRARIES:
            (runtime / name).write_bytes(b"synthetic library")
        (runtime / "SHA256SUMS").write_text("".join(
            f"{d.digest(b'synthetic library')}  {name}\n" for name in d.LIBRARIES))
        for name, target in d.LINKS.items():
            (runtime / name).symlink_to(target)
        for name in ("OpenCV-LICENSES.txt", "source-files.tsv", "source-files.sha256"):
            (runtime / name).write_text("synthetic metadata")
        for name in ("GPL-2.0-or-later", "LGPL-2.1-or-later", "GPL-3.0-or-later", "Apache-2.0"):
            (runtime / "licenses" / f"{name}.txt").write_text("synthetic license")
        def source_query(*args):
            return {"branch": "development", "status": "", "rev-parse": "b" * 40,
                    "diff": ""}[args[0]]
        context = patch.object(d, "git", side_effect=source_query)
        context.start()
        self.addCleanup(context.stop)

    def test_exact_build_payload_and_saved_inverse(self):
        payload, commit = d.load_payload(self.build)
        self.assertEqual(commit, "b" * 40)
        self.assertIn("uninstall.sh", payload)
        self.assertIn("deploy.py", payload)
        self.assertNotIn("libgusb.so.2", payload)
        self.assertNotIn("fprintd", payload)

    def test_modified_library_rejected(self):
        (self.build / "runtime" / d.LIBRARIES[0]).write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
            d.load_payload(self.build)

    def test_traversal_manifest_rejected(self):
        (self.build / "runtime/SHA256SUMS").write_text("0" * 64 + "  ../secret\n")
        with self.assertRaisesRegex(RuntimeError, "manifest"):
            d.load_payload(self.build)

    def test_wrong_build_provenance_rejected(self):
        (self.build / "build-provenance.txt").write_text("SOURCE_COMMIT=other\nBUILD_MODE=normal\n")
        with self.assertRaisesRegex(RuntimeError, "retained normal"):
            d.load_payload(self.build)

    def test_link_outside_runtime_rejected(self):
        link = self.build / "runtime/libfprint-2.so.2"
        link.unlink()
        link.symlink_to("/usr/lib64/libfprint-2.so.2")
        with self.assertRaisesRegex(RuntimeError, "unexpected link"):
            d.load_payload(self.build)


if __name__ == "__main__":
    unittest.main()
