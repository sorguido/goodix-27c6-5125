<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# 10. Login, sudo, PolicyKit, and the lock screen

The same lower fingerprint stack can appear through different front doors.

| Front door | What the user is trying to do |
|---|---|
| Plasma Login greeter | Start a desktop session |
| KScreenLocker | Return to an existing locked session |
| `sudo` | Run a command with administrator authority |
| PolicyKit | Approve a privileged desktop action |

PAM means these consumers can share authentication building blocks, but each
front end chooses its conversation and Fedora policy. A graphical screen may
show buttons; a terminal may print prompts in sequence.

## 🖥️ The project-managed Plasma Login choice

On the tested Fedora configuration, the repository installs a small selector
only for Plasma Login:

```text
nonempty password → use Fedora's current password stack immediately
empty submission   → explicitly choose fingerprint (at most 3 attempts)
```

Submitting the empty field enters `pam_fprintd`, which starts reader preparation
and authentication. With stock Fedora fprintd there is no earlier handoff of a
prepared login session. On the tested system, allow roughly one second after
the empty submission before touching the reader while it opens, establishes
the secure session, prepares finger detection, and becomes ready.

KScreenLocker, ordinary `sudo`, and PolicyKit continue through Fedora's own
paths wherever Fedora's current policy enables fingerprint authentication.
The installer does not rewrite global authselect or PAM policy for them, and
the console conversation can offer fingerprint before password without a
method-selection button.

Password fallback remains essential. Fingerprint login also does not unlock a
password-encrypted KWallet automatically; that wallet may still request its
password.

> 🔎 **Repository view:** the login prefix is readable in
> [`plasmalogin.pam`](../../deployment/plasma-login-opt-in/plasmalogin.pam).

## ✅ What to remember

Shared lower layers do not guarantee identical screens. The login selector is
project-managed; other consumers follow current Fedora policy.

[← Previous](09_verification_and_matching.md) · [Contents](README.md) · [Next →](11_what_is_stored_and_where.md)
