#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""One temporary overlay on the observed D293 deployment; no material access."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

RUNTIME = '/usr/local/lib64/goodix-27c6-5125/login-same-action'
WRAPPER = '/usr/local/sbin/goodix-login-same-action-fprintd'
DROPIN = '/etc/systemd/system/fprintd.service.d/96-goodix-login-same-action.conf'
PAM = '/etc/pam.d/plasmalogin'
STATE = '/etc/goodix-27c6-5125/login-same-action.json'
PREVIOUS = '/usr/local/sbin/goodix-d293-native-fprintd'
DAEMON = '/usr/libexec/fprintd'
VENDOR_PAM = '/usr/lib/pam.d/plasmalogin'
LIBS = ('libfprint-2.so.2.0.0', 'libgusb.so.2', 'libopencv_core.so.413',
        'libopencv_features2d.so.413', 'libopencv_flann.so.413', 'libopencv_imgproc.so.413')
FILES = (*LIBS, 'PROVENANCE', 'source-files.sha256')
BASE_RUNTIME = '/usr/local/lib64/goodix-27c6-5125/d293-native-e61fce313794922a2dab156a1b38a8ddc5837f19'
BASELINE = {
    PREVIOUS: 'ea0f5c0ebc2bb9524943fef0921f2d0ff845380d35d43d7112c3d0df357f78d2',
    '/etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf':
        '91432adc0299628455f98772a42341b7b1fccc432fd85fcb1928eafa75523247',
    DAEMON: '2353dafe60cf731b5cefe8c7ecc1350b151b20b17e9f8d886cfeeb605064403f',
    VENDOR_PAM: '559910be8631f69398332b2979bd5c18f1155a7af0960215d175694082cae2ac',
    BASE_RUNTIME + '/libfprint-2.so.2.0.0':
        '115db4450272435c80ecb61e3540577b99c8355fb02a0f1648175104a7c3dd20',
}
BASELINE.update({BASE_RUNTIME + '/' + name: sha for name, sha in zip(LIBS[1:], (
    '86dd7a7ca9cc621f3bb7f9320d6dfe01d04528dbe7152722b617e0838d7eb9cd',
    'a52af4e78a69e2181a265fb816881a49a556602816d3e13c54cf478d8901d38d',
    '6885430e36f705aeeb15bea7ac47abfef57b606819d30c83ca063bf93456221f',
    '09405e8a9d412d69102a611b2311e6161c635266d1846d6253c3f360a84d7041',
    'c3c3e85cd1c14936ab65df110ac9261487f66adefb219893ea30f9338b4234c4'))})


def p(name):
    return Path(name)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(name):
    path = p(name)
    require(path.is_file() and not path.is_symlink(), f'not a regular file: {name}')
    return path.read_bytes()


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def service_state():
    value = run('systemctl', 'show', '-p', 'ActiveState', '--value', 'fprintd.service')
    require(value in ('active', 'inactive'), f'unsupported service state: {value}')
    return value


def effective(wrapper):
    value = run('systemctl', 'show', '-p', 'ExecStart', '--value', 'fprintd.service')
    require(f'path={wrapper} ; argv[]={wrapper} ;' in value, 'unexpected effective ExecStart')


def baseline():
    for name, expected in BASELINE.items():
        require(digest(read(name)) == expected, f'baseline changed: {name}')
    for name, target in (('libfprint-2.so.2', 'libfprint-2.so.2.0.0'),
                         ('libfprint-2.so', 'libfprint-2.so.2')):
        link = p(BASE_RUNTIME + '/' + name)
        require(link.is_symlink() and os.readlink(link) == target, f'baseline link changed: {name}')


def write(name, data, mode=0o644):
    dest = p(name)
    require(dest.parent.is_dir(), f'missing parent: {dest.parent}')
    fd, temp = tempfile.mkstemp(prefix='.same-action-', dir=dest.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, dest)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def restore_service(previous):
    run('systemctl', 'daemon-reload')
    run('systemctl', 'start' if previous == 'active' else 'stop', 'fprintd.service')
    require(service_state() == previous, 'service state not restored')


def validate_owned(state, partial=False):
    expected = {RUNTIME + '/' + x for x in (*FILES, 'SHA256SUMS')} | {PAM, WRAPPER, DROPIN}
    require(set(state['files']) == expected, 'invalid rollback file set')
    require(state['links'] == {RUNTIME + '/libfprint-2.so.2': 'libfprint-2.so.2.0.0',
                               RUNTIME + '/libfprint-2.so': 'libfprint-2.so.2'},
            'invalid rollback link set')
    require(not p(RUNTIME).is_symlink(), 'runtime replaced by symlink')
    for name, sha in state['files'].items():
        if partial and not p(name).exists() and not p(name).is_symlink():
            continue
        require(digest(read(name)) == sha, f'overlay changed; refusing removal: {name}')
    for name, target in state['links'].items():
        if partial and not p(name).exists() and not p(name).is_symlink():
            continue
        require(p(name).is_symlink() and os.readlink(p(name)) == target, f'link changed: {name}')
    if p(RUNTIME).exists():
        expected = {Path(x).name for x in (*state['files'], *state['links']) if x.startswith(RUNTIME + '/')}
        require({x.name for x in p(RUNTIME).iterdir()} <= expected, 'unexpected file in overlay runtime')


def remove_owned(state):
    # Original files are never overwritten. The sole PAM override was absent.
    for name in (*state['files'], *state['links']):
        if p(name).exists() or p(name).is_symlink():
            p(name).unlink()
    if p(RUNTIME).exists():
        p(RUNTIME).rmdir()


