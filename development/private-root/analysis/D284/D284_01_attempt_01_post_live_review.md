<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D284/01 Attempt 01 — review indipendente e decisione post-live

## Decisione

`PASS_LIVE_CLOSED`. La run prova sul target reale un'autenticazione biometrica
del consumer `sudo -v` attraverso il servizio PAM per-utente
`goodix-d284-01-sudo`, conservando il fallback password e ripristinando lo
stato host. Non prova login, lock screen, installazione permanente o
affidabilità statistica.

Il set canonico è
`captures/D284_01/D28401_ATTEMPT_01_20260911T053552Z_bc478f480be8/sanitized/`.
L'auditor ripetibile è
`analysis/D284/d284_01_attempt_01_evidence_audit.py`.

## Integrità e provenance

La baseline live è
`bc478f480be822c04ffc44ec9e7cd46420712f72`. Gli SHA-256 ricalcolati
coincidono con quelli forniti dall'operatore:

- `operator.log`: `9c0cbe489f83a5a5ddd1bfaeb76249e884fab7f36056e8592d1b7913ff5c2b19`;
- `summary.env`: `66a2a3416b7b90d0e78e343b6a602bd9496020cf14393cf592cb2d181029200d`;
- `terminal-transcript.log`: `476549872552d132d2abc535af8ad7f774778612f80c63eff8ea742efc3f27ff`.

Il capture contiene soltanto i tre file sanitizzati attesi. L'export dichiara
`TEMPLATE_INCLUDED_IN_EXPORT=false`; non contiene FP3 o immagini biometriche.

## Nesso causale `sudo` → PAM → fprintd → SIGFM

Il transcript attraversa Phase A, B e C; l'enrollment completa otto stage. Il
summary riporta `D284_01_SUDO_VALIDATE_RETURN_CODE=0`. Questo return code non è
usato da solo: il journal osserva, prima del delete, una vera epoch VERIFY e
un unico outcome SIGFM `match`, sul sample 1, score 14858 e threshold 40.

Il sorgente della baseline lega causalmente gli eventi. Installa prima il
servizio PAM con `pam_fprintd.so max-tries=1 timeout=45`, seguito da
`pam_unix.so`, e il solo override sudoers dell'utente; invalida il timestamp;
esegue esattamente `runuser ... env -u SUDO_ASKPASS sudo -v`; accetta il
risultato soltanto dopo il match nel journal; invalida nuovamente il timestamp
e rimuove gli override prima del delete. Il launcher invoca un secondo `sudo`
soltanto dopo la Phase C per esportare gli artefatti.

L'assenza di password durante il `sudo -v` testato è quindi `VERIFIED` dalla
combinazione di control-flow baseline, match live e return code zero. La
password inserita dopo Phase C per il secondo `sudo` di export non è visibile
nel transcript ed è classificata separatamente
`USER_OPERATOR_ATTESTED_EXPORT_ONLY`; non è elevata a osservazione del file.

## Lifecycle, safety e rollback

Le tre epoch distinte sono ENROLL, VERIFY e NONE/delete. Le prime due
consumano esattamente due action e due handshake TLS; i submit reali sono
204 + 75 = 279. Il valore enrollment differisce di uno da D283 ma, con action,
retry e reopen invariati, è coerente con variazione di polling/contatto e non
prova un retry. La terza epoch non consuma action, TLS o submit sensor-reaching.

Tutte le epoch riportano outstanding zero, backend drenato e context chiuso.
Retry, reopen, reset, clear-halt e famiglie persistenti note sono zero. Il
delete del solo template isolato è osservato. Il summary finale dichiara
servizio ripristinato, staging rimosso, libreria di sistema, authselect, PAM
preesistenti e storage preesistente invariati, override rimossi, timestamp
invalidato, rollback completo e return code zero. Lo zero delle famiglie
persistenti note resta telemetria su allowlist, non prova assoluta contro ogni
possibile effetto NVM sconosciuto.

## Closure

Il kit D284 è chiuso e i due entrypoint live rifiutano prima di build o
staging. L'auditor entra nel contratto offline con una regressione di tampering
semantico.

```text
OUTCOME=PASS_LIVE_CLOSED
ADVANCEMENT=REAL_SUDO_BIOMETRIC_AUTHENTICATION_COMPLETED
EXECUTABLE_CLOSURE=PASS_LIVE_WITH_HASH_PINNED_REVIEW_AND_ROLLBACK
RESIDUAL_BLOCKER_OR_RISK=PERSISTENT_SINGLE_CONSUMER_INTEGRATION_NOT_DESIGNED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE_PLUS_HASH_PINNED_PRIVATE_CAPTURE
NEXT_BOUNDARY=PERSISTENT_INTEGRATION_ARCHITECTURE_REVIEW
```
