# D274/03 parallel offline forward analysis — execution manifest (post AI-PM corrective)

```text
ARTIFACT_CLASS=PARALLEL_OFFLINE_FORWARD_ANALYSIS
STEP=D274/03
SESSION_BRANCH=session/agent_83eeb7c1-37a4-4ceb-99c3-a831ea31d1ee
BASE_COMMIT=5964d9703d31ccbb3e71ef142bfd2394a37c9932
BASE_MATCHES_ORIGIN_MAIN=true
WORKING_TREE_CLEAN_AT_START=true

OUTCOME=READY_FOR_AI_PM_REVIEW
ADVANCEMENT=DIFFERENTIAL_LINUX_READINESS_MAP_AND_FRAMEWORK_RESPONSIBILITY_CLOSURE
EXECUTABLE_CLOSURE=NOT_APPLICABLE
RESIDUAL_BLOCKER_OR_RISK=SECOND_TARGET_CYCLE_UNOBSERVED; ORIENTATION_POLARITY_PPMM_UNRESOLVED; REAL_SIGFM_BUILD_NOT_AVAILABLE; LIBFPRINT_DEVICE_GLUE_NOT_IMPLEMENTED
CANONICAL_DOCUMENTATION=UPDATED
BUNDLE=analysis/D274/D274_03_offline_forward_bundle.zip
BUNDLE_SHA256=SEE_EXTERNAL_SIDECAR

D274_03_OPERATOR_KIT_MODIFIED=false
LIVE_CRITICAL_SET_MODIFIED=false
REAL_USB_OPEN_COUNT=0
REAL_COMMAND_SEND_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
BASELINE_APPROVAL=false

IMPLEMENTATION=SKIPPED_NO_INDEPENDENT_SAFE_SEAM
LIBFPRINT_ENROLLMENT_AGGREGATION=FRAMEWORK_OWNED_VERIFIED
PROJECT_EXTRA_FPIMAGE_AGGREGATOR_REQUIRED=false
LOCAL_LIBFPRINT_DEVICE_GLUE=NOT_YET_IMPLEMENTED

WINDOWS_NATIVE_QUALIFICATION_ROLE=HOST_ONLY_EXECUTABLE_QUALIFICATION_WITH_GOODIX_ABSENT
WINDOWS_NATIVE_QUALIFICATION_CLOSES_SECOND_CYCLE_EVIDENCE=false
FUTURE_D274_03_LIVE_ROLE=EXPLICIT_ONE_SHOT_SECOND_CYCLE_OBSERVATION_ONLY
TARGET_TIMEOUT_SEMANTICS_CLOSED_BY_SUCCESSFUL_D274_LIVE=false

ROCKY_GOODIXGF_LICENSE=LGPL-2.1-or-later
ROCKY_GOODIXGF_DIRECT_REUSE_POSSIBLE_AFTER_PER_FILE_AUDIT=true
GPL_TO_LGPL_EXPRESSION_CROSSING_ALLOWED=false
```

## Due ruoli distinti di D274/03 (BLOCKER 1)

- `D274_03_WINDOWS_NATIVE_QUALIFICATION_WITH_GOODIX_ABSENT`: qualifica solo la
  parte host-only eseguibile (PowerShell 5.1 runtime, Git/repo gate,
  TShark/USBPcap/preflight, ACL/privacy, selector/same-run gates, simulazione
  pre-authority, hard-disable / host-side executable closure). Il sensore è
  assente → **non può osservare né chiudere l'evidenza del secondo ciclo**.
- `FUTURE_D274_03_EXPLICITLY_AUTHORIZED_LIVE_ONE_SHOT_WITH_GOODIX_ATTACHED`:
  solo dopo qualification PASS + AI-PM freeze review + baseline approval +
  autorizzazione esplicita, osserverà `0x32` re-arm ACK → second `IRQ0002` →
  second `0x22` → ACK `0x01` → second fingerprint `B0` → STOP. Boundary stretto
  = *second-cycle existence/order after re-arm*. Non è una campagna biometrica o
  di timing: un live riuscito non prova il timeout semantico del device.

## File prodotti (analysis/D274/)

- `D274_03_offline_forward_readiness_analysis.md` — report markdown (mappa, sez. B/C/D, due ruoli D274/03).
- `D274_03_offline_forward_matrix.json` — matrice machine-readable (18 componenti, dipendenze causalmente corrette).
- `D274_03_offline_forward_seam_decision.md` — perché il seam precedente è stato rimosso dopo review AI-PM.
- `D274_03_offline_forward_execution_manifest.md` — questo file.

## Nullità di seam (BLOCKER 2)

I 4 file `libfprint-driver/goodix_capture_aggregation.{c,h}`,
`tests/test_goodix_capture_aggregation.c`,
`tests/run_goodix_capture_aggregation_test.sh` aggiunti nello step precedente
sono stati **rimossi**. Non sono stati sostituiti da alcun altro seam.
`IMPLEMENTATION=SKIPPED_NO_INDEPENDENT_SAFE_SEAM`.

## Verifiche eseguite

- `git status` all'inizio: working tree pulito, HEAD == origin/main.
- rimossi solo i 4 file di seam non giustificati; corretti report/matrix/manuale.
- nessuna modifica a file sotto `analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/` né a live-critical.
- live-critical `invoke-d274-03-live-once.ps1` blob SHA invariato: `fca3c40d4a3fcd7c6c21ce6809de794d69908e7a`.

## Non dichiarato

D274/03 NON è qualificato, NON è baseline-approved, NON è live-ready. Il candidato
resta congelato per la qualification nativa successiva.

## Dipendenze da evidenza target (correttamente scisse)

```text
D274_03_ONE_SHOT_BOUNDARY=[
  "Second full capture cycle after re-arm: 0x32 re-arm ACK -> second IRQ0002 -> second 0x22 -> ACK 0x01 -> second B0 -> STOP"
]

SEPARATE_FUTURE_TARGET_EVIDENCE_NOT_CLOSED_BY_D274_03_ONE_SHOT=[
  "Target timeout policy for finger-up / post-up / re-arm (NOT proven by a successful bounded D274 live)",
  "APP12509 physical ppmm / DPI and natural orientation + ridge/valley polarity",
  "Same/different-finger SIGFM score distributions to set a non-assumed threshold",
  "Production matching threshold",
  "Verify quality"
]
```

## NEXT_HOST_ONLY_TASKS

```text
NEXT_HOST_ONLY_TASKS=[
  "Build real SIGFM metric seam in OpenCV4-dev env and re-run D272 synthetic validation",
  "Audit Rockytkg src/goodixgf.c per-file (SPDX/copyright/origins/provenance) then adapt/reuse OR independently implement the libfprint device glue; exclude unsafe and GPL-only portions",
  "Draft libfprint device glue delivering each captured image via fpi_image_device_image_captured() with no separate aggregator"
]
```
