<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# libfprint driver boundary

This directory contains the upstream-facing driver and image integration.
Existing LGPL files retain `LGPL-2.1-or-later`; licensing remains per-file.
The current Goodix-enabled production build also links the separately
ledgered GPL Rockytkg R2 component, so distribution of that combined build
must use GPL-compatible terms while preserving every original notice and
grant. Direct reuse still requires per-file provenance, rights/third-party
review and compatible destination terms; it does not retroactively relicense
the preserved upstream libfprint sources.

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

The original D279/03 runner was NBIS-only. Its outer compatibility entrypoint
now delegates to the D279/52 production-shaped SIGFM action closure, which
checks the generated registry and exact USB ID listing in addition to the
action path. It requires the pinned Fedora OpenCV RPM directory and does not
install libfprint, contact fprintd or access a USB device. The old inner runner
is retained only as historical provenance.

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
ordering and failure cleanup without real paths or hardware. Those setters are
compiled only with `GOODIX_ENABLE_TEST_SEAMS`; the production library contains
neither their symbols nor the direct receive-injection helper. The unmodified
production build therefore selects the runtime loader and libgusb calls.

## D279/09 bounded production activation

For the registered USB subclass, activation now requires a bounded host
pre-session RX deadline completion without bytes and then constructs the native secure
session, retained TLS and post-TLS lifecycle from the open-epoch material.
The first protocol OUT therefore cannot precede RX synchronization. Borrowed
secure/FDT views are cleared after both consumers copy their inputs; their sole
runtime-material owner remains alive until close.

The host deadline is a transition/safety bound only. It does not prove a
device-side timeout or quiescence, either normally or after interruption.

Asynchronous sync, secure-session, post-TLS and receive-rearm failures are
routed to the appropriate libfprint activation/session completion. Synthetic
tests exercise that production vfunc without real paths or USB.

This section records the D279/09 boundary. D279/28 supersedes its enrollment
gate with the reviewed 21-stage one-shot binding described below.

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
IRQ0200-down plus a caller timestamp. D279/59 centralizes the contextual flag
contract in `goodix_fdt_irq_policy.[ch]`: contact requires a nonzero subset of
the six FDT channel bits, zero-touch contexts require exact zero, and the
actual bitfield selects active/fallback FDT-up channels. Stage order and
material availability are fail-closed. The module has no A0 serializer,
backend or submit path.

## D279/13 iterative enrollment lifecycle adapter

`goodix_enrollment_lifecycle_adapter.[ch]` transactionally composes the
configurable command plan, dynamic FDT state and inner-body contract. IRQ FDT
sources and primary rasters remain typed observations; the next command is
resolved once, cached (including its caller-supplied timestamp), and must be
committed exactly before another observation. Profiles 2/3/21 exercise the
full sequence. The adapter still has no A0 serializer, backend or submit path.

## D279/14 inbound post-TLS enrollment events

`goodix_enrollment_post_tls_events.[ch]` strictly maps complete decrypted A0
ACK/IRQ/NAV frames to the lifecycle adapter. Echo/status and IRQ control/id
remain exact; IRQ flags use the centralized D279/59 context policy rather
than duplicated magic values. Zero contact, reserved bits and nonzero
bootstrap/finger-up flags fail closed. The target-observed NAV no-check shape
is likewise state-bound and fail closed.
Primary samples and the opaque auxiliary B0 use separate typed calls. B0
reassembly/decoding is added by the D279/15 layer below; A0 serialization,
transport and submit remain outside.

## D279/15 bounded B0 plaintext delivery

The inbound event layer also reassembles a single declared-length plaintext
B0 within an 8192-byte bound. Primary B0 retains the exact 7693-byte image
decoder contract. Auxiliary B0 is never decoded or discarded: the complete
unchanged message is delivered to a mandatory opaque callback before the
lifecycle transition. Serialization, transport and submit remain absent.

## D279/16 enrollment-only outbound serializer

`goodix_enrollment_outbound_frame.[ch]` revalidates a prepared inner body and
serializes only controls `0x20/0x22/0x32/0x34/0x36/0x50` into zero-padded
fixed64 A0. It has no backend or submit API. Known persistent families are not
allowlisted. That is an allowlist guardrail over known families, not proof that
no other sensor-side persistence is possible.

## D279/28 and D279/55 production USB action binding

For `FPI_DEVICE_ACTION_ENROLL`, the registered USB action installs the exact
target-observed 21-stage enrollment graph between the retained post-TLS
lifecycle and the existing production `GoodixFpiUsbBackend`. All B0
application plaintext reaches the graph through the authenticated TLS server.
The auxiliary B0 stays opaque and is counted without interpretation.

