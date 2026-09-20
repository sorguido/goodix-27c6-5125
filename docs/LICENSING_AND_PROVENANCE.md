<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Licensing and provenance

Licensing is per file. No directory name changes the license or copyright of
the source it contains.

## Distributed components

| Component | Origin | Version or commit | License | Local use |
| --- | --- | --- | --- | --- |
| libfprint base | Fedora 44 source package / upstream libfprint | 1.94.100 | Per-file upstream terms, predominantly `LGPL-2.1-or-later` | Patched base and public ABI |
| Goodix driver sources | This project | current source tree | Per-file SPDX; predominantly `LGPL-2.1-or-later` | USB, TLS, image, lifecycle, enrollment, and matching integration |
| SIGFM | Rockytkg materialized libfprint fork | `7ebe0c809b4d1df3400e84299a4ec4acdea84590` | `LGPL-2.1-or-later` | Feature extraction and matching |
| R2 preprocessing | Adapted from Rockytkg `goodix_imgproc` | `227eba219fa9e3fbac5bd59aca79f624f67cd11b` | `GPL-2.0-or-later` | Image preprocessing |
| OpenCV | Fedora 44 packages | 4.13.0-1.fc44 | Fedora expression `BSD-3-Clause AND Apache-2.0 AND ISC` | Bundled runtime libraries |
| libgusb | Fedora 44 package | 0.4.9-5.fc44 | `LGPL-2.1-or-later` | Bundled runtime library |
| OpenSSL | Fedora 44 system library | host version | Apache-2.0 | TLS implementation |

The exact target-specific compilation units, licenses, origins, and SHA-256
digests are recorded in `production/source-files.tsv` and
`production/source-files.sha256`. The Fedora base provenance and source-package
digests are recorded in
`reference/libfprint-fedora44-1.94.100/PROVENANCE.md`.

Device-material acquisition, extraction, recovery and generation helpers are
not part of the distributed release surface. The runtime expects protected
material supplied separately by the user and the project does not distribute
OEM binaries, secrets, caches or captures.

## Combined binary

The Goodix-enabled `libfprint-2.so.2.0.0` statically incorporates the GPL R2
component and dynamically links Apache-2.0 components. The applicable “or
later” grants permit the combined binary to be conveyed under
`GPL-3.0-or-later`. This does not relicense individual files: every source file
retains its own notice and grant.

The prepared candidate includes the GPL-2.0-or-later,
LGPL-2.1-or-later, GPL-3.0-or-later, and Apache-2.0 license texts, the exact
OpenCV license corpus extracted from the pinned RPMs, third-party notices, and
an SPDX 2.3 JSON SBOM.

## Imported source details

The four SIGFM files in `Rockytkg/libfprint/libfprint/sigfm/` originate from
the Rockytkg materialized libfprint fork commit above. Their original notices
name Matthieu Charette, Natasha England-Elbro, Timur Mangliev, and other
contributors represented in the files.

`libfprint-driver/rockytkg-imgproc/goodix_imgproc.[ch]` is an adapted,
device-independent preprocessing subset of Rockytkg's
`src/goodix_imgproc.c` and `include/goodix_imgproc.h` at commit
`227eba219fa9e3fbac5bd59aca79f624f67cd11b`. Sensor-reaching code, firmware,
environment overrides, and debug dumps are not included.

The libfprint integration forward-ports SIGFM print semantics and bounded image
actions onto Fedora's newer libfprint 1.94.100 core. These are downstream
changes, not upstream libfprint or Fedora behavior.

## Excluded material

No open-source grant in this repository covers OEM firmware or binaries,
device secrets, private captures, fingerprint images or templates, factory
data, or other protected material. None of those items belongs in the public
source tree or candidate.

This project records its compatibility determination and source provenance; it
does not provide legal advice for unrelated distributions or modifications.

## Canonical early-login integration

`reference/fprintd-fedora44-1.94.5/source/` is the immutable upstream GPL-2.0-or-later
source corresponding to Fedora fprintd 1.94.5-5.fc44. Source RPM/tar/spec hashes
are in its `PROVENANCE.md`; `SOURCE_SHA256SUMS` covers all 141 retained upstream files, including dotfiles (eight biometric test images
are excluded). Three reference metadata files outside `source/` are not part
of that upstream count.
`production/login/fprintd.patch` is the original downstream delta,
mechanically promoted byte-for-byte from the live-tested prototype. The
separate `fprintd-cleanup.patch` adds a GPL-2.0-or-later guard for a reproduced
pending-open/suspend race; it preserves the successful preparation/attach path. Upstream
`src/device.c`, `src/manager.c`, `src/fprintd.h`, Device XML and
`pam/pam_fprintd.c` retain their original notices and grants. The new private
login include, GIO greeter, build scripts and daemon/greeter tests are
GPL-2.0-or-later. Driver changes and promoted synthetic driver tests retain
LGPL-2.1-or-later per-file terms.

The daemon paired with the GPL-3.0-or-later libfprint combined work is conveyed
under the compatible later grant; the PAM and greeter source retain GPL-2.0-or-later.
The candidate includes upstream `fprintd-COPYING`, `fprintd-AUTHORS`, existing
license texts/notices, source digest manifests and an expanded SPDX SBOM.
PAM/polkit devel RPMs are hash-pinned compile-time inputs only, not runtime
payload. No Plasma source is imported or relicensed.

Historical `development/patches/login-early/` is frozen evidence of the physical
validation at `9671e02e19504e20e0097f598fa960f2c13e7a1e`, not a build dependency.
The canonical loader and per-reader material contract are retained. Promotion
does not change the public export/audit boundary or publish private history.

