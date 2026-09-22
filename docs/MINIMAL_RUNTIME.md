<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R2 runtime extraction and R3-A audit

Source baseline audited: `09ff7571c1d66e5e3e3bd1f8d89c75c733ca70c1` on
`development`, 22 September 2026. The current changes extract a build-only
path; their final identity is the Git commit containing this document.
R1 is complete. R2 source extraction/static audit is complete; the first VM
build remains required. R3-A is the first integration hypothesis, not a
validated installation. No R4/R5/R6 or release qualification is claimed.

## MINIMAL_RUNTIME_CONTENTS

| Component | Source or output | Why necessary |
| --- | --- | --- |
| Goodix libfprint | Patched Fedora base in `reference/libfprint-fedora44-1.94.100/source/`; `runtime/libfprint-2.so.2.0.0`, SONAME/development symlinks | Public libfprint ABI, device registration, asynchronous USB/TLS, image actions, SIGFM storage and matching |
| Target-specific implementation | Exact 62 paths in `production/source-files.tsv` and `.sha256`: 30 translation units, 32 headers | Transport, material loader, lifecycle, decoder, preprocessing, SIGFM; compiled into libfprint, not separate daemons |
| Four OpenCV libraries | `libopencv_{core,features2d,flann,imgproc}.so.413` | Existing SIGFM/R2 dependencies selected by `build-support/opencv4.pc.in`; extracted from the already pinned Fedora RPMs |
| Fedora libgusb | VM system `libgusb.so.2` | Existing USB backend dependency; copied only to build-time pkgconfig staging, excluded from deployable `runtime/` |
| System libraries | VM GLib/GIO/GObject, OpenSSL, libusb and other ELF dependencies | Remain distribution-owned; actual transitive resolution is recorded in `fprintd.ldd` by the VM build |
| Notices and identity | OpenCV license corpus, existing four license texts, per-file source ledger and hashes, runtime SHA256SUMS | Preserve current licensing/provenance; this internal build payload is not a public release/export |

The source audit verified all 62 existing digests and the four build-support
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

**R3-A proposed surface, not installed or approved by this audit:**

| Path | Purpose | RPM owner / override | Update class and rollback expectation |
| --- | --- | --- | --- |
| `/usr/local/lib64/goodix-27c6-5125/` | Private library payload | Project-owned new files, no Fedora replacement | C: library/ABI failure may disable fingerprint; remove/reinstall private runtime |
| `/etc/systemd/system/fprintd.service.d/<project-drop-in>.conf` | Service-local library search path only | Project-owned new drop-in; vendor unit stays owned by fprintd | C: applies only to fprintd; removal and daemon-reload restore vendor definition; installer must preserve pre-existing files/state |
| `/var/lib/goodix-5125-poc/` | Existing device-specific inputs | Preserved separately; read-only runtime use | C for missing/incompatible materials; never delete/overwrite as software rollback |
| `/var/lib/fprint/` | Stock fprintd template storage | Owned/managed by Fedora fprintd | Preserve across install/uninstall/update; format compatibility requires a separate check |

No additional udev rule is justified by current source evidence. The library
build disables rule generation. The physical workspace's Fedora vendor unit
permits USB access and its RPM-owned hwdb includes `27c6:5125`; this does not
establish the guest's udev/SELinux behavior. Do not copy those files into `/etc`.
The exact R3 surface and RPM ownership must be rechecked in the VM before
installation. This prospective table is not the completed R5 audit.

```text
HOST_FILES_TOUCHED=NONE_BY_R2_BUILD
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

Stock `reference/fprintd-fedora44-1.94.5/source/src/device.c` resubmits VERIFY
and IDENTIFY after `FP_DEVICE_RETRY`. The historical
`production/login/fprintd-consumer-retry.patch` suppresses that behavior; it
is excluded here. In the current driver, failed matching/processing poisons
the action and subsequent activation checks the poison before opening another
transport epoch. This is static evidence of a fence, not a current dynamic
regression PASS with stock fprintd. Clean outcomes permit explicit reopen;
the `login_attempts >= 3` guard belongs to the private prepared-login path,
not automatically to ordinary stock VerifyStart. The native stock workflow
must demonstrate the required three-attempt limit/stop-on-match and reject
hidden retries before any sensor-reaching test. Do not weaken the fence or
reuse the private consumer patch to get a build or live PASS.

The methodological change from the rejected Plasma retest is architectural:
remove private authentication components, first prove the library with the
stock daemon. A recurring device/bootstrap failure calls for targeted evidence
at that boundary, not another VT patch or an equivalent repeated live.

## Verification and next handoff

Source digest/path audit, shell syntax, non-VM refusal before output creation,
and the driver audit from a temporary source subset without historical auth
components are permitted offline checks. They cannot establish compilation,
ELF closure, SELinux, physical attempts, biometric success or R5 survivability.

The user explicitly retains all VM execution. Use the
[VM build handoff](../production/minimal-runtime/README.md), return its source
commit/linkage evidence, then resume R2 review and R3-A preparation. Direct AI
access to the VM is neither needed nor a blocker. The next gate is the manual
VM build, not authorization to reinstall the historical managed candidate.
