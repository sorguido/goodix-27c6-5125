<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R3 Gate A: persistent material labels, sensor disconnected

**HUMAN_REQUIRED — apply project-owned fprintd_var_lib_t material mapping in VM.**
Gate B (one live enumeration/Claim/Release) is blocked until the user returns
Gate A evidence and a separate review/approval permits it. Do not run the live
procedure, start fprintd or reconnect the sensor during this gate.

## Evidence and implementation review

The user reports one Goodix enumerated, then `R3_OPEN_CLOSE=FAIL STAGE=CLAIM`
with `net.reactivated.Fprint.Error.Internal`. No retry; sensor detached,
fprintd inactive/MainPID 0, qualified runtime preserved. The same-window AVC
is a read denial from `fprintd_t` to `target-material-manifest.json` labeled
`var_lib_t`. Directory root:root 0700 and all five files root:root 0600 were
correct. This is accepted human VM evidence, not an AI reproduction.

Source review: stock Claim → fp_device_open → img_open →
default_acquire_runtime_material → goodix_runtime_material_load →
goodix_target_material_load → O_RDONLY manifest open denied. In
`goodix_fpimage_device.c`, material loading precedes interface claim. Thus
`USB_INTERFACE_CLAIM_REACHED=false`, `BIOMETRIC_ACTIVATION_REACHED=false`,
`PRODUCTION_DRIVER_ROOT_CAUSE=false`. Generic GUsb enumeration/open has already
occurred; this is not a claim that there was no USB access at all. The
unrelated OpenCV `nr_hugepages` AVC is outside this corrective.

Before implementation, read-only inspection of the physical Fedora policy
(`selinux-policy-targeted-44.9-1.fc44`, policy.35, via installed Python
setools) confirmed `fprintd_var_lib_t`, fprintd_t dir read/open/search and file
read/open/manage permissions. Vendor file_contexts maps
`/var/lib/fprint(/.*)?` to that type, not the project directory. This corroborates
the user-supplied VM policy evidence; the physical host's historical six local
rules are not imported into the VM. Non-root semanage listing could not access
the local store; its installed implementation was read to verify the listing
format, including local equivalences. No host policy/labels were changed.

```text
DOES_THIS_CHANGE_INCREASE_DISTRO_COUPLING? NO
CAN_A_NORMAL_UPDATE_BREAK_MORE_THAN_FINGERPRINT? NO (static boundary assessment)
DOES_IT_TOUCH_A_FEDORA_OWNED_AUTH_COMPONENT? NO
IS_REINSTALL_DRIVER_SUFFICIENT_RECOVERY? YES (remove/reinstall or update Goodix integration)
```

This reuses the existing Fedora storage type, without changing its allow
rules, modules, daemon, unit, PAM or KDE. The local fcontext is project-owned
configuration managed through Fedora tooling, not an edit of vendor policy.
An incompatible future policy can break fingerprint or installer checks
(classes C/D/E); no new dependency enters password/desktop/sudo/PolicyKit.
Recovery may need an updated Goodix integration if the Fedora contract changes;
R5 update validation remains required. No release qualification is claimed.
The standard type permits more than reading. Production loaders remain
O_RDONLY with no material write path; this correction does not claim a
SELinux read-only sandbox or introduce a custom type/module.

**Method review after failure:** the actual change is a persistent fcontext
mapping for the existing material path. The new hypothesis is that the standard
fprintd storage label resolves the observed manifest denial. Gate A checks
mapping/labels only; it does not test Claim. If the later separately approved
Gate B fails at the same point, stop without retry, inspect the exact new AVC
and runtime provenance, and revise that diagnosis before another live run.

## Deployment and inverse

`deploy.py label-material` is the narrow corrective for the installed qualified
R3 build `b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`, install
`264cd7ff1ba77857e1985502f299e4375f9a0516`. It validates the installed footprint
and hashes, checks clean development, VM/Fedora/stock unit, Enforcing and
inactive/MainPID 0, and requires the reader absent. It updates only the saved
`deploy.py` and `installation.json` plus SELinux configuration/labels; shared
objects, symlinks, drop-in, notices, original build/install identities and
material contents stay unchanged. The old saved inverse is accepted by its
known digest; this is not a general runtime upgrade. `material_label_commit`
records the corrective independently from the installed binary provenance.
Normal future clean `install.sh` also applies this mapping before reporting PASS;
normal `uninstall.sh` runs its inverse before removing the runtime.

The required tools are semanage, restorecon and matchpathcon. If unavailable,
STOP and report the missing tool; do not install packages as part of this gate.
The installer reads **local custom rules** via `semanage fcontext -l -C -n`:

- No overlapping local rule: create exactly
  `/var/lib/goodix-5125-poc(/.*)?`, all file kinds, fprintd_var_lib_t/s0;
  record ownership only after successful creation.
- That exact compatible local rule already exists: use it, record unowned,
  and never delete it in rollback/uninstall.
- Conflicting exact/covering rule, equivalence, or uncertain regex coverage:
  STOP before changes. Regex checking is conservative; complex unrelated
  expressions may require review. No overwrite, delete-all or rule adoption.

