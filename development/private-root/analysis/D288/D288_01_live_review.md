<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D288/01 — review indipendente della live KScreenLocker active-user

## Decisione

```text
D288_LIVE_REVIEW=PASS
D288_KSCREENLOCKER_MATCH_TO_UNLOCKED=PROVEN
PM_DECISION=ACCEPT_AND_CONTINUE
OUTCOME=PASS_MATCH
ADVANCEMENT=KSCREENLOCKER_ACTIVE_USER_FINGERPRINT_MATCH_TO_UNLOCKED_PROVEN
EXECUTABLE_CLOSURE=PASS_LIVE_FOR_KSCREENLOCKER_TESTING_PATH
RESIDUAL_BLOCKER_OR_RISK=REAL_LOCKED_SESSION_AND_SDDM_LOGIN_NOT_PROVEN
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE_PLUS_HASH_PINNED_PRIVATE_CAPTURE
```

## Integrità e provenance

La capture
`d288-active-user-kscreenlocker_20260912T053427Z_4b819a566f39` dichiara la
baseline completa `4b819a566f39abec6bf3e88c8c89743880388b1a`, che esiste ed è
il commit contenente il payload live. `sha256sum -c capture.sha256` passa per
tutti i quattordici file elencati; `capture.sha256` ha digest
`fbbf34b4706ce3d872e8473917b229adb4c5c4b0f53dd0a8e1814f48d1ecf5ae`.

## Evidenza verificata

- `summary.env` chiude harness, payload, sanitizer, tee, cleanup, journal,
  post-audit e i due classifier con return code zero e risultato `PASS`.
- `payload-details.env` e la telemetria osservano un solo tentativo, un solo
  contatto e MATCH al tentativo 1; non esiste un secondo slot.
- Il greeter è nel cgroup utente
  `/user.slice/user-1000.slice/user@1000.service/app.slice/...`, non in
  `user-0` o `system.slice`. Il runtime gate della baseline richiede inoltre
  sessione grafica e runtime utente attivi prima del payload.
- `greeter-1.log` contiene una sola interposizione del service esatto
  `kde-fingerprint`, `Locked at ...` e un solo `Unlocked`. Il sorgente baseline
  inoltra ogni service diverso, inclusi `kde` e `kde-smartcard`, al vero
  `pam_start()` senza redirect.
- Il journal contiene una sola epoch VERIFY: action attempts/rejected/consumed
  `1/0/1`, TLS/first-image/real-submit `1/1/75`.
- SIGFM estrae 133 keypoint, dichiara otto sample e confronta in ordine i
  sample 1, 2 e 3 con score 0, 38 e 146 alla soglia 40; l'unico outcome è
  MATCH sul sample 3.
- retry/reopen/reset/clear-halt/persistent sono `0/0/0/0/0`; outstanding è
  zero, drained e context-closed sono uno.
- Gli audit root pre/post sono integralmente PASS nello stesso boot. Runtime,
  wrapper, scope authselect, fallback password, ownership del template,
  libfprint di sistema e uninstall readiness restano coerenti; entrambi gli
  audit contano zero action sensore proprie.
- Il payload usa un confdir PAM sotto la directory privata effimera e non
  contiene mount o scritture sotto `/etc/pam.d`; cleanup greeter e rimozione
  del workdir comune sono completati.

## Causalità e limiti del claim

Il classifier baseline accetta MATCH soltanto con la congiunzione di una epoch
Goodix valida, un outcome SIGFM MATCH, il marker di redirect fingerprint, un
solo `Unlocked` e return code zero del greeter. Questo chiude il percorso
esercitato:

```text
KScreenLocker --testing
→ kde-fingerprint
→ pam_fprintd
→ fprintd
→ Goodix VERIFY
→ SIGFM MATCH
→ KScreenLocker Unlocked
```

La capture non registra eventi tastiera. L'assenza di password/PIN digitati è
quindi attestazione dell'operatore, coerente con l'istruzione catturata e con
il percorso fingerprint completo, ma non è promossa a telemetria macchina.
Non risultano redirect del service password né evidenza di uso della password;
la causalità tecnica del PASS resta vincolata alla congiunzione sopra.

`persistent=0` significa zero famiglie persistenti note osservate, non prova
assoluta dell'assenza di side effect NVM sconosciuti. La modalità `--testing`
non è un vero lock orchestrato e non crea una sessione SDDM: né unlock di una
sessione realmente bloccata né login SDDM sono provati da D288.

## Primo live del reusable harness

D288 è la prima esecuzione reale di `operator_kit/live_probe/`. Per il percorso
esercitato sono PASS gate/provenance, budget handoff, invocazione singola,
timeout/signal framework, pre/post audit, capture/sanitizzazione, journal,
cleanup, summary/hash e classificazione comune. Questa prova valida il metodo
riusabile sul payload D288; non generalizza automaticamente a payload futuri o
a lifecycle incompatibili.
