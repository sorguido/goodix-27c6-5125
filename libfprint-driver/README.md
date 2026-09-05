<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# libfprint driver boundary

This directory contains the bounded upstream-facing image adapter and is
reserved for future driver/glue under `LGPL-2.1-or-later`.
GPL-only implementation expression, including GPL-only Rockytkg code, must not
cross this boundary without a valid compatible alternative license or a
genuinely independent implementation from specifications, tests and evidence.
A specific Rockytkg file already validly licensed LGPL-2.1-or-later may be
evaluated for this domain only after per-file provenance and rights/third-party
review, preservation of notices/SPDX, and confirmation of compatibility with
upstream libfprint.

## D269/01 bounded image adapter

`goodix_u16_to_fpimage.c` converts only the canonical, already-decoded Goodix
`80x64` raster from `u16` containers carrying 12-bit samples to the one-byte
grayscale buffer required by the repository-local libfprint 1.94.5 `FpImage`.
It uses the fixed Linux-specific mapping `round(sample * 255 / 4095)`. It does
not normalize against frame content, apply biometric enhancement, alter the GPL
decoder, or claim to reproduce the Windows preprocessing contract.

The metadata reports packed rows (`stride == width`) and zero libfprint image
flags. This deliberately preserves the decoder's canonical raster because the
physical/natural fingerprint orientation and polarity policy are not yet
resolved. The adapter has no USB, TLS, secret, fprintd, filesystem, or image
persistence API. A future libfprint glue layer can allocate `FpImage(80, 64)`,
copy the returned 5120 bytes into its object-owned `data`, and apply only a
separately evidenced orientation/polarity decision.

## D270/01 real FpImage construction seam

`goodix_fpimage_pipeline.c` now performs that bounded construction against the
repository-local libfprint API. It allocates a real `FpImage(80, 64)`, lets the
D269 adapter write the fixed 5120-byte mapping directly into the object-owned
pixel buffer, verifies the adapter metadata, and owns the initial GObject
reference until `goodix_fpimage_pipeline_free()`.

The physical scan resolution remains target-specifically unknown. The opaque
owner records `GOODIX_FPIMAGE_PHYSICAL_PPMM_UNKNOWN` separately; the numerical
zero left by GObject initialization is not treated as a measurement. D279/02
verified that libfprint 1.94.100 uses `ppmm` only for reliability quality that
is discarded before Bozorth3, so the local gate no longer blocks NBIS while it
still leaves `FpImage::ppmm` unset. This does not prove biometric quality or
authorize preprocessing, matching, enrollment, or live use. Image flags remain
zero solely because no orientation or polarity transformation is yet justified.

## D279/03 Fedora 44 registration boundary

The standard Meson registry in the Fedora 44/libfprint 1.94.100 reference now
builds the canonical sources in this directory as `goodix_27c6_5125`. The
registered USB subclass has the single exact ID `27c6:5125`, reuses the same
`GoodixDeviceContext` as the host-only and D278 paths, and omits the historical
SIGFM selector only under the target-specific NBIS build definition. No
physical `ppmm` is assigned.

`tests/run_goodix_fedora44_registration_test.sh` performs the offline
production-shaped build and checks the generated registry, linked type symbol,
USB ID listing and zero-reachability of USB enumeration in the listing tool.
It does not install libfprint, contact fprintd or access a USB device. A fully
operational fprintd open/claim/secret lifecycle remains a later boundary.

## D279/04 inert runtime-input providers

`goodix_runtime_inputs.[ch]` closes the LGPL computation gap for the two
runtime inputs that had previously existed only in the GPL operator harness.
It extracts the two six-byte D190 producer seeds from hash-pinned inert PE
bytes and the 12-byte FDT seed from a hash/CRC/OTP-bound cache byte array.  The
PE parser is adapted directly from the project-owned BSD-2-Clause D190 source;
the FDT provider is expressed from the neutral D255/D261 cache contract.

