<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Validation scope and known limitations

Version **3.1.1** adds the Diagnostic Center. Its [offline diagnostic evidence](DIAGNOSTICS_VALIDATION.md) covers synthetic software and GUI contracts. The replacement candidate requires fresh maintainer testing; release preparation and build/signature verification are separate from live acceptance. See the [3.1.1 release notes](RELEASE_NOTES_3.1.1.md).

## Operator observations on the previous 3.1.1 candidate

The maintainer reports successful installation, fingerprint enrollment and
verification, sudo and cold login with **3.1.1-2.fc44** on one clean Fedora 45 KDE
VM using a Goodix USB `27c6:5125`. These are operator observations, not tests
performed by Codex, and do not qualify the replacement package, other machines,
firmware revisions or additional authentication/recovery scenarios.

That candidate also exposed an unreadable service configuration directory,
reader tests that could not start a fresh session, difficult custom time input,
unfocused event reports and a request to improve Home sizing. The Home screenshot
showed the older 3.0.1 interface; measurements of the actual 3.1.1 layout are
required. The corrected candidate needs a new Fedora 45 check of these flows.
An inactive on-demand service is not itself a failure, and partial sign-in
configuration checks remain partial regardless of successful login observations.

The current installer correction makes its verified service configuration
directory readable during normal driver installation/update, including an
existing restricted directory. Offline fixtures cover new, 0700 and 0755
directories, preserved drop-in files and rejection of unsafe paths. The real
3.0.1 → 3.1.1 **Apply Update** path still requires maintainer testing on Fedora 45.
An RPM-only Manager update does not run this correction; a runtime already at
3.1.1 may not offer Update. No forced update, separate repair action or additional
live qualification is implied.

The [3.0.1 validation record](VALIDATION_3.0.1.md) separately tracks historical
packaging checks, operator-reported Fedora 44/45 tests and remaining limits.
The observations below concern earlier versions unless explicitly stated.

## Tested configuration

Initial operator-supervised functional testing concerns one Goodix USB
`27c6:5125` reader, Fedora 44 KDE x86_64 with SELinux Enforcing and local
accounts, using stock fprintd, PAM and KDE authentication consumers. The
reader was passed through to a Fedora VM and also used with a Windows VM.
Software installation and removal were separately exercised on an isolated
Fedora VM without reader access.

The full source-based CLI installation/recovery observations must be distinguished
from the newer RPM/Manager path. The operator reports that a signed local RPM
installed successfully through Discover, that the Goodix icon appeared in KDE,
and that ordinary driver removal through Goodix Manager succeeded (PASS).
Screenshots additionally show recognition of an installed SIGFM 2.2.1 driver
with an upgrade offered, and subsequently a 3.0.0 driver status. Those screens
alone do not establish a complete, recorded 2.x -> 3.0.0 migration sequence,
a post-upgrade reboot/login, or byte-for-byte preservation of populated pairing
state and templates. Interactive migration/rollback and the complete RPM
lifecycle remain separate qualification checks. For 3.0.1 the operator reports
Fedora 45 installation and fingerprint login, screen lock and sudo working;
a Fedora 44 installation with existing 3.0.0 enrollments updated to 3.0.1 and
then upgraded to Fedora 45 successfully; and direct 3.0.1 installation on an
initially clean Fedora 44 VM passing its functional checks. These reports do
not independently qualify the final packaging revision or establish a physical
audit of templates or PSK. The 3.0.1 package removes the `system-release(44)`
dependency and accepts Fedora 44+ x86_64 while preserving runtime and security
checks. Future Fedora versions still require compatible system components.

The maintainer considers the 3.0.0 biometric driver qualified. Driver acceptance,
historical CLI recognition, and RPM/Manager migration remain distinct evidence
categories. Synthetic tests cover recognized 2.2.1 -> 3.0.0 transitions,
historical ChicagoHS CLI receipts, and a fictional GitHub 3.0.1 release/local
update. These are software-contract results, not a published 3.0.1 release
or a populated-device migration with independently recorded preservation and
rollback. An additional 3.0.1 VM run is not required to run those synthetic
checks, but operator VM qualification of the real 2.x migration remains open.

These results supplement offline build and biometric corpus checks. They
do not establish FAR/FRR, liveness, multi-reader compatibility or exhaustive
fault tolerance. Firmware APP12508 is recognized by the software but has not
undergone this reader's full biometric qualification.

## Functional qualification and remaining limits

