<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Validation scope

The supported evidence boundary is Fedora 44 KDE x86_64 with Goodix USB
`27c6:5125` / APP12509.

The user physically tested the early-login prototype at
`9671e02e19504e20e0097f598fa960f2c13e7a1e` after cold boot and reported:

- immediate successful login with immediate finger placement after Enter;
- password login PASS;
- sudo fingerprint authentication PASS;
- temporary overlay rollback PASS.

No deliberate delay was used. No sub-second timing was instrumented or claimed.
That evidence validates the architecture. Its canonical promotion is an offline
source/build/deployment integration; the promoted managed candidate has not been
installed or tested live in this task.

Earlier target evidence covers reader discovery, bounded enrollment, template
persistence, same/different-finger outcomes, local users, session unlock and
account-delete protection. Those results are retained, but are not presented as
a new full live qualification of this promoted managed candidate. Migration,
recovery across the complete release path and independent hardware remain open.

Offline validation commands for the distributed release surface are:

```bash
production/check-source.sh
python3 deployment/managed-install/test_offline.py
```

Per-reader runtime material handling is device-dynamic and has host-only
regression coverage, including distinct synthetic valid bundles and fail-closed
manifest cases. That validates runtime acceptance logic; it is **not** a claim
that this release provides or qualifies acquisition of a fresh five-file bundle.
Device-material acquisition is outside the supported release scope.

The normal and sanitizer builds cover all paired runtime components. Protocol
and driver shell suites use synthetic I/O; private-bus tests exercise actual
patched fprintd handlers, including a reproduced pending-open/suspend race.
Greeter tests execute the actual helper with a marker child. Managed transaction
tests cover complete payload, cleanup failures, update/rollback and drift.
Source checks preserve prototype hashes while separately identifying the cleanup
correction and canonical loader differences. See `production/login/README.md`
for the precise seams and limits of these tests.

After building both modes, run:

```bash
production/login/check-offline.sh /absolute/normal /absolute/sanitizer
```

Promotion closure on 19 September 2026: 16 protocol tests and 34 driver shell
tests pass in normal and ASan/UBSan modes; daemon private-bus and greeter barrier
tests pass in both modes; 25 managed transaction tests pass. The complete
32-file candidate was prepared from a clean committed checkout and passed a
mock-filesystem install/status/uninstall cycle. SPDX integrity checks cover 45
packages, 30 files and 75 relationships, including deterministic regeneration.
All nine runtime binaries/libraries are byte-identical across the canonical
build, a source-only copy without Git/private trees invoked from `/tmp`, and
the prepared candidate. ABI, symbol, dependency and RPATH checks pass. None of
these checks is a new host installation or live fingerprint test.

Candidate `MANIFEST`, source digests, `SHA256SUMS` and SPDX SBOM record the actual
source commit and output identity. A build digest is provenance, not a claim of
live deployment or portability beyond the stated target.

No statistically meaningful false-acceptance or false-rejection rate is
claimed. Functional match/no-match observations are not a substitute for a
population study.