Prepared-login three-attempt follow-up: `production/login/fprintd-attempts.patch`
is a GPL-2.0-or-later local delta over the two existing patches. Upstream bytes
and the original prototype patch/greeter remain unchanged. Modified driver
and lifecycle sources retain LGPL-2.1-or-later notices. Their current digests
are in the production source manifest; they no longer claim prototype byte
equivalence. No new external implementation or licensing boundary is introduced.

## Service-local Polkit bridge (20 September 2026)

New `production/polkit/pam_goodix_polkit.c`, build, deployment and offline tests:
independent project implementation, GPL-2.0-or-later, no third-party code copied
or minimally adapted. Public PAM/stdio/process APIs only; existing Fedora
pam_fprintd remains separately installed and unmodified. Source inspection of
Polkit 127, Linux-PAM 1.7.2 and the exact Fedora KDE source RPM is documented in
`production/polkit/README.md`; it is behavioral reference, not imported source.
The managed SBOM identifies the bridge separately and records host Polkit/KDE/PAM
dependencies. The existing combined libfprint licensing boundary is unchanged.

## Combined sudo/Polkit boundary (20 September 2026)

New `production/sudo/` source, build, rules and offline tests are independent
project GPL-2.0-or-later code; the sudo bridge reuses project-owned child/PAM
patterns from the Polkit bridge with a separate native-conversation design.
No sudo, KDE or Linux-PAM expression is incorporated. Exact Fedora sudo/PAM
SRPM versions, source digests and reviewed functions are recorded in
`production/sudo/README.md`. They are reference evidence, not shipped payload.
`production/login/fprintd-consumer-retry.patch` changes the already pinned
fprintd `src/device.c` retry condition for ordinary Verify/Identify; existing
GPL-2.0-or-later copyright/license and combined GPL-3.0-or-later boundary remain.
SBOM adds the sudo bridge and records the host sudo dependency. Firmware,
protected material and biometric templates are not part of these artifacts.

## Private host migration inventory (20 September 2026)

`development/migration/patched-host-to-combined/inventory.py` and its offline
tests are independent project code, GPL-2.0-or-later. They use only Python's
standard library and do not copy historical deployment implementations.
Historical scripts are reviewed as ownership evidence through Git; no external
code is imported. This host-specific development handoff is not candidate
payload and changes no distribution or licensing boundary.

The follow-up `check-material-boundary.sh` is independent project
GPL-2.0-or-later code; `test_material_boundary.c` is independent
LGPL-2.1-or-later test code linked only with the existing target-material
loader/binder. It consumes the already versioned private D232 non-secret
analysis manifest, whose provenance document excludes PSK/raw OTP/CONFIG90
and biometric content. It neither reads the installed protected bundle nor
copies that fixture into the candidate/public source set. No production
source or material contract is changed by this offline evidence test.

The manifest conversion and fixed host transaction (`manifest.py`, `migration.py`,
`install.sh`, `uninstall.sh`, `prepare-policy.sh`, and `test_migration.py`) are
independent GPL-2.0-or-later project code, standard-library-only. The private
`host-plan.json` contains allowed software hashes and metadata, not binary or
biometric contents. The conversion projects the already versioned D232 metadata;
two absent digest fields use the existing C acceptance pins at commit
`e61fce313794922a2dab156a1b38a8ddc5837f19`, paths
`libfprint-driver/goodix_target_material.c` and `goodix_runtime_inputs.c`.
It does not derive new secrets, change the canonical loader or redistribute
protected files. Full historical manifest remains recoverable on the host only.

Recovery policy reconstruction consumes this project's historical
`deployment/d293-phase-b-account-lifecycle/goodix_fprint_account_delete.te`
and `.fc` at `232e9401ca3ce72a0f9f08448deb46c6251aaa2a`, unchanged; existing
GPL-2.0-or-later project licensing and attribution remain. Source hashes and
reproduced PP/CIL hashes are pinned by `prepare-policy.sh`. No external code,
new permanent dependency or candidate licensing boundary is introduced.
These development-only tools, host plan and historical fixture are excluded
from the canonical candidate payload; public repository remains untouched.

The follow-up `launcher.py`, `operator.sh`, `recovery.py`, and launcher tests
are independent GPL-2.0-or-later project code. The saved recovery manager is
mechanically derived from the same checkout's GPL-2.0-or-later
`deployment/managed-install/root-transaction.sh`: only the unused Git-root
lookup is removed and dispatch is restricted to uninstall for the known local
installer. `production/polkit/deploy.py` and `production/sudo/rules.py` are
copied unchanged into the private recovery snapshot, retaining SPDX notices.
Exact saved-source hashes are recorded in transaction state. No production
source or license boundary changes. The Fedora systemd vendor drop-in is
preserved on the host and its package digest is recorded; it is not copied
into the candidate. No protected or biometric contents enter this tooling.

The package metadata/re-arm corrective adds independent GPL-2.0-or-later
`package_baseline.py`, `rearm.py` and offline tests. `legacy-recovery.json`
contains only source hashes from private commit
`f97de44e0192f249ccb80fd9b32e1488195f0101`, including the previously documented
removal-only manager adapter. It authenticates saved code before import, without
reading protected material or importing new third-party expression. The RPM
verification test uses the already installed Fedora librpm Python binding and
an in-memory copy of package metadata; no RPM database or package is changed.
No production, license, redistribution or public-repository boundary changes.
