#!/usr/bin/python3 -I
# SPDX-License-Identifier: GPL-2.0-or-later
"""Standalone R5 removal. Installed as both user commands; no saved code executed."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

CONFIG = Path('/etc/pam.d/plasmalogin')
SUPPORT = Path('/usr/local/lib64/goodix-plasma-login')
RUNTIME = Path('/usr/local/lib64/goodix-27c6-5125')
DROPIN = Path('/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf')
NORMAL = Path('/usr/local/bin/goodix-uninstall')
FORCE = Path('/usr/local/bin/goodix-force-remove')
RECOVERY = Path('/usr/local/share/goodix-recovery')
MATERIAL = Path('/var/lib/goodix-5125-poc')
MATERIAL_NAMES = ('target-material-manifest.json', 'transport-material.bin',
                  'target-config-90.bin', 'gfusb.dll', 'fdt-cache.bin')
RULE = r'/var/lib/goodix-5125-poc(/.*)?'
MODULE = 'pam_goodix_login_gate.so'
LIBRARIES = ('libfprint-2.so.2.0.0',) + tuple(
    'libopencv_' + part + '.so.413' for part in ('core', 'features2d', 'flann', 'imgproc'))
RUNTIME_FILES = set(LIBRARIES) | {
    'OpenCV-LICENSES.txt', 'source-files.tsv', 'source-files.sha256',
    'LICENSING_AND_PROVENANCE.md', 'build-provenance.txt', 'SHA256SUMS',
    'deploy.py', 'uninstall.sh',
    *('licenses/' + name + '.txt' for name in
      ('GPL-2.0-or-later', 'LGPL-2.1-or-later', 'GPL-3.0-or-later', 'Apache-2.0'))}
LINKS = {'libfprint-2.so.2': 'libfprint-2.so.2.0.0', 'libfprint-2.so': 'libfprint-2.so.2'}
DROPIN_BYTES = b'[Service]\nEnvironment=LD_LIBRARY_PATH=/usr/local/lib64/goodix-27c6-5125\n'
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def present(path):
    return path.exists() or path.is_symlink()


def parents(path):
    # Never follow a redirected parent into unrelated data. Missing parents
    # simply mean this artifact is absent; this is not a Fedora layout gate.
    for parent in reversed(path.parents):
        if present(parent):
            require(stat.S_ISDIR(parent.lstat().st_mode), f'redirected parent: {parent}')


def trusted(path, directory=False):
    parents(path)
    info = path.lstat()
    require((stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode)
            and (info.st_uid, info.st_gid) == (0, 0) and not info.st_mode & 0o022,
            f'project ownership/type/mode drift: {path}')


def read(path):
    trusted(path)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), f'not regular: {path}')
        return stream.read()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_files(directory, hashes, expected):
    require(isinstance(hashes, dict) and set(hashes) == expected, f'invalid project file list: {directory}')
    for name, checksum in hashes.items():
        require(isinstance(checksum, str) and re.fullmatch('[0-9a-f]{64}', checksum), 'invalid project checksum')
        require(digest(read(directory / name)) == checksum, f'project file drift: {directory / name}')


def normal_preflight():
    """Check only our receipts and software, before ANY mutation or service action."""
    parents(CONFIG)
    parents(DROPIN)
    owned_rule = False
    if present(SUPPORT):
        trusted(SUPPORT, directory=True)
        receipt = json.loads(read(SUPPORT / 'receipt.json'))
        require(isinstance(receipt, dict), 'invalid login receipt')
        require(receipt.get('schema') == 1 and isinstance(receipt.get('source_commit'), str)
                and re.fullmatch('[0-9a-f]{40}', receipt['source_commit']), 'invalid login receipt')
        require({p.name for p in SUPPORT.iterdir()} == {MODULE, 'manage.py', 'receipt.json'}, 'partial/drifted login support')
        verify_files(SUPPORT, receipt.get('files'), {MODULE, 'manage.py'})
        require(digest(read(CONFIG)) == receipt.get('config_sha256'), 'project PAM configuration drift')
    else:
        require(not present(CONFIG), 'PAM override without project receipt')
    if present(RUNTIME):
        trusted(RUNTIME, directory=True)
        receipt = json.loads(read(RUNTIME / 'installation.json'))
        require(isinstance(receipt, dict), 'invalid runtime receipt')
        require(receipt.get('schema') == 1 and receipt.get('build_commit') ==
                'b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226', 'unknown runtime receipt')
        trusted(RUNTIME / 'licenses', directory=True)
        require({str(p.relative_to(RUNTIME)) for p in RUNTIME.rglob('*')} ==
                RUNTIME_FILES | set(LINKS) | {'licenses', 'installation.json'}, 'partial/drifted runtime contents')
        verify_files(RUNTIME, receipt.get('files'), RUNTIME_FILES)
        for name, target in LINKS.items():
            require((RUNTIME / name).is_symlink() and os.readlink(RUNTIME / name) == target, 'project library link drift')
        require(read(DROPIN) == DROPIN_BYTES, 'project drop-in drift')
        record = receipt.get('material_selinux')
        if record is not None:
            require(isinstance(record, dict) and record.get('rule') == RULE
                    and type(record.get('owned')) is bool
                    and type(record.get('preexisting')) is bool
                    and record['owned'] != record['preexisting']
                    and record.get('phase') == 'ready', 'uncertain project label ownership')
            owned_rule = record['owned']
    else:
        require(not present(DROPIN), 'runtime drop-in without project receipt')
    trusted(RECOVERY, directory=True)
    receipt = json.loads(read(RECOVERY / 'receipt.json'))
    require(isinstance(receipt, dict), 'invalid recovery receipt')
    require(receipt.get('schema') == 1 and set(receipt.get('files', {})) == {NORMAL.name, FORCE.name}, 'invalid recovery receipt')
    require({p.name for p in RECOVERY.iterdir()} == {'receipt.json'}, 'recovery directory drift')
    for path in (NORMAL, FORCE):
        require(digest(read(path)) == receipt['files'][path.name], f'recovery command drift: {path}')
    return owned_rule


def command(*args):
    result = subprocess.run(args, env=ENV, text=True, capture_output=True, timeout=30)
    # An already removed Fedora service has no loaded project code to stop.
    # This is an absent-target result, never a vendor-file/version precondition.
    if args == ('systemctl', 'stop', 'fprintd.service') and result.returncode != 0:
        if result.stderr.strip() in (
                'Failed to stop fprintd.service: Unit fprintd.service not loaded.',
                'Failed to stop fprintd.service: Unit fprintd.service not found.'):
            return result.stdout
    require(result.returncode == 0, f'{args[0]}: {result.stderr.strip() or result.stdout.strip() or result.returncode}')
    return result.stdout


def remove_path(path):
    parents(path)
    if not present(path):
        return
    if stat.S_ISDIR(path.lstat().st_mode):
        # These are exclusively project-owned trees; rmtree does not follow links.
        require(path in (SUPPORT, RUNTIME, RECOVERY), f'unexpected directory at file path: {path}')
        shutil.rmtree(path)
    else:
        path.unlink()


def remove_label():
    # Query/delete only the exact project customization. No Fedora version,
    # vendor PAM, receipt, material content, or historical labels are consulted.
    def rule_present():
        listing = command('semanage', 'fcontext', '-l', '-C', '-n')
        return any(line.split(maxsplit=1)[0] == RULE for line in listing.splitlines() if line.strip())
    if rule_present():
        command('semanage', 'fcontext', '-d', '-f', 'a', RULE)
    require(not rule_present(), 'project SELinux mapping remains')
    paths = []
    for path in (MATERIAL, *(MATERIAL / name for name in MATERIAL_NAMES)):
        parents(path)
        if present(path):
            info = path.lstat()
            require(stat.S_ISDIR(info.st_mode) if path == MATERIAL else
                    stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                    f'material path is redirected/shared; preserved: {path}')
            paths.append(str(path))
    if paths:
        # Only current Fedora policy supplies labels. No recursive walk/content IO.
        command('restorecon', '-F', '--', *paths)


def remove(force=False):
    owned_rule = True if force else normal_preflight()
    errors = []

    def attempt(label, action):
        try:
            action()
            return True
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append(f'{label}: {error}')
            return False

    # Disarm entry points BEFORE touching their dependencies or service state.
    login_removed = attempt('login entry', lambda: remove_path(CONFIG))
    runtime_detached = attempt('runtime entry', lambda: remove_path(DROPIN))
    attempt('service reload', lambda: command('systemctl', 'daemon-reload'))
    attempt('stop fingerprint service', lambda: command('systemctl', 'stop', 'fprintd.service'))
    # Never start fprintd or restart a login/desktop service during removal.
    if login_removed:
        attempt('login support', lambda: remove_path(SUPPORT))
    labels_removed = True
    if owned_rule:
        labels_removed = attempt('project material labels', remove_label)
    if runtime_detached and labels_removed:
        # Retain the ownership receipt if label cleanup fails. A later normal
        # invocation must not mistake the remaining label effect for absence.
        attempt('runtime files', lambda: remove_path(RUNTIME))
    # Do not remove shared parent directories or unrelated drop-ins.
    if not errors:
        attempt('recovery receipt', lambda: remove_path(RECOVERY))
    if not errors:
        attempt('normal removal command', lambda: remove_path(NORMAL))
    if not errors:
        attempt('emergency command', lambda: remove_path(FORCE))
    if errors:
        print('GOODIX_REMOVAL=INCOMPLETE; recovery command retained where possible.', file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        print('Keep the reader disconnected. Report this final output before continuing.', file=sys.stderr)
        return 1
    print('GOODIX_REMOVAL=PASS GOODIX_PROJECT_IN_CRITICAL_AUTH_PATH=false FEDORA_CURRENT_STATE_EXPOSED=true')
    print('Materials and fingerprint templates preserved. No Fedora files restored.')
    print('Restart the computer normally to close any old authentication sessions.')
    return 0


def main():
    name = Path(sys.argv[0]).name
    require(name in (NORMAL.name, FORCE.name), 'use the installed goodix-uninstall or goodix-force-remove command')
    if sys.argv[1:] == ['--help']:
        print(name + ': remove Goodix software; preserve device materials and fingerprint templates. Requests sudo when needed.')
        return 0
    require(len(sys.argv) == 1, 'this command takes no arguments')
    if os.geteuid() != 0:
        # Fixed root-owned installed path, never sudo a script selected by cwd/PATH.
        path = FORCE if name == FORCE.name else NORMAL
        os.execve('/usr/bin/sudo', ['sudo', '--', '/usr/bin/python3', '-I', '-B', str(path)], ENV)
    return remove(force=name == FORCE.name)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f'GOODIX_REMOVAL=STOP {error}. Use goodix-force-remove for emergency removal.', file=sys.stderr)
        sys.exit(1)
