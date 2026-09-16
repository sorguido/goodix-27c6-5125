<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D276/02 — rescue FpImageDevice host-only

## Closure v2.5

```text
OUTCOME=READY
ADVANCEMENT=HOST_ONLY_EXECUTABLE_VALIDATION_PASS_CLEAN_TREE
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL_UNRESOLVED;TLS_SESSION_LIFETIME_ACROSS_LIBFPRINT_ACTIVATIONS_UNRESOLVED;ENROLLMENT_STAGE_POLICY_NOT_SELECTED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_MAIN_54fa55835ec5192aa794c1302d2e4a7e2fab0fcf_PLUS_VALIDATED_CHECKED_IN_TREE_87d4aacec23b5415cca5de73e0dfeb83ffe65bab_PLUS_BRANCH_d276-02-github-actions-validation_DOCUMENTATION_CLOSURE
```

## Classificazione e stato

`WIP_CLASSIFICATION=B`: il device shell era salvabile e il standalone subset
rimane proporzionato perché esercita il vero `FpImageDevice` 1.94.5. Il rescue
ha corretto fake/test e semantiche asincrone; la successiva validazione GitHub
Actions sul clean checked-in tree ha ora chiuso executable closure host-only.

```text
LOCAL_LIBFPRINT_DEVICE_GLUE_SLICE_1=IMPLEMENTED_CORRECTIVE_EXECUTABLY_CLOSED_HOST_ONLY
FPIMAGE_DEVICE_REAL_FRAMEWORK_USED=true
IN_MEMORY_BACKEND_ONLY=true
D276_02_HOST_ONLY_EXECUTABLE_VALIDATION=PASS_CLEAN_TREE
```

## Root cause del rescue

Confermate:

```text
ROOT_CAUSES_CONFIRMED=
SYNCHRONOUS_DEACTIVATION_EXPECTATION;
ACTIVATING_CANCELLABLE_DISCONNECTED;
GERROR_OWNERSHIP;
LAUNCHER_FAILURE_MASKING;
NONQUIESCENT_CANCEL_MASKED_AS_INACTIVE;
STALE_GENERATION_TEST_NOT_PROBATIVE;
SIGFM_ORDERING_RACE;
STAGE_POLICY_PROMOTION;
NULLABLE_CANCELLABLE;
NON_IDEMPOTENT_REARM
```

Respinta:

```text
ROOT_CAUSES_REJECTED=STANDALONE_SUBSET_HARNESS_FUNDAMENTALLY_UNSALVAGEABLE
```

## Correzioni implementate e validate host-only

- Il cancellable dell'azione libfprint è collegato al `GCancellable` di
  activation e disconnesso phase-correttamente.
- È introdotta una deactivation fake trattenibile per rendere osservabile e
  bounded il caso `DEACTIVATING`.
- Ai confini `GError` si applica `g_steal_pointer()` o una copia owned.
- Il launcher propaga failure normal/sanitizer e supporta un ambiente host
  nativo quando le dipendenze richieste sono disponibili, mantenendo il path
  Freedesktop SDK quando presente.
- La cancellazione dopo activation invalida la generation e lascia il context
  `POISONED` quando la deactivation è non-quiescente; la normale deactivation
  conclusa non è avvelenata.
- Gli eventi fake sono associati al token della generation corrente; la guardia
  `OLD_GENERATION_CALLBACK_TEST=REAL_N_MINUS_1_TOKEN` scarta callback stale.
- Il re-arm è exactly-once per generation (`REARM_EXACTLY_ONCE=IMPLEMENTED_PER_GENERATION`).
- L'assegnazione Goodix dei cinque stage resta rimossa:
  `ENROLLMENT_STAGE_POLICY=NOT_SELECTED`.

```text
GERROR_OWNERSHIP_AUDIT=CORRECTED_AND_HOST_ONLY_VALIDATED
ACTIVATING_CANCEL_PHASE_CORRECT=HOST_ONLY_VALIDATED
DEACTIVATING_TEST_OBSERVABLE_AND_BOUNDED=true
NONQUIESCENT_CANCEL_POISON_POLICY=IMPLEMENTED_HOST_ONLY_VALIDATED
OLD_GENERATION_CALLBACK_TEST=REAL_N_MINUS_1_TOKEN
REARM_EXACTLY_ONCE=IMPLEMENTED_PER_GENERATION
LAUNCHER_PROPAGATES_FAILURE=true
```

Queste validazioni riguardano esclusivamente la shell host-only e le sue
state-machine/test seams. Non provano quiescenza del device reale, lifetime TLS
fra activation multiple né comportamento hardware di cancellation.

## Executable validation GitHub Actions

La precedente condizione `BLOCKED_ENVIRONMENT_VALIDATION` era specifica
dell'ambiente di rescue privo dei metadata di build necessari ed è superata.
La closure è stata eseguita sul clean checked-in tree seguente:

```text
CI_PROVIDER=GITHUB_ACTIONS
CI_WORKFLOW=.github/workflows/d276-fpimage-device-host-only.yml
CI_RUN_ID=33165906857
CI_VALIDATED_COMMIT=87d4aacec23b5415cca5de73e0dfeb83ffe65bab
CI_DIAGNOSTIC_PATCH=NONE
EXECUTION_ENVIRONMENT=HOST_NATIVE_FALLBACK
NORMAL_TEST_RUN=PASS
SANITIZER_TEST_RUN=PASS
TESTS_PER_NORMAL_RUN=14/14_PASS
TESTS_PER_SANITIZER_RUN=14/14_PASS
DETERMINISM_RUNS=2
D276_02_HOST_ONLY_EXECUTABLE_VALIDATION=PASS_CLEAN_TREE
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
```

Il workflow verifica il tree pulito prima dell'esecuzione e lancia due volte il
launcher checked-in. Ogni iterazione compila il subset reale `FpImageDevice`
1.94.5, esegue il forbidden-symbol audit, i 14 test normali e i medesimi 14 test
con ASAN/UBSAN. Entrambe le iterazioni sono PASS.

La futura esecuzione sul Fedora target, quando disponibile, è soltanto una
conferma cross-environment host-only aggiuntiva e non è un gate retroattivo:

```text
D276_02_FEDORA_HOST_CONFIRMATION=NOT_RUN_OPTIONAL_NON_GATING
TARGET_PC_AVAILABLE=false
```

## Safety e limiti ancora aperti

Il backend validato è esclusivamente in-memory. GitHub Actions non dispone né
usa il sensore target e non esegue USB Goodix, TLS reale, PSK, fprintd,
registrazione VID:PID o mutazioni persistenti.

```text
REAL_USB_ACCESS=false
REAL_SENSOR_COMMAND_COUNT=0
REAL_TLS_HANDSHAKE_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
VID_PID_PRODUCTION_REGISTRATION=false
LIVE_AUTHORIZED=false

PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL=UNRESOLVED
TLS_SESSION_LIFETIME_ACROSS_LIBFPRINT_ACTIVATIONS=UNRESOLVED
ENROLLMENT_STAGE_POLICY=NOT_SELECTED
```

`PASS_HOST_ONLY` non promuove nessuno di questi boundary a risolto e non
autorizza una run live.

## Prossimo confine

D276/02 è chiuso host-only. La roadmap torna quindi al successivo slice già
previsto dall'architettura D276:

```text
NEXT_PRIMARY_BOUNDARY=D276_03_A0_B0_CLEANROOM_SINGLE_RECEIVE_SYNTHETIC_TRANSCRIPTS
LIVE_AUTHORIZED=false
```
