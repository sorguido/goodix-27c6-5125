# D274/02 — Windows native qualification closure report

Step: D274/02
Scope: packaging-only final closure (no behavioral change, no hardware, no Windows re-execution)
Authority: AI-PM reviewed third Windows operator run

## Authority (AI-PM reviewed third operator run)

```text
D274_02_WINDOWS_NATIVE_RESULT_ZIP_SHA256=4bbca10957dd30b672a76d84368303083a392eb18480a6d0c506045be313eaf0
SIDECAR_MATCH=PASS
ZIP_CRC=PASS
EXPECTED_RESULT_FILES=6/6
UNEXPECTED_RESULT_FILES=0
PRIVACY_SCAN=PASS
```

## Run history (correct interpretation)

Run 1 -> FAIL pre_gate: false-positive source scan PowerShell `-f`
  Root cause: generic regex `-f\s` matched the PowerShell format operator
  `(".d274-write-probe-{0}" -f [Guid]::NewGuid().ToString("N"))` instead of a
  TShark capture-filter. Tooling failure, not a Windows environment failure.
  Corrective: context-aware source contract (discovery allowlist only).

Run 2 -> FAIL selftest: scalar `.Count` under StrictMode PowerShell 5.1
  Root cause: `MODE_SELECTOR_PIPELINE_SCALAR_COUNT_UNDER_STRICTMODE` — the mode
  selector pipeline produced a scalar under `Set-StrictMode -Version 2.0`, and
  `.Count` on that scalar is unreliable on Windows PowerShell Desktop 5.1.
  Tooling/Kit defect, not a Windows environment failure.
  Corrective: force the mode selector result to always be an array via outer
  `@(...)`. Hard-disable source invariant preserved.

Run 3 -> PASS complete native offline qualification (AUTHORITATIVE)
  Real Windows 11 Home build 26200; Windows PowerShell Desktop 5.1.26100.8655.
  All native stages PASS. This run supersedes Run 1 and Run 2.

Run 1/2 are historical tooling failures and are NOT device-side problems. They
must not be reinterpreted as environment or sensor failures.

## Native stages (Run 3, authority)

```text
assert_windows_powershell_51=PASS
package_integrity=PASS
kit_source_contract=PASS
goodix_absence_gate=PASS
no_active_marker_gate=PASS
selftest=PASS
preflight=PASS
preauthorization_simulation=PASS
hard_disable_adversarial=PASS
```

## Windows native ACL privacy = PASS

```text
canonical_capture_root_match=true
reparse_point=false
acl_readable=true
broad_everyone_read_or_stronger=false
broad_builtin_users_read_or_stronger=false
broad_authenticated_users_read_or_stronger=false
broad_guests_read_or_stronger=false
write_probe_pass=true
WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=PASS
D274_02_OUTPUT_ROOT_PRIVACY_NATIVE=PASS
```

No ACL modified (no Set-Acl / icacls).

## Pre-authorization simulation = PASS

```text
synthetic_marker_lifecycle=PASS
authorization_consumed=false
real_capture_started=false
real_usb_open_count=0
real_finger_interaction_count=0
enrollment_commit_authorized=false
account_mutation_authorized=false
pin_mutation_authorized=false
```

## Native hard-disable adversarial test = PASS (fail-closed)

```text
subprocess_exit_code=1
expected_hard_disable_message_observed=true
no_capture_started=true
no_hardware_action=true
D274_REAL_CAPTURE_CAPABILITY=0
D274_HARD_DISABLED=true
authorization_consumed=false
D274_NATIVE_HARD_DISABLE_ADVERSARIAL_TEST=PASS
D274_HARD_DISABLE_NATIVE_BRANCH=PASS_FAIL_CLOSED
```

The nominal authorization branch fails with `HARD_DISABLED_D274_01` and
`D274_REAL_CAPTURE_CAPABILITY=0`; exit code 1 is the correct adversarial result.

## Safety closure (no hardware / live executed)

```text
REAL_CAPTURE_START_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_COMMAND_SEND_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
REAL_WINDOWS_ACCOUNT_MUTATION_COUNT=0
REAL_WINDOWS_ENROLLMENT_COMMIT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
D274_REAL_CAPTURE_CAPABILITY=0
D274_HARD_DISABLED=true
```

## Final closure

```text
D274_02_FINAL_NATIVE_CLOSURE=PASS
D274_02_WINDOWS_NATIVE_EXECUTION=COMPLETED
D274_02_WINDOWS_NATIVE_QUALIFICATION=PASS
D274_02_SELFTEST_NATIVE=PASS
D274_02_PREFLIGHT_NATIVE=PASS
WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=PASS
D274_02_PREAUTHORIZATION_SIMULATION_NATIVE=PASS
D274_NATIVE_HARD_DISABLE_ADVERSARIAL_TEST=PASS
D274_01_NATIVE_POWERSHELL51_MODE_SELECTOR=PASS_NATIVE
D274_01_NATIVE_POWERSHELL51_MODE_SELECTOR_CORRECTIVE=CLOSED
D274_01_STRICTMODE_PRESERVED=true
D274_02_FINAL_REVIEW=PASS
D274_02_STATUS=CLOSED
CORRECTIVE_REQUIRED=false
D274_02_FINAL_INTEGRITY_MANIFEST_SELF_CONSISTENT=PASS
D274_02_CORRECTED_KIT_CANONICAL_PACKAGE_BYTE_IDENTITY=PASS
```

## Second biometric cycle

D274/02 did NOT observe the second biometric cycle:

```text
D274_SECOND_CYCLE_TARGET_OBSERVATION=NOT_EXECUTED
SECOND_CYCLE_STATUS=TARGET_CAPTURE_NOT_OBSERVED_STATIC_COMPONENTS_PARTIALLY_VERIFIED
```

## Live authorization (must remain false)

```text
APPROVED_FOR_CAPTURE=false
BASELINE_APPROVED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
LIVE_EXECUTION=NOT_PERFORMED
```

## Next boundary (planning only, not execution)

```text
NEXT_PRIMARY_BOUNDARY=AI_PM_PLANNING_D274_03_ONE_SHOT_WINDOWS_OEM_CAPTURE
NEXT_BOUNDARY_PREREQUISITE=SEPARATE_AI_PM_LIVE_DESIGN_REVIEW_BASELINE_APPROVAL_AND_EXPLICIT_ONE_RUN_AUTHORIZATION
```

D274/02 does not enable real capture, does not remove hard-disable, and does
not authorize live. It does not open D274/03.
