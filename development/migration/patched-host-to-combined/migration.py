#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fixed host migration. Real entrypoint is operator/root only; tests use /tmp.

No USB, authentication, material import, binary/template content reads, or
historical uninstaller. Snapshots are recovery state, never authorization tokens.
"""
import base64
import ctypes
from types import SimpleNamespace
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent

def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

manifest = module('manifest')
inventory = module('inventory')
recovery = module('recovery')
package_baseline = module('package_baseline')
rearm = module('rearm')
MATERIAL = '/var/lib/goodix-5125-poc/target-material-manifest.json'
BACKUP = '/var/lib/goodix-27c6-5125-migration'
MASK = '/run/systemd/system/fprintd.service'
POLICY = 'goodix_fprint_account_delete'
POLICY_SHA = '674740ba782b501a68dbaff9bef04d725cc9e88adad6f37c6f3c468a2cc71d03'
CIL_SHA = 'e993729e97ad84f2a89e6cd41bbdb2e5f557a9898f0d96962183053bea0a69f3'
VENDOR_DROPIN = '/usr/lib/systemd/system/service.d/10-timeout-abort.conf'
EXPECTED_DROPINS = [VENDOR_DROPIN,
    '/etc/systemd/system/fprintd.service.d/90-goodix-d285-01.conf',
    '/etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf',
    '/etc/systemd/system/fprintd.service.d/96-goodix-login-early.conf']
VENDOR = {
    '/usr/lib/pam.d/plasmalogin': (
        b'auth        sufficient    /usr/lib64/security/pam_fprintd.so max-tries=3 timeout=45 debug\n', b'',
        'c6fc4a0bc2d89f88fa15ca7e9a6c5aaeccfbe66897755b5416ce9c5e35b4e40b'),
    '/etc/pam.d/kde-fingerprint': (
        b'auth        required      pam_fprintd.so max-tries=3 timeout=45\n',
        b'auth        substack      fingerprint-auth\n',
        '8b3181ce5979f498e2cd07acaf3f57c63b1e2f9593e44bfa9027b6dd8bb62437'),
}
ORDER = (
    '/etc/sudoers.d/90-goodix-d285-01', '/etc/pam.d/goodix-d285-01-sudo',
    '/etc/systemd/user/plasma-login.service.d/96-goodix-login-early.conf',
    '/etc/pam.d/plasmalogin',
    '/etc/systemd/system/fprintd.service.d/96-goodix-login-early.conf',
    '/etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf',
    '/etc/systemd/system/fprintd.service.d/90-goodix-d285-01.conf',
    '/etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete',
    *VENDOR, MATERIAL,
)
COLLISIONS = (
    '/var/lib/goodix-27c6-5125-managed', '/var/lib/goodix-polkit',
    '/usr/lib64/goodix-27c6-5125',
    '/usr/libexec/goodix-27c6-5125/fprintd-wrapper',
    '/etc/systemd/system/fprintd.service.d/99-goodix-27c6-5125-managed.conf',
    '/etc/systemd/user/plasma-login.service.d/99-goodix-login-greeter.conf',
    '/etc/systemd/system/plasmalogin.service.d/99-goodix-plasma-vt.conf',
    '/etc/pam.d/polkit-1', '/etc/pam.d/goodix-polkit-fingerprint',
    '/etc/pam.d/goodix-sudo-fingerprint',
)

def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def digest(data):
    return hashlib.sha256(data).hexdigest()

class Files:
    """Descriptor-relative access; only the migration's exact paths are used."""
    def __init__(self, root='/'):
        self.root = Path(root)
        self.test = str(self.root) != '/'
        if self.test:
            require(os.geteuid() != 0 and self.root.is_dir() and not self.root.is_symlink()
                    and str(self.root).startswith('/tmp/goodix-managed-test.'), 'unsafe_test_root')
        self.uid = os.geteuid() if self.test else 0
        self.gid = os.getegid() if self.test else 0
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def close(self):
        os.close(self.fd)

    def parent(self, path):
        parts = PurePosixPath(path).parts
        require(parts[0] == '/' and '..' not in parts, 'invalid_path')
        fd = os.dup(self.fd)
        try:
            for part in parts[1:-1]:
                new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NOATIME, dir_fd=fd)
                os.close(fd); fd = new
                s = os.fstat(fd)
                require(s.st_uid == self.uid and not s.st_mode & 0o022, 'unsafe_parent')
            return fd, parts[-1]
        except BaseException:
            os.close(fd)
            raise

    def info(self, path):
        try:
            fd, leaf = self.parent(path)
        except FileNotFoundError:
            return None
        try:
            s = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
            return dict(type=stat.S_IFMT(s.st_mode), mode=stat.S_IMODE(s.st_mode),
                        uid=s.st_uid, gid=s.st_gid, size=s.st_size,
                        mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns,
                        ino=s.st_ino, dev=s.st_dev, nlink=s.st_nlink)
        except FileNotFoundError:
            return None
        finally:
            os.close(fd)

    def read(self, path, mode, limit=32 * 1024 * 1024):
        require(path in (MATERIAL, MATERIAL+'.goodix-migration-new') or not path.startswith(('/var/lib/fprint/',
                '/var/lib/goodix-5125-poc/', '/var/lib/goodix-5125-staging/')),
                'protected_binary_or_template_read_forbidden')
        fd, leaf = self.parent(path)
        pin = datafd = None
        try:
            pin = os.open(leaf, os.O_PATH | os.O_NOFOLLOW, dir_fd=fd)
            s = os.fstat(pin)
            require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and
                    stat.S_IMODE(s.st_mode) == mode and
                    (s.st_uid, s.st_gid) == (self.uid, self.gid) and 0 <= s.st_size <= limit,
                    'file_metadata_drift')
            datafd = os.open('/proc/self/fd/' + str(pin), os.O_RDONLY | os.O_NOATIME)
            data = bytearray()
            while len(data) <= limit:
                block = os.read(datafd, min(65536, limit + 1 - len(data)))
                if not block: break
                data.extend(block)
            after = os.fstat(datafd)
            require(len(data) == s.st_size and
                    (s.st_ino, s.st_mtime_ns, s.st_ctime_ns) ==
                    (after.st_ino, after.st_mtime_ns, after.st_ctime_ns), 'file_changed_during_read')
            attrs = os.listxattr(datafd)
            require(set(attrs) <= {'security.selinux'}, 'custom_file_attributes')
            label = os.getxattr(datafd, 'security.selinux') if attrs else b''
            return bytes(data), base64.b64encode(label).decode('ascii')
        finally:
            if datafd is not None: os.close(datafd)
            if pin is not None: os.close(pin)
            os.close(fd)

    def write(self, path, data, mode, label='', exclusive=False, mtime_ns=None):
        fd, leaf = self.parent(path)
        temporary = leaf + '.goodix-migration-new'
        out = None
        created = False
        try:
            require(not exclusive or self.info(path) is None, 'backup_already_exists')
            out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            created = True
            view = memoryview(data)
            while view:
                n = os.write(out, view)
                require(n > 0, 'short_write')
                view = view[n:]
            os.fchown(out, self.uid, self.gid)
            os.fchmod(out, mode)
            if label: os.setxattr(out, 'security.selinux', base64.b64decode(label, validate=True))
            if mtime_ns is not None:
                os.utime(out,ns=(os.fstat(out).st_atime_ns,mtime_ns))
            os.fsync(out); os.close(out); out = None
            if exclusive:
                os.link(temporary, leaf, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                os.unlink(temporary, dir_fd=fd)
            else:
                os.replace(temporary, leaf, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        except BaseException:
            if out is not None: os.close(out)
            if created:
                try: os.unlink(temporary, dir_fd=fd)
                except FileNotFoundError: pass
            raise
        finally:
            os.close(fd)

    def delete(self, path):
        fd, leaf = self.parent(path)
        try: os.unlink(leaf, dir_fd=fd); os.fsync(fd)
        finally: os.close(fd)

    def mkdir(self, path):
        fd, leaf = self.parent(path)
        try: os.mkdir(leaf, 0o700, dir_fd=fd); os.fsync(fd)
        finally: os.close(fd)

    def rename(self, old, new):
        require(self.info(new) is None, 'rename_destination_exists')
        a,x=self.parent(old); b,y=self.parent(new)
        try: os.rename(x,y,src_dir_fd=a,dst_dir_fd=b); os.fsync(a); os.fsync(b)
        finally: os.close(a); os.close(b)

    def exchange(self, old, new):
        a,x=self.parent(old); b,y=self.parent(new)
        try:
            libc=ctypes.CDLL(None,use_errno=True)
            call=libc.renameat2
            call.argtypes=(ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint)
            call.restype=ctypes.c_int
            if call(a,x.encode(),b,y.encode(),2) != 0:
                raise OSError(ctypes.get_errno(),'snapshot_exchange_failed')
            os.fsync(a); os.fsync(b)
        finally: os.close(a); os.close(b)

    def link_value(self, path):
        fd, leaf = self.parent(path)
        try: return os.readlink(leaf, dir_fd=fd)
        finally: os.close(fd)

    def set_mask(self):
        if self.info(MASK) is not None:
            require(self.link_value(MASK) == '/dev/null', 'foreign_runtime_mask')
            return
        fd, leaf = self.parent(MASK)
        try: os.symlink('/dev/null', leaf, dir_fd=fd); os.fsync(fd)
        finally: os.close(fd)

class Host:
    def run(self, *args):
        result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=60,
                                env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL':'C'})
        require(result.returncode == 0, 'host_command_failed_' + Path(args[0]).name)
        return result.stdout.decode('utf-8').strip()

    def packages(self, contract, postimage=False):
        if postimage: package_baseline.verify_host(self,contract)
        else: package_baseline.qualify(self,contract)

    def inactive(self):
        return self.run('/usr/bin/systemctl', 'show', 'fprintd.service', '-p', 'ActiveState', '--value') == 'inactive'

    def reload(self):
        self.run('/usr/bin/systemctl', 'daemon-reload')

    def stop(self):
        self.run('/usr/bin/systemctl', 'stop', 'fprintd.service')

    def policy(self):
        rows = [s.split() for s in self.run('/usr/sbin/semodule', '-lfull', '-m').splitlines()]
        rows = [r for r in rows if len(r) >= 2 and r[1] == POLICY]
        if not rows: return 'absent'
        require(len(rows) == 1 and rows[0][0] == '400', 'policy_priority_drift')
        sums = [s.split() for s in self.run('/usr/sbin/semodule', '-l', '-m').splitlines()]
        sums = [r for r in sums if r and r[0] == POLICY]
        require(len(sums) == 1 and len(sums[0]) == 2 and sums[0][1] == 'sha256:' + CIL_SHA,
                'policy_content_or_enabled_state_drift')
        return 'legacy'

    def remove_policy(self):
        require(self.policy() == 'legacy', 'policy_not_legacy')
        self.run('/usr/sbin/semodule', '-X', '400', '-r', POLICY)
        require(self.policy() == 'absent', 'policy_removal_incomplete')

    def restore_policy(self, path):
        self.run('/usr/sbin/semodule', '-X', '400', '-i', str(path))
        require(self.policy() == 'legacy', 'policy_restore_failed')

    def qualify(self):
        require(self.run('/usr/sbin/getenforce') == 'Enforcing', 'selinux_not_enforcing')
        require(self.run('/usr/bin/rpm', '-q', 'selinux-policy-targeted') ==
                'selinux-policy-targeted-44.9-1.fc44.noarch', 'policy_package_drift')
        require(self.run('/usr/bin/systemctl','show','fprintd.service','-p','FragmentPath','--value') ==
                '/usr/lib/systemd/system/fprintd.service', 'fprintd_unit_override')
        actual = self.run('/usr/bin/systemctl','show','fprintd.service','-p','DropInPaths','--value').split()
        if actual != EXPECTED_DROPINS:
            print('FPRINTD_EXPECTED_DROPINS='+json.dumps(EXPECTED_DROPINS),file=sys.stderr)
            print('FPRINTD_ACTUAL_DROPINS='+json.dumps(actual),file=sys.stderr)
            raise RuntimeError('fprintd_dropins_drift')

class Migration:
    def __init__(self, fs, host, plan=None, checkpoint=None):
        self.fs, self.host = fs, host
        self.backup = BACKUP
        self.hash = digest
        self.module_api = SimpleNamespace(HERE=HERE,BACKUP=BACKUP,digest=digest,
                                          require=require,recovery=recovery,os=os)
        require(plan is None or fs.test, 'real_plan_override_refused')
        self.plan = plan if plan is not None else json.loads((HERE / 'host-plan.json').read_bytes())
        require(set(self.plan['files']) == set(ORDER) - {MATERIAL}, 'plan_file_set')
        require(set(self.plan['packages']) == set(VENDOR), 'package_contract_file_set')
        self.checkpoint = checkpoint or (lambda phase: None)
        require(checkpoint is None or fs.test, 'real_fault_injection_refused')

    def at(self, directory):
        other=Migration(self.fs,self.host,plan=self.plan if self.fs.test else None)
        other.backup=directory
        return other

    def rearm(self, policy_path):
        return rearm.rotate(self,policy_path)

    def preflight(self):
        self.before()
        if self.fs.info(self.backup):
            state,_=rearm.saved(self,self.backup)
            if state['status']=='RESTORED': return 'PREFLIGHT_PASS_REARM_REQUIRED'
        return 'PREFLIGHT_PASS_NO_CONFIGURATION_CHANGE'

    def package_compatible(self, state):
        package_baseline.check_files(self,state)
        self.host.packages(self.plan['packages'],postimage=True)

    def guards(self):
        for p, row in self.plan['guards'].items():
            data, _ = self.fs.read(p, row['mode'])
            require(digest(data) == row['sha256'], 'preserved_software_drift_' + p)
        probe = inventory.Inventory(str(self.fs.root))
        probe.env_state('/etc/goodix-27c6-5125/d285-01.state', set(self.plan['d285_state']))
        require(probe.rows[-1]['fields'] == self.plan['d285_state'], 'd285_state_drift')
        early = '/usr/local/lib64/goodix-27c6-5125/login-early/'
        for leaf, target in [('libfprint-2.so', 'libfprint-2.so.2'), ('libfprint-2.so.2', 'libfprint-2.so.2.0.0')]:
            require(self.fs.link_value(early + leaf) == target, 'legacy_runtime_link_drift')

    def preserve(self):
        result = {}
        for p, expected in self.plan['preserve'].items():
            info = self.fs.info(p)
            require(info is not None, 'preserved_path_missing')
            for key, value in expected.items():
                if key in ('uid','gid') and self.fs.test: value = getattr(self.fs, key)
                if key == 'mode': value = int(value, 8)
                require(info[key] == value, 'preservation_metadata_drift_' + p)
            if info['type'] == stat.S_IFREG:
                require(info['nlink'] == 1, 'preserved_file_hardlink')
                result[p] = info
            else:
                result[p] = {k:info[k] for k in ('type','mode','uid','gid','ino','dev')}
        # Bounded metadata-only tree: detect additions as well as missing template paths.
        probe = inventory.Inventory(str(self.fs.root))
        probe.tree('/var/lib/fprint', 4)
        require(probe.issues == 0 and {r['path'] for r in probe.rows} ==
                {p for p in result if p == '/var/lib/fprint' or p.startswith('/var/lib/fprint/')},
                'template_tree_changed')
        return result

    def no_candidate(self):
        for path in COLLISIONS:
            require(self.fs.info(path) is None, 'candidate_present_uninstall_first')

    def before(self, armed=False):
        self.no_candidate(); self.host.qualify(); self.guards()
        self.host.packages(self.plan['packages'])
        if self.fs.info(self.backup):
            previous,_=rearm.saved(self,self.backup)
            require(not armed or previous['status']=='PREPARED','restored_attempt_requires_rearm')
            if armed:
                require(self.fs.info(self.backup+'.pending') is None,'rearm_finalize_required')
                rearm.finish(self,previous)
        else:
            require(self.fs.info(recovery.SHORT) is None, 'short_recovery_path_collision')
            require(self.fs.info(self.backup+'.pending') is None,'incomplete_snapshot_keep_recovery')
        require(self.host.inactive(), 'fprintd_must_be_inactive')
        require(self.fs.info(MASK) is None, 'runtime_override_present')
        require(self.host.policy() == 'legacy', 'legacy_policy_missing')
        for directory, allowed in (
            ('/etc/systemd/system/fprintd.service.d', {PurePosixPath(p).name for p in ORDER if '/fprintd.service.d/' in p}),
            ('/etc/systemd/user/plasma-login.service.d', {'96-goodix-login-early.conf'}),
            ('/etc/sudoers.d', {'90-goodix-d285-01'})):
            fd, leaf = self.fs.parent(directory + '/entry')
            try: require(set(os.listdir(fd)) == allowed, 'extra_overlay_or_selector')
            finally: os.close(fd)
        files = {}
        for index, p in enumerate(ORDER):
            require(self.fs.info(p + '.goodix-migration-new') is None, 'preexisting_pending_file')
            row = self.plan['files'].get(p, {'mode':0o600, 'sha256':manifest.LEGACY_SHA256})
            data, label = self.fs.read(p, row['mode'], 65536)
            require(digest(data) == row['sha256'], 'owned_file_drift_' + p)
            if p == MATERIAL:
                after = manifest.convert(data)
            elif p in VENDOR:
                old, new, expected = VENDOR[p]
                require(data.count(old) == 1, 'vendor_transform_ambiguous')
                after = data.replace(old, new)
                require(digest(after) == expected, 'vendor_digest_mismatch')
            else:
                after = None
            files[p] = dict(mode=row['mode'], label=label, mtime_ns=self.fs.info(p)['mtime_ns'], before=row['sha256'],
                            after=digest(after) if after is not None else None,
                            backup='original-manifest.json' if p == MATERIAL else str(index))
        plasma_before = self.host.run('/usr/bin/systemctl','show','plasmalogin.service','-p','ActiveState','--value')
        require(plasma_before in ('active','inactive'), 'plasma_service_before_invalid')
        return dict(schema=2, status='PREPARED', files=files, preserved=self.preserve(),
                    plasma_service_before=plasma_before), files

    def save(self, state):
        self.fs.write(self.backup + '/state.json', (json.dumps(state,sort_keys=True,indent=2)+'\n').encode(), 0o600)

    def state(self):
        info = self.fs.info(self.backup)
        require(info is not None and info['type'] == stat.S_IFDIR and info['mode'] == 0o700
                and info['uid'] == self.fs.uid and info['gid'] == self.fs.gid, 'recovery_directory_invalid')
        data, _ = self.fs.read(self.backup + '/state.json', 0o600, 65536)
        state = json.loads(data)
        require(state['schema'] == 2 and set(state['files']) == set(ORDER)
                and state['status'] in ('PREPARED','APPLIED','RESTORED'), 'recovery_state_invalid')
        require(state.get('plasma_service_before') in ('active','inactive'), 'plasma_service_before_invalid')
        require(state['source'] == self.source(), 'migration_source_changed_use_saved_version')
        for name, expected in state['source'].items():
            data, _ = self.fs.read(self.backup+'/'+name,0o600)
            require(digest(data) == expected, 'saved_recovery_source_drift')
        for index,p in enumerate(ORDER):
            row = state['files'][p]
            require(row['backup'] == ('original-manifest.json' if p == MATERIAL else str(index)), 'backup_path_invalid')
            expected = self.plan['files'].get(p, {'mode':0o600,'sha256':manifest.LEGACY_SHA256})
            require(row['mode'] == expected['mode'] and row['before'] == expected['sha256'], 'backup_contract_drift')
            require(type(row['mtime_ns']) is int and 0 <= row['mtime_ns'] < 2**63,'backup_mtime_invalid')
            original, _ = self.fs.read(self.backup+'/'+row['backup'], 0o600, 65536)
            require(digest(original) == row['before'], 'backup_digest_drift')
            after = self.converted(p,original)
            require(row['after'] == (digest(after) if after is not None else None), 'postimage_contract_drift')
        policy, _ = self.fs.read(self.backup + '/recovery-policy.pp', 0o600, 65536)
        require(digest(policy) == POLICY_SHA, 'recovery_policy_drift')
        require(set(state['recovery']) == set(recovery.PATHS), 'recovery_file_set_drift')
        for name, expected in state['recovery'].items():
            data, _ = self.fs.read(self.backup+'/recovery/'+name,0o600)
            require(digest(data) == expected, 'saved_manager_recovery_drift')
        if self.fs.info(recovery.SHORT) is not None:
            data,_ = self.fs.read(recovery.SHORT,0o700,4096)
            require(data == recovery.SHORT_BYTES, 'short_recovery_command_drift')
        return state

    def source(self):
        return {p:digest((HERE/p).read_bytes()) for p in ('migration.py','manifest.py','inventory.py','host-plan.json','recovery.py','package_baseline.py','rearm.py','legacy-recovery.json')}

    def original(self, row):
        return self.fs.read(self.backup+'/'+row['backup'], 0o600, 65536)[0]

    def converted(self, path, original):
        if path == MATERIAL: return manifest.convert(original)
        if path in VENDOR:
            old,new,expected = VENDOR[path]
            require(original.count(old) == 1, 'vendor_transform_ambiguous')
            result = original.replace(old,new)
            require(digest(result) == expected, 'vendor_digest_mismatch')
            return result
        return None

    def clear_pending(self, path, alternatives, modes):
        temporary = path + '.goodix-migration-new'
        info = self.fs.info(temporary)
        if info is None: return
        require(info['mode'] in modes, 'pending_file_mode_drift')
        data,_ = self.fs.read(temporary,info['mode'],65536)
        require(any(value.startswith(data) for value in alternatives), 'foreign_pending_file')
        self.fs.delete(temporary)

    def current(self, p, row):
        info = self.fs.info(p)
        if info is None: return None
        data, label = self.fs.read(p, row['mode'], 65536)
        require(label == row['label'], 'owned_label_drift')
        return digest(data)

    def validate(self, state, which=None):
        self.no_candidate(); self.guards()
        require(self.preserve() == state['preserved'], 'preservation_snapshot_changed')
        for p, row in state['files'].items():
            # An absent owned file is recoverable; a missing parent is drift.
            fd, _ = self.fs.parent(p)
            os.close(fd)
            value = self.current(p,row)
            allowed = {row[which]} if which else {row['before'],row['after']}
            require(value in allowed, 'owned_path_changed_' + p)
            if which=='before':
                require(self.fs.info(p)['mtime_ns']==row['mtime_ns'],'original_mtime_drift')

    def snapshot(self, state, policy_path, publish=True):
        policy = Path(policy_path)
        require(policy.name == POLICY+'.pp', 'invalid_recovery_policy_name')
        pin = os.open(policy,os.O_PATH|os.O_NOFOLLOW)
        try:
            info=os.fstat(pin)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_size==2086,
                    'invalid_recovery_policy_input')
            fd=os.open('/proc/self/fd/'+str(pin),os.O_RDONLY|os.O_NOATIME)
            with os.fdopen(fd,'rb') as stream: data=stream.read(2087)
        finally: os.close(pin)
        require(digest(data) == POLICY_SHA, 'recovery_policy_input_drift')
        pending = self.backup + '.pending'
        self.fs.mkdir(pending)
        for p, row in state['files'].items():
            original, _ = self.fs.read(p,row['mode'],65536)
            require(digest(original) == row['before'], 'file_drift_during_backup')
            self.fs.write(pending+'/'+row['backup'],original,0o600,exclusive=True)
        self.fs.write(pending+'/recovery-policy.pp',data,0o600,exclusive=True)
        sources = {name:(HERE/name).read_bytes() for name in self.source()}
        state['source'] = {name:digest(data) for name,data in sources.items()}
        for name,data in sources.items():
            self.fs.write(pending+'/'+name,data,0o600,exclusive=True)
        saved = recovery.sources(HERE.parents[2])
        for directory in recovery.DIRECTORIES:
            self.fs.mkdir(pending+'/recovery'+directory)
        for name,data in saved.items():
            self.fs.write(pending+'/recovery/'+name,data,0o600,exclusive=True)
        state['recovery'] = {name:digest(data) for name,data in saved.items()}
        self.fs.write(pending+'/state.json',(json.dumps(state,sort_keys=True,indent=2)+'\n').encode(),0o600,exclusive=True)
        self.at(pending).state()  # Verify complete new snapshot before publication.
        if publish:
            self.fs.rename(pending,self.backup)
            self.state()

    def apply(self, policy_path):
        if self.fs.info(self.backup):
            # A historical RESTORED snapshot needs explicit, qualified re-arm.
            raw,_=self.fs.read(self.backup+'/state.json',0o600,65536)
            require(json.loads(raw)['status']!='RESTORED','restored_attempt_requires_rearm')
            state=self.state()
            if state['status']=='APPLIED':
                self.validate(state,'after'); self.package_compatible(state)
                require(self.host.policy()=='absent','policy_reappeared')
                return 'ALREADY_APPLIED'
            require(state['status']=='PREPARED' and 'rearmed_from' in state,'existing_recovery_run_rollback_not_apply')
            self.before(armed=True)
        else:
            state,_=self.before(armed=True)
            self.snapshot(state,policy_path)
        try:
            self.validate(state,'before')
            if self.fs.info(recovery.SHORT) is None:
                self.fs.write(recovery.SHORT,recovery.SHORT_BYTES,0o700,exclusive=True)
            self.fs.set_mask(); self.host.reload(); self.host.stop()
            require(self.host.inactive(), 'daemon_did_not_stop')
            self.checkpoint('masked')
            for p in ORDER:
                row = state['files'][p]
                require(self.current(p,row) == row['before'], 'file_drift_before_change')
                if p == MATERIAL:
                    after = manifest.convert(self.original(row))
                elif p in VENDOR:
                    old,new,_ = VENDOR[p]; after = self.original(row).replace(old,new)
                else:
                    after = None
                if after is None: self.fs.delete(p)
                else: self.fs.write(p,after,row['mode'],row['label'],mtime_ns=
                                    package_baseline.mtime(self.plan['packages'],p) if p in VENDOR else row['mtime_ns'])
                self.checkpoint(p)
            self.host.remove_policy(); self.checkpoint('policy_removed')
            self.host.reload()
            self.validate(state,'after'); self.package_compatible(state)
            state['status'] = 'APPLIED'; self.save(state)
            return 'APPLIED_RUNTIME_MASKED'
        except BaseException:
            try: self.rollback()
            except BaseException as error:
                raise RuntimeError('partial_migration_recovery_required_keep_root_console') from error
            raise

    def release(self):
        state = self.state()
        require(state['status'] == 'APPLIED', 'migration_not_applied')
        self.validate(state,'after')
        self.package_compatible(state)
        print('MANAGED_INSTALLER_BASELINE_COMPATIBLE=PASS',flush=True)
        require(self.host.policy() == 'absent' and self.host.inactive(), 'release_boundary_drift')
        if self.fs.info(MASK) is not None:
            require(self.fs.link_value(MASK) == '/dev/null', 'foreign_runtime_mask')
            self.fs.delete(MASK); self.host.reload()
        return 'RELEASED_FOR_CANDIDATE_INSTALL'

    def rollback(self):
        state = self.state()
        self.validate(state)
        policy = self.host.policy()
        require(policy in ('legacy','absent'), 'foreign_policy')
        for p,row in state['files'].items():
            original = self.original(row)
            after = self.converted(p,original)
            self.clear_pending(p,[original] + ([after] if after is not None else []),{0o600,row['mode']})
        alternatives=[]
        for status in ('PREPARED','APPLIED','RESTORED'):
            value = dict(state,status=status)
            alternatives.append((json.dumps(value,sort_keys=True,indent=2)+'\n').encode())
        self.clear_pending(self.backup+'/state.json',alternatives,{0o600})
        if state['status'] == 'RESTORED' and self.fs.info(MASK) is None:
            require(policy == 'legacy', 'restored_policy_drift')
            self.validate(state,'before')
            return 'ALREADY_RESTORED'
        self.fs.set_mask(); self.host.reload(); self.host.stop()
        require(self.host.inactive(), 'daemon_did_not_stop')
        if policy == 'absent': self.host.restore_policy(self.fs.root / (self.backup+'/recovery-policy.pp').lstrip('/'))
        for p in reversed(ORDER):
            row = state['files'][p]
            value = self.current(p,row)
            require(value in (row['before'],row['after']), 'rollback_path_drift')
            if value != row['before'] or self.fs.info(p)['mtime_ns'] != row['mtime_ns']:
                self.fs.write(p,self.original(row),row['mode'],row['label'],mtime_ns=row['mtime_ns'])
        self.validate(state,'before')
        state['status'] = 'RESTORED'; self.save(state)
        self.fs.delete(MASK); self.host.reload()
        return 'RESTORED_ORIGINALS_DAEMON_INACTIVE_BACKUP_RETAINED'


def main():
    # No real-root override, environment test switch, sudo, or auth escalation.
    if os.geteuid() != 0 or len(sys.argv) not in (2,3):
        print('MIGRATION=REFUSED operator_root_required',file=sys.stderr)
        return 2
    action=sys.argv[1]
    if (action not in ('--preflight','--apply','--release-mask','--rollback') or
            len(sys.argv) != (3 if action == '--apply' else 2)):
        return 2
    fs = Files()
    lock = None
    try:
        # Directory flock needs no new lock file, even on negative preflight.
        if action != '--preflight':
            lock = os.open('/run',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        migration=Migration(fs,Host())
        if action == '--preflight':
            migration.before(); result='PREFLIGHT_PASS_NO_CONFIGURATION_CHANGE'
        elif action == '--apply': result=migration.apply(sys.argv[2])
        elif action == '--release-mask': result=migration.release()
        else: result=migration.rollback()
        print('MIGRATION='+result)
        return 0
    except (OSError,RuntimeError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        # Never render arbitrary exception/state/manifest contents.
        reason = str(error) if isinstance(error,RuntimeError) else 'io_or_state_validation_failure'
        if not re.fullmatch(r'[A-Za-z0-9_./-]{1,240}',reason): reason='validation_failure'
        print('MIGRATION=STOP reason='+reason+' preserve_root_console_and_recovery_directory',file=sys.stderr)
        return 1
    finally:
        if lock is not None: os.close(lock)
        fs.close()

if __name__ == '__main__':
    sys.exit(main())
