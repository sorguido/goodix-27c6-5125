#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Manager-only staging fixtures; no payload build, RPM, installation or host IO."""
import importlib.util
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('goodix_stage', HERE / 'stage.py')
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class ManagerStaging(unittest.TestCase):
    def test_explicit_allowlist_contains_all_runtime_dependencies_and_no_tests(self):
        required = {'main.py', 'model.py', 'diagnostics.py', 'reader.py', 'Main.qml', 'DiagnosticPage.qml'}
        self.assertEqual(set(stage.MANAGER_FILES), required)
        self.assertEqual(len(stage.MANAGER_ICONS), 14)
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'destination'
            source.mkdir()
            (source / 'diagnostic-icons').mkdir()
            for name in required:
                (source / name).write_text('source fixture: ' + name)
            for name in stage.MANAGER_ICONS:
                (source / 'diagnostic-icons' / name).write_text('<svg>fixture</svg>')
            (source / 'test_do_not_ship.py').write_text('excluded')
            (source / 'diagnostic-icons/private-note.txt').write_text('excluded')
            (source / 'diagnostic-icons/unapproved.svg').write_text('excluded')
            with patch.object(stage.builder, 'build_payload', side_effect=AssertionError('no payload build')):
                stage.install_manager(source, target)
            expected = required | {'diagnostic-icons/' + name for name in stage.MANAGER_ICONS}
            actual = {str(p.relative_to(target)) for p in target.rglob('*') if p.is_file()}
            self.assertEqual(actual, expected)
            for name in expected:
                path = target / name
                self.assertEqual(path.read_bytes(), (source / name).read_bytes())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755 if name == 'main.py' else 0o644)

    def test_staged_real_modules_import_in_isolated_process_without_source_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'manager'
            stage.install_manager(HERE / 'manager', target)
            script = '''import importlib, pathlib, sys
sys.path.insert(0, sys.argv[1])
for name in ('main', 'model', 'diagnostics', 'reader'):
    module = importlib.import_module(name)
    assert pathlib.Path(module.__file__).parent == pathlib.Path(sys.argv[1])
print('staged imports only')
'''
            completed = subprocess.run([sys.executable, '-I', '-B', '-c', script, str(target)],
                                       cwd=directory, capture_output=True, text=True, timeout=10, check=True)
            self.assertEqual(completed.stdout.strip(), 'staged imports only')
            self.assertEqual(completed.stderr, '')
            qml = (target / 'DiagnosticPage.qml').read_text()
            self.assertIn('diagnostic-icons/', qml)
            for name in stage.MANAGER_ICONS:
                self.assertTrue((target / 'diagnostic-icons' / name).is_file())

    def test_future_spec_owns_the_manager_subtree_without_activation(self):
        spec = (HERE / 'goodix-manager.spec.in').read_text()
        self.assertIn('/usr/lib/goodix-manager/', spec.split('%files\n')[1])
        for scriptlet in ('%pre\n', '%post\n', '%preun\n', '%postun\n', '%posttrans'):
            self.assertNotIn(scriptlet, spec)


if __name__ == '__main__':
    unittest.main()