| Area | Offline verification | Initial live functional observation | Remaining qualification |
| --- | --- | --- | --- |
| Native backend | Pinned original ChicagoHS C sources; calibration, features, twelve-stage enrollment, Type 24 templates, verify and identify | KDE enrollment complete using native no-finger calibration; registered finger MATCH; different finger NO_MATCH | Exact physical equivalence of USB FDT_B0 and SPI T0/ImageBase, repeated reliability |
| Sensor binding | CRC-checked A6 OTP source; opaque 16-byte identity and full OTP SHA-256 envelope; malformed/mismatch rejection | Enrollment, reboot and limited Windows/Linux switching operated on one reader | Cross-device uniqueness, stability across more units and failure histories |
| Templates and users | Backend identity separation; stock fprintd per-user galleries; historical files preserved by recovery | One local user/finger was enrolled and verified after reboot | Multiple real users/fingers, corrupted gallery live paths, partial-input behavior |
| USB/TLS and pairing | Existing APP12509/APP12508 transport contracts and offline error/cleanup tests | First-use enrollment from empty host pairing state, reboot and bounded Windows/Linux ping-pong passed as reported by operator | Review live audit for E0/readback/TLS invariants; fault/recovery/timeout and APP12508 ChicagoHS |
| Installer | Canonical source build and payload validation; simulated install/update/reinstall/rollback, including SIGFM receipt migration | FIRST_INSTALL, UPDATE, reinstall, source identity and SELinux Enforcing verified in clean Fedora VM via CLI | Real 2.x -> 3.0.0 RPM/Manager migration with populated pairing/templates, failed update and rollback |
| Signed RPM / Goodix Manager | Offline packaging/signature checks and synthetic future-release continuity | Operator reports local Discover install PASS, installed KDE icon, 2.2.1 detection and upgrade offer, later 3.0.0 status | Complete interactive RPM migration and subsequent password/reboot verification, with protected-state comparison |
| Removal | Simulated normal and emergency removal, damaged/missing receipts, state/template preservation | CLI normal remove/TTY recovery with password and vendor fprintd restored; operator additionally reports ordinary Goodix Manager **Remove PASS** | Real damaged-install recovery; byte-for-byte before/after comparison of preexisting templates/host state |
| Desktop integration | PAM selector and stock fprintd ABI/dependency checks | KScreenLocker, sudo, PolicyKit, Plasma Login, reboot login, three failed fingerprint attempts then password fallback PASS | Broader policy/system versions and repeated cold-start latency/reliability |

The existing private CH0 corpus established 35/35 admissions, twelve enrollment
stages in twenty contacts, three genuine matches, three impostor non-matches and
two partial non-matches with the original pinned backend. That small offline set
is neither an FAR/FRR estimate nor liveness or live-device qualification. The
public tree contains no real corpus, biometric template, sensorID, OTP or PSK fixture;
public unit tests use synthetic data.

The runtime obtains the opaque 16-byte upstream identity from CRC-checked A6
OTP and also binds the print envelope to the full OTP SHA-256. This is not a
claim that a sixteen-byte prefix alone proves physical uniqueness. Missing,
invalid or mismatched binding fails closed; no synthetic sensorID, Windows file,
alternate matcher or diagnostic-only flag is accepted in production.
The table distinguishes reported operator observations from software-only
contracts. A successful initial live path is not a general accuracy or
fail-closed recovery qualification. The 3.0.0 architecture retains Fedora's
stock fprintd/PAM/KDE consumers and the same project-owned Plasma Login PAM
selector and fprintd systemd library drop-in used in 2.x. It replaces the
private SIGFM/OpenCV matcher with ChicagoHS and removes the previous SELinux
huge-page `dontaudit` module. Restored SELinux audit visibility does not
prove absence of all AVCs. No measured improvement in cold-login behavior is
claimed.

## Known limitations: KDE Discover and local RPMs

On Fedora 44 KDE with Discover 6.7.5, opening a **local RPM**
displayed a generic `applications-other` icon and "Unknown author" rather
than the embedded Goodix icon and `Guido Sorarù` developer information.
The installed KDE application menu and Goodix Manager use the correct icon;
the package's desktop/AppStream metadata are present.

