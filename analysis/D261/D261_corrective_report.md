# D261 corrective v2 — operational evidence hardening

The same-step corrective passes offline. The supported live path now requires distinct CLI-intent and post-marker Live-I/O capabilities; protected content is validated before marker consumption. All 24 negative rows and all 13 shared-reader/demux cases are execution-derived. Report publication is preflighted before side effects and durably uses a `0600` temporary file, file and directory fsync, and same-directory replacement.

The physical-tail decision is unchanged: `0x32` zero-tail is primary-target observed and accepted; `0x36/0x50/0x82/0x20` remain an unproven live hypothesis. No baseline was approved and no live action occurred.

```text
OUTCOME=READY_FOR_BASELINE_APPROVAL_REVIEW
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_OFFLINE
READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false
EXACT_APPROVED_LIVE_BASELINE_PRESENT=false
REAL_USB_OPEN_COUNT=0
REAL_SECRET_READ_COUNT=0
REAL_COMMAND_SEND_COUNT=0
FPRINTD_MUTATION_COUNT=0
REAL_SINGLE_USE_MARKER_CREATE_COUNT=0
```
