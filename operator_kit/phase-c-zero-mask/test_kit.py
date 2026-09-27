# SPDX-License-Identifier: GPL-2.0-or-later
"""Host-only deployment boundary tests; no root, systemctl, probe or USB calls."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('manage', Path(__file__).with_name('manage.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class KitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='phase-c-kit-test-')
        root = Path(self.tmp.name)
        self.state, self.mask = root / 'state', root / 'fprintd.service'
        self.source = root / 'source'
        self.source.mkdir()
        names = ['probe', 'libfprint-2.so.2', 'source-files.sha256', 'OpenCV-LICENSES.txt',
                 'LICENSING_AND_PROVENANCE.md', 'build-provenance.json', 'GPL-2.0-or-later.txt', 'GPL-3.0-or-later.txt',
                 'LGPL-2.1-or-later.txt', 'Apache-2.0.txt']
        names += ['libopencv_' + p + '.so.410' for p in ('core', 'features2d', 'flann', 'imgproc')]
        for name in names:
            (self.source / name).write_text('synthetic fixture\n')
        manifest = {'schema': 1, 'source_id': m.digest(self.source / 'source-files.sha256'),
                    'files': {p.name: m.digest(p) for p in self.source.iterdir()}}
        (self.source / 'probe-payload.json').write_text(json.dumps(manifest))
        self.patches = [patch.object(m, 'STATE', self.state), patch.object(m, 'MASK', self.mask),
                        patch.object(m.subprocess, 'run'), patch.object(m.resource, 'setrlimit')]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def test_install_and_symmetric_rollback(self):
        m.install(self.source)
        m.validate(self.state / 'payload')
        m.rollback()
        self.assertFalse(self.state.exists())

    def test_corruption_and_symlink_rejected(self):
        (self.source / 'probe').write_text('corrupt')
        with self.assertRaises(RuntimeError): m.install(self.source)
        self.assertFalse(self.state.exists())
        (self.source / 'probe').unlink()
        (self.source / 'probe').symlink_to('/dev/null')
        with self.assertRaises(RuntimeError): m.install(self.source)

    def test_existing_mask_untouched(self):
        m.install(self.source)
        self.mask.symlink_to('/dev/null')
        with self.assertRaises(RuntimeError): m.run(False)
        m.rollback()
        self.assertTrue(self.mask.is_symlink())

    def test_two_manual_runs_no_automatic_retry(self):
        m.install(self.source)
        class Process:
            def __init__(self, *args, **kwargs): self.stdout = io.StringIO('synthetic metadata\n')
            def wait(self, timeout): return 0
        def ctl(*args):
            if args[0] == 'mask': self.mask.symlink_to('/dev/null')
            else: self.mask.unlink()
        with patch.object(m, 'systemctl', side_effect=ctl), patch.object(m.subprocess, 'Popen', side_effect=Process) as launch:
            m.run(False)
            with self.assertRaises(RuntimeError): m.run(False)
            self.assertEqual(launch.call_count, 1)
            m.run(True)
            with self.assertRaises(RuntimeError): m.run(True)
            self.assertEqual(launch.call_count, 2)
            m.rollback()
        self.assertFalse(self.mask.is_symlink())
        self.assertFalse(self.state.exists())

    def test_changed_mask_not_removed(self):
        m.install(self.source)
        (self.state / 'owns-mask').write_text('fprintd.service\n')
        self.mask.write_text('external override')
        with self.assertRaises(RuntimeError): m.rollback()
        self.assertEqual(self.mask.read_text(), 'external override')


if __name__ == '__main__': unittest.main()