At the D279/04 baseline the unit had no filesystem, USB, discovery, subprocess,
executable mapping or write API. Failure zeroes every output, producer seeds
have an explicit cleanse API, and errors expose stable redacted classes.
Production pins are compiled but only synthetic fixtures are executed in the
host-only test; no authentic protected material is read.

## D279/05 private input file adapter

The same module now includes an explicit-path, read-only adapter for the PE and
cache inputs. It requires regular files with exact uid, mode `0600` and size,
uses `O_NOFOLLOW|O_CLOEXEC`, compares `fstat` identity/size/mtime/metadata
before and after the read, cleanses all allocated input buffers, and publishes
the three outputs atomically only after both inputs pass. Production requires
uid 0; test policy can select the current uid for synthetic temporary files.
It never searches paths or opens the three PSK/CONFIG inputs.

The Fedora 44 Meson target compiles the provider, binder and
protected-material loader, but `img_open` does not yet own/compose them or
claim interface 0. D279/05 does not choose installation paths and does not read
authentic protected material.

## D279/06 open-epoch material owner

`goodix_runtime_material.[ch]` composes the five explicit inputs into one
owner. It first validates the PE/cache pair, then loads the existing protected
manifest/transport/CONFIG90 boundary, binds the producer seeds, stores only
the non-owning secure descriptor plus FDT12, and cleanses all producer scratch.
Freeing the owner clears the descriptor and FDT seed and delegates PSK,
validator and CONFIG90 cleansing to the sole `GoodixTargetMaterial` owner.

Returned secure descriptors borrow the owner's storage and must be cleared by
callers after configuring the session. The synthetic suite proves complete
composition and teardown under normal and ASan/UBSan builds. D279/07 later
selected and validated the production paths.

## D279/08 production open/close binding

The registered USB subclass now loads the single runtime-material owner at
`img_open`, then claims only USB interface 0. The owner, borrowed secure view,
FDT12 and audit remain in the same `GoodixDeviceContext` for the complete open
epoch. Close and all open failures release the claim before clearing local
descriptors and freeing the owner; a second open creates a fresh epoch.

libfprint 1.94.100 itself opens `GUsbDevice` before invoking `img_open`, so the
target-compatible order is core USB open, material load, interface claim. No
USB submit or protocol action occurs in `img_open`. Injected test seams prove
ordering and failure cleanup without real paths or hardware; NULL seams select
the production loader and libgusb calls. Production activation still does not
start the secure/post-TLS graph, so this is not fprintd operational closure.

## D279/09 bounded production activation

For the registered USB subclass, activation now requires the drained
pre-session RX quiet boundary and then constructs the existing native secure
session, retained TLS and post-TLS lifecycle from the open-epoch material.
The first protocol OUT therefore cannot precede RX synchronization. Borrowed
secure/FDT views are cleared after both consumers copy their inputs; their sole
runtime-material owner remains alive until close.

Asynchronous sync, secure-session, post-TLS and receive-rearm failures are
routed to the appropriate libfprint activation/session completion. Synthetic
tests exercise that production vfunc without real paths or USB.

Enrollment remains deliberately disabled before any submit. Fedora 44
`FpImageDevice` expects five captures in one activation, while target evidence
and the current lifecycle stop at the second B0. D279/09 does not silently set
two stages or extrapolate an unproven third acquisition. Capture/identify are
only offline-wired and still require a separately authorized live validation.

## D279/11 configurable enrollment oracle

`goodix_enrollment_model.[ch]` is a host-only, zero-sender state oracle for the
three enrollment transition shapes observed in D279/10 ATTEMPT02. Its required
stage count is explicit configuration: 21 is the successful target-local count
from that run, not an OEM-wide constant. Only a primary B0 after `0x22` emits
the libfprint-oriented stage callback. The encrypted B0 after `0x20` is
consumed in its stable protocol position, but its possible quality, template
or NBIS relevance remains unknown.

