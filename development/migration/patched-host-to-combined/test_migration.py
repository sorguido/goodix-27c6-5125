#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
spec = importlib.util.spec_from_file_location('migration',HERE/'migration.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
LEGACY = REPO/'development/private-root/analysis/D232/D232_target_material_manifest.json'
POLICY = None

class FakeHost:
    def __init__(self,root): self.root=root; self.value='legacy'; self.actions=[]
    def qualify(self): pass
    def packages(self,contract,postimage=False): pass
    def inactive(self): return True
    def reload(self): self.actions.append('reload')
    def stop(self): self.actions.append('stop')
    def policy(self):
        if (self.root/'var/lib/goodix-27c6-5125-managed/policy.test').exists():
            raise RuntimeError('candidate_policy_still_installed')
        return self.value
    def remove_policy(self):
        assert self.value=='legacy'; self.actions.append('remove-policy'); self.value='absent'
    def restore_policy(self,path):
        assert m.digest(path.read_bytes())==m.POLICY_SHA
        self.actions.append('restore-policy'); self.value='legacy'
    @staticmethod
    def run(*args):
        if args[0]=='/usr/bin/rpm': return 'plasma-login-manager-6.7.5-1.fc44.x86_64'
        if args[0]=='/usr/bin/busctl': return 'u 6'
        if args[0]=='/usr/bin/systemd-analyze': return '[Login]\n#ReserveVT=6'
        if args[0]=='/usr/bin/ps': return '500 1 0 0 ? openvt\n501 500 0 0 tty12 bash\n600 1 1000 1000 tty2 plasma'
        if args[0]=='/usr/bin/loginctl': return '15 1000 guido seat0 600 user tty2 no -'
        if args[0]=='/usr/bin/systemctl':
            if 'ExecStart' in args: return 'argv[]=/usr/bin/openvt -c 12 -w -- /usr/bin/bash --noprofile --norc ;'
            if 'MainPID' in args: return '500'
            if 'ActiveState' in args: return 'active' if args[2] in ('goodix-migration-recovery.service','plasmalogin.service') else 'inactive'
        raise AssertionError(args)

class ManifestTests(unittest.TestCase):
    def test_exact_projection_and_independent_historical_pins(self):
        original=LEGACY.read_bytes(); output=m.manifest.convert(original)
        self.assertEqual(output,m.manifest.convert(original))
        value=json.loads(output); old=json.loads(original)
        self.assertEqual(set(value),{'schema','vid','pid','app','transport_sha256','config90_sha256','fdt_cache_sha256','a2_response_sha256','chip82_response_sha256','otp_a6_response_sha256'})
        self.assertEqual(value['schema'],'goodix-5125-device-materials-v1')
        self.assertEqual((value['vid'],value['pid'],value['app']),('27c6','5125','GF_ST411SEC_APP_12509'))
        sources={n:subprocess.check_output(['git','-C',str(REPO),'show',m.manifest.LOADER_COMMIT+':libfprint-driver/'+n],text=True)
                 for n in ('goodix_target_material.c','goodix_runtime_inputs.c')}
        for field,array,file in (
            ('transport_sha256','transport_hash','goodix_target_material.c'),
            ('config90_sha256','config_hash','goodix_target_material.c'),
            ('fdt_cache_sha256','cache_hash','goodix_runtime_inputs.c'),
            ('a2_response_sha256','a2_hash','goodix_target_material.c'),
            ('chip82_response_sha256','chip_hash','goodix_target_material.c'),
            ('otp_a6_response_sha256','otp_hash','goodix_target_material.c')):
            source=re.search(r'\b'+array+r'\[32\] = \{([^}]+)',sources[file]).group(1)
            expected=bytes(int(x,16) for x in re.findall(r'0x([0-9a-f]{2})',source)).hex()
            self.assertEqual(value[field],expected,field)
        self.assertEqual(value['config90_sha256'],old['config90']['body_sha256'])
        self.assertLess(len(output),4096)

    def test_every_other_original_refused(self):
        original=LEGACY.read_bytes()
        for value in [original+b'\n',original.replace(b'12509',b'12508'),b'{}',m.manifest.convert(original),b'',b'x'*2305]:
            with self.subTest(size=len(value)),self.assertRaises(ValueError): m.manifest.convert(value)

class MigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global POLICY
        cls.policy_temp=Path(tempfile.mkdtemp(prefix='goodix-policy-test.',dir='/tmp'))
        directory=cls.policy_temp/'policy'
        subprocess.run(['bash',str(HERE/'prepare-policy.sh'),str(directory)],check=True,stdout=subprocess.PIPE)
        POLICY=directory/'goodix_fprint_account_delete.pp'

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.policy_temp)

    def setUp(self):
        self.temp=Path(tempfile.mkdtemp(prefix='goodix-managed-test.',dir='/tmp'))
        self.root=self.temp/'root'; self.root.mkdir()
        self.plan=json.loads((HERE/'host-plan.json').read_bytes())
        self.preserved_bytes={}
        for p,row in self.plan['guards'].items():
            data=('synthetic software '+p).encode()
            if p in ('/etc/pam.d/sudo','/etc/pam.d/sudo-i','/usr/lib/pam.d/polkit-1','/etc/authselect/system-auth'):
                data=Path(p).read_bytes()  # public software only, no protected data
            self.put(p,data,row['mode']); row['sha256']=m.digest(data)
        for p,row in self.plan['files'].items():
            data=Path(p).read_bytes() if p in m.VENDOR else ('synthetic owned '+p).encode()
            self.put(p,data,row['mode']); row['sha256']=m.digest(data)
        self.put(m.MATERIAL,LEGACY.read_bytes(),0o600)
        self.put('/etc/passwd',b'root:x:0:0:root:/root:/bin/bash\nguido:x:1000:1000::/home/guido:/bin/bash\n')
        for p,row in self.plan['preserve'].items():
            if row['type']==stat.S_IFDIR:
                self.path(p).mkdir(parents=True,exist_ok=True); self.path(p).chmod(int(row['mode'],8))
            else:
                self.put(p,b'SYNTHETIC-NOT-REAL',int(row['mode'],8))
                with self.path(p).open('r+b') as stream: stream.truncate(row['size'])
                os.utime(self.path(p),ns=(row['mtime_ns'],row['mtime_ns']))
                self.preserved_bytes[p]=m.digest(self.path(p).read_bytes())
        self.put('/etc/goodix-27c6-5125/d285-01.state',
                 ''.join(k+'='+v+'\n' for k,v in self.plan['d285_state'].items()).encode(),0o600)
        early='/usr/local/lib64/goodix-27c6-5125/login-early/'
        self.path(early+'libfprint-2.so').symlink_to('libfprint-2.so.2')
        self.path(early+'libfprint-2.so.2').symlink_to('libfprint-2.so.2.0.0')
        self.path('/run/systemd/system').mkdir(parents=True)
        self.fs=m.Files(self.root); self.host=FakeHost(self.root)
        self.tx=m.Migration(self.fs,self.host,plan=self.plan)
        self.originals={p:self.path(p).read_bytes() for p in m.ORDER}
        # Independent sentinel in an opaque archive: migration never opens it.
        self.put('/var/lib/goodix-5125-poc/d236-results/archive/keep',b'opaque archive',0o600)
        self.original_snapshot=self.snapshot()
        self.assertTrue(POLICY.is_file(),'run prepare-policy.sh before this suite')

    def tearDown(self): self.fs.close(); shutil.rmtree(self.temp)
    def path(self,p): return self.root/p.lstrip('/')
    def put(self,p,data,mode=0o644):
        file=self.path(p); file.parent.mkdir(parents=True,exist_ok=True)
        file.write_bytes(data); file.chmod(mode)
    def snapshot(self):
        return {p:(self.path(p).read_bytes(),self.path(p).stat().st_mode&0o7777) for p in m.ORDER}
    def assert_preserved(self):
        for p,h in self.preserved_bytes.items(): self.assertEqual(m.digest(self.path(p).read_bytes()),h,p)
        self.assertEqual(self.path('/var/lib/goodix-5125-poc/d236-results/archive/keep').read_bytes(),b'opaque archive')
    def assert_restored(self):
        self.assertEqual(self.snapshot(),self.original_snapshot)
        self.assertEqual(self.host.value,'legacy'); self.assertFalse(self.path(m.MASK).is_symlink())
        self.assertEqual(self.path(m.BACKUP+'/original-manifest.json').read_bytes(),self.originals[m.MATERIAL])
        self.assert_preserved()

    def test_preflight_read_only_and_no_protected_content_reads(self):
        before={p:p.stat().st_atime_ns for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}
        original_read=self.fs.read
        def read(path,*args,**kwargs):
            self.assertNotIn(path,self.preserved_bytes)
            self.assertNotIn('/archive/',path)
            return original_read(path,*args,**kwargs)
        with mock.patch.object(self.fs,'read',side_effect=read): self.tx.before()
        self.assertFalse(self.path(m.BACKUP).exists()); self.assertEqual(self.host.actions,[])
        for p,t in before.items(): self.assertEqual(p.stat().st_atime_ns,t,p)

    def test_apply_and_rollback_idempotent(self):
        self.assertEqual(self.tx.apply(POLICY),'APPLIED_RUNTIME_MASKED')
        self.assertEqual(self.path(m.MATERIAL).read_bytes(),m.manifest.convert(self.originals[m.MATERIAL]))
        self.assertFalse(self.path('/etc/sudoers.d/90-goodix-d285-01').exists())
        self.assertEqual(self.tx.apply(POLICY),'ALREADY_APPLIED')
        self.assert_preserved()
        self.tx.rollback(); self.assert_restored()
        actions=list(self.host.actions)
        self.assertEqual(self.tx.rollback(),'ALREADY_RESTORED'); self.assertEqual(actions,self.host.actions)

    def test_release_mask_is_explicit_and_idempotent(self):
        self.tx.apply(POLICY)
        self.assertTrue(self.path(m.MASK).is_symlink())
        self.tx.release(); self.tx.release()
        self.assertFalse(self.path(m.MASK).is_symlink())
        self.tx.rollback(); self.assert_restored()

    def test_wrong_manifest_stops_before_snapshot(self):
        self.path(m.MATERIAL).write_bytes(b'x'*2305)
        with self.assertRaisesRegex(RuntimeError,'owned_file_drift'): self.tx.apply(POLICY)
        self.assertFalse(self.path(m.BACKUP).exists()); self.assertEqual(self.host.actions,[])

    def test_wrong_recovery_policy_never_removes_overlay(self):
        policy=self.temp/(m.POLICY+'.pp'); policy.write_bytes(b'x'*2086)
        with self.assertRaisesRegex(RuntimeError,'recovery_policy_input_drift'): self.tx.apply(policy)
        self.assertEqual(self.snapshot(),self.original_snapshot); self.assertEqual(self.host.actions,[])

    def test_binary_and_template_reads_explicitly_forbidden(self):
        for p in self.preserved_bytes:
            with self.assertRaisesRegex(RuntimeError,'protected_binary_or_template_read_forbidden'):
                self.fs.read(p,0o600)

    def test_incomplete_snapshot_never_changes_host_configuration(self):
        original=self.fs.write
        def fail(path,*args,**kwargs):
            if path.endswith('/recovery-policy.pp'): raise OSError('disk_full')
            return original(path,*args,**kwargs)
        with mock.patch.object(self.fs,'write',side_effect=fail),self.assertRaises(OSError):
            self.tx.apply(POLICY)
        self.assertEqual(self.snapshot(),self.original_snapshot)
        self.assertEqual(self.host.actions,[])
        self.assertTrue(self.path(m.BACKUP+'.pending').is_dir())
        self.assertFalse(self.path(m.BACKUP).exists())

    def test_missing_parent_stops_rollback_before_changes(self):
        self.tx.apply(POLICY)
        self.path('/etc/sudoers.d').rmdir()
        previous=list(self.host.actions)
        with self.assertRaises(FileNotFoundError): self.tx.rollback()
        self.assertEqual(previous,self.host.actions)
        self.assertEqual(self.host.value,'absent')

    def test_atomic_writer_never_deletes_preexisting_temporary(self):
        p='/etc/sudoers.d/90-goodix-d285-01'
        self.put(p+'.goodix-migration-new',b'foreign',0o600)
        with self.assertRaises(FileExistsError): self.fs.write(p,b'new',0o440)
        self.assertEqual(self.path(p+'.goodix-migration-new').read_bytes(),b'foreign')
        self.assertEqual(self.snapshot(),self.original_snapshot)

    def test_drift_refused_before_any_mutation(self):
        for p in ('/etc/sudoers.d/90-goodix-d285-01','/etc/authselect/system-auth'):
            original=self.path(p).read_bytes(); mode=self.path(p).stat().st_mode&0o7777
            self.path(p).unlink(); self.put(p,original+b'changed',mode)
            with self.assertRaises(RuntimeError): self.tx.apply(POLICY)
            self.path(p).unlink(); self.put(p,original,mode)
        self.assertFalse(self.path(m.BACKUP).exists()); self.assertEqual(self.host.actions,[])

    def test_extra_selector_and_extra_template_fail_closed(self):
        for p in ('/etc/sudoers.d/other','/var/lib/fprint/guido/goodix_27c6_5125/0/8'):
            self.put(p,b'synthetic')
            with self.assertRaises(RuntimeError): self.tx.apply(POLICY)
            self.path(p).unlink()
        self.assertFalse(self.path(m.BACKUP).exists())

    def test_symlink_hardlink_fifo_and_parent_symlink_refused(self):
        p='/etc/sudoers.d/90-goodix-d285-01'; path=self.path(p); data=path.read_bytes()
        path.unlink(); path.symlink_to(self.temp/'external')
        with self.assertRaises(RuntimeError): self.tx.apply(POLICY)
        path.unlink(); self.put(p,data,0o440)
        other=self.temp/'hardlink'; os.link(path,other)
        with self.assertRaises(RuntimeError): self.tx.apply(POLICY)
        other.unlink(); path.unlink(); os.mkfifo(path,0o440)
        with self.assertRaises(RuntimeError): self.tx.apply(POLICY)
        path.unlink(); self.put(p,data,0o440)
        parent=path.parent; moved=self.temp/'moved'; parent.rename(moved); parent.symlink_to(moved)
        with self.assertRaises(OSError): self.tx.apply(POLICY)
        self.assertEqual(self.host.actions,[])

    def test_handled_failure_auto_rolls_back(self):
        def fail(phase):
            if phase=='policy_removed': raise RuntimeError('injected')
        self.tx.checkpoint=fail
        with self.assertRaisesRegex(RuntimeError,'injected'): self.tx.apply(POLICY)
        self.assert_restored()

    def test_crash_prefix_recovery_each_mutation_boundary(self):
        # Each prefix is checked in a fresh, independent root, with automatic
        # recovery deliberately unavailable, then a new transaction instance.
        for phase in ('masked',*m.ORDER,'policy_removed'):
            fixture=MigrationTests(); fixture.setUp()
            try:
                def fail(current):
                    if current==phase: raise RuntimeError('simulated_crash')
                fixture.tx.checkpoint=fail
                with mock.patch.object(fixture.tx,'rollback',side_effect=RuntimeError('unavailable')):
                    with self.assertRaisesRegex(RuntimeError,'partial_migration'): fixture.tx.apply(POLICY)
                recovered=m.Migration(fixture.fs,fixture.host,plan=fixture.plan)
                recovered.rollback(); fixture.assert_restored()
            finally: fixture.tearDown()

    def test_partial_atomic_file_recovered_and_foreign_temp_refused(self):
        self.tx.apply(POLICY)
        path=m.MATERIAL+'.goodix-migration-new'
        self.put(path,self.originals[m.MATERIAL][:17],0o600)
        self.tx.rollback(); self.assert_restored(); self.assertFalse(self.path(path).exists())
        self.put(path,b'FOREIGN',0o600)
        with self.assertRaisesRegex(RuntimeError,'foreign_pending_file'): self.tx.rollback()
        self.assertTrue(self.path(path).exists())

    def test_modified_postimage_backup_and_binary_never_overwritten(self):
        self.tx.apply(POLICY)
        for p in (m.MATERIAL,m.BACKUP+'/original-manifest.json','/var/lib/goodix-5125-poc/transport-material.bin'):
            file=self.path(p); old=file.read_bytes(); oldstat=file.stat()
            file.write_bytes(b'changed')
            with self.assertRaises(RuntimeError): self.tx.rollback()
            self.assertEqual(file.read_bytes(),b'changed')
            file.write_bytes(old); os.utime(file,ns=(oldstat.st_atime_ns,oldstat.st_mtime_ns))
        # ctime changed on the synthetic binary: deliberately remains a STOP.
        with self.assertRaisesRegex(RuntimeError,'preservation_snapshot'): self.tx.rollback()

    def test_nonroot_actual_cli_refuses_from_other_cwd(self):
        result=subprocess.run([sys.executable,'-I','-B',str(HERE/'migration.py'),'--apply',str(POLICY)],cwd='/tmp',capture_output=True,text=True)
        self.assertEqual(result.returncode,2); self.assertIn('operator_root_required',result.stderr)
        self.assertFalse(self.path(m.BACKUP).exists())
        for name,args in [('install.sh',[str(POLICY)]),('uninstall.sh',[])]:
            result=subprocess.run([str(HERE/name),*args],cwd='/tmp',capture_output=True,text=True)
            self.assertEqual(result.returncode,2); self.assertIn('operator_root',result.stderr)

    def test_saved_recovery_sources_complete(self):
        self.tx.apply(POLICY)
        state=self.tx.state()
        for name,h in state['source'].items(): self.assertEqual(m.digest(self.path(m.BACKUP+'/'+name).read_bytes()),h)
        self.assertEqual(set(state['source']),{'migration.py','manifest.py','inventory.py','host-plan.json','recovery.py','rearm.py','package_baseline.py','legacy-recovery.json'})
        manager=self.path(m.BACKUP+'/recovery/'+m.recovery.PATHS[0])
        refused=subprocess.run(['/usr/bin/bash',str(manager),'--status'],cwd='/tmp',capture_output=True)
        self.assertEqual(refused.returncode,2)
        spec=importlib.util.spec_from_file_location('saved_migration',self.path(m.BACKUP+'/migration.py'))
        saved=importlib.util.module_from_spec(spec); spec.loader.exec_module(saved)
        recovered=saved.Migration(self.fs,self.host,plan=self.plan)
        recovered.rollback(); self.assert_restored()

    def test_vendor_dropin_is_preserved_and_digest_drift_refused(self):
        original=self.path(m.VENDOR_DROPIN).read_bytes()
        self.path(m.VENDOR_DROPIN).write_bytes(original+b'changed')
        with self.assertRaisesRegex(RuntimeError,'preserved_software_drift'): self.tx.apply(POLICY)
        self.assertEqual(self.host.actions,[])
        self.path(m.VENDOR_DROPIN).write_bytes(original)
        self.tx.apply(POLICY); self.tx.rollback()
        self.assertEqual(self.path(m.VENDOR_DROPIN).read_bytes(),original)
        self.assertNotIn(m.VENDOR_DROPIN,m.ORDER)

    def test_short_recovery_collision_never_overwritten(self):
        self.put(m.recovery.SHORT,b'foreign',0o700)
        with self.assertRaisesRegex(RuntimeError,'short_recovery_path_collision'): self.tx.apply(POLICY)
        self.assertEqual(self.path(m.recovery.SHORT).read_bytes(),b'foreign')
        self.assertFalse(self.path(m.BACKUP).exists())

    def test_real_candidate_install_status_uninstall_restores_migration_baseline(self):
        candidate=os.environ.get('GOODIX_MIGRATION_TEST_CANDIDATE')
        if not candidate: self.skipTest('set GOODIX_MIGRATION_TEST_CANDIDATE to prepared canonical candidate')
        self.put('/etc/pam.d/system-auth',self.path('/etc/authselect/system-auth').read_bytes())
        self.put('/usr/lib/systemd/user/plasma-login.service',b'[Service]\nExecStart=/usr/libexec/plasma-login-greeter\n')
        self.put('/etc/sudoers.offline.json',b'{}')
        self.tx.apply(POLICY); self.tx.release()
        baseline={p:(self.path(p).read_bytes() if self.path(p).exists() else None) for p in m.ORDER}
        env=os.environ|{'GOODIX_MANAGED_TEST_ROOT':str(self.root),
                        'GOODIX_MANAGED_TEST_KDE_VENDOR_SHA256':m.VENDOR['/etc/pam.d/kde-fingerprint'][2]}
        def run(*args,**extra):
            return subprocess.run([str(REPO/'deployment/managed-install/root-transaction.sh'),*args],env=env|extra,capture_output=True,text=True)
        caller=os.environ.get('USER','guido')
        result=run('--root-install',caller,candidate)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertIn('GOODIX_MANAGED_INSTALL=PASS',result.stdout)
        result=run('--status'); self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('SUDO_INTEGRATION=PASSWORD_FIRST_SERVICE_LOCAL_V1',result.stdout)
        self.assertIn('POLKIT_INTEGRATION=INTERRUPTIBLE_SERVICE_LOCAL_V1',result.stdout)
        # Runtime state is a single bounded Polkit counter; sudo's state lives
        # only in its PAM handle (covered by the native combined PAM tests).
        counter=self.path('/run/polkit/goodix-fingerprint/1000')
        counter.write_bytes(b'4');counter.chmod(0o600)
        def snapshot():
            return {str(p.relative_to(self.root)):(p.lstat().st_mode,
                os.readlink(p) if p.is_symlink() else p.read_bytes() if p.is_file() else None)
                for p in self.root.rglob('*')}
        before=snapshot()
        refused=run('--root-uninstall',caller)
        self.assertNotEqual(refused.returncode,0)
        self.assertIn('counter content drift',refused.stderr)
        self.assertEqual(snapshot(),before,'guard STOP partially uninstalled candidate')
        counter.write_bytes(b'2')
        with self.assertRaisesRegex(RuntimeError,'candidate_present'): self.tx.rollback()
        # The complete saved recovery uses its own manager/deploy/rules copies,
        # not the original checkout. Its only allowed manager mode is uninstall.
        saved_manager=self.path(m.BACKUP+'/recovery/'+m.recovery.PATHS[0])
        self.assertNotIn(b'repo=$(git',saved_manager.read_bytes())
        def invoke(command):
            self.assertEqual(Path(command[1]),saved_manager)
            completed=subprocess.run(command,env=env,capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stderr)
        # Stop after manager uninstall to assert exactly the migration baseline.
        with mock.patch.object(self.tx,'rollback',return_value='stopped_before_historical_restore'):
            self.assertEqual(m.recovery.restore(self.tx,invoke),'stopped_before_historical_restore')
        self.assertEqual({p:(self.path(p).read_bytes() if self.path(p).exists() else None) for p in m.ORDER},baseline)
        self.assertFalse(self.path('/etc/sudoers.d/90-goodix-d285-01').exists())
        self.tx.rollback(); self.assert_restored()

    def test_real_candidate_partial_install_restores_migration_baseline(self):
        candidate=os.environ.get('GOODIX_MIGRATION_TEST_CANDIDATE')
        if not candidate: self.skipTest('set GOODIX_MIGRATION_TEST_CANDIDATE')
        for flag in ('GOODIX_MANAGED_TEST_FAIL_AFTER_POLICY','GOODIX_MANAGED_TEST_FAIL_AFTER_KSCREENLOCKER_PAM',
                     'GOODIX_MANAGED_TEST_FAIL_AFTER_LOGIN_RUNTIME','GOODIX_MANAGED_TEST_FAIL_AFTER_POLKIT'):
            fixture=MigrationTests(); fixture.setUp()
            try:
                fixture.put('/etc/pam.d/system-auth',fixture.path('/etc/authselect/system-auth').read_bytes())
                fixture.put('/usr/lib/systemd/user/plasma-login.service',b'[Service]\nExecStart=/usr/libexec/plasma-login-greeter\n')
                fixture.put('/etc/sudoers.offline.json',b'{}')
                fixture.tx.apply(POLICY); fixture.tx.release()
                env=os.environ|{'GOODIX_MANAGED_TEST_ROOT':str(fixture.root),flag:'true',
                                'GOODIX_MANAGED_TEST_KDE_VENDOR_SHA256':m.VENDOR['/etc/pam.d/kde-fingerprint'][2]}
                result=subprocess.run([str(REPO/'deployment/managed-install/root-transaction.sh'),'--root-install',
                                       os.environ.get('USER','guido'),candidate],env=env,capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0,flag)
                fixture.tx.validate(fixture.tx.state(),'after')
                fixture.tx.rollback(); fixture.assert_restored()
            finally: fixture.tearDown()

