<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D286/01 — review finale delle invocazioni retry

## Esito

```text
OUTCOME=PASS_LIVE_CLOSED
ADVANCEMENT=POST_REBOOT_PERSISTENCE_AND_REAL_SUDO_MATCH_CONFIRMED
EXECUTABLE_CLOSURE=PASS_LIVE_WITH_HASH_PINNED_REVIEW
RESIDUAL_BLOCKER_OR_RISK=OCCASIONAL_SAME_FINGER_NO_MATCH_REQUIRES_EXPLICIT_RETRY_POLICY
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
```

La prima VERIFY post-reboot resta l'autentico `NO_MATCH` già classificato:
112 keypoint, score massimo 14/40, otto confronti e una sola epoch drenata.
Gli audit persistenti avevano già chiuso il survival D285.

## Due invocazioni con failure host-side

Le capture `D28601_RETRY_20260911T192824Z_d1463b41ed26` e
`D28601_RETRY_20260911T193758Z_61c387b33b6f` terminano rispettivamente con
`USAGE` e `ATTEMPT_AUDIT_ARGUMENT_INVALID`. I commit `61c387b33b6f` e
`62808112777a` correggono i due usi non braced dei positional parameter Bash
oltre il nono argomento: prima `${10}`/`${12}`, poi `${11}`/`${13}`.

Entrambe le invocazioni avevano però già raggiunto una VERIFY. Il journal
read-only dello stesso boot `351d5424-2894-4d0c-ba9a-596c42481ab7` consente
di recuperare senza nuova azione sensore:

| Invocazione | Esito biometrico | Keypoint | Match | Epoch/safety |
| --- | --- | ---: | --- | --- |
| 1, `d1463b41ed26` | `MATCH` | 153 | sample 2, score 527/40, 2 confronti | 1 VERIFY, TLS 1, submit 76, retry/reopen/reset/clear-halt/persistent 0, drained |
| 2, `61c387b33b6f` | `MATCH` | 148 | sample 2, score 340/40, 2 confronti | 1 VERIFY, TLS 1, submit 77, retry/reopen/reset/clear-halt/persistent 0, drained |

Questi `MATCH` sono evidenza biometrica autentica recuperata dal journal, ma
non trasformano le due invocazioni in run chiuse: il return code sudo non è
stato catturato, l'audit root post-attempt non è terminato e manca il final
root audit. L'outcome complessivo di ciascuna resta quindi failure host-side.
Il successivo pre-audit della run finale e il relativo final audit provano che
lo stato persistente era ancora coerente dopo tali failure.

## Run finale riuscita

La capture `D28601_RETRY_20260911T194718Z_62808112777a` è completa. Pre-audit,
audit post-attempt e final audit sono PASS. Il primo e unico tentativo produce
`MATCH`, return code sudo 0, 160 keypoint, sample 1 score 75/40 e un confronto.
La sola epoch VERIFY ha un TLS, 76 submit, zero retry/reopen/reset/clear-halt o
famiglie persistenti e cleanup drenato/context-closed. Il fallback password
non viene raggiunto e lo stop sul primo match impedisce altri contatti.

## Conclusione metodologica permanente

Sul target, lo stesso dito/template ha prodotto prima 14/40 `NO_MATCH` e poi
527/40, 340/40 e 75/40 `MATCH`. Questo non misura FAR o FRR, ma prova che un
singolo `NO_MATCH` non è conclusivo nelle condizioni correnti.

I futuri kit che verificano un'impronta già enrollata devono offrire una
sequenza di almeno tre slot: un tentativo iniziale e almeno due retry fisici
espliciti dopo il primo `NO_MATCH`. Ogni slot resta separato e auditabile;
`MATCH` interrompe subito la sequenza, quindi non forza contatti ulteriori.
`PAM_ERROR`, `SAFETY_VIOLATION` o failure non biometrica fermano fail-closed.
Non sono ammessi retry automatici o impliciti sensor-reaching e tre esiti non
autorizzano generalizzazioni FAR/FRR.

D286 è chiuso e il suo entrypoint live non deve essere rieseguito.
