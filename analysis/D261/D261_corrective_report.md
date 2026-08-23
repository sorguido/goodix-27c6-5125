# D261 corrective v4 — import purity and pre-secret ordering

The same-step corrective passes offline. The bounded supported import path contains 16 repository-local Python files; both executed package initializers are now baseline-gated and synthetic drift is detected. A fresh unprivileged subprocess imports the closure with zero USB, protected-filesystem, real-secret, fprintd and marker side effects.

Manifest/config90 and cache hash/layout/CRC validation now precede real-secret loader construction and materialization. Offline rehearsal injects only a synthetic boundary through the protocol seam: the concrete real loader is never instantiated, no real-to-synthetic fallback exists, and all required non-secret failures stop with secret, marker and USB counts at zero.

The physical-tail decision is unchanged: `0x32` zero-tail is primary-target observed and accepted; `0x36/0x50/0x82/0x20` remain an unproven live hypothesis. No baseline was approved and no live action occurred.

```text
OUTCOME=READY_FOR_BASELINE_APPROVAL_REVIEW
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_OFFLINE
LIVE_IMPORT_CLOSURE_STATUS=PASS
NO_IMPORT_TIME_SIDE_EFFECTS=true
NON_SECRET_CONTENT_VALIDATED_BEFORE_SECRET_MATERIALIZATION=true
READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false
EXACT_APPROVED_LIVE_BASELINE_PRESENT=false
REAL_USB_OPEN_COUNT=0
REAL_SECRET_READ_COUNT=0
REAL_COMMAND_SEND_COUNT=0
FPRINTD_MUTATION_COUNT=0
REAL_SINGLE_USE_MARKER_CREATE_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0
```
