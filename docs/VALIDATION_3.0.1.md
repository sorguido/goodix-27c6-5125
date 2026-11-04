<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix Manager 3.0.1: Fedora 44+ candidate qualification

This is Milestone 1 work on `fedora45-port`, starting at
`e6a32afb257c9c08e611f7f50d13eb1cb4ed9f6b`. No official 3.0.1 release has been
published. Existing tags and published assets are unchanged. Fedora 44 x86_64
remains the RPM build baseline. Fedora 45 and later are conditional targets,
subject to actual dependencies and runtime interfaces. Earlier Fedora 44
biometric observations are recorded separately in [VALIDATION.md](VALIDATION.md).

## Audit and compatibility contract

- The published `goodix-manager-3.0.0-13.fc44.x86_64.rpm` has SHA-256
  `ca26fb2028dbf91435ac8d9929d7b03cd81e8a30ee912fa4a71e97e4de75312e` and requires
  `system-release(44)`. Its verified payload source identity is
  `f259f6f10a60e5facc5a8404f951bce3eb18da2aaefebc8c9a167e4540938d97`, already
  recognized by the existing helper. The source tag and downloaded public RPM
  agree on the fixed dependency. The public release currently contains only
  the binary RPM; no historical assets are repaired or replaced by this work.
- The baseline commit already removes that dependency. Source builds and
  activation accept numeric Fedora releases >=44 on x86_64. The RPM build
  command remains restricted to Fedora 44; `.fc44` and `package.json.fedora=44`
  identify that build baseline. The Manager parser and release verifier retain
  this asset identity so already-installed 3.0.0 Managers discover 3.0.1.
- Architecture, package verification, source identity, payload hashes, SONAME,
  versioned fprintd ABI, library resolution, SELinux Enforcing, stock service and
  PAM ownership/structure checks remain required. Activation additionally
  repeats the ABI and relocation check on its immutable staged payload before
  stopping services or replacing project software. Missing or changed runtime
  interfaces fail closed. Recovery remains independent of Fedora release.
- RPM transactions contain no lifecycle scriptlets and own no active runtime,
  pairing state, templates, PAM override or service drop-in. RPM replacement and
  driver activation remain separate. A recognized 3.0.0 runtime offers Apply
  Update after RPM replacement; an unknown source still blocks. Packaging-only
  revision changes do not reapply the driver. Public update discovery continues
  independently of local runtime gates.
- ChicagoHS source, template format, matching/enrollment behavior, USB/TLS and
  pairing code are unchanged. Existing 3.x enrollments remain usable; no implicit
  re-pairing or template conversion/deletion is introduced. 2.x migration still
  requires new enrollment. Synthetic sentinels prove software preservation
  contracts, not preservation of real protected data during a real upgrade.

## Reproducible offline evidence

Build: `python3 -I -B packaging/rpm/build.py --release 2` as the ordinary user
on Fedora 44. Build identities are never overwritten. Outputs and full logs
are in the ignored `development/rpm/` workspace. The candidate is unsigned;
publisher signing and official release verification belong to Milestone 2.

Build revision 1 is reserved and was not overwritten: its real libpam synthetic
dispatch test failed inside the execution sandbox. The identical isolated PAM
test passed outside that sandbox as the ordinary user, with no changes to tests,
system PAM policy or security configuration. Revision 2 uses that environment.
The restriction's exact syscall mechanism was not established.

The complete Python, Qt, native C, deployment/recovery and release-contract
suites are run separately from compilation. Signature fixtures use ephemeral
TEST ONLY keys in the ignored workspace, never the publisher's private key.
Optional private OEM oracle tests do not read private material and are reported
as skipped. Neither unit tests nor loader checks open the USB reader.

The successful ordinary-user Fedora 44 build produced:

```text
/home/guido/Repository/goodix-27c6-5125/development/rpm/builds/3.0.1-2.fc44/rpmbuild/RPMS/x86_64/goodix-manager-3.0.1-2.fc44.x86_64.rpm
SHA256 3e06ae4d3380037b581af01fc389b2f8a6d48e2cc478acb435e0a0beb2fd1084
```

