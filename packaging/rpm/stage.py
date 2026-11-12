#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""RPM build/install staging only: no host changes, network or sensor access."""
import argparse
import gzip
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('builder', ROOT / 'production/build-public.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

MANAGER_FILES = ('main.py', 'model.py', 'diagnostics.py', 'reader.py',
                 'Main.qml', 'DiagnosticPage.qml')
MANAGER_ICONS = ('diagnostic-pulse.svg', 'fingerprint.svg', 'gear.svg', 'layers.svg',
                 'usb.svg', 'checklist.svg', 'sliders.svg', 'flask.svg', 'document.svg',
                 'monitor.svg', 'download.svg', 'more.svg', 'shield.svg', 'chevron-down.svg')


def copy(source, target, mode=0o644):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(mode)


def install_manager(source, target):
    """Stage the explicit desktop allowlist, never tests or private source files."""
    for name in MANAGER_FILES:
        copy(source / name, target / name, 0o755 if name == 'main.py' else 0o644)
    for name in MANAGER_ICONS:
        copy(source / 'diagnostic-icons' / name, target / 'diagnostic-icons' / name)


def install(payload, root, release):
    manifest = builder.validate_payload(payload)
    base = root / 'usr/lib/goodix-manager'
    base.mkdir(parents=True)
    shutil.copytree(payload, base / 'payload', symlinks=True)
    (base / 'payload').chmod(0o755)
    backend_files = ('deployment/install.py', 'deployment/materials.py',
                     'deployment/recovery/remove.py',
                     'deployment/plasma-login-opt-in/plasmalogin.pam',
                     'production/build-public.py', 'production/build-chicago-native.py')
    for name in backend_files:
        copy(ROOT / name, base / 'backend' / name, 0o755 if name.endswith('.py') else 0o644)
        if name.endswith('.py'):
            path = base / 'backend' / name
            content = path.read_bytes()
            if content.startswith(b'#!/usr/bin/env python3\n'):
                path.write_bytes(b'#!/usr/bin/python3 -I\n' + content.split(b'\n', 1)[1])
    install_manager(ROOT / 'packaging/rpm/manager', base / 'manager')
    metadata = dict(schema=1, version=builder.project_version(), release=int(release),
                    fedora=44, arch='x86_64', source_id=manifest['source_id'])
    (base / 'package.json').write_text(json.dumps(metadata, sort_keys=True) + '\n')
    copy(ROOT / 'packaging/rpm/helper.py', root / 'usr/libexec/goodix-manager-helper', 0o755)
    launcher = root / 'usr/bin/goodix-manager'
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text('#!/bin/sh\nexec /usr/bin/python3 -I -B /usr/lib/goodix-manager/manager/main.py "$@"\n')
    launcher.chmod(0o755)
    appid = 'io.github.sorguido.GoodixManager'
    copy(ROOT / 'packaging/rpm/manager' / (appid + '.svg'), base / 'manager' / (appid + '.svg'))
    for suffix, destination in (('desktop', 'applications'), ('metainfo.xml', 'metainfo'),
                                ('svg', 'icons/hicolor/scalable/apps')):
        copy(ROOT / 'packaging/rpm/manager' / (appid + '.' + suffix),
             root / 'usr/share' / destination / (appid + '.' + suffix))
    copy(ROOT / 'packaging/rpm/org.goodix.Manager.policy',
         root / 'usr/share/polkit-1/actions/org.goodix.Manager.policy')
    manual = root / 'usr/share/man/man1/goodix-manager.1.gz'
    manual.parent.mkdir(parents=True, exist_ok=True)
    manual.write_bytes(gzip.compress((ROOT / 'packaging/rpm/goodix-manager.1').read_bytes(), mtime=0))
    assert builder.validate_payload(base / 'payload') == manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    build = sub.add_parser('build')
    build.add_argument('--output', type=Path, required=True)
    stage = sub.add_parser('install')
    stage.add_argument('--payload', type=Path, required=True)
    stage.add_argument('--root', type=Path, required=True)
    stage.add_argument('--release', required=True)
    args = parser.parse_args()
    if args.action == 'build':
        builder.build_payload(args.output.absolute().resolve(), work_root=ROOT.parent)
    else:
        install(args.payload.resolve(), args.root.resolve(), args.release)


if __name__ == '__main__':
    main()
