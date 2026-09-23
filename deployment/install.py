#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build and install the supported Fedora fingerprint integration."""
import argparse
from contextlib import contextmanager, redirect_stdout
import fcntl
import importlib.util
import json
import io
import os
from pathlib import Path
import platform
import re
import resource
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}
VENDOR = Path('/usr/lib/pam.d/plasmalogin')
RUNTIME_PACKAGES = ('fprintd', 'fprintd-pam', 'policycoreutils-python-utils')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Resolve exclusively from this script; never search PATH/cwd for project code.
r = load('goodix_removal', ROOT / 'deployment/recovery/remove.py')
materials = load('goodix_materials', ROOT / 'deployment/materials.py')
builder = load('goodix_builder', ROOT / 'production/build-public.py')
require = r.require


def command(*args):
    result = subprocess.run(args, env=ENV, text=True, capture_output=True, timeout=60)
    require(result.returncode == 0, f'{args[0]} failed: {result.stderr.strip() or result.stdout.strip()}')
    return result.stdout.strip()


def supported_system():
    os_info = platform.freedesktop_os_release()
    require(os_info.get('ID') == 'fedora' and os_info.get('VERSION_ID') == '44'
            and platform.machine() == 'x86_64', 'Fedora 44 x86_64 is required')
    require(command('getenforce') == 'Enforcing', 'SELinux Enforcing is required; do not disable it')


def prerequisites():
    missing = []
    for package in (*builder.BUILD_PACKAGES, *RUNTIME_PACKAGES):
        result = subprocess.run(['rpm', '-q', package], env=ENV, capture_output=True)
        if result.returncode:
            missing.append(package)
    require(not missing, 'Missing Fedora packages. Run: sudo dnf install ' + ' '.join(missing) +
            '; then run ./install.sh again')


def safe_parent(path):
    r.parents(path)
    for parent in path.parents:
        if r.present(parent):
            r.trusted(parent, directory=True)


def host_preflight():
    supported_system()
    safe_parent(VENDOR)
    r.trusted(VENDOR)
    require(command('rpm', '-qf', '--qf', '%{NAME}', str(VENDOR)) == 'plasma-login-manager',
            'current Plasma Login PAM must belong to the Fedora package')
    require(command('systemctl', 'show', 'fprintd.service', '-p', 'FragmentPath', '--value') ==
            '/usr/lib/systemd/system/fprintd.service', 'stock Fedora fprintd unit is required')
    commands = re.findall(r'path=([^ ;]+)', command('systemctl', 'show', 'fprintd.service', '-p', 'ExecStart', '--value'))
    require(commands == ['/usr/libexec/fprintd'], 'stock Fedora fprintd ExecStart is required')
    for name in command('systemctl', 'show', 'fprintd.service', '-p', 'DropInPaths', '--value').split():
        require(name == str(r.DROPIN) or name.startswith('/usr/lib/systemd/system/'),
                'unrecognized fprintd override: ' + name)
    environment = shlex.split(command('systemctl', 'show', 'fprintd.service', '-p', 'Environment', '--value'))
    require(not any(item.startswith('LD_PRELOAD=') for item in environment), 'foreign fprintd preload environment')
    library_paths = [item for item in environment if item.startswith('LD_LIBRARY_PATH=')]
    if library_paths:
        require(library_paths == ['LD_LIBRARY_PATH=/usr/local/lib64/goodix-27c6-5125'],
                'foreign library environment')
        require(r.present(r.DROPIN) and r.read(r.DROPIN) == r.DROPIN_BYTES,
                'foreign library environment')