Payload source identity:
`908364380a00a6ad8b86ab56126ccabc4c0aa277b80179625c23a2c8ea743994`.
It matches the current source inventory. The builder also generated an unsigned
corresponding SRPM as a local build output, not an official release artifact:
`goodix-manager-3.0.1-2.fc44.src.rpm`, SHA-256
`dfd0a905b7bb45132f44fc43a72cf1e2ca2992e7d67c2ca14af1e707d566feee`.
Its source archive SHA-256 is
`c50a1ff64f40b715d3b43cf815f029b3a6ecde1e6897d1338868212a0253dfc3`.

Observed checks:

- Python suites: builder 24, installer 39, selection 8, bootstrap 6, removal 54,
  materials 38 executed/2 compiled-check cases skipped in the standalone run,
  packaging 5, helper 28, compatibility transactions 15, model 16,
  network/UI 13, release/signature contracts 14: **260 executed PASS**. The
  compiled material-check cases additionally run during the real payload build.
  Offscreen Qt cache regression and light/dark render sequences also passed.
  The signature fixture needed ordinary-user execution outside the sandbox for
  its temporary gpg-agent; no publisher key or normal keyring was used.
- Native tests: **274 normal +274 ASan/UBSan PASS** across all retained C
  runners: 202 current transport/pairing/lifecycle tests and 72 retained legacy
  diversity/SIGFM-profile regression tests per mode. Legacy profile tests cover
  retained shared integration code, not ChicagoHS biometric qualification.
  Separately, **64 ChicagoHS native +5 adapter PASS**. The 42 optional private
  OEM oracle cases were skipped; stock-fprintd storage multiuser/delete was
  unavailable without its separate source fixture. ASan/UBSan libraries missing
  from the host were downloaded as matching Fedora 44 packages, signature and
  digest verified, and extracted under `/tmp` for test compiler/loader use.
  No host packages were installed. LSan remains disabled by the existing runners;
  no sanitizer coverage is claimed for the pinned ChicagoHS native archive.
- Actual compilation and RPM `%check`: **PASS**, from the self-contained source
  archive without development material. Stock Fedora 44 fprintd resolves the
  built private library with all relocations satisfied. All **47** versioned
  `fp_*` symbols needed by the signature-verified Fedora 45
  `fprintd-1.94.5-6.fc45` binary are present. That latter check is static ABI
  evidence, not Fedora 45 execution. Neither byte-identical binaries across
  toolchains nor live biometric compatibility is inferred.
- Artifact inspection: exact RPM/SRPM headers and embedded full payload
  inventory, hashes, permissions, links and provenance **PASS**. No fixed
  distribution-release requirement, lifecycle scriptlet, active authentication
  path or private libfprint RPM provide was found. A comparison against the
  published 3.0.0 source ledger found **366 unchanged driver, native, reference
  and PAM files**. The actual model extracted from the signature-verified
  published 3.0.0 RPM successfully parses a 3.0.1 release fixture and offers its
  `.fc44.x86_64.rpm`; this is software discovery evidence only.
- DNF solved the **exact same candidate RPM** with official Fedora/updates
  repositories in empty Fedora 44 and 45 roots: **747** and **753** packages,
  respectively, with no dependency errors. These were `--assumeno` runs; their
  exit status 1 denotes the deliberate cancellation after a transaction summary,
  not a completed installation. No packages were downloaded or installed by
  those solves. The published 3.0.0 RPM fails the same empty Fedora 45 solve
  specifically because nothing provides `system-release(44)`.
- A read-only DNF solve against the existing Fedora 44 host proposes upgrading
  only Goodix Manager **3.0.0-13 → 3.0.1-2**, without extra package removals.
  Full-host Fedora 45 distro-sync resolution removes Goodix's release-version
  blocker when the candidate is included, but still **FAILS** on pre-existing
  rpmfusion-release and protobuf dependencies with only official Fedora repos
  enabled. A baseline solve without the candidate reproduces those blockers and
  the old Goodix dependency. No host package/configuration was changed to resolve
  these unrelated conflicts. This is not a successful distribution upgrade;
  the snapshotted VM test remains required.
