#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fixed, read-only missing-evidence inventory. No authentication or subprocesses."""
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat
import sys

CONFIG = '/etc/goodix-27c6-5125'
RUNTIME = '/usr/local/lib64/goodix-27c6-5125'
RUNTIMES = (
    'd285-01-a9e234e43d2bdf3e81630df143eb7a809a19bff5',
    'd293-native-e61fce313794922a2dab156a1b38a8ddc5837f19',
    'd297-local-c3722987700ea85a9f1062d764a10d8a1103b4f0',
    'd297-02-local-ef302008c85adfecde14433dd486187d2ad9d3f8',
    'login-early',
)
SOFTWARE = ('artifacts.sha256', 'SHA256SUMS', 'PROVENANCE', 'source-files.sha256',
            'libfprint-2.so.2.0.0', 'libgusb.so.2', 'libopencv_core.so.413',
            'libopencv_features2d.so.413', 'libopencv_flann.so.413',
            'libopencv_imgproc.so.413', 'fprintd', 'greeter', 'pam_fprintd.so')
EARLY_FILES = {RUNTIME + '/login-early/' + name for name in SOFTWARE} | {
    '/usr/local/sbin/goodix-login-early-fprintd',
    '/etc/systemd/system/fprintd.service.d/96-goodix-login-early.conf',
    '/etc/systemd/user/plasma-login.service.d/96-goodix-login-early.conf',
    '/etc/pam.d/plasmalogin', CONFIG + '/login-early.json',
}
STATE_KEYS = {
    'd285-01.state': ('D285_01_', '''INSTALL_STATUS BASELINE_SHA USER RUNTIME
        AUTHSELECT_BEFORE AUTHSELECT_ACTIVE AUTHSELECT_BACKUP SERVICE_BEFORE
        DAEMON_SHA256 PAM_SHA256 SUDOERS_SHA256 WRAPPER_SHA256 DROPIN_SHA256
        MANIFEST_SHA256 AUTHSELECT_CONF_BEFORE_SHA256 SYSTEM_AUTH_BEFORE_SHA256
        PASSWORD_AUTH_BEFORE_SHA256 FINGERPRINT_AUTH_BEFORE_SHA256
        PAM_SUDO_BEFORE_SHA256 SYSTEM_LIBFPRINT_BEFORE_SHA256'''),
    'd293-native.state': ('D293_NATIVE_', '''STATUS PRODUCTION_HEAD INSTALLER RUNTIME
        MANIFEST_SHA256 WRAPPER_SHA256 DROPIN_SHA256 INSTALL_SCRIPT_SHA256
        PREVIOUS_SERVICE_STATE PREVIOUS_UNIT_SNAPSHOT_SHA256
        PREVIOUS_D285_WRAPPER_SHA256 PREVIOUS_D285_DROPIN_SHA256
        PREVIOUS_D285_MANIFEST_SHA256 PREVIOUS_OWN_PATHS'''),
    'd293-phase-b-account-lifecycle.state': ('D293_B5_', '''STATUS INSTALLER
        REPOSITORY_HEAD D293_RUNTIME HOOK_SHA256 INSTALL_SCRIPT_SHA256
        CREATED_SHADOW_PARENT CREATED_HOOK_PARENT SELINUX_POLICY_RPM POLICY_NAME
        POLICY_PRIORITY POLICY_TYPE POLICY_SOURCE_SHA256 POLICY_FC_SHA256
        POLICY_PACKAGE_SHA256 POLICY_CIL_SHA256 PREVIOUS_HOOK_CONTEXT HOOK_CONTEXT'''),
    'd297-02-local.state': ('D297_02_LOCAL_', '''STATUS HEAD RUNTIME MANIFEST_SHA256
        WRAPPER_SHA256 DROPIN_SHA256 PREVIOUS_DROPIN_STATUS PREVIOUS_DROPIN_SHA256
        PREVIOUS_SERVICE_STATE'''),
}


