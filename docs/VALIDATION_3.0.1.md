<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix Manager 3.0.1: Fedora 44+ test candidate

Current task: packaging revision **3**, enrollment-notice correction on
`fedora45-port`, starting from `bc1410b9bd3bb0a460dc4b9b827ddb8d43eda54d`.
No official release, tag or published asset is changed. Fedora 44 x86_64 remains
the required RPM build baseline; later Fedora releases require compatible system
components and runtime interfaces. `.fc44` identifies the build baseline.

## Evidence and scope

The signed revision 2 binary and SRPM were verified against the existing public
publisher certificate, fingerprint
`5FB20F583C831729D5FF073FE99ADAE5B7EA4918`. Their current SHA-256 values are
`2e195e7dc84d5803545e06ba28632309f7495b4ff213d6fbbdbaf89046928d14` (binary) and
`e2b513d77539b37968c89eeecbfe15298697942381aed73d42ae101b7dbba74a` (source).
Revision 2 and its `result.json` must remain byte-for-byte unchanged.

The operator's supplied correction request reports installation of signed
revision 2, activation, KDE login, screen lock and sudo on Fedora 45. It also
reports the incorrect mandatory-enrollment notice after reinstalling the driver
with preserved ChicagoHS templates. These are **operator-reported observations
for revision 2**, not independent tests or revision 3 live qualification. They
are not evidence of a completed Fedora 44 → 45 upgrade with the RPM installed.

`enrollment_required` means a known incompatible fingerprint-format migration.
Plain install/reinstall cannot prove absence or incompatibility of saved prints.
The helper and GUI use the verified flag without inferring it from a generic
legacy state. Recognized SIGFM 2.x migration retains its warning. Unqualified
Milan/unknown lineage remains blocked under the existing provenance rules.
No template/gallery, pairing or PSK inspection is added; the fix is confined to
Manager/helper logic, its tests and user documentation.

Version stays **3.0.1** and only packaging Release increases. The expected
payload source identity is unchanged from revision 2:
`908364380a00a6ad8b86ab56126ccabc4c0aa277b80179625c23a2c8ea743994`.
Native biometric behavior, USB/TLS, PAM, password fallback, ABI preflight,
SELinux Enforcing and stock-system checks are unchanged. The RPM still has no
`system-release(44)` dependency, no activation scriptlets and no ownership of
active runtime or protected-data paths. RPM replacement does not reapply an
identical driver payload.

## Offline checks and artifacts

Canonical build: `python3 -I -B packaging/rpm/build.py --release 3` as the
ordinary user on Fedora 44. Build identities are never overwritten. The isolated
PAM dispatch test requires execution outside the tool sandbox, as established
for revision 2; tests and host PAM/security policy are not modified.

Revision 3 build and RPM `%check`: **PASS**. Public Python suite: **265 executed
PASS, 0 FAIL, 2 SKIP**; the two skipped compiled material-check integration cases
run separately during the actual payload build. Offscreen QML visibility,
install/refresh, cached-interface regression and light/dark sequences: **PASS**.
Tests cover unknown template presence, preserved synthetic ChicagoHS templates
through normal removal/reinstall, direct SIGFM 2.2.1 → 3.0.1, 3.0.0 → 3.0.1,
status refresh and blocked unknown lineage. These are software-contract tests.

Artifact headers, full payload hashes/inventory/modes/links, root ownership,
absence of lifecycle scriptlets/release lock/private libfprint provides and
packaged helper/Manager correspondence: **PASS**. Fedora 44 native build/loader
ABI preflight: **PASS**. DNF5 resolves the actual candidate in empty Fedora 44
and 45 roots (747 and 753 packages): **PASS**, cancelled with `--assumeno` before
installation. RPM lint on binary and source: **PASS, 0 errors, 8 existing
warnings**, with no new suppression or security-policy change.

