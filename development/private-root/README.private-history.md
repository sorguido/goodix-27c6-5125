<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 27c6:5125 per Fedora KDE

Driver Linux sperimentale ma funzionante sul target ristretto Goodix USB
`27c6:5125` / `GF_ST411SEC_APP_12509`, integrato nello stack standard
`libfprint -> fprintd -> PAM/KDE` di Fedora 44 KDE.

Lo stato attuale non è una release pubblica. Enrollment, verifica, login Plasma,
sblocco KDE, `sudo`, multi-utente e cancellazione account sono stati provati sul
target reale. Phase C ha inoltre chiuso l'installazione source-first gestita,
ripetibile e reversibile su una Fedora 44 KDE pulita, incluso il lifecycle
rollback/uninstall/recovery.

```text
CURRENT_PHASE=C_CLOSED
PHASE_C_CLOSED=true
PHASE_C_DISTRIBUTION_MODEL=SOURCE_FIRST_MANAGED_INSTALL
RPM_OFFICIAL_DISTRIBUTION=false
D294_RPM_ROLE=HISTORICAL_PROTOTYPE_AND_EVIDENCE
PRODUCTION_READY=false
FINAL_PHASE_C_BASELINE=448f5c8cc6099032a23115a96e90428d75b74a7b
NEXT_PHASE=D
NEXT_GATE=NONE_PHASE_C_CLOSED
PM_DECISION=PROJECT_STEP_COMPLETE
```

## Percorso supportato

1. clonare il repository e fare checkout di `development`;
2. preparare una candidate dalla source-of-truth `production/`, senza privilegi;
3. ispezionare i marker e gli hash della candidate;
4. dopo Human Gate, installarla con il gestore in
   `deployment/phase-c-source-first-managed/`;
5. importare separatamente il materiale protetto legittimo dello stesso
   dispositivo;
6. validare reader, enrollment e login dal normale workflow KDE/fprintd.

La guida operativa completa, inclusi prerequisiti, update, rollback, uninstall,
recovery e origine lecita dei materiali, è in
[`docs/PHASE_C_SOURCE_FIRST_INSTALL.md`](docs/PHASE_C_SOURCE_FIRST_INSTALL.md).
La composizione riproducibile è descritta in
[`production/README.md`](production/README.md). Il manuale tecnico canonico è
[`Goodix 27c6 5125 manuale tecnico.md`](Goodix%2027c6%205125%20manuale%20tecnico.md).

## Sicurezza e limiti

- Nessun firmware, IAP, ClearApp, OTP o provisioning PSK è consentito.
- Secret, cache target, DLL OEM e template biometrici non entrano nel repository,
  nella candidate o nei log.
- Il materiale autentico è riutilizzabile solo se recuperato legittimamente
  dall'installazione Windows originale e per lo stesso dispositivo.
- Il gestore non modifica il PAM vendor in `/usr/lib`: genera e governa un
  override `/etc/pam.d/plasmalogin` dalla copia vendor verificata, con una sola
  regola Fedora-style `pam_fprintd` e fallback password invariato.
- L'RPM D294 resta conservato come prototipo storico; non è il formato ufficiale
  di distribuzione e non va installato sul nuovo ambiente di prova.
- Altri sensori, firmware, distribuzioni e desktop non sono supportati.

## Sviluppo e provenienza

`production/` è l'unica autorità di composizione. `analysis/`, `operator_kit/`,
`packaging/d294-phase-c-runtime/` e i percorsi Dxxx sono evidenza storica o di
test, non dipendenze runtime del percorso ufficiale. Licenze, origini e limiti
di redistribuzione sono registrati in
[`docs/LICENSING_AND_PROVENANCE.md`](docs/LICENSING_AND_PROVENANCE.md).
