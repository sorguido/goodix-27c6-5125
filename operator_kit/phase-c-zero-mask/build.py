#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline native build. Never installs, enumerates, or opens USB."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
spec = importlib.util.spec_from_file_location('public_build', ROOT / 'production/build-public.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def build(output):
    b.prerequisites()
    output = Path(output)
    b.require(output.is_absolute() and not output.exists() and not output.is_symlink(),
              'output must be a new absolute directory')
    inventory = b.source_inventory() + ''.join(
        f'{b.sha256(p.read_bytes())}  {p.relative_to(ROOT)}\n'
        for p in sorted(HERE.iterdir()) if p.is_file())
    version, include, libdir, libraries = b.opencv_inputs()
    output.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix='goodix-phase-c-build-') as tmp:
        work = Path(tmp)
        (work / 'opencv4.pc').write_text(
            f'Name: OpenCV\nDescription: Goodix subset\nVersion: {version}\n'
            f'Libs: -L{shlex.quote(str(libdir))} ' +
            ' '.join('-lopencv_' + p for p in b.OPENCV_PARTS) + '\n'
            f'Cflags: -I{shlex.quote(str(include))}\n')
        env = dict(b.BASE_ENV, PKG_CONFIG_PATH=str(work), CCACHE_DIR=str(work / 'cache'))
        flags = ['-DGOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE', '-DGOODIX_ENABLE_ZERO_MASK_PROBE']
        builddir = work / 'build'
        b.run('meson', 'setup', builddir, ROOT / b.LIBFPRINT_SOURCE,
              '--buildtype=release', '--wrap-mode=nodownload', '-Ddrivers=goodix_27c6_5125',
              '-Dintrospection=false', '-Ddoc=false', '-Dinstalled-tests=false',
              '-Dudev_rules=disabled', '-Dudev_hwdb=disabled', '-Dgoodix_production_minimal=true',
              '-Dc_args=' + json.dumps(flags), '-Dcpp_args=' + json.dumps(flags), env=env)
        b.run('meson', 'compile', '-C', builddir, 'fprint-2', env=env)
        library = builddir / 'libfprint/libfprint-2.so.2.0.0'
        b.require(b.soname(library) == 'libfprint-2.so.2', 'wrong SONAME')
        symbols = set(re.findall(r'\b(goodix_\w+)$', b.run('nm', library), flags=re.M))
        forbidden = set((ROOT / 'production/host-test-only-symbols.txt').read_text().splitlines())
        b.require(not symbols & forbidden, 'test seam in live payload')
        b.require('goodix_fpimage_device_enable_zero_mask_probe@@' in
                  b.run('nm', '-D', '--defined-only', library), 'missing opt-in symbol')
        shutil.copyfile(library, output / 'libfprint-2.so.2')
        for name, path in libraries.items():
            shutil.copyfile(path, output / name)
        public = ROOT / b.LIBFPRINT_SOURCE / 'libfprint'
        pkgflags = shlex.split(b.run('pkg-config', '--cflags', '--libs', 'gio-2.0', 'gusb'))
        b.run('cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', HERE / 'probe.c',
              '-I' + str(public), '-I' + str(builddir / 'libfprint'),
              '-L' + str(output), '-l:libfprint-2.so.2', *pkgflags,
              '-Wl,-z,relro,-z,now', '-o', output / 'probe')
    env = dict(b.BASE_ENV, LD_LIBRARY_PATH=str(output))
    b.require('not found' not in b.run('ldd', output / 'probe', env=env), 'unresolved dependency')
    print(b.run(output / 'probe', '--self-check', env=env))
    (output / 'source-files.sha256').write_text(inventory)
    (output / 'build-provenance.json').write_text(json.dumps({
        'opencv_version': version,
        'packages': b.run('rpm', '-q', *b.BUILD_PACKAGES).splitlines(),
        'probe_macro': True, 'test_seams': False}, sort_keys=True) + '\n')
    (output / 'OpenCV-LICENSES.txt').write_text(b.opencv_notices(libraries))
    for name in b.LICENSES:
        shutil.copyfile(ROOT / 'LICENSES' / (name + '.txt'), output / (name + '.txt'))
    shutil.copyfile(ROOT / 'docs/LICENSING_AND_PROVENANCE.md', output / 'LICENSING_AND_PROVENANCE.md')
    manifest = {'schema': 1, 'source_id': b.sha256(inventory.encode()),
                'files': {p.name: b.sha256(p.read_bytes()) for p in sorted(output.iterdir())}}
    (output / 'probe-payload.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    print('PROBE_PAYLOAD=' + str(output))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: build.py /absolute/new/output')
    build(sys.argv[1])
