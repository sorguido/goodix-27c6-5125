<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R3-A: stock fprintd library-load check, without the reader

**Completed: R3-A STOCK LOAD = PASS**, human-reported at install commit
`92311c5ebe1d05a68ad0542ecb8aeafb9776db0e`, with SELinux Enforcing and the
reader disconnected. Keep this installation and its saved rollback. Do not
repeat the procedure below from newer driver source; the next gate is the
[synthetic retry/attempt test in the VM](../../production/minimal-runtime/STOCK_ATTEMPTS_VM.md).
The installed R2 binary does not include the pending R3 attempt correction.
The remaining instructions preserve this baseline's install/rollback record.

Run manually **inside the Fedora 44 KDE x86_64 VM**, after the human gate.
Reuse the successful R2 output `/home/guido/goodix-r2-20260922-081148/`, built
from `c5df71772b3ade7cf3d1ea2d418a65e0ab75b1f6`. **Do not rebuild.**
The install source is the clean `development` commit obtained below; the
installer records both commits. These are provenance, not approval tokens.

Purpose: establish whether Fedora's stock fprintd can start under its normal
service restrictions and SELinux Enforcing with the private library set.
This does not test fingerprints, device materials, authentication consumers
or update survivability. Keep the Goodix reader disconnected from the VM
throughout installation, the check and any rollback. Do not run enroll/verify
or import materials. The installation remains provisional until this check.

## Prepare and install

Use the same VM and private clone as R2. Password access and the desktop must
already work normally. No old managed deployment or local fprintd override
may be present. Python 3, stock fprintd, system libgusb and the Fedora
dependencies used by the successful R2 build must still be installed.

From the clone, check the branch and worktree first:

```bash
cd "$(git rev-parse --show-toplevel)"
git branch --show-current
git status --short
```

**STOP_IF:** branch is not `development`, status is non-empty, the reader is
assigned to the VM, a prerequisite is missing or any following command fails.
Do not switch branches, discard changes or disable SELinux to proceed.
When the checks are correct:

```bash
git pull --ff-only origin development
git rev-parse HEAD
sudo ./deployment/minimal-runtime/install.sh /home/guido/goodix-r2-20260922-081148
```

The normal sudo password is expected. The installer verifies VM/OS, stock
fprintd ownership and unit, SELinux, source continuity and all five saved
runtime digests before mutation. It refuses foreign local overrides and
occupied destination paths. It adds only:

- `/usr/local/lib64/goodix-27c6-5125/`: the five libraries, two libfprint links,
  license/provenance files, saved uninstall implementation and installation
  state;
- `/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf`:
  `Environment=LD_LIBRARY_PATH=/usr/local/lib64/goodix-27c6-5125` under `[Service]`.

It stops fprintd, applies normal SELinux file labels and reloads systemd. It
leaves fprintd stopped for the explicit check below. It does not replace
`ExecStart`, a Fedora file, PAM, udev rules, templates or device materials.
The previous active/inactive service state and whether the drop-in directory
already existed are saved for rollback. Temporary staging under the two
destination parents is removed on ordinary success/error.

Expected result: `R3_INSTALL=PASS`, both commit identities and
`FPRINTD=STOPPED_READY_FOR_MANUAL_LOAD_CHECK`. An identical repeated install
reports `R3_INSTALL=ALREADY_INSTALLED` without changing the saved state.

## Start the normal service and inspect its loaded libraries

Paste this block as a whole. It starts only the stock service and immediately
reads its executable and library mappings, before its normal idle exit:

```bash
(
  set -euo pipefail
  getenforce
  systemctl show fprintd.service --property=ExecStart --property=Environment
  sudo systemctl start fprintd.service
  r3_pid=$(systemctl show fprintd.service --property=MainPID --value)
  test "$r3_pid" -gt 0
  sudo readlink "/proc/$r3_pid/exe"
  sudo awk '$6 ~ /\/goodix-27c6-5125\// || $6 ~ /\/libgusb[.]so/ {print $6}' \
    "/proc/$r3_pid/maps" | sort -u
)
```

**PASS_IF:** installation and the block succeed, SELinux reports `Enforcing`,
`ExecStart` and the process executable remain `/usr/libexec/fprintd`, and the
maps contain all five private files:

```text
/usr/local/lib64/goodix-27c6-5125/libfprint-2.so.2.0.0
/usr/local/lib64/goodix-27c6-5125/libopencv_core.so.413
/usr/local/lib64/goodix-27c6-5125/libopencv_features2d.so.413
/usr/local/lib64/goodix-27c6-5125/libopencv_flann.so.413
/usr/local/lib64/goodix-27c6-5125/libopencv_imgproc.so.413
```

libgusb must map from Fedora's system library directory (`/usr/lib64/` or its
`/lib64/` alias), not the private runtime or R2 build staging. A subsequent
normal idle exit of fprintd is expected and is not a failure.

**FAIL_IF:** startup fails, a required library is missing or comes from the
wrong location, a permission denial occurs, or the executable differs.
**STOP_IF:** unexpected USB/material activity, an authentication/desktop
regression, or any error. Keep the reader disconnected and roll back after a
failure; do not change service restrictions or add a private daemon to pass.

On PASS, keep the installation and R2 build output for the next step. Do not
attach the reader yet: the stock retry/attempt boundary needs a separate
review and handoff before any sensor-reaching validation.

## Rollback after FAIL, instability, or on request

With the reader still disconnected, use the inverse saved with this install:

```bash
sudo /usr/local/lib64/goodix-27c6-5125/uninstall.sh
```

If installation failed before publishing that directory, the matching
checkout provides the same inverse:

```bash
sudo ./deployment/minimal-runtime/uninstall.sh
```

The inverse stops fprintd, removes only the recorded project drop-in, reloads
the vendor definition, restores the pre-install active/inactive state and
removes the owned runtime. It removes a drop-in directory created by this
install only when empty. It retains all unrelated files, materials and
templates. It needs neither the R2 output, Git nor a pinned Fedora package
version, so it remains available after updates. It does not repair Fedora
packages or reverse unrelated later changes.

Expected: `R3_UNINSTALL=PASS` (or `ALREADY_ABSENT` if nothing was installed).
Check removal and the vendor command:

```bash
test ! -e /usr/local/lib64/goodix-27c6-5125
test ! -e /etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf
systemctl show fprintd.service --property=ExecStart --property=Environment --property=ActiveState
```

The project environment must be absent and the vendor command unchanged.
An initially active service is restarted and may then exit normally when
idle; an initially inactive one is left stopped. On ownership/content drift
or recovery failure, the inverse refuses destructive cleanup and retains
state for review. Return its error; do not delete files manually. Hard power
loss is not a tested transaction guarantee. Rollback is not required on PASS.

## Evidence to return

Return `R3-A STOCK LOAD = PASS/FAIL`, the full install commit, the installer
result and output of the load-check block. Confirm the reader stayed
disconnected and whether installation remains in place or was rolled back.
On failure, give the exact command/stage, error and rollback result. Further
logs will be requested only if that observed failure requires them.

No protected materials, biometric data or broad log collection are needed.
The [runtime audit](../../docs/MINIMAL_RUNTIME.md) records the offline review
and the remaining sensor/update boundaries.
