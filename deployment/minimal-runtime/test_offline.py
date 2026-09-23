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
        self.mask = self.base / "run/systemd/system/fprintd.service"
        self.mask.parent.mkdir(parents=True)
        self.reader = self.base / "sys/bus/usb/devices/reader"
        self.reader.mkdir(parents=True)
        (self.reader / "idVendor").write_text("27c6\n")
        (self.reader / "idProduct").write_text("5125\n")
        self.runtime.parent.mkdir()
        self.dropin.parent.parent.mkdir()
        output = patch("sys.stdout", new_callable=io.StringIO)
        output.start()
        self.addCleanup(output.stop)
        # These original transaction tests isolate the material boundary. The
        # separate test_material_labels.py exercises it with real temp metadata.
        for name in ("material_plan", "apply_material", "remove_material", "selinux_tools",
                     "check_material_record", "runtime_manifest_preflight"):
            context = patch.object(d, name)
            context.start()
            self.addCleanup(context.stop)
        self.calls = []
        self.failure = None
        self.stop_stuck = False
        self.mask_shadowed = False
        self.payload = {name: f"synthetic {name}".encode() for name in d.LIBRARIES}
        self.payload.update({"licenses/test.txt": b"synthetic license", "deploy.py": b"inverse",
                             "uninstall.sh": b"inverse entry"})
        for name, value in (("RUNTIME", self.runtime), ("DROPIN", self.dropin),
                            ("SERVICE_MASK", self.mask)):
            context = patch.object(d, name, value)
            context.start()
            self.addCleanup(context.stop)
        # Host interfaces are replaced; file publication/removal and integrity checks are real.
        for name, replacement in (("safe_directory", lambda _p: None),
                                  ("run", self.command)):
            context = patch.object(d, name, replacement)
            context.start()
            self.addCleanup(context.stop)

    def command(self, *args):
        self.calls.append(args)
        self.assertNotIn(args[:2], (("systemctl", "start"), ("systemctl", "restart")))
        if args == self.failure:
            self.failure = None
            raise RuntimeError("injected host-command failure")
        if args == ("systemctl", "stop", d.UNIT):
            self.assertTrue(self.mask.is_symlink())
            self.assertEqual(d.os.readlink(self.mask), "/dev/null")
        if args[:2] == ("systemctl", "show"):
            state = {"ActiveState": "active" if self.stop_stuck else "inactive",
                     "MainPID": "42" if self.stop_stuck else "0", "SubState": "running" if self.stop_stuck else "dead",
                     "Result": "success", "ExecMainStartTimestamp": "",
                     "LoadState": "loaded" if self.mask_shadowed else "masked"}
            return "\n".join(name + "=" + state[name] for arg in args[3:]
                             if arg.startswith("--property=") for name in [arg.removeprefix("--property=")])
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

    def test_reader_present_active_service_is_not_restarted_after_removal(self):
        self.install("active")
        self.assertNotIn(("systemctl", "start", d.UNIT), self.calls)
        d.uninstall()
        self.assertFalse(self.dropin.parent.exists())
        self.assertEqual(self.calls[-1], ("systemctl", "daemon-reload"))
        self.assertFalse(self.mask.is_symlink())
        self.assertEqual((self.reader / "idVendor").read_text(), "27c6\n")
        self.assertEqual((self.reader / "idProduct").read_text(), "5125\n")
        self.assertFalse(any(call[0] in ("rpm", "git") for call in self.calls))

    def test_identical_install_is_idempotent(self):
        self.install()
        state = d.inspect_owned()
        state["material_selinux"] = {"phase": "ready"}
        d.save_state(state)
        before = (self.runtime / d.STATE).read_bytes()
        self.calls.clear()
        self.install()
        self.assertEqual((self.runtime / d.STATE).read_bytes(), before)
        self.assertFalse(self.calls)

    def test_different_payload_refused_without_mutation(self):
        self.install()
        before = (self.runtime / d.STATE).read_bytes()
        self.payload[d.LIBRARIES[0]] = b"different payload"
        self.calls.clear()
        with self.assertRaisesRegex(RuntimeError, "different payload"):
            self.install()
        self.assertEqual((self.runtime / d.STATE).read_bytes(), before)
        self.assertEqual((self.runtime / d.LIBRARIES[0]).read_bytes(),
                         f"synthetic {d.LIBRARIES[0]}".encode())
        self.assertFalse(self.calls)

    def test_old_install_requires_its_saved_inverse(self):
        self.install()
        state_path = self.runtime / d.STATE
        state = json.loads(state_path.read_text())
        state["build_commit"] = "c5df71772b3ade7cf3d1ea2d418a65e0ab75b1f6"
        state_path.write_text(json.dumps(state))
        before = state_path.read_bytes()
        self.calls.clear()
        for action in (self.install, d.uninstall):
            with self.assertRaisesRegex(RuntimeError, "unknown installation"):
                action()
        self.assertEqual(state_path.read_bytes(), before)
        self.assertTrue((self.runtime / "uninstall.sh").exists())
        self.assertFalse(self.calls)

    def test_saved_inverse_works_without_checkout_or_build(self):
        self.payload["deploy.py"] = (HERE / "deploy.py").read_bytes()
        self.payload["uninstall.sh"] = (HERE / "uninstall.sh").read_bytes()
        self.install()
        saved_spec = importlib.util.spec_from_file_location(
            "r3_saved_inverse", self.runtime / "deploy.py")
        saved = importlib.util.module_from_spec(saved_spec)
        with patch("sys.dont_write_bytecode", True):
            saved_spec.loader.exec_module(saved)
        self.calls.clear()
        with patch.object(saved, "RUNTIME", self.runtime), \
                patch.object(saved, "DROPIN", self.dropin), \
                patch.object(saved, "SERVICE_MASK", self.mask), \
                patch.object(saved, "REPO", self.base / "absent-checkout"), \
                patch.object(saved, "safe_directory"), \
                patch.object(saved, "run", side_effect=self.command), \
                patch.object(saved, "git", side_effect=AssertionError("Git forbidden")), \
                patch.object(saved, "load_payload", side_effect=AssertionError("build forbidden")):
            saved.uninstall()
        self.assertFalse(self.runtime.exists())
        self.assertFalse(self.dropin.exists())
        self.assertIn(("systemctl", "stop", d.UNIT), self.calls)
        self.assertFalse(self.mask.is_symlink())

    def test_only_owned_footprint_changes_vendor_and_materials_preserved(self):
        sentinels = ("usr/libexec/fprintd", "usr/lib/systemd/system/fprintd.service",
                     "etc/pam.d/fingerprint-auth", "usr/lib/udev/rules.d/vendor.rules",
                     "var/lib/fprint/synthetic", "var/lib/goodix-5125-poc/synthetic")
        for name in sentinels:
            path = self.base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"untouched synthetic sentinel")
        def snapshot():
            return {p.relative_to(self.base): p.read_bytes()
                    for p in self.base.rglob("*") if p.is_file()}
        before = snapshot()
        self.install()
        self.assertTrue(all((self.base / name).read_bytes() == data
                            for name, data in before.items()))
        added = set(snapshot()) - set(before)
        expected = {p.relative_to(self.base) for p in self.runtime.rglob("*") if p.is_file()}
        self.assertEqual(added, expected | {self.dropin.relative_to(self.base)})
        d.uninstall()
        self.assertEqual(snapshot(), before)
        self.assertFalse(any(call[0] not in ("systemctl", "restorecon") for call in self.calls))

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

    def test_reload_failure_restores_only_own_mask_without_starting_service(self):
        self.failure = ("systemctl", "daemon-reload")
        with self.assertRaisesRegex(RuntimeError, "injected"):
            self.install("active")
        self.assertFalse(self.runtime.exists())
        self.assertFalse(self.dropin.parent.exists())
        self.assertEqual(self.calls[-1], ("systemctl", "daemon-reload"))
        self.assertFalse(self.mask.is_symlink())

    def test_nonquiescent_service_refuses_runtime_writes_with_precise_state(self):
        self.stop_stuck = True
        with self.assertRaisesRegex(RuntimeError, "ActiveState=active.*MainPID=42"):
            self.install()
        self.assertFalse(self.runtime.exists())
        self.assertFalse(self.dropin.exists())
        self.assertEqual(list(self.runtime.parent.iterdir()), [])
        self.assertIn(("systemctl", "stop", d.UNIT), self.calls)
        self.assertFalse(self.mask.is_symlink())

    def test_failed_stop_retains_runtime_and_inverse_for_retry(self):
        self.install("active")
        self.failure = ("systemctl", "stop", d.UNIT)
        with self.assertRaisesRegex(RuntimeError, "injected"):
            d.uninstall()
        self.assertTrue((self.runtime / "uninstall.sh").exists())
        self.assertTrue(self.dropin.exists())
        self.assertFalse(self.mask.is_symlink())
        d.uninstall()
        self.assertFalse(self.runtime.exists())

    def test_nonquiescent_uninstall_preserves_runtime_and_activation(self):
        self.install()
        before = (self.runtime / d.STATE).read_bytes()
        self.stop_stuck = True
        with self.assertRaisesRegex(RuntimeError, 'ActiveState=active.*MainPID=42'):
            d.uninstall()
        self.assertEqual((self.runtime / d.STATE).read_bytes(), before)
        self.assertEqual(self.dropin.read_bytes(), d.CONFIG)
        self.assertFalse(self.mask.is_symlink())

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
        self.assertFalse(self.mask.is_symlink())
        self.assertNotIn(("systemctl", "start", d.UNIT), self.calls)

    def test_created_tree_has_exact_relative_links(self):
        self.install()
        self.assertEqual(d.os.readlink(self.runtime / "libfprint-2.so.2"), "libfprint-2.so.2.0.0")
        state = json.loads((self.runtime / d.STATE).read_text())
        self.assertEqual(state["build_commit"], d.BUILD_COMMIT)
        self.assertEqual(set(state["files"]), set(self.payload))

    def test_present_reader_install_uninstall_does_not_read_sysfs_or_open_usb(self):
        original_iterdir = Path.iterdir
        original_open = d.os.open
        def guarded_iterdir(path):
            if str(path).startswith('/sys/') or path == self.reader.parent:
                self.fail('runtime lifecycle inspected USB presence')
            return original_iterdir(path)
        def guarded_open(path, *args, **kwargs):
            self.assertFalse(str(path).startswith(('/sys/bus/usb/', '/dev/bus/usb/')),
                             'runtime lifecycle opened USB/sysfs directly')
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'iterdir', guarded_iterdir), patch.object(d.os, 'open', guarded_open):
            self.install()
            self.assertFalse(self.mask.is_symlink())
            d.uninstall()
        self.assertTrue(self.reader.exists())
        self.assertFalse(self.runtime.exists())

    def test_borrowed_runtime_mask_is_preserved(self):
        self.mask.symlink_to('/dev/null')
        identity = self.mask.lstat().st_ino
        self.install()
        d.uninstall()
        self.assertTrue(self.mask.is_symlink())
        self.assertEqual(self.mask.lstat().st_ino, identity)

    def test_mask_lstat_failure_after_create_retains_uncertain_mask_with_diagnostic(self):
        original_lstat = Path.lstat
        def failed_identity(path, *args, **kwargs):
            if path == self.mask:
                original_lstat(path, *args, **kwargs)
                raise OSError('synthetic identity-read failure after creation')
            return original_lstat(path, *args, **kwargs)
        with patch.object(Path, 'lstat', failed_identity), \
                patch('sys.stderr', new_callable=io.StringIO) as error:
            with self.assertRaisesRegex(OSError, 'identity-read failure'):
                self.install()
        self.assertTrue(self.mask.is_symlink())
        self.assertEqual(d.os.readlink(self.mask), '/dev/null')
        self.assertIn('FPRINTD_MASK_ACQUISITION=INCOMPLETE', error.getvalue())
        self.assertIn('retained because ownership could not be established', error.getvalue())
        self.assertFalse(self.runtime.exists())
        self.assertFalse(self.dropin.exists())
        self.assertFalse(self.calls)

    def test_interrupt_after_mask_creation_preserves_unverified_identity(self):
        original_symlink = Path.symlink_to
        def interrupted_creation(path, target, *args, **kwargs):
            original_symlink(path, target, *args, **kwargs)
            if path == self.mask:
                raise KeyboardInterrupt('synthetic signal after creating mask')
        with patch.object(Path, 'symlink_to', interrupted_creation), \
                patch('sys.stderr', new_callable=io.StringIO) as error:
            with self.assertRaises(KeyboardInterrupt):
                self.install()
        self.assertTrue(self.mask.is_symlink())
        self.assertIn('FPRINTD_MASK_ACQUISITION=INCOMPLETE', error.getvalue())
        self.assertFalse(self.runtime.exists())
        self.assertFalse(self.calls)

    def test_foreign_runtime_unit_is_not_overwritten(self):
        self.mask.write_bytes(b'foreign runtime unit')
        with self.assertRaisesRegex(RuntimeError, 'mask path occupied'):
            self.install()
        self.assertEqual(self.mask.read_bytes(), b'foreign runtime unit')
        self.assertFalse(self.runtime.exists())
        self.assertFalse(self.calls)

    def test_shadowed_runtime_mask_refuses_mutation_after_stopping_service(self):
        self.mask_shadowed = True
        with self.assertRaisesRegex(RuntimeError, 'not inhibited.*LoadState=loaded'):
            self.install()
        self.assertIn(('systemctl', 'stop', d.UNIT), self.calls)
        self.assertFalse(self.runtime.exists())
        self.assertFalse(self.dropin.exists())
        self.assertFalse(self.mask.is_symlink())

    def test_changed_mask_is_preserved_after_interrupted_operation(self):
        alternate = self.base / 'foreign-mask'
        alternate.write_bytes(b'preserve')
        with self.assertRaisesRegex(RuntimeError, 'runtime mask changed'):
            with d.quiesced_service():
                self.mask.unlink()
                self.mask.symlink_to(alternate)
        self.assertEqual(d.os.readlink(self.mask), str(alternate))
        self.assertEqual(alternate.read_bytes(), b'preserve')

    def test_interrupt_restores_only_own_mask(self):
        with self.assertRaises(KeyboardInterrupt):
            with d.quiesced_service():
                raise KeyboardInterrupt('synthetic interruption')
        self.assertFalse(self.mask.is_symlink())
        self.assertNotIn(("systemctl", "start", d.UNIT), self.calls)


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
        self.assertEqual(d.BUILD_COMMIT, "b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226")
        self.assertEqual(payload["deploy.py"], (HERE / "deploy.py").read_bytes())
        self.assertEqual(payload["uninstall.sh"], (HERE / "uninstall.sh").read_bytes())

    def test_modified_library_rejected(self):
        (self.build / "runtime" / d.LIBRARIES[0]).write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
            d.load_payload(self.build)

    def test_traversal_manifest_rejected(self):
        (self.build / "runtime/SHA256SUMS").write_text("0" * 64 + "  ../secret\n")
        with self.assertRaisesRegex(RuntimeError, "manifest"):
            d.load_payload(self.build)

    def test_wrong_build_provenance_rejected(self):
        for commit, mode in (("c5df71772b3ade7cf3d1ea2d418a65e0ab75b1f6", "normal"),
                             ("other", "normal"), (d.BUILD_COMMIT, "sanitized")):
            with self.subTest(commit=commit, mode=mode):
                (self.build / "build-provenance.txt").write_text(
                    f"SOURCE_COMMIT={commit}\nBUILD_MODE={mode}\n")
                with self.assertRaisesRegex(RuntimeError, "qualified normal R3"):
                    d.load_payload(self.build)

    def test_dirty_or_wrong_branch_rejected(self):
        for branch, status in (("development", " M file"), ("main", "")):
            with self.subTest(branch=branch, status=status), \
                    patch.object(d, "git", side_effect=lambda *args:
                                 {"branch": branch, "status": status}[args[0]]):
                with self.assertRaisesRegex(RuntimeError, "development|clean committed"):
                    d.load_payload(self.build)

    def test_critical_source_drift_rejected(self):
        original = d.git
        def drift(*args):
            if args[0] == "diff":
                self.assertEqual(args[1:5], ("--exit-code", d.BUILD_COMMIT, "HEAD", "--"))
                self.assertIn("libfprint-driver", args)
                self.assertIn("production/build-inner.sh", args)
                raise RuntimeError("critical source drift")
            return original(*args)
        with patch.object(d, "git", side_effect=drift):
            with self.assertRaisesRegex(RuntimeError, "critical source drift"):
                d.load_payload(self.build)

    def test_missing_or_additional_library_rejected(self):
        manifest = self.build / "runtime/SHA256SUMS"
        original = manifest.read_text()
        for altered in ("\n".join(original.splitlines()[1:]) + "\n",
                        original + "0" * 64 + "  libgusb.so.2\n"):
            with self.subTest(manifest=altered):
                manifest.write_text(altered)
                with self.assertRaisesRegex(RuntimeError, "library set"):
                    d.load_payload(self.build)

    def test_link_outside_runtime_rejected(self):
        link = self.build / "runtime/libfprint-2.so.2"
        link.unlink()
        link.symlink_to("/usr/lib64/libfprint-2.so.2")
        with self.assertRaisesRegex(RuntimeError, "unexpected link"):
            d.load_payload(self.build)


class MachineGate(unittest.TestCase):
    def test_machine_gate_checks_vm_privilege_without_usb_presence_requirement(self):
        with patch.object(d, "run") as command, \
                patch.object(d.os, "geteuid", return_value=0), \
                patch.object(Path, 'iterdir', side_effect=AssertionError('USB/sysfs query forbidden')):
            d.machine_gate()
            command.assert_called_once_with("systemd-detect-virt", "--vm", "--quiet")

    def test_host_command_timeout_is_bounded_and_readable(self):
        args = ('systemctl', 'stop', d.UNIT)
        with patch.object(d.subprocess, 'run', side_effect=d.subprocess.TimeoutExpired(args, 30)) as command:
            with self.assertRaisesRegex(RuntimeError, 'timed out after 30 seconds'):
                d.run(*args)
            command.assert_called_once_with(args, env=d.ENV, text=True, capture_output=True, timeout=30)


if __name__ == "__main__":
    unittest.main()
