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
zero left by GObject initialization is not treated as a measurement or usable
NBIS input. `goodix_fpimage_pipeline_check_ppmm_requirement()` therefore blocks
NBIS explicitly. Its OK result for SIGFM means only that the locally audited
SIGFM extractor does not consume `ppmm`; it does not select an extractor or
authorize preprocessing, matching, enrollment, or live use. Image flags remain
zero solely because no orientation or polarity transformation is yet justified.

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
