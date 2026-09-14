<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D294/01 — prima candidate RPM runtime Phase C

## Scopo

Validare che la stessa libreria production D293 possa essere costruita e
attivata tramite un RPM Fedora package-managed. Il pacchetto installa la sola
libreria privata, il wrapper fprintd e un drop-in systemd con priorità `99`.
Non include materiali protetti, template, firmware o configurazione PAM e non
rimuove D293/B5: la baseline validata precedente resta il rollback immediato.

Questo boundary non corregge il ritardo password di circa 30 secondi per utenti
enrolled. Non modifica `plasmalogin`, authselect, KScreenLocker, sudo, Polkit o
timeout PAM. La modularizzazione dei consumer è lavoro Phase C successivo.

## Prerequisiti e STOP

- branch `development`, HEAD allineato a `origin/development`, worktree pulito;
- Fedora 44 x86_64 e versioni esatte verificate da `install.sh`;
- RPM preparato in `dist/` per l'HEAD corrente oppure `rpmbuild` disponibile
  per ricostruirlo in modo unprivileged;
- i cinque RPM OpenCV locali passano il manifest SHA-256 già versionato;
- baseline D293 e guard B5 installate e funzionanti;
- nessuna UI biometrica o action fprintd in corso.

`STOP_IF=` un prerequisito fallisce, D293/B5 mostra drift, la build RPM non è
verde, compare una richiesta di rimuovere la baseline precedente, oppure si
osserva qualsiasi modifica PAM inattesa.

## Installazione

Dalla root del repository, come utente normale:

```bash
packaging/d294-phase-c-runtime/install.sh
```

Lo script usa l'RPM già preparato e verificato per l'HEAD corrente; se manca,
lo ricostruisce offline dalla source-of-truth `production/`. Usa `sudo` per una
sola installazione `dnf5`. Installa anche gli RPM locali
`opencv-features2d`/`opencv-flann` solo se mancanti, registrandone lo stato per
il rollback. Ferma e ripristina fprintd secondo lo stato iniziale.

Attendere i marker:

```text
D294_01_INSTALL=PASS
D294_01_D293_FALLBACK=PRESERVED
D294_01_D293_B5_FALLBACK=PRESERVED
```

## Workflow reale

1. Aprire Impostazioni di sistema → Utenti e verificare che il reader sia
   visibile e che le impronte già registrate siano elencate.
2. Da terminale eseguire `fprintd-verify`. Effettuare fino a tre tentativi
   fisici indipendenti, fermandosi immediatamente al primo MATCH. Non eseguire
   un quarto tentativo.
3. Verificare un normale login fingerprint Plasma. Non testare deliberatamente
   il fallback password lento: il limite UX è già accettato e non cambia.
4. Confermare che il principal Guido e le print esistenti siano invariati.

`PASS_IF=` reader e template restano visibili, almeno un MATCH avviene entro
tre tentativi, il login fingerprint riesce e non compaiono regressioni.

`FAIL_IF=` package/runtime non si attiva, reader o template spariscono, tre
NO_MATCH consecutivi chiudono la serie, login fingerprint fallisce, PAM cambia
o compare una regressione.

`STOP_IF=` al primo failure, comportamento inatteso o instabilità. Non eseguire
retry nascosti, una seconda serie o diagnostica invasiva.

## Rollback

Dopo PASS lasciare installata la candidate. Dopo FAIL, instabilità o
regressione, dalla root del repository eseguire come utente normale:

```bash
packaging/d294-phase-c-runtime/uninstall.sh
```

Il rollback rimuove l'RPM e soltanto le due dipendenze OpenCV che non erano
presenti prima, ricarica systemd e riattiva D293. Non rimuove B5, template,
materiali protetti o configurazione PAM. È completo solo con:

```text
D294_01_ROLLBACK=PASS
D294_01_D293_BASELINE=RESTORED
D294_01_D293_B5=PRESERVED
```

## Cosa riportare

Riportare PASS oppure il primo step fallito e il messaggio visibile; indicare
il numero del tentativo che ha prodotto MATCH, lo stato del login fingerprint,
l'invarianza di Guido e se la candidate è rimasta installata o è stato eseguito
il rollback.
