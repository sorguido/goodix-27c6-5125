<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Licensing and provenance

## Directory map

| Scope | Default for new project-authored work | Rule |
| --- | --- | --- |
| `core/` | `GPL-2.0-or-later` | Userspace transport, protocol, TLS, FDT, capture and image code. |
| `tools/` | `GPL-2.0-or-later` | Tools connected to or derived from the GPL core. |
| `libfprint-driver/` | `LGPL-2.1-or-later` | Upstream-facing driver/glue; separate copyright boundary. |
| `src/`, `operator_kit/`, historical `analysis/D239`–`D246` | historical status retained | Frozen/reproducibility paths are not mass-moved or mass-relicensed by D247. |
| `docs/`, `analysis/` | file-specific | Check the file header and provenance; private evidence is not made open source by location. |

The canonical GPL and LGPL texts are in `LICENSES/`. The earlier
BSD-2-Clause grant remains effective for revisions already distributed under
it and is preserved in `LICENSES/BSD-2-Clause.txt`; D247 does not revoke it.
Third-party content keeps its own license.

No blanket open-source grant covers OEM firmware/binaries, private captures,
TLS/PSK secrets, biometric samples/templates, factory data, or any other asset
that cannot be redistributed. Such material must remain outside review bundles
and future public exports.

## Evidence authority and implementation reuse

Target-specific evidence authority and implementation provenance are separate:

```text
EVIDENCE AUTHORITY:
local 12509 capture/DLL/APP/live evidence and repeatable local tests
    > external implementation

IMPLEMENTATION REUSE:
Rockytkg GPL-2.0-or-later code = approved implementation source for core/tools
    only, subject to verified source license, attribution and provenance
```

External behavior does not prove that an operation is safe, non-persistent,
factory-preserving, correct for `GF_ST411SEC_APP_12509`, or compatible with the
factory/Windows PSK. The hardware invariant and all no-flash/no-IAP/no-OTP/
no-provisioning/no-persistent-write rules continue to apply.

## Import procedure and ledger

Before copying or adapting external code:

1. retrieve the source read-only and record an immutable commit;
2. verify the source path's license/SPDX, notices, relevant copyright holders,
   and whether third-party components have different terms;
3. confirm the destination domain is license-compatible;
4. preserve applicable SPDX, copyright and attribution notices;
5. add one ledger row recording source repository, commit, path, original
   license, known copyright, local import step/date, destination and changes;
6. review the diff for unintended proprietary, secret or biometric material;
7. validate sensor-reaching behavior independently against target-local
   evidence before any separately authorized live execution.

An author's permission covers only rights that author actually controls.

| LOCAL_PATH | SOURCE_REPO | SOURCE_COMMIT | SOURCE_PATH | LICENSE | COPYRIGHT | IMPORT_STEP | NOTES |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `N/A` | `https://github.com/Rockytkg/goodix-linux-27c6-5125` | `227eba219fa9e3fbac5bd59aca79f624f67cd11b` (2026-08-17) | `N/A — NOT_YET_IMPORTED` | Repository: original code `GPL-2.0-or-later`; `src/goodixgf.c` `LGPL-2.1-or-later`; `libfprint/` upstream terms; vendor firmware excluded. Sampled SPDX: `src/goodix_capture.c`, `src/goodix_init.c`, `src/goodix_tls.c` GPL; `src/goodixgf.c` LGPL. | Repository-level: `Copyright (C) 2026 liushicong (Rockytkg)`; not a claim over every line or third-party contribution. | `NOT_YET_IMPORTED` | `APPROVED_SOURCE / NOT_YET_IMPORTED`; verified externally by the AI Supervisor through authenticated GitHub access and supplied to D247 after the Codex network failure. No functional Rocky code was imported. Revalidate rights, SPDX, notices and third-party terms for each file selected by a future import. |

### Externally verified Rockytkg baseline

The AI Supervisor verified the ledger baseline through authenticated GitHub
access outside this Codex workspace. At commit
`227eba219fa9e3fbac5bd59aca79f624f67cd11b` (observed commit date
2026-08-17), the repository `LICENSE` states that original project code is
GPL-2.0-or-later, `src/goodixgf.c` is LGPL-2.1-or-later, `libfprint/` retains
upstream third-party terms, and vendor firmware at
`firmware/st411sec_app.bin` or embedded in `include/goodix_fw.h` is outside the
project's open-source license. Sampled headers confirm GPL-2.0-or-later for
`src/goodix_capture.c`, `src/goodix_init.c`, and `src/goodix_tls.c`, and
LGPL-2.1-or-later for `src/goodixgf.c`. The repository-level copyright notice
names `liushicong (Rockytkg)`; this is not generalized to third-party work or
every historical contribution.

The Supervisor also verified issue #1: Rockytkg reports direct hardware
validation on a 12508 unit, not an unmodified 12509 unit. Therefore this
verified implementation source remains subordinate to local evidence for every
target-specific APP12509 claim. Per-file rights and SPDX validation remains a
future import-time gate, not a D247 blocker because D247 imports no functional
file.

## GPL/LGPL firewall

GPL-only expression must not be copied, translated or adapted into
`libfprint-driver/`. Crossing is permitted only when the particular code is
already compatibly dual-licensed, every relevant rights holder supplies a
compatible alternative license, or the LGPL implementation is independently
created from specifications, protocol facts, tests and evidence without
transferring GPL expression. Keep design/evidence records sufficient to audit
that separation.

## Publication boundary

```text
private repository = canonical development workspace
public repository  = frozen publication surface pending a separate audited export
```

A clean final working tree does not make private Git history safe to publish.
Before release, perform a separate audit of content and history for proprietary
binaries/firmware, captures, secrets and biometric/private data. Use a clean
export, new history or a purpose-built filter when needed; never automatically
push or expose the private history. D247 does not modify the public repository.