- `rpmlint` on binary and SRPM: **0 errors, 8 warnings, exit 0**. Warnings concern
  the three unstripped hashed binaries, suggested PIE for check-material,
  source-archive URL, duplicated reviewed PAM text, private libfprint development
  link and the reader's existing OpenSSL cipher selection. No new suppression
  or policy relaxation was added. These warnings are not live security proof.
- Official signature/release gate: **NOT_TESTED** for 3.0.1. The unsigned
  candidate correctly fails strict signature verification; no synthetic signer
  is accepted as the publisher. The source/metadata checks were run separately
  and do not attest publication. No draft/tag/release or remote asset was changed.

Raw software-only logs and JSON records are under the ignored
`development/rpm/fedora45-port/`; build logs and hashes are under
`development/rpm/builds/3.0.1-2.fc44/`. They include `python-tests.json`,
`python-12-test_verify_release-escalated.log`, `native-sanitized-summary.txt`,
`sanitizer-library-proof.log`, `published-300-audit.json`,
`artifact-validation.json`, `candidate-*-dependency-solve.log`,
`distro45{,-baseline}-solve.json` and `rpmlint.log`. The initial sandbox failures
are retained alongside their successful environment-specific reruns.

Independent code, documentation and artifact review: **ACCEPT_AND_CONTINUE**
for the offline candidate. Live qualification and publication gates remain closed.

## Completion status for this candidate

| Required area | Status | Boundary |
| --- | --- | --- |
| Automated tests | PASS | Public software suite; explicit optional skips above |
| Native build and ABI verification | PASS | Actual Fedora 44 build/loader; Fedora 45 static symbols only |
| RPM dependency checks | PASS | Empty Fedora 44/45 repository solves, no fixed release dependency |
| RPM upgrade from v3.0.0 | NOT_TESTED | DNF solve and synthetic canonical update PASS; no real transaction |
| Fedora 44 → 45 distribution upgrade | NOT_TESTED | No rebooted upgrade; full-host solver still has unrelated blockers |
| Clean Fedora 45 installation | NOT_TESTED | Dependency solution is not installation/activation |
| Fingerprint enrollment and verification | NOT_TESTED | No 3.0.1 reader access |
| KDE login, screen unlock, sudo and PolicyKit | NOT_TESTED | Earlier Fedora 44 observations do not qualify this candidate |
| Password fallback and recovery | NOT_TESTED | Synthetic tests PASS; live candidate VM tests pending |
| Signature and release verification | NOT_TESTED | Candidate intentionally unsigned; official gate remains closed |

Offline candidate preparation is complete. Milestone 1 qualification remains
at the operator gate below; Milestone 2 is not started.

## HUMAN_REQUIRED: operator-supervised Fedora qualification

**GATE:** `FEDORA_44_45_VM_AND_LIVE_TESTS`. **PURPOSE:** qualify real package
transactions, system upgrade and authentication. **EXPECTED_RESULT:** the same
RPM installs on both releases, stays installed across 44 → 45, preserves
existing protected data and supports ordinary authentication/recovery.
**RISK:** a VM may lose fingerprint access or reveal an integration mismatch.
**ROLLBACK:** use a known-good VM snapshot and documented ordinary removal;
never reset/re-pair the sensor to make a test pass. A VM snapshot cannot restore
sensor pairing: stop on any unexpected persistent-state change.
**EVIDENCE_TO_RETURN:** PASS/FAIL/NOT_TESTED for each row below, versions,
transaction outcomes, fixed Manager diagnostics and sanitized errors only.
Keep any privileged protected-data comparisons private; return only equality
results, never PSK/template contents or hashes.

