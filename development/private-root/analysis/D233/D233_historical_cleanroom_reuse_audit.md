# D233 bounded historical clean-room reuse audit

The metadata-first search was bounded to `/home/guido` and excluded SSH/GPG,
browser, mail, password/keyring and messaging stores. It searched D189/D190 and
D203–D226 names plus Goodix/validator/transport material names. Rockytkg paths
were excluded and no Rockytkg source was read or used.

The original D233 filename/archive search did not find a historical clean-room
implementation. The closure then followed the prompt's stricter A1/A2/A3
sequence: current paths and Git objects remained empty, but a bounded
exact-string search of local Codex session metadata found the original D190
source/KAT patch records and the D191 bounded-parser patch. These records are
hash-identified in `D233_d190_reference_provenance.json`.

The minimum D190 parser/crypto/runtime reference was recovered from those
records. Five pre-existing OEM-attributed validators were reproduced 5/5 using
the canonical local PE. No Rockytkg or GPL source was read or used, and no raw
OEM seed/material was restored as a source literal.

The other reusable project implementation was the current D232 seam:
`src/goodix5125_d232_offline.py`. D233 refactored its already-reviewed replay
body into `_run_exact_oem_core`; D232 retains the exact synthetic-backend type
gate and all its prior tests pass. Serializer, allowlist, order, timeouts,
response validators, protected-file boundary and report publisher are reused.

Two directories named `goodix-d232-private-audit` and
`goodix-d233-private-audit` were inspected by filename and documentation. They
concern unrelated publication/editorial audits of an older sanitized public
tree and contain no D203–D226 backend/KDF source; nothing was reused.

The provenance-valid recovered capture remains at
`analysis/D230/work/GoodixExport/rilevamento.pcapng`, SHA-256
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`.
It is used only as a local provenance source for the future `0x90` procedure
and is excluded from the D233 bundle.
