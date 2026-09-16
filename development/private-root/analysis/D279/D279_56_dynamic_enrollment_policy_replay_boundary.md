<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/56 — authentic dynamic enrollment policy replay boundary

## Decision

The enrollment policy review is accepted as a new, independent evidence
stream.  Fixed 21 remains the authentic ATTEMPT02 regression profile but is
not justified as the final SIGFM biometric policy.  The preferred direction
is Rockytkg-style dynamic diversity, pending both this authentic offline replay
and a later, separate proof of safe APP12509 early termination.

D279/54 identify evidence is not used to select an enrollment count.  D279/55
production identify remains an independent single-acquisition boundary.

## Exact policy replay

`d279_56_dynamic_enrollment_policy.py` ports the exact default policy from the
preserved `Rockytkg/src/goodixgf.c`:

```text
minimum distinct accepted frames = 3
maximum delivered stages = 8
duplicate streak to converge = 2
duplicate iff MAD < 8.0 against any accepted frame
```

For 80x64 8-bit frames, the implementation uses the integer-equivalent test
`sum(abs(delta)) < 40960`, preserving the strict boundary without floating
rounding.  A duplicate is normally rejected.  Once three distinct frames have
been accepted, the second consecutive duplicate is delivered as the terminal
sample and the target becomes `accepted_count + 1`.  A distinct eighth frame
terminates at the maximum.

Only the 21 primary rasters are evaluated.  The ATTEMPT02 baseline is used by
the exact production D279/49 R2 component; auxiliary rasters are excluded.
The aggregate exports only counts, terminal reason and ordered
`ACCEPT/DUPLICATE/CONVERGE` classes.  It exports no numeric per-stage MAD,
raster, feature, descriptor or template.

## Authorization and executable closure

The origin review grants the protected offline study and its bounded technical
retries without further per-run consent.  Its SHA-256 is
`9b93693a27eaa6456b1d72a13d0d61e9bd01a3cd0842ae6f9e5c530ec9c631f6`.
That authority expressly excludes new capture, live/USB, persistent changes,
installation, provisioning, PSK changes and sudo by the AI.

The operator kit records the authority and creates a Git-archive snapshot
bound to a clean `development` HEAD equal to `origin/development`.  It compiles
only the production R2 component and a stdin/stdout helper.  The protected
entrypoint reuses the established hash-gated ATTEMPT02 TLS reconstruction and
root-owned material reader, writes with `O_EXCL` mode 0600 and runs an exact
aggregate schema validator before returning success.  No grant token is
required because the authorization is not one-shot; each result directory is
collision-free and retries remain within the same bounded study.

The normal-user preflight passes 8 tests, the D279/49 R2 KAT hash
`2ff834cd...153b3`, Python reduced-scope logic, output rejection and a helper
symbol audit.  It reads no protected input and performs zero USB action.

The first post-commit snapshot preparation failed before protected access
because `unittest -m` treated the randomized dot in the absolute temporary
path as a module separator.  The corrective executes each test file directly
and guarantees cleanup of incomplete prepared directories.  This was a
host-side executable-closure failure only: PSK/raster access remained false.

The actual replay cannot be executed by the current AI process: the production
material directory requires root access, while both governance and the origin
authorization exclude agent sudo.  This is a manual capability boundary, not
a request for new consent.  After this changeset is committed and pushed, the
normal-user preparation step can produce the exact command the operator must
invoke.

## Closure before protected execution

```text
OUTCOME=HUMAN_REQUIRED
ADVANCEMENT=AUTHORIZED_AUTHENTIC_DYNAMIC_POLICY_REPLAY_EXECUTABLE_READY
EXECUTABLE_CLOSURE=PASS_OFFLINE_PREFLIGHT
FIXED_21_FINAL_BIOMETRIC_POLICY_JUSTIFIED=false
ATTEMPT02_21_STAGE_REGRESSION_PROFILE_RETAINED=true
DYNAMIC_POLICY_DIRECTION=ROCKYTKG_STYLE_PENDING_AUTHENTIC_RESULT
AUTHORIZATION_STATUS=GRANTED_AT_ORIGIN
FURTHER_PER_RUN_USER_AUTHORIZATION_REQUIRED=false
AGENT_SUDO_AUTHORIZED=false
PROTECTED_INPUT_ACCESSED=false
REAL_RASTER_EVALUATED_COUNT=0
LIVE_OR_USB_ACTION_COUNT=0
CURRENT_LIVE_AUTHORIZED=false
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md
REVIEW_SET=GIT_NATIVE
RESIDUAL_BLOCKER_OR_RISK=MANUAL_ROOT_CAPABILITY_REQUIRED;AUTHENTIC_AGGREGATE_PENDING;DYNAMIC_EARLY_TERMINAL_APP12509_UNPROVEN
NEXT_PRIMARY_BOUNDARY=MANUAL_EXECUTION_OF_ALREADY_AUTHORIZED_D279_56_PROTECTED_OFFLINE_REPLAY
```

