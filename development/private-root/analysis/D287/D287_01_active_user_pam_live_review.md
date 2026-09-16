<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D287/01 — review indipendente della live PAM active-user

## Decisione

```text
D287_LIVE_REVIEW=PASS
D287_ACTIVE_USER_MATCH=PROVEN
D287_POLKIT_CONTEXT_HYPOTHESIS=CONFIRMED
PM_DECISION=ACCEPT_AND_CONTINUE
OUTCOME=PASS_MATCH
ADVANCEMENT=ACTIVE_USER_SESSION_PAM_TO_REAL_GOODIX_MATCH_PROVEN
EXECUTABLE_CLOSURE=PASS_LIVE
RESIDUAL_BLOCKER_OR_RISK=NO_FAR_FRR_OR_ABSOLUTE_UNKNOWN_NVM_SIDE_EFFECT_CLAIM
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE_PLUS_HASH_PINNED_PRIVATE_CAPTURE
```

## Integrità e provenance

La capture `D28701_ACTIVE_USER_PAM_20260911T224657Z_e77f6dc1b4c9` dichiara
la baseline completa `e77f6dc1b4c9bbad54eedfa13bfd672de7e05317`, uguale al
commit che contiene runner e launcher live. `sha256sum -c capture.sha256`
passa per tutti i nove file elencati. I digest ricalcolati coincidono con i
valori forniti dall'operatore; `capture.sha256` stesso ha digest
`2e35e05fb9c5e69560795590a2f52101d8e9f96427e07520b2f6ef573cb9cf13`.

## Evidenza indipendente

- `context.env` e `pam-runner.log` osservano UID 1000 e cgroup
  `/user.slice/user-1000.slice/user@1000.service/app.slice/...`, non la
  precedente sessione root/background.
- Il sorgente baseline costruisce `--process PID,start-time,UID` dal medesimo
  processo che prosegue a PAM. Il log osserva return code `0` da `pkcheck` per
  `net.reactivated.fprint.device.verify`, senza user interaction.
- Il journal diagnostico mostra un print registrato, selezione device,
  `About to call VerifyStart`, completion di `VerifyStart` e infine
  `verify-match`. Non compare `Authorization denied ... ListEnrolledFingers`.
- Runner PAM: start/authenticate/end `0/0/0`.
- Epoch: totale/VERIFY `1/1`; action attempts/rejected/consumed `1/0/1`;
  TLS/first-image/real-submit `1/1/75`.
- SIGFM: extract 157 keypoint, 8 sample dichiarati, una comparazione sul sample
  1, score 128/40, outcome MATCH e `matched_sample=1`; match/no-match `1/0`.
- retry/reopen/reset/clear-halt/persistent `0/0/0/0/0`; outstanding/drained/
  context-closed `0/1/1`.
- I root audit pre/post sono PASS e hanno boot ID identico; host PAM write
  count è zero, cleanup temporaneo e tutte le pipeline di export ritornano
  zero, template escluso.

La riga kernel `did not claim interface 1 before use` non è ignorata: nella
stessa epoch il percorso completa MATCH, outstanding zero, drained e close.
Non prova un side effect persistente e non contraddice i contatori osservati;
resta diagnostica USB host da non generalizzare ad assenza assoluta di rischi.

## Causalità qualificata

La run precedente aveva subject UID 1000 ma cgroup/sessione logind root
`background-light`, negazione Polkit su `ListEnrolledFingers` e zero VERIFY.
Questa run cambia il contesto causale, supera sia il preflight esatto sia la
chiamata fprintd reale e raggiunge VERIFY/MATCH. Per questo host, policy e
azione:

```text
ROOT_BACKGROUND_LOGIND_CONTEXT_CAUSED_PREVERIFY_POLKIT_DENIAL=true
ACTIVE_USER_SESSION_CONTEXT_RESOLVES_POLKIT_VERIFY_AUTHORIZATION=true
```

`persistent=0` significa zero famiglie persistenti note nella telemetria; non
viene promosso a prova assoluta della NVM. Un solo match non misura FAR/FRR.
