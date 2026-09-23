#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Human-only VM install/inverse; no authentication or service operations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import tempfile

CONFIG = Path('/etc/pam.d/plasmalogin')
SUPPORT = Path('/usr/local/lib64/goodix-plasma-login')
VENDOR = Path('/usr/lib/pam.d/plasmalogin')
USB = Path('/sys/bus/usb/devices')
OWNER = (0, 0)
MODULE = 'pam_goodix_login_gate.so'
INPUTS = (MODULE, 'plasmalogin.pam', 'manage.py', 'SOURCE_COMMIT')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def environment():
    require(os.geteuid() == 0, 'root required; run only at the human installation gate')
    run('systemd-detect-virt', '--vm', '--quiet')
    release = platform.freedesktop_os_release()
    require(release.get('ID') == 'fedora' and release.get('VERSION_ID') == '44'
            and platform.machine() == 'x86_64', 'Fedora 44 x86_64 VM required')
    require(run('getenforce') == 'Enforcing', 'SELinux Enforcing required')
    require(USB.is_dir(), 'USB presence metadata unavailable')
    for device in USB.iterdir():
        vendor = device / 'idVendor'
        if vendor.exists() and vendor.read_text().strip().lower() == '27c6':
            require((device / 'idProduct').read_text().strip().lower() != '5125',
                    'detach Goodix 27c6:5125 before installation/removal')


def trusted(path, directory=False, mode=None):
    metadata = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    require(kind(metadata.st_mode) and (metadata.st_uid, metadata.st_gid) == OWNER
            and not metadata.st_mode & 0o022, f'untrusted ownership/type/mode: {path}')
    if mode is not None:
        require(stat.S_IMODE(metadata.st_mode) == mode, f'unexpected mode: {path}')


def parents(path):
    for parent in path.parents:
        trusted(parent, directory=True)


def vendor_ready():
    parents(VENDOR)
    trusted(VENDOR)
    require(run('rpm', '-qf', '--qf', '%{NAME}\n', str(VENDOR)) == 'plasma-login-manager',
            'current vendor PAM must belong to plasma-login-manager')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
        require(stat.S_ISREG(os.fstat(source.fileno()).st_mode), f'not a regular file: {path}')
        return source.read()


def candidate(directory):
    content = {name: read_regular(directory / name) for name in INPUTS}
    require(re.fullmatch(rb'[0-9a-f]{40}\n', content['SOURCE_COMMIT']), 'invalid source commit')
    require(read_regular(directory / 'VM_TESTS_PASS') == b'PASS\n', 'VM offline tests not recorded PASS')
    rows = read_regular(directory / 'SHA256SUMS').decode().splitlines()
    expected = {f'{digest(data)}  {name}' for name, data in content.items()}
    require(len(rows) == len(INPUTS) and set(rows) == expected, 'candidate digest/manifest mismatch')
    require(content['manage.py'] == Path(__file__).read_bytes(), 'invoke candidate manage.py')
    return content


def present(path):
    return path.exists() or path.is_symlink()


def record(path, created):
    item = path.lstat()
    created.append((path, item.st_dev, item.st_ino))


def write_new(path, data, created):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as target:
        record(path, created)
        target.write(data)
        target.flush()
        os.fchown(target.fileno(), *OWNER)
        os.fchmod(target.fileno(), 0o644)
        os.fsync(target.fileno())


def rollback_created(created):
    errors = []
    for path, device, inode in reversed(created):
        try:
            if not present(path):
                continue
            item = path.lstat()
            require((item.st_dev, item.st_ino) == (device, inode), f'changed during cleanup: {path}')
            path.rmdir() if stat.S_ISDIR(item.st_mode) else path.unlink()
        except OSError as error:
            errors.append(str(error))
        except RuntimeError as error:
            errors.append(str(error))
    require(not errors, 'partial install cleanup failed: ' + '; '.join(errors))


