#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build a local Fedora payload from this source tree, without installing it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LIBFPRINT_SOURCE = Path('reference/libfprint-fedora44-1.94.100/source')
LOGIN_SOURCE = Path('deployment/plasma-login-opt-in')
BUILD_PACKAGES = ('gcc', 'gcc-c++', 'meson', 'ninja-build', 'pkgconf-pkg-config',
                  'glib2-devel', 'libgusb-devel', 'openssl-devel', 'opencv-devel',
                  'pam-devel', 'binutils')
OPENCV_PARTS = ('core', 'features2d', 'flann', 'imgproc')
LICENSES = ('GPL-2.0-or-later', 'LGPL-2.1-or-later', 'GPL-3.0-or-later', 'Apache-2.0')
BASE_ENV = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C'}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(*args, env=None):
    result = subprocess.run([str(arg) for arg in args], env=env or BASE_ENV,
                            text=True, capture_output=True)
    require(result.returncode == 0,
            f'{args[0]} failed: {result.stderr.strip() or result.stdout.strip()}')
    return result.stdout.strip()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def missing_packages():
    return [name for name in BUILD_PACKAGES if subprocess.run(
        ['rpm', '-q', name], env=BASE_ENV, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL).returncode != 0]


def prerequisites():
    require(os.geteuid() != 0, 'build as your normal user, before privileged installation')
    release = platform.freedesktop_os_release()
    require(release.get('ID') == 'fedora' and release.get('VERSION_ID') == '44'
            and platform.machine() == 'x86_64', 'Fedora 44 x86_64 is required')
    missing = missing_packages()
    require(not missing, 'missing build packages: ' + ' '.join(missing))
    for name in ('meson', 'ninja', 'cc', 'c++', 'pkg-config', 'rpm', 'readelf', 'nm', 'ldd'):
        require(shutil.which(name, path=BASE_ENV['PATH']) is not None, f'missing build command: {name}')


def source_inventory():
    """Content provenance works equally in a source archive or a fresh clone."""
    roots = [LIBFPRINT_SOURCE, Path('libfprint-driver'), Path('Rockytkg/libfprint/libfprint/sigfm')]
    files = [ROOT / 'production/build-public.py',
             *(ROOT / 'deployment' / name for name in
               ('check-material.c', 'materials.py', 'test_material_native.c', 'test_materials.py')),
             ROOT / 'production/host-test-only-symbols.txt',
             ROOT / LOGIN_SOURCE / 'pam_goodix_login_gate.c', ROOT / LOGIN_SOURCE / 'plasmalogin.pam',
             *(ROOT / LOGIN_SOURCE / name for name in ('test_gate.c', 'test_dispatch.c', 'test_dispatch.py')),
             ROOT / 'docs/LICENSING_AND_PROVENANCE.md',
             *(ROOT / 'LICENSES' / (name + '.txt') for name in LICENSES)]
    for relative in roots:
        directory = ROOT / relative
        require(directory.is_dir() and not directory.is_symlink(), f'missing source directory: {relative}')
        files.extend(path for path in directory.rglob('*') if path.is_file() and
                     '__pycache__' not in path.parts and path.suffix != '.pyc')
    rows = []
    for path in sorted(set(files)):
        require(path.is_file() and not path.is_symlink(), f'not a regular source file: {path}')
        rows.append(f'{sha256(path.read_bytes())}  {path.relative_to(ROOT).as_posix()}\n')
    return ''.join(rows)


def soname(path):
    dynamic = run('readelf', '-d', path)
    require('(RPATH)' not in dynamic and '(RUNPATH)' not in dynamic,
            f'library contains a private loader path: {path.name}')
    names = re.findall(r'\(SONAME\).*?\[([^]]+)\]', dynamic)
    require(len(names) == 1, f'library SONAME is missing or ambiguous: {path.name}')
    return names[0]


def opencv_inputs():
    version = run('pkg-config', '--modversion', 'opencv4')
    includedir = Path(run('pkg-config', '--variable=includedir', 'opencv4'))
    libdir = Path(run('pkg-config', '--variable=libdir', 'opencv4'))
    require(version.startswith('4.') and includedir.is_absolute() and libdir.is_absolute(),
            'OpenCV 4 development metadata is required')
    libraries = {}
    for component in OPENCV_PARTS:
        path = (libdir / f'libopencv_{component}.so').resolve(strict=True)
        require(path.is_file(), f'OpenCV library missing: {component}')
        name = soname(path)
        require(re.fullmatch(r'libopencv_' + component + r'\.so\.[0-9]+', name),
                f'unexpected OpenCV SONAME: {name}')
        libraries[name] = path
    return version, includedir, libdir, libraries


