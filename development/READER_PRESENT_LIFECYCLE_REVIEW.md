# R5 corrective: lifecycle and publication review

Internal review index for the corrective requested in
`CODEX_CORRECTIVE_SENSOR_PRESENT_AND_PUBLIC_DOCS.md`. Baseline:
`4f244fa2946da94406f03991332f8a70e9a8b401`. The canonical current state and
operator evidence remain in `Goodix 27c6 5125 manuale tecnico.md`.
This file is excluded from publication. No new release phase or live execution.

## Occurrence classification

Search covered source/scripts/Markdown for `no_sensor`, detach/disconnect,
reader/sensor absence, `SENSOR_CONNECTED`, USB sysfs and device identity.
Device identity alone is not an absence prerequisite. Private capture and
protected binary contents were not opened. Reference and archived source were
classified as reference/history, not as active lifecycle entrypoints.

| Surface | Classification and disposition |
| --- | --- |
| `deployment/recovery/manage.py`, `install.sh`, `uninstall.sh` | Active tooling lifecycle. Root/VM and software ownership gates retained; no USB presence check, USB I/O or fprintd command. Shared lifecycle lock prevents concurrent publication/removal. |
| `deployment/recovery/remove.py`, installed `goodix-uninstall`, `goodix-force-remove` | Active full removal. Standalone fixed paths; no imported/saved inverse. Normal receipt strictness and emergency partial-state tolerance preserved. Reader presence is irrelevant. Temporary service mask plus verified stop before runtime/label mutation; no start. |
| `deployment/minimal-runtime/deploy.py`, `install.sh`, `uninstall.sh`, newly saved inverse | Active component lifecycle, including material-label maintenance. Removed `no_sensor` and all sysfs checks. Temporary activation inhibition and inactive/MainPID 0/LoadState masked checks replace absence gate. Saved historical inverse is not used by the corrected full-removal/update procedure. |
| `deployment/plasma-login-opt-in/manage.py` | Active authentication integration install/uninstall. No presence check or USB operation. Current manager verifies original qualified binary/PAM inputs but publishes its corrected inverse. It never executes the original detached-reader manager. |
| Update | Remove with current standalone command, reinstall with current component managers. Existing recovery tools alone can be replaced with current tooling-only inverse plus install. No new updater or migration engine; final public packaging remains unavailable. |
| `deployment/plasma-login-opt-in/build-vm.sh` | Development-only VM compiler and synthetic module tests; its absent-reader guard is retained. Not called by active install/update/removal; qualified binaries are reused. Eligible source for review is not a public installation instruction. |
| `production/minimal-runtime/check-stock-attempts.sh` | Development-only synthetic fprintd attempt checker; absent-reader guard retained. Not an installed lifecycle dependency. |
| `deployment/minimal-runtime/r3_open_close.py` and its tests | Historical bounded live diagnostic, not a release management entrypoint. Preserved, not invoked. |
| Other `production/login`, `production/plasma-vt`, `production/sudo`, `production/polkit`, `deployment/managed-install` scripts | Superseded integration/build paths, excluded from active lifecycle and source export. No reuse or edits. |
| `deployment/*/test*.py`, upstream mock tests | Synthetic fixtures. Present-reader filesystem fixtures and forbidden USB access assertions deliberately retain VID/PID/sysfs strings. No real device open. |
| `docs/R5_INSTALL.md`, `deployment/recovery/R5_VM.md`, `deployment/recovery/README.md` | Active internal reader-present procedure, corrected. No unplug/unbind/hide instruction; all checkpoints self-contained. |
| `deployment/minimal-runtime/R3_*.md`, `R4_*.md`, `deployment/plasma-login-opt-in/R4_*.md`, component README histories, `docs/R4_PLASMA_LOGIN_INTEGRATION.md`, `docs/MINIMAL_RUNTIME.md`, `docs/STOCK_FPRINTD_ATTEMPTS.md`, `production/minimal-runtime/*.md` | Internal development evidence, excluded from publication. Previous absence requirements describe completed procedures, not current lifecycle. Component README headers explicitly route current work to corrected procedure. |
| `development/private-root/{analysis,operator_kit,src,core,tools,tests}`, `development/issues`, `development/tools`, `development/reference`, `development/Rockytkg` | Historical evidence/diagnostics, preserved and excluded. USB disconnect/reattach also describes transport events, not necessarily a lifecycle precondition. No blanket replacement. |
| `reference/`, `Rockytkg/`, `libfprint-driver/` device code | Protocol/driver identity, reference or transfer behavior. Driver device access is not installer device access. Selected source manifests unchanged. |
| Canonical Italian manual and roadmap | Internal authority/history. Current state updated; past evidence preserved and explicitly scoped. |
| Public documentation | Exact allowlist only. Stable architecture and reader-present contract; no internal VM recipe or detach prerequisite. Detailed document classification is in `development/documentation-history/PUBLIC_DOC_CLASSIFICATION.md`. |

