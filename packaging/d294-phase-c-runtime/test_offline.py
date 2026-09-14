#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import pathlib
import subprocess
import unittest

HERE = pathlib.Path(__file__).resolve().parent


class StaticContract(unittest.TestCase):
    def read(self, name: str) -> str:
        return (HERE / name).read_text(encoding="utf-8")

    def test_shell_syntax(self):
        for name in ("build-rpm.sh", "install.sh", "uninstall.sh", "goodix-27c6-5125-fprintd-wrapper"):
            subprocess.run(["bash", "-n", str(HERE / name)], check=True)

    def test_package_does_not_own_pam_or_usr_local(self):
        spec = self.read("goodix-27c6-5125-runtime.spec.in")
        self.assertNotIn("/pam.d/", spec)
        self.assertNotIn("/usr/local", spec)
        self.assertIn("%{_sysconfdir}/systemd/system/fprintd.service.d/99-goodix-27c6-5125-runtime.conf", spec)

    def test_runtime_dependencies_are_explicit(self):
        spec = self.read("goodix-27c6-5125-runtime.spec.in")
        for requirement in (
            "fprintd = 1.94.5-5.fc44",
            "libfprint = 1.94.100-1.fc44",
            "libgusb = 0.4.9-5.fc44",
            "opencv-core = 4.13.0-1.fc44",
            "opencv-features2d = 4.13.0-1.fc44",
            "opencv-flann = 4.13.0-1.fc44",
            "opencv-imgproc = 4.13.0-1.fc44",
        ):
            self.assertIn(requirement, spec)

    def test_wrapper_is_fail_closed_and_content_free(self):
        wrapper = self.read("goodix-27c6-5125-fprintd-wrapper")
        self.assertIn("GOODIX_PHASE_C_RUNTIME=FAIL", wrapper)
        self.assertIn("stat -c '%u:%g:%a'", wrapper)
        self.assertIn("FP_DRIVERS_ALLOWLIST=goodix_27c6_5125", wrapper)
        self.assertNotIn("sha256sum $path", wrapper)
        self.assertNotIn("cat $path", wrapper)

    def test_dropin_has_single_packaged_execstart(self):
        lines = [line.strip() for line in self.read("99-goodix-27c6-5125-runtime.conf").splitlines()]
        self.assertEqual(lines.count("ExecStart="), 1)
        self.assertEqual(lines.count("ExecStart=/usr/libexec/goodix-27c6-5125/fprintd-wrapper"), 1)

    def test_install_preserves_d293_and_b5_as_fallback(self):
        install = self.read("install.sh")
        uninstall = self.read("uninstall.sh")
        for text in (install, uninstall):
            self.assertIn("goodix-d293-native-fprintd", text)
            self.assertIn("50-goodix-fprint-account-delete", text)
        self.assertNotIn("dnf5 remove -y goodix-d293", uninstall)

    def test_privileged_install_rechecks_provenance_and_freezes_rpm(self):
        install = self.read("install.sh")
        self.assertGreaterEqual(install.count("branch --show-current"), 2)
        self.assertIn("/var/tmp/goodix-d294-root.", install)
        self.assertIn('install -m 0600 "$rpm_path" "$root_work/candidate.rpm"', install)
        self.assertIn("--disablerepo='*'", install)

    def test_rollback_is_exact_and_narrow(self):
        install = self.read("install.sh")
        uninstall = self.read("uninstall.sh")
        for key in (
            "D294_01_UNIT_BEFORE_SHA256",
            "D294_01_D293_WRAPPER_SHA256",
            "D294_01_D293_DROPIN_SHA256",
            "D294_01_B5_HOOK_SHA256",
        ):
            self.assertIn(key, install)
            self.assertIn(key, uninstall)
        self.assertIn('rpm -V "$package"', uninstall)
        self.assertIn('rpm -e "${remove_packages[@]}"', uninstall)
        self.assertNotIn('dnf5 remove', uninstall)

    def test_dependency_cleanup_is_stateful(self):
        install = self.read("install.sh")
        uninstall = self.read("uninstall.sh")
        self.assertIn("D294_01_OPENCV_FEATURES2D_BEFORE", install)
        self.assertIn("D294_01_OPENCV_FLANN_BEFORE", install)
        self.assertIn("features_before == false", uninstall)
        self.assertIn("flann_before == false", uninstall)

    def test_no_pam_mutation_or_biometric_action_in_scripts(self):
        combined = "\n".join(self.read(name) for name in ("install.sh", "uninstall.sh", "build-rpm.sh"))
        for forbidden in ("authselect select", "authselect enable-feature", "fprintd-enroll", "fprintd-verify", "pam_fprintd.so"):
            self.assertNotIn(forbidden, combined)


class BuiltRpmContract(unittest.TestCase):
    rpm_path: pathlib.Path | None = None

    def query(self, *args: str) -> str:
        assert self.rpm_path is not None
        return subprocess.run(["rpm", *args, str(self.rpm_path)], check=True, text=True, capture_output=True).stdout

    def test_built_rpm_metadata(self):
        if self.rpm_path is None:
            self.skipTest("no --rpm supplied")
        self.assertEqual(self.query("-qp", "--qf", "%{NAME}"), "goodix-27c6-5125-runtime")

    def test_built_rpm_file_surface(self):
        if self.rpm_path is None:
            self.skipTest("no --rpm supplied")
        files = self.query("-qpl")
        self.assertIn("/usr/lib64/goodix-27c6-5125/libfprint-2.so.2.0.0", files)
        self.assertIn("/usr/libexec/goodix-27c6-5125/fprintd-wrapper", files)
        self.assertIn("/etc/systemd/system/fprintd.service.d/99-goodix-27c6-5125-runtime.conf", files)
        self.assertNotIn("/pam.d/", files)
        self.assertNotIn("/usr/local", files)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--rpm", type=pathlib.Path)
    known, remaining = parser.parse_known_args()
    BuiltRpmContract.rpm_path = known.rpm
    unittest.main(argv=[__file__, *remaining], verbosity=2)