def opencv_notices(libraries):
    owners = sorted({run('rpm', '-qf', '--qf', '%{NAME}', path) for path in libraries.values()})
    license_files = set()
    for owner in owners:
        for line in run('rpm', '-ql', owner).splitlines():
            path = Path(line)
            if path.is_relative_to('/usr/share/licenses') and path.is_file():
                license_files.add(path)
    require(license_files, 'OpenCV package license notices are unavailable')
    return '\n'.join(f'===== {path.relative_to("/usr/share/licenses")} =====\n' +
                     path.read_text() for path in sorted(license_files)) + '\n'


def _safe_relative(name):
    return isinstance(name, str) and name != '' and not Path(name).is_absolute() and \
        all(part not in ('', '.', '..') for part in name.split('/'))


def validate_payload(directory):
    directory = Path(directory)
    require(directory.is_absolute() and directory.resolve() == directory and directory.is_dir(),
            'payload must be a real absolute directory')
    manifest_path = directory / 'payload.json'
    require(manifest_path.is_file() and not manifest_path.is_symlink(), 'payload manifest missing')
    manifest = json.loads(manifest_path.read_bytes())
    require(isinstance(manifest, dict) and set(manifest) == {'schema', 'source_id', 'files', 'links'}
            and type(manifest['schema']) is int and manifest['schema'] == 1 and isinstance(manifest['source_id'], str)
            and re.fullmatch('[0-9a-f]{64}', manifest['source_id'])
            and isinstance(manifest['files'], dict) and isinstance(manifest['links'], dict),
            'invalid payload manifest')
    files, links = manifest['files'], manifest['links']
    fixed = {'runtime/libfprint-2.so.2.0.0', 'runtime/OpenCV-LICENSES.txt',
             'runtime/LICENSING_AND_PROVENANCE.md', 'runtime/source-files.sha256',
             'runtime/build-provenance.json', 'login/pam_goodix_login_gate.so',
             'login/plasmalogin.pam', 'check-material',
             *(f'runtime/licenses/{name}.txt' for name in LICENSES)}
    dynamic = set(files) - fixed
    require(fixed <= set(files) and len(dynamic) == len(OPENCV_PARTS) and
            all(sum(bool(re.fullmatch(r'runtime/libopencv_' + part + r'\.so\.[0-9]+', name))
                    for name in dynamic) == 1 for part in OPENCV_PARTS), 'unexpected payload file inventory')
    require(links == {'runtime/libfprint-2.so.2': 'libfprint-2.so.2.0.0',
                      'runtime/libfprint-2.so': 'libfprint-2.so.2'}, 'unexpected payload links')
    actual = set()
    for path in directory.rglob('*'):
        if stat.S_ISDIR(path.lstat().st_mode):
            require(path.relative_to(directory).as_posix() in {'runtime', 'runtime/licenses', 'login'},
                    'unexpected payload directory: ' + str(path))
        require(stat.S_ISDIR(path.lstat().st_mode) or path.name == 'payload.json' or
                path.relative_to(directory).as_posix() in files.keys() | links.keys(),
                'unexpected payload entry: ' + str(path))
        if not stat.S_ISDIR(path.lstat().st_mode):
            actual.add(path.relative_to(directory).as_posix())
    require(actual == set(files) | set(links) | {'payload.json'}, 'incomplete payload')
    for name, checksum in files.items():
        require(_safe_relative(name) and isinstance(checksum, str) and
                re.fullmatch('[0-9a-f]{64}', checksum), 'invalid payload path/checksum')
        path = directory / name
        require(stat.S_ISREG(path.lstat().st_mode) and path.resolve().is_relative_to(directory)
                and sha256(path.read_bytes()) == checksum, 'payload content/type drift: ' + name)
    for name, target in links.items():
        path = directory / name
        require(path.is_symlink() and os.readlink(path) == target, 'payload link drift: ' + name)
    require(stat.S_IMODE((directory / 'check-material').stat().st_mode) == 0o755,
            'material checker must be executable with mode 0755')
    return manifest


