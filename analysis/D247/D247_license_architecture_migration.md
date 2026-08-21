<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D247 — License architecture, provenance and reuse boundaries

Date: 2026-08-21

Reasoning level: HIGH
Scope: offline architecture/documentation only

## Initial Git baseline and repository identity

- real Git root: `/workspace/goodix-27c6-5125-private`;
- branch: `work`;
- initial HEAD: `bab0c2cd15daa75849b3a1b713def6156608103c`;
- initial `git status --short`: clean;
- configured remotes: none in this workspace's `.git/config`.

The workspace directory and supplied task identify the intended private
`sorguido/goodix-27c6-5125_private` repository, but no configured remote exists
to independently verify that GitHub identity. No remote was added, and neither
the private nor public repository was pushed or modified remotely.

## Initial inventory

- Root `LICENSE` granted BSD-2-Clause to original project-authored content.
- Runtime/history is under `src/`, `poc/`, `operator_kit/`, tests, and step-local
  `analysis/D230`–`D246`; these paths include active/frozen reproducibility
  dependencies and were neither moved nor mass-relicensed.
- OEM/private evidence is referenced by hashes and some historical analysis
  material exists in the private workspace; it is not covered by the new
  open-source directory defaults and is excluded from this bundle.
- The only project-guideline source initially present was the v2.1 PDF; D247
  adds a machine-readable v2.2 Markdown revision while retaining the PDF as a
  historical revision.
- No pre-existing `LICENSES/`, `core/`, `libfprint-driver/`, operational license
  map, or external-import ledger existed.

## Rockytkg provenance closure

The original Codex read-only attempt with `git ls-remote` failed with HTTP
CONNECT 403, and the Codex web lookup was unavailable. D247 does not rewrite
that observation or claim that this workspace performed the later verification.

The AI Supervisor subsequently supplied authenticated GitHub verification,
performed outside this workspace, for source commit
`227eba219fa9e3fbac5bd59aca79f624f67cd11b` (observed date 2026-08-17). At
that commit:

- the root `LICENSE` identifies original project code as GPL-2.0-or-later,
  `src/goodixgf.c` as LGPL-2.1-or-later, `libfprint/` under its upstream
  third-party terms, and vendor firmware in `firmware/st411sec_app.bin` and
  `include/goodix_fw.h` as outside the project's open-source grant;
- the repository-level notice is `Copyright (C) 2026 liushicong (Rockytkg)`,
  without implying ownership of every line or third-party contribution;
- sampled SPDX headers are GPL-2.0-or-later in `src/goodix_capture.c`,
  `src/goodix_init.c`, and `src/goodix_tls.c`, and LGPL-2.1-or-later in
  `src/goodixgf.c`;
- issue #1 states that Rockytkg's direct hardware validation used a 12508, not
  an unmodified 12509. Rocky therefore remains an implementation/provenance
  source, not target-specific evidence authority for APP12509.

The ledger is now `APPROVED_SOURCE / NOT_YET_IMPORTED`. D247 imported no
functional Rocky code. Per-file rights, SPDX, notices, and third-party terms
remain mandatory import-time checks, but are not a D247 blocker because no
source file is selected or imported here.

## Changes

- Converted root `LICENSE` into a multi-license pointer and preserved the prior
  BSD text verbatim as `LICENSES/BSD-2-Clause.txt`.
- Added unmodified canonical system copies of GPL v2 and LGPL v2.1 at the
  required `-or-later` license-text paths.
- Created future boundaries with documentation only: `core/` and `tools/` GPL;
  `libfprint-driver/` LGPL. No fake driver and no AF/FDT/capture code was added.
- Added `docs/LICENSING_AND_PROVENANCE.md`: directory map, exclusions, import
  procedure, minimal ledger, attribution rules, target-evidence hierarchy,
  GPL/LGPL firewall and private-to-public export boundary.
- Added project-guideline revision v2.2 and updated `AGENTS.md`, the canonical
  manual and README organically. Historical BSD/clean-room statements are now
  explicitly historical through D246, not future policy.
- No runtime file was moved or modified. This deliberately preserves D239–D246
  launcher/import reproducibility and avoids cosmetic duplication.

## Final policy

