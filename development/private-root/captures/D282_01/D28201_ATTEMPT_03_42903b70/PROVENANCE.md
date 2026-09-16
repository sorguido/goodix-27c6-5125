<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Provenance D282/01 attempt 03

I tre file sotto `sanitized/` sono copie byte-identiche degli allegati forniti
dall'operatore il 10 settembre 2026. Non contengono template FP3, payload
USB/TLS, raster, pixel, PSK o altro materiale biometrico/protetto.

Sorgenti operatore:

- `/home/guido/Scaricati/D282_01_ATTEMPT_03_42903b70/operator.log`
- `/home/guido/Scaricati/D282_01_ATTEMPT_03_42903b70/summary.env`
- `/home/guido/Scaricati/D282_01_ATTEMPT_03_42903b70/phase-a-audit.raw`

SHA-256:

```text
operator.log      f9751a16cd6985adad69e4013b40a9a02c5df212d16375a08c0e0feeab81e291
summary.env       84edc196d617ced362eff4b3bd7ae598bbd42e3002efb9dfdfc896a80d8cc459
phase-a-audit.raw 36cb1223a8a0de4b6491933929a1ce239da9f40862b8b0b395bbf2c8d420c12a
```

Il documento di contesto operatore allegato separatamente ha SHA-256
`ab235489406232a44a190d9c6f5fd7f6cb89d1d0c2b492a2f2b962039348f4af`.
È una ricostruzione narrativa e non sostituisce i tre file sopra come evidenza
primaria. Attesta inoltre l'output client `enroll-completed` dopo otto contatti
e `verify-match` dopo un contatto dello stesso indice destro; questi due esiti
client non sono presenti nell'export sanitizzato minimo.

Limite probatorio: la run si è fermata prima della Phase B. Non esistono in
questo export un'acquisizione dell'indice sinistro, un risultato different-
finger, la Phase C/delete o l'audit finale a quattro epoch.
