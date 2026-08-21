<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D248 — Repository hygiene and structural consolidation

## Scope and preflight

D248 is offline repository hygiene only. It performed no hardware/USB access,
used no `sudo`, imported no Rockytkg code, and changed no runtime, protocol,
TLS, capture, image, AF/FDT, operator execution, safety, or licensing behavior.

| Check | Observed |
| --- | --- |
| canonical repository | `/workspace/goodix-27c6-5125-private` |
| branch | `work` (already separate from `main`) |
| expected/actual baseline | `9e19370d068a71ad0794fdb570aaf9693011ed78` / exact match |
| initial worktree | clean |
| tracked paths | 394 |
| root historical bundle pairs | 12 ZIPs plus 12 sidecars, D230–D239 |
| tracked generated artifacts | 25 `.pyc` files and two `.orig` backups |

The initial root listing and directory sizes were inspected before modification.
The largest project areas were `analysis/` (21 MiB), `src/` (432 KiB),
`tests/` (404 KiB), `operator_kit/` (96 KiB), and `poc/` (72 KiB), excluding
`.git`. No `.bak`, `.tmp`, `.pytest_cache`, or `.mypy_cache` tracked path was
found.

## Actions and risk matrix

| Path | Action | Rationale | Reference scan | Risk |
| --- | --- | --- | --- | --- |
| `.gitignore` | narrow generated-output policy added | private evidence remains trackable; ephemeral output does not | policy-only | low |
| tracked `**/__pycache__/*.pyc` (25) | removed | reproducible interpreter cache, never a fixture | path/type and tracked-file audit; no runtime dependency | low |
| `src/goodix5125_d233_backend.py.orig` | removed; `SAFE_TO_REMOVE_GENERATED_BACKUP` | generated backup introduced by D243 and reconstructible from Git | no textual references; history commit recorded | low |
| `src/goodix5125_d235_entrypoint.py.orig` | removed; `SAFE_TO_REMOVE_GENERATED_BACKUP` | generated backup introduced by D243 and reconstructible from Git | no textual references; history commit recorded | low |
| root D230–D239 ZIP/sidecars | classified, not moved | Codex Web binary-transfer constraint; preserve paired artifacts | every name scanned; references recorded in manifest | low pending mechanical move |
| `analysis/README.md` | created | concise canonical step index | paths checked | low |
| `operator_kit/README.md` | created | distinguishes consumed/superseded launchers; grants no authorization | manual and Dxxx reports reviewed | low |
| `src/`, `tests/`, `poc/` | README only; no move | freeze reproducible legacy D232–D246 chain | tree/path audit | low |
| manual, `AGENTS.md`, AI guidelines | policy integrated | makes organization durable without a second manual | canonical-document review | low |
| runtime `*.py`, `*.c`, `*.sh` | no content or mode change | functional diff prohibited | Git diff/path verification | none |

Both `.orig` blobs remain obtainable from commit
`1c66b43c63e21e2dc4547a903154167233731fdd` (blob IDs
`9a8ddec10e6176fb720b6f21aa243587daef7b51` and
`ad87f42de12f8a20ddb3009cd0ca8b744e8a1f39`). Their differences from current
sources are historical runtime evolution, not unique evidence in the backups.

## Binary relocation inventory

Every declared ZIP checksum equals the bytes currently tracked. Destinations
were absent, so there are no collisions. Historical status/report references
and sidecar self-references are non-blocking: a mechanical `git mv` must update
live path consumers where the manifest's `references` list identifies them,
while historical captured reports should not be retro-edited.

