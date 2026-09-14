<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D295/01 — Phase C source-first managed install

Data: 14 settembre 2026

## Decisione

La decisione Utente sostituisce il modello RPM come distribuzione ufficiale:

```text
PHASE_C_DISTRIBUTION_MODEL=SOURCE_FIRST_MANAGED_INSTALL
RPM_OFFICIAL_DISTRIBUTION=false
D294_RPM_ROLE=HISTORICAL_PROTOTYPE_AND_EVIDENCE
D294_RETROACTIVE_FAILURE=false
```

D294 non viene cancellato né retro-modificato. La sua build, i test e i limiti
restano evidenza storica valida; la live D294 è superata e non va eseguita nella
VM pulita.

## Avanzamento implementato

`deployment/phase-c-source-first-managed/` è indipendente dalle baseline D285,
D293 e D294. Il flusso ufficiale è:

```text
clone development
  -> production/build.sh normal (unprivileged, network-unshared)
  -> candidate content-addressed per commit
  -> root transaction gestita
  -> runtime immutabile + systemd + SELinux + fprintd
  -> materiali protetti importati separatamente
  -> PAM/KDE osservati nella clean VM
```

La candidate contiene la libreria libfprint production, le dipendenze private
GUsb/OpenCV già pin/verificate dal builder, wrapper, drop-in, guard B5 e sorgente
della policy SELinux. Non contiene RPM, PAM, materiale protetto, firmware,
template o output Dxxx.

Il gestore espone `prepare`, `install`, `update`, `status`, `rollback`,
`uninstall` e `import-materials`. La runtime usa directory immutabili denominate
col commit e symlink atomico `current`. Il primo install è idempotente; un update
conserva un solo slot precedente; un secondo update fallisce chiuso. Rollback
scambia current/previous. Uninstall verifica state e hash, rimuove solo file
attribuibili e preserva materiali e template.

La guard account-deletion e la policy sono copie production del comportamento
D293/B5 target-proven. Non sono stati importati nuovi sorgenti Rockytkg e non
cambia il ledger esterno o il regime GPL-compatible già documentato.

## Materiali e PSK

Il runtime conserva i cinque path target-proven sotto
`/var/lib/goodix-5125-poc`, mode root:root `0700/0600`. Il gestore accetta solo
un set completo da directory esplicita, senza overwrite e senza log di contenuto
o digest. L'uninstall non lo cancella.

La sola origine dichiarata è un export legittimo dall'installazione Windows
originale legata allo stesso dispositivo. La VM Windows con driver OEM resta un
metodo osservativo del bootstrap, non un extractor generalizzato. Non sono
ammessi PSK zero/random/sostitutivi, cross-device, provisioning, firmware,
ClearApp, IAP o OTP.

## Verifica offline

Comando:

```text
python3 deployment/phase-c-source-first-managed/test_offline.py
```

Esito:

```text
Ran 6 tests
OK
```

Copertura:

1. candidate tampered respinta prima della mutazione;
2. rollback automatico di una installazione interrotta dopo la policy SELinux;
3. install, seconda installazione idempotente, update, status, rollback e
   uninstall su filesystem sintetico;
4. import separato e preservazione dei materiali all'uninstall;
5. safety wall statico: nessun enrollment/verify/PAM/provisioning PSK;
6. sintassi shell di tutti gli entrypoint.

Sono inoltre PASS `git diff --check`, la sintassi shell e la build reale
unprivileged da tree D295 pulito. Il builder ha verificato i cinque RPM OpenCV,
la source-of-truth e la patch, ha prodotto ABI fprintd/SONAME validi, zero
RPATH/RUNPATH e zero simboli host/test. La candidate contiene manifest e
SHA256SUMS coerenti, senza materiale protetto; il run ha dichiarato zero USB e
zero live. La build finale va sempre rieseguita dal commit HEAD effettivamente
usato nella VM.

## Documentazione canonica aggiornata

- `README.md`: entrypoint coerente col driver funzionante e col nuovo modello;
- `docs/PHASE_C_SOURCE_FIRST_INSTALL.md`: installazione, materiali, update,
  rollback, uninstall, recovery e test VM;
- `analysis/PROJECT_NEXT_STEPS_PLAN.md`: Phase C source-first e responsabilità
  documentali anticipate da Phase F;
- manuale tecnico: stato corrente, D294 storico e D295 Human Gate.

## Rischi residui e Human Gate

- installazione reale systemd/SELinux mai eseguita in clean VM;
- disponibilità futura delle NEVRA OpenCV Fedora 44 pinned da verificare;
- configurazione PAM della Fedora 44 KDE pulita non ancora osservata;
- import reale dei materiali non eseguito;
- sensore/USB e normale workflow KDE non raggiunti;
- update/rollback provati solo su root sintetica, non con fprintd reale.

Il gate successivo è quindi la VM Fedora 44 KDE pulita. Fermarsi prima di ogni
`sudo`, materiale protetto o USB finché l'Utente non decide di procedere.

```text
D295_01_OUTCOME=READY_OFFLINE_HUMAN_GATE_PENDING
D295_01_OFFLINE_TESTS=6_PASS
D295_01_SOURCE_FIRST_BUILD=PASS
D295_01_CANDIDATE_DIGESTS=PASS
D295_01_PRODUCTION_ABI=PASS
D295_01_REAL_SUDO_EXECUTED=false
D295_01_REAL_USB_ACCESS=0
D295_01_PROTECTED_CONTENT_READ=false
D295_01_PAM_CHANGED=false
NEXT_BOUNDARY=FEDORA_44_KDE_CLEAN_VM_MANAGED_INSTALL
PM_DECISION=HUMAN_REQUIRED
```
