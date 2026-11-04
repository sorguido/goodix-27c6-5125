#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Public build contract with synthetic compiler/package outputs; no real build."""
import importlib.util
import json
import re
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name('build-public.py')
SPEC = importlib.util.spec_from_file_location('public_build', SOURCE)
b = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(b)


class BuildHostCompatibility(unittest.TestCase):
    def test_source_build_allows_fedora_44_and_newer(self):
        for version in ('44', '45', '46'):
            with self.subTest(version=version), \
                    patch.object(b.os, 'geteuid', return_value=1000), \
                    patch.object(b.platform, 'freedesktop_os_release', return_value={'ID': 'fedora', 'VERSION_ID': version}), \
                    patch.object(b.platform, 'machine', return_value='x86_64'), \
                    patch.object(b, 'missing_packages', return_value=[]), \
                    patch.object(b.shutil, 'which', return_value='/usr/bin/tool'):
                b.prerequisites()

    def test_source_build_rejects_unsupported_host(self):
        for distro, version, arch in (('fedora', '43', 'x86_64'), ('ubuntu', '45', 'x86_64'),
                                      ('fedora', '45', 'aarch64'), ('fedora', 'rawhide', 'x86_64')):
            with self.subTest(host=(distro, version, arch)), \
                    patch.object(b.os, 'geteuid', return_value=1000), \
                    patch.object(b.platform, 'freedesktop_os_release', return_value={'ID': distro, 'VERSION_ID': version}), \
                    patch.object(b.platform, 'machine', return_value=arch):
                with self.assertRaises(RuntimeError):
                    b.prerequisites()