def material_rule():
    listing = command('semanage', 'fcontext', '-l', '-C', '-n')
    found = False
    kinds = 'all files|regular file|directory|character device|block device|socket|symbolic link|named pipe'
    for line in listing.splitlines():
        if not line.strip():
            continue
        row = re.fullmatch(r'(.+?)\s+(' + kinds + r')\s+(\S+)\s*', line)
        if row:
            expression, kind, context = row.groups()
            if expression == r.RULE:
                require(not found and kind == 'all files' and context ==
                        'system_u:object_r:fprintd_var_lib_t:s0', 'conflicting material SELinux mapping')
                found = True
                continue
        else:
            row = re.fullmatch(r'(\S+)\s+=\s+(\S+)', line)
            require(row is not None, 'unrecognized local SELinux mapping')
            expression = row[1]
        stem = re.split(r'[.\\\[\]()*+?{}$]', expression.removeprefix('^'), maxsplit=1)[0]
        require('|' not in expression and not (str(r.MATERIAL).startswith(stem) or
                stem.startswith(str(r.MATERIAL) + '/')), 'possibly conflicting material mapping: ' + expression)
    return found


def label_materials():
    paths = (r.MATERIAL, *(r.MATERIAL / n for n in r.MATERIAL_NAMES))
    command('restorecon', '-F', '--', *(str(p) for p in paths))
    for path in paths:
        context = os.getxattr(path, 'security.selinux', follow_symlinks=False).rstrip(b'\0')
        require(context == b'system_u:object_r:fprintd_var_lib_t:s0', 'material label verification failed')


def write_file(path, data, mode=0o644):
    safe_parent(path)
    fd, name = tempfile.mkstemp(prefix='.goodix-publish-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fchmod(out.fileno(), mode)
            os.fsync(out.fileno())
        command('restorecon', '-F', str(temporary))
        os.link(temporary, path, follow_symlinks=False)  # atomic, no overwrite
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, value, mode=0o600):
    write_file(path, (json.dumps(value, sort_keys=True) + '\n').encode(), mode)


def software_paths():
    return (r.CONFIG, r.DROPIN, r.SUPPORT, r.RUNTIME, r.NORMAL, r.FORCE, r.RECOVERY)


def snapshot_software(destination):
    saved = []
    for index, path in enumerate(software_paths()):
        if r.present(path):
            target = destination / str(index)
            if path.is_dir():
                shutil.copytree(path, target, symlinks=True)
            else:
                shutil.copy2(path, target, follow_symlinks=False)
            saved.append((path, target))
    return saved


def install_tools(source_id):
    payload = (ROOT / 'deployment/recovery/remove.py').read_bytes()
    r.RECOVERY.mkdir(mode=0o755)
    for path in (r.NORMAL, r.FORCE):
        write_file(path, payload, 0o755)
    write_json(r.RECOVERY / 'receipt.json', {'schema': 2, 'source_id': source_id,
               'files': {p.name: r.digest(payload) for p in (r.NORMAL, r.FORCE)}}, 0o644)
    command('restorecon', '-F', str(r.RECOVERY), str(r.RECOVERY / 'receipt.json'), str(r.NORMAL), str(r.FORCE))


def install_runtime(payload, manifest, rule_preexisting):
    r.RUNTIME.mkdir(mode=0o755)
    hashes = {}
    for name, digest in manifest['files'].items():
        if not name.startswith('runtime/'):
            continue
        relative = name.removeprefix('runtime/')
        path = r.RUNTIME / relative
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        write_file(path, (payload / name).read_bytes())
        hashes[relative] = digest
    links = {}
    for name, target in manifest['links'].items():
        if name.startswith('runtime/'):
            relative = name.removeprefix('runtime/')
            (r.RUNTIME / relative).symlink_to(target)
            links[relative] = target
    write_json(r.RUNTIME / 'installation.json', {'schema': 2, 'source_id': manifest['source_id'],
        'files': hashes, 'links': links, 'material_selinux': {'rule': r.RULE,
        'owned': not rule_preexisting, 'preexisting': rule_preexisting, 'phase': 'ready'}})
    command('restorecon', '-RF', str(r.RUNTIME))
    r.DROPIN.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    write_file(r.DROPIN, r.DROPIN_BYTES)
    command('restorecon', '-F', str(r.DROPIN))


