# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic runtime swaps. No root, systemctl, journal, materials or USB."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('phase_e', Path(__file__).with_name('manage.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class KitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='goodix-phase-e-kit-')
        self.base = Path(self.tmp.name)
        self.runtime = self.base / 'runtime'
        self.state = self.base / 'state'
        self.old = self.base / 'previous'
        self.staged = self.base / 'next'
        self.mask = self.base / 'mask'
        self.payload = self.base / 'payload'
        self.runtime.mkdir(); (self.payload / 'runtime').mkdir(parents=True)
        files = set(m.CHANGED) | {'unchanged-dependency', 'licenses/test.txt'}
        before = {}; after = {}
        for name in files:
            old = ('old-' + name).encode()
            new = ('new-' + name).encode() if name in m.CHANGED else old
            for root, content in [(self.runtime, old), (self.payload / 'runtime', new)]:
                (root / name).parent.mkdir(exist_ok=True)
                (root / name).write_bytes(content)
            before[name] = m.digest(old); after['runtime/' + name] = m.digest(new)
        links = {'libfprint-2.so.2': 'libfprint-2.so.2.0.0'}
        for root in (self.runtime, self.payload / 'runtime'):
            for name, dest in links.items(): (root / name).symlink_to(dest)
        receipt = {'schema': 2, 'source_id': 'b' * 64, 'files': before,
                   'links': links, 'material_selinux': {'owned': True}}
        (self.runtime / 'installation.json').write_text(json.dumps(receipt))
        self.manifest = {'source_id': 'e' * 64, 'files': after,
                         'links': {'runtime/' + n: t for n, t in links.items()}}
        self.calls = []
        self.stopped = False

        def trusted(path, directory=False):
            info = path.lstat()
            self.assertTrue((stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode))
        def read(path):
            trusted(path)
            return path.read_bytes()
        def inventory(receipt): return set(receipt['files']), receipt['links']
        def stop():
            self.assertTrue(self.mask.is_symlink())
            self.calls.append('stop')
            self.stopped = True
        def command(*args):
            self.calls.append(args)
            if args[0] == 'restorecon': self.assertTrue(self.stopped)
            return ''
        self.patches = [patch.object(m, 'STATE', self.state), patch.object(m, 'RUNTIME', self.runtime),
                        patch.object(m, 'OLD', self.old), patch.object(m, 'STAGED', self.staged),
                        patch.object(m.r, 'MASK', self.mask), patch.object(m.r, 'trusted', side_effect=trusted),
                        patch.object(m.r, 'read', side_effect=read), patch.object(m.r, 'runtime_inventory', side_effect=inventory),
                        patch.object(m.r, 'normal_preflight'), patch.object(m.installer, 'host_preflight'),
                        patch.object(m.builder, 'validate_payload', return_value=self.manifest),
                        patch.object(m, 'command', side_effect=command), patch.object(m.r, 'command'),
                        patch.object(m.r, 'stop_and_verify', side_effect=stop)]
        for p in self.patches: p.start()
        self.before = m.snapshot(self.runtime)
        self.old_inode = self.runtime.stat().st_ino

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def test_exact_runtime_restoration_and_idempotence(self):
        m.apply(self.payload)
        self.assertTrue(self.stopped)
        self.assertEqual(m.snapshot(self.old), self.before)
        self.assertFalse(self.mask.is_symlink())
        after = m.snapshot(self.runtime)
        self.assertNotEqual(after, self.before)
        m.apply(self.payload)
        self.assertEqual(m.snapshot(self.runtime), after)
        m.rollback()
        self.assertEqual(m.snapshot(self.runtime), self.before)
        self.assertEqual(self.runtime.stat().st_ino, self.old_inode)
        self.assertFalse(self.old.exists())
        self.assertFalse(self.mask.is_symlink())
        m.rollback()

    def test_corrupt_candidate_and_changed_dependency(self):
        target = self.payload / 'runtime/libfprint-2.so.2.0.0'
        target.write_text('corrupt')
        with self.assertRaises(RuntimeError): m.apply(self.payload)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.staged.exists())
        self.assertFalse(self.stopped)
        self.manifest['files']['runtime/unchanged-dependency'] = '0' * 64
        with self.assertRaises(RuntimeError): m.apply(self.payload)
        self.assertEqual(m.snapshot(self.runtime), self.before)

    def test_payload_symlink_refused(self):
        target = self.payload / 'runtime/libfprint-2.so.2.0.0'
        target.unlink(); target.symlink_to('/dev/null')
        with self.assertRaises(OSError): m.apply(self.payload)
        self.assertFalse(self.staged.exists())
        self.assertFalse(self.stopped)

    def test_foreign_mask_or_backup_preserved(self):
        self.mask.symlink_to('/dev/null')
        with self.assertRaises(RuntimeError): m.apply(self.payload)
        self.assertTrue(self.mask.is_symlink())
        self.assertFalse(self.state.exists())
        self.mask.unlink(); self.old.mkdir()
        with self.assertRaises(RuntimeError): m.apply(self.payload)
        self.assertTrue(self.old.exists())
        self.assertFalse(self.stopped)

    def test_failure_after_swap_restores_old(self):
        original = m.command
        count = 0
        def fail_once(*args):
            nonlocal count
            if args[0] == 'restorecon':
                count += 1
                if count == 1: raise RuntimeError('synthetic label error')
            return original(*args)
        with patch.object(m, 'command', side_effect=fail_once):
            with self.assertRaisesRegex(RuntimeError, 'label error'): m.apply(self.payload)
        self.assertEqual(m.snapshot(self.runtime), self.before)
        self.assertFalse(self.mask.is_symlink())
        self.assertFalse(self.old.exists())

    def test_error_stopping_keeps_runtime_and_owned_mask(self):
        with patch.object(m.r, 'stop_and_verify', side_effect=RuntimeError('stop failed')):
            with self.assertRaises(RuntimeError): m.apply(self.payload)
        self.assertEqual(m.snapshot(self.runtime), self.before)
        self.assertTrue(self.mask.is_symlink())
        m.rollback()
        self.assertFalse(self.mask.is_symlink())

    def test_external_runtime_or_backup_change_blocks_rollback(self):
        m.apply(self.payload)
        (self.runtime / 'libfprint-2.so.2.0.0').write_text('external replacement')
        self.stopped = False
        with self.assertRaises(RuntimeError): m.rollback()
        self.assertFalse(self.stopped)
        self.assertTrue(self.old.exists())

    def test_interrupted_swap_restored_without_start(self):
        after = m.stage(self.payload, self.manifest, self.before)
        self.state.mkdir()
        data = {'schema': 1, 'phase': 'prepared', 'source_id': 'e' * 64,
                'before': self.before, 'after': after, 'since': '2026-09-27T00:00:00+00:00', 'mask_inode': None}
        m.write_state(data)
        m.acquire_mask(data)
        self.runtime.rename(self.old)
        # Simulate termination before publishing STAGED as RUNTIME.
        self.stopped = False
        m.rollback()
        self.assertEqual(m.snapshot(self.runtime), self.before)
        self.assertFalse(self.staged.exists())
        self.assertFalse(self.mask.is_symlink())
        self.assertFalse(any('start' in c for c in self.calls if isinstance(c, tuple)))

    def test_collect_whitelists_metadata(self):
        m.apply(self.payload)
        with patch.object(m, 'command', return_value='unrelated private line\n** GOODIX_ZERO_MASK_RECOVERY event=sample ZERO_MASK_RECOVERY=1\n'), patch('builtins.print') as emit:
            m.collect()
        messages = [c.args[0] for c in emit.call_args_list]
        self.assertFalse(any('private' in s for s in messages))
        self.assertTrue(any(s.startswith('GOODIX_ZERO_MASK_RECOVERY') for s in messages))

    def test_interrupted_receipt_write_uses_last_committed_state(self):
        m.apply(self.payload)
        (self.state / 'state.next').write_text('{incomplete')
        m.rollback()
        self.assertEqual(m.snapshot(self.runtime), self.before)
        self.assertFalse((self.state / 'state.next').exists())

    def test_restore_label_failure_can_be_resumed(self):
        m.apply(self.payload)
        with patch.object(m, 'command', side_effect=RuntimeError('restore label failed')):
            with self.assertRaises(RuntimeError): m.rollback()
        self.assertEqual(m.snapshot(self.runtime), self.before)
        self.assertFalse(self.old.exists())
        self.assertTrue(self.mask.is_symlink())
        m.rollback()
        self.assertFalse(self.mask.is_symlink())

    def test_initial_receipt_failure_leaves_no_changes(self):
        def fail_write(data):
            (self.state / 'state.next').write_text('{incomplete')
            raise OSError('synthetic write failure')
        with patch.object(m, 'write_state', side_effect=fail_write):
            with self.assertRaises(OSError): m.apply(self.payload)
        self.assertEqual(m.snapshot(self.runtime), self.before)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.staged.exists())
        self.assertFalse(self.stopped)

    def test_partial_candidate_deletion_can_be_resumed(self):
        m.apply(self.payload)
        def interrupted_remove(path):
            self.assertEqual(path, self.staged)
            (path / 'libfprint-2.so.2.0.0').unlink()
            raise OSError('interrupted deletion')
        with patch.object(m.shutil, 'rmtree', side_effect=interrupted_remove):
            with self.assertRaises(OSError): m.rollback()
        self.assertEqual(m.snapshot(self.runtime), self.before)
        self.assertTrue(self.mask.is_symlink())
        m.rollback()
        self.assertFalse(self.staged.exists())
        self.assertFalse(self.mask.is_symlink())


if __name__ == '__main__': unittest.main()