For `FPI_DEVICE_ACTION_IDENTIFY`, D279/55 keeps the same target-specific OEM
bootstrap and release lifecycle but selects a single-acquisition profile. One
primary B0 is passed through the Rockytkg-derived R2/SIGFM path; after the
release `0x34 -> IRQ 0x0200 -> 0x20 -> B0 -> 0x50 -> NAV`, the lifecycle enters
`STOP` before libfprint release callbacks. It never enters `REARM_GATE`, sends
no second `0x32`, and cannot request a second image. Public verify falls back
to the image-device identify action with a one-print gallery in this libfprint
version, so it uses the same boundary.

Enrollment and identify are admitted by the production action allowlist;
capture remains rejected. The first admitted attempt consumes the complete
open epoch even on failure.
A second action is rejected before generation allocation or USB submit, and a
full close/open is required. There is no retry, automatic reopen, reset,
clear-halt, or persistent-family sender. Multi-action reactivation and fprintd
packaging remain intentionally outside this first-live boundary.

The offline production-shaped test covers open, pre-session host deadline,
secure protocol, real TLS 1.2 PSK handshake, post-TLS bootstrap, all 21 stages,
one libfprint completion, second-action rejection, and close/release. Its USB
and protected-material inputs are test seams, so it records zero real USB
submits. The Fedora 44 production library is separately built without any of
those transcript seam symbols; the native NBIS action remains covered by the
exact-target D279/27 test.

## D279/17 completion-gated synthetic OUT transaction

`goodix_enrollment_outbound_transaction.[ch]` joins the serializer to an
abstract host-test sink. Exactly one frame may be pending; the lifecycle is
committed only after a positive same-generation completion. Early inbound,
duplicate OUT, stale generation and transport failure are terminal with zero
retry. The module has no production USB backend dependency.

## D279/18 dormant FpiUsbBackend binding

`goodix_enrollment_fpi_usb_binding.[ch]` adapts the transaction sink and OUT
completion callback to the existing `GoodixFpiUsbBackend`. Construction sends
nothing. Offline tests require the asynchronous host seam and prove zero real
USB submit. No production device code constructs the binding, and the
pre-activation enrollment rejection remains intact.

## D279/19 terminal cancellation and OUT drain

The dormant enrollment binding now cancels the backend first, terminally
fences its transaction without retry, and remains non-freeable while its
physical OUT completion is outstanding. A late same-generation cancellation
completion drains the backend but cannot commit the lifecycle planner. The
operation is idempotent and still has no production device-context owner or
caller; production enrollment remains rejected before activation.

## D279/20 dormant device-context ownership

During an explicit host-only operator epoch, the device context may adopt an
already constructed enrollment binding only when it uses the context backend
and current generation and no TLS, secure-session, or legacy post-TLS owner is
present. The binding owns its event graph after successful construction; the
context cancels it at the terminal fence and frees the graph only after backend
drain. The context neither constructs nor submits through the binding, and the
production enrollment activation gate remains unchanged.

## D279/21 first-arm backend handoff

The legacy post-TLS lifecycle has an optional, pre-start callback that stops
after the initial `0x32` arm ACK, with no OUT outstanding, and transfers the
single backend completion slot before the first IRQ2. The default two-capture
path is unchanged. Host-only tests prove that the next owner keeps its callback
even after the legacy lifecycle is freed. No production caller configures this
handoff and no real USB submit is performed.

## D279/22 ordered enrollment contact callbacks

The strict inbound enrollment layer can optionally emit validated contact
events. IRQ2 produces finger-down only after adapter acceptance; IRQ0200
produces finger-up after acceptance and, on the terminal stage, after the
deferred `FpImage` has synchronously entered the libfprint capture path. This
orders finger-up before asynchronous extraction completion without inventing
an image from IRQ data. Callback rejection is terminal and retry-free.

## D279/23 graph-ready enrollment progression

The dormant FpiUsb binding now advances one command automatically only after
an accepted A0 or completed plaintext message leaves the parametric graph in a
command slot. Inbound slots and fragmented plaintext do not submit; each OUT
still commits only on its matching positive backend completion. This is a
host-tested prerequisite for the first-arm context handoff, not a production
enrollment caller or gate change.

## D279/24 context-owned first-arm handoff

An explicit offline configuration seam lets `GoodixDeviceContext` prepare a
parametric enrollment graph before the legacy post-TLS lifecycle starts. At
the drained first-arm boundary the context transfers event ownership into the
FpiUsb binding, routes later A0/TLS plaintext to it, and rearms protocol receive
after each positive OUT completion. A synthetic bootstrap-through-first-IRQ2
test covers the ownership transition; production enrollment remains rejected
before activation and has no configuration caller.