class RuntimeAbi(unittest.TestCase):
    def test_host_resolution_rejects_incompatible_or_missing_interfaces(self):
        runtime = Path('/tmp/verified-payload/runtime')
        good_link = f'libfprint-2.so.2 => {runtime}/libfprint-2.so.2'
        for fault in ('none', 'soname', 'required-symbol', 'missing-library',
                      'undefined-symbol', 'foreign-library', 'cpp-dependency'):
            def run(*args, env=None, timeout=None):
                self.assertEqual(timeout, 30)
                if args[0] == 'readelf':
                    name = 'libfprint-2.so.9' if fault == 'soname' else 'libfprint-2.so.2'
                    return f'(SONAME) [{name}]'
                if args[0] == 'nm':
                    if '--undefined-only' in args:
                        return ' U fp_context_new@LIBFPRINT_2.0.0'
                    return '' if fault == 'required-symbol' else ' T fp_context_new@@LIBFPRINT_2.0.0'
                self.assertEqual(args, ('ldd', '-r', '/usr/libexec/fprintd'))
                self.assertEqual(env, dict(b.BASE_ENV, LD_LIBRARY_PATH=str(runtime)))
                return {'missing-library': good_link + '\nlibmissing.so => not found',
                        'undefined-symbol': good_link + '\nundefined symbol: g_missing (/tmp/library)',
                        'foreign-library': 'libfprint-2.so.2 => /usr/lib64/libfprint-2.so.2',
                        'cpp-dependency': good_link + '\nlibstdc++.so.6 => /usr/lib64/libstdc++.so.6'
                        }.get(fault, good_link)
            with self.subTest(fault=fault), patch.object(b, 'run', side_effect=run):
                if fault == 'none':
                    b.verify_runtime_abi(runtime)
                else:
                    with self.assertRaises(RuntimeError):
                        b.verify_runtime_abi(runtime)


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
        for relative in [b.LIBFPRINT_SOURCE / 'meson.build', Path('libfprint-driver/driver.c'),
                         b.native.NATIVE_SOURCE / 'NOTICES.txt',
                         *(Path('deployment') / name for name in
                           ('check-material.c', 'materials.py', 'test_material_native.c', 'test_materials.py')),
                         b.LOGIN_SOURCE / 'pam_goodix_login_gate.c', b.LOGIN_SOURCE / 'plasmalogin.pam',
                         *(b.LOGIN_SOURCE / name for name in ('test_gate.c', 'test_dispatch.c', 'test_dispatch.py')),
                         Path('docs/LICENSING_AND_PROVENANCE.md'),
                         *(Path('LICENSES') / (name + '.txt') for name in b.LICENSES)]:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic source or notice\n')
        (self.root / 'production').mkdir(exist_ok=True)
        (self.root / 'VERSION').write_text('3.0.0\n')
        (self.root / 'production/build-public.py').write_bytes(SOURCE.read_bytes())
        (self.root / 'production/build-chicago-native.py').write_bytes(
            SOURCE.with_name('build-chicago-native.py').read_bytes())
        (self.root / 'production/host-test-only-symbols.txt').write_text('goodix_forbidden_test_seam\n')
        for name, value in (('ROOT', self.root),):
            self.start(patch.object(b, name, value))
        self.start(patch.object(b, 'prerequisites'))
        self.start(patch.object(b, 'validate_chicago_sources', return_value={}))
        self.start(patch.object(b.native, 'build_native', return_value=(
            self.base / 'libnative.a', self.root / b.native.NATIVE_SOURCE, {'native_pic_objects': 94})))
        self.start(patch.object(b, 'run', side_effect=self.command))

    def start(self, replacement):
        value = replacement.start()
        self.addCleanup(replacement.stop)
        return value

    def command(self, *args, env=None, timeout=None):
        args = tuple(str(arg) for arg in args)
        self.commands.append((args, env))
        program = args[0]
        if program == 'pkg-config':
            self.assertIn(args[1:], (('--cflags', '--libs', 'glib-2.0', 'openssl'),
                                    ('--cflags', '--libs', 'gio-2.0', 'gobject-2.0', 'gusb')))
            return '-I/synthetic/glib -lglib-2.0 -lssl -lcrypto'
        if program == 'readelf':
            return ' (SONAME) Library soname: [libfprint-2.so.2]'
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
                   'libfprint-2.so.2 => ' + str(self.output / 'runtime') + '/libfprint-2.so.2'
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
        self.assertFalse(any('opencv' in name.lower() for name in manifest['files']))
        self.assertIn('runtime/ChicagoHS-NOTICES.txt', manifest['files'])
        self.assertEqual((self.output / 'login/plasmalogin.pam').read_bytes(),
                         (self.root / b.LOGIN_SOURCE / 'plasmalogin.pam').read_bytes())
        self.assertEqual((self.output / 'check-material').stat().st_mode & 0o777, 0o755)
        self.assertFalse(any('milan' in name.lower() or 'diagnostic' in name for name in manifest['files']))
        self.assertFalse(any(path.name.startswith('goodix-source-build-') for path in self.base.iterdir()))
        programs = {args[0] for args, _ in self.commands}
        self.assertFalse(programs & {'git', 'sudo', 'dnf', 'flatpak', 'systemctl', 'fprintd'})
        self.assertFalse(any('/dev/bus/usb' in arg or '/sys/bus/usb' in arg
                             for args, _ in self.commands for arg in args))

    def test_chicago_does_not_request_a_cpp_compiler_or_opencv(self):
        self.build()
        self.assertNotIn('gcc-c++', b.BUILD_PACKAGES)
        self.assertNotIn('opencv-devel', b.BUILD_PACKAGES)
        self.assertFalse(any(args[0] in ('c++', 'g++') or any('opencv' in arg for arg in args)
                             for args, _ in self.commands))
        setup = next(args for args, _ in self.commands if args[:2] == ('meson', 'setup'))
        self.assertIn('-Dgoodix_chicago=true', setup)
        self.assertFalse(any(arg.startswith('-Dcpp_args=') for arg in setup))

    def test_missing_native_sources_stops_before_build_or_output(self):
        with patch.object(b, 'validate_chicago_sources', side_effect=RuntimeError(b.native.INCOMPLETE_SOURCE_SET)):
            with self.assertRaisesRegex(RuntimeError, 'native source set is incomplete'):
                self.build()
        self.assertEqual(self.commands, [])
        self.assertFalse(self.output.exists())

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
        dispatch = next(args for args, _ in self.commands if args[0] == 'python3'
                        and args[3].endswith('/test_dispatch.py'))
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


