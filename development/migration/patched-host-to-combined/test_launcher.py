#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent

def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

l=load('launcher')
tests=load('test_migration')

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=Path(tempfile.mkdtemp(prefix='goodix-launcher-test.',dir='/tmp'))
        self.repo=self.temp/'repo'; self.repo.mkdir()
        subprocess.run(['git','init','-q','-b','development',str(self.repo)],check=True)
        for folder in l.FOLDERS:
            path=self.repo/folder; path.mkdir(parents=True); (path/'file').write_bytes(b'source')
        subprocess.run(['git','-C',str(self.repo),'add','.'],check=True)
        subprocess.run(['git','-C',str(self.repo),'-c','user.name=Offline Test','-c','user.email=test@example.invalid',
                        'commit','-qm','fixture'],check=True)
        self.head=l.git(self.repo,'rev-parse','HEAD')
        self.candidate=self.temp/'candidate'; self.candidate.mkdir()
        for n in range(35): (self.candidate/str(n)).write_bytes(b'synthetic')
        (self.candidate/'MANIFEST').write_text('SOURCE_COMMIT='+self.head+'\nSUDO_INTEGRATION=PASSWORD_FIRST_SERVICE_LOCAL_V1\n'
                'POLKIT_INTEGRATION=INTERRUPTIBLE_SERVICE_LOCAL_V1\nPROTECTED_MATERIAL_INCLUDED=false\n')
        self.policy=self.temp/'policy.pp'; self.policy.write_bytes(b'synthetic policy')
        paths=set(self.candidate.iterdir())|{self.policy}
        paths.update(self.repo/name for name in l.git(self.repo,'ls-files').splitlines())
        self.receipt=self.temp/'receipt'
        self.receipt.write_text(''.join(l.sha(p.read_bytes())+'  '+str(p)+'\n' for p in sorted(paths)))
    def tearDown(self): shutil.rmtree(self.temp)
    def check(self): return l.delivery(self.repo,self.candidate,self.policy,self.receipt)
    def test_delivery_head_and_exact_receipt_pass(self): self.assertEqual(self.check(),self.head)
    def test_dirty_checkout_stops(self):
        (self.repo/'untracked').write_text('changed')
        with self.assertRaisesRegex(RuntimeError,'worktree_dirty'): self.check()
    def test_changed_candidate_stops(self):
        (self.candidate/'0').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'digest_drift'): self.check()
    def test_arbitrary_or_duplicate_receipt_path_never_read(self):
        original=self.receipt.read_text()
        for line in ('0'*64+'  /var/lib/fprint/forbidden\n', original.splitlines()[0]+'\n'):
            self.receipt.write_text(original+line)
            with self.assertRaisesRegex(RuntimeError,'receipt_path_set|duplicate_receipt_path'): self.check()
    def test_policy_symlink_stops(self):
        self.policy.unlink(); self.policy.symlink_to('/dev/null')
        with self.assertRaisesRegex(RuntimeError,'missing_or_symlink'): self.check()

