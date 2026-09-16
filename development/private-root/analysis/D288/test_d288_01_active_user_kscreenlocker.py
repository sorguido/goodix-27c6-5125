#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "operator_kit/live_probe/experiments/d288-active-user-kscreenlocker"


class D288ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = (EXP / "experiment.conf").read_text()
        cls.payload = (EXP / "payload.sh").read_text()
        cls.audit = (EXP / "audit.sh").read_text()
        cls.shim = (EXP / "pam-start-redirect.c").read_text()
        cls.readme = (EXP / "README_IT.md").read_text()

    def test_config_is_small_bounded_and_reuses_common_harness(self):
        for marker in (
            "MAX_ACTIONS=3",
            "MAX_CONTACTS=3",
            "MAX_RETRIES=0",
            "LIVE_CAPABLE=true",
            "OFFLINE_TEST_CAPABLE=true",
            "REQUIRES_ACTIVE_USER_SESSION=true",
            "TIMEOUT_SECONDS=240",
        ):
            self.assertIn(marker, self.config)
        self.assertNotIn("retry=", self.config.lower())

    def test_preload_redirect_is_exact_and_passes_other_services_through(self):
        self.assertIn('strcmp (service, "kde-fingerprint") == 0', self.shim)
        self.assertIn('dlsym (RTLD_NEXT, "pam_start_confdir")', self.shim)
        self.assertIn('dlsym (RTLD_NEXT, "pam_start")', self.shim)
        self.assertEqual(self.shim.count("return redirected"), 1)
        self.assertEqual(self.shim.count("return original"), 1)

    def test_preload_exports_versioned_pam_start(self):
        with tempfile.TemporaryDirectory(prefix="d288-shim-") as directory:
            output = Path(directory) / "redirect.so"
            result = subprocess.run(
                [
                    "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared",
                    "-Wl,-z,defs,-z,relro,-z,now,--build-id=none",
                    f"-Wl,--version-script={EXP / 'pam-start-redirect.map'}",
                    str(EXP / "pam-start-redirect.c"), "-o", str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            symbols = subprocess.run(
                ["nm", "-D", str(output)], text=True, stdout=subprocess.PIPE, check=True
            ).stdout
            self.assertIn("pam_start@@LIBPAM_1.0", symbols)

    def test_payload_enforces_three_explicit_slots_and_stop_on_match(self):
        self.assertIn("for attempt in 1 2 3", self.payload)
        self.assertIn("attempts < max_actions && contacts < max_contacts", self.payload)
        self.assertIn('confirmation == "TENTATIVO $attempt"', self.payload)
        self.assertIn("[[ $matched -eq 0 ]] || break", self.payload)
        self.assertIn("MAX_RETRIES_ENFORCED=$max_retries", self.payload)
        self.assertIn("RETRY_COUNT=0", self.payload)

    def test_payload_requires_match_unlocked_and_zero_exit_together(self):
        self.assertRegex(
            self.payload,
            re.compile(r"match_count -eq 1.*unlocked_count -eq 1.*greeter_rc -eq 0", re.S),
        )
        self.assertIn("D288_PAM_REDIRECT_SERVICE=kde-fingerprint", self.payload)
        self.assertIn("GOODIX_D282_EPOCH_AUDIT", self.payload)

    def test_greeter_is_group_owned_and_active_user_cgroup_checked(self):
        self.assertIn('ps -o pgid= -p "$greeter_pid"', self.payload)
        self.assertIn('greeter_pgid == "$greeter_pid"', self.payload)
        self.assertIn('/user.slice/user-0.slice/*|/system.slice/*', self.payload)
        self.assertIn('kill -TERM -- "-$pid"', self.payload)
        self.assertIn('kill -KILL -- "-$pid"', self.payload)

    def test_no_host_pam_write_mount_or_privileged_greeter_launch(self):
        combined = self.payload + self.audit
        self.assertNotIn(">/etc/pam.d", combined)
        self.assertNotIn('>"/etc/pam.d', combined)
        self.assertNotIn("mount --bind", combined)
        self.assertNotIn("runuser", combined)
        self.assertNotIn("pkexec /usr/libexec/kscreenlocker_greet", combined)
        self.assertIn("setsid env GOODIX_D288_PAM_CONFDIR", self.payload)

    def test_privilege_is_limited_to_separate_root_audits(self):
        self.assertEqual(self.audit.count("pkexec"), 1)
        self.assertIn("--root-audit", self.audit)
        self.assertIn("D288_EXISTING_GREETER_COUNT=0", self.audit)
        self.assertIn("D288_TARGET_SYSFS_CARDINALITY=1", self.audit)

    def test_documented_ux_and_human_gate_are_explicit(self):
        for text in (
            "fullscreen",
            "Non digitare",
            "Ctrl-C",
            "tre action/contatti totali",
            "Nessun file sotto `/etc/pam.d` viene scritto",
            "non autorizza un rerun",
        ):
            self.assertIn(text, self.readme)


if __name__ == "__main__":
    unittest.main()
