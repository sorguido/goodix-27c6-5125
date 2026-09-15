<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D297/01 — risultato offline correttivo KScreenLocker dual deployment

Data: 15 settembre 2026

## Esito

Il correttivo bounded richiesto prima di Phase F è chiuso nel massimo grado
offline consentito. La candidate source-first al commit
`df2b8331c260ef3b26bd5483ee88b92d5c88bca5` gestisce ora persistentemente e
in modo reversibile anche `/etc/pam.d/kde-fingerprint`; il laptop reale è stato
classificato read-only come `HISTORICAL_D293_RUNTIME` e dispone di una patch
transitoria D289-derived che non sostituisce quel runtime.

Resta obbligatoria la Human Gate per installazione e vero unlock `Meta+L`.
Nessuna azione privilegiata, USB o biometrica è stata eseguita dall'AI.

## Evidence recovery e root cause

D289 aveva provato la sessione KWin/KScreenLocker realmente bloccata fino a
SIGFM MATCH, ma con un bind mount PAM temporaneo e ripulito a fine prova. Il
deployment source-first successivo gestiva solo `plasmalogin`; sul target
Fedora 44 `kde-fingerprint` continuava invece a usare il substack globale
`fingerprint-auth`, che con il profilo authselect corrente non raggiunge
`pam_fprintd`.

Il file `/etc/pam.d/kde-fingerprint` è posseduto direttamente da
`plasma-workspace-6.7.5-1.fc44.x86_64` come `%config(noreplace)`, con digest
package `8b3181ce5979f498e2cd07acaf3f57c63b1e2f9593e44bfa9027b6dd8bb62437`.
Non esiste un corrispondente file vendor sotto `/usr/lib/pam.d`.

## Delta implementato

- regola candidate `kde-fingerprint-pam.rule` con `pam_fprintd`, tre tentativi
  massimi e timeout bounded;
- trasformazione del solo auth stack, preservando account/password/session;
- state e hash distinti, install/update/rollback/uninstall/status simmetrici;
- pin di package owner, digest RPM, `%config(noreplace)`, metadata e layout;
- fail-closed su customizzazione, drift, collisione, `.rpmnew` o `.rpmsave`;
- nessuna modifica ad authselect, `fingerprint-auth`, driver, libfprint o
  fprintd;
- kit storico `operator_kit/d297-01-kscreenlocker-historical-runtime/` che
  applica soltanto il medesimo delta PAM e conserva un rollback exact-state.

## Verifiche PM indipendenti

| Confine | Evidenza | Esito |
|---|---|---|
| suite manager | 17 test synthetic-root | PASS |
| lifecycle | fresh, update da due legacy, rollback bidirezionale, uninstall, idempotenza | PASS |
| failure safety | collisioni, drift, tamper e due rollback parziali | PASS fail-closed |
| regressioni | `plasmalogin` preservato; authselect e `fingerprint-auth` non modificati | PASS offline |
| kit storico | sintassi Bash e status read-only sul target | PASS |
| host mode | `HISTORICAL_D293_RUNTIME`, PAM KScreenLocker vendor non patchato | DETERMINED |
| build | due build pulite complete | PASS |
| riproducibilità | candidate byte-identiche | PASS |
| integrità | allowlist esatta di 23 file e `sha256sum -c` completo | PASS |
| SBOM | SPDX 2.3 JSON: 38 package, 21 file, 59 relazioni | PASS |
| runtime binary | SHA-256 invariato rispetto a D296 | PASS |

Il digest comune dell'indice `SHA256SUMS` è
`2eef7a406f61b03b838562f68eb6531e986129231dd56a3a653f79749272c6a1`.
Il binario `libfprint-2.so.2.0.0` conserva lo SHA-256
`115db4450272435c80ecb61e3540577b99c8355fb02a0f1648175104a7c3dd20`.
Manifest e SBOM includono la nuova regola KScreenLocker. Le precedenti closure
runtime/ABI/licensing/privacy D296 restano valide perché il binario e il
licensing boundary non cambiano; il nuovo delta host PAM è coperto dalla
review e dalla suite sopra riportata.

## Confine della prova e decisione

La candidate è implementata, riproducibile e testata offline. La prova live
corrente deve restare sul runtime storico e dimostrare soltanto che il medesimo
delta PAM sblocca una sessione KDE realmente locked, senza migrare il laptop.
Un eventuale PASS non proverà la migrazione live completa alla candidate.

```text
D289_PATH_RECOVERED_AND_UNDERSTOOD=true
PRODUCTION_DEPLOYMENT_GAP_CONFIRMED=true
AUTHSELECT_GLOBAL_FINGERPRINT_UNCHANGED=true
FINGERPRINT_AUTH_GLOBAL_STACK_UNCHANGED=true
KDE_FINGERPRINT_MANAGED_INTEGRATION_PRESENT=true
INSTALL_UPDATE_REMOVE_ROLLBACK_TESTED=true
PLASMALOGIN_REGRESSION=false
DRIVER_LIBFPRINT_FPRINTD_CORE_CHANGED=false
ACTIVE_HOST_DEPLOYMENT_MODE=HISTORICAL_D293_RUNTIME
HISTORICAL_RUNTIME_REPLACED_AS_SIDE_EFFECT=false
CANDIDATE_MANAGED_FIX_OFFLINE_TESTED=true
LIVE_PROOF_SCOPE_EXPLICIT=true
REAL_KDE_LOCKED_SESSION_UNLOCK=AWAITING_HUMAN_GATE
SUDO_REGRESSION=AWAITING_HUMAN_GATE
HISTORICAL_RUNTIME_KSCREENLOCKER_LIVE_UNLOCK=AWAITING_HUMAN_GATE
CANDIDATE_FULL_LIVE_MIGRATION_TEST=DEFERRED_UNTIL_USER_MIGRATION
EXECUTABLE_CLOSURE=PASS_OFFLINE_MAXIMUM
PM_DECISION=HUMAN_REQUIRED
```
