# R4 — explicit fingerprint choice at Plasma Login

Status: **R4 CLOSED; Plasma Login SUPPORTED_ON_TESTED_BASELINE. R5 removal
qualification is active; [current removal/recovery](UNINSTALL.md) awaits VM qualification.**
Replan baseline: `4997fe47825cb1748bf34650b3b2eaaedb9dba49`; qualified login
guide/guest checkout: `7d0e2d3bcd33dc1311f70cc26b0a72b6889acfbe`.
The required fingerprint login is now demonstrated, rather than closed as a
stock limitation. No R5 files or operational matrix have been prepared.

## VM gate review and closure

The human's `CODEX_MINI_RESUME_R4_PLASMA_BUILD_PASS.md` reports source
`6fc6e640710885954d9e6fd603b3bc47b45d2ac6`, the final
`PLASMA_LOGIN_VM_BUILD_TESTS=PASS` marker, 11 lifecycle tests OK and
`INSTALLATION=NOT_PERFORMED`. The marker follows compilation, C unit tests,
actual libpam synthetic dispatch and lifecycle tests in the versioned script;
the reported completion is accepted. Individual C-case output, binary hashes
and a fresh RPM inventory were not supplied and are not invented. The test
sets contain 33 C unit cases and 16 dispatcher cases; these counts come from
source review, not a separately quoted VM transcript. The initial missing
pam-devel STOP was before build; the user installed that build dependency and
completed the gate. No runtime corrective or new build is justified.

The user preserved the complete `/tmp/goodix-login-build.OeCmF8Ja` directory at
`development/build-artifacts/plasma-login-opt-in/goodix-login-build.OeCmF8Ja`
inside the VM clone, excluded only through local `.git/info/exclude`, with
clean Git status. The production module and manager have no dependency on the
original build directory. The synthetic gate variant has compiled temporary
fixture paths and must not be installed or rerun from the moved copy.
Build artifacts remain local, untracked and outside the review/export set.

**Installation review: ACCEPT_AND_CONTINUE.** The subsequent
`CODEX_MINI_RESUME_R4_PLASMA_INSTALL_PASS.md` identifies guide checkout
`24c3018071e8d120687ff8fbd2f344cde620692d` and the same source/output above.
It reports `R4_LOGIN_SAVED_BUILD=PASS`, `PLASMA_LOGIN_INSTALL=PASS`,
`R4_LOGIN_INSTALLED_FILES=PASS`, all five default-label checks and
`R4_PLASMA_INSTALL=PASS SENSOR_CONNECTED=false LOGIN_TEST=NOT_PERFORMED`.
Silent vendor-hash and clean-worktree checks also passed. Review of the exact
[procedure](../deployment/plasma-login-opt-in/README.md) and manager confirms
manifest/source validation, installed bytes, root ownership/modes, exact receipt
and support contents, with publication of the PAM entry last. Installer, inverse,
module, PAM and tests have no delta from the tested source. This accepts the
human's deployment evidence; it does not claim direct guest inspection or
invent binary hashes, label strings or a fresh fprintd state.

At the installation checkpoint the desktop remained open, reader detached,
no logout/reboot/login, R3 runtime and
template preserved. Keep the installation without rebuild/reinstall/rollback.
Default file labels do not prove SELinux permission in the real login helper.