class NativeSourceContract(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='goodix-chicago-source-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / b.native.NATIVE_SOURCE
        shutil.copytree(SOURCE.parents[1] / b.native.NATIVE_SOURCE, self.source)

    def test_complete_snapshot_validates_without_git_or_private_sources(self):
        manifest = b.native.validate_sources(self.root)
        self.assertEqual(manifest['upstream_commit'], b.native.CHICAGO_PIN)
        self.assertFalse((self.root / '.git').exists())
        self.assertFalse((self.root / 'development').exists())

    def test_content_tampering_rejected(self):
        path = self.source / 'NOTICES.txt'
        path.write_text(path.read_text() + 'tampered')
        with self.assertRaisesRegex(RuntimeError, 'source drift'):
            b.native.validate_sources(self.root)

    def test_revision_and_missing_checkout_rejected(self):
        path = self.source / 'source-manifest.json'
        manifest = json.loads(path.read_text())
        manifest['upstream_commit'] = '0' * 40
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(RuntimeError, 'manifest'):
            b.native.validate_sources(self.root)
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            b.native.validate_sources(self.root / 'absent')

    def test_unknown_file_and_symlink_rejected(self):
        path = self.source / 'extra.c'
        path.write_text('unexpected')
        with self.assertRaisesRegex(RuntimeError, 'inventory drift'):
            b.native.validate_sources(self.root)
        path.unlink()
        notice = self.source / 'NOTICES.txt'
        notice.unlink()
        notice.symlink_to(self.source / 'LICENSE')
        with self.assertRaises(RuntimeError):
            b.native.validate_sources(self.root)


def manual_report_leaks(text):
    """Catch obvious reports, not ordinary technical terminology or hex values."""
    keys = ('HUMAN_REQUIRED|NEXT_OPERATOR_ACTION|PUBLIC_EXPORT_CHECK|'
            'LIVE_ACTIONS_PERFORMED|BUILDER_TESTS|EXISTING_REGRESSIONS|'
            'SANITIZER|WORKTREE|PUSH|OUTCOME')
    patterns = (rf'\b(?:{keys})\s*=', r'\bHEAD\s*=\s*[0-9a-f]{7,40}\b',
                r'\b\d+\s+(?:(?:builder|deployment|production|recovery|unit|synthetic)\s+)?tests?\s+(?:passed|pass)\b',
                r'\bRan\s+\d+\s+tests?\b')
    return [pattern for pattern in patterns if re.search(pattern, text, re.IGNORECASE)]


class DocumentationHygieneTests(unittest.TestCase):
    def test_public_manual_has_no_machine_reports(self):
        text = (SOURCE.parents[1] / 'TECHNICAL_MANUAL.md').read_text()
        self.assertEqual(manual_report_leaks(text), [])

    def test_obvious_report_leaks_are_detected(self):
        for text in ('HUMAN_REQUIRED=REVIEW', 'NEXT_OPERATOR_ACTION=RUN',
                     'PUBLIC_EXPORT_CHECK=PASS', 'LIVE_ACTIONS_PERFORMED=NONE',
                     'BUILDER_TESTS=87', 'EXISTING_REGRESSIONS=PASS', 'SANITIZER=PASS',
                     'WORKTREE=CLEAN', 'PUSH=PASS', 'OUTCOME=PASS', 'HEAD=abcdef1234',
                     '78 builder tests passed', 'Ran 78 tests in 1s'):
            self.assertTrue(manual_report_leaks(text), text)

    def test_technical_vocabulary_and_protocol_values_are_allowed(self):
        self.assertEqual(manual_report_leaks('The test must pass on the qualified target. '
            'Observed control 0x90, HEAD field, a 224-byte body and 20 contacts. '
            'These tests cover parser bounds; the checksum must pass validation.'), [])


if __name__ == '__main__':
    unittest.main()