| Source | Destination | Git blob | SHA-256 of file | Bytes | Collision |
| --- | --- | --- | --- | ---: | --- |
| `D230_definitive_arbitrary_resident_memory_read_audit_bundle.zip` | `analysis/D230/D230_definitive_arbitrary_resident_memory_read_audit_bundle.zip` | `376f828b68a3bdc6cf8173243647fa3f262bf9f0` | `b98305437017ddf5fa8e06e150ccd2706a7f879635d85a23fc0ec39a3e62b51a` | 47281 | DESTINATION_ABSENT |
| `D230_definitive_arbitrary_resident_memory_read_audit_bundle.zip.sha256` | `analysis/D230/D230_definitive_arbitrary_resident_memory_read_audit_bundle.zip.sha256` | `6c27576fe0f012fadf5ad2e41f1b43a9557ce331` | `cd0e60fd1d3b9424f3a5c14e47c7e2a45c5104ff3d1d88fc89920498136a6d61` | 130 | DESTINATION_ABSENT |
| `D231_A2_70_cross_version_semantic_convergence_bundle.zip` | `analysis/D231/D231_A2_70_cross_version_semantic_convergence_bundle.zip` | `b11e29e51d9c7d35b50ac4b80009de44c8a66b5e` | `6af8dbef9d5efb0e4cbeeb7b4d7cfabc033e598fa073191b6d67dc8d352627df` | 22552 | DESTINATION_ABSENT |
| `D231_A2_70_cross_version_semantic_convergence_bundle.zip.sha256` | `analysis/D231/D231_A2_70_cross_version_semantic_convergence_bundle.zip.sha256` | `31457af736832c40ad883d7b96481672dd337fda` | `a80abb724b6f9dba1c8c87654d3ea52a17132895c32170fb492303e2cdc2247b` | 123 | DESTINATION_ABSENT |
| `D231_postseal_contract_repair_bundle.zip` | `analysis/D231/D231_postseal_contract_repair_bundle.zip` | `0d32dc20f45423d6abed7be04406484fec703b11` | `165e58a4acab9db162740367e42b84313f9f410acb3a08bd8e27a98d87a52b05` | 13585 | DESTINATION_ABSENT |
| `D231_postseal_contract_repair_bundle.zip.sha256` | `analysis/D231/D231_postseal_contract_repair_bundle.zip.sha256` | `a7673a743f84b4f1dcfeab6ac2b89d879cd0a6e6` | `751871d917ab2209270aea8462927aee37bc66dafc651864d882d98e79475214` | 107 | DESTINATION_ABSENT |
| `D232_exact_oem_replay_offline_hard_disabled_bundle.zip` | `analysis/D232/D232_exact_oem_replay_offline_hard_disabled_bundle.zip` | `a6d91894b446abd70309de28e0e0e5a2012381e6` | `f96b29249c1a2c1e08dbeba26c7cccfa5ca12c1339b805707e7f35fc6ce571b8` | 34645 | DESTINATION_ABSENT |
| `D232_exact_oem_replay_offline_hard_disabled_bundle.zip.sha256` | `analysis/D232/D232_exact_oem_replay_offline_hard_disabled_bundle.zip.sha256` | `78cb843f14a27ba6a3b38fa6875ce51be7ff14fa` | `4bd1d2158e8435afd122d8c016e39928ad312445379516da9eff946c07b6dcee` | 121 | DESTINATION_ABSENT |
| `D233_real_usb_tls_backend_offline_hard_disabled_bundle.zip` | `analysis/D233/D233_real_usb_tls_backend_offline_hard_disabled_bundle.zip` | `11f00561b35262516053cd38ebd38a3f44ac66a0` | `c749afdf27596202553f856268ed9a4ea3b8ec6220e27b1ce909c8f07271330a` | 45359 | DESTINATION_ABSENT |
| `D233_real_usb_tls_backend_offline_hard_disabled_bundle.zip.sha256` | `analysis/D233/D233_real_usb_tls_backend_offline_hard_disabled_bundle.zip.sha256` | `c7beda6e561e7edc612c5d7a7f0b5daf2ecd4470` | `ffabb318bd6b0fc7f74e9cd9bbb0027f4f430ae36f23348047804df57fcf48d3` | 125 | DESTINATION_ABSENT |
| `D233_runtime_binding_and_orchestrator_closure_bundle.zip` | `analysis/D233/D233_runtime_binding_and_orchestrator_closure_bundle.zip` | `0ac0f56e4b27eadc14bc4dc114a9672369ee1f25` | `3fca219ebf312997f039de0438a07500817c60162167126cf661fb6d819ba36a` | 67961 | DESTINATION_ABSENT |
| `D233_runtime_binding_and_orchestrator_closure_bundle.zip.sha256` | `analysis/D233/D233_runtime_binding_and_orchestrator_closure_bundle.zip.sha256` | `1c90f34a6e25640b2f82b12168330712cbb3af02` | `8714f8c8bb8459817f77045dfcdfc89d93b961f1f8f5349a8d4e4f68c4adab26` | 123 | DESTINATION_ABSENT |
| `D234_live_exact_oem_replay_tls_single_shot_bundle.zip` | `analysis/D234/D234_live_exact_oem_replay_tls_single_shot_bundle.zip` | `e516b41b098e56d8b67ee64bfa46fc0ee6f3497f` | `1991902232007b9898ab09b38e5d472976b340edad51cda3c1aa9d5b11317d86` | 6358 | DESTINATION_ABSENT |
| `D234_live_exact_oem_replay_tls_single_shot_bundle.zip.sha256` | `analysis/D234/D234_live_exact_oem_replay_tls_single_shot_bundle.zip.sha256` | `5373a2139eafafed3208c7f95beba2b1918e1ee0` | `5e411a3930817a836c148cad8dcd37db2ed3eea32ab233479972c403f792ea5f` | 120 | DESTINATION_ABSENT |
| `D235_real_live_entrypoint_offline_hard_disabled_bundle.zip` | `analysis/D235/D235_real_live_entrypoint_offline_hard_disabled_bundle.zip` | `44ee8b1a58622e7ef82c0c8a7daca5a491d1d117` | `0a5e4b042bdb9ba4c097cf55b2e5774c394982f53af288800e0ddc2a2a0d05ae` | 34920 | DESTINATION_ABSENT |
| `D235_real_live_entrypoint_offline_hard_disabled_bundle.zip.sha256` | `analysis/D235/D235_real_live_entrypoint_offline_hard_disabled_bundle.zip.sha256` | `748f14fe2869848dbc2aba4be7b1628c5e06fbbb` | `51bde433644ec650de28ea71166a5e6bb20d096057f276bbe14e74ed474f774e` | 125 | DESTINATION_ABSENT |
| `D236_live_exact_oem_replay_tls_single_shot_bundle.zip` | `analysis/D236/D236_live_exact_oem_replay_tls_single_shot_bundle.zip` | `8e743babc2a3b62cc38ef1c462fc4694249c924e` | `db50c97ab185b9d914b340541b975d79c4169105685811174894de350c01a918` | 29091 | DESTINATION_ABSENT |
| `D236_live_exact_oem_replay_tls_single_shot_bundle.zip.sha256` | `analysis/D236/D236_live_exact_oem_replay_tls_single_shot_bundle.zip.sha256` | `6c98b8631e5dc808b445350dfb21ca35a9fbef8f` | `60a01eac3f60cd7469d35d0713bec349b9cb56594159a09ab13902d4c6755791` | 120 | DESTINATION_ABSENT |
| `D237_live_exact_oem_replay_tls_single_shot_bundle.zip` | `analysis/D237/D237_live_exact_oem_replay_tls_single_shot_bundle.zip` | `057a7b40c7a7a1efc0d58f09a80894c10130a921` | `452d0a3c5a97492af295dfd705b49257db45b534bed3664402a7d183211a3a6e` | 6353 | DESTINATION_ABSENT |
| `D237_live_exact_oem_replay_tls_single_shot_bundle.zip.sha256` | `analysis/D237/D237_live_exact_oem_replay_tls_single_shot_bundle.zip.sha256` | `445d2eea7e309aa7d1cc6cdb91f0557a8ae9cf65` | `24c977db6df45b13a689b541b055f0fd9ca6794937414981b7ec449ec9119905` | 120 | DESTINATION_ABSENT |
| `D238_pre_d1_live_path_consolidation_bundle.zip` | `analysis/D238/D238_pre_d1_live_path_consolidation_bundle.zip` | `05053594b4bc8b7cec2b4de305edecccd35b2bfc` | `39c1254ca54de250bb4ee29cdaa033e729ed972de5fea683687343a50c53076a` | 18611 | DESTINATION_ABSENT |
| `D238_pre_d1_live_path_consolidation_bundle.zip.sha256` | `analysis/D238/D238_pre_d1_live_path_consolidation_bundle.zip.sha256` | `1134a187eb6a992c9f60fed9dc380c60400d69d7` | `e3f310289439e08142759ad6fef7d7da92b474b1ae78e78bc64aaeda15f71bad` | 113 | DESTINATION_ABSENT |
| `D239_operator_kit_executability_gate_bundle.zip` | `analysis/D239/D239_operator_kit_executability_gate_bundle.zip` | `72a2c129709e69e79775ace5d40a2a609faf0208` | `0afb408a09c4306622ad2396ee7fa8246d43557557786bc6bf10b7d7505f12bc` | 24693 | DESTINATION_ABSENT |
| `D239_operator_kit_executability_gate_bundle.zip.sha256` | `analysis/D239/D239_operator_kit_executability_gate_bundle.zip.sha256` | `23e220d9944b141229d1b3a2dbac6ac812793df2` | `4bc02b352648e19a414a93b1a8847aeb6a6995ccb96d1cf22a4c73cafa36a349` | 114 | DESTINATION_ABSENT |

