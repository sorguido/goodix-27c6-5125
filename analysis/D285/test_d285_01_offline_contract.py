#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "operator_kit/d285-01-persistent-sudo"
SCRIPT = KIT / "run-d285-01.sh"


def function_slice(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end, text.index(start))]


class D285OfflineContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text()
        cls.pam = (KIT / "goodix-d285-01-sudo.pam").read_text()
        cls.readme = (KIT / "README_IT.md").read_text()
        cls.pam_source = (ROOT / "reference/fprintd-fedora44-1.94.5/source/pam/pam_fprintd.c").read_text()

    def test_01_pam_has_one_try_password_fallback_and_deny(self):
        self.assertEqual(self.pam.count("pam_fprintd.so"), 1)
        self.assertIn("pam_fprintd.so max-tries=1 timeout=45", self.pam)
        self.assertIn("pam_unix.so nullok", self.pam)
        self.assertIn("pam_deny.so", self.pam)
        self.assertLess(self.pam.index("pam_fprintd.so"), self.pam.index("pam_unix.so"))

    def test_02_pam_fprintd_uses_one_global_dbus_service(self):
        self.assertIn('"net.reactivated.Fprint"', self.pam_source)
        self.assertNotIn("pam_service", self.pam_source)

    def test_03_authselect_without_feature_removes_global_fingerprint(self):
        rendered = subprocess.run(
            ["authselect", "test", "local", "-a", "with-silent-lastlog", "with-mdns4"],
            check=True, capture_output=True, text=True).stdout
        system = rendered.split("File /etc/pam.d/system-auth:", 1)[1].split(
            "File /etc/pam.d/password-auth:", 1)[0]
        fingerprint = rendered.split("File /etc/pam.d/fingerprint-auth:", 1)[1].split(
            "File /etc/pam.d/smartcard-auth:", 1)[0]
        self.assertNotIn("pam_fprintd.so", system)
        self.assertIn("pam_debug.so auth=authinfo_unavail", fingerprint)

    def test_04_install_uses_only_named_persistent_paths(self):
        for marker in (
                "/usr/local/lib64/goodix-27c6-5125",
                "/usr/local/sbin/goodix-d285-01-fprintd",
                "/etc/systemd/system/fprintd.service.d/90-goodix-d285-01.conf",
                "/etc/pam.d/goodix-d285-01-sudo",
                "/etc/sudoers.d/90-goodix-d285-01",
                "/etc/goodix-27c6-5125/d285-01.state"):
            self.assertIn(marker, self.script)
        self.assertNotIn('>"/etc/pam.d/sudo"', self.script)

    def test_05_system_libfprint_is_never_replaced(self):
        self.assertNotIn('install -m 0644 "$candidate/libfprint-2.so.2.0.0" /usr/lib64/',
                         self.script)
        self.assertNotIn("dnf install", self.script)
        self.assertNotIn("rpm -U", self.script)

    def test_06_wrapper_fails_closed_on_daemon_or_runtime_drift(self):
        wrapper = function_slice(self.script, "d285_write_wrapper ()", "d285_write_dropin ()")
        for marker in (
                "D285_01_DAEMON_PROVENANCE_DRIFT", "D285_01_RUNTIME_INTEGRITY_DRIFT",
                "sha256sum -c artifacts.sha256", "FP_DRIVERS_ALLOWLIST=goodix_27c6_5125",
                "libfprint-2.so.2.0.0"):
            self.assertIn(marker, wrapper)

    def test_07_dropin_execs_the_integrity_wrapper(self):
        dropin = function_slice(self.script, "d285_write_dropin ()", "d285_hash_host_config ()")
        self.assertIn("ExecStart=", dropin)
        self.assertIn("ExecStart=/usr/local/sbin/goodix-d285-01-fprintd", dropin)

    def test_08_all_material_host_gates_precede_install_start(self):
        install = function_slice(self.script, "d285_install ()", "d285_verify_installed_file ()")
        staging = install.index("d285_install_started=true")
        for marker in (
                "d285_verify_baseline", "d285_validate_host_contract",
                "AUTHSELECT_INITIAL_TOPOLOGY_DRIFT", "OPERATOR_NOT_SUDOER",
                "TARGET_CARDINALITY_NOT_ONE", "PREEXISTING_USER_FPRINT_STORAGE",
                "d285_validate_parent_paths", "d285_paths_absent",
                "FPRINTD_INITIAL_STATE_UNSAFE"):
            self.assertLess(install.index(marker), staging, marker)

    def test_09_global_pam_scope_is_reduced_before_daemon_start(self):
        install = function_slice(self.script, "d285_install ()", "d285_verify_installed_file ()")
        disable = install.index("authselect disable-feature with-fingerprint")
        start = install.index("systemctl start fprintd.service")
        self.assertLess(disable, start)
        self.assertLess(install.index("SYSTEM_AUTH_FINGERPRINT_STILL_ENABLED"), start)

    def test_10_install_budget_is_one_enroll_and_one_sudo_verify(self):
        install = function_slice(self.script, "d285_install ()", "d285_verify_installed_file ()")
        self.assertEqual(install.count("fprintd-enroll -f"), 1)
        self.assertEqual(install.count("env -u SUDO_ASKPASS sudo -v"), 1)
        self.assertNotIn("fprintd-verify", install)
        self.assertIn("$epoch_count -eq 2", install)
        self.assertLess(install.index("systemctl restart fprintd.service"),
                        install.index("env -u SUDO_ASKPASS sudo -v"))

    def test_11_success_requires_zero_retry_and_one_live_match(self):
        install = function_slice(self.script, "d285_install ()", "d285_verify_installed_file ()")
        for marker in (
                "$retry_count -eq 0", "$reopen_count -eq 0", "$reset_count -eq 0",
                "$clear_halt_count -eq 0", "$persistent_count -eq 0",
                "$match_count -eq 1", "event=outcome result=match"):
            self.assertIn(marker, install)

    def test_12_template_ownership_is_empty_then_exactly_one_and_hash_pinned(self):
        install = function_slice(self.script, "d285_install ()", "d285_verify_installed_file ()")
        self.assertLess(install.index("PREEXISTING_USER_FPRINT_STORAGE"),
                        install.index("fprintd-enroll -f"))
        self.assertIn('$(find "$d285_user_storage" -type f | wc -l) -eq 1', install)
        state = function_slice(self.script, "d285_write_state ()", "d285_install ()")
        self.assertIn("D285_01_TEMPLATE_RELATIVE_PATH", state)
        self.assertIn("D285_01_TEMPLATE_SHA256", state)

    def test_13_state_is_root_only_and_not_exported(self):
        state = function_slice(self.script, "d285_write_state ()", "d285_install ()")
        self.assertIn('chmod 0600 "$d285_state"', self.script)
        install = function_slice(self.script, "d285_install ()", "d285_verify_installed_file ()")
        export_block = install[install.index("d285_export=$(mktemp"):]
        self.assertNotIn("D285_01_TEMPLATE_SHA256", export_block)
        self.assertIn("TEMPLATE_INCLUDED_IN_EXPORT=false", export_block)
        for marker in (
                "D285_01_AUTHSELECT_CONF_BEFORE_SHA256",
                "D285_01_SYSTEM_AUTH_BEFORE_SHA256",
                "D285_01_PASSWORD_AUTH_BEFORE_SHA256",
                "D285_01_FINGERPRINT_AUTH_BEFORE_SHA256"):
            self.assertIn(marker, state)

    def test_14_uninstall_refuses_every_drift_before_template_delete(self):
        uninstall = function_slice(self.script, "d285_uninstall ()", "operator_install ()")
        delete = uninstall.index('fprintd-delete "$user"')
        for marker in (
                "AUTHSELECT_ACTIVE_DRIFT", "DAEMON_PROVENANCE_DRIFT", "PAM_FILE_DRIFT",
                "SUDOERS_FILE_DRIFT", "WRAPPER_FILE_DRIFT", "DROPIN_FILE_DRIFT",
                "RUNTIME_ARTIFACT_DRIFT", "TEMPLATE_OWNERSHIP_DRIFT_HUMAN_REVIEW_REQUIRED",
                "TARGET_CARDINALITY_NOT_ONE"):
            self.assertLess(uninstall.index(marker), delete, marker)

    def test_15_uninstall_deletes_owned_template_before_config(self):
        uninstall = function_slice(self.script, "d285_uninstall ()", "operator_install ()")
        self.assertLess(uninstall.index('fprintd-delete "$user"'),
                        uninstall.index("d285_remove_config_files"))
        self.assertLess(uninstall.index("d285_remove_config_files"),
                        uninstall.index("authselect enable-feature with-fingerprint"))

    def test_16_uninstall_restores_authselect_and_service(self):
        uninstall = function_slice(self.script, "d285_uninstall ()", "operator_install ()")
        self.assertIn('[[ $(authselect current --raw) == "$auth_before" ]]', uninstall)
        self.assertIn("d285_restore_service_state", uninstall)
        self.assertIn("authselect check", uninstall)
        self.assertIn("HOST_CONFIG_EXACT_RESTORE_FAILED", uninstall)

    def test_17_runtime_delete_is_bounded_and_refuses_symlinks(self):
        remove = function_slice(self.script, "d285_remove_runtime ()", "d285_restore_service_state ()")
        self.assertIn("/usr/local/lib64/goodix-27c6-5125/d285-01-*", remove)
        self.assertIn("! -L $runtime", remove)
        self.assertIn('find "$runtime" -xdev -depth -delete', remove)
        self.assertNotIn("rm -rf", remove)

    def test_18_install_failure_trap_rolls_back_all_owned_surfaces(self):
        rollback = function_slice(self.script, "d285_rollback_install ()", "d285_write_state ()")
        for marker in (
                "fprintd-delete", "d285_remove_config_files",
                "authselect enable-feature with-fingerprint", "d285_remove_runtime",
                "d285_restore_service_state", "D285_01_RECOVERY_REQUIRED"):
            self.assertIn(marker, rollback)
        self.assertLess(rollback.index("TEMPLATE_OWNERSHIP_OR_DELETE_REVIEW"),
                        rollback.index("d285_remove_config_files"))
        self.assertIn('== "$d285_template_sha"', rollback)
        self.assertIn("d285_export_failure", rollback)
        self.assertIn("d285_remove_result", rollback)

    def test_19_operator_entrypoints_are_direct_and_human_gated(self):
        install = function_slice(self.script, "operator_install ()", "operator_uninstall ()")
        uninstall = function_slice(self.script, "operator_uninstall ()", "cleanup_d285_offline_work ()")
        self.assertIn("INSTALLA D285", install)
        self.assertIn("--install", install)
        self.assertIn("TERMINAL_TRANSCRIPT", install)
        self.assertIn("RIMUOVI D285", uninstall)
        self.assertIn("--uninstall", uninstall)
        self.assertNotIn("grant", (install + uninstall).lower())

    def test_20_offline_preflight_cannot_call_live_modes(self):
        offline = function_slice(self.script, "offline_preflight ()",
                                 "if [[ ${D285_LIBRARY_ONLY")
        self.assertIn("REAL_USB_ENUMERATION_ATTEMPTED=false", offline)
        self.assertIn("REAL_SENSOR_ACCESSED=false", offline)
        self.assertIn("LIVE_EXECUTION_PERFORMED=false", offline)
        self.assertNotIn("d285_install ", offline)
        self.assertNotIn("d285_uninstall ", offline)

    def test_21_readme_has_risk_scope_stop_and_recovery(self):
        for marker in (
                "HUMAN REQUIRED", "Ctrl-C", "non ripetere", "fallback password",
                "ownership-pinned", "polkit", "with-fingerprint",
                "--operator-install", "--operator-uninstall"):
            self.assertIn(marker, self.readme)

    def test_22_runtime_staging_helper_preserves_manifest_and_symlinks(self):
        names = (
            "libfprint-2.so.2.0.0", "libgusb.so.2", "libopencv_core.so.413",
            "libopencv_features2d.so.413", "libopencv_flann.so.413",
            "libopencv_imgproc.so.413")
        with tempfile.TemporaryDirectory(prefix="goodix-d285-01-offline.", dir="/tmp") as td:
            work = Path(td)
            candidate = work / "candidate"
            runtime = work / f"d285-01-{'a' * 40}"
            candidate.mkdir()
            runtime.mkdir()
            for name in names:
                (candidate / name).write_bytes(name.encode())
            manifest = "".join(
                f"{subprocess.run(['sha256sum', str(candidate / name)], check=True, capture_output=True, text=True).stdout.split()[0]}  {name}\n"
                for name in names)
            (candidate / "d282-01-artifacts.sha256").write_text(manifest)
            command = (
                'D285_LIBRARY_ONLY=true; source "$0"; d285_runtime_test_mode=true; '
                'd285_stage_persistent_runtime "$1" "$2"')
            subprocess.run(["bash", "-c", command, str(SCRIPT), str(candidate), str(runtime)],
                           check=True)
            self.assertEqual((runtime / "libfprint-2.so.2").readlink(),
                             Path("libfprint-2.so.2.0.0"))
            self.assertTrue((runtime / "artifacts.sha256").is_file())

    def test_23_runtime_staging_rejects_unowned_path(self):
        with tempfile.TemporaryDirectory(prefix="goodix-d285-unowned.", dir="/tmp") as td:
            work = Path(td)
            candidate, runtime = work / "candidate", work / "runtime"
            candidate.mkdir()
            runtime.mkdir()
            command = (
                'D285_LIBRARY_ONLY=true; source "$0"; d285_runtime_test_mode=true; '
                'd285_stage_persistent_runtime "$1" "$2"')
            result = subprocess.run(["bash", "-c", command, str(SCRIPT),
                                     str(candidate), str(runtime)])
            self.assertNotEqual(result.returncode, 0)

    def test_24_generated_wrapper_and_sudoers_are_exact(self):
        baseline = "a" * 40
        daemon_sha = "b" * 64
        with tempfile.TemporaryDirectory(prefix="goodix-d285-write-") as td:
            work = Path(td)
            wrapper, sudoers = work / "wrapper", work / "sudoers"
            command = (
                'D285_LIBRARY_ONLY=true; source "$0"; '
                'd285_write_wrapper "$1" "$2" "$3"; '
                'd285_write_sudoers goodix_test "$4"')
            runtime = f"/usr/local/lib64/goodix-27c6-5125/d285-01-{baseline}"
            subprocess.run(["bash", "-c", command, str(SCRIPT), runtime,
                            daemon_sha, str(wrapper), str(sudoers)], check=True)
            self.assertIn(daemon_sha, wrapper.read_text())
            self.assertEqual(sudoers.read_text(),
                             "Defaults:goodix_test pam_service=goodix-d285-01-sudo\n")
            subprocess.run(["visudo", "-cf", str(sudoers)], check=True,
                           capture_output=True)

    def test_25_generated_systemd_dropin_is_parser_valid(self):
        with tempfile.TemporaryDirectory(prefix="goodix-d285-unit-") as td:
            work = Path(td)
            unit = work / "etc/systemd/system/fprintd.service"
            dropin_dir = work / "etc/systemd/system/fprintd.service.d"
            wrapper = work / "usr/local/sbin/goodix-d285-01-fprintd"
            unit.parent.mkdir(parents=True)
            dropin_dir.mkdir()
            wrapper.parent.mkdir(parents=True)
            unit.write_text(Path("/usr/lib/systemd/system/fprintd.service").read_text())
            wrapper.write_text("#!/bin/sh\nexit 0\n")
            wrapper.chmod(0o755)
            (unit.parent / "sysinit.target").write_text("[Unit]\nDescription=Test sysinit\n")
            (unit.parent / "dbus.socket").write_text(
                "[Unit]\nDescription=Test bus\n[Socket]\nListenStream=/run/test-dbus\n")
            dropin = dropin_dir / "90-goodix-d285-01.conf"
            command = ('D285_LIBRARY_ONLY=true; source "$0"; d285_write_dropin "$1"')
            subprocess.run(["bash", "-c", command, str(SCRIPT), str(dropin)], check=True)
            verified = subprocess.run(
                ["systemd-analyze", "verify", f"--root={work}", "fprintd.service"],
                capture_output=True, text=True)
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)

    def test_26_shell_syntax_and_previous_live_are_closed(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
        d284 = (ROOT / "operator_kit/d284-01-transient-sudo-pilot/run-d284-01.sh").read_text()
        self.assertIn("d284_live_closed=true", d284)

    def test_27_fedora_usr_local_sbin_symlink_is_narrowly_accepted(self):
        helper = function_slice(
            self.script, "d285_validate_local_sbin_path ()",
            "d285_validate_parent_paths ()")
        for marker in (
                '[[ $link_target == bin ]]', 'readlink -f -- "$path"',
                '[[ $resolved == "$expected" ]]',
                '[[ -d $expected && ! -L $expected ]]'):
            self.assertIn(marker, helper)
        parent_gate = function_slice(
            self.script, "d285_validate_parent_paths ()",
            "d285_write_sudoers ()")
        self.assertIn(
            "d285_validate_local_sbin_path /usr/local/sbin /usr/local/bin",
            parent_gate)

        with tempfile.TemporaryDirectory(prefix="goodix-d285-sbin-", dir="/tmp") as td:
            root = Path(td)
            (root / "bin").mkdir()
            (root / "sbin").symlink_to("bin")
            command = (
                'D285_LIBRARY_ONLY=true; source "$0"; '
                'd285_validate_local_sbin_path "$1" "$2"')
            accepted = subprocess.run(
                ["bash", "-c", command, str(SCRIPT),
                 str(root / "sbin"), str(root / "bin")])
            self.assertEqual(accepted.returncode, 0)

            (root / "sbin").unlink()
            (root / "other").mkdir()
            (root / "sbin").symlink_to("other")
            unexpected = subprocess.run(
                ["bash", "-c", command, str(SCRIPT),
                 str(root / "sbin"), str(root / "bin")],
                capture_output=True, text=True)
            self.assertNotEqual(unexpected.returncode, 0)
            self.assertIn("D285_01_REFUSAL_REASON=PARENT_PATH_UNSAFE",
                          unexpected.stderr)

            (root / "sbin").unlink()
            (root / "bin").rmdir()
            (root / "real-bin").mkdir()
            (root / "bin").symlink_to("real-bin")
            (root / "sbin").symlink_to("bin")
            ambiguous = subprocess.run(
                ["bash", "-c", command, str(SCRIPT),
                 str(root / "sbin"), str(root / "bin")],
                capture_output=True, text=True)
            self.assertNotEqual(ambiguous.returncode, 0)
            self.assertIn("D285_01_REFUSAL_REASON=PARENT_PATH_UNSAFE",
                          ambiguous.stderr)


if __name__ == "__main__":
    unittest.main()
