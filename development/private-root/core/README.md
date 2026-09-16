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

D260 adds the production-shaped offline architecture in
`persistent_runtime.py` and `runtime_transport.py`. One coordinator now owns a
single logical transport session, a single synthetic validated-secret handoff,
one retained TLS 1.2 PSK server, the B0 handshake bridge, post-handshake D4 and
AF plaintext A0, a separate asynchronous `EventSource`, and the exact minimal
FDT path. D4 is represented byte-exact as a fixed-64 zero-tail submission after
20 ms with a 200 ms timeout; server-flight B0 records retain the D242/D245
fixed-64 staging and 10 ms pacing contract. The future Linux physical tail for
FDT A0 commands remains explicitly abstract, so D260 closes architecture
readiness only and does not provide a USB backend or operational live path.