The machine-readable manifest is
`analysis/D248/D248_binary_relocation_manifest.json`. The required action is a
paired, byte-preserving Git relocation of each ZIP and sidecar; D248 does not
perform it.

## Structural and licensing result

`analysis/` is indexed without becoming a second technical manual. No launcher
was moved or edited. `src/`, `tests/`, and `poc/` remain legacy/historical;
post-D247 work remains in GPL-2.0-or-later `core/`/`tools/` and the separate
LGPL-2.1-or-later `libfprint-driver/`. No legacy file was mass-relicensed.

## Verification

Static checks passed: JSON parsing and 24/24 manifest coverage, ZIP/sidecar
checksums, analysis index paths, no tracked generated artifacts, no runtime
content/mode changes, no moved legacy/runtime paths, `git diff --check`, and
bundle integrity. The full pytest collection is environment-blocked because
the optional `cryptography` package is not installed; this is the anticipated
offline environment limitation, not a D248 regression.

## Codex Web PR transport correction

The first D248 run produced local commit
`ac062270fc25c742e711a3f93ebd3545fb42ad35`, but did not create a Draft PR.
The remaining obstacle was not technical: Codex Web cannot transport the new
binary ZIP in the PR tree. The unchanged bundle is therefore carried
temporarily as the lossless Base64 file
`analysis/D248/D248_repository_hygiene_bundle.zip.b64`; its decoded SHA-256 and
ZIP integrity match the sidecar. The binary ZIP is absent from the PR tree and
must be restored from Base64, verified, and replace the temporary transport
file before the final baseline is merged.

## Closure

```text
OUTCOME=READY
ADVANCEMENT=REPOSITORY_HYGIENE_STATE_CHANGED_NO_FUNCTIONAL_OR_HARDWARE_ADVANCEMENT
EXECUTABLE_CLOSURE=NOT_APPLICABLE
RESIDUAL_BLOCKER_OR_RISK=PAIRED_BYTE_PRESERVING_ROOT_BUNDLE_RELOCATION_PENDING_AI_SUPERVISOR
CANONICAL_DOCUMENTATION=UPDATED
BUNDLE=analysis/D248/D248_repository_hygiene_bundle.zip
FUNCTIONAL_DIFF=NO
RUNTIME_PATHS_MOVED=NO
TRACKED_GENERATED_ARTIFACTS_REMOVED=YES
ORIG_AUDIT_COMPLETE=YES
ANALYSIS_INDEX_CREATED=YES
BINARY_RELOCATION_MANIFEST_READY=YES
READY_FOR_BINARY_RELOCATION=YES
DRAFT_PR_CREATED=NO
READY_FOR_DRAFT_PR=YES
PR_MERGED=NO
```