## D279/25 complete target-local 21-stage context transcript

The host-only operator epoch can inject already-decrypted B0 plaintext through
the router only when no secure session exists; production always takes the TLS
branch first. The regression drives the full ATTEMPT02-shaped 21-stage graph
through the context: 125 completion-gated commands, 21 primary images, 21
opaque auxiliary deliveries and 21 ordered contact pairs. The stage count is
test configuration, not a universal OEM constant, and completed bindings are
not retroactively cancelled during teardown.

## D279/26 true libfprint 21-stage action

The same ATTEMPT02-shaped transcript now runs inside a real asynchronous
`fp_device_enroll()` action on the virtual host-only device. It reports all 21
progress callbacks, returns one `FpPrint`, completes once, deactivates and
closes without cancelling the already-complete enrollment binding.

The router plaintext injection used by this regression is allowed only for an
operator epoch or a non-production device and only when no secure session
exists. The registered USB subclass still rejects enrollment before creating
a generation, and the source audit still proves that no production caller can
configure the enrollment graph. The host action uses the historical SIGFM
test double; the Fedora 44 build compiles the same driver with native NBIS but
does not execute biometric extraction, so target NBIS quality remains unknown.

## D279/49 production SIGFM preprocessing boundary

`goodix_sigfm_preprocess.[ch]` fixes the authenticated D279/48 R2 chain for
the canonical 80×64 u16/12-bit frame plus a session-local baseline. The
algorithm implementation under `rockytkg-imgproc/` is a GPL-2.0-or-later
minimal adaptation of the preserved Rockytkg source: its image stages remain,
while the complete `goodix_dev`, environment overrides and debug/file dump
surface are absent. No USB, TLS, secret or persistence API is reachable.

`tests/run_goodix_sigfm_preprocess_test.sh` validates argument/range failure
before output mutation, audits forbidden symbols, and reproduces the exact
D279/48 R2 KAT digest
`2ff834cdef0316b3280d86a46fa75881c50bff3f4240e03dc31c24f6fc4153b3`.
The host sanitizer lane reports an explicit environment block when `libasan`
is absent. The same ASan/UBSan suite passes offline in the already installed
Freedesktop SDK 25.08 (LeakSanitizer disabled at the sandbox ptrace boundary).

This slice does not yet bind preprocessing to the libfprint action or persist
SIGFM templates. The next boundary connects the baseline-aware output to real
SIGFM extraction and establishes strict sample ownership/storage.

## D279/50 SIGFM ownership and strict storage

D279/50 extends the original D272 C++ seam with production-grade owned sample
copy, extraction from D279/49 preprocessed pixels, matching, and a bounded
storage envelope. The Rockytkg extraction/match/copy/serialization functions
remain the implementation; the local wrapper contains every exception at the
C ABI and validates the native Rocky payload before deserialization.

The `GSF1` envelope is currently restricted to the target x86_64
little-endian ABI. It carries version, ABI marker, keypoint count, payload
length and CRC-32. The inner parser requires 25..1024 keypoints, exact SIFT
128×float descriptors, exact length, finite keypoint/descriptor floats and
80×64 coordinate bounds. A successful deserialize must reserialize
byte-identically before ownership is released to the caller. Invalid data is
rejected before Rockytkg/OpenCV allocation.

The test-double suite passes normal and ASan/UBSan paths. The real
`sigfm.cpp` suite passes against the five Fedora 44 OpenCV 4.13 RPMs already
pinned by D279/48, extracted only under `/tmp`; no package is installed. It
proves real extraction (220 keypoints), copy, strict round-trip, corruption
rejection and matching. `run_goodix_sigfm_storage_real_test.sh` reproduces the
closure from a directory containing those RPMs.

This is the inner sample format only. D279/51 must forward-port its multi-sample
container into libfprint 1.94.100 FP3 serialization and verify/identify paths.

## D279/51 Fedora 44 SIGFM print core

The Fedora 44/libfprint 1.94.100 fork now has a private `FPI_PRINT_SIGFM`
type with 1..21 owned samples, single-sample probes, SIGFM score dispatch and
strict FP3 `(a(ay))` storage. Every stored `ay` is the bounded D279/50 `GSF1`
envelope; copy, equality and deserialization stay behind the exception-safe C
wrapper. Builds without SIGFM reject the type rather than treating it as raw.

The focused double suite passes normal and ASan/UBSan paths. A separate
closure links the authentic preserved Rockytkg `sigfm.cpp` with the pinned
Fedora OpenCV RPMs and proves extraction, match and byte-identical FP3
round-trip on a deterministic non-biometric raster. It does not validate a
production threshold or target biometric accuracy.

## D279/52 SIGFM image action and production Meson binding

