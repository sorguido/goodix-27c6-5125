# D278/02 — Native target-material boundary + single-shot secure-session harness — host-only preparation

**REASONING:** HIGH

## 1. Authority, repository and mandatory starting state

Work only in the canonical private repository. Determine the real repository root first:

```bash
git rev-parse --show-toplevel
```

Then read, in this order:

1. `<git-root>/Linee Guida di Progetto Goodix 27c6 5125 per AI.md`
2. `<git-root>/AGENTS.md`
3. `<git-root>/Goodix 27c6 5125 manuale tecnico.md`
4. `analysis/D278/D278_01_native_secure_session_host_only.md`
5. `analysis/D278/D278_01_native_secure_session_host_only.json`
6. `analysis/D277/D277_02_native_a8_real_usb.md` and `.json`
7. the D232/D245 evidence referenced below
8. `docs/LICENSING_AND_PROVENANCE.md`

The manual is always canonical at:

```text
<git-root>/Goodix 27c6 5125 manuale tecnico.md
```

On the operator workstation this corresponds to:

```text
/home/guido/Repository/goodix-27c6-5125_private/Goodix 27c6 5125 manuale tecnico.md
```

Keep this manual recursively and organically updated during the task. Do not leave new knowledge only in chat, a report, or a Dxxx appendix. Update high/canonical sections whenever the project state changes; add a D278/02 subsection only where useful. Preserve index, tables, explanations and historical chronology. Do not turn the manual into an append-only task log.

Expected canonical starting point:

```text
branch: main (or a task branch created exactly from main)
main HEAD: 52e190b2ceaee0e8de618accd4da9fadbad54115
working tree: clean
```

The D278/01 corrective canonical commit is:

```text
5030c66e67db5a7f6cedfbf3bb0deeec107e79db
```

It was merged by PR #32 into the main commit above. Corrective GitHub Actions evidence is:

```text
D276 native TLS and async USB host-only
run: 33239781874
result: success

D276 USB router host-only
run: 33239781860
result: success
```

If the repository is dirty, if the starting commit is not the expected canonical baseline, or if the task branch is not based exactly on that baseline, **stop before modifying files and report the discrepancy**. Do not reset, clean, rebase, amend, or discard user work.

Do not invoke `git commit`, `git push`, merge, rebase, force-push, PR administration or any remote mutation yourself. If the Codex platform materializes a task branch/commit automatically outside your control, report the resulting ref/SHA accurately; do not perform additional Git administration.

---

## 2. Absolute safety invariant

The project invariant remains:

```text
factory_firmware_and_persistent_state_must_remain_untouched
```

This task is **host-only preparation**. It does **not** authorize target execution.

During this task there must be:

```text
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
USB_OPEN_COUNT=0
USB_CLAIM_COUNT=0
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
```

Do not enumerate/open/claim the real fingerprint reader for purposes of this task. Do not run any D277/D278 live mode, even if hardware unexpectedly exists in the environment.

Never execute or introduce a path that performs:

- flash, IAP, ClearApp, firmware replacement;
- OTP/factory/persistent writes;
- PSK provisioning/replacement;
- persistent VID:PID/mode changes;
- reset/recovery/reopen/retry behavior;
- D4 or any post-TLS application command;
- AF/FDT/finger/image/enroll/fprintd/PAM work;
- installation or registration of a production `27c6:5125` libfprint driver;
- `sudo`, `setfacl`, `chmod`, `chown`, udev changes or service changes during this cloud task.

The future live harness may be **compiled**, but must never be executed in a sensor-reaching mode in this task.

---

## 3. Current proven boundary — do not redesign what is already closed

D277/02 target-proved the native A8/A0 path through the real target:

```text
GUsb/libfprint-owned USB
-> FpiUsbTransfer
-> GoodixFpiUsbBackend
-> GoodixUsbRouter
-> A0
-> exact A8
-> ACK
-> typed APP12509 response
```

D278/01 already implements and host-only proves the complete native C/LGPL secure-session sequencer:

```text
A8
-> E4
-> A2_1
-> CHIP_82
-> OTP_A6
-> A2_2
-> MODE_70
-> DAC_220
-> DAC_236
-> DAC_238
-> DAC_23A
-> CONFIG_90
-> D1
-> B0/TLS 1.2 PSK
-> TLS ESTABLISHED
-> STOP
```

