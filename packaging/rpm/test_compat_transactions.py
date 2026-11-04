#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""PASS_SYNTHETIC migration fixtures; no root, real secrets, USB or host services.

Reuse the canonical installer test sandbox. Only the initial historical software
is constructed as a fixture; every successful transition calls helper.execute →
install.apply with real payload validation, normal_preflight, lock and rollback.
"""
import contextlib
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

fixture = load('canonical_install_fixture', ROOT / 'deployment/test_install.py')
h = load('compat_helper', HERE / 'helper.py')
m = fixture.m
CLI = 'bdc3729d6467636d06045190f08e3eb3852dcc84181e080f9182984c3f0cc5a4'
SIGFM = 'e67de418620282d54de2ecbd56eb7c74ffd3deec27176cad629e0c55a67e9e18'
RPM300 = 'f259f6f10a60e5facc5a8404f951bce3eb18da2aaefebc8c9a167e4540938d97'


class Transactions(fixture.Installer):
    def setUp(self):
        super().setUp()
        self.ctx.enter_context(patch.object(h, 'PAYLOAD', self.payload))
        self.ctx.enter_context(patch.object(h, 'trusted', side_effect=self.trusted))
        self.ctx.enter_context(patch.object(h, 'sensor_present', return_value=False))
        self.ctx.enter_context(patch.object(h, 'runtime_prerequisites'))
        self.metadata = {'schema': 1, 'version': '3.0.0', 'release': 8, 'fedora': 44,
                         'arch': 'x86_64', 'source_id': RPM300}
        self.package('3.0.0', RPM300)
        self.ctx.enter_context(patch.object(m.os, 'geteuid', return_value=0))

    def package(self, version, source_id):
        """Simulate replacement of package-owned payload only, never runtime."""
        provenance = self.payload / 'runtime/build-provenance.json'
        provenance.write_text(json.dumps({'version': version, 'source_id': source_id}))
        manifest_path = self.payload / 'payload.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['source_id'] = source_id
        manifest['files']['runtime/build-provenance.json'] = m.r.digest(provenance.read_bytes())
        manifest_path.write_text(json.dumps(manifest))
        self.metadata = dict(self.metadata, version=version, source_id=source_id)

    def execute(self, operation):
        return h.execute(operation, m, self.metadata)

    def initial(self, kind='rpm', *, declared=False):
        # Initial fixture creation is not counted as a migration result.
        self.apply()
        if kind in ('sigfm', 'cli', 'schema1'):
            identity = SIGFM if kind == 'sigfm' else CLI
            ledger = HERE / 'fixtures/historical' / ('v2.2.1.sha256' if kind == 'sigfm' else 'c760413.sha256')
            receipt = json.loads((m.r.RUNTIME / 'installation.json').read_bytes())
            receipt['source_id'] = identity
            receipt.pop('version')
            if kind == 'sigfm':
                receipt.pop('matcher')  # Genuine schema-2 SIGFM receipts omitted it.
                names = {'libfprint-2.so.2.0.0', 'OpenCV-LICENSES.txt',
                         'LICENSING_AND_PROVENANCE.md', 'source-files.sha256', 'build-provenance.json',
                         *(f'licenses/{name}.txt' for name in ('GPL-2.0-or-later', 'LGPL-2.1-or-later',
                                                           'GPL-3.0-or-later', 'Apache-2.0')),
                         *(f'libopencv_{part}.so.413' for part in ('core', 'features2d', 'flann', 'imgproc'))}
                self.selinux_modules = [f'{m.r.SELINUX_MODULE_PRIORITY} {m.r.SELINUX_MODULE_NAME} cil']
            else:
                names = set(receipt['files'])
            shutil.rmtree(m.r.RUNTIME)
            m.r.RUNTIME.mkdir(mode=0o755)
            receipt['files'] = {}
            provenance = {'source_id': identity}
            if kind == 'cli':
                provenance['matcher'] = 'chicago-type24'
            if declared:
                receipt['version'] = provenance['version'] = '2.2.1' if kind == 'sigfm' else '3.0.0'
            for name in names:
                path = m.r.RUNTIME / name
                path.parent.mkdir(parents=True, exist_ok=True)
                data = (ledger.read_bytes() if name == 'source-files.sha256' else
                        json.dumps(provenance).encode() if name == 'build-provenance.json' else
                        b'SYNTHETIC HISTORICAL PUBLIC SOFTWARE ' + name.encode())
                path.write_bytes(data)
                path.chmod(0o644)
                receipt['files'][name] = m.r.digest(data)
            for name, target in m.r.LINKS.items():
                (m.r.RUNTIME / name).symlink_to(target)
            (m.r.RUNTIME / 'installation.json').write_text(json.dumps(receipt))
            support = m.r.SUPPORT / 'receipt.json'
            support_receipt = json.loads(support.read_bytes())
            support_receipt['source_id'] = identity
            support.write_text(json.dumps(support_receipt))
        state = m.r.STATE / 'synthetic-pairing-sentinel'
        state.write_bytes(b'SYNTHETIC STATE V2; NOT A REAL PSK')
        state.chmod(0o600)
        m.r.normal_preflight()
        self.events.clear()
        self.preserved = self.protected_snapshot()

    def protected_snapshot(self):
        paths = [self.vendor, self.template, *m.r.MATERIAL.iterdir(), *m.r.STATE.iterdir()]
        return {str(p): (p.read_bytes(), p.stat().st_ino, p.stat().st_uid,
                         p.stat().st_gid, p.stat().st_mode) for p in paths}

    def preserved_and_safe(self):
        self.assertEqual(self.preserved, self.protected_snapshot())
        self.assertFalse(m.r.MASK.is_symlink())
        self.assertFalse(any(call and Path(call[0]).name == 'goodix-force-remove' for call in self.events))
        self.assertFalse(any(call[:2] == ('systemctl', 'start') for call in self.events))
        m.r.normal_preflight()

    def test_rpm_300_to_301_canonical_apply(self):
        self.initial()
        before = (m.r.RUNTIME / 'installation.json').read_bytes()
        self.package('3.0.1', 'b' * 64)
        self.assertEqual((m.r.RUNTIME / 'installation.json').read_bytes(), before)
        status = self.execute('status')
        self.assertEqual((status['runtime_version'], status['message_code']), ('3.0.0', 'update_available'))
        result = self.execute('update')
        self.assertEqual((result['result'], result['runtime_version']), ('success', '3.0.1'))
        self.assertFalse(result['enrollment_required'])
        self.assertEqual(json.loads((m.r.RUNTIME / 'installation.json').read_bytes())['version'], '3.0.1')
        self.preserved_and_safe()
        self.package('3.0.2', 'd' * 64)
        result = self.execute('update')
        self.assertEqual((result['result'], result['runtime_version']), ('success', '3.0.2'))
        self.preserved_and_safe()
        before = (m.r.RUNTIME / 'installation.json').read_bytes()
        self.events.clear()
        self.package('3.0.1', 'b' * 64)
        with self.assertRaisesRegex(h.Blocked, 'downgrade_blocked'):
            self.execute('update')
        self.assertEqual((m.r.RUNTIME / 'installation.json').read_bytes(), before)
        self.assertEqual(self.events, [])

    def test_absent_runtime_installs_future_payload_canonically(self):
        self.assertFalse(m.r.RUNTIME.exists())
        self.package('3.0.1', 'b' * 64)
        self.assertEqual(self.execute('status')['state'], 'absent')
        self.assertFalse(m.r.RUNTIME.exists())
        result = self.execute('install')
        self.assertEqual((result['result'], result['runtime_version']), ('success', '3.0.1'))
        self.assertFalse(result['enrollment_required'])
        self.assertTrue(result['reboot_required'])
        receipt = json.loads((m.r.RUNTIME / 'installation.json').read_bytes())
        provenance = json.loads((m.r.RUNTIME / 'build-provenance.json').read_bytes())
        for record in (receipt, provenance):
            self.assertEqual((record['version'], record['source_id']), ('3.0.1', 'b' * 64))
        self.assertEqual(self.vendor.read_text(), 'Fedora vendor sentinel\n')
        self.assertEqual(self.template.read_bytes(), b'synthetic template sentinel')
        self.assertFalse(m.r.MASK.is_symlink())
        m.r.normal_preflight()

    def test_chicago_software_remove_and_reinstall_preserves_templates_without_enrollment_claim(self):
        self.initial()
        self.package('3.0.1', 'b' * 64)
        updated = self.execute('update')
        self.assertFalse(updated['enrollment_required'])
        self.preserved_and_safe()
        removed = self.execute('remove')
        self.assertEqual((removed['state'], removed['result']), ('absent', 'success'))
        self.assertFalse(removed['enrollment_required'])
        self.assertEqual(self.preserved, self.protected_snapshot())
        self.assertFalse(self.execute('status')['enrollment_required'])
        reinstalled = self.execute('install')
        self.assertEqual((reinstalled['runtime_version'], reinstalled['result']), ('3.0.1', 'success'))
        self.assertFalse(reinstalled['enrollment_required'])
        self.preserved_and_safe()
        refreshed = self.execute('status')
        self.assertEqual(refreshed['message_code'], 'up_to_date')
        self.assertFalse(refreshed['enrollment_required'])

    def test_sigfm_221_to_300_to_301(self):
        self.initial('sigfm')
        result = self.execute('status')
        self.assertEqual((result['runtime_version'], result['message_code']), ('2.2.1', 'legacy_upgrade_available'))
        result = self.execute('update')
        self.assertEqual((result['result'], result['runtime_version']), ('success', '3.0.0'))
        self.assertTrue(result['enrollment_required'] and result['reboot_required'])
        self.assertFalse(any(p.name.startswith('libopencv_') for p in m.r.RUNTIME.iterdir()))
        self.assertEqual(self.selinux_modules, [])
        self.preserved_and_safe()
        self.package('3.0.1', 'b' * 64)
        result = self.execute('update')
        self.assertEqual((result['result'], result['runtime_version']), ('success', '3.0.1'))
        self.preserved_and_safe()

    def test_sigfm_with_version_and_ordinary_remove(self):
        self.initial('sigfm', declared=True)
        self.assertEqual(self.execute('status')['message_code'], 'legacy_upgrade_available')
        result = self.execute('remove')
        self.assertEqual((result['state'], result['result']), ('absent', 'success'))
        self.assertFalse(result['enrollment_required'])
        self.assertEqual(self.preserved, self.protected_snapshot())

    def test_recognized_sigfm_direct_301_upgrade_keeps_mandatory_enrollment_notice(self):
        self.initial('sigfm')
        self.package('3.0.1', 'b' * 64)
        current = self.execute('status')
        self.assertEqual((current['runtime_version'], current['message_code']),
                         ('2.2.1', 'legacy_upgrade_available'))
        self.assertTrue(current['enrollment_required'])
        result = self.execute('update')
        self.assertEqual((result['runtime_version'], result['result']), ('3.0.1', 'success'))
        self.assertTrue(result['enrollment_required'])
        self.preserved_and_safe()

    def test_cli_300_missing_version_up_to_date_then_301(self):
        self.initial('cli')
        before = (m.r.RUNTIME / 'installation.json').read_bytes()
        self.assertEqual(self.execute('status')['message_code'], 'up_to_date')
        with self.assertRaisesRegex(h.Blocked, 'up_to_date'):
            self.execute('update')
        self.assertEqual((m.r.RUNTIME / 'installation.json').read_bytes(), before)
        self.assertEqual(self.events, [])
        self.package('3.0.1', 'b' * 64)
        self.assertEqual(self.execute('status')['message_code'], 'update_available')
        result = self.execute('update')
        self.assertEqual((result['result'], result['runtime_version']), ('success', '3.0.1'))
        self.preserved_and_safe()

    def test_unknown_cli_identity_cannot_inherit_local_version(self):
        self.initial('cli')
        path = m.r.RUNTIME / 'installation.json'
        receipt = json.loads(path.read_bytes())
        receipt['source_id'] = 'c' * 64
        provenance_path = m.r.RUNTIME / 'build-provenance.json'
        provenance_path.write_text(json.dumps({'source_id': 'c' * 64}))
        receipt['files'][provenance_path.name] = m.r.digest(provenance_path.read_bytes())
        path.write_text(json.dumps(receipt))
        for version in ('3.0.0', '3.0.1'):
            self.metadata['version'] = version
            self.assertEqual(self.execute('status')['message_code'], 'version_unknown')
            with self.assertRaisesRegex(h.Blocked, 'version_unknown'):
                self.execute('update')
        self.assertEqual(self.events, [])

    def test_tampered_hash_or_missing_runtime_blocks_before_services(self):
        self.initial('sigfm')
        library = m.r.RUNTIME / 'libfprint-2.so.2.0.0'
        original = library.read_bytes()
        library.write_bytes(b'altered')
        with self.assertRaisesRegex(RuntimeError, 'drift'):
            self.execute('update')
        library.write_bytes(original)
        library.unlink()
        with self.assertRaisesRegex(RuntimeError, 'drifted'):
            self.execute('update')
        self.assertEqual(self.events, [])

    def test_ambiguous_ownership_blocks_before_services(self):
        self.initial('sigfm')
        original = self.trusted
        def ambiguous(path, directory=False):
            if path == m.r.RUNTIME:
                raise RuntimeError('synthetic ownership uncertainty')
            return original(path, directory=directory)
        with patch.object(m.r, 'trusted', side_effect=ambiguous):
            with self.assertRaisesRegex(RuntimeError, 'ownership'):
                self.execute('update')
        self.assertEqual(self.events, [])

    def test_identity_race_under_lock_refuses_replacement(self):
        self.initial('sigfm')
        old = m.r.inhibit_activation
        def raced():
            result = old()
            path = m.r.RUNTIME / 'installation.json'
            receipt = json.loads(path.read_bytes())
            receipt['source_id'] = 'f' * 64
            path.write_text(json.dumps(receipt))
            return result
        with patch.object(m.r, 'inhibit_activation', side_effect=raced):
            result = self.execute('update')
        self.assertEqual(result['result'], 'failed')
        self.assertTrue((m.r.RUNTIME / 'libopencv_core.so.413').exists())
        self.assertEqual(self.preserved, self.protected_snapshot())
        self.assertFalse(m.r.MASK.is_symlink())

    def test_schema1_guard_is_not_absent_identity(self):
        self.initial()
        path = m.r.RUNTIME / 'installation.json'
        receipt = json.loads(path.read_bytes())
        receipt.update(schema=1, build_commit='a' * 40)
        receipt.pop('source_id')
        receipt.pop('matcher')
        shutil.rmtree(m.r.RUNTIME)
        m.r.RUNTIME.mkdir(mode=0o755)
        receipt['files'] = {}
        for name in m.r.RUNTIME_FILES:
            target = m.r.RUNTIME / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'SYNTHETIC SCHEMA1 SOFTWARE ' + name.encode())
            receipt['files'][name] = m.r.digest(target.read_bytes())
        for name, target in m.r.LINKS.items():
            (m.r.RUNTIME / name).symlink_to(target)
        path.write_text(json.dumps(receipt))
        before = path.read_bytes()
        m.r.normal_preflight()
        for expected in (None, 'git:' + 'b' * 40):
            with self.assertRaisesRegex(RuntimeError, 'runtime changed'):
                m.apply(self.payload, m.r.MATERIAL, 0, expected_source_id=expected)
        self.assertEqual(m.r.receipt_identity(receipt), 'git:' + 'a' * 40)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.execute('status')['message_code'], 'legacy_unqualified')
        self.preserved_and_safe()

    def test_same_version_unknown_source_stays_blocked_with_future_payload(self):
        self.initial()
        path = m.r.RUNTIME / 'installation.json'
        receipt = json.loads(path.read_bytes())
        receipt['source_id'] = 'c' * 64
        provenance_path = m.r.RUNTIME / 'build-provenance.json'
        provenance_path.write_text(json.dumps({'source_id': 'c' * 64, 'version': '3.0.0'}))
        receipt['files'][provenance_path.name] = m.r.digest(provenance_path.read_bytes())
        path.write_text(json.dumps(receipt))
        for version in ('3.0.0', '3.0.1'):
            self.package(version, RPM300 if version == '3.0.0' else 'b' * 64)
            self.assertEqual(self.execute('status')['message_code'], 'source_mismatch')
            with self.assertRaisesRegex(h.Blocked, 'source_mismatch'):
                self.execute('update')
        self.assertEqual(self.events, [])

    def test_lock_contention_blocks_second_operation(self):
        self.initial('sigfm')
        fd = os.open(m.r.RUNTIME.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(h.Blocked, 'busy'):
                self.execute('update')
        finally:
            os.close(fd)
        self.assertEqual(self.events, [])

    def test_legacy_failure_and_interruption_restore_software(self):
        self.initial('sigfm')
        before = (m.r.RUNTIME / 'installation.json').read_bytes()
        for error in (RuntimeError('synthetic mid-transaction failure'), KeyboardInterrupt()):
            with patch.object(m, 'install_login', side_effect=error):
                result = self.execute('update')
            self.assertEqual(result['result'], 'rolled_back')
            self.assertEqual((m.r.RUNTIME / 'installation.json').read_bytes(), before)
            self.assertEqual(self.execute('status')['message_code'], 'legacy_upgrade_available')
            self.assertTrue(m.r.NORMAL.is_file() and m.r.FORCE.is_file())
            self.preserved_and_safe()

    def test_incomplete_cleanup_never_reports_success_or_rollback(self):
        self.initial('sigfm')
        original = m.r.release_inhibition
        def failed_cleanup(created):
            original(created)
            raise RuntimeError('synthetic cleanup failure')
        with patch.object(m, 'install_login', side_effect=RuntimeError('synthetic update failure')), \
                patch.object(m.r, 'release_inhibition', side_effect=failed_cleanup):
            result = self.execute('update')
        self.assertEqual((result['result'], result['message_code']), ('failed', 'operation_failed'))
        self.preserved_and_safe()

    def test_status_reads_no_protected_data(self):
        self.initial('sigfm')
        original = m.r.read
        def software_only(path):
            self.assertFalse(path.is_relative_to(m.r.MATERIAL) or path.is_relative_to(m.r.STATE)
                             or path == self.template)
            return original(path)
        with patch.object(m.r, 'read', side_effect=software_only):
            self.assertEqual(self.execute('status')['message_code'], 'legacy_upgrade_available')
        self.assertEqual(self.events, [])


def load_tests(loader, tests, pattern):
    # Reuse setup/utilities, without rerunning the inherited Installer suite.
    return unittest.TestSuite(Transactions(name) for name in Transactions.__dict__ if name.startswith('test_'))

if __name__ == '__main__':
    unittest.main()
