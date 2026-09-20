<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Validation scope

The supported evidence boundary is Fedora 44 KDE x86_64 with Goodix USB
`27c6:5125` / APP12509.

Polkit closure at source commit `82e3ae67b01075fc5509c85bca22647665d9fb39`:
18 PAM tests in normal and ASan/UBSan modes, 7 local transaction tests and
30 managed transaction tests PASS. Actual daemon handlers on a private bus
cover ordinary pending Claim, claimed idle and pending Verify owner loss with
18 synthetic opens/closes. Both real candidates pass mock-filesystem
install/remove. The bridge is byte-identical between local and managed builds,
SHA-256 `9de3aba169b78298e539df1320f9bb10d64d418b6dd3ece196dcc401f1b7e3c2`.
The managed artifact has 34 files; verified SPDX: 48 packages, 32 files and
80 relationships. These results require no real authentication or device I/O.

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

The user's current observation on 20 September 2026 confirms sudo fingerprint
PASS on the development PC through D285's `pam_service=goodix-d285-01-sudo`.
This is current host evidence. It does not qualify a clean managed install:
that installer supplies neither this selector/service nor global fingerprint.
Clean candidate sudo fingerprint remains a release integration gap; ordinary
sudo configuration is preserved.

Polkit now has an independently implemented service-local PAM conversation
bridge and reversible local/managed deployment. Password-first submission,
explicit fingerprint selection, cancellation and cross-conversation limits are
checked offline. Real Discover behavior, SELinux execution and target cleanup
are pending human validation. No Polkit live PASS is claimed.

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
build, a working-tree copy without Git/private trees invoked from `/tmp`, and
the prepared candidate. That copy was not sufficient proof of reproduction
from committed content: it inherited an ignored upstream `.gitignore` absent
from the original import. ABI, symbol, dependency and RPATH checks pass. None of
these checks is a new host installation or live fingerprint test.

Corrective committed-source reproduction on 20 September 2026:

- Source commit: `99f19e6cdd9ed71ffd757001d29f3316818cc949`.
- A strict `git archive` of the publication allowlist produced 504 files in
  `/tmp/goodix-committed-repro`. Every file was compared with its committed
  blob, including dotfiles; the fprintd manifest and tree both contain exactly
  141 upstream files. No workspace copy, private history or development tree
  was included. The sole PNG in the export is the upstream libfprint demo icon,
  not a biometric fixture.
- A single temporary local commit,
  `aa7834c42f64541b0afb4308e67e0a789ca1cf27`, records that exact export for
  managed preparation's provenance requirement. It is not a project release
  commit and contains no private ancestors.
- All seven external RPM prerequisites were downloaded afresh from Fedora
  and checked against the committed manifests. SDK and Fedora system
  libraries/toolchain remain documented external prerequisites. The claim is
  no ignored/untracked **source** or accidental local cache dependency, not
  a hermetic build from Git alone: RPM staging remains intentionally ignored.

Commands executed using that committed export (build, login tests and
managed preparation invoked with `/tmp` as the working directory):

```bash
/tmp/goodix-committed-repro/production/check-source.sh
/tmp/goodix-committed-repro/production/build.sh normal /tmp/goodix-committed-normal
/tmp/goodix-committed-repro/production/build.sh sanitizer /tmp/goodix-committed-sanitizer
/tmp/goodix-committed-repro/production/login/check-offline.sh /tmp/goodix-committed-normal /tmp/goodix-committed-sanitizer
/tmp/goodix-committed-repro/deployment/managed-install/manage.sh prepare /tmp/goodix-committed-managed
python3 /tmp/goodix-committed-repro/deployment/managed-install/test_offline.py
git -C /tmp/goodix-committed-repro diff --check
```

All pass: 16 protocol and 34 driver cases in both modes, daemon/greeter tests
in both modes, and 25 transaction tests. Exact candidate set: 32 files. SPDX:
45 packages, 30 files, 75 relationships; hashes, package verification code,
references and byte-identical regeneration verified. Candidate SHA256SUMS
digest: `93d6eeb95ebcbf0f088c303a9dce9df485b33c28ed65456b0b0500f79a657ea7`.
The real candidate passes the existing mock-filesystem transaction test. All
nine runtime binaries/libraries match both the exported normal build and the
pre-correction build byte-for-byte. Prototype equivalence checks pass and the
cleanup patch is unchanged. No executable source or login behavior changed.