## Authentic post-run review

The authorized offline run completed successfully on baseline
`10d041da31f571408f53ba1029230e830d19fd60`. The validator passes, protected
transport input was verified, and the run reports zero USB/live actions and
no PSK, raster, feature or template export. The authentic primary artifacts
are preserved byte-identically as:

```text
D279_56_SUCCESS_summary.json
SHA256=f16977450fe01d03990409d479dd3daaab30a522d0a00b2a6f0c59225713f6be

D279_56_SUCCESS_operator.log
SHA256=1cba568ade84cf7a6cc098fc0e185e2aa93e49a3bb6a84c7c763931d7c6816b9
```

All first eight primary R2 frames classify `ACCEPT`. No duplicate is observed,
so the duplicate-streak convergence branch is not reached. The exact Rockytkg
selector terminates at its maximum with eight distinct samples:

```text
INPUT_PRIMARY_STAGE_COUNT=21
EVALUATED_STAGE_COUNT=8
DISTINCT_SAMPLE_ACCEPT_COUNT=8
DUPLICATE_REJECT_COUNT=0
FIRST_POSSIBLE_CONVERGENCE_STAGE=null
FINAL_SELECTED_STAGE_COUNT=8
TERMINAL_REASON=MAX_STAGE_REACHED
```

This directly answers the replay question: on ATTEMPT02, the reference policy
would have stopped after eight delivered samples rather than 21. It supports
retiring fixed 21 as the final biometric policy and retaining it only as the
authentic protocol/regression profile. It does not validate the constants
across fingers/sessions, FAR/FRR, or the APP12509 sensor state after omitting
the stage-8 re-arm. Production therefore remains at 21 until the distinct
`DYNAMIC_EARLY_TERMINAL_APP12509` hardware boundary is proven.

The first result required a manual copy because the root-owned results parent
was mode 0700 even though its child had been chowned. The retry-capable runner
now emits a separate user-owned mode-0700 `EXPORT_DIRECTORY` containing only
the already validated summary and operator log. This corrective does not
change the authentic result and no retry is required.

```text
OUTCOME=READY
ADVANCEMENT=AUTHENTIC_ATTEMPT02_DYNAMIC_POLICY_REPLAY_COMPLETED
EXECUTABLE_CLOSURE=PASS_PROTECTED_OFFLINE_AND_AGGREGATE_VALIDATION
AUTHENTIC_RESULT_PRESERVED_BYTE_IDENTICAL=true
ROCKYTKG_POLICY_REPLAY_TERMINAL=MAX_STAGE_REACHED
REFERENCE_SELECTED_SAMPLE_COUNT=8
FIXED_21_FINAL_BIOMETRIC_POLICY_RETIRED=true
ATTEMPT02_21_STAGE_REGRESSION_PROFILE_RETAINED=true
PRODUCTION_ENROLLMENT_STAGE_POLICY=21_UNCHANGED_PENDING_DEVICE_PROOF
ROCKYTKG_CONSTANTS_PRODUCTION_VALIDATED=false
DYNAMIC_EARLY_TERMINAL_APP12509_PROVEN=false
PROTECTED_INPUT_ACCESSED=true
PSK_OR_RASTER_EXPORTED=false
LIVE_OR_USB_ACTION_COUNT=0
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
RESIDUAL_BLOCKER_OR_RISK=APP12509_STAGE8_NO_REARM_TERMINAL_AND_REUSABILITY_UNPROVEN
NEXT_PRIMARY_BOUNDARY=OFFLINE_D279_57_STAGE8_EARLY_TERMINAL_LIVE_BOUNDARY_PREPARATION
```