1. Use disposable snapshotted Fedora KDE x86_64 VMs with working password login,
   TTY/sudo access and SELinux Enforcing. Keep USB passthrough disabled during
   package tests. Preserve the existing 3.0.0 runtime, enrollments and pairing.
   Confirm `rpm -q goodix-manager fprintd fprintd-pam libfprint`,
   `getenforce`, and the existing Manager status. An integrity/source mismatch
   is a STOP. Never use force-remove as an upgrade prerequisite.
2. Transfer the exact candidate locally and compare its SHA-256 with the
   recorded build result. It is an unsigned local test artifact, not an official
   download. Use the target's ordinary package policy with
   `sudo dnf install /absolute/path/goodix-manager-3.0.1-2.fc44.x86_64.rpm`.
   Never pass `--nogpgcheck`, `--nodeps`, `--allowerasing` or weaken policy. If
   local policy requires a publisher signature, STOP: obtain an explicitly
   authorized normally signed test build before installing. Do not import a
   synthetic test key. Compare project PAM/drop-in files and protected state
   privately before/after the RPM-only transaction: they must be unchanged.
3. On the populated Fedora 44 VM, reopen Goodix Manager: it must show package
   3.0.1 and runtime 3.0.0 with **Apply Update**, with no new enrollment warning.
   With networking disabled, apply the update under PolicyKit and restart as
   instructed. Existing ChicagoHS fingerprints must remain usable. Compare
   pairing/template bytes, ownership and modes privately. Unexpected drift,
   new pairing, enrollment demand or incomplete rollback is a STOP.
4. Upgrade that Fedora 44 VM through Fedora's normal 44 → 45 procedure while
   keeping Goodix Manager installed. Review the transaction before accepting:
   it must not remove Goodix Manager or report `system-release(44)` as a blocker.
   After reboot confirm `rpm -q goodix-manager` still reports 3.0.1, SELinux is
   Enforcing, password login works, and the Manager verifies the runtime.
   A dependency solution alone is not a completed distribution upgrade.
5. Separately test a clean Fedora 45 KDE VM: install the same RPM, launch
   Manager and activate offline without USB. Confirm PolicyKit authorization,
   stock fprintd/PAM ownership, no unexplained AVCs, restart and password login.
   Test ordinary Manager removal, restart/password access and reinstall.
   Verify standalone `goodix-uninstall` remains available if the RPM alone is
   removed while its runtime is active. Follow [UNINSTALL.md](UNINSTALL.md) for
   TTY recovery; retain snapshots before destructive test scenarios.
6. Only after the package checks pass, assign the reader exclusively to the
   populated upgraded Fedora 45 VM with its existing valid host pairing state.
   Keep the clean Fedora 45 VM USB-free: do not copy protected state between
   VMs or trigger first-use pairing there. Start with verification of existing
   enrollment on the upgraded VM. Each VERIFY/MATCH series has **at most three physical attempts, stopping
   at the first MATCH**, with no hidden retry. No fourth attempt is authorized.
   A timeout, corrupt template, unknown firmware, binding/identity mismatch or
   pairing request on an already-active reader is a STOP. Do not reprovision.
   Test new enrollment separately with an unused finger on that same populated
   VM, without deleting prior enrollments. Enrollment uses the normal twelve-stage policy;
   its contacts are distinct from the bounded VERIFY/MATCH series.
7. Record separately enrollment, verification, KDE login, screen unlock, sudo,
   PolicyKit, reboot and password fallback/recovery. A console `fprintd-verify`
   MATCH does not qualify all authentication consumers. Preserve password access
   throughout. Stop on unexplained authentication or SELinux changes, incomplete
   cleanup, or unexpected changes to existing pairing, protected data or
   Windows coexistence. A deliberately added enrollment may create its own
   new template; it must not alter or delete earlier enrollments.

**PASS:** observed expected result at the tested layer, with preserved data and
working fallback. **FAIL:** an attempted check contradicts the contract.
**NOT_TESTED:** no real observation, including unavailable hardware or VM.
No publication or Milestone 2 is authorized by completing these instructions.
