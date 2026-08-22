<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Userspace core boundary

Future active Goodix userspace components belong here under
`GPL-2.0-or-later`: `transport`, `protocol`, `tls`, `fdt`, `capture`, and
`image`. D247 does not move the frozen `src/` implementation or add functional
code. Any later migration must preserve historical reproducibility and record
file-level provenance.

D257 adds the offline-only FDT lifecycle and explicit read-only seed provider:
`fdt_lifecycle.py` models bootstrap, arm, host cancel, session re-entry,
terminal stop and first-image state without a USB backend; `fdt_seed.py`
validates the target-observed 13,520-byte OTP-bound cache and returns only its
FDT12 field. Neither module searches Windows paths, writes cache state,
retries, or exposes persistent/provisioning command families.
