#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
INSTALL = HERE / "install.sh"
NAMES = (
    "libfprint-2.so.2.0.0",
    "libgusb.so.2",
    "libopencv_core.so.413",
    "libopencv_features2d.so.413",
    "libopencv_flann.so.413",
    "libopencv_imgproc.so.413",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class D293NativePatchTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="d293-native-test.", dir="/tmp"))
        self.commands = self.base / "commands"
        self.commands.mkdir()
        self.candidate = self.base / "candidate"
        self.candidate.mkdir()
        self.head = "a" * 40
        for name in NAMES:
            (self.candidate / name).write_bytes(("candidate-" + name).encode())
        (self.candidate / "deploy.sha256").write_text(
            "".join(f"{sha(self.candidate / name)}  {name}\n" for name in NAMES)
        )
        self._make_previous_d285()
        self._make_commands()
        self.env = os.environ.copy()
        self.env.update(
            D293_NATIVE_TEST_MODE="true",
            D293_NATIVE_TEST_ROOT=str(self.base),
            D293_NATIVE_TEST_COMMAND_DIR=str(self.commands),
        )

    def tearDown(self):
        shutil.rmtree(self.base)

    def _write(self, relative: str, data: str, mode: int = 0o644) -> Path:
        path = self.base / relative.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        path.chmod(mode)
        return path

    def _make_previous_d285(self):
        baseline = "b" * 40
        daemon = self._write("/usr/libexec/fprintd", "fedora-fprintd", 0o755)
        self._write("/usr/lib64/libfprint-2.so.2.0.0", "fedora-lib")
        (self.base / "usr/local/bin").mkdir(parents=True)
        (self.base / "usr/local/sbin").symlink_to("bin", target_is_directory=True)
        wrapper = self._write("/usr/local/sbin/goodix-d285-01-fprintd", "d285-wrapper", 0o755)
        dropin = self._write(
            "/etc/systemd/system/fprintd.service.d/90-goodix-d285-01.conf",
            "[Service]\nExecStart=\nExecStart=/usr/local/sbin/goodix-d285-01-fprintd\n",
        )
        pam = self._write("/etc/pam.d/goodix-d285-01-sudo", "d285-pam")
        sudoers = self._write("/etc/sudoers.d/90-goodix-d285-01", "d285-sudoers", 0o440)
        runtime = self.base / f"usr/local/lib64/goodix-27c6-5125/d285-01-{baseline}"
        runtime.mkdir(parents=True)
        artifact = runtime / "libfprint-2.so.2.0.0"
        artifact.write_text("d285-lib")
        (runtime / "artifacts.sha256").write_text(
            f"{sha(artifact)}  libfprint-2.so.2.0.0\n"
        )
        (runtime / "libfprint-2.so.2").symlink_to("libfprint-2.so.2.0.0")
        (runtime / "libfprint-2.so").symlink_to("libfprint-2.so.2")
        state = self._write(
            "/etc/goodix-27c6-5125/d285-01.state",
            "\n".join(
                (
                    "D285_01_INSTALL_STATUS=ACTIVE",
                    f"D285_01_BASELINE_SHA={baseline}",
                    f"D285_01_RUNTIME=/usr/local/lib64/goodix-27c6-5125/d285-01-{baseline}",
                    f"D285_01_DAEMON_SHA256={sha(daemon)}",
                    f"D285_01_PAM_SHA256={sha(pam)}",
                    f"D285_01_SUDOERS_SHA256={sha(sudoers)}",
                    f"D285_01_WRAPPER_SHA256={sha(wrapper)}",
                    f"D285_01_DROPIN_SHA256={sha(dropin)}",
                    f"D285_01_MANIFEST_SHA256={sha(runtime / 'artifacts.sha256')}",
                )
            )
            + "\n",
            0o600,
        )
        self.previous = {
            str(path.relative_to(self.base)): sha(path)
            for path in (daemon, wrapper, dropin, pam, sudoers, runtime / "artifacts.sha256", state)
        }
        self.previous_parent_modes = {
            self.base / "usr/local/lib64/goodix-27c6-5125": 0o711,
            self.base / "usr/local/bin": 0o713,
            self.base / "etc/systemd/system/fprintd.service.d": 0o750,
            self.base / "etc/goodix-27c6-5125": 0o700,
        }
        for path, mode in self.previous_parent_modes.items():
            path.chmod(mode)

    def _make_commands(self):
        (self.base / "service.state").write_text("inactive\n")
        systemctl = self.commands / "systemctl"
        systemctl.write_text(
            """#!/usr/bin/env bash
set -eu
root=${D293_NATIVE_TEST_ROOT:?}
case $1 in
  is-active) cat "$root/service.state" ;;
  stop) echo inactive >"$root/service.state" ;;
  start) echo active >"$root/service.state" ;;
  daemon-reload) : ;;
  cat)
    printf '%s\n' '[Service]' 'ExecStart=/usr/libexec/fprintd'
    cat "$root/etc/systemd/system/fprintd.service.d/90-goodix-d285-01.conf"
    if [[ -f $root/unit.drift && ! -f $root/etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf ]]; then
      echo UNIT_DRIFT
    fi
    ;;
  show)
    if [[ -f $root/etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf ]]; then
      echo "$root/usr/local/sbin/goodix-d293-native-fprintd"
    else
      echo "$root/usr/local/sbin/goodix-d285-01-fprintd"
    fi
    ;;
  *) exit 2 ;;
esac
"""
        )
        systemctl.chmod(0o755)
        restorecon = self.commands / "restorecon"
        restorecon.write_text("#!/bin/sh\nexit 0\n")
        restorecon.chmod(0o755)

    def run_install(self, expect=0):
        cp = subprocess.run(
            [str(INSTALL), "--root-install", str(self.candidate), self.head, "tester"],
            env=self.env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(cp.returncode, expect, cp.stdout + cp.stderr)
        return cp

    def run_uninstall(self, expect=0):
        cp = subprocess.run(
            [str(INSTALL), "--root-uninstall", "tester"],
            env=self.env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(cp.returncode, expect, cp.stdout + cp.stderr)
        return cp

    def assert_previous_exact(self):
        for relative, expected in self.previous.items():
            self.assertEqual(sha(self.base / relative), expected, relative)
        for path, expected in self.previous_parent_modes.items():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), expected, str(path))
        wrapper_parent = self.base / "usr/local/sbin"
        self.assertTrue(wrapper_parent.is_symlink())
        self.assertEqual(os.readlink(wrapper_parent), "bin")

    def test_install_candidate_and_exact_rollback(self):
        cp = self.run_install()
        self.assertIn("D293_NATIVE_INSTALL=PASS", cp.stdout)
        runtime = self.base / f"usr/local/lib64/goodix-27c6-5125/d293-native-{self.head}"
        self.assertTrue(runtime.is_dir())
        for name in NAMES:
            self.assertEqual((runtime / name).read_bytes(), (self.candidate / name).read_bytes())
        state = self.base / "etc/goodix-27c6-5125/d293-native.state"
        self.assertIn(f"D293_NATIVE_PRODUCTION_HEAD={self.head}", state.read_text())
        cp = self.run_uninstall()
        self.assertIn("D293_NATIVE_ROLLBACK=PASS", cp.stdout)
        self.assertFalse(runtime.exists())
        self.assertFalse(state.exists())
        self.assert_previous_exact()

    def test_active_service_state_is_preserved(self):
        (self.base / "service.state").write_text("active\n")
        self.run_install()
        self.assertEqual((self.base / "service.state").read_text(), "active\n")
        self.run_uninstall()
        self.assertEqual((self.base / "service.state").read_text(), "active\n")
        self.assert_previous_exact()

    def test_parent_directory_modes_are_preserved(self):
        self.run_install()
        for path, expected in self.previous_parent_modes.items():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), expected, str(path))
        self.run_uninstall()
        self.assert_previous_exact()

    def test_uninstall_fails_closed_on_candidate_drift(self):
        self.run_install()
        wrapper = self.base / "usr/local/sbin/goodix-d293-native-fprintd"
        wrapper.write_text("drift")
        cp = self.run_uninstall(expect=1)
        self.assertIn("patch_wrapper_drift", cp.stderr)
        self.assertTrue((self.base / "etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf").exists())
        self.assert_previous_exact()

    def test_unit_snapshot_failure_restores_patch_and_service_state(self):
        self.run_install()
        (self.base / "unit.drift").write_text("true\n")
        cp = self.run_uninstall(expect=1)
        self.assertIn("previous_service_definition_not_restored", cp.stderr)
        self.assertTrue((self.base / "etc/systemd/system/fprintd.service.d/95-goodix-d293-native.conf").exists())
        self.assertTrue((self.base / "etc/goodix-27c6-5125/d293-native.state").exists())
        self.assertEqual((self.base / "service.state").read_text(), "inactive\n")
        self.assert_previous_exact()

    def test_install_fails_closed_on_previous_d285_drift(self):
        (self.base / "usr/local/sbin/goodix-d285-01-fprintd").write_text("drift")
        cp = self.run_install(expect=1)
        self.assertIn("d285_wrapper_drift", cp.stderr)
        self.assertFalse((self.base / "etc/goodix-27c6-5125/d293-native.state").exists())

    def test_entrypoints_use_production_and_not_operator_kit(self):
        install_text = INSTALL.read_text()
        uninstall_text = (HERE / "uninstall.sh").read_text()
        self.assertIn('"$root/production/build.sh" normal', install_text)
        self.assertNotIn("operator_kit/", install_text + uninstall_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
