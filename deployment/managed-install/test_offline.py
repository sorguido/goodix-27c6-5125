#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
TRANSACTION = HERE / "root-transaction.sh"
FILES = (
    "MANIFEST", "SHA256SUMS", "SBOM.spdx.json", "THIRD_PARTY_NOTICES.md",
    "LICENSE", "GPL-2.0-or-later.txt", "LGPL-2.1-or-later.txt",
    "GPL-3.0-or-later.txt", "Apache-2.0.txt", "OpenCV-LICENSES.txt",
    "fprintd", "greeter", "pam_fprintd.so", "99-goodix-login-greeter.conf",
    "login-source.sha256", "fprintd-COPYING", "fprintd-AUTHORS",
    "production-source.sha256", "fprintd-source.sha256",
    "libfprint-2.so.2.0.0",
    "libgusb.so.2", "libopencv_core.so.413", "libopencv_features2d.so.413",
    "libopencv_flann.so.413", "libopencv_imgproc.so.413", "fprintd-wrapper",
    "50-goodix-fprint-account-delete", "goodix_fprint_account_delete.te",
    "goodix_fprint_account_delete.fc", "99-goodix-27c6-5125-managed.conf",
    "plasmalogin-pam.rule", "kde-fingerprint-pam.rule",
)


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ManagedInstallContract(unittest.TestCase):
    def setUp(self):
        self.temp = pathlib.Path(tempfile.mkdtemp(prefix="goodix-managed-test.", dir="/tmp"))
        self.root = self.temp / "root"
        self.root.mkdir()
        self.vendor_pam = self.root / "usr/lib/pam.d/plasmalogin"
        self.vendor_pam.parent.mkdir(parents=True)
        self.vendor_pam.write_text(
            "#%PAM-1.0\n"
            "auth       [success=done ignore=ignore default=bad] pam_selinux_permit.so\n"
            "auth       substack     password-auth\n"
            "auth       optional     pam_kwallet5.so\n"
            "account    include      password-auth\n"
            "password   include      password-auth\n"
            "session    include      password-auth\n"
            "session    optional     pam_kwallet5.so auto_start\n",
            encoding="utf-8",
        )
        unit = self.root / "usr/lib/systemd/user/plasma-login.service"
        unit.parent.mkdir(parents=True)
        unit.write_text("[Service]\nExecStart=/usr/libexec/plasma-login-greeter\n")
        self.vendor_bytes = self.vendor_pam.read_bytes()
        self.kde_fingerprint_pam = self.root / "etc/pam.d/kde-fingerprint"
        self.kde_fingerprint_pam.parent.mkdir(parents=True)
        self.kde_fingerprint_pam.write_text(
            "auth        substack      fingerprint-auth\n"
            "auth        include       postlogin\n\n"
            "account     required      pam_nologin.so\n"
            "account     include       fingerprint-auth\n\n"
            "password    include       fingerprint-auth\n\n"
            "session     required      pam_selinux.so close\n"
            "session     required      pam_loginuid.so\n"
            "session     required      pam_selinux.so open\n"
            "session     optional      pam_keyinit.so force revoke\n"
            "session     required      pam_namespace.so\n"
            "session     include       fingerprint-auth\n"
            "session     include       postlogin\n",
            encoding="utf-8",
        )
        self.kde_vendor_bytes = self.kde_fingerprint_pam.read_bytes()
        self.env = os.environ | {
            "GOODIX_MANAGED_TEST_ROOT": str(self.root),
            "GOODIX_MANAGED_TEST_KDE_VENDOR_SHA256": sha(self.kde_fingerprint_pam),
        }
        self.caller = os.environ.get("USER", "tester")

    def tearDown(self):
        shutil.rmtree(self.temp)

    def candidate(self, commit: str) -> pathlib.Path:
        candidate = self.temp / f"candidate-{commit[0]}"
        candidate.mkdir()
        for name in FILES:
            if name in ("MANIFEST", "SHA256SUMS"):
                continue
            source = HERE / name
            if source.exists():
                shutil.copyfile(source, candidate / name)
            else:
                (candidate / name).write_bytes(f"synthetic-{name}\n".encode())
        (candidate / "MANIFEST").write_text(
            "GOODIX_MANAGED_DISTRIBUTION_MODEL=SOURCE_FIRST_MANAGED_INSTALL\n"
            "RPM_OFFICIAL_DISTRIBUTION=false\n"
            f"SOURCE_COMMIT={commit}\n"
            "TARGET_OS=Fedora-44-KDE-x86_64\n"
            "PROTECTED_MATERIAL_INCLUDED=false\n"
            "PAM_FILES_INCLUDED=true\n"
            "PAM_INTEGRATION=MANAGED_ETC_OVERRIDE_FROM_VENDOR\n"
            "KSCREENLOCKER_PAM_INTEGRATION=MANAGED_PACKAGE_CONFIG_TRANSFORM\n"
            "EARLY_LOGIN_INTEGRATION=PAIRED_FPRINTD_PAM_GREETER_V1\n"
            "SBOM_FORMAT=SPDX-2.3-JSON\n"
            "COMBINED_BINARY_LICENSE=GPL-3.0-or-later\n"
            "FAR_FRR_CLAIM=NOT_MADE\n",
            encoding="utf-8",
        )
        rows = []
        for path in sorted(candidate.iterdir()):
            if path.name != "SHA256SUMS":
                rows.append(f"{sha(path)}  {path.name}\n")
        (candidate / "SHA256SUMS").write_text("".join(rows), encoding="utf-8")
        return candidate

    def run_tx(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(TRANSACTION), *args], env=self.env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check,
        )

    def test_install_idempotent_update_rollback_uninstall(self):
        a = "a" * 40
        b = "b" * 40
        first = self.candidate(a)
        second = self.candidate(b)
        result = self.run_tx("--root-install", self.caller, str(first))
        self.assertIn("GOODIX_MANAGED_INSTALL=PASS", result.stdout)
        runtime_root = self.root / "usr/lib64/goodix-27c6-5125"
        self.assertEqual(runtime_root.stat().st_mode & 0o777, 0o755)
        managed = self.root / "etc/pam.d/plasmalogin"
        self.assertTrue(managed.is_file())
        self.assertEqual(self.vendor_pam.read_bytes(), self.vendor_bytes)
        managed_text = managed.read_text(encoding="utf-8")
        rule = (HERE / "plasmalogin-pam.rule").read_text(encoding="utf-8").strip()
        self.assertEqual(managed_text.count(rule), 1)
        self.assertLess(managed_text.index(rule), managed_text.index("auth       substack     password-auth"))
        self.assertIn("auth       substack     password-auth", managed_text)
        self.assertNotIn(self.caller, managed_text)
        kde_managed_text = self.kde_fingerprint_pam.read_text(encoding="utf-8")
        kde_rule = (HERE / "kde-fingerprint-pam.rule").read_text(encoding="utf-8").strip()
        self.assertEqual(kde_managed_text.count(kde_rule), 1)
        self.assertNotIn("auth        substack      fingerprint-auth", kde_managed_text)
        self.assertIn("account     include       fingerprint-auth", kde_managed_text)
        self.assertIn("session     include       fingerprint-auth", kde_managed_text)
        result = self.run_tx("--root-install", self.caller, str(first))
        self.assertIn("PASS_ALREADY_CURRENT", result.stdout)
        result = self.run_tx("--root-update", self.caller, str(second))
        self.assertIn("GOODIX_MANAGED_UPDATE=PASS", result.stdout)
        status = self.run_tx("--status").stdout
        self.assertIn(f"CURRENT_COMMIT={b}", status)
        self.assertIn(f"PREVIOUS_COMMIT={a}", status)
        result = self.run_tx("--root-rollback", self.caller)
        self.assertIn(f"CURRENT_COMMIT={a}", result.stdout)
        self.assertTrue(managed.is_file())
        result = self.run_tx("--root-uninstall", self.caller)
        self.assertIn("FEDORA_FPRINTD_BASELINE=RESTORED", result.stdout)
        self.assertFalse((self.root / "var/lib/goodix-27c6-5125-managed/state").exists())
        self.assertFalse(managed.exists())
        self.assertEqual(self.vendor_pam.read_bytes(), self.vendor_bytes)
        self.assertEqual(self.kde_fingerprint_pam.read_bytes(), self.kde_vendor_bytes)

    def test_single_attempt_candidate_update_fails_without_host_changes(self):
        first = self.candidate("a" * 40)
        second = self.candidate("b" * 40)
        self.run_tx("--root-install", self.caller, str(first))
        saved = self.root / "var/lib/goodix-27c6-5125-managed/plasmalogin.managed"
        managed = self.root / "etc/pam.d/plasmalogin"
        state = saved.parent / "state"
        old_hash = sha(saved)
        old_pam = saved.read_bytes().replace(b"max-tries=3 timeout=8", b"max-tries=1 timeout=8")
        saved.write_bytes(old_pam)
        managed.write_bytes(old_pam)
        state.write_text(state.read_text().replace(old_hash, sha(saved)))
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = self.run_tx("--root-update", self.caller, str(second), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("single_attempt_pam_requires_previous_uninstall_then_fresh_install", result.stderr)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_legacy_update_adds_pam_and_rollback_restores_absence(self):
        first = self.candidate("1" * 40)
        second = self.candidate("2" * 40)
        self.run_tx("--root-install", self.caller, str(first))
        state = self.root / "var/lib/goodix-27c6-5125-managed/state"
        legacy = "\n".join(
            line for line in state.read_text(encoding="utf-8").splitlines()
            if not line.startswith((
                "CURRENT_PAM_STATUS=", "PREVIOUS_PAM_STATUS=", "PAM_VENDOR_SHA256=", "PAM_OVERRIDE_SHA256=",
                "CURRENT_KSCREENLOCKER_PAM_STATUS=", "PREVIOUS_KSCREENLOCKER_PAM_STATUS=",
                "KSCREENLOCKER_VENDOR_SHA256=", "KSCREENLOCKER_OVERRIDE_SHA256=",
            ))
        ) + "\n"
        state.write_text(legacy, encoding="utf-8")
        (self.root / "etc/pam.d/plasmalogin").unlink()
        (self.root / "var/lib/goodix-27c6-5125-managed/plasmalogin.managed").unlink()
        self.kde_fingerprint_pam.write_bytes(self.kde_vendor_bytes)
        (self.root / "var/lib/goodix-27c6-5125-managed/kde-fingerprint.vendor").unlink()
        (self.root / "var/lib/goodix-27c6-5125-managed/kde-fingerprint.managed").unlink()
        status = self.run_tx("--status").stdout
        self.assertIn("MANAGED_PAM_INTEGRATION=false", status)
        result = self.run_tx("--root-update", self.caller, str(second))
        self.assertIn("GOODIX_MANAGED_UPDATE=PASS", result.stdout)
        self.assertTrue((self.root / "etc/pam.d/plasmalogin").is_file())
        result = self.run_tx("--root-rollback", self.caller)
        self.assertIn("MANAGED_PAM_STATUS=ABSENT", result.stdout)
        self.assertFalse((self.root / "etc/pam.d/plasmalogin").exists())
        result = self.run_tx("--root-rollback", self.caller)
        self.assertIn("MANAGED_PAM_STATUS=ACTIVE", result.stdout)
        self.assertTrue((self.root / "etc/pam.d/plasmalogin").is_file())
        self.assertEqual(self.vendor_pam.read_bytes(), self.vendor_bytes)

    def test_previous_candidate_update_adds_kscreenlocker_and_rollback_is_symmetric(self):
        first = self.candidate("5" * 40)
        second = self.candidate("6" * 40)
        self.run_tx("--root-install", self.caller, str(first))
        state = self.root / "var/lib/goodix-27c6-5125-managed/state"
        old_state = "\n".join(
            line for line in state.read_text(encoding="utf-8").splitlines()
            if not line.startswith((
                "CURRENT_KSCREENLOCKER_PAM_STATUS=", "PREVIOUS_KSCREENLOCKER_PAM_STATUS=",
                "KSCREENLOCKER_VENDOR_SHA256=", "KSCREENLOCKER_OVERRIDE_SHA256=",
            ))
        ) + "\n"
        state.write_text(old_state, encoding="utf-8")
        state_dir = state.parent
        self.kde_fingerprint_pam.write_bytes(self.kde_vendor_bytes)
        (state_dir / "kde-fingerprint.vendor").unlink()
        (state_dir / "kde-fingerprint.managed").unlink()

        status = self.run_tx("--status").stdout
        self.assertIn("KSCREENLOCKER_MANAGED_PAM_INTEGRATION=false", status)
        result = self.run_tx("--root-update", self.caller, str(second))
        self.assertIn("GOODIX_MANAGED_UPDATE=PASS", result.stdout)
        self.assertIn("pam_fprintd.so max-tries=3 timeout=45", self.kde_fingerprint_pam.read_text())

        result = self.run_tx("--root-rollback", self.caller)
        self.assertIn("KSCREENLOCKER_MANAGED_PAM_STATUS=ABSENT", result.stdout)
        self.assertEqual(self.kde_fingerprint_pam.read_bytes(), self.kde_vendor_bytes)
        result = self.run_tx("--root-rollback", self.caller)
        self.assertIn("KSCREENLOCKER_MANAGED_PAM_STATUS=ACTIVE", result.stdout)
        self.assertIn("pam_fprintd.so max-tries=3 timeout=45", self.kde_fingerprint_pam.read_text())

    def test_vendor_pam_drift_fails_closed(self):
        candidate = self.candidate("3" * 40)
        self.run_tx("--root-install", self.caller, str(candidate))
        self.vendor_pam.write_text(self.vendor_pam.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")
        result = self.run_tx("--status", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("plasmalogin_vendor_pam_drift", result.stderr)
        result = self.run_tx("--root-uninstall", self.caller)
        self.assertIn("MANAGED_PAM_REMOVED=true", result.stdout)
        self.assertFalse((self.root / "etc/pam.d/plasmalogin").exists())

    def test_preexisting_managed_pam_collision_fails_closed(self):
        managed = self.root / "etc/pam.d/plasmalogin"
        managed.parent.mkdir(parents=True, exist_ok=True)
        managed.write_text("preexisting\n", encoding="utf-8")
        candidate = self.candidate("4" * 40)
        result = self.run_tx("--root-install", self.caller, str(candidate), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("managed_path_collision", result.stderr)
        self.assertEqual(managed.read_text(encoding="utf-8"), "preexisting\n")

    def test_preexisting_kde_fingerprint_customization_fails_closed(self):
        self.kde_fingerprint_pam.write_text("auth required pam_permit.so\n", encoding="utf-8")
        candidate = self.candidate("7" * 40)
        result = self.run_tx("--root-install", self.caller, str(candidate), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("kde_fingerprint_vendor_auth_boundary_invalid", result.stderr)
        self.assertEqual(self.kde_fingerprint_pam.read_text(), "auth required pam_permit.so\n")

    def test_kde_fingerprint_package_and_override_drift_fail_closed(self):
        candidate = self.candidate("8" * 40)
        self.run_tx("--root-install", self.caller, str(candidate))
        self.env["GOODIX_MANAGED_TEST_KDE_VENDOR_SHA256"] = "0" * 64
        result = self.run_tx("--status", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("kde_fingerprint_vendor_package_drift", result.stderr)
        self.env["GOODIX_MANAGED_TEST_KDE_VENDOR_SHA256"] = sha(
            self.root / "var/lib/goodix-27c6-5125-managed/kde-fingerprint.vendor"
        )
        self.kde_fingerprint_pam.write_text("auth required pam_permit.so\n", encoding="utf-8")
        result = self.run_tx("--status", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("kde_fingerprint_managed_override_drift", result.stderr)

    def test_kde_fingerprint_metadata_drift_fails_closed(self):
        candidate = self.candidate("0" * 40)
        self.run_tx("--root-install", self.caller, str(candidate))
        self.kde_fingerprint_pam.chmod(0o600)
        result = self.run_tx("--status", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("kde_fingerprint_pam_mode_drift", result.stderr)

    def test_candidate_digest_tamper_fails_closed(self):
        candidate = self.candidate("c" * 40)
        (candidate / "libgusb.so.2").write_bytes(b"tampered")
        result = self.run_tx("--root-install", self.caller, str(candidate), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("candidate_digest_mismatch", result.stderr)

    def test_release_metadata_is_mandatory(self):
        candidate = self.candidate("9" * 40)
        (candidate / "SBOM.spdx.json").unlink()
        result = self.run_tx("--root-install", self.caller, str(candidate), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("candidate_SBOM.spdx.json_invalid", result.stderr)

    def test_sbom_installed_package_queries_the_package_not_a_shared_path(self):
        script = HERE / "generate-sbom.py"
        spec = importlib.util.spec_from_file_location("goodix_generate_sbom", script)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        query = "%{NAME}\t%{EVR}\t%{ARCH}\t%{LICENSE}"
        with mock.patch.object(
            module, "run", return_value="libgusb\t0.4.9-5.fc44\tx86_64\tLGPL-2.1-or-later"
        ) as rpm_run:
            package = module.installed_package("libgusb")
        rpm_run.assert_called_once_with("rpm", "-q", "--qf", query, "libgusb")
        self.assertEqual(package["name"], "libgusb")
        self.assertEqual(package["versionInfo"], "0.4.9-5.fc44")

    def test_partial_install_is_rolled_back(self):
        candidate = self.candidate("e" * 40)
        self.env["GOODIX_MANAGED_TEST_FAIL_AFTER_POLICY"] = "true"
        result = self.run_tx("--root-install", self.caller, str(candidate), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("injected_failure_after_policy", result.stderr)
        self.assertFalse((self.root / "var/lib/goodix-27c6-5125-managed").exists())
        self.assertFalse((self.root / "usr/lib64/goodix-27c6-5125").exists())
        self.assertFalse((self.root / "etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete").exists())

    def test_partial_install_after_kscreenlocker_pam_restores_vendor(self):
        candidate = self.candidate("4" * 40)
        self.env["GOODIX_MANAGED_TEST_FAIL_AFTER_KSCREENLOCKER_PAM"] = "true"
        result = self.run_tx("--root-install", self.caller, str(candidate), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("injected_failure_after_kscreenlocker_pam", result.stderr)
        self.assertEqual(self.kde_fingerprint_pam.read_bytes(), self.kde_vendor_bytes)
        self.assertFalse((self.root / "var/lib/goodix-27c6-5125-managed").exists())
        self.assertFalse((self.root / "etc/pam.d/plasmalogin").exists())

    def test_material_import_is_separate_and_preserved(self):
        source = self.temp / "material-source"
        source.mkdir(mode=0o700)
        for name in (
            "target-material-manifest.json", "transport-material.bin",
            "target-config-90.bin", "gfusb.dll", "fdt-cache.bin",
        ):
            (source / name).write_bytes(f"synthetic-{name}".encode())
        result = self.run_tx("--root-import-materials", self.caller, str(source))
        self.assertIn("MATERIAL_CONTENT_LOGGED=false", result.stdout)
        candidate = self.candidate("d" * 40)
        self.run_tx("--root-install", self.caller, str(candidate))
        self.run_tx("--root-uninstall", self.caller)
        self.assertTrue((self.root / "var/lib/goodix-5125-poc/transport-material.bin").is_file())

    def test_status_repairs_legacy_runtime_root_and_reports_material_readiness(self):
        candidate = self.candidate("f" * 40)
        self.run_tx("--root-install", self.caller, str(candidate))
        runtime_root = self.root / "usr/lib64/goodix-27c6-5125"
        runtime_root.chmod(0o700)

        material = self.root / "var/lib/goodix-5125-poc"
        material.mkdir(mode=0o700)
        for name in (
            "target-material-manifest.json", "transport-material.bin",
            "target-config-90.bin", "gfusb.dll", "fdt-cache.bin",
        ):
            path = material / name
            path.write_bytes(f"synthetic-{name}".encode())
            path.chmod(0o600)

        status = self.run_tx("--status").stdout
        self.assertEqual(runtime_root.stat().st_mode & 0o777, 0o755)
        self.assertIn("PROTECTED_MATERIAL_READY=true", status)
        self.assertIn("MANAGED_PAM_INTEGRATION=true", status)

    def test_static_safety_and_distribution_contract(self):
        combined = "\n".join(
            (HERE / name).read_text(encoding="utf-8")
            for name in ("prepare.sh", "manage.sh", "root-transaction.sh", "fprintd-wrapper")
        )
        self.assertIn("SOURCE_FIRST_MANAGED_INSTALL", combined)
        self.assertIn("RPM_OFFICIAL_DISTRIBUTION=false", combined)
        self.assertNotIn("PHASE_C_", combined)
        self.assertNotIn("origin/development", combined)
        self.assertNotIn("branch --show-current", combined)
        self.assertNotIn("fprintd-enroll", combined)
        self.assertNotIn("fprintd-verify", combined)
        self.assertNotIn("authselect enable-feature", combined)
        self.assertNotIn("PSK=000", combined)
        self.assertNotIn("random PSK", combined)
        self.assertNotIn("/usr/lib/pam.d/plasmalogin\" >", combined)
        self.assertNotIn("authselect opt-out", combined)
        self.assertNotIn("/etc/pam.d/fingerprint-auth\" >", combined)
        self.assertIn("MANAGED_ETC_OVERRIDE_FROM_VENDOR", combined)
        self.assertIn("MANAGED_PACKAGE_CONFIG_TRANSFORM", combined)
        manage = (HERE / "manage.sh").read_text(encoding="utf-8")
        self.assertIn('exec sudo -- "$here/root-transaction.sh" --status', manage)
        self.assertNotIn("ensure_runtime_root_mode", manage)

    def test_early_login_payload_and_rollback_ownership(self):
        candidate = self.candidate("a" * 40)
        self.run_tx("--root-install", self.caller, str(candidate))
        runtime = self.root / ("usr/lib64/goodix-27c6-5125/" + "a" * 40)
        for name in ("fprintd", "greeter", "pam_fprintd.so"):
            self.assertEqual((runtime / name).read_bytes(), (candidate / name).read_bytes())
        dropin = self.root / "etc/systemd/user/plasma-login.service.d/99-goodix-login-greeter.conf"
        self.assertEqual(dropin.read_bytes(), (HERE / dropin.name).read_bytes())
        self.assertIn("EARLY_LOGIN_STATUS=MANAGED", self.run_tx("--status").stdout)
        self.run_tx("--root-uninstall", self.caller)
        self.assertFalse(dropin.exists())
        self.assertFalse(dropin.parent.exists())
        self.assertEqual(self.vendor_pam.read_bytes(), self.vendor_bytes)
        self.assertEqual(self.kde_fingerprint_pam.read_bytes(), self.kde_vendor_bytes)

    def test_missing_paired_component_is_rejected(self):
        candidate = self.candidate("b" * 40)
        (candidate / "pam_fprintd.so").unlink()
        result = self.run_tx("--root-install", self.caller, str(candidate), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("candidate_pam_fprintd.so_invalid", result.stderr)
        self.assertFalse((self.root / "var/lib/goodix-27c6-5125-managed/state").exists())

    def test_greeter_override_collision_and_drift(self):
        candidate = self.candidate("c" * 40)
        directory = self.root / "etc/systemd/user/plasma-login.service.d"
        directory.mkdir(parents=True)
        override = directory / "custom.conf"
        override.write_text("custom")
        result = self.run_tx("--root-install", self.caller, str(candidate), check=False)
        self.assertIn("greeter_dropin_collision", result.stderr)
        self.assertEqual(override.read_text(), "custom")
        override.unlink()
        self.run_tx("--root-install", self.caller, str(candidate))
        owned = directory / "99-goodix-login-greeter.conf"
        original = owned.read_bytes()
        owned.write_text("drift")
        self.assertIn("greeter_dropin_drift", self.run_tx("--status", check=False).stderr)
        owned.write_bytes(original)
        self.run_tx("--root-uninstall", self.caller)
        self.assertTrue(directory.is_dir())  # Preexisting directory is not ours.

    def test_partial_login_payload_rolls_back_fresh_and_update(self):
        first = self.candidate("d" * 40)
        second = self.candidate("e" * 40)
        self.env["GOODIX_MANAGED_TEST_FAIL_AFTER_LOGIN_RUNTIME"] = "true"
        result = self.run_tx("--root-install", self.caller, str(first), check=False)
        self.assertIn("injected_failure_after_login_runtime", result.stderr)
        self.assertEqual(self.kde_fingerprint_pam.read_bytes(), self.kde_vendor_bytes)
        self.assertFalse((self.root / "etc/pam.d/plasmalogin").exists())
        self.env.pop("GOODIX_MANAGED_TEST_FAIL_AFTER_LOGIN_RUNTIME")
        self.run_tx("--root-install", self.caller, str(first))
        state = self.root / "var/lib/goodix-27c6-5125-managed/state"
        before = state.read_bytes()
        self.env["GOODIX_MANAGED_TEST_FAIL_AFTER_LOGIN_RUNTIME"] = "true"
        result = self.run_tx("--root-update", self.caller, str(second), check=False)
        self.assertIn("injected_failure_after_login_runtime", result.stderr)
        self.assertEqual(state.read_bytes(), before)
        self.assertIn("CURRENT_COMMIT=" + "d" * 40, self.run_tx("--status").stdout)
        self.assertFalse((self.root / ("usr/lib64/goodix-27c6-5125/" + "e" * 40)).exists())

    def test_manifest_must_cover_exact_candidate_file_set(self):
        candidate = self.candidate("1" * 40)
        sums = candidate / "SHA256SUMS"
        sums.write_text("".join(line for line in sums.read_text().splitlines(True)
                                if not line.endswith("  greeter\n")))
        result = self.run_tx("--root-install", self.caller, str(candidate), check=False)
        self.assertIn("candidate_checksum_file_set", result.stderr)

    def test_label_failure_and_rollback_service_failure_are_reversible(self):
        first = self.candidate("2" * 40)
        second = self.candidate("3" * 40)
        self.env["GOODIX_MANAGED_TEST_FAIL_ACTION"] = "chcon:--reference=/usr/libexec/fprintd"
        result = self.run_tx("--root-install", self.caller, str(first), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "etc/pam.d/plasmalogin").exists())
        self.assertEqual(self.kde_fingerprint_pam.read_bytes(), self.kde_vendor_bytes)
        self.env.pop("GOODIX_MANAGED_TEST_FAIL_ACTION")
        self.run_tx("--root-install", self.caller, str(first))
        self.run_tx("--root-update", self.caller, str(second))
        state = self.root / "var/lib/goodix-27c6-5125-managed/state"
        before = state.read_bytes()
        self.env["GOODIX_MANAGED_TEST_FAIL_ACTION"] = "systemctl:daemon-reload"
        result = self.run_tx("--root-rollback", self.caller, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(state.read_bytes(), before)
        self.env.pop("GOODIX_MANAGED_TEST_FAIL_ACTION")
        self.assertIn("CURRENT_COMMIT=" + "3" * 40, self.run_tx("--status").stdout)
        self.run_tx("--root-rollback", self.caller)
        self.assertIn("CURRENT_COMMIT=" + "2" * 40, self.run_tx("--status").stdout)

    def test_runtime_symlink_drift_is_rejected(self):
        candidate = self.candidate("4" * 40)
        self.run_tx("--root-install", self.caller, str(candidate))
        link = self.root / ("usr/lib64/goodix-27c6-5125/" + "4" * 40 + "/libfprint-2.so.2")
        link.unlink(); link.symlink_to("/unrelated/library")
        self.assertIn("runtime_symlink_drift", self.run_tx("--status", check=False).stderr)

    def test_policy_change_requires_fresh_install_instead_of_silent_omission(self):
        first = self.candidate("5" * 40)
        second = self.candidate("6" * 40)
        policy = second / "goodix_fprint_account_delete.fc"
        policy.write_text(policy.read_text() + "# different policy\n")
        sums = second / "SHA256SUMS"
        sums.write_text("".join(f"{sha(path)}  {path.name}\n" for path in sorted(second.iterdir())
                                if path.name != "SHA256SUMS"))
        self.run_tx("--root-install", self.caller, str(first))
        result = self.run_tx("--root-update", self.caller, str(second), check=False)
        self.assertIn("managed_host_assets_changed_requires_fresh_install", result.stderr)
        self.assertIn("CURRENT_COMMIT=" + "5" * 40, self.run_tx("--status").stdout)

    def test_shell_syntax(self):
        for name in ("prepare.sh", "manage.sh", "root-transaction.sh", "fprintd-wrapper", "50-goodix-fprint-account-delete"):
            subprocess.run(["bash", "-n", str(HERE / name)], check=True)
        subprocess.run(
            ["python3", "-m", "py_compile", str(HERE / "generate-sbom.py")],
            check=True,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