Payload comparison initially stopped progression for independent review:
**raw byte equality FAIL; executable/data equivalence PASS**. The identical
source identity permits this packaging-only revision. All payload files except
`runtime/libfprint-2.so.2.0.0` and `runtime/build-provenance.json` are byte-identical.
The library differs in exactly **21 bytes**: 20 GNU build-ID bytes and one
nonallocated debug-path byte (`3.0.1-2.fc44` → `3.0.1-3.fc44`). Executable code,
initialized data, relocation tables, dynamic symbols, ABI versions and layout
are identical. Temporary copies with debug/build-ID removed are byte-identical,
SHA-256 `2883e0fd4f5195b88470d355bf735c2c0c0c914f16c9825abfed4e1e90db078a`.
Only the native archive hash differs in provenance. **Original RPM/payload
bytes were never stripped or rewritten.** Independent review accepted the
metadata-only difference; no version bump or native change is required.
Revision 2 artifacts and `result.json` remain byte-for-byte unchanged.

Unsigned artifacts (not yet installable under the required publisher-signature
gate):

```text
/home/guido/Repository/goodix-27c6-5125/development/rpm/builds/3.0.1-3.fc44/rpmbuild/RPMS/x86_64/goodix-manager-3.0.1-3.fc44.x86_64.rpm
SHA256 66fbe15c2ae9a5095de353c985639e3bbff1e0f029798e98f6007dde57c0e3f7
/home/guido/Repository/goodix-27c6-5125/development/rpm/builds/3.0.1-3.fc44/rpmbuild/SRPMS/goodix-manager-3.0.1-3.fc44.src.rpm
SHA256 a6c1abefeab8a30c59e548d8cebd0efb1be9cf1582dee98f2fd60deba63efab7
```

Independent review: **ACCEPT_AND_CONTINUE** to the human signing handoff only.
Publisher signature/verification, actual revision 3 VM reinstall, KDE login,
screen unlock, sudo, PolicyKit, password fallback/recovery and biometric use:
**NOT_TESTED**. Previous revision 2 operator reports are not promoted to revision
3 qualification. Broad native/ASan/UBSan tests from revision 2 were not rerun for
this Manager-only delta; executable equivalence and native compilation were
verified directly. No active runtime, sensor or protected data was accessed.

Raw software-only evidence belongs in ignored
`development/rpm/enrollment-301-3/`; the canonical build log and result are in
`development/rpm/builds/3.0.1-3.fc44/`. Earlier broad native/ASan/UBSan and
Fedora 44/45 dependency evidence remains under `development/rpm/fedora45-port/`.
Optional private OEM-oracle cases were skipped; no synthetic test qualifies
biometrics or password login on real hardware.

## HUMAN_REQUIRED: publisher signing

**GATE:** `SIGN_TEST_RPM_3_0_1_3`. **PURPOSE:** sign the exact reviewed binary
and SRPM locally with the existing publisher identity. **EXPECTED_RESULT:**
canonical isolated verification passes for both files and `result.json` records
`signature=VERIFIED`, the full expected fingerprint and new signed checksums.
**RISK:** signing changes artifact bytes and attests this specific candidate.
**ROLLBACK:** retain the untouched signed revision 2; a cancelled/failed canonical
sign operation leaves the unsigned revision 3 artifacts and record intact.
**EVIDENCE_TO_RETURN:** updated revision 3 `result.json` and non-secret signature
verification output, never private keys or pinentry/passphrase content.

The operator runs this in their Fedora 44 terminal as the normal user:

```sh
cd /home/guido/Repository/goodix-27c6-5125
python3 -I -B packaging/rpm/build.py --release 3 \
  --sign 5FB20F583C831729D5FF073FE99ADAE5B7EA4918 \
  --sign-existing /home/guido/Repository/goodix-27c6-5125/development/rpm/builds/3.0.1-3.fc44
```

Use normal local pinentry. No private-key export, new key, loopback passphrase,
chat credential or policy bypass is permitted. **Stop before running this command
in the agent workflow**, as explicitly required by the current user request.
After the operator signs, signature, fingerprint and digests must be verified
and **new signed SHA-256 values** returned before VM installation. Unsigned build
hashes below are not valid checksums for the signed files.

