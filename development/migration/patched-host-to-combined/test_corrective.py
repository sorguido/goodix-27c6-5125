# SPDX-License-Identifier: GPL-2.0-or-later
"""Actual RPM verifier + restored-attempt lifecycle, entirely as uid 1000."""
import copy
import grp
import importlib.util
import json
import os
from pathlib import Path
import pwd
import subprocess
import tempfile
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('fixtures',HERE/'test_migration.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
m=t.m


class CorrectiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): t.MigrationTests.setUpClass()
    @classmethod
    def tearDownClass(cls): t.MigrationTests.tearDownClass()
    def setUp(self):
        self.f=t.MigrationTests();self.f.setUp()
        self.tx=self.f.tx
    def tearDown(self): self.f.tearDown()
    def restored(self): self.tx.apply(t.POLICY);self.tx.rollback()

    def test_package_postimage_and_nanosecond_rollback(self):
        times={p:self.f.path(p).stat().st_mtime_ns for p in m.ORDER}
        self.tx.apply(t.POLICY)
        self.tx.package_compatible(self.tx.state())
        for p in m.VENDOR:
            self.assertEqual(self.f.path(p).stat().st_mtime_ns,1788825600000000000)
        self.tx.rollback();self.f.assert_restored()
        self.assertEqual(times,{p:self.f.path(p).stat().st_mtime_ns for p in m.ORDER})

    def test_mtime_and_other_attributes_drift_block_release_while_masked(self):
        self.tx.apply(t.POLICY)
        p=self.f.path('/usr/lib/pam.d/plasmalogin'); original=p.read_bytes();old=p.stat()
        for kind in ('mtime','mode','content','size','xattr'):
            if kind=='mtime': os.utime(p,ns=(old.st_atime_ns,old.st_mtime_ns+1000000000))
            elif kind=='mode': p.chmod(0o600)
            elif kind=='content': p.write_bytes(original.replace(b'auth',b'xxxx',1))
            elif kind=='size': p.write_bytes(original+b'\n')
            else: os.setxattr(p,'user.foreign',b'drift')
            with self.subTest(kind=kind),self.assertRaises(RuntimeError): self.tx.release()
            self.assertTrue(self.f.path(m.MASK).is_symlink())
            if kind=='xattr': os.removexattr(p,'user.foreign')
            p.write_bytes(original);p.chmod(0o644);os.utime(p,ns=(old.st_atime_ns,old.st_mtime_ns))
        self.tx.release()

    def test_actual_rpm_verifier_proves_only_mtime_after_old_transform(self):
        import rpm  # Fedora's existing verifier; never changes the RPM database.
        header=next(rpm.TransactionSet().dbMatch('name','plasma-login-manager'))
        row=next(f for f in rpm.files(header) if f.name=='/usr/lib/pam.d/plasmalogin')
        directory=self.f.temp/'rpm-proof';directory.mkdir()
        path=directory/'plasmalogin'
        path.write_bytes(self.tx.converted('/usr/lib/pam.d/plasmalogin',self.f.originals['/usr/lib/pam.d/plasmalogin']))
        path.chmod(0o644)
        clone=rpm.hdr(header.unload())
        # Path and test uid/gid only. Every other RPM attribute remains original.
        for key,values in ((rpm.RPMTAG_DIRNAMES,[str(directory)+'/' for _ in header[rpm.RPMTAG_DIRNAMES]]),
                           (rpm.RPMTAG_FILEUSERNAME,[pwd.getpwuid(os.geteuid()).pw_name for _ in header[rpm.RPMTAG_FILEUSERNAME]]),
                           (rpm.RPMTAG_FILEGROUPNAME,[grp.getgrgid(os.getegid()).gr_name for _ in header[rpm.RPMTAG_FILEGROUPNAME]])):
            del clone[key];clone[key]=values
        file=next(f for f in rpm.files(clone) if f.basename=='plasmalogin' and f.size==1010)
        self.assertEqual(file.verify(),rpm.RPMVERIFY_MTIME)
        os.utime(path,ns=(path.stat().st_atime_ns,row.mtime*1000000000))
        self.assertEqual(file.verify(),0)

    def test_exact_package_metadata_contract_refuses_every_changed_attribute(self):
        contract=self.f.plan['packages'];host=m.Host()
        for path,row in contract.items():
            with mock.patch.object(host,'run',side_effect=[row['package'],'\t'.join(row['rpm'])]):
                m.package_baseline.qualify(host,{path:row})
            for i in range(10):
                altered=list(row['rpm']);altered[i]+='drift'
                with mock.patch.object(host,'run',side_effect=[row['package'],'\t'.join(altered)]),self.assertRaises(RuntimeError):
                    m.package_baseline.qualify(host,{path:row})

    def test_restored_short_recovery_rearm_preflight_second_apply(self):
        self.restored();old=self.f.path(m.BACKUP+'/state.json').read_bytes()
        self.assertEqual(self.tx.preflight(),'PREFLIGHT_PASS_REARM_REQUIRED')
        self.assertEqual(self.f.path(m.recovery.SHORT).read_bytes(),m.recovery.SHORT_BYTES)
        with self.assertRaisesRegex(RuntimeError,'requires_rearm'): self.tx.apply(t.POLICY)
        self.assertTrue(self.tx.rearm(t.POLICY).startswith('REARMED_'))
        archive=m.BACKUP+'.restored-'+m.digest(old)
        self.assertEqual(self.f.path(archive+'/state.json').read_bytes(),old)
        self.assertEqual(self.tx.rearm(t.POLICY),'ALREADY_REARMED')
        self.assertEqual(self.tx.preflight(),'PREFLIGHT_PASS_NO_CONFIGURATION_CHANGE')
        self.assertEqual(self.tx.apply(t.POLICY),'APPLIED_RUNTIME_MASKED')
        self.tx.rollback();self.f.assert_restored()
        self.assertEqual(self.f.path(archive+'/state.json').read_bytes(),old)

    def test_modified_short_and_foreign_backup_stop_without_rotation(self):
        self.restored()
        for path,content in ((m.recovery.SHORT,b'foreign'),(m.BACKUP+'/migration.py',b'foreign'),
                             (m.BACKUP+'/state.json',b'{}')):
            p=self.f.path(path);old=p.read_bytes();p.write_bytes(content)
            with self.subTest(path=path),self.assertRaises((RuntimeError,KeyError)): self.tx.rearm(t.POLICY)
            self.assertEqual(p.read_bytes(),content);p.write_bytes(old)

    def test_rearm_can_be_cancelled_by_saved_rollback_before_second_apply(self):
        self.restored();old=self.f.path(m.BACKUP+'/state.json').read_bytes()
        self.tx.rearm(t.POLICY)
        spec=importlib.util.spec_from_file_location('saved_recovery',self.f.path(m.BACKUP+'/migration.py'))
        saved=importlib.util.module_from_spec(spec);spec.loader.exec_module(saved)
        saved.Migration(self.f.fs,self.f.host,plan=self.f.plan).rollback()
        self.f.assert_restored()
        self.assertEqual(self.tx.preflight(),'PREFLIGHT_PASS_REARM_REQUIRED')
        archive=m.BACKUP+'.restored-'+m.digest(old)
        self.assertEqual(self.f.path(archive+'/state.json').read_bytes(),old)

    def test_restored_baseline_candidate_mask_policy_and_daemon_drift_stop(self):
        self.restored()
        for path in ('/etc/pam.d/polkit-1','/etc/sudoers.d/unknown',m.BACKUP+'/foreign'):
            self.f.put(path,b'foreign',0o600)
            with self.subTest(path=path),self.assertRaises(RuntimeError): self.tx.rearm(t.POLICY)
            self.f.path(path).unlink()
        self.f.path(m.MASK).symlink_to('/dev/null')
        with self.assertRaisesRegex(RuntimeError,'runtime_override'): self.tx.rearm(t.POLICY)
        self.f.path(m.MASK).unlink()
        self.f.host.value='absent'
        with self.assertRaisesRegex(RuntimeError,'legacy_policy'): self.tx.rearm(t.POLICY)
        self.f.host.value='legacy'
        with mock.patch.object(self.f.host,'inactive',return_value=False),self.assertRaisesRegex(RuntimeError,'inactive'):
            self.tx.rearm(t.POLICY)
        p=self.f.path('/usr/lib/pam.d/plasmalogin');p.write_bytes(p.read_bytes()+b'changed')
        with self.assertRaises(RuntimeError): self.tx.rearm(t.POLICY)

    def test_rearm_crash_before_exchange_safe_stop_and_old_recovery_intact(self):
        self.restored();old=self.f.path(m.BACKUP+'/state.json').read_bytes()
        def fail(phase):
            if phase=='rearm_prepared': raise RuntimeError('crash')
        self.tx.checkpoint=fail
        with self.assertRaisesRegex(RuntimeError,'crash'): self.tx.rearm(t.POLICY)
        self.assertEqual(self.f.path(m.BACKUP+'/state.json').read_bytes(),old)
        self.assertEqual(self.tx.rollback(),'ALREADY_RESTORED')
        with self.assertRaisesRegex(RuntimeError,'pending_before_exchange'): self.tx.rearm(t.POLICY)

    def test_rearm_crash_after_exchange_retries_finalize_with_recovery_available(self):
        self.restored()
        def fail(phase):
            if phase=='rearm_exchanged': raise RuntimeError('crash')
        self.tx.checkpoint=fail
        with self.assertRaisesRegex(RuntimeError,'crash'): self.tx.rearm(t.POLICY)
        self.assertEqual(self.tx.state()['status'],'PREPARED')
        with self.assertRaisesRegex(RuntimeError,'finalize'): self.tx.apply(t.POLICY)
        self.tx.checkpoint=lambda phase:None
        self.assertEqual(self.tx.rearm(t.POLICY),'ALREADY_REARMED')
        self.tx.apply(t.POLICY);self.tx.rollback();self.f.assert_restored()

    legacy_index=0

    def test_historical_d7_snapshot_import_is_pinned_and_preserved(self):
        self.legacy_index=1
        self.test_historical_f97_snapshot_import_is_pinned_and_preserved()

    def test_historical_f97_snapshot_import_is_pinned_and_preserved(self):
        repo=self.f.temp/'old-repo';base=repo/'development/migration/patched-host-to-combined'
        base.mkdir(parents=True)
        pins=json.loads((HERE/'legacy-recovery.json').read_text())['revisions'][self.legacy_index];rev=pins['source_commit']
        for name in pins['source']:
            (base/name).write_bytes(subprocess.check_output(['git','-C',str(t.REPO),'show',rev+':development/migration/patched-host-to-combined/'+name]))
        for name in m.recovery.PATHS:
            p=repo/name;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(subprocess.check_output(['git','-C',str(t.REPO),'show',rev+':'+name]))
        spec=importlib.util.spec_from_file_location('old_migration',base/'migration.py')
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        previous=old.Migration(self.f.fs,self.f.host,plan=self.f.plan)
        previous.apply(t.POLICY);previous.rollback()
        before=self.f.path(m.BACKUP+'/state.json').read_bytes()
        self.assertEqual(self.tx.preflight(),'PREFLIGHT_PASS_REARM_REQUIRED')
        self.tx.rearm(t.POLICY)
        archive=m.BACKUP+'.restored-'+m.digest(before)
        self.assertEqual(self.f.path(archive+'/state.json').read_bytes(),before)
        self.tx.apply(t.POLICY);self.tx.rollback();self.f.assert_restored()

    def test_launcher_candidate_failure_automatic_rollback_rearm_second_apply(self):
        candidate=os.environ.get('GOODIX_MIGRATION_TEST_CANDIDATE')
        if not candidate: self.skipTest('prepared candidate required')
        spec=importlib.util.spec_from_file_location('launcher',HERE/'launcher.py')
        launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
        self.f.put('/etc/pam.d/system-auth',self.f.path('/etc/authselect/system-auth').read_bytes())
        self.f.put('/usr/lib/systemd/user/plasma-login.service',b'[Service]\nExecStart=/usr/libexec/plasma-login-greeter\n')
        self.f.put('/etc/sudoers.offline.json',b'{}')
        self.f.host.run=t.FakeHost.run
        env=os.environ|{'GOODIX_MANAGED_TEST_ROOT':str(self.f.root),
                        'GOODIX_MANAGED_TEST_FAIL_AFTER_POLICY':'true',
                        'GOODIX_MANAGED_TEST_KDE_VENDOR_SHA256':m.VENDOR['/etc/pam.d/kde-fingerprint'][2]}
        def invoke(command):
            if command[0]=='/usr/bin/setpriv': return
            subprocess.run(command,env=env,cwd='/tmp',check=True,capture_output=True)
        self.tx.recovery_restore=lambda call:m.recovery.restore(self.tx,call)
        with mock.patch.object(launcher,'POLICY',t.POLICY),mock.patch.object(launcher,'CANDIDATE',Path(candidate)):
            with self.assertRaises(subprocess.CalledProcessError):
                launcher.run_flow(self.tx,invoke,lambda prompt:'',lambda:None)
        self.f.assert_restored()
        self.assertEqual(self.tx.state()['status'],'RESTORED')
        self.assertEqual(self.tx.preflight(),'PREFLIGHT_PASS_REARM_REQUIRED')
        self.tx.rearm(t.POLICY)
        self.assertEqual(self.tx.preflight(),'PREFLIGHT_PASS_NO_CONFIGURATION_CHANGE')
        self.tx.apply(t.POLICY);self.tx.rollback();self.f.assert_restored()

    def test_package_verifier_failure_before_release_recovers_and_foreign_archive_stops(self):
        with mock.patch.object(self.f.host,'packages',side_effect=lambda contract,postimage=False:
                               (_ for _ in ()).throw(RuntimeError('rpm_failure')) if postimage else None):
            with self.assertRaisesRegex(RuntimeError,'rpm_failure'): self.tx.apply(t.POLICY)
        self.f.assert_restored()
        old=self.f.path(m.BACKUP+'/state.json').read_bytes()
        archive=m.BACKUP+'.restored-'+m.digest(old)
        self.f.path(archive).mkdir(mode=0o700)
        with self.assertRaisesRegex(RuntimeError,'archive_collision'): self.tx.rearm(t.POLICY)
        self.assertEqual(self.f.path(m.BACKUP+'/state.json').read_bytes(),old)


if __name__=='__main__': unittest.main()
