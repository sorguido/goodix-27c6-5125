<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R3: clean replacement of the R3-A runtime

**Completed: clean replacement, SELinux material correction, production material
preflight and live stock-fprintd Claim/Release PASS** on 22 September 2026.
The post-replacement open failures had two deployment causes: the material tree
initially carried a generic SELinux label, and after that correction the installed
`target-material-manifest.json` was still the historical
`d232-target-material-v1` source rather than the production loader's
`goodix-5125-device-materials-v1` projection.  The reviewed deterministic
conversion restored the runtime-v1 manifest; the production material loader then
passed sensor-free and one subsequent enumeration -> Claim -> Release passed.
Do not repeat those gates.  The procedure below is retained as historical
clean-replacement evidence, not as the next live action.

**Enrollment acquisition/storage PASS, with a label mismatch:** the user confirms
the physical **RIGHT index** was saved as `guido` / `left-index-finger`. Eight enrollment
contacts/stages, completed and listed, clean epoch closure; runtime/template
retained and reader detached. [The enrollment procedure](R3_ENROLL_VM.md) is
completed evidence. [Stock verification](R3_VERIFY_VM.md) also passed with the
RIGHT index at the first attempt, with clean release/drain/close. **R3 is closed
at the biometric boundary. R4 KScreenLocker password unlock and first-contact
fingerprint unlock also passed, with closed/drained host cleanup: SUPPORTED on
the tested baseline. Ordinary stock sudo also passed password and first-contact
fingerprint authentication. Stock PolicyKit is now also SUPPORTED after password
and first-contact fingerprint PASS. The [VM login configuration query](R4_LOGIN_PREFLIGHT_VM.md)
is complete: normal stock Plasma Login uses password-auth without fingerprint.
Plasma fingerprint login is required; R4 remains open and R5 is blocked.
The opt-in selector's VM build/tests passed at `6fc6e64`; installation and
file/default-label checks passed at `24c3018`. Keep the installed candidate.
Next human gate: [password login first, then opt-in fingerprint](../plasma-login-opt-in/R4_PLASMA_LOGIN_VM.md),
in the VM, with USB absent until password PASS.**
The audit query identified three nr_hugepages read denials, non-fatal for the
tested KScreenLocker path; its [SELinux review](R4_KSCREENLOCKER_VM.md#completed-selinux-review) is closed. Keep
the runtime/template and known label mismatch; no rollback or repeated KScreenLocker live.
The completed sudo live ended with exit 0, no password during MATCH, closed/drained
cleanup and fprintd inactive/MainPID 0. It is SUPPORTED on the tested baseline;
do not repeat it. sudo-i auth is configuration-covered, its login shell/session
untested. PolicyKit's configuration/action queries and native test are all closed.
The KDE agent authenticated guido for exec on /usr/bin/true as root: A real
password with reader absent, B one RIGHT-index contact/MATCH with no password,
input or restart, both exit 0. Temporary authorizations were empty after revocation
before both stages. One VERIFY/epoch, closed/drained cleanup, no retry/reopen/reset
or persistent family observed, final fprintd inactive/MainPID 0, reader detached.
This supersedes historical preflight PID 8053. Guide commit `8ed5218` resolves
locally to `8ed52181897c4078dfb2be26fe67481e7a7b6961`; the handoff does not print
the guest checkout SHA. No new PolicyKit SELinux recurrence is confirmed.
No repeat or rollback of these PASSes. The separate opt-in candidate preserves
this R3 runtime and delegates login to current vendor PAM. It is installed;
the real-login procedure is reviewed, but login remains unqualified.

The user reports PM-accepted normal **44/44** and ASan/UBSan **44/44** synthetic
results, and a clean, reviewed normal runtime build from
`b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`. Reuse that output; do not rebuild.
The installed R3-A baseline uses build
`c5df71772b3ade7cf3d1ea2d418a65e0ab75b1f6` and install commit
`92311c5ebe1d05a68ad0542ecb8aeafb9776db0e`; its stock load-check passed.
A cold VM snapshot exists as an external laboratory fallback. Neither the
installer nor its inverse depends on that snapshot.

This is a clean uninstall → Fedora stock → clean install, with the accepted
R3-A footprint. There is no in-place upgrade or multi-version uninstaller.
The **old installed inverse** must remove the old runtime. The new checkout
accepts only the qualified R3 build and must not uninstall the old R3-A.

## Manual VM procedure

Use the existing Fedora 44 KDE x86_64 VM and private clone. Password access
and desktop must work normally; keep SELinux Enforcing. No new packages,
materials, templates or USB passthrough are needed. Do not run enroll/verify,
start fprintd for a load-check, or change PAM/udev/Fedora files.

**STOP_IF:** any command fails, the checkout is dirty/not `development`,
SELinux is not Enforcing, the reader is present/assigned to the VM, build
provenance or hashes differ, vendor verification fails, or service state is
unexpected. Return the error; do not bypass checks, delete drifted files or
use the snapshot as an installer step.

From inside the VM clone, paste the block as a whole. The user-confirmed
qualified output is `/home/guido/goodix-r3-20260922-111144`, containing
`build-provenance.txt` and `runtime/`. The ordinary sudo password is expected
for removal and installation.

```bash
(
  set -euo pipefail
  # 1. Preflight: VM, disconnected reader, stock vendor files, qualified build.
  cd "$(git rev-parse --show-toplevel)"
  test "$(git branch --show-current)" = development
  test -z "$(git status --porcelain)"
  git pull --ff-only origin development
  git rev-parse HEAD
  systemd-detect-virt --vm
  . /etc/os-release
  test "$ID" = fedora
  test "$VERSION_ID" = 44
  test "$(uname -m)" = x86_64
  test "$(getenforce)" = Enforcing
  for device in /sys/bus/usb/devices/*; do
    if [[ -f $device/idVendor && -f $device/idProduct &&
          $(<"$device/idVendor") == 27c6 && $(<"$device/idProduct") == 5125 ]]; then
      echo 'STOP: disconnect the Goodix reader from the VM' >&2
      exit 1
    fi
  done
  rpm -V fprintd libfprint
  r3_build_out=/home/guido/goodix-r3-20260922-111144
  test "$(sed -n '1p' "$r3_build_out/build-provenance.txt")" = \
    SOURCE_COMMIT=b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226
  test "$(sed -n '2p' "$r3_build_out/build-provenance.txt")" = BUILD_MODE=normal
  (cd "$r3_build_out/runtime" && sha256sum -c SHA256SUMS)

  # 2. Old R3-A removal: use ONLY its saved inverse, before the new install.
  sudo /usr/local/lib64/goodix-27c6-5125/uninstall.sh

  # 3. Fedora stock checkpoint. Stop here on any mismatch.
  test ! -e /usr/local/lib64/goodix-27c6-5125
  test ! -L /usr/local/lib64/goodix-27c6-5125
  test ! -e /etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf
  test ! -L /etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf
  test "$(systemctl show fprintd.service -p FragmentPath --value)" = \
    /usr/lib/systemd/system/fprintd.service
  r3_exec=$(systemctl show fprintd.service -p ExecStart --value)
  [[ $r3_exec == *'path=/usr/libexec/fprintd ;'* ]]
  r3_environment=$(systemctl show fprintd.service -p Environment --value)
  [[ $r3_environment != *LD_LIBRARY_PATH=* && $r3_environment != *goodix-27c6-5125* ]]
  systemctl show fprintd.service -p ExecStart -p Environment -p ActiveState
  rpm -V fprintd libfprint
  echo R3_STOCK_CHECKPOINT=PASS

  # 4. Clean install of the qualified build; no rebuild or service start.
  sudo ./deployment/minimal-runtime/install.sh "$r3_build_out"

  # 5. Verify the new installation leaves fprintd stopped.
  test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
  test "$(systemctl show fprintd.service -p MainPID --value)" = 0
  systemctl show fprintd.service -p ExecStart -p Environment -p ActiveState -p MainPID
  rpm -V fprintd libfprint
  test -z "$(git status --porcelain)"
  echo R3_CLEAN_INSTALL=PASS FPRINTD=STOPPED LOAD_CHECK=NOT_EXECUTED
  # 6. STOP for review. Do not start fprintd or connect the sensor.
)
```

The old inverse restores its saved active/inactive state **with Fedora's
stock libraries**; an initially active service may start and then idle-exit.
The new install records that current state, stops the service and leaves it
stopped. If it is unexpectedly active at the final checkpoint, stop it with
`sudo systemctl stop fprintd.service` and report the discrepancy as a failure;
do not perform a load-check.

**PASS_IF:** old inverse reports `R3_UNINSTALL=PASS`, the stock checkpoint
passes, new install reports `R3_INSTALL=PASS` with the qualified build SHA and
the current install SHA, final state is inactive/MainPID 0, vendor checks are
clean and the checkout is clean. **FAIL_IF:** any failed check, transaction,
collision/drift, unexpected activation or password/desktop regression.
On PASS keep the new runtime installed and both build outputs. Load-check
and any later sensor work require separate review/handoff.

## Footprint and rollback

The current installer owns:

- `/usr/local/lib64/goodix-27c6-5125/`: five private libraries (libfprint and
  four OpenCV), two libfprint links, notices/hashes/provenance, `deploy.py`,
  `uninstall.sh` and `installation.json`;
- `/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf`:
  `[Service]` with only the project `LD_LIBRARY_PATH`;
- the exact local fcontext `/var/lib/goodix-5125-poc(/.*)?` **only if created
  by this installation**, recorded in `installation.json`. Existing compatible
  rules remain unowned. Six material labels are applied and verified. The
  non-secret target manifest is additionally parsed fail-closed and must match
  the exact runtime-v1 schema and acceptance pins; secret/binary material
  contents remain unopened by deployment code. Duplicate fields and escaped
  strings are rejected consistently with the production parser. See the
  [historical Gate A](R3_SELINUX_MATERIAL_VM.md) ownership
  review.

No ExecStart replacement, daemon, wrapper, PAM, udev, template or material
content change. Temporary staging is removed on ordinary success/error. The installer
checks clean `development`, VM/OS, stock fprintd, SELinux, exact normal-build
identity, critical-source continuity, five library digests and relative links.
Identical payload reinstall is idempotent; a different payload or old build
is refused. Ownership/content drift is preserved for review.

After a failed new deployment, instability or explicit rollback request,
keep the reader disconnected and use the **new** installed inverse if present:

```bash
sudo /usr/local/lib64/goodix-27c6-5125/uninstall.sh
```

If the new transaction already removed its runtime, its matching checkout's
`sudo ./deployment/minimal-runtime/uninstall.sh` can confirm `ALREADY_ABSENT`.
Never use that fallback for the old R3-A installation. On rollback error,
stop and return the error; do not delete remaining state manually.

The updated saved inverse needs neither Git nor build output. It first
removes only an owned material fcontext and restores default labels on the
six paths; pre-existing compatible rules are preserved, drift stops for review.
It then removes only owned
files/drop-in, reloads systemd and restores the saved service state using
Fedora stock libraries. It returns to **Fedora stock**, not the old R2 payload.
Repeat the stock checkpoint from step 3 after rollback. Unrelated files,
materials and templates are preserved; drift/recovery failure retains the
inverse for review. Hard power-loss recovery remains unqualified. The original
R3-A instructions/inverse are recoverable at `92311c5`; no history is rewritten.

## Evidence to return

Return the full install commit, selected build directory and provenance,
five checksum results, old uninstall result, stock checkpoint output, new
installer result and final service properties. Confirm sensor disconnected,
SELinux Enforcing, vendor verification clean, checkout clean, no load-check,
and whether the new installation remains in place. On failure include the
exact command/error and rollback outcome. No protected contents or broad logs.

Offline verification: `python3 -B deployment/minimal-runtime/test_offline.py`
passes 27 checks using temporary files and mocked host/device interfaces.
It covers install/uninstall, idempotence, build/payload rejection, drift and
collisions, service state, transaction rollback, saved inverse independent of
checkout/build, unchanged vendor/material sentinels and reader-absence gates.
This does not substitute for the manual VM deployment.

The original 27 filesystem tests isolate the material boundary; the dedicated
`test_material_labels.py` exercises creation/adoption/conflicts, label and
metadata checks, partial failure recovery, the existing-install corrective
and saved inverse using synthetic files and mock SELinux interfaces. Current
recovery validation: 27 deployment + 36 material/preflight + 14 open/close = 77 PASS.
The JSON corrective requires no change to the installed runtime or saved inverse.
Do not rerun the completed receipt reconciliation.
The enrollment preflight corrective retains the stopped-service gate and adds
the observed service properties to failures. Its subsequent preflight and live
enrollment passed. The current verify guide retains the single human-executed
stop with the reader disconnected; no further corrective is required.
