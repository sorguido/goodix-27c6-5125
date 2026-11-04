#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline tests: no privilege elevation, system mutations, USB or material IO."""
from contextlib import nullcontext, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location('rpm_helper', Path(__file__).with_name('helper.py'))
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
META = {'schema': 1, 'version': '3.0.0', 'release': 1, 'fedora': 44,
        'arch': 'x86_64', 'source_id': 'a' * 64}


class HelperTests(unittest.TestCase):
    def backend(self, *, installed=True, matcher='chicago-type24', version='3.0.0', source_id='a' * 64):
        receipt = {'schema': 2, 'matcher': matcher, 'source_id': source_id}
        provenance = {'source_id': source_id}
        if version is not None:
            receipt['version'] = version
            provenance['version'] = version
        runtime = Path('/fake/runtime')
        def read(path):
            return json.dumps(receipt if path.name == 'installation.json' else provenance).encode()
        r = SimpleNamespace(RUNTIME=runtime, MATERIAL=Path('/fake/protected'),
                            NORMAL=Path('/usr/local/bin/goodix-uninstall'),
                            present=Mock(return_value=installed), normal_preflight=Mock(),
                            read=Mock(side_effect=read), main=Mock(return_value=0),
                            receipt_identity=lambda record: record['source_id'], digest=Mock(return_value=source_id))
        return SimpleNamespace(r=r, software_paths=lambda: [runtime],
                               RUNTIME_PACKAGES=('fprintd',), apply=Mock(),
                               builder=SimpleNamespace(validate_payload=Mock(return_value={'source_id': 'a' * 64})))

    def inspect(self, backend):
        with patch.object(h, 'status_lock', return_value=nullcontext()):
            return h.inspect_runtime(backend, META)

    def test_absent_status_never_reads_receipts_or_material(self):
        backend = self.backend(installed=False)
        value, identity = self.inspect(backend)
        self.assertEqual(value['state'], 'absent')
        self.assertIsNone(identity)
        self.assertFalse(value['enrollment_required'])
        backend.r.read.assert_not_called()
        backend.r.normal_preflight.assert_not_called()

    def test_installed_version_not_inferred_from_payload(self):
        value, _ = self.inspect(self.backend(version=None, source_id='b' * 64))
        self.assertEqual((value['state'], value['message_code']), ('blocked', 'version_unknown'))
        self.assertIsNone(value['runtime_version'])

    def test_released_sigfm_known_with_or_without_version(self):
        for identity, (version, matcher) in h.HISTORICAL.items():
            if matcher != 'sigfm':
                continue
            for declared in (None, version):
                value, guard = self.inspect(self.backend(matcher=matcher, version=declared, source_id=identity))
                self.assertEqual((value['state'], value['message_code']), ('legacy', 'legacy_upgrade_available'))
                self.assertEqual(value['runtime_version'], version)
                self.assertEqual(guard, identity)
                self.assertTrue(value['enrollment_required'])

    def test_unknown_sigfm_and_milan_are_not_promoted(self):
        for matcher in ('sigfm', 'milan-type17'):
            value, _ = self.inspect(self.backend(matcher=matcher, version=None))
            self.assertEqual(value['message_code'], 'legacy_unqualified')
            self.assertFalse(value['enrollment_required'])

    def test_exact_local_source_proves_missing_version(self):
        value, _ = self.inspect(self.backend(version=None))
        self.assertEqual((value['runtime_version'], value['message_code']), ('3.0.0', 'up_to_date'))

    def test_known_chicago_identity_and_specific_equivalence(self):
        identity = next(key for key, value in h.HISTORICAL.items() if value[1] == 'chicago-type24')
        backend = self.backend(version=None, source_id=identity)
        with patch.object(h, 'status_lock', return_value=nullcontext()):
            for local_source in h.CHICAGO_300_EQUIVALENT:
                value, _ = h.inspect_runtime(backend, dict(META, source_id=local_source))
                self.assertEqual((value['runtime_version'], value['message_code']), ('3.0.0', 'up_to_date'))
            value, _ = h.inspect_runtime(backend, META)
            self.assertEqual(value['message_code'], 'source_mismatch')
        backend.r.digest.return_value = 'f' * 64
        with self.assertRaises(h.Blocked):
            self.inspect(backend)

    def test_known_identity_cannot_claim_another_version(self):
        identity = next(iter(h.HISTORICAL))
        with self.assertRaises(h.Blocked):
            self.inspect(self.backend(matcher='sigfm', source_id=identity, version='2.9.0'))

    def test_version_order_is_numeric(self):
        for version, code in [('3.0.0', 'up_to_date'), ('2.10.0', 'update_available'),
                              ('3.10.0', 'downgrade_blocked')]:
            with self.subTest(version=version):
                value, _ = self.inspect(self.backend(version=version))
                self.assertEqual(value['message_code'], code)

    def test_same_version_different_build_is_blocked(self):
        backend = self.backend()
        with patch.object(h, 'status_lock', return_value=nullcontext()):
            value, _ = h.inspect_runtime(backend, dict(META, source_id='c' * 64))
        self.assertEqual((value['state'], value['message_code']), ('blocked', 'source_mismatch'))
        self.assertEqual(value['runtime_version'], '3.0.0')

    def test_packaging_only_upgrade_does_not_reapply_driver(self):
        backend = self.backend(version='3.0.0')
        with patch.object(h, 'status_lock', return_value=nullcontext()), \
                patch.object(h, 'sensor_present', return_value=False):
            for revision in (5, 6):
                metadata = dict(META, release=revision)
                value = h.execute('status', backend, metadata)
                self.assertEqual(value['message_code'], 'up_to_date')
                self.assertEqual(value['package_version'], f'3.0.0-{revision}.fc44')
                with self.assertRaises(h.Blocked):
                    h.execute('update', backend, metadata)
        backend.apply.assert_not_called()
        backend.r.main.assert_not_called()

    def test_receipt_and_provenance_identity_must_agree(self):
        backend = self.backend()
        backend.r.read.side_effect = [json.dumps({'schema': 2, 'matcher': 'chicago-type24',
                                                'source_id': 'a' * 64, 'version': '3.0.0'}).encode(),
                                     json.dumps({'source_id': 'b' * 64, 'version': '3.0.0'}).encode()]
        with self.assertRaises(h.Blocked):
            self.inspect(backend)

    def test_present_version_cannot_be_null_or_malformed(self):
        for bad in (None, '', '3.0', '3.0.0-rc1', 3):
            for corrupt_receipt in (True, False):
                backend = self.backend()
                receipt = {'schema': 2, 'matcher': 'chicago-type24', 'source_id': 'a' * 64,
                           'version': bad if corrupt_receipt else '3.0.0'}
                provenance = {'source_id': 'a' * 64, 'version': '3.0.0' if corrupt_receipt else bad}
                backend.r.read.side_effect = [json.dumps(receipt).encode(), json.dumps(provenance).encode()]
                with self.subTest(value=bad, receipt=corrupt_receipt), self.assertRaises(h.Blocked):
                    self.inspect(backend)

    def test_provenance_matcher_when_present_must_match_receipt(self):
        for matcher in ('sigfm', 'milan-type17', None, ''):
            backend = self.backend()
            backend.r.read.side_effect = [
                json.dumps({'schema': 2, 'matcher': 'chicago-type24',
                            'source_id': 'a' * 64, 'version': '3.0.0'}).encode(),
                json.dumps({'source_id': 'a' * 64, 'version': '3.0.0',
                            'matcher': matcher}).encode()]
            with self.subTest(matcher=matcher), self.assertRaises(h.Blocked):
                self.inspect(backend)

    def test_status_reads_only_runtime_software(self):
        backend = self.backend()
        self.inspect(backend)
        self.assertEqual([call.args[0] for call in backend.r.read.call_args_list],
                         [backend.r.RUNTIME / 'installation.json', backend.r.RUNTIME / 'build-provenance.json'])
        backend.apply.assert_not_called()
        backend.r.main.assert_not_called()

    def test_update_legacy_or_downgrade_stops_before_apply(self):
        for backend in [self.backend(matcher='sigfm'), self.backend(version='3.1.0')]:
            with patch.object(h, 'status_lock', return_value=nullcontext()), patch.object(h, 'sensor_present', return_value=False):
                with self.assertRaises(h.Blocked):
                    h.execute('update', backend, META)
            backend.apply.assert_not_called()

    def test_install_with_unknown_template_presence_uses_fixed_payload_without_enrollment_claim(self):
        backend = self.backend(installed=False)
        absent = h.response(META, state='absent', result='success')
        installed = h.response(META, state='installed', runtime_version='3.0.0', result='success')
        with patch.object(h, 'inspect_runtime', side_effect=[(absent, None), (installed, 'a' * 64)]), \
             patch.object(h, 'sensor_present', return_value=False), \
             patch.object(h, 'runtime_prerequisites'), patch.object(h, 'read_json', return_value={'version': '3.0.0'}):
            value = h.execute('install', backend, META)
        backend.apply.assert_called_once_with(h.PAYLOAD, backend.r.MATERIAL, 0, expected_source_id=None)
        self.assertEqual(value['result'], 'success')
        self.assertFalse(value['enrollment_required'])
        self.assertTrue(value['reboot_required'])
        backend.r.read.assert_not_called()

    def test_noop_or_racing_update_cannot_report_success(self):
        backend = self.backend()
        before = h.response(META, state='installed', runtime_version='2.2.1', result='success')
        for final_version, final_source in [('2.2.1', 'a' * 64), ('3.0.0', 'b' * 64)]:
            after = h.response(META, state='installed', runtime_version=final_version, result='success')
            with patch.object(h, 'inspect_runtime', side_effect=[(before, 'a' * 64), (after, final_source)]), \
                    patch.object(h, 'sensor_present', return_value=False), \
                    patch.object(h, 'runtime_prerequisites'), \
                    patch.object(h, 'read_json', return_value={'version': '3.0.0'}):
                with self.assertRaisesRegex(h.Blocked, 'runtime_changed'):
                    h.execute('update', backend, META)

    def test_remove_dispatches_normal_entrypoint_and_restores_argv(self):
        backend = self.backend()
        calls = []
        backend.r.main.side_effect = lambda: calls.append(list(h.sys.argv)) or 0
        before = h.response(META, state='legacy', result='success')
        after = h.response(META, state='absent', result='success')
        original = h.sys.argv
        with patch.object(h, 'inspect_runtime', side_effect=[(before, 'b' * 64), (after, None)]), \
             patch.object(h, 'sensor_present', return_value=False):
            value = h.execute('remove', backend, META)
        self.assertEqual(calls, [[str(backend.r.NORMAL)]])
        self.assertIs(h.sys.argv, original)
        self.assertEqual(value['message_code'], 'removed')
        backend.apply.assert_not_called()

    def test_source_mismatch_remains_normally_removable(self):
        backend = self.backend()
        before = h.response(META, state='blocked', message_code='source_mismatch')
        after = h.response(META, state='absent', result='success')
        with patch.object(h, 'inspect_runtime', side_effect=[(before, 'b' * 64), (after, None)]), \
             patch.object(h, 'sensor_present', return_value=False):
            value = h.execute('remove', backend, META)
        backend.r.main.assert_called_once_with()
        self.assertEqual(value['result'], 'success')
        backend.apply.assert_not_called()

    def test_backend_error_and_output_are_never_returned(self):
        backend = self.backend()
        def fail():
            print('private simulated data')
            raise RuntimeError('private simulated exception')
        backend.r.main.side_effect = fail
        current = h.response(META, state='installed', result='success')
        with patch.object(h, 'inspect_runtime', return_value=(current, 'b' * 64)), \
             patch.object(h, 'sensor_present', return_value=False):
            value = h.execute('remove', backend, META)
        self.assertEqual(value['result'], 'failed')
        self.assertNotIn('private', json.dumps(value))

    def test_verified_rollback_vs_incomplete_service_cleanup(self):
        for cleanup_failed in (False, True):
            backend = self.backend(installed=False)
            def fail(*args, **kwargs):
                print('GOODIX_ROLLBACK=PASS PRIOR_PROJECT_SOFTWARE_RESTORED=true', file=h.sys.stderr)
                raise RuntimeError('final service cleanup incomplete' if cleanup_failed else 'original failure')
            backend.apply.side_effect = fail
            absent = h.response(META, state='absent', result='success')
            with patch.object(h, 'inspect_runtime', return_value=(absent, None)), \
                 patch.object(h, 'sensor_present', return_value=False), \
                 patch.object(h, 'runtime_prerequisites'), \
                 patch.object(h, 'read_json', return_value={'version': '3.0.0'}):
                value = h.execute('install', backend, META)
            self.assertEqual(value['result'], 'failed' if cleanup_failed else 'rolled_back')

    def test_rollback_marker_without_restored_identity_is_failure(self):
        backend = self.backend(installed=False)
        def fail(*args, **kwargs):
            print('GOODIX_ROLLBACK=PASS PRIOR_PROJECT_SOFTWARE_RESTORED=true', file=h.sys.stderr)
            raise RuntimeError('original failure')
        backend.apply.side_effect = fail
        absent = h.response(META, state='absent', result='success')
        drifted = h.response(META, state='blocked', result='blocked')
        with patch.object(h, 'inspect_runtime', side_effect=[(absent, None), (drifted, 'c' * 64)]), \
             patch.object(h, 'sensor_present', return_value=False), \
             patch.object(h, 'runtime_prerequisites'), \
             patch.object(h, 'read_json', return_value={'version': '3.0.0'}):
            value = h.execute('install', backend, META)
        self.assertEqual(value['result'], 'failed')

    def test_runtime_dependencies_exclude_build_packages(self):
        backend = self.backend()
        with patch.object(h.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            h.runtime_prerequisites(backend)
        self.assertEqual(run.call_args.args[0], ['/usr/bin/rpm', '-q', 'fprintd'])

    def test_invalid_arguments_never_load_backend(self):
        for args in [[], ['status', '--force'], ['remove', '/tmp/evil'], ['install;id'], ['force-remove']]:
            with patch.object(h, 'load_backend') as load, patch.object(h.resource, 'setrlimit'), \
                 patch.object(h.os, 'umask'), patch.object(h.signal, 'signal'), redirect_stdout(io.StringIO()) as out:
                self.assertEqual(h.main(args), 1)
            load.assert_not_called()
            self.assertEqual(json.loads(out.getvalue())['message_code'], 'invalid_request')

    def test_unprivileged_never_loads_backend(self):
        with patch.object(h.os, 'geteuid', return_value=1000), patch.object(h.resource, 'setrlimit'), \
             patch.object(h.os, 'umask'), patch.object(h.signal, 'signal'), \
             patch.object(h, 'load_backend') as load, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(h.main(['status']), 1)
        load.assert_not_called()
        self.assertEqual(json.loads(out.getvalue())['message_code'], 'authorization_required')

    def test_package_verification_disables_scripts(self):
        with patch.object(h, '__file__', str(h.HELPER)), patch.object(h, 'trusted'), \
             patch.object(h, 'read_json', return_value=META), \
             patch.object(h.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=b'', stderr=b'')) as run:
            self.assertEqual(h.verified_package(), META)
        self.assertEqual(run.call_args.args[0], ['/usr/bin/rpm', '-V', '--noscripts', '--nodeps', 'goodix-manager'])

    def test_package_drift_fails_closed(self):
        with patch.object(h, '__file__', str(h.HELPER)), patch.object(h, 'trusted'), \
             patch.object(h.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout=b'drift', stderr=b'')):
            with self.assertRaises(h.Blocked):
                h.verified_package()

    def test_polkit_has_exact_operation_actions_and_no_retained_auth(self):
        root = ET.parse(Path(__file__).with_name('org.goodix.Manager.policy')).getroot()
        seen = set()
        for action in root.findall('action'):
            annotations = {item.attrib['key']: item.text for item in action.findall('annotate')}
            self.assertEqual(annotations['org.freedesktop.policykit.exec.path'], str(h.HELPER))
            operation = annotations['org.freedesktop.policykit.exec.argv1']
            seen.add(operation)
            self.assertEqual(action.findtext('defaults/allow_active'), 'yes' if operation == 'status' else 'auth_admin')
            self.assertEqual(action.findtext('defaults/allow_any'), 'no')
            self.assertEqual(action.findtext('defaults/allow_inactive'), 'no')
        self.assertEqual(seen, h.OPERATIONS)


if __name__ == '__main__':
    unittest.main()
