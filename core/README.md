<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Userspace core boundary

Future active Goodix userspace components belong here under
`GPL-2.0-or-later`: `transport`, `protocol`, `tls`, `fdt`, `capture`, and
`image`. D247 does not move the frozen `src/` implementation or add functional
code. Any later migration must preserve historical reproducibility and record
file-level provenance.

D257 adds the offline-only FDT lifecycle and explicit read-only seed provider.
`fdt_lifecycle.py` keeps the historical projected three-sample model distinct
from the exact target-order candidate `36,50,36,82,20,36,32`. The exact model
requires caller-provided semantic gates for dynamic NAV, FDT-delta and
decrypted baseline data; missing gates fail closed. Its first `0x36` is latched
before submission, single-shot and non-retrying. `fdt_seed.py` validates the
target-observed 13,520-byte OTP-bound cache and returns only FDT12. Neither
module opens USB, searches Windows paths, writes cache state, or exposes
persistent/provisioning command families.