It already owns the exact A0 codec, response gates, one-IN/one-OUT constraints, fixed-64 B0 egress with zero tail, 10 ms inter-record pacing, OpenSSL TLS 1.2 PSK and the corrected D1→TLS advancement gate.

**Do not create a second protocol sequencer, second A0/B0 parser, second TLS implementation, or parallel USB transport.** Reuse the existing production-shaped native components.

D4 must remain structurally unreachable from the D278 secure-session module and from the new bounded harness.

---

## 4. Objective of D278/02

Build the smallest technically sound **native target-material boundary and test-only single-shot target harness** required to make a future, separately authorized D278/02 live validation possible.

The result of this task must stop at:

```text
HOST-ONLY PREPARATION READY
```

It must **not** claim target proof beyond the already proven A8/A0 boundary.

The future live experiment that this task prepares is exactly:

```text
one open/claim epoch
-> A8
-> E4 using a validator derived from the same factory PSK later handed to TLS
-> A2_1
-> 82
-> A6
-> A2_2
-> 70
-> 80 x4
-> 90
-> D1
-> TLS 1.2 PSK established
-> STOP
-> cancel/drain if needed
-> release/close
```

with:

```text
D4_REACHABLE=false
APPLICATION_DATA_COUNT=0
FINGER_PATH_REACHABLE=false
IMAGE_PATH_REACHABLE=false
RETRY_COUNT=0
TRANSPORT_REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
```

---

## 5. First required action: canonically close the D278/01 corrective state

Before adding D278/02 knowledge, reconcile the stale `PENDING` fields that remain in the D278/01 manual/report with the now-observed repository state.

The AI-PM review of the D1→TLS corrective is **PASS**. The corrective GitHub Actions run `33239781874` is **PASS**. The canonical corrective commit is `5030c66e67db5a7f6cedfbf3bb0deeec107e79db`, merged into canonical main at `52e190b2ceaee0e8de618accd4da9fadbad54115`.

Update `analysis/D278/D278_01_native_secure_session_host_only.{md,json}` and the corresponding canonical manual state so they no longer claim corrective review/CI pending.

Preserve all historical chronology and the fact that the initial pre-corrective CI evidence was run `33237274978` on `0efa30f...`.

Do **not** rewrite D278/01 as target-proven. It remains host-only beyond A8/A0.

---

## 6. Canonical target-material facts

Use local project evidence as authority. Relevant canonical facts include:

### Target identity

```text
VID=0x27c6
PID=0x5125
APP=GF_ST411SEC_APP_12509
```

### Protected runtime material paths historically used by the project

```text
/var/lib/goodix-5125-poc/transport-material.bin
/var/lib/goodix-5125-poc/target-material-manifest.json
/var/lib/goodix-5125-poc/target-config-90.bin
```

The cloud environment is not expected to contain these real protected files. Their absence is **not** a reason to contact hardware or fabricate replacements.

### Canonical hashes / pins

```text
transport-material.bin:
  length = 88
  magic = G5125POC
  sha256 = eb47bbed40e079ca780cd9cd4b2324520a67584ad3d576674914152fd6080a75
  factory PSK slice = bytes 24..55 inclusive (32 bytes)

target-material-manifest.json:
  sha256 = 1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15

target-config-90.bin:
  length = 224
  sha256 = e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82
  finalizer = 519a LE
  tuple offsets = 117, 121, 125, 129
  DAC values = d80b, be00, bd00, bc00

E4 validator sha256:
  1fa642d3f190e7074d1db201aa32ee8f34e41d69d55797158b9480affb3d0b87

A2 response sha256:
  39e469ce5a5ba3136c4a44381f2e4183dca275257adfcf3c0025094f05c022f5

82 response sha256:
  82537d2c108887baef128b47ad401fc888d54b184673b1fc23811d79ab6d5703

A6 response sha256:
  d7e81a415aa5e7b0168c9a632756d1dc8b7b47346cc0a44dc68796f854c2b92b
```

Relevant evidence to read includes at minimum:

```text
analysis/D232/D232_target_material_manifest.json
analysis/D232/D232_target_material_provenance.md
analysis/D245/D245_A8_E4_contract.json
src/goodix5125_d232_offline.py
```