class Inventory:
    def __init__(self, root='/'):
        self.root = root
        self.rows = []
        self.issues = 0

    def open(self, name, directory=False, path_only=False):
        # Open each ancestor relative to a held fd: never follow symlinks,
        # including ones swapped concurrently. Never use paths from state files.
        parts = PurePosixPath(name).parts
        if not name.startswith('/') or '..' in parts:
            raise ValueError('unsafe_path')
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NOATIME
        fd = os.open(self.root, flags | os.O_DIRECTORY)
        try:
            for index, part in enumerate(parts[1:]):
                want_dir = index < len(parts) - 2 or directory
                selected = flags | os.O_DIRECTORY if want_dir else (
                    os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC if path_only else flags | os.O_NONBLOCK)
                next_fd = os.open(part, selected, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            return fd
        except BaseException:
            os.close(fd)
            raise

    def read(self, name, limit=65536):
        fd = self.open(name, path_only=True)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
                raise ValueError('unsafe_type_links_or_size')
            # O_PATH pins the inode without opening a device/FIFO. Only a
            # validated regular inode can reach the actual data-open operation.
            data_fd = os.open('/proc/self/fd/' + str(fd), os.O_RDONLY | os.O_CLOEXEC | os.O_NOATIME)
            with os.fdopen(data_fd, 'rb') as stream:
                data = stream.read(limit + 1)
            after = os.fstat(fd)
            if len(data) > limit or (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError('file_changed_or_too_large')
            return data
        finally:
            os.close(fd)

    def metadata(self, name):
        parent, leaf = str(PurePosixPath(name).parent), PurePosixPath(name).name
        fd = self.open(parent, directory=True)
        try:
            info = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
            row = dict(path=name, mode=oct(stat.S_IMODE(info.st_mode)), uid=info.st_uid,
                       gid=info.st_gid, size=info.st_size, mtime_ns=info.st_mtime_ns,
                       type=stat.S_IFMT(info.st_mode))
            if stat.S_ISLNK(info.st_mode):
                row['symlink'] = True  # Do not follow or disclose arbitrary targets.
            self.rows.append(row)
            return info
        finally:
            os.close(fd)

    def attempt(self, name, action):
        try:
            action()
        except FileNotFoundError:
            self.rows.append(dict(path=name, status='ABSENT'))
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            # No exception text: JSON errors can include state contents.
            self.issues += 1
            self.rows.append(dict(path=name, status='UNKNOWN_STOP'))

    def tree(self, name, depth=0):
        info = self.metadata(name)
        if not stat.S_ISDIR(info.st_mode):
            return
        fd = self.open(name, directory=True)
        try:
            with os.scandir(fd) as entries:
                names = []
                for item in entries:
                    names.append(item.name)
                    if len(names) > 128 or len(self.rows) > 1024:
                        raise ValueError('entry_limit')
            if names and depth == 0:
                raise ValueError('depth_limit')
            for leaf in sorted(names):
                child = name + '/' + leaf
                self.attempt(child, lambda child=child: self.tree(child, depth - 1))
        finally:
            os.close(fd)

    def software(self, name):
        self.metadata(name)
        data = self.read(name, 32 * 1024 * 1024)
        self.rows.append(dict(path=name, sha256=hashlib.sha256(data).hexdigest()))

    def env_state(self, name, keys):
        self.metadata(name)
        values = {}
        suppressed = 0
        for line in self.read(name).decode('utf-8').splitlines():
            key, sep, value = line.partition('=')
            if key not in keys:
                suppressed += 1
                continue
            if not sep or key in values or len(value) > 512 or not re.fullmatch(r'[A-Za-z0-9_./: +\-]*', value):
                raise ValueError('invalid_state')
            values[key] = value
        self.rows.append(dict(path=name, fields=values, suppressed_fields=suppressed))

    def json_state(self, name):
        self.metadata(name)
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate_state_key')
                result[key] = value
            return result
        data = json.loads(self.read(name), object_pairs_hook=unique)
        if not isinstance(data, dict) or not isinstance(data.get('files'), dict):
            raise ValueError('invalid_state_shape')
        fields = {}
        for key in ('status', 'service', 'unit', 'greeter_dir_created'):
            if key in data:
                value = data[key]
                valid = ((key == 'status' and value in ('ACTIVE', 'INSTALLING', 'REMOVING')) or
                         (key == 'service' and value in ('active', 'inactive')) or
                         (key == 'unit' and isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value)) or
                         (key == 'greeter_dir_created' and type(value) is bool))
                if not valid:
                    raise ValueError('invalid_state_scalar')
                fields[key] = value
        if 'links' in data:
            expected = {RUNTIME + '/login-early/libfprint-2.so': 'libfprint-2.so.2',
                        RUNTIME + '/login-early/libfprint-2.so.2': 'libfprint-2.so.2.0.0'}
            if data['links'] != expected:
                raise ValueError('unknown_state_links')
            fields['links'] = expected
        files = {}
        for path, row in data['files'].items():
            if path not in EARLY_FILES:
                raise ValueError('unknown_software_path')
            if isinstance(row, dict):
                files[path] = {k: row[k] for k in ('before', 'after', 'mode') if k in row}
                for key, value in files[path].items():
                    if key == 'mode':
                        if type(value) is not int or not 0 <= value <= 0o7777:
                            raise ValueError('invalid_mode')
                    elif not re.fullmatch('[0-9a-f]{64}', str(value)):
                        raise ValueError('invalid_digest')
            elif isinstance(row, str) and re.fullmatch('[0-9a-f]{64}', row):
                files[path] = row
            else:
                raise ValueError('invalid_digest')
        fields['files'] = files
        self.rows.append(dict(path=name, fields=fields))

    def sudo_config(self, name):
        self.software(name)
        text = self.read(name).decode('utf-8')
        # Report selector scopes without disclosing unrelated sudo command arguments.
        selectors, includes = [], []
        logical = text.replace('\\\n', ' ')
        for line in logical.splitlines():
            line = line.strip()
            if line.startswith(('#include', '@include')):
                includes.append(line[:512])
            if line.startswith('Defaults') and re.search(r'\bpam_(?:login_)?service\b', line):
                selectors.append(dict(scope=line.split()[0], values=re.findall(
                    r'\b(pam_(?:login_)?service)\s*=\s*([A-Za-z0-9_./"\-]+)', line)))
        self.rows.append(dict(path=name, selectors=selectors, includes=includes,
                              parser='LEXICAL_ONLY_NOT_EFFECTIVE_SUDO_POLICY'))

    def collect(self):
        for path, depth in ((CONFIG, 2), ('/etc/sudoers.d', 1),
                ('/var/lib/fprint', 5), ('/var/lib/goodix-5125-poc', 2),
                ('/var/lib/goodix-5125-staging', 2),
                ('/var/lib/goodix-d297-01-kscreenlocker', 1),
                ('/var/lib/goodix-27c6-5125-managed', 0),
                ('/var/lib/goodix-polkit', 0),
                ('/var/lib/authselect/backups/d285-01-20260911T163528Z-a9e234e43d2b', 1),
                ('/var/lib/selinux/targeted/active/modules/400/goodix_fprint_account_delete', 1)):
            self.attempt(path, lambda: self.tree(path, depth))
        for leaf, (prefix, suffixes) in STATE_KEYS.items():
            path = CONFIG + '/' + leaf
            self.attempt(path, lambda: self.env_state(path, {prefix + x for x in suffixes.split()}))
        path = '/var/lib/goodix-d297-01-kscreenlocker/state'
        self.attempt(path, lambda: self.env_state(path, {
            'SOURCE_COMMIT', 'VENDOR_SHA256', 'MANAGED_SHA256', 'ACTIVE_HOST_DEPLOYMENT_MODE'}))
        for path in (CONFIG + '/login-early.json', CONFIG + '/login-three-backup/snapshot.json'):
            self.attempt(path, lambda: self.json_state(path))
        paths = [CONFIG + '/d297-02-local.previous-dropin']
        paths += [CONFIG + '/login-three-backup/' + str(i) for i in range(8)]
        paths += ['/var/lib/goodix-d297-01-kscreenlocker/kde-fingerprint.' + x
                  for x in ('vendor', 'managed')]
        paths += [RUNTIME + '/' + rt + '/' + file for rt in RUNTIMES for file in SOFTWARE]
        for path in paths:
            self.attempt(path, lambda: self.software(path))
        for path in ('/etc/sudoers', '/etc/sudo.conf'):
            self.attempt(path, lambda: self.sudo_config(path))
        def fragments():
            fd = self.open('/etc/sudoers.d', directory=True)
            try:
                with os.scandir(fd) as entries:
                    for index, item in enumerate(entries):
                        if index >= 32:
                            raise ValueError('sudoers_fragment_limit')
                        path = '/etc/sudoers.d/' + item.name
                        self.attempt(path, lambda: self.sudo_config(path))
            finally:
                os.close(fd)
        self.attempt('/etc/sudoers.d', fragments)
        return dict(schema=1, outcome='REVIEW_REQUIRED', unknown_stop_count=self.issues,
                    host_mutation=False, sensor_access=False, records=self.rows)


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0:
        print('INVENTORY=REFUSED requires_existing_root_shell no_sudo_or_authentication_by_script')
        return 2
    print(json.dumps(Inventory().collect(), indent=2, sort_keys=True))
    return 0  # A collected report is never migration approval.


if __name__ == '__main__':
    sys.exit(main())
