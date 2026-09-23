#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fixed sudo host rules owned by the combined Polkit/managed transaction."""
import json
import re
import subprocess

PAM = "/etc/pam.d/sudo"
LOGIN = "/etc/pam.d/sudo-i"
LEAF = "/etc/pam.d/goodix-sudo-fingerprint"
VENDOR = (b"#%PAM-1.0\nauth       include      system-auth\n"
          b"account    include      system-auth\npassword   include      system-auth\n"
          b"session    optional     pam_keyinit.so revoke\n"
          b"session    required     pam_limits.so\nsession    include      system-auth\n")
LOGIN_VENDOR = (b"#%PAM-1.0\nauth       include      sudo\naccount    include      sudo\n"
                b"password   include      sudo\nsession    optional     pam_keyinit.so force revoke\n"
                b"session    include      sudo\n")


def selectors(policy):
    """Reject scoped selectors too; checking only a global default misses D285."""
    if isinstance(policy, dict):
        for key, value in policy.items():
            if key in {"pam_service", "pam_login_service", "pam_askpass_service"}:
                raise RuntimeError("custom sudo PAM selector: original owner rollback required")
            selectors(value)
    elif isinstance(policy, list):
        for value in policy:
            selectors(value)


def local_nss(text):
    # sudo_parseln accepts continuations. Reject that unqualified syntax rather
    # than mistaking a split sudoers keyword for the default files-only case.
    if "\\" in text: return False
    rows = [match.group(1).split() for line in text.splitlines()
            if (match := re.match(r"^\s*sudoers:(.*)$", line.split("#", 1)[0], re.I))]
    return not rows or [[word.lower() for word in row] for row in rows] == [["files"]]


def baseline(d):
    for name in (PAM, LOGIN):
        for suffix in (".rpmnew", ".rpmsave"):
            path = d.p(name + suffix)
            d.require(not path.exists() and not path.is_symlink(), "resolve sudo PAM rpmnew/rpmsave first")
    d.require(d.regular(LOGIN) == LOGIN_VENDOR, "custom/drifted sudo-i PAM")
    if d.TEST:
        policy = json.loads(d.p("/etc/sudoers.offline.json").read_bytes())
        selectors(policy)
        return d.digest(json.dumps(policy, sort_keys=True).encode())
    version = subprocess.check_output(["rpm", "-q", "--qf", "%{VERSION}-%{RELEASE}", "sudo"], text=True)
    d.require(version == "1.9.17-8.p2.fc44", "unsupported sudo version")
    for name, mode, digest in (
        ("/etc/sudo.conf", 0o640, "9af0d568d19a8c778d17202647b5eb75e36b074f42b2df65aa1ea23e567e3be3"),
        ("/usr/bin/sudo", 0o4111, "52d280f4d4411a54afcad91468f765790056c8b388e1074f2324dad3e31846de"),
        ("/usr/bin/cvtsudoers", 0o755, "ea6d47e365fd7d264f25bc04e7d96f6390807a6ebbecc40ab967b59902eac1c7"),
        ("/usr/libexec/sudo/sudoers.so", 0o644, "e5fc42d97a200a0281fdf0dd8718692eebddd62260ac897160112d6dc7b8e7b1"),
    ):
        d.require(d.digest(d.regular(name, mode)) == digest, f"sudo component drift: {name}")
    # No NSS network policy can silently replace these audited local defaults.
    d.require(local_nss(d.p("/etc/nsswitch.conf").read_text()),
              "only local sudoers policy supported")
    # cvtsudoers parses includes and scoped Defaults without authenticating.
    raw = subprocess.check_output(["/usr/bin/cvtsudoers", "-c", "/dev/null", "-f", "json", "/etc/sudoers"])
    policy = json.loads(raw)
    selectors(policy)
    return d.digest(json.dumps(policy, sort_keys=True).encode())


def payload():
    prefix = (b"auth required pam_env.so\nauth required pam_faildelay.so delay=2000000\n"
              b"auth [success=done ignore=ignore open_err=ignore symbol_err=ignore module_unknown=ignore default=die] "
              b"/usr/lib64/goodix-27c6-5125/current/pam_goodix_sudo.so\n")
    return {
        PAM: VENDOR.replace(b"auth       include", prefix + b"auth       include", 1),
        LEAF: b"#%PAM-1.0\nauth required /usr/lib64/security/pam_fprintd.so max-tries=1 timeout=8\n",
    }