## HUMAN_REQUIRED: Fedora 45 VM message/reinstall test

**GATE:** `FEDORA45_3_0_1_3_REINSTALL_AND_AUTH`. **PURPOSE:** verify the corrected
message with preserved compatible enrollments and repeat the reported
login/lock/sudo observations. **EXPECTED_RESULT:** no mandatory-enrollment notice
on ChicagoHS reinstall, existing fingerprint usable and password fallback intact.
**RISK:** temporary fingerprint unavailability or an unexpected integration error.
**ROLLBACK:** ordinary removal and the known-good VM snapshot/software; a VM
snapshot does not restore reader pairing. **EVIDENCE_TO_RETURN:** RPM version,
Manager diagnostics, notice visible/absent and PASS/FAIL/NOT_TESTED for each live
operation, with sanitized errors only. Keep protected-data comparisons private.

1. Use the populated, snapshotted Fedora 45 KDE VM that retains its existing
   valid host pairing and ChicagoHS templates. Confirm password/TTY/sudo access
   and SELinux Enforcing. Keep USB passthrough disabled for package operations;
   never copy protected state from another VM or trigger fresh pairing.
2. Only after publisher signing and verification, transfer the signed binary
   and public certificate to the VM. Compare the binary SHA-256 with the **new
   signed** result. Authenticate the full public fingerprint independently.
   In the VM terminal, with the files in your Downloads directory:

   ```sh
   goodix_test_rpm="$HOME/Scaricati/goodix-manager-3.0.1-3.fc44.x86_64.rpm"
   sha256sum "$goodix_test_rpm"
   gpg --show-keys --with-fingerprint "$HOME/Scaricati/Guido-Soraru.asc"
   sudo rpmkeys --import "$HOME/Scaricati/Guido-Soraru.asc"
   rpmkeys --define '_pkgverify_level all' --checksig --verbose "$goodix_test_rpm"
   sudo dnf5 install "$goodix_test_rpm"
   rpm -q goodix-manager
   goodix-manager
   ```

   Adjust the Downloads path if necessary. Signature and digest checks must be
   OK for the expected publisher. Never use `--nogpgcheck`, `--nodeps`,
   `--allowerasing` or weaken SELinux/PAM. Installing the -3 RPM should leave the
   existing 3.0.1 runtime up to date, without requiring Apply Update or enrollment.
3. Close Manager. Run **`goodix-uninstall`** for ordinary driver removal, follow
   its authorization prompt and reboot. Confirm password login, then open
   Manager: runtime must be absent. Existing pairing/templates must remain.
   Removing only the Manager RPM would leave the runtime active and would not
   exercise this test. Do not use force-remove as an ordinary test procedure.
4. Choose **Install** in Manager and authorize activation with USB still disabled.
   After success and a status refresh, the mandatory incompatible-template
   notice must stay absent. A new user can enroll in KDE settings if needed;
   do not delete or re-enroll existing compatible fingerprints to hide the bug.
   Restart as instructed. Compare existing protected bytes/ownership/modes
   privately; report only preserved/not-preserved, never contents or hashes.
5. Assign the reader exclusively to this VM only for supervised authentication.
   Verify an existing fingerprint, then separately repeat KDE login, lock-screen
   unlock and sudo; retain password fallback throughout. Each VERIFY/MATCH
   series allows **at most three physical attempts, stopping at the first
   MATCH**, with no fourth attempt or hidden retry. Do not repeat enrollment
   merely because software was reinstalled.
6. **STOP/FAIL** for unexpected notice, source/integrity mismatch, pairing request,
   missing templates, unexpected protected-data/SELinux changes, authentication
   regression or incomplete rollback/cleanup. Do not reprovision/reset the reader.
   Report unavailable live checks as NOT_TESTED. Follow [UNINSTALL.md](UNINSTALL.md)
   for ordinary removal/recovery; seek review before any emergency intervention.

No signing, installation or sensor action is performed automatically. Official
release, merge and tag creation require a later explicit authorization.
