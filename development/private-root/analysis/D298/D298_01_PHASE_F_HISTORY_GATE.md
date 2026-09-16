<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D298/01 — Phase F protected-history gate

Date: 15 September 2026

## Outcome

The Phase F inventory found protected, private, and non-redistributable material
in both the current private tree and its Git history. Moving these paths under
`red_tag/` can separate the future working tree, but cannot make the existing
history suitable for publication. No public repository was accessed or
modified, no history was rewritten, and no protected payload was copied or
displayed during this audit.

This is a publication-history gate, not a defect in the qualified runtime.
D297 remains closed and the source-first candidate remains qualified for the
declared Fedora 44 KDE target.

## Confirmed protected/private families

| Family | Current tracked scope | Files | Bytes | First introduction | Classification |
| --- | --- | ---: | ---: | --- | --- |
| OEM Windows package and reverse-engineering corpus | `analysis/D230/work/GoodixExport/` | 27 | 19,175,652 | `b7ee001811c0c8034d1e59610aff2e21254fdb01` | `PROTECTED_OR_NONREDISTRIBUTABLE` |
| APP12509 mapped binary material | `analysis/D230/work/app/` | 3 | 262,015 | `b7ee001811c0c8034d1e59610aff2e21254fdb01` | `PROTECTED_OR_NONREDISTRIBUTABLE` |
| Private target captures and runtime evidence | `captures/` | 184 | 1,237,342 | `7751e26806f5aa0e57750ae20febc96325f99c7a` | `PRIVATE_RED_TAG` |
| Vendor firmware in the preserved Rocky snapshot | `Rockytkg/firmware/` | 2 | 130,015 | `0b03b3af6ff9ad2d40ad606bf190ff033c4a34f0` | `PROTECTED_OR_NONREDISTRIBUTABLE` |

The OEM family includes DLL/EXE/CAT artifacts such as `gfusb.dll`; the APP
family includes `GF_ST411SEC_APP_12509_mapped_code.bin`; the capture family
contains raw USB traces and cache binaries; the Rocky firmware family includes
`st411sec_app.bin`. The Rocky provenance record also identifies embedded
vendor firmware bytes in `Rockytkg/include/goodix_fw.h` as outside the
GPL/LGPL grant. PSK/secret-boundary analysis paths and private evidence require
exclusion even when a filename alone does not prove that a file contains a
live secret.

A path-oriented scan of all reachable objects found 343 distinct historical
paths matching protected/private indicators (`capture`, `raw`, `firmware`,
OEM binary extensions, PSK/secret terminology, or equivalent categories).
This count is a triage result, not a claim that every matching path contains a
secret. The four confirmed families above are sufficient to fail publication
of the private history.

## Initial repository classification

| Scope | Proposed classification | Reason |
| --- | --- | --- |
| `production/` and the production-listed source subset | `PUBLIC` after standalone-export correction | Current production authority, but its build still depends on a private-history baseline commit and must be made export-independent. |
| `deployment/phase-c-source-first-managed/` | `PUBLIC` after editorial/path cleanup | Supported installer lifecycle; public names and documentation must lose internal phase/milestone terminology. |
| Public-facing `README.md`, `docs/`, `LICENSE`, `LICENSES/` | `PUBLIC` after English product-oriented rewrite | Required entry point, guides, technical reference, licensing and notices. |
| `analysis/`, `captures/`, `operator_kit/`, `prompt/` | `PRIVATE_RED_TAG` | Internal chronology, evidence, historical live tooling and orchestration. |
| Governance files and the private Italian technical manual | `PRIVATE_RED_TAG` | Internal governance and chronological source material, not public documentation. |
| `Rockytkg/` snapshot | split: imported qualified source remains public; snapshot itself `PRIVATE_RED_TAG` | Contains useful licensed source and required provenance, but also vendor firmware and historical/reference material unsuitable for blanket export. |
| `reference/` | `KEEP_IN_PRIVATE_REPO_OUTSIDE_PUBLIC_EXPORT` pending source flattening, then `PRIVATE_RED_TAG` | Current build/reference topology is history-dependent and includes upstream test captures not needed by the supported product. |
| Historical `core/`, `src/`, `tools/`, `tests/`, `poc/`, `orchestration/`, `packaging/`, old deployment directories and D239 bundles | `PRIVATE_RED_TAG` | Superseded development paths, historical tests/tooling, or internal packaging evidence. |
| `.github/` Dxxx workflows | `PRIVATE_RED_TAG` | Historical milestone workflows, not a supported public CI contract. |
| generated caches and local package payloads | `REMOVE_ONLY_IF_TRULY_GENERATED_OR_DISPOSABLE` | Rebuildable and already intended to be ignored; deletion requires a separate exact-target check. |

No move is authorized by this report. Import/build/test/script/documentation and
licensing dependencies must be checked before populating `red_tag/`.

## Why working-tree exclusion is insufficient

`.gitignore` affects only untracked-path discovery. It does not remove blobs
from existing commits. Likewise, moving tracked material to `red_tag/` leaves
the earlier paths and payloads reachable from the private history. Publishing
this branch or cloning its history into a public repository would therefore
expose material that the project explicitly classifies as private, protected,
or non-redistributable.

## User decision and resumed scope

The user resolved the gate on 15 September 2026. The private repository and
its complete history remain private and unchanged. They are not publication
inputs, do not need history sanitization, and must not be rewritten. No fresh
public root is to be created by the agent and the public repository remains
out of scope.

Phase F therefore resumes as a current-working-tree separation:

1. audit dependencies before every move;
2. keep only the publishable product surface outside `red_tag/`;
3. make build, tests, installation, and public documentation independent of
   `red_tag/` and of the private Git history;
4. preserve all excluded material under ignored `red_tag/` in the private
   workspace;
5. let the user manually copy the approved public files into their own public
   clone and perform any public commit or push personally.

```text
OUTCOME=USER_DECISION_RECEIVED
ADVANCEMENT=WORKING_TREE_SEPARATION_AUTHORIZED
PRIVATE_HISTORY_PUBLISHABLE=false
PRIVATE_HISTORY_IS_PUBLICATION_INPUT=false
WORKTREE_MOVE_SUFFICIENT=true
PUBLIC_REPOSITORY_ACCESSED=false
HISTORY_REWRITE_PERFORMED=false
PUBLIC_ROOT_HISTORY_CREATED=false
AUTHORIZED_STRATEGY=USER_MANUAL_COPY_OF_VALIDATED_PUBLIC_WORKING_TREE
EXECUTABLE_CLOSURE=NOT_APPLICABLE
```
