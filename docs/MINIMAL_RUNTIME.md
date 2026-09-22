<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R2 runtime extraction and R3-A audit

R2 extraction baseline: `09ff7571c1d66e5e3e3bd1f8d89c75c733ca70c1` on
`development`, 22 September 2026. R3-A deployment preparation starts from
`c5df71772b3ade7cf3d1ea2d418a65e0ab75b1f6`; its final identity is the Git
commit containing `deployment/minimal-runtime/` and this review.
R1 and R2 are complete. The user reported a successful normal build on Fedora
44 KDE x86_64/KVM at `c5df71772b3ade7cf3d1ea2d418a65e0ab75b1f6`, with the
reader disconnected. The retained VM output is
`/home/guido/goodix-r2-20260922-081148/`. Stock fprintd resolves the private
libfprint and all four OpenCV libraries, with no missing dependencies; all
five runtime checksum checks passed and the checkout stayed clean.
The reported `LIBFPRINT_2_0_0` ABI check passed; host/test-only symbols and
private-tree dependencies were zero, and no RPATH was present.
The daemon was not executed, USB/material loaders were not accessed and no
Fedora component was replaced. This is human-produced evidence reviewed
against the committed build/source path, not an AI rerun or independently
rehashing the guest's binaries. R3-A stock load is now also **PASS**, reported
by the user for install `92311c5ebe1d05a68ad0542ecb8aeafb9776db0e`: SELinux
Enforcing, stock ExecStart/process `/usr/libexec/fprintd`, five private library
mappings and `/usr/lib64/libgusb.so.2.0.10`. The reader stayed disconnected;
installation and R2 output remain in place, rollback untested in the VM.
No biometric, R4/R5/R6 or release qualification is claimed. The user now
reports PM-accepted [synthetic retry/attempt results](STOCK_FPRINTD_ATTEMPTS.md):
44/44 normal and 44/44 ASan/UBSan at `b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`.
A normal runtime build from that SHA is also reported complete/reviewed,
at `/home/guido/goodix-r3-20260922-111144`. The installed old R2 binary lacks
that correction; the next gate is clean replacement, not another build/test.
A cold VM snapshot is only an external lab fallback, not a product dependency.

## MINIMAL_RUNTIME_CONTENTS

| Component | Source or output | Why necessary |
| --- | --- | --- |
| Goodix libfprint | Patched Fedora base in `reference/libfprint-fedora44-1.94.100/source/`; `runtime/libfprint-2.so.2.0.0`, SONAME/development symlinks | Public libfprint ABI, device registration, asynchronous USB/TLS, image actions, SIGFM storage and matching |
| Target-specific implementation | Exact 62 paths in `production/source-files.tsv` and `.sha256`: 30 translation units, 32 headers | Transport, material loader, lifecycle, decoder, preprocessing, SIGFM; compiled into libfprint, not separate daemons |
| Four OpenCV libraries | `libopencv_{core,features2d,flann,imgproc}.so.413` | Existing SIGFM/R2 dependencies selected by `build-support/opencv4.pc.in`; extracted from the already pinned Fedora RPMs |
| Fedora libgusb | VM system `libgusb.so.2` | Existing USB backend dependency; copied only to build-time pkgconfig staging, excluded from deployable `runtime/` |
| System libraries | VM GLib/GIO/GObject, OpenSSL, libusb and other ELF dependencies | Remain distribution-owned; actual transitive resolution is recorded in `fprintd.ldd` by the VM build |
| Notices and identity | OpenCV license corpus, existing four license texts, per-file source ledger and hashes, runtime SHA256SUMS | Preserve current licensing/provenance; this internal build payload is not a public release/export |

The source audit verifies the 62 manifest digests and the four build-support
inputs. The new `check-source.sh --driver-only` stops before historical
fprintd/login/sudo/Polkit checks. Its default mode remains the historical full
audit. The new build reuses `build-inner.sh`'s Goodix-only Meson selection,
`GOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE` and disabled udev generation.
It does not invoke `production/build.sh`, `production/login/`, `production/sudo/`,
`production/polkit/`, `production/plasma-vt/` or `deployment/managed-install/`.
The separate source manifest covers the active build inputs only.

