<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# GPL tools boundary

New tools linked to or derived from the userspace core belong here under
`GPL-2.0-or-later`. Historical step-local tools remain at their existing paths.

`d264_first_image_offline.py` drives the public persistent coordinator with the
reviewed D263 synthetic fixtures. It cannot open real USB or materialize a real
secret and emits only non-biometric audit metadata.

`d268_live_first_image_once.py` è l'entrypoint esclusivo del Kit Operatore
D268. Il suo `--dry-run` verifica offline authority, hash e launcher senza
costruire dipendenze reali; il futuro ramo live richiede flag D268 esatto e
baseline Git full-SHA approvata, oggi entrambi non autorizzati.