This is a known difference between Discover's local-package
`LocalFilePKResource`/`PackageKitResource` and the usual
`AppPackageKitResource` path for AppStream metadata. See the upstream
[local-file resource](https://github.com/KDE/discover/blob/v6.7.5/libdiscover/backends/PackageKitBackend/LocalFilePKResource.cpp),
[package resource](https://github.com/KDE/discover/blob/v6.7.5/libdiscover/backends/PackageKitBackend/PackageKitResource.h)
and [AppStream resource](https://github.com/KDE/discover/blob/v6.7.5/libdiscover/backends/PackageKitBackend/AppPackageKitResource.cpp).
Changing publisher fields inside the RPM does not fix this specific
local-file view; signature verification is an independent trust check.

On the tested KDE system, the menu **Uninstall** action for the locally
installed RPM opened an AppStream link that Discover could not resolve.
To remove the Manager RPM alone, use `sudo dnf remove goodix-manager`.
That command does **not** remove an activated driver. Use **Remove** inside
Goodix Manager, or `goodix-uninstall`, for normal driver removal; the
operator reports ordinary Manager removal **PASS**. Neither observation
qualifies damaged-state removal or rollback.

The Manager uses the KDE system light/dark palette rather than a separate
theme selector. Automated Qt palette tests passed; actual behavior depends
on the platform delivering system palette changes.

## Offline evidence and reproducible checks

From a complete source tree, the public tests use no hardware:

```text
python3 -B production/test_build_public.py
python3 -B deployment/test_install.py
python3 -B deployment/test_install_selection.py
python3 -B deployment/test_bootstrap.py
python3 -B deployment/recovery/test_remove.py
python3 -B packaging/rpm/test_helper.py
python3 -B packaging/rpm/test_compat_transactions.py
python3 -B packaging/rpm/manager/test_model.py
python3 -B packaging/rpm/manager/test_network_ui.py
python3 -B packaging/rpm/test_verify_release.py
```

Builder tests use synthetic compiler/package output. Deployment/recovery and
RPM compatibility tests use isolated fixtures/mocked host operations; they do
not perform a real system migration or independently prove password login and
protected-data preservation. The synthetic publication/signature contracts
do not prove public GitHub asset availability. A real canonical build validates
C compilation, shared-library ABI and dependency resolution independently.
See [production](../production/README.md) and [RPM packaging](../packaging/rpm/README.md).

## Installation and live-device qualification

On 21 October 2026 the operator reported the following **initial bounded
functional observations** from a clean Fedora 44 KDE VM. Without USB passthrough,
installation, update, reinstall, normal removal, emergency TTY removal and
password recovery succeeded; the obsolete `dontaudit` module was absent and
SELinux remained Enforcing. With the Goodix assigned exclusively to the VM,
KDE enrollment from an initially empty host pairing state completed; a
registered finger returned `verify-match` and a different finger returned
`verify-no-match`. KScreenLocker, sudo, PolicyKit and Plasma Login succeeded.
Login after reboot, Windows/Linux switching, and password fallback after three
failed fingerprint attempts were also reported PASS. These are operator
observations; raw audit traces for E0/readback/TLS and an independent repeat
of the hardware tests were not supplied with this documentation revision.

For reproducible software-only validation, leave USB passthrough disabled,
follow the [documented RPM procedure](INSTALLATION.md), then exercise
Manager update, reinstall, package removal and both [removal/recovery](UNINSTALL.md)
paths. Record RPM results separately from CLI observations. The operator has
reported ordinary Manager removal PASS; no claim is made here about every
failure/rollback or removal of damaged software through the GUI. Preserve
password access. Without actual pre-populated pairing state and templates,
a clean VM cannot establish their byte-for-byte preservation. These UI presentation issues are recorded under the known limitations
below.

Additional live qualification requires supervised authorization and should
cover sensor binding stability and cross-device separation, multiple users and
fingers, bad captures and false-positive risk, errors/cancellation, explicit
reopen, cold starts, and Windows/reboot recovery. For each verify/match series,
allow at most three physical attempts and stop at the first match. A timeout,
corrupted template, binding mismatch or ambiguous state is a STOP, not an
instruction to provision or reset the sensor. The pairing journal/readback/E0
contract must be audited separately from the observed success of a fingerprint
action. The normal installer is designed to upgrade a recognized earlier
installation transactionally, retaining pairing state and historical
templates but requiring new fingerprint enrollment. This direct
migration still requires a populated real-installation validation before
3.0.0. An optional return to SIGFM uses the two ordinary recovery commands
and a separate pinned historical checkout such as `v2.2.1`, **not `main`**,
without deleting templates, host state or factory data.

## Earlier driver qualification

The full test and integration record of the former SIGFM-based Goodix driver
is preserved in the [historical validation archive](VALIDATION_SIGFM_LEGACY.md).
That record documents the preceding implementation; its recognition statistics,
enrollment acceptance and pairing observations must not be represented as
biometric qualification of the current engine.

The change in template format introduced for version 3.0.0 requires new
fingerprint enrollment. A direct upgrade from a real, populated 2.x
installation, including fail-closed rollback and preservation checks, remains
a release gate. The reference for an optional older-version installation is
the historical `v2.2.1` tag, not the current `main` branch.