## Prepared-login three-attempt follow-up

Implementation commit `62eca6aa331e980683c09fc961042bc2631f6fe1` and recipe
correction `cde01e3e3e8e7dad1f6dc00e10ef303634d4f913` were exported using the
committed publication allowlist. All 505 source files, including dotfiles,
match Git blobs byte-for-byte. The local source-only checkout at
`eb9972e14e6bdc21b62d5d5a6b8283c4451186e6` contains only export commits, no private
ancestors. Seven documented external RPM prerequisites were copied after
checking their committed hashes; no ignored/untracked source supplied a build.
The recipe now extracts RPMs through a temporary archive, avoiding the observed
SIGPIPE when cpio finishes before rpm2cpio writes archive padding.

From `/tmp`, these complete paths passed:

```bash
/tmp/goodix-three-committed/production/check-source.sh
/tmp/goodix-three-committed/production/build.sh normal /tmp/goodix-three-final-normal
/tmp/goodix-three-committed/production/build.sh sanitizer /tmp/goodix-three-final-sanitizer
/tmp/goodix-three-committed/production/login/check-offline.sh /tmp/goodix-three-final-normal /tmp/goodix-three-final-sanitizer
/tmp/goodix-three-committed/deployment/managed-install/manage.sh prepare /tmp/goodix-three-final-managed
git -C /tmp/goodix-three-committed diff --check
```

Results: 17 protocol and 45 driver tests in **each** normal/sanitizer mode;
paired daemon and greeter tests in both modes; 26 managed transaction tests.
The suite covers second/third MATCH, three NO MATCH, refusal of attempt four,
hard error/retry/cancel on attempts one/two, complete physical-release gating,
same-generation rearm, cancellation during deferred completion, close between
attempts, cleanup and existing ordinary-consumer/enrollment regressions.
Daemon tests observe 15 synthetic opens and 15 closes per executable, with
no reopen within a claim. MATCH remains immediate, while NO MATCH waits for
release. These tests use synthetic protocol images/matching and a post-secure
session seam; they do not qualify a physical handshake or target rearm.

That pre-Polkit managed candidate had 32 files. Its SPDX SBOM has 45 packages,
30 files and 75 relationships; hashes, references, package verification code
and byte-identical regeneration pass. The SBOM includes the attempts patch.
SHA256SUMS digest:
`59ab21d9c41ff51694fc6f52316dd9bc0faf4ef09b09ce7b4557caa3d6ee4100`.
All nine runtime components match the independent normal build byte-for-byte;
there is no RPATH or test-only symbol in the production driver. The real
candidate passes the existing mock install/status/uninstall path, restoring
password/PAM files. A managed candidate with the old one-attempt PAM rule is
rejected before update changes; it requires its original uninstall before a
fresh install. Update/rollback within the three-attempt rule still passes.

The separate development delta was also built from `cde01e3...`. Its fprintd
and PAM binaries match the canonical candidate byte-for-byte; its driver
sources differ only in the four explicitly retained historical loaders. Its
SHA256SUMS digest is
`bbc5f1e4d8e0d47cceaf12421183842b1356cc8a1fb7b461cec47f3a11af8792`.
Nine delta transaction tests and the real candidate's mock install/rollback
pass, including exact prior bytes/modes and failure recovery. The frozen
historical overlay is unchanged and is not a canonical build dependency.

Physical second/third-attempt recovery, password/sudo behavior on the target
and timing remain subject to human validation. No host install, sudo, real USB
access or live biometric test was performed. Original prototype patch/greeter
hashes remain intact; none of the new offline results extend the old live
qualification to the new physical attempts.

Candidate `MANIFEST`, source digests, `SHA256SUMS` and SPDX SBOM record the actual
source commit and output identity. A build digest is provenance, not a claim of
live deployment or portability beyond the stated target.

No statistically meaningful false-acceptance or false-rejection rate is
claimed. Functional match/no-match observations are not a substitute for a
population study.
