<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Goodix libfprint driver sources

This directory contains the target-specific source used by the
`goodix_27c6_5125` libfprint driver:

- asynchronous USB routing and transfer ownership;
- TLS 1.2 PSK server and secure-session state;
- protected-material validation and binding;
- image record decoding and preprocessing;
- enrollment, template, matching, and action integration;
- cancellation, terminal events, cleanup, and bounded retries.

The source is selected by
`reference/libfprint-fedora44-1.94.100/source/libfprint/meson.build`. The exact
production file set and digests are in `production/source-files.tsv` and
`production/source-files.sha256`.

Licensing is per file. Most local driver files are `LGPL-2.1-or-later`.
`rockytkg-imgproc/goodix_imgproc.[ch]` retains `GPL-2.0-or-later`; its presence
makes the distributed Goodix-enabled combined binary GPL-compatible rather
than an LGPL-only work. See `docs/LICENSING_AND_PROVENANCE.md`.

No file in this directory contains firmware, a PSK, factory data, a real
fingerprint sample, a template, or a private capture.

Synthetic A0 regressions run with `sh tests/run_goodix_enrollment_a0_test.sh`
and `sh tests/run_goodix_post_tls_test.sh` from this directory. Both run normal
and ASan/UBSan builds using the public source tree, without a reader or real
materials. The enrollment suite preserves zero-mask rejection at repeated
contacts and checks that the rejected event does not deliver the pending
primary, send an auxiliary acquisition, or rearm. These tests do not establish
the correct recovery sequence on hardware.

The separate [zero-mask contract](../docs/ENROLLMENT_ZERO_MASK_CONTRACT.md)
has a Python standard-library specification model under `tests/spec/`.
Run `python3 -I -B tests/spec/test_irq0200_late_contract.py` from this directory.
It is not linked into the driver or production tests and intentionally leaves
rearm blocked while the device release boundary is unproved. Its passing tests
do not change or qualify runtime acceptance of zero flags.