Excluded: custom fprintd, pam_fprintd, greeter, Plasma daemon, sudo/PolicyKit
bridges, KScreenLocker/login PAM overrides, account lifecycle hook, SELinux
hook module, persistent authselect changes and all protected device material.
The library still contains existing optional prepared-login extension code;
removing it is not part of this extraction. No custom client/daemon that calls
that extension is shipped. Its presence does not prove stock-path safety.

## Controlled material access

The existing loader reads these five direct children of
`/var/lib/goodix-5125-poc/`: `target-material-manifest.json`,
`transport-material.bin`, `target-config-90.bin`, `gfusb.dll`, `fdt-cache.bin`.
`goodix_runtime_material.c` requires a root-owned 0700 directory;
`goodix_target_material.c` and `goodix_runtime_inputs.c` use read-only,
no-follow opens, root-owned 0600 file checks, content binding and cleansing.
The build does not execute those loaders and requires no material import.
No protected contents were read for this audit.

The historical D282/D293 evidence in the canonical manual supports the
library's feasibility with the ordinary fprintd interface. It does not prove
the current source against the new VM. The actual VM execution must identify
its own source commit, dependencies and later live-critical hashes.

The Rockytkg provenance file has moved from the governance's historical path:
it was located and read at
`development/Rockytkg/snapshot/PROVENANCE.md`. Existing source provenance and
per-file terms remain in `docs/LICENSING_AND_PROVENANCE.md`; no new third-party
source is imported and the build does not depend on the private snapshot.

## HOST_FILES_TOUCHED / WHY_EACH_FILE_IS_NECESSARY

**R2 build:** only the new user-selected output directory and temporary build
staging are written. The terminal log is adjacent to output. No project file
is installed, no service is started, and no Fedora-owned file is changed.
Optional prerequisite installation in the README is manual VM package setup.

**R3-A installed surface, stock loading PASS; runtime/update qualification pending:**

| Path | Purpose | RPM owner / override | Update class and rollback expectation |
| --- | --- | --- | --- |
| `/usr/local/lib64/goodix-27c6-5125/` shared objects and two links | Private library payload | New project files, no RPM owner or Fedora replacement | C: incompatible/missing libraries can disable only the fprintd path; remove/reinstall the private runtime |
| Same directory: notices, `SHA256SUMS`, source/build provenance | Trace the five binaries and preserve license terms | New project files | D/E: integrity checks/maintenance may fail; no password runtime dependency |
| Same directory: `installation.json`, `deploy.py`, `uninstall.sh` | Remember previous service state and retain the exact inverse | New root-owned project files; state mode 0600 | D: preserve and review on drift; rollback does not require Git, build output or a Fedora version/hash pin |
| `/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf` | Service-local library search path only | New project drop-in; vendor unit remains fprintd RPM-owned | C by design: removal and daemon-reload restore the vendor definition; no ExecStart/authentication override |
| `/etc/systemd/system/fprintd.service.d/` if absent | Contain the new drop-in | Existing directory preserved, or a new project-created directory | D: remove only if created here and still empty |
| `.goodix-5125-stage-*` under `/usr/local/lib64/`, `.goodix-5125-dropin-*` under the drop-in directory | Stage owned files and publish without replacing an occupied drop-in | Temporary project files | D: removed on ordinary completion/error; abrupt power-loss recovery not qualified |

The installer never reads or modifies `/var/lib/goodix-5125-poc/` or
`/var/lib/fprint/`. The former remains the separate protected input boundary;
the latter remains stock fprintd storage. Neither is an uninstall target.
This sensor-disconnected step needs no material/template migration.

