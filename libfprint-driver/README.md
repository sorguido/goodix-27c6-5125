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
