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
