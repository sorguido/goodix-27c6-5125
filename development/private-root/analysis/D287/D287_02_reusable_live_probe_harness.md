<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D287/02 — reusable Live Probe Harness, closure offline

```text
OUTCOME=PASS_HOST_ONLY
ADVANCEMENT=MATERIAL_ARCHITECTURAL_AND_REPOSITORY_ADVANCEMENT
EXECUTABLE_CLOSURE=PASS_OFFLINE_REFERENCE
RESIDUAL_BLOCKER_OR_RISK=EACH_FUTURE_LIVE_PAYLOAD_STILL_REQUIRES_BOUNDARY_SPECIFIC_REVIEW_AND_HUMAN_GATE
CANONICAL_DOCUMENTATION=UPDATED_V2_8
REVIEW_SET=GIT_NATIVE
LIVE_EXECUTION_PERFORMED=false
```

Il common harness vive in `operator_kit/live_probe/`; il riferimento D287
eseguito resta storico e non viene riscritto. La fixture
`experiments/offline-reference` è esplicitamente non-live e dimostra il
contratto comune con config e payload piccoli.

Responsabilità comuni chiuse: root/branch/HEAD/origin e dirty critical set per
operator-run, Human Gate UX, conferma, budget passati al payload, singola
invocazione, zero retry del harness, timeout/signal, pre/post audit, cursor e
journal opzionali, stream sanitizzato, capture, cleanup, summary, hash,
failure propagation e classificazione della telemetria comune.

Il payload deve applicare i limiti ricevuti prima del sensor-reaching e gestire
release/reseal specifici. Il classifier common verifica budget handoff,
contatori, zero famiglie persistenti note e cleanup drenato/chiuso. Questo
separa correttamente enforcement specifico e orchestration senza fingere che
una validazione post-hoc possa rendere sicuro un payload arbitrario.

Test policy:

```text
PAYLOAD_ONLY_CHANGE=LOCAL_TESTS_PLUS_COMMON_COMPATIBILITY
COMMON_HARNESS_CHANGE=FULL_HARNESS_REGRESSION
MILESTONE_OR_HIGH_RISK_PRELIVE=FULL_RELEVANT_SAFETY_REGRESSION
```

La prima suite completa conteneva sette test; il primo payload reale ha poi
richiesto due estensioni comuni non isolabili localmente: offline compatibility
test anche per esperimenti live e cardinalità cleanup multi-epoch. La full
regression aggiornata contiene nove test, aggiungendo outcome multipli/context
drained multipli e pathspec Git con spazi. Reference da cwd esterna, rifiuto
live della fixture, budget exact/superati, invocazione unica, timeout senza
retry, `SIGINT`, cleanup/post-audit/capture e manifest restano PASS.
`bash -n` e `git diff --check` passano. Nessuna dipendenza nuova e nessuna live
sono state introdotte.
