<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Canonical paired login implementation

`fprintd.patch` and `greeter.c` are mechanically promoted from the physically
validated prototype at `9671e02e19504e20e0097f598fa960f2c13e7a1e`. The preserved
hashes in `prototype-equivalence.sha256` cover those two unchanged files. The
subsequent three-attempt driver/lifecycle delta is versioned separately in Git
and pinned by `production/source-files.sha256`; it does not claim identity to
the original one-attempt prototype. The libfprint base and SIGFM sources match those
used by that prototype. The complete runtime is not byte-identical: canonical
per-reader loaders replace the historical fixed loaders, build layout/flags
change, and the managed installer owns the full component set.

`fprintd-cleanup.patch` was the only behavioral correction introduced during
promotion: if suspend/abandon finishes PrepareLogin while async open is still
pending, the late open callback must close instead of preparing. A held-open
private-bus test reproduced the original hang, then passed with this guard.
The READY/baseline20/first32ACK/ClaimLogin/Verify path is unchanged.

The upstream source is copied from the immutable canonical `reference/` tree;
all three patches apply at build time with zero fuzz. No installed daemon is
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

Prepared login now permits at most three explicit VerifyStart actions in one
ClaimLogin, with 8 s per attempt, 10 s preparation and 120 s initial READY.
`fprintd-attempts.patch` allows continuation only after an ordinary NO MATCH;
PAM is capped at three even if configured higher. The driver also limits the
prepared context to three and retains it only after host NO MATCH plus the
complete physical release tail. A new VerifyStart sends only the existing
0x32 arm using the fresh down table; another IRQ2 is required before 0x22.
TLS, baseline and generation are preserved. MATCH is reported immediately;
NO MATCH is deferred until completion, preventing PAM's VerifyStop from
cancelling a still-active release. Error/retry/timeout/cancel is terminal.
An abandoned between-attempt context expires after 8 s. No fourth action.

Tests cover second/third MATCH, three NO MATCH, cancel/protocol failure on
attempts one/two, cancellation during deferred completion and close between
attempts. The driver fixture begins at a synthetic post-secure-session seam
and then executes the actual post-TLS protocol and libfprint matching/release
callbacks, with synthetic images/matcher. It does not qualify a physical TLS
handshake or hardware rearm. Protocol tests assert fresh release/arm/down,
unchanged baseline and command counts; daemon tests exercise the real handlers
on a private bus and hold action completion to test signal ordering.

The installed historical overlay has a separate reversible follow-up under
`development/patches/login-three/`; it builds these same canonical behavioral
sources while retaining its four historical material loaders. It is not a
canonical build dependency. The managed candidate contains the canonical
material loaders and keeps its existing install/update/rollback workflow.
No hidden retry, second bootstrap/recalibration/reopen or pre-Verify image is
introduced. The broader project and managed-candidate target qualification
remain open. This promotion performs no host installation or live run.