The registered Goodix class now selects SIGFM in the real `FpImageDevice`
action path. The initial authenticated FDT B0 is decoded and retained only for
the session; each primary 80x64 u16 raster is transformed by the exact R2
pipeline before asynchronous SIGFM extraction. Baseline and source rasters are
cleansed at owner teardown.

Template append is checked and atomic. If copying the new SIGFM sample fails,
the destination is unchanged and enrollment completes with an error before
the progress callback; the stage counter cannot advance. The focused suite
injects that failure and passes normal plus ASan/UBSan.

The production Meson graph compiles the R2 component, the real Rockytkg SIGFM
source and OpenCV4. The compatibility-named
`tests/run_goodix_fedora44_nbis_action_test.sh` is now the D279/52 SIGFM action
runner: given the pinned OpenCV RPM directory, it builds the production graph
and checks the standard registry. At D279/52 it executed 21 real SIGFM
enrollment stages. D279/57 subsequently moved the current production action
to the target-proven fixed-eight policy; the same runner now executes eight
stages on a deterministic non-biometric raster with zero USB access, while the
21-stage transcript remains regression evidence. The historical
filename avoids unnecessary test reorganization; its markers identify D279/52.
The default score threshold remains plumbing only and is not a FAR/FRR or
different-finger validation.

## D279/53 public FP3 and true SIGFM identify interoperability

The same production-shaped build originally proved that the 21-sample enrollment
template survives the public `fp_print_serialize()`/
`fp_print_deserialize()` boundary with metadata intact and can be used as the
gallery for a true host-only `fp_device_identify()` action. The deterministic
single-sample SIGFM probe matches and both the gallery match and scanned print
are returned.

Fedora 44/libfprint 1.94.100 validates non-NBIS scanned prints by byte equality
against the gallery. D279/53 extends the existing matcher-backed NBIS
exception to SIGFM, whose single-sample probe is intentionally not identical
to its multi-sample template. This is a local adaptation of the newer Fedora
core; the older Rockytkg tree has no equivalent validation.

The runner also audits, without executing it, the exact installed
`fprintd-1.94.5-5.fc44.x86_64` binary. Its `libfprint-2.so.2` dependency and
all 47 required `LIBFPRINT_2.0.0` symbols are satisfied by the built library.
This does not prove daemon execution, on-disk policy, D-Bus/SELinux behavior,
production identify protocol safety or a biometric threshold. At this
historical boundary the production driver remained enrollment-only; D279/55
later enabled the separate target-derived single-acquisition identify profile.

## D280/01 close/open template reuse composition

The target Fedora build now carries only serialized FP3 bytes across a device
close/open boundary: it destroys the eight-sample source print, opens a new
host-only context, deserializes the bytes and completes a real SIGFM identify.
It also rejects a corrupted FP3 header. The byte blob remains in memory and
fprintd is not executed.

A complementary full production-shaped test exercises enrollment, context
teardown, a fresh open/secure-session/TLS epoch and single-acquisition identify
through the fake USB backend. Successful match and legitimate no-match use
separate open epochs and both end with zero re-arm, retry and outstanding
transfer. This harness uses the historical deterministic SIGFM test double;
real extraction, FP3 and matching are covered by the target Fedora test. The
combination proves offline composition, not authentic biometric reuse, a
production threshold, disk persistence or end-user integration.

The accompanying D280/01 operator boundary is intentionally outside the
installed driver. It can build a baseline-bound client for one eight-stage
enrollment and one single-acquisition identify in distinct open epochs. An
authentic FP3 would exist only as a root-owned 0600 file between those epochs
and is unlinked before identify; logs and export exclude its bytes and hash.
The offline preflight passes, but no baseline or live run is authorized.
Unlinking is not a physical-erasure guarantee for SSD, CoW, journal or
snapshot storage.

## D272/01 historical ephemeral SIGFM metric seam

`goodix_sigfm_metrics.cpp` wraps the repository-local LGPL SIGFM C API without
reimplementing it. It applies only the D269 mapper, contains every C++/OpenCV
exception at the C ABI, preserves the 25-keypoint gate, and distinguishes a
valid score zero from matcher failure. The API intentionally exposes neither
SIGFM serialization nor template storage; raster, u8 pixels and SIGFM objects
are transient and are released after comparison. Stack u8 pixels are
explicitly cleared, while complete zeroization of allocations owned internally
by C++/OpenCV cannot be guaranteed by this seam.

At D272 the synthetic test double verified mapping and error plumbing only,
because OpenCV4 development files were absent. D279/48 and D279/50 later close
the real-SIGFM executable path using hash-pinned extracted Fedora RPMs. The
historical limitation was not evidence of target biometric quality.
