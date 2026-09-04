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

The unit has no filesystem, USB, discovery, subprocess, executable mapping or
write API.  Failure zeroes every output, producer seeds have an explicit
cleanse API, and errors expose stable redacted classes.  Production pins are
compiled but only synthetic fixtures are executed in the host-only test; no
authentic protected material is read.  The Fedora 44 Meson target compiles the
provider, binder and protected-material loader, but `img_open` does not yet
connect them to file loading, interface claim or the secure session.

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
