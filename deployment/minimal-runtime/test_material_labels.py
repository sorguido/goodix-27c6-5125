# SPDX-License-Identifier: GPL-2.0-or-later
"""SELinux lifecycle with mock commands/xattrs, real temp files, no protected input."""
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("r3_label_deploy", HERE / "deploy.py")
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
DEFAULT = "system_u:object_r:var_lib_t:s0"


class MaterialLifecycle(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="r3-label-test-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.runtime = self.base / "lib64/runtime"
        self.runtime.parent.mkdir()
        self.dropin = self.base / "system/unit.d/runtime.conf"
        self.dropin.parent.parent.mkdir()
        self.material = self.base / "var/lib/goodix-5125-poc"
        self.material.mkdir(parents=True, mode=0o700)
        for name in d.MATERIAL_NAMES:
            p = self.material / name
            p.write_bytes(b"synthetic protected-content sentinel")
            p.chmod(0o600)
        self.contexts = [DEFAULT] * 6
        self.rules = []
        self.calls = []
        self.fail = None
        self.bad_restore = False
        self.foreign_rule = r"/opt/foreign\.data(/.*)?    all files    system_u:object_r:usr_t:s0"
        self.rules.append(self.foreign_rule)
        self.rule = str(self.material) + "(/.*)?"
        self.payload = {name: b"synthetic ELF sentinel" for name in d.LIBRARIES}
        self.payload.update({"deploy.py": (HERE / "deploy.py").read_bytes(),
                             "uninstall.sh": (HERE / "uninstall.sh").read_bytes(),
                             "licenses/test.txt": b"synthetic notice"})
        real_lstat = Path.lstat
        def metadata(path, *args, **kwargs):
            st = real_lstat(path, *args, **kwargs)
            if path == self.material or path.parent == self.material:
                # Only synthetic fixture ownership: never chown or use root.
                from types import SimpleNamespace
                attrs = {key: getattr(st, key) for key in dir(st) if key.startswith("st_")}
                attrs.update(st_uid=0, st_gid=0)
                return SimpleNamespace(**attrs)
            return st
        self.patch(Path, "lstat", metadata)
        for name, value in (("RUNTIME", self.runtime), ("DROPIN", self.dropin),
                            ("MATERIAL", self.material), ("MATERIAL_RULE", self.rule),
                            ("safe_directory", lambda p: None), ("no_sensor", lambda: None),
                            ("run", self.command), ("git", self.git)):
            self.patch(d, name, value)
        self.patch(d.shutil, "which", lambda name, **kwargs: "/mock/" + name)
        self.patch(d.os, "getxattr", self.xattr)
        self.patch(__import__('sys'), "stdout", io.StringIO())
        self.before = self.snapshot()

    def patch(self, obj, name, value):
        ctx = patch.object(obj, name, value)
        ctx.start()
        self.addCleanup(ctx.stop)

    def git(self, *args):
        return {"branch": "development", "status": "", "rev-parse": "a" * 40}[args[0]]

    def snapshot(self):
        return [(p.read_bytes() if p.is_file() else None, p.stat().st_uid,
                 p.stat().st_gid, stat.S_IMODE(p.stat().st_mode), p.stat().st_mtime_ns)
                for p in d.material_paths()]

    def xattr(self, path, key, **kwargs):
        self.assertEqual(key, "security.selinux")
        self.assertEqual(kwargs, {"follow_symlinks": False})
        return self.contexts[list(d.material_paths()).index(path)].encode() + b"\0"

    def exact(self, context=None, kind="all files"):
        return f"{self.rule}    {kind}    {context or d.MATERIAL_CONTEXT}"

    def command(self, *args):
        self.calls.append(args)
        if self.fail == args:
            self.fail = None
            raise RuntimeError("injected failure")
        if args == ("getenforce",):
            return "Enforcing"
        if args == ("semanage", "fcontext", "-l", "-C", "-n"):
            return "\n".join(self.rules)
        if args[:3] == ("semanage", "fcontext", "-a"):
            self.assertEqual(args, ("semanage", "fcontext", "-a", "-f", "a", "-t",
                                    "fprintd_var_lib_t", "-r", "s0", self.rule))
            self.assertNotIn(self.exact(), self.rules)
            self.rules.append(self.exact())
        elif args[:3] == ("semanage", "fcontext", "-d"):
            self.assertEqual(args, ("semanage", "fcontext", "-d", "-f", "a", self.rule))
            self.rules.remove(self.exact())
        elif args[:3] == ("restorecon", "-F", "--"):
            self.assertEqual(args[3:], tuple(str(p) for p in d.material_paths()))
            expected = d.MATERIAL_CONTEXT if self.exact() in self.rules else DEFAULT
            self.contexts[:3 if self.bad_restore else 6] = [expected] * (3 if self.bad_restore else 6)
        elif args[:2] == ("matchpathcon", "-n"):
            return DEFAULT
        elif args[:2] == ("systemctl", "show"):
            return {"--property=ActiveState": "inactive", "--property=MainPID": "0"}[args[3]]
        elif args[0] not in ("systemctl", "restorecon"):
            self.failTest(f"unexpected command: {args}")
        return ""

    def mutations(self):
        return [c for c in self.calls if c[0] == "restorecon" or
                (c[0] == "semanage" and c[2] != "-l") or
                (c[0] == "systemctl" and c[1] != "show")]

    def install(self):
        d.install(self.payload, "a" * 40, "inactive")

    def test_create_owned_and_uninstall_preserves_metadata_contents_and_foreign_rule(self):
        self.install()
        record = d.inspect_owned()["material_selinux"]
        self.assertTrue(record["owned"])
        self.assertEqual(record["phase"], "ready")
        self.assertEqual(self.contexts, [d.MATERIAL_CONTEXT] * 6)
        self.assertEqual(self.snapshot(), self.before)
        d.uninstall()
        self.assertEqual(self.rules, [self.foreign_rule])
        self.assertEqual(self.contexts, [DEFAULT] * 6)
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse(self.runtime.exists())

    def test_preexisting_compatible_rule_never_owned_or_deleted(self):
        self.rules.append(self.exact())
        self.install()
        self.assertFalse(d.inspect_owned()["material_selinux"]["owned"])
        d.uninstall()
        self.assertIn(self.exact(), self.rules)
        self.assertEqual(self.contexts, [d.MATERIAL_CONTEXT] * 6)
        self.assertFalse(any(c[:3] == ("semanage", "fcontext", "-d") for c in self.calls))
        self.assertEqual(self.snapshot(), self.before)

    def test_conflicting_rules_rejected_before_any_mutation(self):
        for row in (self.exact(DEFAULT), self.exact(kind="regular file"),
                    str(self.material.parent) + "(/.*)? all files " + DEFAULT,
                    str(self.material / "gfusb.dll") + " regular file " + DEFAULT,
                    str(self.material) + " = /var/lib/foreign",
                    "/unlikely|" + str(self.material) + " all files " + DEFAULT,
                    "unparseable output"):
            with self.subTest(row=row):
                self.rules = [self.foreign_rule, row]
                self.calls.clear()
                with self.assertRaisesRegex(RuntimeError, "conflict|cover|unrecognized"):
                    self.install()
                self.assertFalse(self.mutations())
                self.assertFalse(self.runtime.exists())
                self.assertIn(row, self.rules)

    def test_context_drift_or_rule_drift_preserves_entire_install(self):
        self.install()
        state = (self.runtime / d.STATE).read_bytes()
        for variant in ("label", "rule", "missing", "cover"):
            with self.subTest(variant=variant):
                self.contexts = [d.MATERIAL_CONTEXT] * 6
                self.rules = [self.foreign_rule, self.exact()]
                if variant == "label": self.contexts[2] = "system_u:object_r:etc_t:s0"
                if variant == "rule": self.rules[1] = self.exact(DEFAULT)
                if variant == "missing": self.rules.pop()
                if variant == "cover": self.rules.append("/.* all files " + DEFAULT)
                self.calls.clear()
                with self.assertRaisesRegex(RuntimeError, "drift|conflict"):
                    d.uninstall()
                self.assertFalse(self.mutations())
                self.assertTrue(self.dropin.exists())
                self.assertEqual((self.runtime / d.STATE).read_bytes(), state)

    def test_failed_effective_type_verification_rolls_back_fresh_install(self):
        self.bad_restore = True
        with self.assertRaisesRegex(RuntimeError, "effective material"):
            self.install()
        self.assertFalse(self.runtime.exists())
        self.assertEqual(self.contexts, [DEFAULT] * 6)
        self.assertEqual(self.rules, [self.foreign_rule])
        self.assertEqual(self.snapshot(), self.before)

    def test_missing_tool_enforcement_and_bad_metadata_stop_without_mutation(self):
        with patch.object(d.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "missing semanage"):
                self.install()
        self.assertFalse(self.mutations())
        p = self.material / d.MATERIAL_NAMES[0]
        p.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "metadata mismatch"):
            self.install()
        self.assertFalse(self.mutations())
        p.chmod(0o600)
        original = d.run
        with patch.object(d, "run", side_effect=lambda *a: "Permissive" if a == ("getenforce",) else original(*a)):
            with self.assertRaisesRegex(RuntimeError, "Enforcing"):
                self.install()
        self.assertFalse(self.mutations())

    def test_material_links_and_extra_entries_rejected(self):
        p = self.material / d.MATERIAL_NAMES[-1]
        content = p.read_bytes()
        p.unlink()
        p.symlink_to(self.material / d.MATERIAL_NAMES[0])
        with self.assertRaisesRegex(RuntimeError, "metadata mismatch"):
            self.install()
        p.unlink()
        p.write_bytes(content)
        p.chmod(0o600)
        foreign = self.material / "foreign"
        foreign.write_bytes(b"foreign")
        with self.assertRaisesRegex(RuntimeError, "unexpected material"):
            self.install()
        self.assertFalse(self.mutations())

    def test_wrong_owner_and_hardlink_rejected_without_mutation(self):
        original = Path.lstat
        def wrong_owner(path, *args, **kwargs):
            st = original(path, *args, **kwargs)
            if path == self.material:
                st.st_uid = 1000
            return st
        with patch.object(Path, "lstat", wrong_owner):
            with self.assertRaisesRegex(RuntimeError, "metadata mismatch"):
                self.install()
        os.link(self.material / d.MATERIAL_NAMES[0], self.base / "outside-link")
        with self.assertRaisesRegex(RuntimeError, "hard link"):
            self.install()
        self.assertFalse(self.mutations())

    def test_material_contents_are_never_opened_by_deployment(self):
        original = d.read_regular
        def checked_read(path, *args):
            self.assertNotEqual(path.parent, self.material)
            self.assertNotEqual(path, self.material)
            return original(path, *args)
        with patch.object(d, "read_regular", checked_read):
            self.install()
            d.uninstall()
        self.assertEqual(self.snapshot(), self.before)

    def test_idempotent_install_checks_labels_and_preserves_ownership(self):
        self.install()
        state = (self.runtime / d.STATE).read_bytes()
        self.calls.clear()
        self.install()
        self.assertFalse(self.mutations())
        self.assertEqual((self.runtime / d.STATE).read_bytes(), state)
        self.contexts[0] = DEFAULT
        with self.assertRaisesRegex(RuntimeError, "context drift"):
            self.install()

    def test_saved_inverse_with_owned_mapping_needs_no_git_or_build(self):
        self.install()
        saved_spec = importlib.util.spec_from_file_location("r3_saved", self.runtime / "deploy.py")
        saved = importlib.util.module_from_spec(saved_spec)
        with patch("sys.dont_write_bytecode", True): saved_spec.loader.exec_module(saved)
        for name in ("RUNTIME", "DROPIN", "MATERIAL", "MATERIAL_RULE", "safe_directory", "no_sensor", "run"):
            self.patch(saved, name, getattr(d, name))
        self.patch(saved, "REPO", self.base / "nonexistent")
        self.patch(saved, "git", lambda *a: self.failTest("saved inverse used Git"))
        self.patch(saved, "load_payload", lambda *a: self.failTest("saved inverse used build"))
        saved.uninstall()
        self.assertFalse(self.runtime.exists())
        self.assertEqual(self.contexts, [DEFAULT] * 6)

    def legacy(self):
        # Model the already-qualified installation, without new labels.
        with patch.object(d, "material_plan"), patch.object(d, "apply_material"):
            self.install()
        state = d.inspect_owned()
        state["install_commit"] = d.LEGACY_INSTALL
        old = b"synthetic prior saved inverse"
        (self.runtime / "deploy.py").write_bytes(old)
        state["files"]["deploy.py"] = d.digest(old)
        self.patch(d, "LEGACY_INVERSE_DIGEST", d.digest(old))
        d.save_state(state)
        self.calls.clear()
        return {name: (self.runtime / name).read_bytes() for name in d.LIBRARIES}

    def test_label_existing_replaces_only_inverse_state_and_labels_and_rolls_back_labels_only(self):
        binaries = self.legacy()
        d.label_existing()
        state = d.inspect_owned()
        self.assertEqual(state["install_commit"], d.LEGACY_INSTALL)
        self.assertEqual(state["build_commit"], d.BUILD_COMMIT)
        self.assertEqual(state["material_label_commit"], "a" * 40)
        self.assertEqual((self.runtime / "deploy.py").read_bytes(), self.payload["deploy.py"])
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            d.label_existing()  # No duplicate acquisition of ownership or rule.
        self.assertIn("ALREADY_APPLIED OWNED=true LABEL_COMMIT=" + "a" * 40, output.getvalue())
        d.remove_material(d.inspect_owned())
        d.remove_material(d.inspect_owned())
        self.assertTrue(self.dropin.exists())
        self.assertEqual(self.contexts, [DEFAULT] * 6)
        self.assertEqual(binaries, {n: (self.runtime / n).read_bytes() for n in d.LIBRARIES})
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse(any(c[0] == "systemctl" and c[1] != "show" for c in self.calls))

    def test_existing_conflict_unknown_inverse_and_active_service_leave_install_untouched(self):
        self.legacy()
        before = (self.runtime / d.STATE).read_bytes()
        with patch.object(d, "LEGACY_INVERSE_DIGEST", "0" * 64):
            with self.assertRaisesRegex(RuntimeError, "unknown saved inverse"):
                d.label_existing()
        with patch.object(d, "property_value", return_value="active"):
            with self.assertRaisesRegex(RuntimeError, "inactive/MainPID"):
                d.label_existing()
        self.rules.append(self.exact(DEFAULT))
        with self.assertRaisesRegex(RuntimeError, "conflicting"):
            d.label_existing()
        self.assertEqual((self.runtime / d.STATE).read_bytes(), before)
        self.assertFalse(self.mutations())

    def test_failed_label_existing_keeps_inverse_for_label_only_rollback(self):
        self.legacy()
        self.bad_restore = True
        with self.assertRaisesRegex(RuntimeError, "effective material"):
            d.label_existing()
        self.assertEqual(d.inspect_owned()["material_selinux"]["phase"], "apply")
        self.bad_restore = False
        d.remove_material(d.inspect_owned())
        self.assertEqual(self.contexts, [DEFAULT] * 6)
        self.assertTrue(self.dropin.exists())

    def test_preexisting_rule_partial_label_rollback_preserves_rule(self):
        self.legacy()
        self.rules.append(self.exact())
        self.bad_restore = True
        with self.assertRaisesRegex(RuntimeError, "effective material"):
            d.label_existing()
        self.bad_restore = False
        d.remove_material(d.inspect_owned())
        self.assertIn(self.exact(), self.rules)
        self.assertEqual(self.contexts, [d.MATERIAL_CONTEXT] * 6)
        self.assertFalse(any(c[:3] == ("semanage", "fcontext", "-d") for c in self.calls))
        self.assertTrue(self.dropin.exists())

    def test_metadata_publication_failure_restores_legacy_inverse_before_labeling(self):
        self.legacy()
        old = (self.runtime / "deploy.py").read_bytes()
        old_state = (self.runtime / d.STATE).read_bytes()
        original = d.atomic_file
        once = True
        def fail_state(path, data, mode):
            nonlocal once
            if once and path == self.runtime / d.STATE:
                once = False
                raise OSError("synthetic state publication failure")
            return original(path, data, mode)
        with patch.object(d, "atomic_file", fail_state):
            with self.assertRaisesRegex(OSError, "publication failure"):
                d.label_existing()
        self.assertEqual((self.runtime / "deploy.py").read_bytes(), old)
        self.assertEqual((self.runtime / d.STATE).read_bytes(), old_state)
        self.assertFalse(self.mutations())

    def test_owned_metadata_inconsistent_or_material_drift_blocks_uninstall(self):
        self.install()
        state = d.inspect_owned()
        state["material_selinux"]["owned"] = False
        d.save_state(state)
        self.calls.clear()
        with self.assertRaisesRegex(RuntimeError, "inconsistent material ownership"):
            d.uninstall()
        self.assertFalse(self.mutations())
        state["material_selinux"]["owned"] = True
        d.save_state(state)
        (self.material / d.MATERIAL_NAMES[0]).write_bytes(b"externally replaced sentinel")
        with self.assertRaisesRegex(RuntimeError, "metadata drift"):
            d.uninstall()
        self.assertFalse(self.mutations())
        self.assertTrue(self.dropin.exists())

    def test_failed_creation_is_ambiguous_and_never_deleted_automatically(self):
        self.legacy()
        self.fail = ("semanage", "fcontext", "-a", "-f", "a", "-t", "fprintd_var_lib_t", "-r", "s0", self.rule)
        with self.assertRaisesRegex(RuntimeError, "injected"):
            d.label_existing()
        self.rules.append(self.exact())  # Concurrent foreign creation cannot be adopted.
        self.calls.clear()
        with self.assertRaisesRegex(RuntimeError, "uncertain mapping creation"):
            d.remove_material(d.inspect_owned())
        self.assertFalse(self.mutations())
        self.assertFalse(d.inspect_owned()["material_selinux"]["owned"])

    def test_failed_removal_retains_inverse_and_finishes_relabel_on_retry(self):
        self.install()
        self.fail = ("restorecon", "-F", "--", *(str(p) for p in d.material_paths()))
        with self.assertRaisesRegex(RuntimeError, "injected"):
            d.uninstall()
        self.assertTrue(self.runtime.exists())
        self.assertTrue(self.dropin.exists())
        self.assertEqual(d.inspect_owned()["material_selinux"]["phase"], "removing")
        d.uninstall()
        self.assertFalse(self.runtime.exists())
        self.assertEqual(self.contexts, [DEFAULT] * 6)

    def test_prohibited_tools_and_material_content_reads_absent(self):
        self.install()
        d.uninstall()
        self.assertTrue(all(c[0] in ("getenforce", "semanage", "restorecon", "systemctl", "matchpathcon")
                            for c in self.calls))
        source = (HERE / "deploy.py").read_text()
        for token in ("audit2allow", "semodule", "chcon", "setenforce"):
            self.assertNotIn(token, source)
        self.assertEqual(self.snapshot(), self.before)


if __name__ == "__main__":
    unittest.main()