def install_login(payload, source_id):
    r.SUPPORT.mkdir(mode=0o755)
    module = (payload / 'login' / r.MODULE).read_bytes()
    config = (payload / 'login/plasmalogin.pam').read_bytes()
    # The public payload must use exactly the reviewed current integration.
    require(config == (ROOT / 'deployment/plasma-login-opt-in/plasmalogin.pam').read_bytes(),
            'unexpected Plasma Login configuration in build output')
    write_file(r.SUPPORT / r.MODULE, module)
    write_json(r.SUPPORT / 'receipt.json', {'schema': 2, 'source_id': source_id,
        'files': {r.MODULE: r.digest(module)}, 'config_sha256': r.digest(config)}, 0o644)
    command('restorecon', '-RF', str(r.SUPPORT))
    # Publish auth entry only after the module and its labels are ready.
    write_file(r.CONFIG, config)
    command('restorecon', '-F', str(r.CONFIG))


def rollback(saved, rule_before):
    try:
        r.stop_and_verify()
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        raise RuntimeError('rollback incomplete: service could not be quiesced; software and recovery '
                           'commands retained. Report this error: ' + str(error)) from error
    errors = []
    tool_paths = (r.NORMAL, r.FORCE, r.RECOVERY)
    for path in software_paths():
        if path in tool_paths:
            continue
        try:
            r.remove_path(path)
        except (OSError, RuntimeError) as error:
            errors.append(str(error))
    if not errors:
        for path, backup in saved:
            if path in tool_paths:
                continue
            try:
                if backup.is_dir():
                    shutil.copytree(backup, path, symlinks=True)
                else:
                    shutil.copy2(backup, path, follow_symlinks=False)
            except OSError as error:
                errors.append(str(error))
    try:
        exists = material_rule()
        if rule_before and not exists:
            command('semanage', 'fcontext', '-a', '-f', 'a', '-t', 'fprintd_var_lib_t', '-r', 's0', r.RULE)
        elif exists and not rule_before:
            command('semanage', 'fcontext', '-d', '-f', 'a', r.RULE)
        if r.present(r.MATERIAL):
            command('restorecon', '-F', '--', str(r.MATERIAL), *(str(r.MATERIAL / n) for n in r.MATERIAL_NAMES))
        command('systemctl', 'daemon-reload')
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        errors.append(str(error))
    # Keep current rescue commands if any non-tool cleanup/restoration failed.
    if not errors:
        for path in tool_paths:
            try:
                r.remove_path(path)
                backup = next((b for p, b in saved if p == path), None)
                if backup is not None:
                    if backup.is_dir():
                        shutil.copytree(backup, path, symlinks=True)
                    else:
                        shutil.copy2(backup, path, follow_symlinks=False)
            except OSError as error:
                errors.append(str(error))
    require(not errors, 'rollback incomplete; retain recovery commands and report: ' + '; '.join(errors))


