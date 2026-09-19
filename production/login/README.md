<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Canonical paired login implementation

`fprintd.patch` and `greeter.c` are mechanically promoted from the physically
validated prototype at `9671e02e19504e20e0097f598fa960f2c13e7a1e`. The preserved
hashes in `prototype-equivalence.sha256` also cover the exact driver login and
post-TLS lifecycle sources. The libfprint base and SIGFM sources match those
used by that prototype. The complete runtime is not byte-identical: canonical
per-reader loaders replace the historical fixed loaders, build layout/flags
change, and the managed installer owns the full component set.

`fprintd-cleanup.patch` is the only behavioral correction introduced during
promotion: if suspend/abandon finishes PrepareLogin while async open is still
pending, the late open callback must close instead of preparing. A held-open
private-bus test reproduced the original hang, then passed with this guard.
The READY/baseline20/first32ACK/ClaimLogin/Verify path is unchanged.

The upstream source is copied from the immutable canonical `reference/` tree;
both patches apply at build time with zero fuzz. No installed daemon is
modified, and no private Git commit or development directory supplies build
inputs. `source.sha256` covers every file in this directory except itself.
The upstream source has its own complete retained-file manifest.

`build.sh` is called by `production/build.sh`; use the latter entry point.
The output contains the library and paired daemon/PAM/greeter together.
`check-offline.sh NORMAL_BUILD SANITIZER_BUILD` verifies the canonical sources
with synthetic I/O and a private D-Bus only. Driver shell tests retain their
in-memory binding profile (and deterministic matcher double), while compiling
the actual Fedora core with its SIGFM adapter. They do not simulate a complete
production hardware bootstrap or qualify physical matching. The production
profile itself is compiled in both complete builds; the post-TLS tests exercise
its real preparation/authorization protocol boundary. Daemon tests use actual
patched handlers but bypass host PolicyKit authorization with synthetic qdata.
Greeter tests execute the real helper with a marker child instead of Plasma.

The normal prepared login remains one explicit attempt (8 s), with 10 s driver
preparation and 120 s READY lifetime; password fallback remains available.
No hidden retry, second bootstrap/recalibration/reopen or pre-Verify image is
introduced. The broader project and managed-candidate target qualification
remain open. This promotion performs no host installation or live run.