Do not copy the Python runtime implementation into the LGPL driver. Treat it as historical implementation/evidence according to the licensing rules below.

---

## 7. D190 PSK→E4 binding — mandatory provenance decision before implementation

The E4 validator must be produced from the **same 32-byte PSK instance/origin** that is handed to the native TLS server. A stale historical `MATCH` or a separately persisted validator is not sufficient.

The repository contains the recovered D190 project reference under:

```text
poc/goodix5125/tools/binding_reference/
  crypto_reference.py
  pe_parser.py
  runtime.py
  known_answers.py
```

Before adapting any expression from those files, perform a repository-local provenance audit using Git history and the licensing documentation. In particular verify the relevant historical revision and rights rather than assuming the current directory's default license.

Known historical evidence to verify, not blindly trust:

```text
historical commit: b475a6eca72e340816779afae917334a6146c986
repository license at that revision: BSD-2-Clause
```

If and only if the audit confirms that the exact project-authored expression you intend to adapt was available under a license compatible with the destination, record the source commit/path/license/copyright/destination/changes in `docs/LICENSING_AND_PROVENANCE.md`.

If that provenance cannot be demonstrated cleanly per file, **do not move or translate the expression into LGPL**. Choose a compatible tool-only boundary or stop and report the blocker.

### Required architectural judgment

Do not mechanically place the entire historical PE parser into the production libfprint path.

Explicitly evaluate the smallest design that satisfies both target validation and future maintainability. The preferred shape, unless evidence argues otherwise, is:

```text
LGPL/native reusable crypto binder:
    secret32 + two producer seed[6] inputs
    -> validator[32]

harness/tooling-only read-only producer-material acquisition:
    canonical gfusb.dll (hash-gated, never executed)
    -> seed_a[6] + seed_b[6]
    -> immediately consumed by binder
```

This keeps a permanent `gfusb.dll` parsing/runtime dependency out of the production `FpImageDevice` path while still allowing the D278/02 target-validation harness to derive E4 natively.

A different design is allowed only if it is technically better and the report/manual explain why.

### Forbidden shortcuts

Do not:

- persist a raw E4 validator as a new file;
- persist extracted producer seeds as a new file;
- print PSK, validator, producer seeds, raw envelope, raw CONFIG90 or raw OTP in logs/reports/tests;
- add real factory PSK or raw target response bodies to Git;
- silently hard-code previously intentionally unexposed producer seed values merely for convenience;
- make the production libfprint driver permanently depend on `gfusb.dll` without an explicit, strongly justified architectural decision.

The canonical `gfusb.dll` reference is:

```text
analysis/D230/work/GoodixExport/gfusb.dll
sha256 = 904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2
```

It may be parsed as bytes for host-only/KAT purposes. It must never be loaded or executed.

Use the five synthetic/non-factory D190 known-answer vectors already in `known_answers.py` to prove the native binder. Do not generate a circular test whose expected output comes from the implementation under test.

---

## 8. Native protected-material boundary requirements

Implement a minimal native owner/loader boundary suitable for later target use without weakening the existing protected-store policy.

The real production wrapper must require protected files to be:

```text
regular file
non-symlink
uid = 0
mode = 0600
```

Use race-resistant read-only opening where available (`O_RDONLY`, `O_CLOEXEC`, `O_NOFOLLOW`), then `fstat()` and same-inode/metadata checks before trusting content. Do not alter ownership or permissions.

Avoid adding a JSON dependency solely to parse the target manifest if it is unnecessary. It is acceptable to verify the exact canonical manifest file hash and use already-canonical non-secret metadata constants in native code, provided the rationale is explicit and all existing D232 correlations remain enforced.

At minimum validate before any future USB open:

1. protected manifest exact hash;
2. CONFIG90 length 224 and exact SHA-256;
3. CONFIG90 finalizer rule/value;
4. all four DAC register/value/offset correlations;
5. transport material length, magic and exact SHA-256;
6. extract exactly one 32-byte PSK from the canonical slice;
7. verify canonical `gfusb.dll` hash before extracting producer material;
8. derive E4 validator in memory from that PSK;
9. verify the derived validator SHA-256 equals the D232 target pin;
10. construct the existing `GoodixSecureSessionMaterial` without creating a second protocol model.

### Ownership and zeroization

