#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Local host-file transaction tests, in a temporary tree only."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
import json
import subprocess
import stat
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
        d.p(d.sudo.PAM).write_bytes(d.sudo.VENDOR)
        d.p(d.sudo.LOGIN).write_bytes(d.sudo.LOGIN_VENDOR)
        d.p('/etc/passwd').write_text('root:x:0:0:root:/root:/bin/bash\nguido:x:1000:1000::/home/guido:/bin/bash\n')
        d.p("/etc/sudoers.offline.json").write_text("{}")
        self.module = self.root / "candidate.so"
        self.module.write_bytes(b"\x7fELFoffline-only-fixture")
        (self.root / "PROVENANCE").write_text("SOURCE_COMMIT=" + "a" * 40 + "\nPURPOSE=POLKIT_INTERRUPTIBLE_SERVICE_LOCAL_V1\n")

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self):
        result={}
        for p in self.root.rglob('*'):
            info=p.lstat()
            if stat.S_ISDIR(info.st_mode): continue
            data=p.read_bytes() if stat.S_ISREG(info.st_mode) else os.readlink(p) if p.is_symlink() else None
            result[str(p.relative_to(self.root))]=(data,info.st_mode,info.st_nlink,info.st_uid,info.st_gid)
        return result

    def counter(self, contents=b'0'):
        path=d.p(d.GUARD)/'1000'
        path.write_bytes(contents); path.chmod(0o600)
        return path

    def test_every_bad_runtime_entry_stops_before_mutation(self):
        d.install('managed')
        for kind in ('mode','symlink','hardlink','fifo','content','size','unexpected-counter','extra-entry','xattr'):
            with self.subTest(kind=kind):
                counter=d.p(d.GUARD)/'1000'
                if kind=='fifo': os.mkfifo(counter,0o600)
                elif kind=='symlink': counter.symlink_to(self.module)
                else: self.counter(b'4' if kind=='content' else b'00' if kind=='size' else b'0')
                extra=None
                if kind=='mode': counter.chmod(0o644)
                if kind=='hardlink': extra=self.root/'hardlink'; os.link(counter,extra)
                if kind in ('unexpected-counter','extra-entry'):
                    extra=d.p(d.GUARD)/('1001' if kind=='unexpected-counter' else 'foreign')
                    extra.write_bytes(b'0');extra.chmod(0o600)
                if kind=='xattr': os.setxattr(counter,'user.foreign',b'1')
                before=self.snapshot()
                with patch.object(d,'run') as actions, self.assertRaises((RuntimeError,OSError)):
                    d.uninstall('managed')
                actions.assert_not_called();self.assertEqual(before,self.snapshot())
                counter.unlink()
                if extra is not None: extra.unlink()

    def virtual_root_metadata(self, counter_uid=0, counter_gid=0):
        original_stat,original_fstat=os.stat,os.fstat
        def convert(info):
            values=list(info);values[4]=0;values[5]=0
            if info.st_ino==self.counter_inode:
                values[4]=counter_uid;values[5]=counter_gid
            return os.stat_result(values)
        return (patch.object(d,'guard_owners',return_value=(0,0)),
                patch.object(os,'stat',side_effect=lambda *a,**k:convert(original_stat(*a,**k))),
                patch.object(os,'fstat',side_effect=lambda *a,**k:convert(original_fstat(*a,**k))))

    def test_foreign_uid_gid_and_unpinned_legacy_stop_before_mutation(self):
        d.install('managed');counter=self.counter();self.counter_inode=counter.stat().st_ino
        for uid,gid in ((1,0),(0,10),(0,1000)):
            before=self.snapshot();owners,pathstat,fdstat=self.virtual_root_metadata(uid,gid)
            with owners,pathstat,fdstat,patch.object(d,'run') as actions,self.assertRaises(RuntimeError):
                d.uninstall('managed')
            actions.assert_not_called();self.assertEqual(before,self.snapshot())

    def test_authentic_d7_runtime_allows_only_exact_primary_group(self):
        candidate=os.environ.get('GOODIX_HISTORICAL_POLKIT_MODULE')
        if not candidate: self.skipTest('historical d7 module required')
        self.module.write_bytes(Path(candidate).read_bytes())
        self.assertEqual(d.digest(self.module.read_bytes()),d.HISTORICAL_MODULE)
        d.install('local',self.module);counter=self.counter();self.counter_inode=counter.stat().st_ino
        owners,pathstat,fdstat=self.virtual_root_metadata(0,1000)
        with owners,pathstat,fdstat:
            with self.assertRaisesRegex(RuntimeError,'counter group drift'):
                d.verify('local')
            d.uninstall('local')
        self.assertFalse(d.p(d.STATE).exists());self.assertFalse(d.p(d.PAM).exists())

    def test_production_runtime_virtual_setuid_counter_then_uninstall(self):
        headers=os.environ.get('GOODIX_PAM_TEST_HEADERS')
        if not headers: self.skipTest('PAM headers required')
        binary=self.root/'guard-test'
        subprocess.run(['gcc','-Wall','-Wextra','-Werror','-O2','-I'+headers,
            str(HERE/'test_guard.c'),'/usr/lib64/libpam.so.0',
            '-Wl,--wrap=open,--wrap=fstat,--wrap=fchown,--wrap=pam_set_data','-o',str(binary)],check=True)
        d.install('managed')
        result=subprocess.run([str(binary),str(d.p(d.GUARD)),'pass'],check=True,capture_output=True,text=True)
        self.assertIn('COUNTER_GID=0',result.stdout)
        self.assertEqual((d.p(d.GUARD)/'1000').read_bytes(),b'0')
        d.uninstall('managed');self.assertFalse(d.p(d.STATE).exists())
        guard=self.root/'failure-guard';guard.mkdir(mode=0o700)
        subprocess.run([str(binary),str(guard),'fail'],check=True)
        self.assertFalse((guard/'1000').exists())

    def test_all_state_and_temporary_collisions_precede_mutation(self):
        d.install('managed')
        for name in (d.STATE+'/foreign', d.PAM+'.goodix-next', d.sudo.PAM+'.goodix-next'):
            path=d.p(name);path.write_bytes(b'preserve');before=self.snapshot()
            with self.assertRaises(RuntimeError): d.uninstall('managed')
            self.assertEqual(before,self.snapshot());path.unlink()

    def test_handled_io_failure_restores_candidate_including_runtime_counter(self):
        d.install('managed');self.counter(b'2')
        for stage in ('reload','unlink','final-directory'):
            before=self.snapshot();failed=False
            original_unlink,original_rmdir=Path.unlink,Path.rmdir
            def maybe_fail(kind):
                nonlocal failed
                if kind==stage and not failed:
                    failed=True;raise OSError('injected removal I/O failure')
            def unlink(path,*args,**kwargs):
                if path==d.p(d.LEAF): maybe_fail('unlink')
                return original_unlink(path,*args,**kwargs)
            def rmdir(path,*args,**kwargs):
                if path==d.p(d.STATE): maybe_fail('final-directory')
                return original_rmdir(path,*args,**kwargs)
            def run(*args):
                if args[0]=='systemctl': maybe_fail('reload')
            with self.subTest(stage=stage),patch.object(Path,'unlink',unlink),patch.object(Path,'rmdir',rmdir),\
                 patch.object(d,'run',run),self.assertRaisesRegex(OSError,'injected'):
                d.uninstall('managed')
            self.assertTrue(failed);self.assertEqual(before,self.snapshot())
            d.verify('managed')
        d.uninstall('managed')

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

    def test_interrupted_uninstall_missing_parent_resumes(self):
        before = self.snapshot()
        d.install("local", self.module)
        d.p(d.LOCAL).unlink()
        d.p(d.LOCAL).parent.rmdir()
        d.uninstall("local")
        self.assertEqual(before, self.snapshot())

    def test_combined_second_service_failure_restores_both(self):
        before = self.snapshot()
        original = d.atomic
        def fail(name, data, *args):
            if name == d.PAM and data != d.VENDOR_BYTES:
                raise RuntimeError("injected final Polkit enable failure")
            return original(name, data, *args)
        with patch.object(d, "atomic", side_effect=fail):
            with self.assertRaises(RuntimeError): d.install("managed")
        self.assertEqual(before, self.snapshot())

    def test_missing_owned_file_with_symlink_parent_is_not_recovery(self):
        d.install("local", self.module)
        d.p(d.LOCAL).unlink()
        d.p(d.LOCAL).parent.rmdir()
        outside = self.root / "unowned"
        outside.mkdir()
        d.p(d.LOCAL).parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(RuntimeError): d.uninstall("local")
        self.assertTrue(d.p(d.PAM).exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_sudo_selectors_custom_pam_login_and_rpmnew_refused(self):
        cases = ((d.sudo.PAM, b"custom"), (d.sudo.LOGIN, b"custom"),
                 (d.sudo.PAM + ".rpmnew", b"new"),
                 ("/etc/sudoers.offline.json", b'{"Defaults":[{"Binding":[{"username":"anyone"}],"Options":[{"pam_service":"goodix-d285-01-sudo"}]}]}'))
        for name, contents in cases:
            path = d.p(name); old = path.read_bytes() if path.exists() else None
            path.write_bytes(contents)
            before = self.snapshot()
            with self.assertRaises(RuntimeError): d.install("managed")
            self.assertEqual(before, self.snapshot())
            if old is None: path.unlink()
            else: path.write_bytes(old)

    def test_real_sudoers_parser_expands_scoped_includes(self):
        included = self.root / "included-sudoers"
        policy = self.root / "sudoers-fixture"
        policy.write_text(f"@include {included}\nALL ALL=(ALL) ALL\n")
        for option in ("pam_service", "pam_login_service", "pam_askpass_service"):
            included.write_text(f'Defaults:offline_user {option}="custom"\n')
            parsed = json.loads(subprocess.check_output(
                ["/usr/bin/cvtsudoers", "-c", "/dev/null", "-f", "json", str(policy)]))
            with self.assertRaises(RuntimeError): d.sudo.selectors(parsed)

    def test_nss_local_boundary_case_spacing_and_continuation(self):
        for text in ("hosts: files dns\n", "sudoers:files\n", " SUDOERS: FILES # local\n"):
            self.assertTrue(d.sudo.local_nss(text))
        for text in ("sudoers:files sss\n", "SUDOERS:ldap\n", "sudoers:\n",
                     "sudoers:files\nsudoers:files\n", "sudoers\\\n: sss\n"):
            self.assertFalse(d.sudo.local_nss(text))

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
