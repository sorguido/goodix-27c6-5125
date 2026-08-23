<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Userspace core boundary

Future active Goodix userspace components belong here under
`GPL-2.0-or-later`: `transport`, `protocol`, `tls`, `fdt`, `capture`, and
`image`. D247 does not move the frozen `src/` implementation or add functional
code. Any later migration must preserve historical reproducibility and record
file-level provenance.

D257 adds the offline-only FDT lifecycle and explicit read-only seed provider;
D258 corrects the exact candidate with the recovered target OEM host path.
`fdt_lifecycle.py` keeps the historical projected three-sample model distinct
from the exact target-order candidate `36,50,36,82,20,36,32`. The exact model
stores NAV and baseline state before the third sample, enforces the native
register-`0x0082` unsigned absolute-delta predicate, and evaluates the still
unresolved NAV/image classifiers only after stage2. Per-command budgets are
`0x36/0x50/0x82=500 ms`, `0x20=2000 ms`, and `0x32=100 ms`; timeout and missing
classifier/decryptor paths fail closed with no retry. D259 adds a separate
minimal-device-contract finalizer: it retains both native delta predicates but
omits the host-only semantic classifiers and cache write. The D259 corrective
requires the `0x20` B0 to be authenticated/decrypted immediately, before the
third `0x36`. `tls_b0.py` adapts the same already-handshaked MemoryBIO
`SSLObject` without creating another context, session, handshake, transport or
PSK provision. It best-effort wipes only its mutable plaintext buffer;
OpenSSL-internal and immutable Python copies are not proven zeroized. The
sealed D245 runtime currently closes its local TLS engine at the end of
`tls_handshake()` and does not expose it, so live adapter plumbing remains
unimplemented and live-readiness review is fail-closed. `fdt_seed.py` validates the
target-observed 13,520-byte OTP-bound cache and returns only FDT12. Neither
module opens USB, searches Windows paths, writes cache state, or exposes
persistent/provisioning command families.