No additional udev rule is justified by current source evidence. The library
build disables rule generation. The physical workspace's Fedora vendor unit
permits USB access and its RPM-owned hwdb includes `27c6:5125`; this does not
establish the guest's udev/SELinux behavior. Do not copy those files into `/etc`.
The installer checks stock RPM integrity, unit path/ExecStart, absence of
foreign local overrides and SELinux Enforcing in the VM before mutation.
It only applies Fedora's normal file contexts with `restorecon` to its new
files. This table is an architectural audit, not the completed R5 test.

```text
HOST_FILES_TOUCHED=NONE_BY_R2_BUILD
R3_HOST_FILES_TOUCHED=PRIVATE_LIBRARY_DIRECTORY_AND_ONE_FPRINTD_ENVIRONMENT_DROPIN
FEDORA_COMPONENTS_REPLACED=NONE
EXPECTED_UPDATE_FAILURE=FINGERPRINT_ONLY   # R3 design requirement, not measured
RUNTIME_VERSION_HASH_PINS_FOR_PASSWORD_ACCESS=NONE
BUILD_INPUT_DIGEST_PINS=EXISTING_OPENCV_AND_SOURCE_PROVENANCE_ONLY
```

## R3-A feasibility and unresolved checks

Read-only observation of the physical workspace found Fedora 44 x86_64,
fprintd 1.94.5-5.fc44, libfprint 1.94.100-1.fc44, libgusb 0.4.9-5.fc44 and
OpenCV core 4.13.0-1.fc44. Its vendor unit has `ExecStart=/usr/libexec/fprintd`
and its daemon needs `libfprint-2.so.2`. These are local corroboration, not a
substitute for guest evidence. R3-A can therefore be investigated first:

```ini
[Service]
Environment=LD_LIBRARY_PATH=/usr/local/lib64/goodix-27c6-5125
```

No ExecStart replacement, wrapper or daemon fork is selected. R3-B/C remain
unselected; failure of R3-A must be supported by evidence before changing it.
The library loaders already enforce material checks, so the old wrapper is
not automatically needed merely to validate those inputs.

Before an R3 live handoff, verify the VM's stock daemon ABI/linkage, vendor
unit restrictions, SELinux access, missing-library failure containment,
install/remove symmetry and actual library mappings. Preserve the vendor
ExecStart and stock authentication files. A normal update must not require a
frozen package version to keep password/desktop/sudo/PolicyKit available.

The completed first R3 handoff was limited to installation and the normal
stock-daemon start **without the sensor**. It tests actual mappings and
SELinux/service load restrictions using the successful R2 binaries. It does
not claim to close sensor access, material access, retry behavior or update
survivability. A failed stock startup calls for its exact error and targeted
diagnosis; do not repeat the already successful build or select R3-B/C without
evidence that the environment-only approach is insufficient.

`deployment/minimal-runtime/install.sh` and `uninstall.sh` share a small
standard-library filesystem transaction. The install uses no version-pinned
Fedora payload and copies only the allowlisted five-library payload. The
accepted build SHA and unchanged build-critical source comparison bind this handoff to the
retained binaries; they are installation provenance, not a runtime prerequisite
for password access. Documentation-only changes do not invalidate that build.
The installed inverse has no Git/OS-release/RPM-version prerequisite.

The transaction refuses a non-VM before host actions, verifies runtime digests,
source continuity and destination ownership, preserves existing files and retains an
exact saved inverse. It records service state, stops fprintd, publishes the
runtime and environment drop-in, then leaves fprintd stopped for the user's
explicit start. On ordinary deployment failure it reverses owned changes;
on a foreign collision/content drift or recovery failure it retains evidence
and reports the error rather than guessing ownership. Rollback removes the
project environment before restoring the prior service state. No udev rule,
SELinux policy module, D-Bus policy, PAM file or system executable is changed.

**Update failure reasoning:** the only loader change is scoped to fprintd,
whose executable/unit remain RPM-managed. Loss of ABI/dependencies can stop
fingerprint service, but no new project dependency is inserted in password,
desktop, sudo or PolicyKit. No A/B element is identified in this footprint;
this is a static conclusion, pending the mandatory R5 real-update checks.
Existing distro consumer failure handling must still be exercised, not assumed
from a successful library load. No release qualification follows from R3 alone.