Only the directory and five direct expected regular files are relabeled with
non-recursive `restorecon -F -- <six explicit paths>`. Symlinks, hard-linked
inputs, extra directory entries and wrong owner/mode are rejected. Inode,
size, mtime, owner and mode are checked before/after, and effective SELinux
xattrs must equal `system_u:object_r:fprintd_var_lib_t:s0`. No material content
is read, printed, hashed, copied, moved or regenerated for this operation.

The saved inverse has no Git/build dependency. Owned rule removal deletes
only the exact local entry, verifies absence, obtains current Fedora default
contexts and restorecons those same six paths. A pre-existing rule and its
labels remain. Rule/context/metadata drift stops with the runtime and inverse
preserved. Known partial apply/remove results are recorded for rollback;
ambiguous creation is retained for review and is never assumed owned. A hard
power loss between saved inverse/state replacements remains unqualified: stop
on any mismatch and keep both files; never delete state to bypass validation.
Do not run simultaneous SELinux administration or modify material metadata.

## Manual VM Gate A

Use the existing VM clone, sensor detached/not passed through. No rebuild,
reinstall, load-check or snapshot restoration. Expected sudo password access
is only for metadata/rule inspection and this label correction. The retained
build output `/home/guido/goodix-r3-20260922-111144` is not needed.

First set `r3_label_commit` to the **full commit SHA in the handoff**, then
paste this block from inside the VM clone. The SHA identifies provenance;
there is no extra authorization file/token. Any failed command means STOP.

```bash
(
  set -euo pipefail
  : "${r3_label_commit:?Set to the full commit SHA supplied in the handoff}"
  cd "$(git rev-parse --show-toplevel)"
  test "$(git branch --show-current)" = development
  test -z "$(git status --porcelain)"
  git pull --ff-only origin development
  test "$(git rev-parse HEAD)" = "$r3_label_commit"
  systemd-detect-virt --vm
  test "$(getenforce)" = Enforcing
  test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
  test "$(systemctl show fprintd.service -p MainPID --value)" = 0
  # Each deployment action independently refuses a present Goodix reader.
  sudo python3 -B deployment/minimal-runtime/deploy.py material-status
  sudo python3 -B deployment/minimal-runtime/deploy.py label-material
  sudo python3 -B deployment/minimal-runtime/deploy.py material-status
  test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
  test "$(systemctl show fprintd.service -p MainPID --value)" = 0
  test -z "$(git status --porcelain)"
  echo R3_LABEL_GATE_A=PASS SENSOR_CONNECTED=false FPRINTD=inactive MAINPID=0
  echo RUNTIME_BINARY_CHANGED=false GATE_B=NOT_EXECUTED
)
```

**PASS_IF:** before-state printed, mapping absent or exact-compatible,
`R3_MATERIAL_LABEL=PASS` (or validated ALREADY_APPLIED), ownership and full label
commit reported, all six effective contexts fprintd_var_lib_t, unchanged
root:root 0700/0600, service inactive/MainPID 0, sensor absent, clean checkout.
Keep the correction and qualified runtime in place. **STOP here for PM review.**

**FAIL_IF / STOP_IF:** any error, missing tool, foreign/ambiguous rule, context
or metadata drift, changed library/inverse, unexpected service state or
sensor present. Keep the sensor disconnected. Do not retry labeling/live or
repair rules manually. Return the exact error and point of failure. If fprintd
became active unexpectedly, use `sudo systemctl stop fprintd.service`, then
report it; do not start it as a diagnostic.

### Label-only rollback after failure or explicit request

This leaves the qualified runtime installed. Use the **updated saved inverse**:

```bash
sudo python3 -B /usr/local/lib64/goodix-27c6-5125/deploy.py unlabel-material
```

It requires inactive/MainPID 0 and no sensor, restores default labels only
when this install owned the rule, preserves all material files, and prints
`R3_MATERIAL_ROLLBACK=PASS RUNTIME_PRESERVED=true` plus labels/local-rule status.
If it reports ambiguous creation, drift or an unavailable inverse, STOP for
review; do not remove SELinux rules or installed files manually. If preflight
failed before any change, no rollback is needed. On PASS rollback is not needed.
The new inverse/ownership history stays saved after label rollback; this is
necessary for auditing and later complete uninstall.

Full runtime removal remains available through the updated saved
`/usr/local/lib64/goodix-27c6-5125/uninstall.sh`, independently of Git/build,
but is not the action for this gate. It includes owned mapping removal and
then the existing symmetric runtime/drop-in cleanup/service-state restore.

## Evidence to return

Return full commit, both material-status outputs, label result/OWNED,
final gate markers, and confirmation SELinux Enforcing, sensor disconnected,
runtime retained, no fprintd start or live retry. On failure return exact
command/error and label rollback result if attempted. No protected contents,
broad logs or new audit capture are requested. Gate A PASS establishes labels
only; it is not a successful open/close or proof of material readability by a
running fprintd. Gate B needs later separate approval.

Offline checks use temporary synthetic files and mocked SELinux commands/xattrs:
`python3 -B deployment/minimal-runtime/test_material_labels.py`, the existing
`test_offline.py` and `test_r3_open_close.py`. No AI VM/root, live SELinux
mutation, USB, service execution or production build is performed.

Offline result: **27 deployment + 20 SELinux lifecycle + 12 open/close = 59 PASS**.
Driver-only digest audit PASS; Python/shell syntax PASS; the actual labeling
entrypoint refuses the physical host before mutation. VM Gate A remains pending.
