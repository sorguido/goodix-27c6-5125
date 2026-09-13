<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Analysis index

`analysis/` conserva output **step-local e non cumulativi**. Ogni nuovo output
Dxxx, incluso bundle e checksum, appartiene a `analysis/Dxxx/`; la root non è
usata per output di step. Lo stato qui riassunto descrive l'esito storico e non
costituisce autorizzazione live.

La review complessiva successiva alla chiusura D291 e la roadmap per le fasi
di integrazione, packaging e release sono in
`analysis/PROJECT_NEXT_STEPS_PLAN.md`. Phase B/B2 è il boundary offline corrente;
nessuna fase autorizza implicitamente live o modifiche del repository pubblico.

D292/01 chiude l'inventario A1; D292/02 chiude A3/A4 materializzando
`production/` come autorità di composizione e provando clean build normale,
ASan/UBSan e riproducibilità byte-for-byte; D292/03 chiude A5 e Phase A dopo
review PM diretta. Report correnti:
`analysis/D292/D292_01_PRODUCTION_SOURCE_INVENTORY.md` e
`analysis/D292/D292_02_SOURCE_OF_TRUTH_AND_REPRODUCIBLE_BUILD.md`, con closure
in `analysis/D292/D292_03_PHASE_A_CLOSURE.md`; manifest e validator sono
`D292_01_PRODUCTION_FILE_SET.json` e
`validate_d292_01_inventory.py`. Nessun file storico è stato spostato o
cancellato. Prossimo boundary:
`PHASE_B_B2_MULTI_USER_STORAGE_MODEL_AND_MULTI_FINGER_ANY_OFFLINE`.

D293/01 chiude B1 offline derivando dal vero fprintd 1.94.5 il contratto
utente/claim/PolicyKit/storage e separandolo dai cinque input runtime
system-wide protetti. Identifica come gap B2 il lifecycle rename/delete/name
reuse e la selezione `VerifyStart(any)` con più dita quando IDENTIFY è
disabilitato. Report e validator sono
`analysis/D293/D293_01_MULTI_USER_AND_RUNTIME_MATERIAL_CONTRACT.md` e
`analysis/D293/validate_d293_01_contract.py`; nessun contenuto protetto, USB o
live è stato raggiunto.

