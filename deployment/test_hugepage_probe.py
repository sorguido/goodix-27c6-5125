#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Optional native regression check for Fedora 44's OpenCV/oneTBB packages."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class AllocatorProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Path('/usr/lib64/libopencv_core.so.413').exists() or not shutil.which('cc'):
            raise unittest.SkipTest('requires Fedora OpenCV 4.13 and a C compiler')
        cls.directory = tempfile.TemporaryDirectory(prefix='goodix-allocator-test-')
        cls.addClassCleanup(cls.directory.cleanup)
        cls.binary = Path(cls.directory.name) / 'probe'
        cls.env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}
        subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-rdynamic',
                        str(Path(__file__).with_suffix('.c')), '-ldl', '-o', str(cls.binary)],
                       env=cls.env, check=True, capture_output=True, text=True)

    def check_probe(self, response, **environment):
        result = subprocess.run([str(self.binary), response], env=self.env | environment,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(result.stdout, 'PROBES_AT_LIBRARY_LOAD=1\nPROBES_AFTER_100_ALLOCATIONS=1\n')

    def test_denial_is_nonfatal_and_probe_is_per_library_initialization(self):
        self.check_probe('denied')

    def test_hugepage_and_thread_options_do_not_prevent_probe(self):
        self.check_probe('denied', TBB_MALLOC_USE_HUGE_PAGES='0', OPENCV_FOR_THREADS_NUM='1')

    def test_empty_response_preserves_allocator(self):
        self.check_probe('empty')

    def test_fresh_process_probes_again(self):
        self.check_probe('empty')
        self.check_probe('empty')


if __name__ == '__main__':
    unittest.main()
