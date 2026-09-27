#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Manual temporary deployment. No invocation of sudo inside this program."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
import tarfile
import threading

STATE = Path('/run/goodix-phase-c-zero-mask')
MASK = Path('/run/systemd/system/fprintd.service')
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(directory):
    require(directory.is_dir() and not directory.is_symlink(), 'not a real payload directory')
    entries = list(directory.iterdir())
    require(all(p.is_file() and not p.is_symlink() for p in entries), 'nonregular payload entry')
    manifest = json.loads((directory / 'probe-payload.json').read_text())
    require(manifest.get('schema') == 1 and isinstance(manifest.get('files'), dict), 'wrong schema')
    files = manifest['files']
    fixed = {'probe', 'libfprint-2.so.2', 'source-files.sha256', 'OpenCV-LICENSES.txt',
             'LICENSING_AND_PROVENANCE.md', 'build-provenance.json', 'GPL-2.0-or-later.txt', 'GPL-3.0-or-later.txt',
             'LGPL-2.1-or-later.txt', 'Apache-2.0.txt'}
    dynamic = set(files) - fixed
    require(fixed <= set(files) and len(dynamic) == 4 and
            all(sum(bool(re.fullmatch('libopencv_' + part + r'\.so\.[0-9]+', name))
                    for name in dynamic) == 1 for part in ('core', 'features2d', 'flann', 'imgproc')),
            'unexpected payload inventory')
    require({p.name for p in entries} == set(files) | {'probe-payload.json'}, 'extra/missing payload files')
    require(all(digest(directory / name) == value for name, value in files.items()), 'payload hash mismatch')
    require(digest(directory / 'source-files.sha256') == manifest.get('source_id'), 'source inventory mismatch')
    return manifest


def systemctl(*args):
    subprocess.run(['/usr/bin/systemctl', *args], env=ENV, check=True)


def install(source):
    source = Path(source).resolve(strict=True)
    validate(source)
    require(not STATE.exists() and not STATE.is_symlink(), 'already installed: collect and rollback first')
    STATE.mkdir(mode=0o700)
    try:
        payload = STATE / 'payload'
        payload.mkdir(mode=0o700)
        for p in source.iterdir():
            # O_NOFOLLOW plus the second hash validation also detects source replacement.
            fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as src, (payload / p.name).open('xb') as dst:
                shutil.copyfileobj(src, dst)
            (payload / p.name).chmod(0o700 if p.name == 'probe' else 0o600)
        validate(payload)
        (STATE / 'runs').write_text('0\n')
        subprocess.run([str(payload / 'probe'), '--self-check'], check=True,
                       env=dict(ENV, LD_LIBRARY_PATH=str(payload)))
    except BaseException:
        shutil.rmtree(STATE)
        raise
    print('PROBE_INSTALLED_TEMPORARILY=1 SYSTEM_LIBRARY_REPLACED=0 USB_OPENED=0')


def run(reviewed):
    payload = STATE / 'payload'
    validate(payload)
    count = int((STATE / 'runs').read_text())
    require(count < 2, 'two manual attempts consumed; no further run authorized by this kit')
    require(count == 0 or reviewed, 'run 2 requires --reviewed-run-1 after human log review')
    if count == 0:
        require(not MASK.exists() and not MASK.is_symlink(), 'existing runtime fprintd override: stop')
        (STATE / 'owns-mask').write_text('fprintd.service\n')
        systemctl('mask', '--runtime', '--now', 'fprintd.service')
    require(MASK.is_symlink() and os.readlink(MASK) == '/dev/null', 'temporary exclusion mask missing')
    # Consume the attempt before starting, including failures: never auto retry.
    count += 1
    (STATE / 'runs').write_text(str(count) + '\n')
    logpath = STATE / f'run-{count}.log'
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    with logpath.open('x') as log:
        proc = subprocess.Popen([str(payload / 'probe'), '--run-once'], stdout=subprocess.PIPE, text=True,
                                stderr=subprocess.STDOUT, env=dict(ENV, LD_LIBRARY_PATH=str(payload)),
                                start_new_session=True)
        def copy_metadata():
            for line in proc.stdout:
                log.write(line)
                log.flush()
                print(line, end='', flush=True)
        copier = threading.Thread(target=copy_metadata, daemon=True)
        copier.start()
        try:
            code = proc.wait(timeout=140)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            proc.send_signal(signal.SIGTERM)  # C handler cancels and drains.
            try:
                code = proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                code = 124
                log.write('GOODIX_PROBE_FORCED_STOP=1 CLEANUP_UNPROVEN=1\n')
        copier.join(timeout=2)
        log.write(f'GOODIX_PROBE_PROCESS_EXIT={code}\n')
    print('STOP: raccogli il log e fai review. fprintd resta escluso fino al rollback.')
    print('LOG=' + str(logpath))


def collect():
    # Archive only explicit metadata logs/manifest, never material or payload binaries.
    with tarfile.open(fileobj=sys.stdout.buffer, mode='w|gz') as archive:
        for path in sorted(STATE.glob('run-[12].log')):
            archive.add(path, arcname=path.name, recursive=False)
        archive.add(STATE / 'payload/probe-payload.json', arcname='probe-payload.json', recursive=False)


def rollback():
    if (STATE / 'owns-mask').exists():
        require(not MASK.exists() and not MASK.is_symlink() or
                MASK.is_symlink() and os.readlink(MASK) == '/dev/null', 'mask changed externally: inspect manually')
        systemctl('unmask', '--runtime', 'fprintd.service')
        require(not MASK.exists() and not MASK.is_symlink(), 'mask still present')
    shutil.rmtree(STATE)
    require(not STATE.exists(), 'temporary installation remains')
    print('ROLLBACK_VERIFIED=1 TEMPORARY_PAYLOAD_REMOVED=1 SYSTEM_LIBRARY_REPLACED=0')
    print('fprintd nuovamente attivabile tramite D-Bus; nessun riavvio automatico del sensore.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('install').add_argument('payload')
    subs.add_parser('run').add_argument('--reviewed-run-1', action='store_true')
    subs.add_parser('collect')
    subs.add_parser('rollback')
    args = parser.parse_args()
    require(os.geteuid() == 0, 'invoke explicitly with sudo, as documented')
    os.umask(0o077)
    if args.command == 'install':
        install(args.payload)
        return
    require(STATE.is_dir() and not STATE.is_symlink() and STATE.stat().st_uid == 0,
            'temporary root-owned installation missing')
    with (STATE / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'run': run(args.reviewed_run_1)
        elif args.command == 'collect': collect()
        else: rollback()


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        sys.exit('STOP: ' + str(error))
