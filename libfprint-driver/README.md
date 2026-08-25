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
