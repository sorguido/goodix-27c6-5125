# D274/03 parallel offline forward analysis — execution manifest

```text
ARTIFACT_CLASS=PARALLEL_OFFLINE_FORWARD_ANALYSIS
STEP=D274/03
SESSION_BRANCH=session/agent_83eeb7c1-37a4-4ceb-99c3-a831ea31d1ee
BASE_COMMIT=5964d9703d31ccbb3e71ef142bfd2394a37c9932
BASE_MATCHES_ORIGIN_MAIN=true
WORKING_TREE_CLEAN_AT_START=true

OUTCOME=PARALLEL_OFFLINE_FORWARD_ANALYSIS_COMPLETE
ADVANCEMENT=DIFFERENTIAL_LINUX_READINESS_MAP_PLUS_ONE_HOST_ONLY_SEAM
EXECUTABLE_CLOSURE=PARTIAL_SEAM_BUILD_BLOCKED_SANDBOX_TOOLCHAIN; FORBIDDEN_SYMBOL_AUDIT_PASS
RESIDUAL_BLOCKER_OR_RISK=SECOND_TARGET_CYCLE_UNOBSERVED; ORIENTATION_POLARITY_PPMM_UNRESOLVED; REAL_SIGFM_OPENCV_BUILD_BLOCKED; SEAM_BUILD_TOOLCHAIN_ABSENT_IN_SANDBOX
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
IMPLEMENTATION=IMPLEMENTED_ONE_SAFE_HOST_ONLY_SEAM
SEAM_PATH=libfprint-driver/goodix_capture_aggregation.{c,h}
SEAM_BUILD_VERIFICATION=BUILD_BLOCKED_SANDBOX_TOOLCHAIN_ABSENT; RUN_SCRIPT_READY_FOR_DEV_ENV; FORBIDDEN_SYMBOL_AUDIT_PASS

NEXT_HOST_ONLY_TASKS=[
  "Run run_goodix_capture_aggregation_test.sh in dev-env (flatpak Sdk) to confirm seam build/run PASS",
  "Build real SIGFM metric seam in OpenCV4-dev env and re-run D272 synthetic validation",
  "Study Rockytkg goodixgf.c as clean-room LGPL reference for libfprint device glue (exclude unsafe paths)",
  "Draft libfprint driver capture callback wiring the aggregator to fpi_image_device_image_captured()"
]

TARGET_EVIDENCE_DEPENDENCIES=[
  "Second full capture cycle after re-arm (REARM_0X32 -> IRQ2 -> 0x22 -> ACK -> image) on target",
  "Target timeout policy for finger-up / post-up / re-arm",
  "APP12509 physical ppmm / DPI and natural orientation + ridge/valley polarity",
  "Same/different-finger SIGFM score distributions to set a non-assumed threshold",
  "D274/03 Windows native qualification (Goodix absent) closing the second-cycle evidence"
]
```

## File prodotti (analysis/D274/)

- `D274_03_offline_forward_readiness_analysis.md` — report markdown (mappa, sez. B/C/D).
- `D274_03_offline_forward_matrix.json` — matrice machine-readable (18 componenti).
- `D274_03_offline_forward_seam_report.md` — dettaglio seam implementato.
- `D274_03_offline_forward_execution_manifest.md` — questo file.

## File implementati (libfprint-driver/, nuovi, non live-critical)

- `goodix_capture_aggregation.h`, `goodix_capture_aggregation.c`
- `tests/test_goodix_capture_aggregation.c`, `tests/run_goodix_capture_aggregation_test.sh`

## Verifiche eseguite

- `git status` all'inizio: working tree pulito, HEAD == origin/main.
- forbidden-symbol audit sul nuovo `.c`: PASS (nessun simbolo USB/TLS/I/O/persistent).
- tentativo di esecuzione harness: bloccato da `flatpak`/`gcc` assenti nel sandbox
  (condizione identica al blocco OpenCV4-dev di D272/D273).
- nessuna modifica a file D274/03 o live-critical (solo nuovi file + manuale).

## Non dichiarato

D274/03 NON è qualificato, NON è baseline-approved, NON è live-ready.