Introduce an owning object/structure with explicit lifetime. Project-owned sensitive buffers must be wiped on every success/failure path before free.

At minimum treat as sensitive:

```text
factory PSK
D190 intermediate producer/derived key material
D190 envelope/intermediate crypto state under project ownership
E4 validator derived from the factory PSK
producer seeds after use
```

Do not claim zeroization of OpenSSL internal copies that the project does not control.

After `GoodixSecureSession` has successfully taken the material it needs, the external loader's PSK copy must not remain live unnecessarily.

Audit the existing `goodix_secure_session_free()` path: if a future factory-derived E4 validator would currently be freed without explicit cleansing, harden that project-owned buffer with an appropriate explicit zeroization and add regression coverage. Keep this fix minimal and do not broaden it into unrelated memory-hardening work.

CONFIG90 is not a secret, but it is proprietary target material; do not print or version its raw bytes. Wiping a private in-memory copy at teardown is acceptable if done consistently and without overclaiming security semantics.

---

## 9. Test-only D278/02 live-capable native harness

Create the smallest bounded harness needed for a **future** single-shot validation. It may live under `tools/` if that best preserves the GPL/LGPL boundary.

It must reuse, rather than reimplement:

```text
GoodixFpiUsbBackend
GoodixUsbRouter
GoodixSecureSession
GoodixTlsServer
existing A0/B0 logic
```

A harness-specific `FpDevice`/GUsb test binding analogous in role to D277 is acceptable. Duplicating the secure-session state machine is not.

The harness must not register/install a production libfprint device and must not change the existing `GoodixFpImageDevice` production-registration status merely to make the test easier.

### Required modes

Provide modes equivalent to:

```text
--self-test
--material-preflight-only
--live-exact-secure-session
```

Exact spelling may differ if there is a strong reason, but document it.

`--self-test` must be completely hardware-free.

`--material-preflight-only` must never enumerate/open/claim/submit USB. It may validate the real protected inputs when later run manually on the operator host. It must output only redacted status/hashes/failure classes, never raw sensitive material.

`--live-exact-secure-session` is the future sensor-reaching path. **Compile it but do not execute it in this task.**

### Future privilege model

Do not weaken the existing root-only protected material solely so the harness can run unprivileged.

The future live/material-preflight execution should therefore be designed for an operator-invoked root context, because the canonical material stores are `root:root 0600`. That future privilege requirement is concrete and should be documented; Codex must not run `sudo` during this task.

Do not add ACLs or persistent udev changes as a workaround.

### Future live ordering

For the future live mode, all protected material validation and D190 KAT/target-pin validation must complete **before the first USB open attempt**. If material validation fails, USB counts must remain zero.

After target selection, enforce exactly one open/claim epoch and exactly one monotonic secure-session attempt. No retry, reopen, reset or recovery command is permitted.

### Bounded timeout

The current shared async USB backend uses cancellable transfers and may submit with no intrinsic libfprint timeout. The future harness therefore must have an explicit bounded outer watchdog so a lost response cannot hang indefinitely.

Prefer a phase-aware watchdog using the already-canonical historical phase bounds where practical:

```text
A8        1000 ms
E4        1000 ms
A2_1      1000 ms
82         500 ms
A6         750 ms
A2_2      1000 ms
70         500 ms
80 x4      250 ms each
90        1000 ms
D1        1000 ms
TLS       3000 ms
```

Do not add retries. On timeout or any terminal protocol/USB error:

```text
stop producing commands
set terminal fence
cancel host async I/O
wait for backend drain
release interface if claimed
close device if opened
zeroize project-owned secret material
return one redacted failure result
```

If a simpler total watchdog is selected instead, justify why it preserves at least the same bounded/fail-closed behavior and diagnostic value.

### Future success terminal

Success is reached only when the existing native TLS server reports the TLS 1.2 PSK handshake established and all queued B0 server-flight egress required for that handshake has completed. Then STOP immediately.

No D4, no TLS application data, no finger/image path.

---

## 10. Telemetry for the future harness

The future live result must be redacted and machine-readable. Include enough fields to review safety and exact advancement, for example:

```text
result
failure_class
reached_phase
current_live_authorized=false after an attempt
live_authorization_consumed
usb_open_attempt_count
usb_open_count
usb_claim_count
usb_release_count
usb_close_count
real_usb_submit_count
physical_in_submit_count
physical_out_submit_count
max_outstanding_bulk_in
max_outstanding_bulk_out
command_count
phase_trace
ack_count
typed_response_count
e4_binding_match
tls_handshake_count
tls_established
secret_handoff_count
project_secret_zeroized
d4_reachable=false
application_data_count=0
finger_wait_count=0
image_count=0
retry_count=0
transport_reopen_count=0
device_reset_count=0
persistent_device_write_count=0
terminal_cleanup_completed
```

Never include PSK, raw validator, raw seed material, raw CONFIG90, raw OTP, TLS master material or biometric data.

For host-only execution in this task, live counters must remain zero.

---

## 11. Host-only tests required in this task

Add deterministic tests sufficient to prove the new boundary without hardware.

At minimum cover:

### D190 native binder

- all five existing independent synthetic KAT vectors;
- canonical `gfusb.dll` hash gate and read-only parser path if that parser is part of the selected design;
- malformed/truncated PE or wrong hash fails closed;
- no DLL execution/loading;
- intermediate project-owned crypto buffers are cleared on success/failure where testable without exposing secrets.

### Protected input boundary

Using synthetic temporary files and a test-injected ownership policy where needed so CI does not depend on being root:

- regular/non-symlink positive path;
- symlink rejection;
- wrong mode rejection;
- wrong owner policy rejection;
- length mismatch;
- transport magic/hash mismatch;
- CONFIG90 hash mismatch;
- finalizer mismatch;
- DAC tuple mismatch/order mismatch;
- derived E4 hash mismatch;
- one-load/one-owner lifetime and zeroization behavior.

The production wrapper must remain fixed to uid 0/mode 0600 even if tests inject a current-uid policy.

### Harness/sequencer composition

- no real GUsb open/submit in self-tests;
- complete synthetic material → existing `GoodixSecureSession` happy path;
- timeout/watchdog fail-closed path;
- no second reader;
- max one IN and max one OUT in flight;
- no retry/reopen/reset;
- D4 unreachable;
- application data rejected/out of scope;
- teardown drains before freeing transfer-owned state;
- material invalidity blocks before any hypothetical USB-open seam.

### Regression suites

Run at least:

```text
libfprint-driver/tests/run_goodix_d278_secure_session_test.sh
libfprint-driver/tests/run_goodix_d276_04_test.sh
libfprint-driver/tests/run_goodix_fpimage_device_test.sh
libfprint-driver/tests/run_goodix_usb_router_test.sh
D277 host-only regression suite / live harness build-only path
```

Preserve the existing normal + ASAN/UBSAN coverage. Run the D278/new runner twice if it is the task's principal executable path, to demonstrate determinism.

Update CI so it compiles/tests the D278/02 host-only work but **never executes**:

```text
--material-preflight-only against /var/lib/goodix-5125-poc
--live-exact-secure-session
```

CI must not enumerate/open a USB sensor.

Also run:

```text
git diff --check
```

Validate any JSON artifact with an appropriate parser.

---

## 12. Scope discipline / debt-prevention rules

Do not use this task to implement D4, FDT, image capture, enrollment, production device registration, fprintd/PAM integration, orientation, PPMM, cross-activation TLS reuse, or arbitrary cancellation/quiescence policy.

Do not refactor unrelated D276/D277 code simply to make the diff prettier.

A small refactor is allowed only when it removes an actual duplicate authority required by D278/02 (for example, a shared material owner or bounded timeout hook) and is covered by regressions.

If a design choice would create a permanent production dependency on a proprietary Windows binary, a second protocol engine, a second secret store, or a new persisted derived secret, stop and choose a cleaner boundary unless there is strong evidence that no better design exists.

---

## 13. Methodological pre-live review to prepare — no authorization

As part of the D278/02 analysis/manual, prepare the concise methodological block required before a future live run:

### 1. What materially changes from the last native target run?

Expected substance:

```text
D277/02 proved only A8/A0.
D278/02 adds the already host-only-proven full native secure-session sequencer,
real protected target material loading,
native PSK->E4 binding,
and a bounded single-shot TLS-to-STOP harness.
```

### 2. What new hypothesis would the future run test?

Expected substance:

```text
The APP12509 target accepts the existing native C sequence beyond A8,
with E4 bound to the same factory PSK used by OpenSSL,
and reaches one TLS 1.2 PSK established state without D4.
```

### 3. What happens if it fails?

Expected policy:

```text
No retry/reopen/reset.
Capture the first exact failing phase and redacted USB/protocol error,
complete cleanup/zeroization,
and return to AI-PM review.
A second equivalent live attempt is not authorized by this task.
```

This block is preparation only. It must explicitly state:

```text
CURRENT_LIVE_AUTHORIZED=false
```

---

## 14. Canonical D278/02 artifacts

Create/update a step-local Git-native review set under:

```text
analysis/D278/D278_02_native_target_material_secure_session_prep.md
analysis/D278/D278_02_native_target_material_secure_session_prep.json
```

Do not create ZIP/Base64 packaging.

The report must distinguish clearly:

- historical target-live evidence;
- D277/02 target proof;
- D278/01 host-only proof;
- D278/02 new host-only preparation evidence;
- future target claims still unproven.

Do not place secret/raw proprietary material in these artifacts.

---

## 15. Required canonical state after successful host-only preparation

Use names consistent with the existing repository, but the final state must semantically include at least:

```text
D278_01_D1_TLS_GATE_AI_PM_REVIEW=PASS
D278_01_D1_TLS_GATE_CI=PASS
D278_01_D1_TLS_GATE_CI_RUN=33239781874
D278_01_D1_TLS_GATE_CORRECTIVE_COMMIT=5030c66e67db5a7f6cedfbf3bb0deeec107e79db
D278_01_MERGED_MAIN_COMMIT=52e190b2ceaee0e8de618accd4da9fadbad54115

D278_02_HOST_ONLY_PREPARATION=PASS
NATIVE_D190_E4_BINDER_KAT_PROVEN=true
NATIVE_PROTECTED_MATERIAL_LOADER_HOST_ONLY_PROVEN=true
TARGET_PROTECTED_MATERIAL_PREFLIGHT_EXECUTED=false
D278_02_LIVE_HARNESS_BUILD=PASS
D278_02_LIVE_HARNESS_EXECUTED=false
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
TARGET_E4_DERIVATION_NATIVE_LIVE_PROVEN=false
TARGET_TLS_NATIVE_LIVE_PROVEN=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
D4_REACHABLE=false
APPLICATION_DATA_COUNT=0
FINGER_PATH_NOT_EXERCISED=true
IMAGE_PATH_NOT_EXERCISED=true
PERSISTENT_DEVICE_WRITE_COUNT=0
CURRENT_LIVE_AUTHORIZED=false
```

Do not set a target-proof boolean true merely because KATs, synthetic material tests or historical Python live evidence pass.

---

## 16. Closure fields

Finish with the standard project closure:

```text
OUTCOME=READY | BLOCKED_<technical_reason>
ADVANCEMENT=<precise host-only architectural/executable advancement or NONE>
EXECUTABLE_CLOSURE=PASS_HOST_ONLY | FAIL
RESIDUAL_BLOCKER_OR_RISK=<concise truthful list>
CANONICAL_DOCUMENTATION=<manual updated + sections>
REVIEW_SET=<baseline + final working-tree/task ref + relevant paths>
```

Also report separately:

```text
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
CURRENT_LIVE_AUTHORIZED=false
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
```

If successful, the next boundary must be phrased as **AI-PM review of D278/02 pre-live readiness**, not as automatic permission to execute hardware.

Suggested semantic endpoint:

```text
NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_FOR_D278_02_SINGLE_SHOT_NATIVE_SECURE_SESSION_TARGET_VALIDATION
```

---

## 17. Stop conditions

Stop and report rather than improvising if any of the following occurs:

- starting Git baseline differs materially from the expected main state;
- D190 per-file provenance is not demonstrably compatible with the intended destination;
- implementing the binder would require copying GPL-only expression into LGPL;
- a real protected target file/secret unexpectedly appears in a path that would cause it to be committed or logged;
- a test would require real USB access;
- a design would require provisioning/replacing PSK or modifying device persistent state;
- a clean bounded future live path cannot be constructed without D4/retry/reset/reopen;
- a new external dependency is necessary but not already justified by repository architecture.

Do not solve a blocker by weakening the factory-preserving invariant or by manufacturing evidence.