@contextmanager
def lifecycle():
    safe_parent(r.RUNTIME)
    r.RUNTIME.parent.mkdir(mode=0o755, exist_ok=True)
    fd = os.open(r.RUNTIME.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    created_mask = None
    body_completed = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('another Goodix lifecycle operation is active') from error
        if any(r.present(p) for p in software_paths()):
            r.normal_preflight()
        created_mask = r.inhibit_activation()
        r.stop_and_verify()
        yield
        body_completed = True
    finally:
        try:
            try:
                r.release_inhibition(created_mask)
            except (RuntimeError, OSError, subprocess.SubprocessError) as error:
                state = 'software installed; recovery commands retained' if body_completed else 'transaction failed'
                raise RuntimeError('final service cleanup incomplete (' + state + '); '
                    'report this error before continuing: ' + str(error)) from error
        finally:
            os.close(fd)


def apply(payload, material_directory, owner_uid):
    require(os.geteuid() == 0, 'administrative installation requires sudo')
    host_preflight()
    bundle = materials.validate_bundle(material_directory, source=True, owner_uid=owner_uid)
    manifest = builder.validate_payload(payload)
    for path in software_paths():
        safe_parent(path)
    if any(r.present(p) for p in software_paths()):
        r.normal_preflight()  # Refuse partial/foreign state before any mutation.
    rule_before = material_rule()
    # Make an immutable root-owned copy before executing the compiled checker.
    with tempfile.TemporaryDirectory(prefix='goodix-install-') as staging_name:
        staging = Path(staging_name)
        staged_payload = staging / 'payload'
        shutil.copytree(payload, staged_payload, symlinks=True)
        require(builder.validate_payload(staged_payload) == manifest, 'build payload changed during staging')
        with lifecycle():
            saved = snapshot_software(staging)
            rule_before = material_rule()
            try:
                if saved:
                    with redirect_stdout(io.StringIO()):
                        require(r.remove(force=False) == 0, 'existing installation could not be removed')
                install_tools(manifest['source_id'])
                materials.install_materials(bundle, r.MATERIAL,
                    native_check=lambda directory: command(str(staged_payload / 'check-material'), str(directory)))
                preexisting = material_rule()
                if not preexisting:
                    command('semanage', 'fcontext', '-a', '-f', 'a', '-t', 'fprintd_var_lib_t', '-r', 's0', r.RULE)
                label_materials()
                print('GOODIX_MATERIALS=VALID')
                install_runtime(staged_payload, manifest, preexisting)
                install_login(staged_payload, manifest['source_id'])
                command('systemctl', 'daemon-reload')
                r.normal_preflight()
                r.stop_and_verify()
            except BaseException:
                rollback(saved, rule_before)
                print('GOODIX_ROLLBACK=PASS PRIOR_PROJECT_SOFTWARE_RESTORED=true', file=sys.stderr)
                raise
    print('GOODIX_INSTALL=PASS READER_PRESENT_ALLOWED=true')
    print('Use KDE fingerprint settings to enroll or your existing template. The service was not started by installation.')
    print('Removal: goodix-uninstall. Emergency recovery: goodix-force-remove.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--materials', type=Path, default=Path.home() / 'goodix-5125-materials',
                        help='directory containing the five protected files (default: ~/goodix-5125-materials)')
    parser.add_argument('--check', action='store_true', help='check prerequisites and material structure without installation')
    parser.add_argument('--apply', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--owner-uid', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    material_directory = args.materials.expanduser().absolute()
    require(not material_directory.resolve().is_relative_to(ROOT),
            'protected material must be staged outside the repository')
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt('installation interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    if args.apply is not None:
        require(not args.check and args.owner_uid is not None, 'invalid administrative invocation')
        apply(args.apply.absolute(), material_directory, args.owner_uid)
        return 0
    require(os.geteuid() != 0, 'run ./install.sh as your ordinary user; it requests sudo itself')
    require(args.owner_uid is None, 'invalid invocation')
    supported_system()
    materials.validate_bundle(material_directory, source=True)
    prerequisites()
    if args.check:
        print('GOODIX_CHECK=PASS STATIC_MATERIAL_CHECK=PASS NATIVE_BINDING_CHECK_AT_INSTALL=true')
        return 0
    # Build before privileged file/service changes; never place materials in the clone.
    with tempfile.TemporaryDirectory(prefix='goodix-build-') as output:
        payload = Path(output) / 'payload'
        builder.build_payload(payload)
        manifest = builder.validate_payload(payload)
        print('GOODIX_BUILD=PASS SOURCE_ID=' + manifest['source_id'], flush=True)
        result = subprocess.run(['/usr/bin/sudo', '--', '/usr/bin/python3', '-I', '-B',
            str(Path(__file__).resolve()), '--apply', str(payload), '--materials', str(material_directory),
            '--owner-uid', str(os.getuid())], env=ENV)
        return result.returncode


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit('GOODIX_INSTALL=STOP interrupted; report the last completed step')
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        sys.exit(f'GOODIX_INSTALL=STOP {error}')
