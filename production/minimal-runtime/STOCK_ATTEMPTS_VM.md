<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R3: synthetic retry/attempt regression in the VM

**Next human gate: compile and run offline tests only. Keep the reader
disconnected. Do not rebuild R2, reinstall R3-A or run a live test.**

The latest VM run **compiled/linked and started both normal and sanitizer
tests**. Both report the same single known failure:
`/goodix/d291/fixed-raw-baseline-pinning-mechanics`, fixture line 2146.
The SIGFM test seam had recorded probe and enrolled signatures in the wrong
audit arrays. This corrective fixes that mapping and its comment, and names
the first parameter `probe`. All four getter uses and the existing D291
assertions have been reviewed; the assertions and score calculation remain
unchanged. The support file passes syntax-only analysis in both profiles.
Production behavior and the preceding ten-case R3 lifecycle correction are
unchanged. Full normal/sanitizer execution of this corrective is pending.
Pull the corrective and repeat this same gate with a new output directory.
Keep previous outputs as evidence. R3-A stays installed; no rollback is needed.

R3-A stock loading is accepted from the user's Fedora 44 KDE x86_64 VM
evidence: R2 build `c5df71772b3ade7cf3d1ea2d418a65e0ab75b1f6`, installation
`92311c5ebe1d05a68ad0542ecb8aeafb9776db0e`, stock `/usr/libexec/fprintd`,
SELinux Enforcing, five private libraries and Fedora libgusb. Keep that
installation and `/home/guido/goodix-r2-20260922-081148/` in place.

The current source keeps a terminal latch after MATCH/error and removes the
cumulative three-capture cap from `c0b2369`, following the user's explicit
decision. Fedora stock chooses the number of explicit attempts. After clean
NO_MATCH and cleanup, fourth and later explicit actions must be admitted.
The counter is telemetry only. The installed R2 binary does **not** contain
this source correction. The synthetic tests require five clean NO_MATCH
actions and a sixth MATCH, one normal acquisition per explicit call, then
zero new material acquisitions, USB claims or transport submissions on the
single rejected action after MATCH in each Claim. Retry/error resubmissions
remain fenced in the same Claim; full close/open starts with fresh state.
It also covers processing retries, client cancellation immediately after
the early MATCH report, drain/outcome ordering, resource release, synthetic
TLS secret cleansing and IDENTIFY→ENROLL.

This uses the canonical driver and Fedora libfprint source with synthetic
USB/material/SIGFM interfaces, not the system daemon, installed runtime,
real protected materials or real USB. It reuses the existing integration
fixtures; no operator harness or authentication consumer is introduced.
Corrective normal and ASan/UBSan execution is still pending. A source review
alone is not a regression PASS or permission for a live test.

## Run as the ordinary VM user

Prerequisites: the same Fedora 44 KDE x86_64 VM and installed user SDK
`org.freedesktop.Sdk//25.08` used for R2. No new packages or sudo are required.
From the private clone, check `development` and a clean worktree first:

```bash
cd "$(git rev-parse --show-toplevel)"
git branch --show-current
git status --short
```

STOP if the branch differs, status is non-empty, the sensor is assigned to
the guest, the SDK is missing, or any command fails. Do not discard changes,
install anything on the physical host, or enable USB to make a test pass.
Then:

```bash
git pull --ff-only origin development
git rev-parse HEAD
r3_tests_out="$HOME/goodix-r3-attempts-$(date +%Y%m%d-%H%M%S)"
./production/minimal-runtime/check-stock-attempts.sh "$r3_tests_out"
```

The source checkout is read-only to the SDK; network and device permissions
are disabled. The new output directory holds provenance, the test log and
test build objects. The suite runs 44 cases in normal and sanitized modes,
including ten new R3 series/early-MATCH cancellation cases. Each run has a
90-second ceiling.
LeakSanitizer remains disabled under the existing SDK restriction; address
and undefined-behavior checks are enabled.

**PASS_IF:** both runs pass all 44 tests, no sanitizer finding/timeout occurs,
the command exits zero and ends with `R3_STOCK_ATTEMPTS_VM_TEST=PASS` and
`R3_INSTALLED_RUNTIME_CHANGED=false`. The checkout must remain clean.
In particular, `/goodix/r3/{verify,identify}-no-match-5-then-match` must pass:
the test's five-NO_MATCH length is coverage, not a new driver limit.

**FAIL_IF:** compilation, assertion, sanitizer, source audit or timeout fails.
**STOP_IF:** any failure or request for root, real material, USB or runtime
installation. Preserve the error and output; do not try enrollment/verify.

## Cleanup and evidence

No install/uninstall is needed at this test-build boundary: no service, host
configuration or installed library is changed. The successful R3-A install
and its saved rollback remain available. Do not run its uninstall for a
synthetic test failure. After review, the inverse for these test artifacts is
only removal of the newly selected output, without sudo:

```bash
rm -r -- "$r3_tests_out"
```

Keep the output until the AI has reviewed the result. Return `provenance.txt`
(full source commit and Fedora fprintd package version), normal/sanitizer
test summaries, final result, output directory and confirmation that the
reader stayed disconnected and R3-A stayed installed.
On failure, return the first compiler/assertion/sanitizer error and the test
name from `tests.log`. No protected contents or broad system logs are needed.

After PASS the AI reviews dynamic evidence before preparing a separate
runtime update or any sensor handoff. Stock consumer workflow, material
availability and live safety do not follow automatically from these tests.