```text
private repository = canonical development workspace
core/ + tools/      = GPL-2.0-or-later; verified Rocky reuse allowed;
                       provenance and target-local validation required
libfprint-driver/   = LGPL-2.1-or-later; GPL expression barred absent a
                       compatible alternative license
public repository  = frozen pending separate content + history audit/export
hardware invariant = factory firmware and persistent state remain untouched
```

Past BSD recipients retain their existing license grant. Third-party and
proprietary material retains its own rights. A clean working tree never implies
that private history is publishable.

## Verification

- `python -m unittest discover -s tests -v`: 41 tests discovered; 24 passed,
  1 skipped, 3 failed and 13 module-load errors. Every failure/error requiring
  the runtime path traces to the environment's absent `cryptography` package;
  D247 changed no runtime/import path. This is recorded as an environment
  limitation, not represented as a pass.
- `cmp /usr/share/common-licenses/GPL-2 LICENSES/GPL-2.0-or-later.txt` and the
  corresponding LGPL comparison: pass.
- `git diff --check`: pass.
- New authored boundary/guideline/provenance files contain matching SPDX
  headers; canonical license texts and the root license map are intentionally
  not modified with extra headers.
- New-file extension scan found no capture, DLL, firmware, image or raw asset.
- Diff review found policy references to PSK/secret/biometric classes but no
  secret value, PSK material or biometric data.
- No USB/device command, live path, AF, FDT, capture, D4, provisioning,
  persistent write, `sudo`, push or public-repository action was executed.

## Codex Web PR transport

The original ZIP bundle was generated and verified at SHA-256
`779538b9e0762e57e5f29f7abc0da6aa8c4e37d4d70004651114f211ad8d7a72`.
Because Codex Web cannot transfer the binary file in the PR diff, the PR tree
contains the exact lossless standard-Base64 representation
`D247_license_architecture_migration_bundle.zip.b64` while retaining the ZIP
SHA-256 receipt. An offline decode round-trip reproduced the same ZIP hash.
The Base64 file is a temporary transport artifact: after recovery and hash
verification of the ZIP, do not retain the `.b64` file in the future final
baseline. This transport workaround changes no D247 technical content.

## Residual risks and next step

1. Revalidate rights, SPDX, notices, and third-party components for every
   individual Rocky file selected in a future import. This is an import-time
   gate, not an unresolved D247 provenance blocker.
2. The prior full runtime suite remains environment-limited by the missing
   `cryptography` dependency; D247 changed no runtime/import path and this
   correction reruns only document, license, bundle, and exclusion checks.
3. The old AF/GetMcuState → FDT → first-image D247 prompt is
   `SUPERSEDED / DO_NOT_EXECUTE / NOT_EXECUTED`. Regenerate it as the next step,
   allowing selective provenance-preserving GPL-core reuse while requiring
   differential APP12509 validation.

Correction-specific files: `docs/LICENSING_AND_PROVENANCE.md`, the canonical
manual, this report, the regenerated bundle, and its SHA-256 receipt.

`ROCKY_SOURCE_COMMIT_VERIFIED_EXTERNALLY=227eba219fa9e3fbac5bd59aca79f624f67cd11b`

`FUNCTIONAL_ROCKY_CODE_IMPORTED=NO`

`NEW_COMMIT_CREATED=YES` (required by the repository-level execution policy that overrides the step-local no-commit request)

`PUSH_PERFORMED=NO`

`PR_CREATED=NO` (the required `make_pr` facility is not exposed in this environment)

## Six-field closure

`OUTCOME=READY`

`ADVANCEMENT=ARCHITECTURAL_STATE_CHANGED_NO_HARDWARE_ADVANCEMENT`

`EXECUTABLE_CLOSURE=NOT_APPLICABLE`

`RESIDUAL_BLOCKER_OR_RISK=PER_FILE_RIGHTS_AND_SPDX_REVALIDATION_REQUIRED_AT_EACH_FUTURE_IMPORT;CODEX_CLOUD_RUNTIME_TESTS_LIMITED_BY_MISSING_CRYPTOGRAPHY_DEPENDENCY`

`CANONICAL_DOCUMENTATION=UPDATED`

`BUNDLE=analysis/D247/D247_license_architecture_migration_bundle.zip`
