<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Combined sudo and Polkit: operator handoff

> **HISTORICAL_ONLY / REJECTED_ARCHITECTURE — 22 September 2026.**
> The managed candidate, private fprintd/PAM pair, Plasma daemon/greeter,
> KScreenLocker overrides and custom sudo/PolicyKit integrations described
> below are preserved as historical evidence. Their installation, build and
> live instructions are not the active release workflow. Past PASS results
> do not qualify them for the new release.
>
> Follow the [distro-decoupled roadmap](../../ROADMAP_DISTRO_DECOUPLED_RELEASE.md). R0 restored the physical
> Fedora host to its stock baseline; new build/runtime validation is VM-only.
> The next runtime must use the Goodix library with Fedora stock fprintd and
> stock authentication consumers. No replacement candidate is ready yet.

Status: offline candidate, **live validation pending**. The development PC's
D285 sudo fingerprint PASS remains valid; the local Polkit patch is **not
installed**. Do not install that standalone patch as part of this handoff.
The AI has not changed host PAM, sudoers, authselect, services or sensor state.

## Baseline and installation

Use a clean Fedora 44 KDE x86_64 baseline, local accounts, the supported package
versions in `production/{sudo,polkit}/README.md`, the audited password-only
system-auth and the prerequisites in `docs/INSTALLATION.md`. Protected material
and enrolled prints must already be provisioned through the existing approved
process; this test neither extracts nor changes them. No firmware/factory write
is involved. A local user with an enrolled print and one without enrollment
cover the two account cases. Keep a working password and the prepared checkout.

**STOP before install on the current D285 development PC.** The clean manager
refuses historical overlays, custom sudo selectors and custom PAM. The separate
migration plan below must be resolved first. Do not remove collision checks.

From the repository root on branch `development`, using the delivered committed
checkout (its full SHA is recorded by prepare in candidate/MANIFEST):

```bash
git rev-parse HEAD
deployment/managed-install/manage.sh prepare /tmp/goodix-auth-candidate
deployment/managed-install/manage.sh install /tmp/goodix-auth-candidate/candidate
deployment/managed-install/manage.sh status
```

Prepare is unprivileged. Install/status invoke sudo through the existing
manager and are **operator-only**. Close all authentication dialogs and other
sudo processes before lifecycle changes. Install must report PASS; status must
show the candidate commit and both `POLKIT_INTEGRATION` and `SUDO_INTEGRATION`.
An already occupied output directory requires a new empty directory name.

The combined transaction changes `/etc/pam.d/sudo`, creates the two fingerprint
leaf services, Polkit PAM override, Polkit tmpfiles/helper drop-in and its private
state/counter directory. The outer manager also installs the existing complete
driver/daemon/login/KScreenLocker/account-delete integration listed in the main
installation guide. It does not modify sudoers, sudo-i, system-auth or authselect.
New sudo/polkit bridges and the daemon are part of the immutable runtime/current
switch. No KDE/Polkit executable is patched or restarted.

## Native workflow, one bounded series at a time

1. Run `sudo -k`, then `sudo -v`. At the native prompt, first validate password
   directly. For a separate fingerprint series run `sudo -k`, then `sudo -v`
   and submit an empty response. Touch once. After NO MATCH the next prompt
   allows password or another explicit empty response. Stop on the first MATCH;
   at most three physical attempts in the series, never a fourth. Each selected
   fingerprint interval lasts at most 8 seconds; wait for the prompt before
   typing a password. Ctrl+C cancels. Error, timeout, no enrollment or contention
   must return to password, without automatically starting another attempt.
2. Validate `sudo -i` in the same way in a separate series, then `exit` the shell.
   The run-as account is still selected by ordinary sudo policy. A user without
   enrollment must succeed by password and never be trapped behind 30–45 seconds
   of fingerprint waiting. Do not enroll/delete any print for this check.
3. Use Discover's normal authorization dialog. Password works immediately.
   Empty submission selects one fingerprint attempt; password submission while
   waiting interrupts it. Up to three choices across dialog restarts, stopping
   on MATCH; after exhaustion a valid password resets that user's Polkit guard.
   Cancellation must close the request. Do not reopen to evade the limit.
4. Exercise contention in two separate cases: leave one explicitly selected
   Discover fingerprint attempt waiting, then start sudo; reverse the order in
   the second case. The blocked consumer must offer usable password fallback,
   without stealing/restarting the other's acquisition. Cancel the owner, then
   check the next normal password workflow. Each contention case tests Claim/BUSY only: do not touch the sensor.
   It permits one owner choice and at most one blocked-consumer choice, zero
   physical contacts and zero automatic repeat; an unexpected MATCH ends the case. Do not create concurrent authentication by scripts.
5. Separately validate the usual screen unlock and login workflows, retaining
   their existing maximum-three-attempt/stop-on-MATCH boundaries. Cross-consumer
   daemon logic for these paths is covered offline; real simultaneous login and
   desktop-dialog behavior is not claimed by that proof.

`PASS_IF`: both native services accept fingerprint within the bound, passwords
work as described, sudo-i behaves consistently, no-enrollment/BUSY/cancel have
usable outcomes, and login/unlock show no regression. Retain the candidate on
PASS. `FAIL_IF`: wrong credentials accepted, known-valid password unusable,
30–45-second sudo password stall, broken credential/session setup, or regression.
`STOP_IF`: fourth contact, implicit acquisition/retry, activity continuing after
cancel, unexplained persistence, collision, drift or recovery-required message.
Stop the series immediately on FAIL/STOP and use rollback; do not repeat it.

## Rollback

For a fresh installation, from the same checkout and repository directory:

```bash
deployment/managed-install/manage.sh uninstall
```

For an update **between compatible combined candidates**, use:

```bash
deployment/managed-install/manage.sh rollback
deployment/managed-install/manage.sh status
```

Both invoke sudo and belong to the operator. Uninstall restores original PAM
presence/content/mode/owner and supported default SELinux labels, removes owned
integration files and restores Fedora fprintd; templates/protected material are
preserved. Update rollback restores the prior complete runtime through current
and retains identical host rules and Polkit counters. File timestamps are not
restored. Custom attributes/ACLs on qualified files are refused at preflight.
Check the PASS output, expected status/commit and the normal password workflow.

On `POLKIT_ROLLBACK_FAILED`/RECOVERY_REQUIRED, runtime and ownership state are
retained: stop, keep the checkout and report the precise message. Do not delete
files or repeat an authentication loop. After other FAIL/instability/regression,
rollback is required; on PASS retain the advancement.

Report PASS/FAIL, the observed native behavior, exact error text and where it
occurred. Additional logs are only needed after a real failure.

## Separate development-PC migration plan — not executed

The current PC has D285 plus later D293/login overlays. The old D285 uninstall
can delete its owned enrollment template and restore a different authselect
baseline. Therefore neither a direct combined install nor a blanket sequence of
old uninstall commands is an approved migration recipe.

Before that future migration, the operator and AI must establish the exact
installed overlay versions, ownership states and their original rollback paths
through a targeted read-only inventory. Preserve the current functioning sudo
path and enrollment; do not export protected material into the review set.
Review top-down overlay removal and template preservation against those actual
states, then produce a specific reversible migration delta. A clean baseline
can instead be prepared separately, without altering this PC. No D285 file or
sudoers selector is modified by the current work. This migration dependency is
a Human Gate, not a missing clean-candidate sudo dependency.