class PolicyTests(unittest.TestCase):
    def test_actual_fedora_dropin_list_and_unknown_order_missing_refused(self):
        host=m.Host()
        prefix=['Enforcing','selinux-policy-targeted-44.9-1.fc44.noarch',
                '/usr/lib/systemd/system/fprintd.service']
        with mock.patch.object(host,'run',side_effect=prefix+[' '.join(m.EXPECTED_DROPINS)]):
            host.qualify()
        for rows in (m.EXPECTED_DROPINS[1:],m.EXPECTED_DROPINS+['/etc/systemd/system/service.d/unknown.conf'],
                     list(reversed(m.EXPECTED_DROPINS)),m.EXPECTED_DROPINS+[m.VENDOR_DROPIN]):
            with self.subTest(rows=rows),mock.patch.object(host,'run',side_effect=prefix+[' '.join(rows)]),self.assertRaisesRegex(RuntimeError,'fprintd_dropins_drift'):
                host.qualify()

    def test_effective_policy_digest_priority_and_disabled(self):
        host=m.Host()
        correct=[f'400 {m.POLICY} pp sha256:ignored',f'{m.POLICY} sha256:{m.CIL_SHA}']
        with mock.patch.object(host,'run',side_effect=correct): self.assertEqual(host.policy(),'legacy')
        with mock.patch.object(host,'run',return_value='other_policy'): self.assertEqual(host.policy(),'absent')
        for outputs in ([f'300 {m.POLICY} pp'],[f'400 {m.POLICY} pp\n200 {m.POLICY} pp'],
                        [correct[0],f'{m.POLICY} sha256:wrong'],
                        [correct[0],correct[1]+' disabled'],[correct[0],'']):
            with self.subTest(outputs=outputs),mock.patch.object(host,'run',side_effect=outputs),self.assertRaises(RuntimeError):
                host.policy()

if __name__=='__main__': unittest.main()
