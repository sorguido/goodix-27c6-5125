#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""A bounded delta over the frozen early-login overlay; restores exact prior bytes."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('early', HERE.parent / 'login-early/transaction.py')
early = importlib.util.module_from_spec(spec)
spec.loader.exec_module(early)
BACKUP = '/etc/goodix-27c6-5125/login-three-backup'
FILES = ('libfprint-2.so.2.0.0', 'fprintd', 'pam_fprintd.so', 'PROVENANCE', 'source-files.sha256')
TARGETS = tuple(early.RUNTIME + '/' + x for x in FILES) + (early.RUNTIME + '/SHA256SUMS', early.PAM, early.STATE)


def regular(path):
    early.require(path.is_file() and not path.is_symlink(), f'not regular: {path}')
    return path.read_bytes()


def snapshot():
    directory = early.p(BACKUP)
    early.require(directory.is_dir() and not directory.is_symlink(), 'invalid backup directory')
    data = json.loads(regular(directory / 'snapshot.json'))
    early.require(set(data['files']) == set(TARGETS), 'invalid backup target set')
    early.require({p.name for p in directory.iterdir()} == {'snapshot.json', *map(str, range(len(TARGETS)))}, 'unexpected backup file')
    for i, name in enumerate(TARGETS):
        row = data['files'][name]
        early.require(early.digest(regular(directory / str(i))) == row['before'], 'backup digest mismatch')
        early.require(early.digest(early.read(name)) in (row['before'], row['after']), f'local drift: {name}')
    return data


def restore():
    if not early.p(BACKUP).exists():
        print('LOGIN_THREE_ROLLBACK=ALREADY_ABSENT')
        return
    data = snapshot()
    early.run('systemctl', 'stop', 'fprintd.service')
    early.require(early.service_state() == 'inactive', 'fprintd did not stop')
    for i, name in enumerate(TARGETS):
        backup = early.p(BACKUP) / str(i)
        early.write(name, regular(backup), data['files'][name]['mode'])
        early.run('chcon', '--reference=' + str(backup), str(early.p(name)))
    early.validate_owned(json.loads(early.read(early.STATE)))
    early.restore_service(data['service'])
    early.effective(early.WRAPPER)
    for i in range(len(TARGETS)):
        (early.p(BACKUP) / str(i)).unlink()
    (early.p(BACKUP) / 'snapshot.json').unlink()
    early.p(BACKUP).rmdir()
    print('LOGIN_THREE_ROLLBACK=PASS previous=EXACT_EARLY_LOGIN_OVERLAY')


def install(candidate):
    if early.p(BACKUP).exists():
        data = snapshot()
        early.require(all(early.digest(early.read(n)) == row['after'] for n, row in data['files'].items()),
                      'interrupted update: run rollback.sh')
        early.validate_owned(json.loads(early.read(early.STATE)))
        print('LOGIN_THREE_INSTALL=ALREADY_ACTIVE')
        return
    early.baseline()
    state = json.loads(early.read(early.STATE))
    early.require(state['status'] == 'ACTIVE', 'early-login overlay not active')
    early.validate_owned(state)
    early.effective(early.WRAPPER)
    candidate = Path(candidate)
    early.require(candidate.is_dir() and not candidate.is_symlink(), 'invalid candidate directory')
    early.require({x.name for x in candidate.iterdir()} == {*FILES, 'SHA256SUMS'}, 'candidate file set mismatch')
    rows = [line.split() for line in regular(candidate / 'SHA256SUMS').decode().splitlines()]
    early.require(all(len(row) == 2 for row in rows) and len(rows) == len(FILES) and
                  {row[1] for row in rows} == set(FILES), 'candidate manifest mismatch')
    payload = {early.RUNTIME + '/' + name: regular(candidate / name) for name in FILES}
    for sha, name in rows:
        early.require(early.digest(payload[early.RUNTIME + '/' + name]) == sha, 'candidate digest mismatch')
    early.require(b'\nMODE=normal\nPURPOSE=PREPARED_LOGIN_THREE_ATTEMPTS\n' in payload[early.RUNTIME + '/PROVENANCE'], 'wrong candidate purpose/mode')
    pam = early.read(early.PAM)
    before = f'{early.RUNTIME}/pam_fprintd.so max-tries=1 timeout=8'.encode()
    early.require(pam.count(before) == 1, 'unexpected prepared PAM rule')
    payload[early.PAM] = pam.replace(before, before.replace(b'max-tries=1', b'max-tries=3'))
    # Keep untouched libraries/greeter and rebuild the existing runtime index.
    payload[early.RUNTIME + '/SHA256SUMS'] = ''.join(
        f'{early.digest(payload.get(early.RUNTIME + "/" + n, early.read(early.RUNTIME + "/" + n)))}  {n}\n'
        for n in early.FILES).encode()
    for name, contents in payload.items():
        state['files'][name] = early.digest(contents)
    payload[early.STATE] = json.dumps(state).encode()
    data = dict(service=early.service_state(), files={})
    for name in TARGETS:
        mode = stat.S_IMODE(early.p(name).stat().st_mode)
        data['files'][name] = dict(before=early.digest(early.read(name)), after=early.digest(payload[name]), mode=mode)
    directory = early.p(BACKUP)
    early.require(not directory.is_symlink(), 'backup is a symlink')
    directory.mkdir(mode=0o700)
    try:
        for i, name in enumerate(TARGETS):
            shutil.copy2(early.p(name), directory / str(i), follow_symlinks=False)
        early.write(BACKUP + '/snapshot.json', json.dumps(data).encode(), 0o600)
    except Exception:
        # No host payload has changed yet; remove only our incomplete backup.
        for p in directory.iterdir(): p.unlink()
        directory.rmdir()
        raise
    try:
        early.run('systemctl', 'stop', 'fprintd.service')
        early.require(early.service_state() == 'inactive', 'fprintd did not stop')
        for i, name in enumerate(TARGETS):
            early.write(name, payload[name], data['files'][name]['mode'])
            early.run('chcon', '--reference=' + str(directory / str(i)), str(early.p(name)))
        early.validate_owned(state)
        early.restore_service(data['service'])
        early.effective(early.WRAPPER)
        print('LOGIN_THREE_INSTALL=PASS attempts=3 next=normal_login backup=retained')
    except Exception:
        restore()
        raise


if __name__ == '__main__':
    try:
        early.require(os.geteuid() == 0, 'run through install.sh/rollback.sh')
        early.require(len(sys.argv) in (2, 3), 'usage: install CANDIDATE | rollback')
        # Lock the existing directory, without creating another persistent file.
        lock = os.open(str(early.p(early.STATE).parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if sys.argv[1] == 'install' and len(sys.argv) == 3: install(sys.argv[2])
            elif sys.argv[1] == 'rollback' and len(sys.argv) == 2: restore()
            else: raise RuntimeError('invalid command')
        finally:
            os.close(lock)
    except Exception as error:
        print(f'LOGIN_THREE=FAIL reason={error}', file=sys.stderr)
        sys.exit(1)
