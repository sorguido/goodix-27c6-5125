# Early login boundary — implementation and offline review

Entry: development `7c0f83b53ca2b8452a1c5ed5bc1f00d1314bc9aa`.
The current user explicitly authorized architecture B. No new strategy gate.
The authorized live boundary remains with the user.

`plasma-login.service` (user unit, after KWin) starts `greeter` instead of the
Qt executable. The small parent process retains a system-bus connection, calls
PrepareLogin, and starts the unchanged Qt executable only after READY or a
bounded failure. GetDefaultDevice has a 2 s deadline, PrepareLogin 12 s; the
driver's preparation deadline is 10 s. Failure starts the password UI. READY
expires after 120 s. There is no retry on restart, hotplug, expiry or failure.

fprintd authenticates PrepareLogin as the `plasmalogin` account and ClaimLogin
as root; normal user authorization still selects the PAM username. Its existing
claim ownership is retained. Open occurs once before the greeter; ClaimLogin
transfers that open session and VerifyStart authorizes exactly one acquisition.
The private paired-driver GObject signals add no exported libfprint ABI.
READY follows baseline decode and the first32 ACK. Before Verify, IRQ2 invalidates
and cancels the receiver without finger delivery, 22, matcher or enrollment.
The activation handoff returns before the normal generation/bootstrap/reopen
code. Production single-acquisition cleanup remains unchanged after handoff.

Greeter bus loss, timeout, suspend and removal close the prepared device after
USB cancellation/drain. Close is deferred out of protocol callbacks. Suspend
continues asynchronously after close, without nested waiting or preparation on
resume. A consumed/expired login cannot prepare again in the same greeter
lifetime. A new greeter can prepare once. Daemon restart loses readiness and
ClaimLogin fails closed instead of running ordinary initialization after Enter.
The login PAM override has max-tries=1 / timeout=8; ClaimLogin failure informs the
user to use password. Ordinary Claim, sudo PAM and ENROLL retain their paths.

Fedora Plasma 6.7.5 waits five seconds after session startup before stopping the
greeter. Ordinary Claim is therefore allowed as soon as the previous open session
is closed, even while the greeter bus owner still exists. Source checked:
`src/daemon/Display.cpp` slotSessionStarted/slotHelperFinished and
`src/daemon/Greeter.cpp` stop, plus the Fedora user unit. Fedora patches 170/200
and package configuration patches do not alter those ownership paths.

Private build provenance:
- unchanged staged libfprint integration: `c0e13ff5f78ac32403a753446dcbc44aa7f30556`;
- current canonical driver sources, with exactly four D293 material loader source
  files retained from `e61fce313794922a2dab156a1b38a8ddc5837f19`; no protected files read;
- fprintd 1.94.5 source from the existing Fedora provenance snapshot, patched only
  in the staging directory; original snapshot untouched;
- Fedora plasma-login-manager source RPM 6.7.5-1.fc44:
  `c85da4dac283ac8f4ebf0d3e68505d966347251b6c3896f6351dd19c18cda75b`;
  upstream tar `6ed7c3bbac1c79bc1a21c330923804aa6c3f720fafd6accb1a6a1fada684e84f`;
  inspected for lifecycle only, not imported or rebuilt;
- PAM/polkit header RPM hashes in `headers.sha256`. Compilation is isolated in
  SDK 25.08 with network disabled; final link uses installed Fedora libraries
  because Fedora libpam requires GLIBC_2.43. No host package installation.

Reproduce offline validation after the two builds:

```sh
./prepare.sh /tmp/goodix-login-normal
./prepare.sh /tmp/goodix-login-sanitizer sanitizer
./check-offline.sh /tmp/goodix-login-normal /tmp/goodix-login-sanitizer
```

Existing protocol and FpImageDevice suites use synthetic frames/material and
USB seams. New protocol assertions cover baseline/ACK before READY, one baseline
and arm in the authorized acquisition, early IRQ2 with zero22, and cancel.
Driver tests exercise the real 10 s deadline and drain-before-close. Daemon tests
include the actual patched handlers over a private D-Bus, substituting only
libfprint device operations and synthetic print loading: preparation precedes
reply; ClaimLogin adds zero opens; explicit Verify runs once; repeat fails;
expiry closes; ordinary Claim works afterward; suspend closes before forwarding.
PolicyKit is bypassed only in that test; live system-bus/SELinux authorization is
not claimed validated. Greeter tests replace only the child executable with a
marker script and verify UI ordering on success, false readiness and D-Bus error.
Both C paths run normally and under ASan/UBSan. Transaction tests use temporary
filesystem/service doubles, covering idempotence, partial failures, rollback and
drift protection. No real fingerprint, USB, service activation or sudo occurs.

Pre-live methodological review: the changed method moves the real calibration
before the interactive greeter, keeping the same armed session. It tests whether
removing the setup/contact race fixes immediate contact. If failure persists at
FIRST_IRQ2 despite READY and same-session attach, inspect that failure's bounded
journal and physical timing; do not extend waiting, repeat the same test, add
recovery commands or broaden the strategy automatically.

Offline ordering and ownership checks do not prove hardware recognition,
SELinux deployment behavior or Windows compatibility after this candidate.
Those are residual live checks, not reported as completed.

## Completed offline validation and PM disposition

`prepare.sh` completed from the actual recipe in both normal and sanitizer modes.
`check-offline.sh` completed: protocol 16/16 and driver 34/34 in each mode;
private-bus daemon and greeter checks in each mode; 6/6 transaction tests.
Source/manifest checks pass in both staging and the canonical checkout. Production
ABI LIBFPRINT_2.0.0, absence of host-test symbols/RPATH, native linking and ldd
resolution pass. The complete rebuilt daemon uses `/etc` configuration and
`/var/lib/fprint` storage, matching Fedora; no storage was opened by the tests.
Read-only installed-file audit confirms the D293 hashes and absence of this overlay.

Hostile PM review inspected actual driver diff, patched daemon handlers, PAM,
greeter process ordering, build recipe and ownership of install/rollback files.
The review checked callback reentrancy/drain, no pre-action22, timer lifetime,
client loss, suspend continuation, no automatic retry and ordinary Claim during
the five-second greeter tail. Disposition: offline candidate accepted;
HUMAN_REQUIRED for installation and target validation. Live/SELinux behavior,
physical immediate-contact recognition and Windows remain unclaimed.

Reviewed normal-build artifacts (before the documentation/commit step; installation
rebuilds from the clean committed recipe and records that full SHA):

| Artifact | SHA-256 |
| --- | --- |
| libfprint-2.so.2.0.0 | `3c787a5a9dbe84f884cade0d8190777d0ada6841fe456d01d204215091661dfc` |
| fprintd | `c1b38582ddbfe1149ced999ce1c123ac9ea8d2457ba37225cf8ac6f06dab65de` |
| pam_fprintd.so | `e6269190c42dc4f2446e6a24e500f1b9dffd91617d0f24394706a879b946c16b` |
| greeter | `6b0f919275d5eb2cde7911a32f07a7f7058ac256d97f2bee779f95c0edf6d02b` |

OUTCOME=OFFLINE_CANDIDATE_COMPLETE
ADVANCEMENT=PRE_GREETER_PREPARATION_AND_SAME_SESSION_VERIFY_IMPLEMENTED
EXECUTABLE_CLOSURE=OFFLINE_PASS_LIVE_PENDING
RESIDUAL_BLOCKER_OR_RISK=COLD_LOGIN_AND_HOST_SELINUX_VALIDATION
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md
REVIEW_SET=development Git diff, canonical sources/tests, this directory
