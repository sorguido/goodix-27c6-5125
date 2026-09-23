#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Production controls, real libpam, exclusively synthetic modules."""
import pathlib
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager


@contextmanager
def gate_fixtures(path):
    # These text-only files are read by the gate, never loaded by libpam.
    values = {
        "plasmalogin": "auth [success=done ignore=ignore default=bad] pam_selinux_permit.so\n"
                       "auth substack password-auth\n-auth optional pam_gnome_keyring.so\n"
                       "-auth optional pam_kwallet5.so\n-auth optional pam_kwallet.so\n"
                       "-auth optional pam_oo7.so\nauth include postlogin\n",
        "password-auth": "auth required pam_env.so\nauth required pam_faildelay.so delay=2000000\n"
                         "auth sufficient pam_unix.so nullok\nauth required pam_deny.so\n",
        "postlogin": "# Synthetic configuration: no auth rows\n",
    }
    path.mkdir()
    try:
        for name, value in values.items():
            (path / name).write_text(value)
        yield
    finally:
        for name in values:
            (path / name).unlink(missing_ok=True)
        path.rmdir()


def main():
    if len(sys.argv) != 6:
        raise SystemExit("usage: test_dispatch.py DRIVER MOCK_MODULE PRODUCTION_PAM REAL_GATE_TEST_SO FIXTURES_DIR")
    driver, module, config, real_gate = (pathlib.Path(p).resolve(strict=True) for p in sys.argv[1:5])
    fixtures = pathlib.Path(sys.argv[5]).resolve()
    original = config.read_text()
    vendor_path = "/usr/lib/pam.d/plasmalogin"
    assert original.count(vendor_path) == 4, "expected four current vendor includes"
    replacements = {
        "/usr/local/lib64/goodix-plasma-login/pam_goodix_login_gate.so": "gate",
        "pam_selinux_permit.so": "selinux",
        "pam_fprintd.so": "fp",
        "pam_permit.so": "reset",
    }
    for source in replacements:
        assert original.count(source) == 1, f"unexpected production module: {source}"
    passed = 0
    with gate_fixtures(fixtures), tempfile.TemporaryDirectory(prefix="goodix-pam-synthetic-") as temporary:
        root = pathlib.Path(temporary)
        service, vendor, log = (root / name for name in
                                ("goodix-opt-in-synthetic", "vendor", "calls"))

        def run(name, gate="ignore", fp="success", selinux="ignore",
                password="success", account="success", opening="success",
                missing=None, reset=True, real=None):
            nonlocal passed
            results = {"gate": gate, "fp": fp, "selinux": selinux, "reset": "success"}
            text = original.replace(vendor_path, str(vendor))
            if not reset:
                text = "\n".join(line for line in text.splitlines()
                                 if "pam_permit.so" not in line) + "\n"
            for source, role in replacements.items():
                if real and role == "gate":
                    text = text.replace(source, str(real_gate))
                    continue
                target = root / "missing.so" if missing == role else module
                credential = "ignore" if role in ("gate", "selinux") else "success"
                text = text.replace(source, f"{target} role={role} auth={results[role]} cred={credential}")
            allowed = {str(module), str(real_gate), str(root / "missing.so"), str(vendor)}
            for line in text.splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                parsed = re.fullmatch(
                    r"\s*-?(?:auth|account|password|session)\s+"
                    r"(?:\[[^\]]+\]|\S+)\s+(\S+)(?:\s+.*)?", line)
                assert parsed and parsed[1] in allowed, f"unsafe fixture line: {line}"
            # No distro auth module, D-Bus path, sensor or real credential is used.
            service.write_text(text)
            expect = "expect_token=synthetic-password" if real == "nonempty" else ""
            vendor.write_text(
                f"auth [success=done ignore=ignore default=bad] {module} role=vendor_selinux auth={selinux} cred=ignore\n"
                f"auth requisite {module} role=vendor_auth auth={password} {expect}\n"
                f"auth optional {module} role=vendor_tail\n"
                f"account required {module} role=vendor_account account={account}\n"
                f"password required {module} role=vendor_password\n"
                f"session required {module} role=vendor_session open={opening}\n")
            log.write_text("")
            command = [str(driver), str(root), str(log)] + ([real] if real else [])
            process = subprocess.run(command,
                                     check=True, text=True, capture_output=True, timeout=10)
            status = tuple(map(int, process.stdout.split()))
            assert len(status) == 5, (name, process.stdout, process.stderr)
            calls = log.read_text().splitlines()
            passed += 1
            return status, calls

        def password_path(name, **kwargs):
            status, calls = run(name, **kwargs)
            assert status == (0, 0, 0, 0, 0), (name, status, calls)
            assert "fp.auth" not in calls and "fp.cred" not in calls, (name, calls)
            assert "vendor_auth.auth" in calls and "vendor_auth.cred" in calls, (name, calls)
            assert calls.index("reset.cred") < calls.index("vendor_auth.cred"), (name, calls)

        password_path("nonempty")
        password_path("gate error", gate="auth_err")
        password_path("gate missing", missing="gate")
        status, calls = run("reset module missing", missing="reset")
        assert status == (0, 0, 0, 0, 0) and "vendor_auth.cred" in calls, (status, calls)
        assert "fp.auth" not in calls and "reset.cred" not in calls
        status, calls = run("wrong password", password="auth_err")
        assert status[0] != 0 and "fp.auth" not in calls and "vendor_auth.auth" in calls
        status, calls = run("empty match", gate="success")
        assert status == (0, 0, 0, 0, 0), (status, calls)
        assert calls == ["gate.auth", "selinux.auth", "fp.auth", "vendor_account.account",
                         "gate.cred", "selinux.cred", "fp.cred",
                         "vendor_session.open", "vendor_session.close"], calls
        for failure in ("auth_err", "module_unknown"):
            status, calls = run("fingerprint failure", gate="success", fp=failure)
            assert status == (0, 0, 0, 0, 0) and "vendor_auth.auth" in calls, (status, calls)
            assert calls.index("fp.cred") < calls.index("reset.cred") < calls.index("vendor_auth.cred")
        status, calls = run("fingerprint missing", gate="success", missing="fp")
        assert status == (0, 0, 0, 0, 0) and "vendor_auth.cred" in calls, (status, calls)
        assert "fp.auth" not in calls and "fp.cred" not in calls
        status, calls = run("SELinux rejection", gate="success", selinux="auth_err")
        assert status[0] != 0 and "fp.auth" not in calls and "vendor_selinux.auth" in calls
        status, calls = run("SELinux permit", gate="success", selinux="success")
        assert status == (0, 0, 0, 0, 0), (status, calls)
        assert "fp.auth" not in calls and "fp.cred" not in calls, calls
        assert "vendor_selinux.auth" in calls and "vendor_auth.auth" not in calls, calls
        assert "vendor_auth.cred" in calls, calls
        status, calls = run("vendor account changed", account="auth_err")
        assert status[0] == 0 and status[1] != 0 and status[2:] == (-1, -1, -1)
        status, calls = run("vendor session changed", opening="auth_err")
        assert status[:3] == (0, 0, 0) and status[3] != 0 and status[4] == -1
        status, calls = run("negative control: absent reset", missing="gate", reset=False)
        assert status[:2] == (0, 0) and status[2] != 0, (status, calls)
        assert "vendor_auth.cred" in calls, calls
        status, calls = run("real gate preserves nonempty token", real="nonempty")
        assert status == (0, 0, 0, 0, 0), (status, calls)
        assert "fp.auth" not in calls and "vendor_auth.auth" in calls, calls
        status, calls = run("real gate accepts explicit empty selection", real="empty")
        assert status == (0, 0, 0, 0, 0), (status, calls)
        assert "fp.auth" in calls and "fp.cred" in calls and "vendor_auth.auth" not in calls, calls
    print(f"PLASMA_LOGIN_SYNTHETIC_DISPATCH=PASS cases={passed}")


if __name__ == "__main__":
    main()