**Live review: PASS / R4 CLOSED.** The human's
`CODEX_CLOSE_R4_PLASMA_LOGIN_PASS_STOP_BEFORE_R5.md` reports execution of the
[reviewed procedure](../deployment/plasma-login-opt-in/R4_PLASMA_LOGIN_VM.md)
at the complete checkout above. Password login after normal logout, reader absent,
reached a working desktop with no fingerprint request/wait, approximately zero
delay and no unusual message. Then one empty Enter at the real greeter and one
RIGHT-index contact reached the desktop without a password, second series or
observed hidden retry. The labelled left-index-finger template was preserved.
One terminal VERIFY/MATCH and closed/drained audit corroborate the human result;
final fprintd inactive/MainPID 0 and USB detached. Complete telemetry appears
once in the [canonical manual](../Goodix%2027c6%205125%20manuale%20tecnico.md#plasma-login--live-pass-closure-r4-e-stop-prima-di-r5).

`release_tail=0` and `single_terminal=0` are consistent with early stock PAM
return after MATCH, alongside terminal capture, zero outstanding work and
closed/drained cleanup; they do not prove full device quiescence. The successful
real login establishes functional helper authentication/session startup on this
baseline, not universal SELinux permission or future update safety. No new AVC
observation or audit event is supplied. Preparation PASS includes the reviewed
Enforcing prerequisite; no separate post-live getenforce output is invented.

Failure fallback B, later NO_MATCH contacts and live uninstall were not exercised.
Do not create another live to exercise them. Password A, source review, bounded
stock PAM, accepted synthetic lifecycle and successful B suffice for this R4
qualification. Keep the installed integration, R3 runtime/template and inverse.
No rebuild/reinstall/rollback; stop here as requested by the user.

## Evidence and the supported option A

The human's completed login configuration query reports guest checkout
`725b3c1f8bf879b9e56632b4f15da494968cead7`, Fedora 44 KDE Wayland,
`plasma-login-manager-6.7.5-1.fc44`, PAM `1.7.2-2.fc44`, authselect
`1.7.1-1.fc44`, systemd `259.9-1.fc44`, and fprintd-pam `1.94.5-5.fc44`.
At that preflight the active display manager was stock `plasmalogin.service`, with stock
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
test covers both the broken prefix without reset and the corrected case using
the real library, including the SELinux-success branch; its containing gate
is now reported PASS as scoped above. See
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
fails and returns to the greeter. `Display::startAuth` rejects a concurrently
active authentication; no automatic second GUI submission was found.

**Pre-live source-review correction:** `Main.qml::onLoginFailed` re-enables the
UI, but that signal does not prove terminal PAM completion. `PamBackend::converse`
maps each `PAM_ERROR_MSG` to `ERROR_AUTHENTICATION`; `Display::slotAuthError`
emits `loginFailed` immediately. Stock pam_fprintd sends such an error for each
NO_MATCH before continuing its bounded loop. Thus the field may be enabled and
show generic failure while a second VerifyStart is already pending. Also,
`GreeterProxy::informationMessage` has no display handler in the audited stock
frontend, so no visible finger-specific prompt is promised. These are source
findings, not new VM observations or a reason to modify private Plasma code.

The procedure forbids resubmission during the series and additional contacts
on generic/ambiguous feedback. Up to three are available in PAM; continuation
requires an unambiguous native NO_MATCH/new request. After a STOP, detach before
password recovery and allow the outstanding call to end; a conservative wait
around the 30-second per-attempt timeout is an operator margin, not a guarantee
against a hung helper. A failed password return is a blocker. A successful
first MATCH does not exercise failure fallback: that is the actual outcome of
the completed run, recorded as NOT_EXERCISED. Real session startup, one-contact
MATCH/cleanup and password A are now observed; intermediate-error UI behavior
and failure fallback remain source-reviewed, not live-qualified by that run.

## Update and uninstall model

| Change/failure | Intended result | Qualification |
| --- | --- | --- |
| Gate missing/unloadable, token/config check fails | Current vendor password path; no fingerprint | Synthetic PAM gate accepted PASS; these fault cases were not live-tested |
| Current vendor auth policy changes in any of the three files | Fingerprint disabled; current password/auth policy used | C fixture gate accepted PASS |
| Current account/session/password-change rules change | New rules read directly | Account/session synthetic cases in accepted gate; password-change not exercised |
| fprintd/module/device unavailable | Chosen fingerprint series fails; next password submission skips it | Synthetic dispatch; failure fallback B NOT_EXERCISED in the successful live |
| Content update at the vendor's packaged path | No frozen copy masks it; compatible fingerprint may remain available | Future update compatibility unproven; R5 now qualifies removal/recovery |
| Remove integration | Remove owned override first; current Fedora configuration becomes visible | Accepted synthetic lifecycle; real removal not run on PASS; no stock backup replay |

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

**Phase boundary:** R4 closes functional login and the reviewed architecture on
the tested baseline. Empirical package-update survivability remains mandatory
in R5 before release; it is not also required as an R4 entry to that later phase.
The safety goal is unchanged: any update-induced class A/B failure is a release
blocker. Removing that circular dependency does not assert an update PASS or
erase the vendor-path risk. R5 is not prepared or started by this closure.

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
remain preserved. Normal password and opt-in fingerprint login have now passed
with stock Plasma and project-owned PAM composition. No source corrective or
deeper integration is required by these results. R4 is formally closed; the
explicit user instruction ends orchestration here, before preparing or starting
R5 or anticipating R6. The installed inverse remains available without execution.
