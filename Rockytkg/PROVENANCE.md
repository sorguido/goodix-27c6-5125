# Rockytkg snapshot provenance

## Purpose

This directory is the project-local preserved snapshot of the Rockytkg Goodix 27c6:5125 work. It exists for three distinct purposes:

1. preserve the upstream knowledge even if the original remote repository later changes or disappears;
2. provide Codex and other project AIs with an offline, repository-local source that does not require network access;
3. serve as a real implementation source from which code may be copied or adapted when the applicable license permits it and project safety/provenance rules are satisfied.

This snapshot is **not** primary evidence for target-specific behavior of the local `GF_ST411SEC_APP_12509` device. Local captures, DLL/APP12509 evidence, the canonical manual and authorized live evidence remain authoritative for target-specific claims.

## Canonical project location

```text
<git-root>/Rockytkg/
```

This file is the canonical provenance record for the snapshot:

```text
<git-root>/Rockytkg/PROVENANCE.md
```

Project AIs should consult this local snapshot first. The remote repository is provenance/origin information, not a required runtime dependency of the normal workflow.

## Upstream identity

- Upstream project: `Rockytkg/goodix-linux-27c6-5125`
- Upstream repository: `https://github.com/Rockytkg/goodix-linux-27c6-5125`
- Preserved upstream commit: `227eba219fa9e3fbac5bd59aca79f624f67cd11b`
- Upstream tree at that commit: `6dda93a960ceddb085c59b5382df47ecc5d56a39`
- Snapshot acquisition/preservation date: `2026-08-21`
- Snapshot form in this project: materialized directory; nested upstream `.git` metadata removed.

The upstream commit above is the immutable source identity used by D249 and by subsequent differential/provenance work unless this snapshot is deliberately refreshed and this file is updated.

## Materialized libfprint submodule

At upstream commit `227eba219fa9e3fbac5bd59aca79f624f67cd11b`, Rockytkg declares:

```text
submodule path: libfprint
submodule origin: https://github.com/goodix-fp-linux-dev/libfprint.git
submodule gitlink commit: 7ebe0c809b4d1df3400e84299a4ec4acdea84590
```

In this project snapshot, `Rockytkg/libfprint/` is materialized as ordinary files rather than retained as a nested Git submodule. Its licensing and reuse rights therefore remain those of the upstream libfprint material; materialization does not relicense it.

## Licensing map

The upstream `LICENSE` at the preserved commit states the following scope. Per-file SPDX headers and third-party origins remain controlling where more specific.

The first two columns below record immutable snapshot/upstream facts. The last
column is the project's current local reuse policy, effective after D279/48;
changes to that column do not assert any retroactive change to the upstream
license, copyright, commit, tree or historical origin.

| Snapshot material | Immutable upstream licensing status | Current local project reuse policy |
| --- | --- | --- |
| `src/` original Rockytkg code | `GPL-2.0-or-later`, except where a more specific per-file notice applies | May be copied/adapted into GPL-compatible project components or a GPL-compatible fork/combined work, with attribution and source-path/commit provenance |
| `include/` original Rockytkg headers | `GPL-2.0-or-later`, subject to per-file notices and the firmware exception below | May be reused in GPL-compatible project components after per-file audit |
| `tools/`, `Makefile`, install/uninstall scripts | `GPL-2.0-or-later` | May be reused under GPL-compatible terms with attribution and provenance |
| `src/goodixgf.c` | `LGPL-2.1-or-later` | May be evaluated after per-file provenance/licensing audit; its hardware stack is not selected because it duplicates the locally proven APP12509 path, not because it resides in a nominal LGPL-facing domain |
| `libfprint/` | Third-party upstream libfprint licensing | Reuse only under its own upstream terms; never treat as relicensed by Rockytkg or by this snapshot |
| `firmware/st411sec_app.bin` | Vendor-copyrighted; explicitly **not** covered by Rockytkg GPL/LGPL grant | Preserved as evidence/reference only; do not assume redistribution, modification or incorporation rights |
| Firmware data embedded in `include/goodix_fw.h` | Vendor-copyrighted; explicitly **not** covered by Rockytkg GPL/LGPL grant | Same restriction as the binary firmware; do not treat embedded bytes as GPL material |
| Documentation and other files not explicitly covered by the upstream scope list | No blanket assumption beyond explicit notices | Use as reference/evidence; copy expressive material only after confirming applicable rights/per-file notices |

Licensing permission and project authorization are separate questions. Code may be legally reusable yet still be excluded from this project because it violates factory-preserving, no-flash, no-PSK-reprovisioning, no-persistent-write or other safety constraints.

## Project reuse rules

When code or expressive material from this snapshot is imported or adapted into the project:

1. identify the exact source file/path under `Rockytkg/`;
2. record the preserved source commit `227eba219fa9e3fbac5bd59aca79f624f67cd11b` unless a later snapshot is explicitly adopted;
3. verify the relevant per-file SPDX/license and any third-party origin before reuse;
4. preserve required copyright, attribution and license notices;
5. classify the resulting project component using the project provenance vocabulary where applicable (`IMPORTED_FROM_ROCKY`, `ADAPTED_FROM_ROCKY`, etc.);
6. keep GPL-only expression under applicable GPL-compatible terms; its placement does not convert it to LGPL, and a distributed fork/combined work must satisfy every applicable per-file license;
7. do not infer target-specific APP12509 behavior solely from Rockytkg implementation;
8. do not import unsafe device lifecycle, firmware-update/IAP, PSK provisioning, persistent-write or factory-state-changing behavior merely because its source code is license-compatible.

Facts learned from the snapshot may inform clean-room implementation and differential analysis, but factual protocol claims must still be classified according to the project's evidence hierarchy.

After the authentic D279/48 comparison, this snapshot is the primary
implementation reference for the production SIGFM path. Direct reuse or
minimal adaptation is preferred over independent reimplementation when the
per-file audit, dependency licenses and resulting distribution terms are
compatible. Local APP12509 evidence remains authoritative for sensor-reaching
behavior, and the factory-preserving exclusions above remain unchanged.

This policy update does not rewrite the provenance of any snapshot file. The
preserved upstream commit/tree, materialized submodule identity, per-file
licenses, copyright holders and vendor-firmware exclusions above remain the
same facts recorded when the snapshot was acquired.

## Documented local working-tree adaptations

The directory retains the immutable upstream identity above, but its current
Git working tree is not asserted to be byte-identical to that upstream tree.
D279/57 applies the project's bounded enrollment-completion hold to
`libfprint/libfprint/{fp-image-device-private.h,fp-image-device.c,fpi-image-device.c,fpi-image-device.h}`
so host-only tests exercise the same internal contract as the Fedora 44
production fork. This is local LGPL-2.1-or-later adaptation and does not alter
the preserved upstream commit/tree, original licensing, copyright, or the
historical facts of the materialized libfprint submodule.

## Snapshot maintenance rule

Do not silently replace this directory with a newer upstream state.

If the snapshot is refreshed:

- record the new upstream commit and tree;
- retain the previous snapshot through normal Git history;
- update this provenance file in the same change;
- re-check license scope, per-file SPDX notices, submodule commit and vendor-material exceptions;
- review whether new upstream behavior changes any project safety or implementation assumption.

## Important external discussion

Rockytkg issue #1 remains an external discussion/evidence source and is not contained in a normal Git clone of the repository:

`https://github.com/Rockytkg/goodix-linux-27c6-5125/issues/1`

Its claims remain external corroboration unless independently established by local project evidence.
