#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Public build contract with synthetic compiler/package outputs; no real build."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name('build-public.py')
SPEC = importlib.util.spec_from_file_location('public_build', SOURCE)
b = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(b)


class PublicBuild(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='goodix-public-build-test-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'arbitrary clone with spaces'
        self.output = self.base / 'built payload'
        self.root.mkdir()
        self.commands = []
        self.bad_abi = False
        self.bad_link = False
        self.test_symbol = False
        self.pam_test_failure = False
        self.material_test_failure = False
        self.package_root = self.base / 'synthetic-fedora'
        self.include = self.package_root / 'include/opencv4'
        self.include.mkdir(parents=True)
        self.libdir = self.package_root / 'lib64'
        self.libdir.mkdir()
        for part in b.OPENCV_PARTS:
            library = self.libdir / f'libopencv_{part}.so.4.13.0'
            library.write_bytes(b'SYNTHETIC FEDORA OPENCV ' + part.encode())
            (self.libdir / f'libopencv_{part}.so').symlink_to(library.name)
        for relative in [b.LIBFPRINT_SOURCE / 'meson.build', Path('libfprint-driver/driver.c'),
                         Path('Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp'),
                         *(Path('deployment') / name for name in
                           ('check-material.c', 'materials.py', 'test_material_native.c', 'test_materials.py')),
                         b.LOGIN_SOURCE / 'pam_goodix_login_gate.c', b.LOGIN_SOURCE / 'plasmalogin.pam',
                         *(b.LOGIN_SOURCE / name for name in ('test_gate.c', 'test_dispatch.c', 'test_dispatch.py')),
                         Path('docs/LICENSING_AND_PROVENANCE.md'),
                         *(Path('LICENSES') / (name + '.txt') for name in b.LICENSES)]:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic source or notice\n')
        (self.root / 'production').mkdir()
        (self.root / 'production/build-public.py').write_bytes(SOURCE.read_bytes())
        (self.root / 'production/host-test-only-symbols.txt').write_text('goodix_forbidden_test_seam\n')
        for name, value in (('ROOT', self.root),):
            self.start(patch.object(b, name, value))
        self.start(patch.object(b, 'prerequisites'))
        self.start(patch.object(b, 'opencv_notices', return_value='Synthetic package license corpus\n'))
        self.start(patch.object(b, 'run', side_effect=self.command))

    def start(self, replacement):
        value = replacement.start()
        self.addCleanup(replacement.stop)
        return value

    def command(self, *args, env=None):
        args = tuple(str(arg) for arg in args)
        self.commands.append((args, env))
        program = args[0]
        if program == 'pkg-config':
            if args[1] == '--modversion':
                return '4.13.0'
            if args[1] == '--variable=includedir':
                return str(self.include)
            if args[1] == '--variable=libdir':
                return str(self.libdir)
            self.assertEqual(args[1:], ('--cflags', '--libs', 'glib-2.0', 'openssl'))
            return '-I/synthetic/glib -lglib-2.0 -lssl -lcrypto'
        if program == 'readelf':
            name = Path(args[-1]).name
            if name.startswith('libopencv_'):
                name = name.replace('.so.4.13.0', '.so.413')
            else:
                name = 'libfprint-2.so.2'
            return f' (SONAME) Library soname: [{name}]'
        if program == 'meson':
            if args[1] == 'setup':
                Path(args[2]).mkdir()
            else:
                self.assertEqual(args[1:3], ('compile', '-C'))
                library = Path(args[3]) / 'libfprint/libfprint-2.so.2.0.0'
                library.parent.mkdir()
                library.write_bytes(b'SYNTHETIC COMPILED LIBFPRINT')
            return ''
        if program == 'cc':
            Path(args[args.index('-o') + 1]).write_bytes(b'SYNTHETIC COMPILED PAYLOAD')
            return ''
        if program == 'python3' and args[3].endswith('/test_materials.py'):
            self.assertTrue(Path(env['GOODIX_MATERIAL_TEST_NATIVE']).is_file())
            if self.material_test_failure:
                raise RuntimeError('synthetic native E4 binding test failed')
            return 'SYNTHETIC_NATIVE_MATERIAL=PASS'
        if Path(program).name == 'test_gate' or program == 'python3':
            if self.pam_test_failure:
                raise RuntimeError('synthetic PAM assertion failed')
            return 'SYNTHETIC_PAM=PASS'
        if program == 'nm':
            if '--undefined-only' in args:
                return ' U fp_context_new@LIBFPRINT_2.0.0'
            if '--defined-only' in args:
                return '0000 T other_function@@LIBFPRINT_2.0.0' if self.bad_abi else \
                       '0000 T fp_context_new@@LIBFPRINT_2.0.0'
            return '0000 T goodix_forbidden_test_seam' if self.test_symbol else ''
        if program == 'ldd':
            return 'libmissing.so => not found' if self.bad_link else \
                   'libfprint-2.so.2 => ' + env['LD_LIBRARY_PATH'] + '/libfprint-2.so.2'
        if program == 'rpm':
            self.assertEqual(args[1], '-q')
            return '\n'.join(name + '-synthetic.fc44.x86_64' for name in args[2:])
        self.fail(f'unexpected host/build command: {args}')

    def build(self):
        return b.build_payload(self.output)

    def test_fresh_public_source_build_without_git_or_internal_files(self):
        manifest = self.build()
        self.assertFalse((self.root / '.git').exists())
        self.assertFalse((self.root / 'development').exists())
        self.assertEqual(manifest, b.validate_payload(self.output))
        self.assertEqual(set(manifest), {'schema', 'source_id', 'files', 'links'})
        self.assertNotIn('payload.json', manifest['files'])
        self.assertEqual(len([name for name in manifest['files'] if '/libopencv_' in name]), 4)
        self.assertEqual((self.output / 'login/plasmalogin.pam').read_bytes(),
                         (self.root / b.LOGIN_SOURCE / 'plasmalogin.pam').read_bytes())
        self.assertEqual((self.output / 'check-material').stat().st_mode & 0o777, 0o755)
        self.assertFalse(any(path.name.startswith('goodix-source-build-') for path in self.base.iterdir()))
        programs = {args[0] for args, _ in self.commands}
        self.assertFalse(programs & {'git', 'sudo', 'dnf', 'flatpak', 'systemctl', 'fprintd'})
        self.assertFalse(any('/dev/bus/usb' in arg or '/sys/bus/usb' in arg
                             for args, _ in self.commands for arg in args))

    def test_compile_contract_minimal_no_generated_target_execution_or_download(self):
        self.build()
        setup, env = next((args, env) for args, env in self.commands if args[:2] == ('meson', 'setup'))
        self.assertIn('--wrap-mode=nodownload', setup)
        self.assertIn('-Ddrivers=goodix_27c6_5125', setup)
        self.assertIn('-Dgoodix_production_minimal=true', setup)
        self.assertIn('-Dintrospection=false', setup)
        self.assertIn('-Dudev_rules=disabled', setup)
        self.assertIn('-Dudev_hwdb=disabled', setup)
        flags = json.loads(next(arg.split('=', 1)[1] for arg in setup if arg.startswith('-Dc_args=')))
        self.assertIn('-DGOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE', flags)
        self.assertTrue(any(str(self.root) in flag for flag in flags))
        checker = next(args for args, _ in self.commands if args[0] == 'cc' and args[-1].endswith('/check-material'))
        self.assertFalse(any('gusb' in arg or 'usb_backend' in arg for arg in checker))
        self.assertIn(str(self.root / 'deployment/check-material.c'), checker)
        native = next(args for args, _ in self.commands if args[0] == 'cc' and args[-1].endswith('/test-material-native'))
        self.assertIn(str(self.root / 'deployment/test_material_native.c'), native)
        self.assertIn(str(self.root / 'libfprint-driver/goodix_action_binding.c'), native)
        self.assertFalse(any('gusb' in arg or 'usb_backend' in arg for arg in native))
        material_run, material_env = next((args, env) for args, env in self.commands
            if args[0] == 'python3' and args[3].endswith('/test_materials.py'))
        self.assertEqual(material_run[1:3], ('-I', '-B'))
        self.assertEqual(material_env['GOODIX_MATERIAL_TEST_NATIVE'], native[-1])
        self.assertEqual(len([args for args, _ in self.commands if args[:2] == ('meson', 'compile')]), 1)
        self.assertTrue(any(Path(args[0]).name == 'test_gate' for args, _ in self.commands))
        dispatch = next(args for args, _ in self.commands if args[0] == 'python3')
        self.assertEqual(dispatch[1:3], ('-I', '-B'))
        self.assertTrue(dispatch[3].endswith('/test_dispatch.py'))
        for path in dispatch[4:6] + dispatch[7:]:
            self.assertNotIn(' ', path)

    def test_failed_synthetic_pam_test_prevents_payload_publication(self):
        self.pam_test_failure = True
        with self.assertRaisesRegex(RuntimeError, 'PAM assertion failed'):
            self.build()
        self.assertFalse((self.output / 'payload.json').exists())

    def test_failed_native_material_test_prevents_payload_publication(self):
        self.material_test_failure = True
        with self.assertRaisesRegex(RuntimeError, 'native E4 binding test failed'):
            self.build()
        self.assertFalse((self.output / 'payload.json').exists())

    def test_source_id_uses_content_not_clone_path_or_private_history(self):
        first = b.source_inventory()
        moved = self.base / 'unrelated location'
        self.root.rename(moved)
        with patch.object(b, 'ROOT', moved):
            self.assertEqual(first, b.source_inventory())
            (moved / 'libfprint-driver/driver.c').write_text('different source\n')
            self.assertNotEqual(first, b.source_inventory())

    def test_existing_or_in_tree_output_is_refused_before_build(self):
        self.output.mkdir()
        with self.assertRaisesRegex(RuntimeError, 'new absolute'):
            self.build()
        with self.assertRaisesRegex(RuntimeError, 'outside the source'):
            b.build_payload(self.root / 'output')
        self.assertEqual(self.commands, [])

    def test_incompatible_abi_and_unresolved_runtime_dependencies_rejected(self):
        self.bad_abi = True
        with self.assertRaisesRegex(RuntimeError, 'stock fprintd ABI'):
            self.build()
        self.assertFalse((self.output / 'payload.json').exists())
        self.output = self.base / 'second payload'
        self.bad_abi = False
        self.bad_link = True
        with self.assertRaisesRegex(RuntimeError, 'dependency resolution'):
            self.build()
        self.assertFalse((self.output / 'payload.json').exists())

    def test_test_only_seam_is_rejected(self):
        self.test_symbol = True
        with self.assertRaisesRegex(RuntimeError, 'test-only entrypoints'):
            self.build()
        self.assertFalse((self.output / 'payload.json').exists())

    def test_payload_content_tamper_and_unexpected_entries_rejected(self):
        self.build()
        checker = self.output / 'check-material'
        original = checker.read_bytes()
        checker.write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError, 'content/type drift'):
            b.validate_payload(self.output)
        checker.write_bytes(original)
        extra = self.output / 'runtime/unexpected-file'
        extra.write_text('extra')
        with self.assertRaisesRegex(RuntimeError, 'unexpected payload entry'):
            b.validate_payload(self.output)
        extra.unlink()
        (self.output / 'extra-dir').mkdir()
        with self.assertRaisesRegex(RuntimeError, 'unexpected payload directory'):
            b.validate_payload(self.output)

    def test_payload_symlink_cannot_redirect_a_file_or_library_link(self):
        self.build()
        library = self.output / 'runtime/libfprint-2.so.2.0.0'
        outside = self.base / 'outside-library'
        outside.write_bytes(library.read_bytes())
        library.unlink()
        library.symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, 'content/type drift'):
            b.validate_payload(self.output)
        library.unlink()
        library.write_bytes(outside.read_bytes())
        link = self.output / 'runtime/libfprint-2.so'
        link.unlink()
        link.symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, 'link drift'):
            b.validate_payload(self.output)

    def test_payload_manifest_cannot_add_traversal_or_omit_a_required_file(self):
        manifest = self.build()
        path = self.output / 'payload.json'
        del manifest['files']['login/plasmalogin.pam']
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(RuntimeError, 'inventory'):
            b.validate_payload(self.output)

    def test_help_from_exported_script_needs_no_packages_or_git(self):
        foreign = self.base / 'cwd'
        foreign.mkdir()
        result = subprocess.run(['python3', '-I', '-B', str(self.root / 'production/build-public.py'), '--help'],
                                cwd=foreign, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--output', result.stdout)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