def rollback():
    if not p(STATE).exists():
        require(not any(p(x).exists() or p(x).is_symlink() for x in (RUNTIME, WRAPPER, DROPIN)),
                'overlay exists without rollback state')
        print('SAME_ACTION_ROLLBACK=ALREADY_ABSENT')
        return
    state = json.loads(read(STATE))
    baseline()
    require(state['status'] in ('ACTIVE', 'INSTALLING', 'REMOVING'), 'invalid rollback status')
    validate_owned(state, partial=state['status'] != 'ACTIVE')
    run('systemctl', 'stop', 'fprintd.service')
    require(service_state() == 'inactive', 'service did not stop')
    state['status'] = 'REMOVING'
    write(STATE, json.dumps(state).encode(), 0o600)
    remove_owned(state)
    restore_service(state['service'])
    effective(PREVIOUS)
    require(digest(run('systemctl', 'cat', 'fprintd.service').encode()) == state['unit'],
            'original service definition changed')
    p(STATE).unlink()
    print('SAME_ACTION_ROLLBACK=PASS previous=D293 PAM=vendor')


def install(candidate):
    baseline()
    if p(STATE).exists():
        state = json.loads(read(STATE))
        require(state['status'] == 'ACTIVE', 'interrupted installation: run rollback.sh')
        validate_owned(state)
        effective(WRAPPER)
        print('SAME_ACTION_INSTALL=ALREADY_ACTIVE')
        return
    effective(PREVIOUS)
    for name in (RUNTIME, WRAPPER, DROPIN, PAM, STATE):
        require(not p(name).exists() and not p(name).is_symlink(), f'expected absent: {name}')
    require(p(STATE).parent.is_dir(), 'missing D293 state directory')
    candidate = Path(candidate)
    rows = [line.split() for line in (candidate / 'SHA256SUMS').read_text().splitlines()]
    require(all(len(row) == 2 for row in rows), 'invalid candidate manifest')
    hashes = {name: sha for sha, name in rows}
    require(len(rows) == len(FILES) and set(hashes) == set(FILES), 'candidate file set mismatch')
    payload = {}
    for name in FILES:
        file = candidate / name
        require(file.is_file() and not file.is_symlink(), f'invalid candidate file: {name}')
        data = file.read_bytes()
        require(digest(data) == hashes[name], f'candidate hash mismatch: {name}')
        payload[RUNTIME + '/' + name] = data
    payload[RUNTIME + '/SHA256SUMS'] = (candidate / 'SHA256SUMS').read_bytes()
    pam = read(VENDOR_PAM)
    before = b'/usr/lib64/security/pam_fprintd.so max-tries=3 timeout=45 debug'
    require(pam.count(before) == 1, 'unexpected Plasma PAM fingerprint rule')
    payload[PAM] = pam.replace(before, b'/usr/lib64/security/pam_fprintd.so max-tries=1 timeout=20 debug')
    payload[WRAPPER] = f'''#!/usr/bin/env bash
set -euo pipefail
[[ $(sha256sum {DAEMON} | cut -d' ' -f1) == {BASELINE[DAEMON]} ]] || exit 126
cd {RUNTIME}
[[ -L libfprint-2.so.2 && $(readlink libfprint-2.so.2) == libfprint-2.so.2.0.0 ]] || exit 126
[[ -L libfprint-2.so && $(readlink libfprint-2.so) == libfprint-2.so.2 ]] || exit 126
sha256sum -c SHA256SUMS >/dev/null
sed 's/^/GOODIX_SAME_ACTION_BUILD /' PROVENANCE >&2
exec env LD_LIBRARY_PATH={RUNTIME} FP_DRIVERS_ALLOWLIST=goodix_27c6_5125 {DAEMON}
'''.encode()
    payload[DROPIN] = f'[Service]\nExecStart=\nExecStart={WRAPPER}\n'.encode()
    state = dict(status='INSTALLING', service=service_state(),
                 unit=digest(run('systemctl', 'cat', 'fprintd.service').encode()),
                 files={name: digest(data) for name, data in payload.items()},
                 links={RUNTIME + '/libfprint-2.so.2': 'libfprint-2.so.2.0.0',
                        RUNTIME + '/libfprint-2.so': 'libfprint-2.so.2'})
    write(STATE, json.dumps(state).encode(), 0o600)
    try:
        run('systemctl', 'stop', 'fprintd.service')
        require(service_state() == 'inactive', 'service did not stop')
        p(RUNTIME).mkdir(mode=0o755)
        os.chmod(p(RUNTIME), 0o755)
        for name, data in payload.items():
            write(name, data, 0o755 if name == WRAPPER else 0o644)
        for name, target in state['links'].items():
            p(name).symlink_to(target)
        run('restorecon', '-RF', RUNTIME, WRAPPER, DROPIN, PAM, STATE)
        restore_service(state['service'])
        effective(WRAPPER)
        validate_owned(state)
        state['status'] = 'ACTIVE'
        write(STATE, json.dumps(state).encode(), 0o600)
    except BaseException:
        # Keep the state if recovery fails; rollback.sh can complete it.
        rollback()
        raise
    print('SAME_ACTION_INSTALL=PASS max_tries=1 timeout=20 rollback=REQUIRED_AFTER_TEST')


if __name__ == '__main__':
    try:
        require(os.geteuid() == 0, 'installation/rollback requires user-invoked sudo')
        if len(sys.argv) == 3 and sys.argv[1] == 'install':
            install(sys.argv[2])
        elif sys.argv[1:] == ['rollback']:
            rollback()
        else:
            raise RuntimeError('usage: transaction.py install CANDIDATE | rollback')
    except Exception as error:
        print(f'SAME_ACTION_TRANSACTION=FAIL {error}', file=sys.stderr)
        sys.exit(1)