def install(directory):
    environment()
    vendor_ready()
    parents(CONFIG)
    parents(SUPPORT)
    require(not present(CONFIG) and not present(SUPPORT), 'project path collision; uninstall before reinstall')
    content = candidate(directory)
    receipt = {'schema': 1, 'source_commit': content['SOURCE_COMMIT'].decode().strip(),
               'files': {name: digest(content[name]) for name in (MODULE, 'manage.py')},
               'config_sha256': digest(content['plasmalogin.pam'])}
    created = []
    try:
        SUPPORT.mkdir(mode=0o755)
        record(SUPPORT, created)
        os.chown(SUPPORT, *OWNER)
        SUPPORT.chmod(0o755)
        trusted(SUPPORT, directory=True, mode=0o755)
        for name in (MODULE, 'manage.py'):
            write_new(SUPPORT / name, content[name], created)
        write_new(SUPPORT / 'receipt.json', (json.dumps(receipt, sort_keys=True) + '\n').encode(), created)
        fd, pending_name = tempfile.mkstemp(prefix='.goodix-plasmalogin.', dir=CONFIG.parent)
        pending = Path(pending_name)
        record(pending, created)
        with os.fdopen(fd, 'wb') as target:
            target.write(content['plasmalogin.pam'])
            target.flush()
            os.fchown(target.fileno(), *OWNER)
            os.fchmod(target.fileno(), 0o644)
            os.fsync(target.fileno())
        require(run('matchpathcon', '-n', str(pending)) == run('matchpathcon', '-n', str(CONFIG)),
                'temporary and final PAM SELinux contexts differ')
        run('restorecon', '-F', str(SUPPORT), *(str(SUPPORT / name) for name in (MODULE, 'manage.py', 'receipt.json')), str(pending))
        vendor_ready()
        os.link(pending, CONFIG, follow_symlinks=False)  # Atomic publication; never overwrite.
        record(CONFIG, created)
        pending.unlink()
    except BaseException:
        rollback_created(created)
        raise
    print('PLASMA_LOGIN_INSTALL=PASS')


def uninstall():
    environment()
    parents(CONFIG)
    parents(SUPPORT)
    if not present(SUPPORT):
        require(not present(CONFIG), 'foreign PAM configuration; no project receipt')
        print('PLASMA_LOGIN_UNINSTALL=ALREADY_ABSENT')
        return
    trusted(SUPPORT, directory=True, mode=0o755)
    entries = {p.name for p in SUPPORT.iterdir()}
    if not entries and not present(CONFIG):
        SUPPORT.rmdir()  # Resume an interruption after the last receipt removal.
        print('PLASMA_LOGIN_UNINSTALL=PASS')
        return
    require(entries <= {MODULE, 'manage.py', 'receipt.json'} and 'receipt.json' in entries,
            'unexpected project support contents or missing receipt')
    for name in entries:
        trusted(SUPPORT / name, mode=0o644)
    receipt = json.loads(read_regular(SUPPORT / 'receipt.json'))
    require(isinstance(receipt, dict) and set(receipt) == {'schema', 'source_commit', 'files', 'config_sha256'}
            and receipt['schema'] == 1 and isinstance(receipt['source_commit'], str)
            and re.fullmatch('[0-9a-f]{40}', receipt['source_commit'])
            and isinstance(receipt['files'], dict) and set(receipt['files']) == {MODULE, 'manage.py'},
            'invalid project receipt')
    require(all(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value)
                for value in [receipt['config_sha256'], *receipt['files'].values()]), 'invalid receipt hashes')
    for name in (MODULE, 'manage.py'):
        if name in entries:
            require(digest(read_regular(SUPPORT / name)) == receipt['files'][name], f'project file drift: {name}')
    require(digest(Path(__file__).read_bytes()) == receipt['files']['manage.py'],
            'invoke saved inverse or its identical candidate/repository copy')
    if present(CONFIG):
        trusted(CONFIG, mode=0o644)
        require(digest(read_regular(CONFIG)) == receipt['config_sha256'], 'project PAM configuration drift')
    vendor_ready()  # Current vendor, not an old copy/hash, becomes effective below.
    if present(CONFIG):
        CONFIG.unlink()  # Remove authentication entry point before its dependencies.
    for name in (MODULE, 'manage.py', 'receipt.json'):  # Keep receipt until all payload is removed.
        if name in entries:
            (SUPPORT / name).unlink()
    SUPPORT.rmdir()
    print('PLASMA_LOGIN_UNINSTALL=PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'uninstall'))
    parser.add_argument('build_output', nargs='?', type=Path)
    args = parser.parse_args()
    require((args.action == 'install') == (args.build_output is not None), 'install requires BUILDOUT; uninstall takes no argument')
    install(args.build_output) if args.action == 'install' else uninstall()


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'PLASMA_LOGIN_STOP: {error}')