Stock `reference/fprintd-fedora44-1.94.5/source/src/device.c` resubmits VERIFY
and IDENTIFY after `FP_DEVICE_RETRY`. The historical
`production/login/fprintd-consumer-retry.patch` suppresses that behavior; it
is excluded here. In the current driver, failed matching/processing poisons
the action and subsequent activation checks the poison before opening another
transport epoch. This is static evidence of a fence, not a current dynamic
regression PASS with stock fprintd. Clean outcomes permit explicit reopen;
the `login_attempts >= 3` guard belongs to the private prepared-login path,
not to ordinary stock VerifyStart. Per the user's explicit decision, the
current R3 correction removes the cumulative cap introduced in `c0b2369`.
Clean NO_MATCH with cleanup admits further explicit attempts chosen by the
stock consumer; the counter is telemetry only. MATCH/error remains terminal
for that Claim. Synthetic evidence now passes 44/44 in both modes as reported
by the user; see `STOCK_FPRINTD_ATTEMPTS.md`. This does not establish real sensor behavior.
The native stock workflow must preserve terminal-outcome fencing, cleanup
and zero implicit sensor-reaching retries before any sensor test. Do not
weaken the fence or reuse the private consumer patch to get a build or live PASS.

The methodological change from the rejected Plasma retest is architectural:
remove private authentication components, first prove the library with the
stock daemon. A recurring device/bootstrap failure calls for targeted evidence
at that boundary, not another VT patch or an equivalent repeated live.

## Verification and next handoff

Source digest/path audit, shell syntax, non-VM refusal before output creation,
and the driver audit from a temporary source subset without historical auth
components passed during R2 preparation. The subsequent human VM evidence
closes compilation and ELF linkage for the reported source. It does not
establish SELinux execution, physical attempts,
biometric success or R5 survivability.

The user explicitly retains all VM execution. R2 review is
`ACCEPT_AND_CONTINUE`: preserve the existing build; do not repeat it. R3-A
original install/load evidence is also `ACCEPT_AND_CONTINUE`; its removal
is now explicitly requested for the clean replacement below.
Direct AI access to the VM is neither needed nor a
blocker. The previous [build procedure](../production/minimal-runtime/README.md)
remains reproducible reference, not the next task.

R3-A preparation verification: 17 temporary-filesystem/input tests cover symmetric
removal, active/inactive restoration, idempotence, checksum and ownership
drift, collision preservation, failed reload and failed vendor restart with
the inverse retained. All host-command/device interfaces are test doubles;
no service, library or USB execution is claimed. The real install entry point
also refuses this physical host from an unrelated cwd before mutation. Both
shell wrappers pass syntax checks; the driver-only source audit remains PASS.

The current **HUMAN_REQUIRED** is the
[clean replacement procedure](../deployment/minimal-runtime/README.md).
The only deployment logic delta is the accepted normal build SHA, now
`b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`, plus its rejection message.
Source continuity and all existing guards remain. The user must first run the
old inverse saved under the installed runtime, verify stock files/environment,
then install the qualified build and leave fprintd stopped for review before
load-check. The new uninstaller rejects old metadata; no multi-version
compatibility or in-place update is introduced. The footprint table is unchanged.
The new saved inverse returns to Fedora stock without Git/build/snapshot.

Current offline deployment verification: **27 tests PASS**, including exact
build/mode and payload rejection, old metadata preservation, critical-source
drift, clean checkout, five-library set, saved inverse executed from its copy
with no checkout/build access, vendor/material sentinels and reader-absence
gates. Existing transaction/service/collision tests remain. Host interfaces
are mocked and filesystem writes remain temporary; no VM, root, service or USB
operation was performed by the AI. Wrapper/documented-command syntax and
non-VM refusal also pass. The manual VM clean replacement and the later new
runtime load-check are still pending; synthetic PASS is not release closure.
