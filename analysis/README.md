<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Analysis index

`analysis/` conserva output **step-local e non cumulativi**. Ogni nuovo output
Dxxx, incluso bundle e checksum, appartiene a `analysis/Dxxx/`; la root non è
usata per output di step. Lo stato qui riassunto descrive l'esito storico e non
costituisce autorizzazione live.

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
| D250 | Rocky canonico + boundary exactly-one AF + operator closure same-step | protocollo READY offline; live path hard-gated pronto per review baseline, hardware non eseguito | `analysis/D250/D250_report.md`; `analysis/D250/D250_live_operator_closure_report.md` | `analysis/D250/D250_bundle.zip`; `analysis/D250/D250_live_operator_closure_bundle.zip` |

I bundle D230–D238 in root attendono la relocation meccanica byte-preserving
descritta dal manifest D248; ZIP e sidecar devono muoversi insieme. La coppia
D239 resta intenzionalmente in root perché il controllo offline D245 apre quel
path: rimuovere l'eccezione richiede migrazione e nuova verifica della closure.
