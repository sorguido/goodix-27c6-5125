<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D291/01 — closure offline multi-VERIFY dopo NO_MATCH

## Evidenza iniziale e root cause

Con PAM D285 portato dall'Utente a `max-tries=3`, la prima VERIFY reale
deliberatamente errata ha concluso correttamente con `NO_MATCH`; il successivo
`VerifyStart` esplicito di pam_fprintd è stato invece rifiutato con
`Goodix production open epoch already consumed; close/reopen required`.
L'audit osservato (`attempts=2 rejected=1`, una sola TLS/acquisizione) prova che
il consumer ha richiesto il secondo tentativo, ma il flag
`production_action_consumed` era ancora sticky per l'intero `FpDevice` open.

## Correzione minima

Dopo una VERIFY terminale normale, e soltanto dopo STOP post-TLS e drain del
backend, il driver:

1. rilascia claim USB e oggetti runtime/secure/post-TLS dell'epoch;
2. non avvia alcuna nuova acquisizione;
3. conserva aperto il device logico libfprint;
4. al successivo `VerifyStart` esplicito ricrea material view, claim, secure
   session e generazione USB puliti;
5. mantiene cancellation, errori non quiescenti e richieste concorrenti
   fail-closed.

Il teardown VERIFY viene completato al giro successivo del main loop: la
callback finger-off nasce dentro lo stack post-TLS e liberare sincronicamente
quell'oggetto produrrebbe use-after-free. La callback consumer viene quindi
emessa solo dopo la release completa dell'epoch precedente.

`reopen` mantiene il significato aggregato storico. Un nuovo campo
`explicit_verify_reopen` rende visibile il solo rollover richiesto dal consumer:
la prima epoch riporta `reopen=0 explicit_verify_reopen=0`; la seconda o terza
esplicita riporta `reopen=1 explicit_verify_reopen=1`. I contatori USB vengono
azzerati fra epoch solo dopo terminal fence e drain, senza reset o clear-halt.

## Verifica offline

Il test `/goodix/d291/explicit-multi-verify-after-no-match` copre:

- MATCH al primo VerifyStart e assenza di reopen/acquisizioni successive;
- NO_MATCH → secondo VerifyStart → MATCH;
- NO_MATCH → NO_MATCH → terzo VerifyStart → MATCH;
- tre NO_MATCH, tre sole acquisizioni e nessuna quarta;
- secondo VerifyStart concorrente rifiutato `FP_DEVICE_ERROR_BUSY`;
- una TLS e una acquisizione per richiesta esplicita;
- zero retry secure/post-TLS, reset, clear-halt e famiglie persistenti;
- claim/materiali rilasciati e backend drained dopo ogni epoch.

Risultati:

```text
FULL_DRIVER_NORMAL=28/28 PASS
FULL_DRIVER_ASAN_UBSAN=28/28 PASS
D285_D286_OFFLINE_CONTRACT=64/64 PASS
D291_OPERATOR_KIT_CONTRACT=12/12 PASS
PRODUCTION_BUILD_WITHOUT_TEST_SEAMS=PASS
PRODUCTION_ABI_PREFLIGHT=PASS
REAL_USB_ACCESS=0
REAL_SENSOR_ACCESS=0
```

## Stato e Human Gate

Il repository include il percorso minimo reversibile
`operator_kit/d291-01-multi-verify/`. Costruisce la candidate dal commit
pushato, sostituisce soltanto libfprint nel runtime D285, conserva rollback
automatico e consente un solo `sudo ls`: primo contatto volontariamente
NO_MATCH, secondo MATCH. Qualunque password prompt, audit diverso da due epoch
o contatore di safety non nullo fallisce e ripristina il runtime precedente.

```text
PM_DECISION=HUMAN_REQUIRED
D291_MULTI_VERIFY_IMPLEMENTED_OFFLINE=true
UPSTREAM_PAM_MAX_TRIES_3_SUPPORTED_OFFLINE=true
GOODIX_EXPLICIT_SECOND_VERIFY_SUPPORTED_OFFLINE=true
GOODIX_EXPLICIT_THIRD_VERIFY_SUPPORTED_OFFLINE=true
ONE_ACQUISITION_PER_VERIFY_START=true
STOP_ON_MATCH=true
NO_HIDDEN_RETRY=true
NO_FOURTH_VERIFY_FROM_MAX_TRIES_3=true
FACTORY_PRESERVING=true
LIVE_VALIDATION_REQUIRED=true
```
