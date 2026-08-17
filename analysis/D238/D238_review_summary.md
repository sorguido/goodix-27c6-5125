# D238 review summary

D238 consolidates the fragmented pre-D1 work into one evidence-backed offline
closure. It does not perform or authorize the next live run.

- Audited the actual untracked working corpus rather than assuming public Git
  `HEAD` contained D232–D237.
- Confirmed D233/D235 source seals and post-D236 exit-code correction; confirmed
  diagnostic unseal logic was not left active.
- Reconstructed the primary capture lifecycle and reconciled it with all three
  D236 live results.
- Replaced the E4-only `0x07` exception with one explicit per-phase policy for
  the two evidenced ACK success values, exact response count/order and typed
  response shapes.
- Added safe per-phase completion/order observability.
- Verified the 88-byte G5125POC loader, same-secret E4/TLS ownership, config90,
  manifest and PE pins.
- Added six D238 tests and repaired one stale D235 subprocess expectation to
  match the already-canonical nonzero sealed-entrypoint exit contract.
- Full offline suite: 68 tests, all passed.
- Added exactly one operator script and one reviewed temporary unseal patch;
  syntax and dry-run review passed, script not executed.
- Updated the canonical technical manual with live evidence, ACK lifecycle,
  runtime material and current safety boundary.

Residual risk: status `0x07` has direct live proof only for E4 and A2 #1; its
use on later controls is an evidence-based session/transport inference from
cross-control stability, not a live observation of those phases. Receiver
internals remain unavailable and `DEVICE_RESIDENT_NO_NVM_SIDE_EFFECT_PROVEN`
remains false. These risks require renewed human authorization.

Decision: `D238_READY_FOR_ONE_HUMAN_AUTHORIZED_LIVE_ATTEMPT`.
