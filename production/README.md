<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Production source-of-truth

Questa directory è l'autorità di **composizione** del build production per
Fedora KDE x86_64 e Goodix `27c6:5125` / APP12509. Non duplica il tree
libfprint completo: ricostruisce il baseline Fedora/libfprint 1.94.100 dal
commit Git pristine `f609c865f760768edb6a9e404b863ccd0569e1c8`, applica
`patches/0001-goodix-fedora44-production.patch` e aggiunge soltanto il subset
Goodix/SIGFM/R2 elencato in `source-files.tsv`.

Il requisito del commit pristine implica che un clone shallow privo di quel
commit non è sufficiente: `build.sh` fallisce prima della build. Il tree già
patchato sotto `reference/` viene usato solo per verificare la rigenerazione
della patch, mai come sorgente dell'assembly.

Invocazione unprivileged e offline:

```text
production/build.sh normal /percorso/assoluto/output
production/build.sh sanitizer /percorso/assoluto/output
```

L'output deve essere nuovo o vuoto. La build usa il Flatpak SDK 25.08 già
installato con rete disabilitata, verifica i cinque RPM OpenCV locali e non
esegue installazione host, enumeration USB, material loader o deploy. Il solo
artefatto principale è `libfprint-2.so.2.0.0`, accompagnato dalle dipendenze
runtime staging e dai report di build/ABI.

Licensing/provenance: baseline Fedora e delta core conservano LGPL; sorgenti
locali conservano la licenza per-file; SIGFM Rocky è LGPL e il subset R2
preprocessor/imgproc è GPL-2.0-or-later. Il combined work resta nel medesimo
regime GPL-compatible già documentato in `docs/LICENSING_AND_PROVENANCE.md`.
Nessun relicensing è introdotto.

