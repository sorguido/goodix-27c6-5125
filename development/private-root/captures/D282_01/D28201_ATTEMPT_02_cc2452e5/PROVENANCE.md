<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Provenance D282/01 attempt 02

I due file sotto `sanitized/` sono copie byte-identiche degli allegati forniti
dall'operatore nella nuova chat del 10 settembre 2026. Non contengono template
FP3, payload USB/TLS, raster, pixel, PSK o altro materiale biometrico/protetto.

Sorgenti operatore:

- `/home/guido/Scaricati/D282_01_ATTEMPT_02_cc2452e5/operator.log`
- `/home/guido/Scaricati/D282_01_ATTEMPT_02_cc2452e5/summary.env`

SHA-256:

```text
operator.log c6d680671af7bf6bb5b994980d5cd3f0131d7a3555caee4db301608e7ce4aa25
summary.env  e6b41990bbfe82e2bb8bae70cd504f37e76a4957e91a133cb6204c369e1cca4e
```

Limite probatorio: `operator.log` contiene una sola riga e `summary.env`
contiene soltanto lo stato aggregato/rollback. L'export non include journal,
audit `GOODIX_D282_EPOCH_AUDIT` o contatori protocollo della run fallita.