The module has no USB/backend/TLS dependency and is not wired into the
production lifecycle or device vfuncs. It therefore validates sequencing and
stage accounting without enabling enrollment or changing sensor-reaching code.
`goodix_enrollment_pipeline.[ch]` composes the same oracle with the canonical
`u16 → FpImage` adapter. It requires one raster only at a primary B0, checks the
NBIS ppmm contract, exposes the image as transfer-none during the callback and
destroys it afterward. Non-primary events carrying a raster fail closed.

The 27c6:5125 `FpImageDevice` class now advertises the target-local 21-stage
policy observed in ATTEMPT02; the generic model remains configurable. With
terminal deferral enabled, the final primary raster is retained until the
terminal IRQ0200 so the caller can report finger-up before asynchronous image
extraction can complete enrollment. The full 21-stage framework fixture uses
the historical SIGFM test double and therefore proves state/progress ordering,
not production NBIS biometric quality. Production enrollment remains rejected
before any submit while the sensor-reaching lifecycle is still bounded.

`goodix_enrollment_command_plan.[ch]` provides the next zero-sender layer. It
maps the configured protocol position to typed `0x20/0x22/0x32/0x34/0x36/0x50`
intents and structural body classes, while deliberately exposing no body
bytes, A0 serializer or backend. For the observed 21-stage profile it matches
the enrollment-only ATTEMPT02 control counts. Dynamic per-cycle FDT tables and
timestamps remain a separate unresolved material contract.

`goodix_enrollment_command_body.[ch]` implements that structural contract
without adding a wire-frame serializer. It binds each FDT table to the exact
stage and role, requires a timestamp only for `0x32`, rejects stale or
extraneous material, and builds only the 2/14/16-byte inner body. Dynamic
derivation of per-cycle tables from IRQ observations remains outside this
layer.

## D279/12 target-local dynamic FDT state

`goodix_enrollment_fdt_state.[ch]` implements the hash-gated ATTEMPT02 table
relations without exporting authentic table bytes: `0x34` uses same-stage
IRQ2-up, `0x36` uses previous-stage IRQ0200-down, and `0x32` uses same-stage
IRQ0200-down plus a caller timestamp. Stage order and material availability
are fail-closed. The module has no A0 serializer, backend or submit path.

## D279/13 iterative enrollment lifecycle adapter

`goodix_enrollment_lifecycle_adapter.[ch]` transactionally composes the
configurable command plan, dynamic FDT state and inner-body contract. IRQ FDT
sources and primary rasters remain typed observations; the next command is
resolved once, cached (including its caller-supplied timestamp), and must be
committed exactly before another observation. Profiles 2/3/21 exercise the
full sequence. The adapter still has no A0 serializer, backend or submit path.

## D279/14 inbound post-TLS enrollment events

`goodix_enrollment_post_tls_events.[ch]` strictly maps complete decrypted A0
ACK/IRQ/NAV frames to the lifecycle adapter. Echo/status, IRQ control/id/flags
and the target-observed NAV no-check shape are state-bound and fail closed.
Primary samples and the opaque auxiliary B0 use separate typed calls. B0
reassembly/decoding, A0 serialization, transport and submit remain outside.

## D272/01 ephemeral SIGFM metric seam

`goodix_sigfm_metrics.cpp` wraps the repository-local LGPL SIGFM C API without
reimplementing it. It applies only the D269 mapper, contains every C++/OpenCV
exception at the C ABI, preserves the 25-keypoint gate, and distinguishes a
valid score zero from matcher failure. The API intentionally exposes neither
SIGFM serialization nor template storage; raster, u8 pixels and SIGFM objects
are transient and are released after comparison. Stack u8 pixels are
explicitly cleared, while complete zeroization of allocations owned internally
by C++/OpenCV cannot be guaranteed by this seam.

The synthetic test double verifies mapping and error plumbing only. On the
current D272 environment OpenCV4 development files are absent, so the real
SIGFM object cannot be compiled/linked and the full executable path remains
blocked. This is not evidence of target biometric quality.
