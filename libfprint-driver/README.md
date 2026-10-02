<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Goodix libfprint driver sources

This directory contains the target-specific source used by the
`goodix_27c6_5125` libfprint driver:

- asynchronous USB routing and transfer ownership;
- TLS 1.2 PSK server and secure-session state;
- bounded read-only target preflight and CONFIG90 derivation;
- self-contained host pairing and crash-safe persistent pairing state;
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

Synthetic enrollment parser/binding regressions run with
`sh tests/run_goodix_enrollment_a0_test.sh`; preparation/capture lifecycle checks
run with `sh tests/run_goodix_post_tls_test.sh` from this directory. Both run
normal and ASan/UBSan builds without a reader or real materials. Enrollment
coverage includes primary ownership, zero-mask continuation, omitted auxiliary
commands, bounded late releases, raw bounds, cancellation and terminal cleanup.
The low-level binding suite also checks diagnostic fallback when recovery is not
enabled. The self-contained boundaries have their own runners in the same
directory: `tests/run_goodix_pairing_crypto_test.sh`,
`tests/run_goodix_config90_bb010002_test.sh`,
`tests/run_goodix_self_state_test.sh`,
`tests/run_goodix_live_preflight_test.sh`,
`tests/run_goodix_pairing_provision_test.sh` and
`tests/run_goodix_pairing_activation_test.sh`. All of them run without a reader,
real material or USB access. Runtime semantics and qualification limits are
described in the
[technical manual](../TECHNICAL_MANUAL.md#74-enrollment-zero-mask-recovery).

The image-device integration runner accepts the source root and a fresh build
directory. With the required compiler/GLib/OpenSSL development tools available,
run from this directory:

```sh
GOODIX_PRODUCTION_FPRINTD_ACTION_PROFILE_TEST=1 \
  sh tests/run_goodix_fpimage_device_test_inner.sh "$(pwd)/.." \
  "$(mktemp -d /tmp/goodix-image-device-test.XXXXXX)"
```

This exercises actual libfprint actions with synthetic transport and image
processing seams, including asynchronous decisions and ownership/drain. It does
not require private fixtures or establish real biometric accuracy. Build output
stays in the temporary directory; no host runtime is installed.
