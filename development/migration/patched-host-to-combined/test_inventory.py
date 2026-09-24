#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic files only; never run the privileged entrypoint."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('inventory', HERE / 'inventory.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='goodix-inventory-', dir='/tmp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reader = module.Inventory(str(self.root))

    def put(self, path, data):
        target = self.root / path.lstrip('/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def test_metadata_only_for_protected_and_biometric_files(self):
        self.put('/var/lib/fprint/alice/driver/0/1', b'BIOMETRIC_SENTINEL')
        self.put('/var/lib/goodix-5125-poc/transport-material.bin', b'PSK_SENTINEL')
        self.put('/var/lib/goodix-5125-staging/private.bin', b'STAGING_SENTINEL')
        reads = []
        original = self.reader.read
        def tracked(name, *args):
            reads.append(name)
            return original(name, *args)
        with patch.object(self.reader, 'read', tracked):
            output = json.dumps(self.reader.collect())
        for text in ('BIOMETRIC_SENTINEL', 'PSK_SENTINEL', 'STAGING_SENTINEL'):
            self.assertNotIn(text, output)
            self.assertNotIn(hashlib.sha256(text.encode()).hexdigest(), output)
        self.assertFalse(any(p.startswith(('/var/lib/fprint/', '/var/lib/goodix-5125-')) for p in reads))
        self.assertIn('/var/lib/fprint/alice/driver/0/1', output)

    def test_d285_pin_and_unknown_fields_never_exported(self):
        path = module.CONFIG + '/d285-01.state'
        self.put(path, b'D285_01_INSTALL_STATUS=ACTIVE\nD285_01_TEMPLATE_SHA256=PIN_SENTINEL\n'
                 b'D285_01_TEMPLATE_RELATIVE_PATH=PRIVATE_PIN_PATH\nUNRECOGNIZED=SECRET_SENTINEL\n')
        prefix, suffixes = module.STATE_KEYS['d285-01.state']
        self.reader.env_state(path, {prefix + x for x in suffixes.split()})
        output = json.dumps(self.reader.rows)
        self.assertIn('ACTIVE', output)
        for value in ('PIN_SENTINEL', 'PRIVATE_PIN_PATH', 'SECRET_SENTINEL'):
            self.assertNotIn(value, output)
        self.assertEqual(self.reader.rows[-1]['suppressed_fields'], 3)

    def test_no_writes_or_atime_changes(self):
        target = self.put(module.CONFIG + '/d293-native.state', b'D293_NATIVE_STATUS=ACTIVE\n')
        os.utime(target, ns=(1_000_000_000, 2_000_000_000))
        objects = [self.root, *self.root.rglob('*')]
        before = {p: p.stat() for p in objects}
        with patch('subprocess.Popen', side_effect=AssertionError('No subprocess allowed')):
            self.reader.collect()
        for path, old in before.items():
            new = path.stat()
            self.assertEqual((old.st_mode, old.st_uid, old.st_gid, old.st_size,
                              old.st_atime_ns, old.st_mtime_ns, old.st_ctime_ns),
                             (new.st_mode, new.st_uid, new.st_gid, new.st_size,
                              new.st_atime_ns, new.st_mtime_ns, new.st_ctime_ns))
        self.assertEqual(set(objects), {self.root, *self.root.rglob('*')})

    def test_symlink_ancestor_leaf_hardlink_fifo_refused(self):
        target = self.put('/outside/value', b'UNREAD_SENTINEL')
        (self.root / 'alias').symlink_to('outside', target_is_directory=True)
        (self.root / 'leaf').symlink_to('outside/value')
        for name in ('/alias/value', '/leaf'):
            with self.assertRaises((OSError, ValueError)):
                self.reader.read(name)
        os.link(target, self.root / 'hardlink')
        with self.assertRaises(ValueError):
            self.reader.read('/hardlink')
        os.mkfifo(self.root / 'fifo')
        original = os.open
        def no_data_open(name, flags, *args, **kwargs):
            self.assertFalse(str(name).startswith('/proc/self/fd/'))
            if name == 'fifo':
                self.assertTrue(flags & os.O_PATH)
            return original(name, flags, *args, **kwargs)
        with patch('os.open', side_effect=no_data_open):
            with self.assertRaises(ValueError):
                self.reader.read('/fifo')

    def test_bounds_and_malformed_state_do_not_dump_content(self):
        self.put('/large', b'x' * 65537)
        with self.assertRaises(ValueError):
            self.reader.read('/large')
        path = module.CONFIG + '/login-early.json'
        self.put(path, b'{MALFORMED_SECRET')
        self.reader.attempt(path, lambda: self.reader.json_state(path))
        self.assertEqual(self.reader.issues, 1)
        self.assertNotIn('MALFORMED_SECRET', json.dumps(self.reader.rows))
        for malformed in (b'{"files":[]}', b'[]', b'{"files":{},"files":{}}',
                          b'{"files":{},"status":"PRIVATE_SENTINEL"}'):
            self.put(path, malformed)
            self.reader.attempt(path, lambda: self.reader.json_state(path))
            self.assertEqual(self.reader.rows[-1]['status'], 'UNKNOWN_STOP')
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(self.reader.rows))
        for index in range(129):
            self.put('/many/' + str(index), b'')
        with self.assertRaises(ValueError):
            self.reader.tree('/many', 1)

    def test_state_paths_are_not_followed(self):
        path = module.CONFIG + '/login-early.json'
        self.put(path, json.dumps({'files': {'/var/lib/fprint/alice/1': 'a' * 64}}).encode())
        with self.assertRaises(ValueError):
            self.reader.json_state(path)
        self.assertNotIn('/var/lib/fprint/alice/1', json.dumps(self.reader.rows))
        software = module.RUNTIME + '/login-early/fprintd'
        self.put(path, json.dumps({'status': 'ACTIVE', 'service': 'inactive',
                                 'files': {software: 'a' * 64}}).encode())
        self.reader.json_state(path)
        self.assertEqual(self.reader.rows[-1]['fields']['files'][software], 'a' * 64)
        snapshot = module.CONFIG + '/login-three-backup/snapshot.json'
        self.put(snapshot, json.dumps({'service': 'inactive', 'files': {
            software: {'before': 'a' * 64, 'after': 'b' * 64, 'mode': 0o755}}}).encode())
        self.reader.json_state(snapshot)
        self.assertEqual(self.reader.rows[-1]['fields']['files'][software]['after'], 'b' * 64)

    def test_sudo_selectors_keep_scope_without_other_command_arguments(self):
        path = '/etc/sudoers.d/90-goodix-d285-01'
        self.put(path, b'Defaults:guido pam_service="goodix-d285-01-sudo"\n'
                 b'Defaults:alice pam_login_service=custom-login\n'
                 b'guido ALL=(ALL) /bin/echo UNRELATED_ARGUMENT\n')
        self.reader.sudo_config(path)
        record = self.reader.rows[-1]
        self.assertEqual(record['selectors'][0]['scope'], 'Defaults:guido')
        self.assertIn('goodix-d285-01-sudo', json.dumps(record))
        self.assertIn('pam_login_service', json.dumps(record))
        self.assertNotIn('UNRELATED_ARGUMENT', json.dumps(record))

    def test_actual_entrypoint_refuses_unprivileged_from_other_cwd(self):
        self.assertNotEqual(os.geteuid(), 0, 'Run these tests as an ordinary user')
        result = subprocess.run([sys.executable, '-I', '-B', str(HERE / 'inventory.py')],
                                cwd='/tmp', capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn('INVENTORY=REFUSED', result.stdout)
        self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
