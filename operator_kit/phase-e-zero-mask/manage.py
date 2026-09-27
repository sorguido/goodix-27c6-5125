#!/usr/bin/python3 -I
# SPDX-License-Identifier: GPL-2.0-or-later
"""Manual, reversible Phase E runtime swap; never opens a sensor or runs sudo."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
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

ROOT = Path(__file__).resolve().parents[2]
STATE = Path('/var/lib/goodix-phase-e-zero-mask')
RUNTIME = Path('/usr/local/lib64/goodix-27c6-5125')
OLD = RUNTIME.with_name(RUNTIME.name + '.phase-e-previous')
STAGED = RUNTIME.with_name(RUNTIME.name + '.phase-e-next')
CHANGED = {'libfprint-2.so.2.0.0', 'source-files.sha256', 'build-provenance.json'}
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


installer = load('phase_e_installer', ROOT / 'deployment/install.py')
r = installer.r
builder = installer.builder
require = r.require


def digest(data):
    return hashlib.sha256(data).hexdigest()


def command(*args):
    result = subprocess.run(args, env=ENV, capture_output=True, text=True, timeout=60)
    require(result.returncode == 0, f'{args[0]} failed: {result.stderr.strip()}')
    return result.stdout.strip()


def snapshot(directory):
    """Only project software metadata; never traverse device-material paths."""
    r.trusted(directory, directory=True)
    receipt_bytes = r.read(directory / 'installation.json')
    receipt = json.loads(receipt_bytes)
    require(receipt.get('schema') == 2, 'Phase E requires the public schema-2 runtime')
    files, links = r.runtime_inventory(receipt)
    dirs = {str(Path(n).parent) for n in files if '/' in n}
    require({str(p.relative_to(directory)) for p in directory.rglob('*')} ==
            files | set(links) | dirs | {'installation.json'}, 'runtime inventory drift')
    for name in dirs:
        r.trusted(directory / name, directory=True)
    hashes = {name: digest(r.read(directory / name)) for name in files}
    require(hashes == receipt['files'], 'runtime checksum drift')
    for name, target in links.items():
        require((directory / name).is_symlink() and os.readlink(directory / name) == target,
                'runtime symlink drift')
    hashes['installation.json'] = digest(receipt_bytes)
    return {'files': hashes, 'links': links}


def read_state():
    r.trusted(STATE, directory=True)
    names = {p.name for p in STATE.iterdir()}
    require('state.json' in names and names <= {'state.json', 'state.next'},
            'backup receipt directory drift')
    if r.present(STATE / 'state.next'):
        r.trusted(STATE / 'state.next')
    return json.loads(r.read(STATE / 'state.json'))


def write_state(data):
    target = STATE / 'state.json'
    temp = STATE / 'state.next'
    if r.present(temp):
        r.trusted(temp)
        temp.unlink()  # interrupted write; state.json is the last committed receipt
    with temp.open('xb') as out:
        out.write((json.dumps(data, sort_keys=True, indent=2) + '\n').encode())
        os.fchmod(out.fileno(), 0o600)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, target)
    fd = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def lock():
    r.trusted(RUNTIME.parent, directory=True)
    fd = os.open(RUNTIME.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def stage(payload, manifest, before):
    receipt = json.loads(r.read(RUNTIME / 'installation.json'))
    incoming = {n.removeprefix('runtime/'): h for n, h in manifest['files'].items()
                if n.startswith('runtime/')}
    incoming_links = {n.removeprefix('runtime/'): t for n, t in manifest['links'].items()
                      if n.startswith('runtime/')}
    require(set(incoming) == set(receipt['files']) and incoming_links == receipt['links'],
            'candidate runtime topology differs; full installation is outside this kit')
    require(CHANGED <= set(incoming), 'candidate missing Phase E runtime files')
    require(all(incoming[n] == receipt['files'][n] for n in incoming if n not in CHANGED),
            'candidate changes dependencies/licenses; build against the installed baseline')
    STAGED.mkdir(mode=0o755)
    try:
        for name, checksum in incoming.items():
            source = payload / 'runtime' / name
            # Copy bytes, not source ownership or xattrs; refuse links and races.
            fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'nonregular candidate file')
                content = stream.read()
            require(digest(content) == checksum, 'candidate changed while staging')
            dest = STAGED / name
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            dest.write_bytes(content)
            dest.chmod(0o644)
        for name, target in incoming_links.items():
            (STAGED / name).symlink_to(target)
        receipt['files'] = incoming
        receipt['source_id'] = manifest['source_id']
        (STAGED / 'installation.json').write_text(json.dumps(receipt, sort_keys=True) + '\n')
        (STAGED / 'installation.json').chmod(0o600)
        require(snapshot(RUNTIME) == before, 'installed runtime changed during preparation')
        return snapshot(STAGED)
    except BaseException:
        shutil.rmtree(STAGED)
        raise


def acquire_mask(data):
    # Refuse foreign/pre-existing inhibition. A mask retained by an interrupted
    # Phase E operation may be reused only with the matching recorded inode.
    if r.present(r.MASK):
        info = r.MASK.lstat()
        require(data.get('mask_inode') == [info.st_dev, info.st_ino] and
                r.MASK.is_symlink() and os.readlink(r.MASK) == '/dev/null',
                'foreign fprintd mask/override; left untouched')
        r.stop_and_verify()
        return (info.st_dev, info.st_ino)
    mask = r.inhibit_activation()
    require(mask is not None, 'could not own the fprintd runtime mask')
    data['mask_inode'] = list(mask)
    write_state(data)
    r.stop_and_verify()
    return mask


def discard_staged(data):
    if not r.present(STAGED):
        return
    r.trusted(STAGED, directory=True)
    info = STAGED.lstat()
    identity = [info.st_dev, info.st_ino]
    if data.get('discard_inode') != identity:
        require(snapshot(STAGED) == data['after'], 'staged runtime drift')
        data['discard_inode'] = identity
        write_state(data)
    # The receipt owns this exact directory, including a partially completed
    # deletion. This never relaxes verification of the active runtime/backup.
    shutil.rmtree(STAGED)
    data.pop('discard_inode', None)


def restore(data):
    require(r.present(OLD) and snapshot(OLD) == data['before'], 'previous runtime missing or changed')
    if r.present(RUNTIME):
        require(snapshot(RUNTIME) == data['after'], 'current runtime drift; do not overwrite external work')
        require(not r.present(STAGED), 'staging path occupied during restoration')
        RUNTIME.rename(STAGED)
    OLD.rename(RUNTIME)
    command('restorecon', '-RF', str(RUNTIME))
    require(snapshot(RUNTIME) == data['before'], 'restoration verification failed')
    discard_staged(data)
    data['phase'] = 'rolled-back'
    write_state(data)


def apply(payload):
    payload = Path(payload).resolve(strict=True)
    manifest = builder.validate_payload(payload)
    installer.host_preflight()
    r.normal_preflight()
    before = snapshot(RUNTIME)
    if r.present(STATE):
        data = read_state()
        require(data.get('phase') == 'installed' and data.get('source_id') == manifest['source_id']
                and before == data['after'] and snapshot(OLD) == data['before'],
                'existing Phase E state: collect and rollback; do not overwrite its backup')
        print('PHASE_E_INSTALL=ALREADY_INSTALLED')
        return
    require(not r.present(OLD) and not r.present(STAGED) and not r.present(r.MASK),
            'pre-existing backup/staging/mask; stop without changing it')
    r.trusted(STATE.parent, directory=True)
    after = stage(payload, manifest, before)
    data = {'schema': 1, 'phase': 'prepared', 'source_id': manifest['source_id'],
            'before': before, 'after': after,
            'since': datetime.now(timezone.utc).isoformat(), 'mask_inode': None}
    created_state = False
    try:
        STATE.mkdir(mode=0o700)
        created_state = True
        write_state(data)
    except BaseException:
        # No service or installed path has been touched at this point.
        shutil.rmtree(STAGED)
        if created_state:
            for name in ('state.next', 'state.json'):
                if r.present(STATE / name):
                    r.trusted(STATE / name)
                    (STATE / name).unlink()
            STATE.rmdir()
        raise
    mask = None
    try:
        mask = acquire_mask(data)
        require(snapshot(RUNTIME) == before, 'runtime changed before swap')
        RUNTIME.rename(OLD)
        STAGED.rename(RUNTIME)
        command('restorecon', '-RF', str(RUNTIME))
        require(snapshot(RUNTIME) == after, 'candidate verification failed')
        data['phase'] = 'installed'
        write_state(data)
    except BaseException:
        # Restore the exact old directory when the swap has begun. On failed
        # restoration keep both backup and mask for explicit recovery.
        if r.present(OLD):
            restore(data)
        elif r.present(STAGED):
            discard_staged(data)
            data['phase'] = 'rolled-back'
            write_state(data)
        if mask is not None:
            r.release_inhibition(mask)
        raise
    r.release_inhibition(mask)
    print('PHASE_E_INSTALL=PASS SOURCE_ID=' + manifest['source_id'] + ' USB_OPENED=0')


def rollback():
    if not r.present(STATE):
        require(not r.present(OLD) and not r.present(STAGED), 'orphaned backup/staging; manual review required')
        print('PHASE_E_ROLLBACK=NOT_INSTALLED')
        return
    data = read_state()
    if data['phase'] == 'rolled-back':
        require(snapshot(RUNTIME) == data['before'], 'restored runtime drift')
        if r.present(r.MASK):
            mask = acquire_mask(data)
            r.release_inhibition(mask)
        print('PHASE_E_ROLLBACK=ALREADY_RESTORED')
        return
    # Validate before stopping fprintd. Accept an interrupted swap with its
    # runtime path absent; refuse any unrelated current build.
    if r.present(OLD):
        require(snapshot(OLD) == data['before'], 'backup drift')
        if r.present(RUNTIME):
            require(snapshot(RUNTIME) == data['after'], 'current runtime drift')
    else:
        # A previous restoration may have renamed OLD back, then failed during
        # restorecon or receipt write. The exact baseline is sufficient here.
        require(snapshot(RUNTIME) == data['before'], 'backup missing or baseline changed')
    mask = acquire_mask(data)
    if r.present(OLD):
        restore(data)
    else:
        command('restorecon', '-RF', str(RUNTIME))
        discard_staged(data)
        data['phase'] = 'rolled-back'
        write_state(data)
    r.release_inhibition(mask)
    print('PHASE_E_ROLLBACK=PASS PREVIOUS_RUNTIME_RESTORED=1 USB_OPENED=0')


def collect():
    data = read_state()
    print('PHASE_E_SOURCE_ID=' + data['source_id'])
    print('PHASE_E_DEPLOYMENT_STATE=' + data['phase'])
    logs = command('journalctl', '-u', 'fprintd.service', '--since', data['since'],
                   '--no-pager', '-o', 'cat')
    for line in logs.splitlines():
        match = re.search(r'GOODIX_(?:ZERO_MASK_RECOVERY|PRODUCTION_EPOCH_AUDIT|STOCK_CAPTURE_RESULT|ENROLLMENT_CONTACT_UNUSABLE)\b.*', line)
        if match:
            print(match[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('install').add_argument('payload', type=Path)
    sub.add_parser('rollback')
    sub.add_parser('collect')
    args = parser.parse_args()
    require(os.geteuid() == 0, 'manual sudo invocation required; this program never invokes sudo')
    with lock():
        if args.action == 'install': apply(args.payload)
        elif args.action == 'rollback': rollback()
        else: collect()


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit('PHASE_E_KIT=STOP ' + str(error))
