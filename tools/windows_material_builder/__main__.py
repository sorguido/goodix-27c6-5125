# SPDX-License-Identifier: GPL-2.0-or-later
"""Launch the Windows GUI, or diagnose an offline capture without writing it."""
import argparse
from pathlib import Path
from .diagnostics import Failure


def main():
    parser = argparse.ArgumentParser(description='Goodix 5125 Windows VM Material Builder (development candidate)')
    parser.add_argument('--diagnose', type=Path, help='Read a retained capture offline; print safe codes only. Never builds a bundle.')
    args = parser.parse_args()
    if args.diagnose:
        from .capture import analyze
        try:
            evidence = analyze(args.diagnose)
            for name in ('CONFIG90', 'A2', 'CHIP82', 'A6'):
                print(name + '=' + ('PASS' if name in evidence.selected else 'FAIL'))
            evidence.require_complete()
            return 0
        except Failure as failure:
            print(failure.diagnostic.text())
            return 1
        except Exception:
            print('CAPTURE_TRUNCATED_OR_INVALID')
            return 1
    try:
        from .windows import normal_user
        normal_user()
        from .gui import main as gui
        gui()
        return 0
    except Failure as failure:
        print(failure.diagnostic.text())
        return 1
    except ImportError:
        print('Required Python components are missing. Install Python with Tkinter and the cryptography dependency; see README.md.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
