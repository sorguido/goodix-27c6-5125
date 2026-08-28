<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D276/02 — rescue FpImageDevice host-only

## Closure v2.5

```text
OUTCOME=BLOCKED_ENVIRONMENT_VALIDATION
ADVANCEMENT=HOST_ONLY_CORRECTIVE_IMPLEMENTATION_AND_NEW_STATE_MACHINE_TEST_SEAMS
EXECUTABLE_CLOSURE=NOT_REACHED_ENVIRONMENT_LACKS_REQUIRED_BUILD_METADATA
RESIDUAL_BLOCKER_OR_RISK=REQUIRED_NORMAL_AND_ASAN_UBSAN_RUNS_NOT_EXECUTED;PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL_UNRESOLVED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=CANONICAL_MAIN_2e3fa20443542b9f06c080393b6c9123dea4436b
```

## Classificazione e stato

`WIP_CLASSIFICATION=B`: il device shell è salvabile; il standalone subset
rimane proporzionato perché esercita il vero `FpImageDevice` 1.94.5, ma fake e
test richiedevano semantiche asincrone osservabili e token espliciti.

```text
LOCAL_LIBFPRINT_DEVICE_GLUE_SLICE_1=IMPLEMENTED_CORRECTIVE_NOT_EXECUTABLY_CLOSED
FPIMAGE_DEVICE_REAL_FRAMEWORK_USED=true
IN_MEMORY_BACKEND_ONLY=true
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

## Correzioni implementate

- Il cancellable dell'azione libfprint è collegato al `GCancellable` di
  activation e disconnesso phase-correttamente.
- È introdotta una deactivation fake trattenibile per rendere osservabile e
  bounded il caso `DEACTIVATING`.
- Ai confini `GError` si applica `g_steal_pointer()` o una copia owned.
- Il launcher usa timeout e restituisce failure se la run normal o quella
  sanitizer fallisce (`LAUNCHER_PROPAGATES_FAILURE=true`).
- La cancellazione dopo activation invalida la generation e lascia il context
  `POISONED` (`NONQUIESCENT_CANCEL_POISON_POLICY=IMPLEMENTED`); la normale
  deactivation conclusa non è avvelenata.
- Gli eventi fake sono associati al token della generation corrente; la guardia
  `OLD_GENERATION_CALLBACK_TEST=REAL_N_MINUS_1_TOKEN` scarta callback stale.
- Il re-arm è exactly-once per generation (`REARM_EXACTLY_ONCE=IMPLEMENTED_PER_GENERATION`).
- L'assegnazione Goodix dei cinque stage è rimossa:
  `ENROLLMENT_STAGE_POLICY=NOT_SELECTED`.

```text
GERROR_OWNERSHIP_AUDIT=CORRECTED_STATIC_AUDIT
ACTIVATING_CANCEL_PHASE_CORRECT=IMPLEMENTED_NOT_RUNTIME_VALIDATED
DEACTIVATING_TEST_OBSERVABLE_AND_BOUNDED=true
```

## Limite di verifica

L'ambiente non contiene `flatpak`; inoltre `pkg-config` non trova GLib/GIO/
GObject. Il launcher non può quindi compilare qui. Sono passati soltanto check
statici shell/Python/diff. La milestone resta
`BLOCKED_ENVIRONMENT_VALIDATION`, senza affermazione READY.

```text
FLATPAK_AVAILABLE=false
FREEDESKTOP_SDK_25_08_AVAILABLE=false
HOST_GLIB_DEV_METADATA_AVAILABLE=false
NORMAL_TEST_RUN=NOT_RUN_ENVIRONMENT_BLOCKED
SANITIZER_TEST_RUN=NOT_RUN_ENVIRONMENT_BLOCKED
DETERMINISM_RUNS=0
```

## Safety

Il backend è esclusivamente in-memory. Nessun accesso USB, comando sensore,
TLS, secret, fprintd, registrazione VID:PID o mutazione persistente è presente
o è stato eseguito.

```text
REAL_USB_ACCESS=false
REAL_SENSOR_COMMAND_COUNT=0
REAL_TLS_HANDSHAKE_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
VID_PID_PRODUCTION_REGISTRATION=false
LIVE_AUTHORIZED=false
```

## Prossimo confine

```text
NEXT_PRIMARY_BOUNDARY=HOST_ONLY_D276_02_EXECUTABLE_VALIDATION
```
