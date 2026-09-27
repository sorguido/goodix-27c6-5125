<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Phase E: manual zero-mask recovery validation

This kit installs the functional enrollment candidate described in the
[contract](../../docs/ENROLLMENT_ZERO_MASK_CONTRACT.md). Offline checks do not
establish sensor behavior. Only the human operator installs it and performs the
live test. The agent does not run these privileged or sensor-reaching commands.
No additional approval token or SHA ceremony is needed.

## Preparation

Use the reviewed `development` checkout on Fedora 44 x86_64 with the existing
public schema-2 Goodix installation and its normal password fallback. Close
fingerprint dialogs and other authentication attempts; keep fingers off the
reader during install/rollback. Finish rollback of any Phase C probe first.
The kit refuses a pre-existing service mask, backup, changed installation or
different dependency/library inventory. A refusal means stop and inspect the
reported condition, not delete files to bypass it.

From the repository root, build as the ordinary user if this candidate has not
already been built:

```sh
python3 -B production/build-public.py --output /tmp/goodix-phase-e-production
```

The output path must be new. An existing payload produced by this reviewed
checkout can be used directly; do not overwrite it or rebuild as root. The
builder runs offline ABI/material/PAM mock checks and does not install anything.

## Install (human only)

```sh
sudo sh operator_kit/phase-e-zero-mask/install.sh /tmp/goodix-phase-e-production
```

The installer validates the candidate and the current installation, stages the
replacement, temporarily masks D-Bus activation of fprintd, stops and verifies
the service, then swaps the runtime directory. It releases only its own mask
and does not start fprintd or open USB. Successful output is
`PHASE_E_INSTALL=PASS`; an identical repeat reports `ALREADY_INSTALLED`.

Only `libfprint-2.so.2.0.0`, `source-files.sha256`, `build-provenance.json` and the
generated `installation.json` receipt may differ. Dependencies and licenses
must match the installed baseline exactly. The previous runtime directory is
retained at `/usr/local/lib64/goodix-27c6-5125.phase-e-previous`; the root-only
receipt is `/var/lib/goodix-phase-e-zero-mask/state.json`. No PAM, PolicyKit,
systemd configuration, stored fingerprint, key or device material is changed.
The temporary mask is `/run/systemd/system/fprintd.service`.

## Run one targeted enrollment (human only)

Open the ordinary Users settings as the desktop user:

```sh
kcmshell6 kcm_users
```

Start one enrollment using an available finger slot, preserving existing
enrollments. After the first accepted contact, use a brief or poorly positioned
little-finger contact to try to reproduce the observed zero-mask. Continue only
as requested by the ordinary UI, then let this same enrollment complete. Do not
run automated enrollment loops. A placement choice does not guarantee zero-mask.
Stop at completion, cancellation, a red error, unexpected acquisition or a
stalled UI; close the dialog so the client releases the device.

The target PASS requires an actual logged zero-mask recovery, no red error for
that accepted sample, and successful continuation/completion of the same
enrollment. If zero-mask is not logged, the targeted test is **inconclusive**;
ordinary success alone is not proof. Review the evidence before another attempt.

After a targeted PASS, perform one ordinary enrollment in a free slot, one
normal verification through the established client, and one duplicate-detection
attempt using an already enrolled finger. Do not delete existing prints just to
create a test slot. A second user/profile is optional and requires explicit
human participation. These are separate manual actions, not an automatic suite.

## Collect metadata

After client Release/close:

```sh
sudo sh operator_kit/phase-e-zero-mask/collect.sh > /tmp/goodix-phase-e-metadata.log
```

The collector reads the journal since installation, strips surrounding journal
text, and emits only the candidate ID and these driver metadata families:
`GOODIX_ZERO_MASK_RECOVERY`, `GOODIX_PRODUCTION_EPOCH_AUDIT`,
`GOODIX_STOCK_CAPTURE_RESULT`, `GOODIX_ENROLLMENT_CONTACT_UNUSABLE`.
It does not dump frames, images, prints, keys or material. Keep the file together
with a short human note about the UI outcome and action order. An empty record
or missing close audit is incomplete evidence, not PASS.

For each target zero sample expect:

```text
event=sample ZERO_MASK_RECOVERY=1 PRIMARY_PRESERVED=1
OPTIONAL_20_SENT=0 AUX_B0_COUNT=0 FINAL_AUX_34_SENT=0 HIDDEN_RETRY=0
```

The zero-specific `event=closed` record summarizes `recovered`,
`LATE_0200_COUNT`, `REARM32_COUNT`, and `HIDDEN_RETRY=0` for that enrollment.
Each accepted nonterminal zero permits one normal next-sample 0x32; a terminal
zero permits none. A quality failure/cancellation may terminate without rearm.
One passive late0200 per zero window is allowed; a second terminates the action.
For multiple zero contacts, closed-record counters are cumulative within the
action, so correlate them with the individual sample/rearm/late-release records.
The general epoch `enroll_rearm32` counter includes ordinary contacts as well.

The final epoch audit record must show `outstanding=0`, `drained=1`,
`context_closed=1` and no persistent writes. These lowercase audit fields are
the requested `OUTSTANDING=0 / DRAINED=1 / CONTEXT_CLOSED=1` criteria; the kit does
not manufacture uppercase success markers or infer a wire trace from counters.

Stop and collect on red error, unexpected retry/acquisition, wrong command
counts, duplicate stale release, missing drain/close, or action state leaking
between attempts. Roll back after failure. Do not keep retrying a failing path.
On PASS, the operator may keep the candidate installed; rollback remains ready.

## Rollback (human only)

Close fingerprint dialogs and keep fingers off the reader, then run:

```sh
sudo sh operator_kit/phase-e-zero-mask/rollback.sh
```

Rollback inhibits activation, verifies the backup and current runtime, restores
the exact previous directory/receipt, restores its SELinux context and releases
only the owned mask. It does not start fprintd or remove host integration.
`PHASE_E_ROLLBACK=PASS` confirms restoration; an identical repeat reports
`ALREADY_RESTORED`. Collect before rollback where possible; collection also works
afterward. The small root-only receipt remains as an audit record and prevents
silently replacing the saved baseline with a second candidate.

Interrupted directory swaps, receipt writes and candidate cleanup can be
resumed by the same rollback command. A failed service stop or restoration can
intentionally leave the owned temporary mask to keep fingerprint unavailable
until rollback succeeds; password authentication is unchanged. An external
runtime/backup change or an unrecorded/foreign mask is refused. Do not remove
those guards or use the full uninstaller as a substitute for restoration.

## Offline verification and remaining risk

```sh
python3 -I -B operator_kit/phase-e-zero-mask/test_kit.py
```

Tests use temporary synthetic directories and mocked service/SELinux/journal
operations, with no root, USB or protected materials. They cover exact and
idempotent restoration, drift, corrupt/symlinked payloads, foreign masks,
interrupted swaps/receipts/deletion and restoration failure.

The first valid IRQ0002 after actual 0x32/ACK closes the host stale-release
window. This is the explicitly accepted Phase E rule, **not a proved firmware
barrier**. Old release bytes returned later in the new contact's ordinary
release slot can be indistinguishable from its current release. Offline tests,
the two silent Phase C observations and a successful live run cannot eliminate
that general protocol ambiguity. No timeout grants rearm; contacts remain
bounded by 20; no persistent sensor operation is introduced.
