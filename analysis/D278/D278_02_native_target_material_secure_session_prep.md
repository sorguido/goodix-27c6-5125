<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D278/02 — preparazione nativa target-material e secure session

## Risultato

D278/02 aggiunge host-only un binder C/OpenSSL LGPL verificato contro i cinque
KAT D190 indipendenti, un owner/loader protetto root:root 0600 race-resistant e
un parser PE confinato al tooling GPL. Il parser verifica il pin della DLL e
non la carica né esegue. Validator e PSK appartengono a un solo owner, sono
consegnati insieme al modello `GoodixSecureSessionMaterial` esistente e sono
azzerati al teardown; anche la copia E4 posseduta dal sequencer è ora liberata
con `OPENSSL_clear_free`.

Il CLI test-only espone `--self-test`, `--material-preflight-only` e
`--live-exact-secure-session`. Il preflight precede ogni seam USB e produce
solo JSON redatto. Il live mode resta terminalmente fenced in questa revisione
host-only (`CURRENT_LIVE_AUTHORIZED=false`): nessuna enumerazione/open/claim o
submit è stata eseguita. La state machine secure-session resta quella D278/01;
non sono stati aggiunti D4, application data, retry, reopen o reset.

## Autorità probatoria

* storico Python live: prova storica distinta, non nuova prova nativa;
* D277/02: target-proven solo A8/A0/APP12509;
* D278/01: sequenza completa e TLS provati host-only;
* D278/02: binder, PE gate, owner e build/preflight boundary provati host-only;
* sequenza nativa oltre A8 sul target, binding E4 live e TLS target: non provati.

## Riesame metodologico pre-live (preparazione, non autorizzazione)

1. **Cosa cambia?** D277/02 provava solo A8/A0; ora la sequenza D278/01 si può
   alimentare con materiale protetto reale, binder PSK→E4 nativo e timeout di
   fase bounded fino a TLS→STOP.
2. **Nuova ipotesi:** APP12509 accetta la sequenza C oltre A8, con E4 derivato
   dalla stessa PSK consegnata a OpenSSL, e raggiunge TLS 1.2 established senza D4.
3. **Se fallisce:** nessun retry/reopen/reset; si conserva la prima fase e
   classe d'errore redatta, si completa drain/cleanup/zeroization e si ritorna
   ad AI-PM. Nessun secondo tentativo equivalente è autorizzato.

`CURRENT_LIVE_AUTHORIZED=false`.

```text
OUTCOME=READY
ADVANCEMENT=NATIVE_D190_BINDER_AND_PROTECTED_MATERIAL_OWNER_HOST_ONLY_PROVEN
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=TARGET_PROTECTED_PREFLIGHT_NOT_EXECUTED;NATIVE_TARGET_SEQUENCE_BEYOND_A8_UNPROVEN;NEW_LIVE_AUTHORIZATION_REQUIRED
CANONICAL_DOCUMENTATION=MANUAL_UPDATED_D278_01_STATE_AND_D278_02_BOUNDARY
REVIEW_SET=BASELINE_52e190b2ceaee0e8de618accd4da9fadbad54115_PLUS_TRANSPORT_94a61c69_PLUS_D278_02_PATHS
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
CURRENT_LIVE_AUTHORIZED=false
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_FOR_D278_02_SINGLE_SHOT_NATIVE_SECURE_SESSION_TARGET_VALIDATION
```
