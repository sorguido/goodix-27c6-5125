#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Local host-file transaction tests, in a temporary tree only."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("deploy", HERE / "deploy.py")
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class Deployment(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="goodix-managed-test.", dir="/tmp")
        self.root = Path(self.temp.name)
        d.ROOT = self.root
        d.TEST = True
        for directory in ("usr/lib/pam.d", "etc/pam.d", "var/lib"):
            (self.root / directory).mkdir(parents=True)
        d.p(d.VENDOR).write_bytes(d.VENDOR_BYTES)
        d.p("/etc/pam.d/system-auth").write_text(
            "auth required pam_env.so\nauth required pam_faildelay.so delay=2000000\n"
            "auth sufficient pam_unix.so nullok\nauth required pam_deny.so\n")
        self.module = self.root / "candidate.so"
        self.module.write_bytes(b"\x7fELFoffline-only-fixture")
        (self.root / "PROVENANCE").write_text("SOURCE_COMMIT=" + "a" * 40 + "\nPURPOSE=POLKIT_INTERRUPTIBLE_SERVICE_LOCAL_V1\n")

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self):
        return {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mode & 0o7777)
                for p in self.root.rglob("*") if p.is_file()}

    def test_absence_install_idempotence_restore(self):
        before = self.snapshot()
        previous = os.umask(0o077)
        try: d.install("local", self.module)
        finally: os.umask(previous)
        d.install("local", self.module)
        d.verify("local")
        self.assertEqual(d.p(d.PAM).stat().st_mode & 0o777, 0o644)
        self.assertEqual(d.p(d.LOCAL).stat().st_mode & 0o777, 0o644)
        d.uninstall("local")
        d.uninstall("local")
        self.assertEqual(before, self.snapshot())
        self.assertFalse(d.p("/run/polkit").exists())

    def test_existing_stock_override_restored_exactly(self):
        d.p(d.PAM).write_bytes(d.VENDOR_BYTES)
        before = self.snapshot()
        d.install("local", self.module)
        d.uninstall("local")
        self.assertEqual(before, self.snapshot())

    def test_custom_override_vendor_drift_rpmnew_and_global_stack_rejected(self):
        for name, content in ((d.PAM, b"custom"), (d.VENDOR, b"drift"),
                              (d.PAM + ".rpmnew", b"new"),
                              ("/etc/pam.d/system-auth", b"auth sufficient pam_fprintd.so\n")):
            with self.subTest(name=name):
                path = d.p(name)
                old = path.read_bytes() if path.exists() else None
                path.write_bytes(content)
                before = self.snapshot()
                with self.assertRaises(RuntimeError): d.install("local", self.module)
                self.assertEqual(before, self.snapshot())
                if old is None: path.unlink()
                else: path.write_bytes(old)

    def test_partial_install_restores_original(self):
        before = self.snapshot()
        original = d.atomic
        def fail(name, *args):
            if name == d.DROPIN: raise RuntimeError("injected drop-in write failure")
            return original(name, *args)
        with patch.object(d, "atomic", side_effect=fail):
            with self.assertRaises(RuntimeError): d.install("local", self.module)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(d.p(d.STATE).exists())

    def test_owned_file_drift_preserved_and_mode_collision(self):
        d.install("local", self.module)
        d.p(d.PAM).write_bytes(b"new administrator config")
        with self.assertRaises(RuntimeError): d.uninstall("local")
        self.assertEqual(d.p(d.PAM).read_bytes(), b"new administrator config")

    def test_uninstall_after_vendor_update_preserves_new_vendor(self):
        d.install("local", self.module)
        d.p(d.VENDOR).write_bytes(b"new vendor config")
        with self.assertRaises(RuntimeError): d.verify("local")
        d.uninstall("local")
        self.assertEqual(d.p(d.VENDOR).read_bytes(), b"new vendor config")

    def test_managed_local_collision_and_runtime_counters(self):
        d.install("managed")
        with self.assertRaises(RuntimeError): d.install("local", self.module)
        counter = d.p(d.GUARD) / str(os.getuid())
        counter.write_text("3"); counter.chmod(0o600)
        d.verify("managed")
        d.install("managed")
        self.assertEqual(counter.read_text(), "3")
        d.uninstall("managed")
        self.assertFalse(d.p(d.GUARD).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