def pam_synthetic_tests(work):
    """Only test modules and temporary policy text; never a distro login."""
    source = ROOT / LOGIN_SOURCE
    flags = ('-std=c11', '-Wall', '-Wextra', '-Werror', '-O2')
    unit, mock, dispatch, gate = (work / name for name in
                                  ('test_gate', 'mock.so', 'dispatch-test', 'gate-test.so'))
    fixtures = work / 'gate-fixtures'
    run('cc', *flags, source / 'test_gate.c', '-o', unit)
    run(unit)
    run('cc', *flags, '-fPIC', '-shared', '-DBUILD_MODULE', source / 'test_dispatch.c',
        '-lpam', '-o', mock)
    run('cc', *flags, source / 'test_dispatch.c', '-lpam', '-o', dispatch)
    run('cc', *flags, '-fPIC', '-shared', '-DGOODIX_GATE_TEST',
        '-DGOODIX_GATE_VENDOR_PATH=' + json.dumps(str(fixtures / 'plasmalogin')),
        '-DGOODIX_GATE_PASSWORD_PATH=' + json.dumps(str(fixtures / 'password-auth')),
        '-DGOODIX_GATE_POSTLOGIN_PATH=' + json.dumps(str(fixtures / 'postlogin')),
        source / 'pam_goodix_login_gate.c', '-lpam', '-o', gate)
    run('python3', '-I', '-B', source / 'test_dispatch.py', dispatch, mock,
        source / 'plasmalogin.pam', gate, fixtures)


