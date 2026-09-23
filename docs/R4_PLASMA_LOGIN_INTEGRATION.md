# R4 — explicit fingerprint choice at Plasma Login

Status: **implemented candidate for sensor-free VM checks; not installed or live-qualified**.
Baseline for this review: `4997fe47825cb1748bf34650b3b2eaaedb9dba49`.
The user superseded the proposed login-limitation/R5 transition. R4 stays open,
Plasma fingerprint login is required, and R5 stays blocked. No obsolete R5 files
or commits existed in the clean checkout when this replan started.

## Evidence and the supported option A

The human's completed login configuration query reports guest checkout
`725b3c1f8bf879b9e56632b4f15da494968cead7`, Fedora 44 KDE Wayland,
`plasma-login-manager-6.7.5-1.fc44`, PAM `1.7.2-2.fc44`, authselect
`1.7.1-1.fc44`, systemd `259.9-1.fc44`, and fprintd-pam `1.94.5-5.fc44`.
The active display manager is stock `plasmalogin.service`, with stock
`/usr/bin/plasmalogin`, no local normal-login PAM override, no autologin user,
and valid authselect `local` with `with-fingerprint` already enabled.

Normal vendor authentication enters `password-auth`, whose auth rules are
env, faildelay, unix and deny, with no fingerprint module. `system-auth` and
`fingerprint-auth` contain fingerprint authentication but are not the normal
login auth route. An include in another PAM facility does not invoke its auth
rules. The greeter and autologin services are distinct from normal user login.

The immutable [Fedora source provenance](../reference/plasma-login-manager-fedora44-6.7.5/PROVENANCE.md)
and its source manifest were checked. `PamBackend.cpp::start` selects only
`plasmalogin`, `plasmalogin-greeter`, or `plasmalogin-autologin`. The normal
greeter forwards username/password to `Display::startAuth`; no configurable
fingerprint service or separate biometric transaction is present in this
version and its four Fedora patches. This is a finding about the observed
baseline, not a claim that Fedora cannot support fingerprint login.

