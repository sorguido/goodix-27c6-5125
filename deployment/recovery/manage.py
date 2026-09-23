#!/usr/bin/python3 -I
# SPDX-License-Identifier: GPL-2.0-or-later
"""Install/remove only the R5 recovery commands, never runtime or authentication."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMMANDS = (Path('/usr/local/bin/goodix-uninstall'), Path('/usr/local/bin/goodix-force-remove'))
SUPPORT = Path('/usr/local/share/goodix-recovery')
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def run(*args):
    return subprocess.run(args, check=True, env=ENV, capture_output=True, text=True).stdout.strip()


def present(path):
    return path.exists() or path.is_symlink()


def trusted(path, directory=False):
    metadata = path.lstat()
    require((stat.S_ISDIR if directory else stat.S_ISREG)(metadata.st_mode)
            and metadata.st_uid == metadata.st_gid == 0 and not metadata.st_mode & 0o022,
            f'unsafe recovery path: {path}')


def parents(path):
    for parent in path.parents:
        trusted(parent, directory=True)


def gate():
    require(os.geteuid() == 0, 'root required')
    run('systemd-detect-virt', '--vm', '--quiet')
    for device in Path('/sys/bus/usb/devices').iterdir():
        vendor = device / 'idVendor'
        if vendor.exists() and vendor.read_text().strip().lower() == '27c6':
            require((device / 'idProduct').read_text().strip().lower() != '5125',
                    'detach the Goodix reader before installing/removing recovery tooling')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect():
    trusted(SUPPORT, directory=True)
    require({p.name for p in SUPPORT.iterdir()} == {'receipt.json'}, 'recovery support drift')
    trusted(SUPPORT / 'receipt.json')
    receipt = json.loads((SUPPORT / 'receipt.json').read_bytes())
    require(isinstance(receipt, dict), 'invalid recovery receipt')
    require(receipt.get('schema') == 1 and set(receipt.get('files', {})) == {p.name for p in COMMANDS},
            'invalid recovery receipt')
    for path in COMMANDS:
        trusted(path)
        require(stat.S_IMODE(path.lstat().st_mode) == 0o755, f'recovery command is not executable with mode 0755: {path}')
        require(digest(path.read_bytes()) == receipt['files'][path.name], f'recovery command drift: {path}')
    return receipt


def install():
    for path in (*COMMANDS, SUPPORT):
        parents(path)
    payload = (HERE / 'remove.py').read_bytes()
    git_args = ('git', '-c', f'safe.directory={ROOT}', '-C', str(ROOT))
    require(run(*git_args, 'branch', '--show-current') == 'development', 'development required')
    require(not run(*git_args, 'status', '--porcelain'), 'clean committed checkout required')
    source = run(*git_args, 'rev-parse', 'HEAD')
    if any(present(p) for p in (*COMMANDS, SUPPORT)):
        receipt = inspect()
        require(all(value == digest(payload) for value in receipt['files'].values()),
                'different recovery version installed; retain for review')
        print('GOODIX_RECOVERY_INSTALL=ALREADY_INSTALLED')
        return
    created = []
    try:
        SUPPORT.mkdir(mode=0o755)
        SUPPORT.chmod(0o755)
        created.append(SUPPORT)
        receipt = {'schema': 1, 'source_commit': source,
                   'files': {p.name: digest(payload) for p in COMMANDS}}
        for path, data, mode in [*( (p, payload, 0o755) for p in COMMANDS ),
                                 (SUPPORT / 'receipt.json', (json.dumps(receipt, sort_keys=True) + '\n').encode(), 0o644)]:
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
                created.append(path)
                stream.write(data)
                stream.flush()
                os.fchmod(stream.fileno(), mode)
                os.fsync(stream.fileno())
        run('restorecon', '-F', str(SUPPORT), str(SUPPORT / 'receipt.json'), *(str(p) for p in COMMANDS))
        inspect()
    except BaseException:
        for path in reversed(created):
            path.rmdir() if path == SUPPORT else path.unlink()
        raise
    print('GOODIX_RECOVERY_INSTALL=PASS SOURCE_COMMIT=' + source)


def uninstall():
    for path in (*COMMANDS, SUPPORT):
        parents(path)
    if not any(present(p) for p in (*COMMANDS, SUPPORT)):
        print('GOODIX_RECOVERY_ROLLBACK=ALREADY_ABSENT')
        return
    inspect()
    for path in COMMANDS:
        path.unlink()
    (SUPPORT / 'receipt.json').unlink()
    SUPPORT.rmdir()
    print('GOODIX_RECOVERY_ROLLBACK=PASS RUNTIME_AND_LOGIN_UNCHANGED=true')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'uninstall'))
    args = parser.parse_args()
    if os.geteuid() != 0:
        os.execve('/usr/bin/sudo', ['sudo', '--', '/usr/bin/python3', '-I', '-B',
                                   str(HERE / 'manage.py'), args.action], ENV)
    gate()
    install() if args.action == 'install' else uninstall()


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        sys.exit(f'GOODIX_RECOVERY=STOP {error}')