class BoundaryTests(unittest.TestCase):
    def test_actual_launcher_from_other_cwd_and_root_guard(self):
        result=subprocess.run([str(HERE/'operator.sh'),'--help'],cwd='/tmp',capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        result=subprocess.run([str(HERE/'operator.sh'),'--root-run'],cwd='/tmp',capture_output=True,text=True,
                              env=os.environ|{'PKEXEC_UID':'1000','GOODIX_MANAGED_TEST_ROOT':'/tmp/not-used'})
        self.assertNotEqual(result.returncode,0)
        self.assertIn('operator_root_boundary',result.stderr)
    def test_failed_pkexec_has_no_retry_or_fallback(self):
        for rc in (1,126,127):
            invoke=mock.Mock(side_effect=subprocess.CalledProcessError(rc,['pkexec']))
            with self.assertRaisesRegex(RuntimeError,'privileged_phase_failed_rc_'+str(rc)): l.elevate('run',invoke)
            self.assertEqual(invoke.call_count,1)
            command=invoke.call_args.args[0]
            self.assertEqual(command[:4],['/usr/bin/pkexec','--disable-internal-agent','--user','root'])
            self.assertEqual(command[-1],'--root-run')
    def test_missing_pkexec_stops(self):
        with self.assertRaises(FileNotFoundError): l.elevate('preflight',mock.Mock(side_effect=FileNotFoundError()))
    def test_password_only_rejects_managed_polkit_before_elevation(self):
        with tempfile.TemporaryDirectory(prefix='goodix-launcher-test.',dir='/tmp') as root:
            root=Path(root); path=root/'etc/pam.d'; path.mkdir(parents=True)
            (path/'polkit-1').write_text('managed')
            with self.assertRaisesRegex(RuntimeError,'polkit_not_password_only'): l.password_only(root)
    def test_main_refuses_changed_pam_before_calling_pkexec(self):
        with mock.patch.object(sys,'argv',['operator.sh','preflight']),mock.patch.object(l,'delivery',return_value='a'*40),\
             mock.patch.object(l,'password_only',side_effect=RuntimeError('changed_pam')),mock.patch.object(l,'elevate') as elevate:
            with self.assertRaisesRegex(RuntimeError,'changed_pam'): l.main()
            elevate.assert_not_called()

class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tx=mock.Mock(); self.tx.host.run.side_effect=['active',
            'argv[]=/usr/bin/openvt -s -w -- /usr/bin/bash --noprofile --norc ;']
        self.tx.apply.return_value='APPLIED_RUNTIME_MASKED'; self.tx.release.return_value='RELEASED'
        self.tx.recovery_restore.return_value='RESTORED'
        self.invoke=mock.Mock(); self.ask=mock.Mock(); self.check=mock.Mock()
    def test_negative_preflight_no_host_mutation(self):
        self.tx.before.side_effect=RuntimeError('fprintd_dropins_drift')
        with self.assertRaises(RuntimeError): l.run_flow(self.tx,self.invoke,self.ask,self.check)
        self.tx.apply.assert_not_called(); self.invoke.assert_not_called(); self.ask.assert_not_called()
    def test_no_console_no_apply(self):
        self.tx.host.run.side_effect=['inactive']
        with self.assertRaisesRegex(RuntimeError,'recovery_console'): l.run_flow(self.tx,self.invoke,self.ask,self.check)
        self.tx.apply.assert_not_called(); self.invoke.assert_not_called()
    def test_phases_password_drop_privilege_then_install_status(self):
        l.run_flow(self.tx,self.invoke,self.ask,self.check)
        calls=[x.args[0] for x in self.invoke.call_args_list]
        self.assertEqual(calls[0],['/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','--','/usr/bin/sudo','-k','/usr/bin/true'])
        self.assertEqual(calls[1][-3:],['--root-install','guido',str(l.CANDIDATE)])
        self.assertEqual(calls[2][-1],'--status'); self.assertEqual(len(calls),3)
        self.assertEqual(self.ask.call_count,2); self.tx.recovery_restore.assert_not_called()
    def test_cancel_before_apply_no_changes(self):
        self.ask.side_effect=KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt): l.run_flow(self.tx,self.invoke,self.ask,self.check)
        self.tx.apply.assert_not_called(); self.tx.recovery_restore.assert_not_called()
    def test_interrupted_apply_or_failed_password_recovers_without_install(self):
        for at in ('apply','password'):
            self.setUp()
            if at=='apply': self.tx.apply.side_effect=KeyboardInterrupt()
            else: self.invoke.side_effect=subprocess.CalledProcessError(1,['sudo'])
            with self.assertRaises((KeyboardInterrupt,subprocess.CalledProcessError)):
                l.run_flow(self.tx,self.invoke,self.ask,self.check)
            self.tx.release.assert_not_called(); self.tx.recovery_restore.assert_called_once_with(self.invoke)
    def test_cancel_after_password_rolls_back(self):
        self.ask.side_effect=['',KeyboardInterrupt()]
        with self.assertRaises(KeyboardInterrupt): l.run_flow(self.tx,self.invoke,self.ask,self.check)
        self.tx.release.assert_not_called(); self.tx.recovery_restore.assert_called_once()
    def test_failed_candidate_status_recovers(self):
        self.invoke.side_effect=[None,None,subprocess.CalledProcessError(1,['status'])]
        with self.assertRaises(subprocess.CalledProcessError): l.run_flow(self.tx,self.invoke,self.ask,self.check)
        self.tx.recovery_restore.assert_called_once()

class SyntheticFlowTests(unittest.TestCase):
    def test_real_transaction_and_saved_recovery_from_unrelated_cwd(self):
        candidate=os.environ.get('GOODIX_MIGRATION_TEST_CANDIDATE')
        if not candidate: self.skipTest('prepared candidate required')
        tests.MigrationTests.setUpClass(); fixture=tests.MigrationTests(); fixture.setUp()
        try:
            fixture.put('/etc/pam.d/system-auth',fixture.path('/etc/authselect/system-auth').read_bytes())
            fixture.put('/usr/lib/systemd/user/plasma-login.service',b'[Service]\nExecStart=/usr/libexec/plasma-login-greeter\n')
            fixture.put('/etc/sudoers.offline.json',b'{}')
            fixture.host.run=lambda *args: ('active' if 'ActiveState' in args else
                'argv[]=/usr/bin/openvt -s -w -- /usr/bin/bash --noprofile --norc ;')
            env=os.environ|{'GOODIX_MANAGED_TEST_ROOT':str(fixture.root),
                'GOODIX_MANAGED_TEST_KDE_VENDOR_SHA256':tests.m.VENDOR['/etc/pam.d/kde-fingerprint'][2]}
            def invoke(command):
                if command[0]=='/usr/bin/setpriv':
                    self.assertTrue(fixture.path(tests.m.MASK).is_symlink())
                    self.assertFalse(fixture.path('/etc/sudoers.d/90-goodix-d285-01').exists())
                    return
                subprocess.run(command,cwd='/tmp',env=env,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            fixture.tx.recovery_restore=lambda call: tests.m.recovery.restore(fixture.tx,call)
            with mock.patch.object(l,'POLICY',tests.POLICY),mock.patch.object(l,'CANDIDATE',Path(candidate)):
                l.run_flow(fixture.tx,invoke,lambda prompt:'',lambda:None)
            self.assertEqual(fixture.path(tests.m.recovery.SHORT).read_bytes(),tests.m.recovery.SHORT_BYTES)
            tests.m.recovery.restore(fixture.tx,invoke)
            fixture.assert_restored()
        finally: fixture.tearDown(); tests.MigrationTests.tearDownClass()

if __name__=='__main__': unittest.main()