Linux-PAM supports composition: an absolute `include` reads the current file
directly. A named `include plasmalogin` inside an `/etc/pam.d/plasmalogin`
override would recurse into that override. `substack` contains control-flow
effects but does not conditionally select fingerprint from an empty token.
See [v1.7.2 include handling](https://raw.githubusercontent.com/linux-pam/linux-pam/v1.7.2/libpam/pam_handlers.c)
and [documented control syntax](https://raw.githubusercontent.com/linux-pam/linux-pam/v1.7.2/doc/man/pam.conf-syntax.xml).

Putting `pam_fprintd sufficient` before password authentication alone retains
the historical forced password wait. The stock module does not use the
password token as a branch selector. Its [local source](../reference/fprintd-fedora44-1.94.5/source/pam/pam_fprintd.c)
and [manual](../reference/fprintd-fedora44-1.94.5/source/data/pam_fprintd.pod)
also distinguish serial PAM from concurrent application-managed conversations.

A `pam_exec expose_authtok` empty-stdin test is not selected: v1.7.2 logs a
failed token pipe write without changing the eventual successful child result;
an empty stream is therefore not proof of explicitly empty input. It also
does not check the result of storing a newly prompted token. This follows
from [the implementation](https://raw.githubusercontent.com/linux-pam/linux-pam/v1.7.2/modules/pam_exec/pam_exec.c),
not a failure observed in the VM. The exact Fedora PAM SRPM audit found no
Fedora change to these paths. Exact source package:
[pam-1.7.2-2.fc44.src.rpm](https://kojipkgs.fedoraproject.org/packages/pam/1.7.2/2.fc44/src/pam-1.7.2-2.fc44.src.rpm),
SHA256 `7fc17d339337dda1afa8df8deb9c78fcbf706d4bb8306957f72a610d195e077d`.
Its patchset leaves pam_exec, pam_dispatch and pam_get_authtok unchanged.
The Fedora `pam_selinux_permit.so` symlink targets pam_sepermit, whose setcred
returns `PAM_IGNORE`; this is why the prefix below delegates its non-IGNORE
authentication results back to the complete vendor lifecycle. The source RPM
was inspected in memory, not installed or added as runtime input.
No password is deliberately sent to a helper.

**Option A result:** supported composition exists and is reused below; no
complete native configuration satisfying explicit token selection and the
failure model was identified in the audited baseline. This justifies the
small option B selector, not a private Plasma implementation.

## Option B — one login integration, explicit owned files

The candidate is [deployment/plasma-login-opt-in](../deployment/plasma-login-opt-in/README.md).
It introduces one PAM service entry, `/etc/pam.d/plasmalogin`, plus its own
selector library and removal metadata under
`/usr/local/lib64/goodix-plasma-login/`. These are multiple explicitly owned
files forming one integration; they are not hidden inside the qualified R3
runtime or its manifest. No Fedora-owned file is overwritten. No service unit,
ExecStart, authselect profile, sudo, PolicyKit, greeter or daemon is changed.

The selector is independent project code using public PAM APIs. It never
checks a password, grants access, contacts fprintd, handles USB, reads a
biometric template, logs a token, or starts another process. Its success means
only “the opt-in fingerprint branch may be tried”; the PAM control maps that
success to `ignore`, never to authentication success.

The candidate prefix is:

```pam
auth [success=ignore default=2] /usr/local/lib64/goodix-plasma-login/pam_goodix_login_gate.so
auth [ignore=ignore default=1] pam_selinux_permit.so
auth sufficient pam_fprintd.so max-tries=3 timeout=30
auth [default=reset] pam_permit.so
auth include /usr/lib/pam.d/plasmalogin
```

Account, password-change and session facilities separately include the same
current absolute vendor file. There is no copied vendor stack or stored vendor
backup to restore over a later package update.

### Password and fingerprint paths

The user explicitly accepted this UX on 23 September 2026: typing a nonempty
password and submitting it selects password immediately; submitting an empty
field explicitly selects fingerprint. During that chosen bounded series, the
stock greeter may disable the field. After failure it must restore the normal
password UI. Concurrent password entry/cancellation during the series is not
required by this decision.

The selector obtains the token through `pam_get_authtok`. Nonempty input returns
before configuration inspection. Null response, API error (including incomplete
conversation), incompatible configuration and missing selector all skip the
two biometric-prefix rules. The reset then restores the initial dispatcher
state before any vendor rule executes. It cannot erase a vendor denial. The
vendor reads the already stored token through the normal PAM API. No fingerprint
timeout is introduced on this path; normal password policy and failure delays
remain Fedora's responsibility.

For empty input, a conservative compatibility check reads **current auth rules**
from vendor `plasmalogin`, effective `/etc/pam.d/password-auth`, and
`/etc/pam.d/postlogin`. Only the observed small rule sequences enable fingerprint.
Whitespace/comments may differ; new auth rules, unknown syntax, unreadable or
oversized files disable fingerprint. Other facilities are delegated and may
change without being copied. This is a fingerprint eligibility check, not a
PAM interpreter or a hash/version prerequisite for password login.

Checking all three files matters: a future `pam_faillock`/`pam_access` rule
inside a referenced stack must not silently be bypassed by an early fingerprint
success. The existing SELinux prefix is performed only on the compatible
opt-in branch. Only its `PAM_IGNORE` result proceeds to fingerprint; success
or error delegates to the vendor, which applies its own control and credential
lifecycle. Wallet auth rules are optional in the accepted shape; fingerprint
does not supply a password to unlock wallets. Current account/session checks
still apply after fingerprint success.

The reset is necessary for **pam_setcred**, not just pam_authenticate. Linux-PAM
reuses authentication routing for credential establishment; a numerical jump
can contribute the missing module's error before the vendor runs. The reset
clears only the project prefix's accumulated result. The included VM regression
test must demonstrate both the broken prefix without reset and the corrected
case using the real library, including the SELinux-success branch. See
[dispatcher implementation](https://raw.githubusercontent.com/linux-pam/linux-pam/v1.7.2/libpam/pam_dispatch.c)
and [token API](https://raw.githubusercontent.com/linux-pam/linux-pam/v1.7.2/libpam/pam_get_authtok.c).

### Bound and fallback

Stock pam_fprintd has `max-tries=3` explicitly and exits immediately on MATCH.
Its loop decrements on completed NO_MATCH; timeout, disconnect and terminal
error exit the series. `timeout=30` is per attempt, not a 30-second bound for
the whole series. The unchanged R3 driver fences processing failures and MATCH;
clean NO_MATCH permits the next explicit stock VerifyStart. No new retry loop
is added. Driver epoch/capture telemetry remains the evidence for real contacts.

On exhaustion/unavailability the prefix resets and the vendor evaluates the
empty submission normally; for the laboratory account with a password this
fails and returns to the greeter. `Main.qml::onLoginFailed` re-enables the UI;
`Display::startAuth` rejects a concurrently active authentication. No automatic
second GUI submission was found. The eventual human live must still verify
return to the field, at most three contacts, first-MATCH stop and no second
series. Source review and synthetic tests cannot claim these live observations.

## Update and uninstall model

| Change/failure | Intended result | Qualification |
| --- | --- | --- |
| Gate missing/unloadable, token/config check fails | Current vendor password path; no fingerprint | Real PAM VM regression pending |
| Current vendor auth policy changes in any of the three files | Fingerprint disabled; current password/auth policy used | C fixture checks prepared |
| Current account/session/password-change rules change | New rules read directly | Real PAM include checks prepared |
| fprintd/module/device unavailable | Chosen fingerprint series fails; next password submission skips it | Synthetic dispatch plus later live required |
| Content update at the vendor's packaged path | No frozen copy masks it; compatible fingerprint may remain available | R5 update validation still blocked |
| Remove integration | Remove owned override first; current Fedora configuration becomes visible | Synthetic lifecycle checks; no stock backup replay |

The absolute path is an explicit packaging dependency. Fedora's observed
package owns `/usr/lib/pam.d/plasmalogin`; its spec and CMake install location
corroborate it. Content updates preserving that service contract are the target
of this model. **Removal/relocation of the vendor file while an override remains
can break password login (class A)**, as can an invalid vendor PAM configuration.
The gate cannot repair a configuration-parse failure by returning `ignore`.
There is no claimed perpetual Fedora path guarantee or complete R5 PASS.
This dependency must remain visible in the release audit: an actual normal
update that changes it without compatible integration handling is a release
blocker, not an acceptable fingerprint-only outcome. No TTY repair, vendor
snapshot restoration or runtime Fedora hash pin is part of the lifecycle.

Thus `UPDATE_FAILURE_MODEL=FINGERPRINT_ONLY` is the **candidate's intended model
under the current vendor service-path contract**, not a measured global result.
Password safety under normal package updates remains a required qualification.
Updating/removing only the project integration must suffice; otherwise reject
the architecture before release.

## D295/02 comparison and option D

The manual's D295/02 section and
`development/private-root/analysis/D295/D295_02_PLASMALOGIN_PAM_CORRECTIVE.md`
record successful PAM-only integration without a rebuilt Plasma daemon.
That feasibility and collision-safe, reversible ownership are retained.
The persistent vendor-copy model, hash-dependent runtime accessibility and
historical password-wait acceptance are not retained. Historical drift tests
mostly detected drift in status/install tools; they did not prove live password
safety after an update. The separate roughly 30-second password-delay evidence
is not attributed to the D295/02 run without provenance.

Option B has not been excluded, so option D (private Plasma/greeter or VT work)
is neither selected nor implemented. R3 and the other three consumer PASSes
remain preserved. The next boundary is solely human VM build and synthetic
PAM tests with no reader, no root and no system PAM installation. A live login
procedure is not ready until those results have been reviewed.