def build_payload(output):
    output = Path(output)
    prerequisites()
    require(output.is_absolute() and not output.exists() and not output.is_symlink(),
            'build output must be a new absolute directory')
    require(not output.resolve().is_relative_to(ROOT), 'build output must be outside the source tree')
    inventory = source_inventory()
    source_id = sha256(inventory.encode())
    version, includedir, libdir, libraries = opencv_inputs()
    notices = opencv_notices(libraries)
    output.mkdir(mode=0o700)
    runtime, login = output / 'runtime', output / 'login'
    runtime.mkdir()
    login.mkdir()
    # PAM module paths cannot contain whitespace; this private build directory
    # is independent of the source clone and output directory names.
    with tempfile.TemporaryDirectory(prefix='goodix-source-build-', dir='/tmp') as temporary:
        work = Path(temporary)
        pkgconfig = work / 'pkgconfig'
        pkgconfig.mkdir()
        # Fedora's full OpenCV .pc links unrelated modules. Keep the exact four
        # components used by feature matching; all dependencies remain Fedora's.
        (pkgconfig / 'opencv4.pc').write_text(
            f'Name: OpenCV\nDescription: Goodix feature matching subset\nVersion: {version}\n'
            f'Libs: -L{shlex.quote(str(libdir))} ' +
            ' '.join('-lopencv_' + part for part in OPENCV_PARTS) + '\n'
            f'Cflags: -I{shlex.quote(str(includedir))}\n')
        env = dict(BASE_ENV, PKG_CONFIG_PATH=str(pkgconfig))
        build = work / 'build'
        cflags = ['-DGOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE',
                  f'-ffile-prefix-map={ROOT}=/usr/src/goodix',
                  f'-ffile-prefix-map={work}=/usr/src/goodix-build']
        run('meson', 'setup', build, ROOT / LIBFPRINT_SOURCE, '--prefix=/usr', '--libdir=lib64',
            '--buildtype=release', '--wrap-mode=nodownload', '-Ddrivers=goodix_27c6_5125',
            '-Dintrospection=false', '-Ddoc=false', '-Dinstalled-tests=false',
            '-Dudev_rules=disabled', '-Dudev_hwdb=disabled', '-Dgoodix_production_minimal=true',
            '-Dc_args=' + json.dumps(cflags), '-Dcpp_args=' + json.dumps(cflags), env=env)
        run('meson', 'compile', '-C', build, 'fprint-2', env=env)
        library = build / 'libfprint/libfprint-2.so.2.0.0'
        require(soname(library) == 'libfprint-2.so.2', 'unexpected libfprint ABI')
        symbols = set(re.findall(r'\b(goodix_\w+)$', run('nm', library), flags=re.M))
        forbidden = set((ROOT / 'production/host-test-only-symbols.txt').read_text().splitlines())
        require(not symbols & forbidden, 'test-only entrypoints present in production library')
        shutil.copyfile(library, runtime / library.name)
        for name, path in libraries.items():
            shutil.copyfile(path, runtime / name)
        (runtime / 'libfprint-2.so.2').symlink_to(library.name)
        (runtime / 'libfprint-2.so').symlink_to('libfprint-2.so.2')
        run('cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', '-fPIC', '-shared',
            ROOT / LOGIN_SOURCE / 'pam_goodix_login_gate.c', '-lpam',
            '-Wl,-z,relro,-z,now', '-Wl,--no-undefined', '-o', login / 'pam_goodix_login_gate.so')
        pam_synthetic_tests(work)
        shutil.copyfile(ROOT / LOGIN_SOURCE / 'plasmalogin.pam', login / 'plasmalogin.pam')
        material_sources = [ROOT / f'libfprint-driver/{name}.c' for name in
            ('goodix_runtime_material', 'goodix_target_material', 'goodix_runtime_inputs', 'goodix_action_binding')]
        flags = shlex.split(run('pkg-config', '--cflags', '--libs', 'glib-2.0', 'openssl'))
        checker_flags = ('-std=c11', '-D_GNU_SOURCE', '-Wall', '-Wextra', '-Werror', '-O2',
                         '-I' + str(ROOT / 'libfprint-driver'))
        run('cc', *checker_flags, ROOT / 'deployment/check-material.c', *material_sources,
            *flags, '-o', output / 'check-material')
        (output / 'check-material').chmod(0o755)
        native_test = work / 'test-material-native'
        run('cc', *checker_flags, ROOT / 'deployment/test_material_native.c', *material_sources,
            *flags, '-o', native_test)
        run('python3', '-I', '-B', ROOT / 'deployment/test_materials.py',
            env=dict(BASE_ENV, GOODIX_MATERIAL_TEST_NATIVE=str(native_test)))
    required = set(re.findall(r'\b(fp_\w+)@LIBFPRINT_2\.0\.0', run('nm', '-D', '--undefined-only', '/usr/libexec/fprintd')))
    provided = set(re.findall(r'\b(fp_\w+)@@LIBFPRINT_2\.0\.0', run('nm', '-D', '--defined-only', runtime / library.name)))
    require(required and required <= provided, 'built libfprint does not supply the stock fprintd ABI')
    linked = run('ldd', '/usr/libexec/fprintd', env=dict(BASE_ENV, LD_LIBRARY_PATH=str(runtime)))
    require(str(runtime / 'libfprint-2.so.2') in linked and 'not found' not in linked,
            'stock fprintd dependency resolution failed')
    (runtime / 'OpenCV-LICENSES.txt').write_text(notices)
    shutil.copyfile(ROOT / 'docs/LICENSING_AND_PROVENANCE.md', runtime / 'LICENSING_AND_PROVENANCE.md')
    (runtime / 'licenses').mkdir()
    for name in LICENSES:
        shutil.copyfile(ROOT / 'LICENSES' / (name + '.txt'), runtime / 'licenses' / (name + '.txt'))
    (runtime / 'source-files.sha256').write_text(inventory)
    provenance = {'source_id': source_id, 'opencv_version': version,
                  'packages': run('rpm', '-q', *BUILD_PACKAGES, 'fprintd').splitlines()}
    (runtime / 'build-provenance.json').write_text(json.dumps(provenance, sort_keys=True) + '\n')
    require(source_inventory() == inventory, 'source content changed during the build')
    manifest = {'schema': 1, 'source_id': source_id, 'files': {}, 'links': {}}
    for path in sorted(output.rglob('*')):
        name = path.relative_to(output).as_posix()
        if path.is_symlink():
            manifest['links'][name] = os.readlink(path)
        elif path.is_file():
            path.chmod(0o755 if name == 'check-material' else 0o644)
            manifest['files'][name] = sha256(path.read_bytes())
    (output / 'payload.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    return validate_payload(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = build_payload(args.output)
    print('GOODIX_BUILD=PASS SOURCE_ID=' + manifest['source_id'])


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        raise SystemExit(f'GOODIX_BUILD=STOP {error}')
