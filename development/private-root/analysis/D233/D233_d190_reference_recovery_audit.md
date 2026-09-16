# D190 reference recovery audit

Recovery was read-only until the minimum clean-room files were reintegrated.

1. **A1 current tree:** `binding_reference`, `binding_cleanroom`,
   `oem_binding_oracle`, D190 sources and tests were absent.
2. **A2 local Git:** path-scoped `git log --all` and
   `git rev-list --all --objects` contained no recoverable D190 object. No
   checkout, reset, clean, merge, rebase, cherry-pick, pull or push was used.
3. **A3 bounded metadata-first filesystem:** filename and archive inventories
   under `/home/guido`, excluding credential/browser/mail/messaging locations
   and secret-store content, found no source tree. A bounded exact-string search
   in local Codex session metadata located the original D190 and D191 patch
   records.
4. **A4 not invoked:** reconstruction from scratch was unnecessary.

The D190 transcript (2026-07-28) contains the original `pe_parser.py`,
`crypto_reference.py`, CLI, five public KAT values, clean-room models, OEM
oracle comparison and six tests. The D191 transcript contains the subsequent
bounded-parser hardening. Their SHA-256 identities and precise record numbers
are in the provenance JSON.

Only the minimum parser, crypto, runtime API, public KAT inputs/validators and
README were restored. CLI/OEM emulator and the two large models were not needed
for runtime closure and were not copied. The parser adds a fail-closed unique
target-pattern check. Raw OEM seeds are deliberately not restored as literals.

Result: `D190_REFERENCE_RECOVERED_OR_RECONSTRUCTED=yes` (recovered), with
provenance valid and no theory reopened.
