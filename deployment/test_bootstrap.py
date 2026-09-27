#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Execute the documented bootstrap with synthetic Git and installer commands."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://github.com/sorguido/goodix-27c6-5125.git'


class Bootstrap(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='goodix-bootstrap-test-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.repo = self.home / 'goodix-27c6-5125'
        self.log = self.home / 'commands.jsonl'
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        blocks = re.findall(r'```bash\n(.*?)\n```', (ROOT / 'docs/INSTALLATION.md').read_text(), re.S)
        self.assertEqual(len(blocks), 1, 'one canonical installation/update/reinstall block')
        self.block = blocks[0]
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin) + ':/usr/bin:/bin',
                        BOOTSTRAP_LOG=str(self.log), BOOTSTRAP_URL=URL, BOOTSTRAP_FAIL='')
        self.fixture = self.home / 'install-fixture'
        self.fixture.write_text('#!/bin/sh\nprintf "installed\\n" > "$HOME/installed"\n')
        self.fixture.chmod(0o755)
        git = self.bin / 'git'
        git.write_text('''#!/usr/bin/python3
import json, os, pathlib, shutil, sys
args = sys.argv[1:]
with open(os.environ['BOOTSTRAP_LOG'], 'a') as log:
    log.write(json.dumps(args) + '\\n')
if args[0] == 'clone':
    assert args[1] == os.environ['BOOTSTRAP_URL']
    if os.environ['BOOTSTRAP_FAIL'] == 'clone': sys.exit(9)
    repo = pathlib.Path(args[2])
    (repo / '.git').mkdir(parents=True)
    shutil.copy2(pathlib.Path(os.environ['HOME']) / 'install-fixture', repo / 'install.sh')
elif args[0] == '-C' and args[2:] == ['remote', 'get-url', 'origin']:
    print(os.environ['BOOTSTRAP_URL'])
elif args[0] == '-C' and args[2:] == ['pull', '--ff-only']:
    if os.environ['BOOTSTRAP_FAIL'] == 'pull': sys.exit(9)
else:
    raise AssertionError(args)
''')
        git.chmod(0o755)

    def existing_clone(self):
        (self.repo / '.git').mkdir(parents=True)
        (self.repo / 'install.sh').write_bytes(self.fixture.read_bytes())
        (self.repo / 'install.sh').chmod(0o755)

    def run_block(self):
        return subprocess.run(['/bin/bash', '-c', self.block], cwd=self.home, env=self.env,
                              capture_output=True, text=True, timeout=10)

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_absent_path_clones_then_installs(self):
        result = self.run_block()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.commands(), [['clone', URL, str(self.repo)]])
        self.assertTrue((self.home / 'installed').exists())

    def test_existing_clone_pulls_then_installs(self):
        self.existing_clone()
        result = self.run_block()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.commands(), [['-C', str(self.repo), 'remote', 'get-url', 'origin'],
                                          ['-C', str(self.repo), 'pull', '--ff-only']])
        self.assertTrue((self.home / 'installed').exists())

    def test_conflicting_paths_stop_without_git_or_install(self):
        for kind in ('directory', 'file', 'dangling-link'):
            with self.subTest(kind=kind):
                if kind == 'directory': self.repo.mkdir()
                elif kind == 'file': self.repo.touch()
                else: self.repo.symlink_to(self.home / 'missing')
                result = self.run_block()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('STOP:', result.stdout)
                self.assertFalse((self.home / 'installed').exists())
                self.assertFalse(self.commands())
                if kind == 'directory': self.repo.rmdir()
                else: self.repo.unlink()

    def test_unrelated_git_clone_is_preserved(self):
        self.existing_clone()
        self.env['BOOTSTRAP_URL'] = 'https://github.com/unrelated/project.git'
        result = self.run_block()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('STOP:', result.stdout)
        self.assertFalse((self.home / 'installed').exists())
        self.assertEqual(len(self.commands()), 1)

    def test_git_failure_never_runs_installer(self):
        for action in ('clone', 'pull'):
            with self.subTest(action=action):
                if action == 'pull': self.existing_clone()
                self.env['BOOTSTRAP_FAIL'] = action
                self.assertEqual(self.run_block().returncode, 9)
                self.assertFalse((self.home / 'installed').exists())


if __name__ == '__main__':
    unittest.main()
