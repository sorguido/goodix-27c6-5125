<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix Manager 3.0.1: validation and limitations

Version 3.0.1 removes the exact Fedora-release dependency while retaining
dependency, platform and runtime ABI checks. Fedora 44 x86_64 is the build
baseline; `.fc44` does not restrict installation to Fedora 44. Fedora KDE 44
and 45 have operator-reported functional evidence. Compatibility with later
Fedora releases depends on their system components and further testing.
Version 3.0.1 is being prepared as an unpublished draft; it is not yet a
public download or an update offered by Goodix Manager.

## Operator-reported observations

The following are reports supplied by the operator, not independently repeated
tests by the release agent:

| Environment and operation | Reported result | Scope |
| --- | --- | --- |
| Fedora 45 VM: 3.0.1 installation, activation, KDE login, screen unlock and sudo | PASS | Earlier report identifies signed revision 2; it also identifies an incorrect mandatory-enrollment notice after reinstall |
| Fedora 44 VM with 3.0.0 and existing enrollment: update to 3.0.1, then Fedora 44 → 45 upgrade | PASS | Latest operator report; packaging revision not specified |
| Initially clean Fedora 44 VM: direct first installation of 3.0.1 | PASS | Latest operator report; packaging revision and individual authentication checks not specified |

These reports supersede the earlier statement that Fedora 45 testing and an
upgrade with the RPM installed had not occurred. They do not establish physical
testing of revision 3 or a later documentation-only rebuild. No byte-for-byte
audit of real templates or PSK is claimed. The 3.0.0 → 3.0.1 update retains the
ChicagoHS format; SIGFM 2.x migration still requires new enrollment.

## Available software evidence

The enrollment-notice correction reserves `enrollment_required` for a recognized
incompatible-format migration. An ordinary ChicagoHS install/reinstall does not
set it, and the Manager does not inspect protected galleries to infer whether
fingerprints exist. Unknown or unqualified lineage still fails closed.

Revision 3's recorded public Python suite contains **265 tests passed, 0 failed,
2 skipped**; the skipped compiled material-check cases ran in the payload build.
Qt offscreen, cached-interface and light/dark regressions passed. Synthetic
transactions cover preserved ChicagoHS fixtures, recognized SIGFM migration,
3.0.0 → 3.0.1, status refresh and blocked unknown lineage. These tests establish
software behavior, not live authentication or biometric accuracy.

The recorded canonical Fedora 44 build, payload inventory/hashes/modes, ABI and
loader checks passed. Fedora 44 and 45 clean-root dependency resolution passed
without installing packages. RPM lint reported **0 errors and 8 existing
warnings**. No exact `system-release(44)` requirement, activation scriptlet or
ownership of active-runtime/protected-data paths was found.

Revision 3's actual binary and SRPM have been rechecked against their current
`result.json`: both signatures and digests pass isolated verification using
publisher fingerprint **5FB2 0F58 3C83 1729 D5FF 073F E99A DAE5 B7EA 4918**.
Earlier unsigned hashes and signing handoffs are historical, not current status.

Revision 2 and 3 share payload source identity
`908364380a00a6ad8b86ab56126ccabc4c0aa277b80179625c23a2c8ea743994`.
Recorded independent comparison found identical executable/data sections;
raw library bytes differed only in build-ID/debug-path metadata, with a
corresponding archive-hash change in provenance. Original artifacts were not
rewritten. This supports software equivalence; it does not turn revision 2's
physical observations into revision 3 tests.

## Final artifact and distribution checks

The final source archive must include the committed installation guide and
release documentation. A new packaging revision is required when the existing
archive differs; an existing signed build is never replaced. Its canonical
build record, suite logs, source/payload comparison, Fedora 44/45 dependency
resolution and lint results must be checked before the signing handoff.
The final pair then requires publisher signing through local pinentry,
post-signature checksums and the offline **draft-mode** release gate.

A local gate proves package contracts only. Draft completion additionally
requires authenticated GitHub metadata with `draft=true`, `prerelease=false`
and exactly one signed binary RPM plus its matching signed SRPM, whose uploaded
bytes match the local artifacts. No publication is authorized. Drafts must not
be offered by the Manager's public update check.

Software-only records are kept in ignored `development/rpm/`; canonical builds
and signature records are under `development/rpm/builds/`. They contain no new
sensor capture or protected-state export for this documentation work.

## NOT_TESTED and remaining limits

- Revision 3 and the final documentation rebuild: physical authentication,
  corrected-notice behavior in a real VM and full interactive lifecycle were
  not independently rerun. Use targeted software regression and payload
  comparison without labeling missing live tests PASS.
- No new physical template/PSK preservation audit, live pairing audit,
  populated SIGFM migration/rollback or damaged-state recovery was performed.
- Future Fedora releases, broad multiuser/multireader behavior, FAR/FRR,
  liveness and spoof resistance remain unqualified.

The earlier native/sanitizer evidence and the general limitations in
[VALIDATION.md](VALIDATION.md) remain distinct from these packaging checks.
No runtime installation, USB action or protected-data inspection is needed to
finalize the documentation and draft assets.
