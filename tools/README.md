<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# GPL tools boundary

New tools linked to or derived from the userspace core belong here under
`GPL-2.0-or-later`. Historical step-local tools remain at their existing paths.

`d264_first_image_offline.py` drives the public persistent coordinator with the
reviewed D263 synthetic fixtures. It cannot open real USB or materialize a real
secret and emits only non-biometric audit metadata.
