#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
TRANSACTION = HERE / "root-transaction.sh"
FILES = (
    "MANIFEST", "SHA256SUMS", "LICENSE", "GPL-2.0-or-later.txt",
    "LGPL-2.1-or-later.txt", "libfprint-2.so.2.0.0",
    "libgusb.so.2", "libopencv_core.so.413", "libopencv_features2d.so.413",
    "libopencv_flann.so.413", "libopencv_imgproc.so.413", "fprintd-wrapper",
    "50-goodix-fprint-account-delete", "goodix_fprint_account_delete.te",
    "goodix_fprint_account_delete.fc", "99-goodix-27c6-5125-managed.conf",
)


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ManagedInstallContract(unittest.TestCase):
    def setUp(self):
        self.temp = pathlib.Path(tempfile.mkdtemp(prefix="goodix-managed-test.", dir="/tmp"))
        self.root = self.temp / "root"
        self.root.mkdir()
        self.env = os.environ | {"GOODIX_MANAGED_TEST_ROOT": str(self.root)}
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
            "PHASE_C_DISTRIBUTION_MODEL=SOURCE_FIRST_MANAGED_INSTALL\n"
            "RPM_OFFICIAL_DISTRIBUTION=false\n"
            f"SOURCE_COMMIT={commit}\n"
            "TARGET_OS=Fedora-44-KDE-x86_64\n"
            "PROTECTED_MATERIAL_INCLUDED=false\n"
            "PAM_FILES_INCLUDED=false\n",
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
        self.assertIn("PHASE_C_INSTALL=PASS", result.stdout)
        result = self.run_tx("--root-install", self.caller, str(first))
        self.assertIn("PASS_ALREADY_CURRENT", result.stdout)
        result = self.run_tx("--root-update", self.caller, str(second))
        self.assertIn("PHASE_C_UPDATE=PASS", result.stdout)
        status = self.run_tx("--status").stdout
        self.assertIn(f"CURRENT_COMMIT={b}", status)
        self.assertIn(f"PREVIOUS_COMMIT={a}", status)
        result = self.run_tx("--root-rollback", self.caller)
        self.assertIn(f"CURRENT_COMMIT={a}", result.stdout)
        result = self.run_tx("--root-uninstall", self.caller)
        self.assertIn("FEDORA_FPRINTD_BASELINE=RESTORED", result.stdout)
        self.assertFalse((self.root / "var/lib/goodix-27c6-5125-managed/state").exists())

    def test_candidate_digest_tamper_fails_closed(self):
        candidate = self.candidate("c" * 40)
        (candidate / "libgusb.so.2").write_bytes(b"tampered")
        result = self.run_tx("--root-install", self.caller, str(candidate), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("candidate_digest_mismatch", result.stderr)

    def test_partial_install_is_rolled_back(self):
        candidate = self.candidate("e" * 40)
        self.env["GOODIX_MANAGED_TEST_FAIL_AFTER_POLICY"] = "true"
        result = self.run_tx("--root-install", self.caller, str(candidate), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("injected_failure_after_policy", result.stderr)
        self.assertFalse((self.root / "var/lib/goodix-27c6-5125-managed").exists())
        self.assertFalse((self.root / "usr/lib64/goodix-27c6-5125").exists())
        self.assertFalse((self.root / "etc/shadow-maint/userdel-pre.d/50-goodix-fprint-account-delete").exists())

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

    def test_static_safety_and_distribution_contract(self):
        combined = "\n".join(
            (HERE / name).read_text(encoding="utf-8")
            for name in ("prepare.sh", "manage.sh", "root-transaction.sh", "fprintd-wrapper")
        )
        self.assertIn("SOURCE_FIRST_MANAGED_INSTALL", combined)
        self.assertIn("RPM_OFFICIAL_DISTRIBUTION=false", combined)
        self.assertNotIn("fprintd-enroll", combined)
        self.assertNotIn("fprintd-verify", combined)
        self.assertNotIn("authselect enable-feature", combined)
        self.assertNotIn("PSK=000", combined)
        self.assertNotIn("random PSK", combined)

    def test_shell_syntax(self):
        for name in ("prepare.sh", "manage.sh", "root-transaction.sh", "fprintd-wrapper", "50-goodix-fprint-account-delete"):
            subprocess.run(["bash", "-n", str(HERE / name)], check=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