| Step | Sintesi | Stato storico | Report principale | Bundle |
| --- | --- | --- | --- | --- |
| D230 | Audit readback resident | READY / corpus esaurito | `analysis/D230/D230_definitive_arbitrary_resident_read_audit.md` | `D230_definitive_arbitrary_resident_memory_read_audit_bundle.zip` (temporaneamente in root) |
| D231 | Convergenza A2/70 e repair post-seal | READY | `analysis/D231/D231_safety_decision.md` | due bundle D231 temporaneamente in root |
| D232 | Exact OEM replay offline | READY offline | `analysis/D232/D232_exact_oem_replay_contract.md` | bundle D232 temporaneamente in root |
| D233 | Backend reale hard-disabled | READY offline | `analysis/D233/D233_closure_report.md` | due bundle D233 temporaneamente in root |
| D234 | Tentativo bloccato dall'unseal | BLOCKED | `analysis/D234/D234_review_summary.md` | bundle D234 temporaneamente in root |
| D235 | Entrypoint reale hard-disabled | READY offline | `analysis/D235/D235_test_report.md` | bundle D235 temporaneamente in root |
| D236 | Preflight e successiva evidenza parziale | SUPERSEDED / consumato | `analysis/D236/D236_review_summary.md` | bundle D236 temporaneamente in root |
| D237 | Sudo non predisposto | BLOCKED / consumato | `analysis/D237/D237_review_summary.md` | bundle D237 temporaneamente in root |
| D238 | Consolidamento pre-D1 | SUPERSEDED / consumato | `analysis/D238/D238_review_summary.md` | bundle D238 temporaneamente in root |
| D239 | Gate kit e primo B0 live | SUPERSEDED / consumato | `analysis/D239/D239_incident_and_root_cause.md` | bundle D239 mantenuto in root: eccezione di compatibilità executable closure D245 |
| D241 | Transizione TLS | SUPERSEDED / consumato | `analysis/D241/D241_technical_report.md` | `analysis/D241/D241_d1_direct_b0_tls_transition_bundle.zip` |
| D242 | Differenziale trasporto/pacing | SUPERSEDED / consumato | `analysis/D242/D242_technical_report.md` | `analysis/D242/D242_post_server_flight_causal_differential_bundle.zip` |
| D243 | Split trasporto A0/B0 | SUPERSEDED / consumato | `analysis/D243/D243_final_report.md` | `analysis/D243/D243_a0_b0_transport_split_regression_bundle.zip` |
| D244 | Controllo fresh-state | SUPERSEDED / consumato | `analysis/D244/D244_final_report.md` | `analysis/D244/D244_e4_timeout_forensic_fresh_state_control_bundle.zip` |
| D245 | A8→E4→TLS | SUPERSEDED / consumato | `analysis/D245/D245_final_report.md` | due bundle in `analysis/D245/` |
| D246 | TLS→D4 | READY / consumato | `analysis/D246/D246_report.md` | `analysis/D246/D246_bundle.zip` |
| D247 | Architettura licenze | READY | `analysis/D247/D247_license_architecture_migration.md` | `analysis/D247/D247_license_architecture_migration_bundle.zip` |
| D248 | Hygiene e indice strutturale | READY | `analysis/D248/D248_repository_hygiene_report.md` | `analysis/D248/D248_repository_hygiene_bundle.zip` |
| D249 | Core GPL offline AF→FDT→prima immagine | READY offline | `analysis/D249/D249_rocky_assisted_af_fdt_first_image.md` | `analysis/D249/D249_rocky_assisted_af_fdt_first_image_bundle.zip` |
| D250 | Rocky canonico + boundary exactly-one AF + run live | eseguito una volta e consumato; AE strutturalmente valida, abort nel validator byte0 | `analysis/D250/D250_report.md`; `analysis/D250/D250_live_operator_closure_report.md`; evidenza operatore non tracciata in `analysis/D250/D250_operator_live_stdout.json` | `analysis/D250/D250_bundle.zip`; `analysis/D250/D250_live_operator_closure_bundle.zip` |
| D251 | Post-mortem semantica AF + candidate one-shot corretto | PASS live, eseguito una volta e consumato; AF/AE con byte0 opaco 0 e flags `0x02` | `analysis/D251/D251_report.md` | `analysis/D251/D251_af_state_semantics_and_operator_closure_bundle.zip` |
| D252 | Audit precondizione fresh-FDT e restore | BLOCKED offline; nessun kit live | `analysis/D252/D252_fdt_precondition_restore_audit.md` | `analysis/D252/D252_fdt_precondition_restore_audit_bundle.zip` |
| D253 | Dataflow seed, restore post-FDT e semantica `0x22` | BLOCKED offline; core corretto a IRQ2→`0x22`, richiesta evidenza esterna | `analysis/D253/D253_fdt_seed_restore_cmd22_audit.md` | `analysis/D253/D253_fdt_seed_restore_cmd22_audit_bundle.zip` |
| D254 | Audit esterno FDT/cache/lifecycle | BLOCKED offline; bootstrap ridotto, restore non ridotto | `analysis/D254/D254_external_fdt_evidence_audit.md` | `analysis/D254/D254_external_fdt_evidence_audit_bundle.zip` |
| D255 | Evidenza Windows APP12509 correlata | run finale consumata e recuperata offline: capture 27.684 byte/218 frame, cache↔primo seed, zero-finger cancel e re-entry; nessuna nuova capture richiesta | `analysis/D255/D255_windows_targeted_evidence_capture_kit_report.md` | `analysis/D255/D255_windows_targeted_evidence_capture_kit_bundle.zip` |
| D256 | Contratto lifecycle USB D255 | READY offline; re-entry/re-arm senza restore USB esplicito e terminal-stop host/bus chiuso come quiescenza path-bounded | `analysis/D256/D256_usb_lifecycle_contract_audit.md` | `analysis/D256/D256_usb_lifecycle_contract_audit_bundle.zip` |
| D257 | Corrective exact fresh-bootstrap | BLOCKED exact offline: sottosequenza proiettata PASS storico, gate dinamici `0x50`/`0x82`/`0x20` non derivabili; first-`0x36` single-shot fail-closed; nessuna autorizzazione live | `analysis/D257/D257_fresh_fdt_candidate_live_readiness.md` | `analysis/D257/D257_exact_fresh_bootstrap_corrective_bundle.zip` (sostituisce il bundle D257 precedente, preservato) |

I bundle D230–D238 in root attendono la relocation meccanica byte-preserving
descritta dal manifest D248; ZIP e sidecar devono muoversi insieme. La coppia
D239 resta intenzionalmente in root perché il controllo offline D245 apre quel
path: rimuovere l'eccezione richiede migrazione e nuova verifica della closure.