The only executable absence gates remaining in the selected component/build
surface are the two development-only checks above. All active wrappers were
traced to their current Python entrypoint. No installer/remover imports a USB
backend, opens a device node, or starts fprintd. The service stop may cause an
already running daemon to perform its normal cleanup; that is not a new capture.

## Review answers and boundaries

| Required question | Answer |
| --- | --- |
| CAN_INSTALL_WITH_INTEGRATED_READER_PRESENT? | YES in corrected component paths and synthetic tests; real installation qualification pending. Public package not available. |
| CAN_UPDATE_WITH_INTEGRATED_READER_PRESENT? | YES for explicit remove/reinstall path; no separate public updater claimed. |
| CAN_NORMAL_UNINSTALL_WITH_INTEGRATED_READER_PRESENT? | YES, present-reader fixture and strict receipt tests. |
| CAN_FORCE_REMOVE_WITH_INTEGRATED_READER_PRESENT? | YES, active/inactive/partial-state tests; exact final real-system evidence remains pending. |
| DO_ANY_FINAL_RELEASE_PATHS_STILL_REQUIRE_DETACH_OR_USB_ABSENCE? | NO active lifecycle path. Development compiler/test guards are not lifecycle dependencies. |
| DO_PUBLIC_DOCS_READ_AS_PRODUCT_DOCUMENTATION_RATHER_THAN_DEVELOPMENT_LOG? | YES, stable English pages with explicit availability/limitations. |
| DO_PUBLIC_DOCS_DESCRIBE_ONLY_CURRENT_ARCHITECTURE? | YES; Fedora daemon/consumers, private libfprint libraries, minimal login selector. No private daemon/greeter/sudo/PolicyKit deployment. |
| ARE_INTERNAL_MILESTONE_DOCS_EXCLUDED_FROM_PUBLICATION? | YES, exact 17-page Markdown allowlist; no blanket docs/deployment/production export. |

Tests cover reader-present recovery-tool install/remove, runtime install/remove,
login install/remove, normal removal, active/inactive emergency removal, drift,
symlink/collision/receipt checks, partial state, preserved sentinel data/vendor
files, lock contention, mask ownership and failure/interruption paths. Foreign
cwd wrapper/installed-command and fixed interpreter/sudo arguments remain tested.
Service and privileged commands are simulated; no real runtime validation.

Independent review required and received local corrections for effective mask
state (including a shadowing unit), mask acquisition exceptions, shared tooling
lock, and self-contained post-removal checks. Unknown mask ownership is reported
and retained, never guessed. An unquiescent service retains runtime/material
state for diagnosis. No success result is printed before owned mask cleanup.

The TTY fallback source review found stock serialized PAM (no guaranteed immediate
password selector), and explicitly unsupported `27c6:5125` in retained Fedora
libfprint's hwdb allowlist. The actual guest console PAM chain is unverified.
The dedicated user check therefore keeps the reader physically present and
observes password login after project driver removal; it does not claim a
broken-hardware test or substitute hardware hiding.
