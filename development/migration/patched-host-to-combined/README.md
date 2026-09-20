# Inventario preliminare della migrazione — solo lettura

**OUTCOME=HUMAN_REQUIRED — GATE=PRIVILEGED_READ_ONLY_INVENTORY**

Il prompt Utente `AI_PM_MIGRATE_PATCHED_HOST_TO_COMBINED_CANDIDATE.md`, §§5 e
14 caso A, richiede questo stop prima di definire la migrazione: mancano gli
stati di ownership/rollback, sudoers, sudo.conf e metadata protetti leggibili
soltanto da root. La baseline sorgente esaminata è `development` a
`dfc33c3e44d6172dc7244b4f958ad71be3774be5`. Il commit che aggiunge questa directory
identifica la versione dello script; non serve approvare lo SHA come credenziale.

`inventory.py` è l'unico comando operatore. Non è un installer, un rollback o
una prova di autenticazione. Non esegue processi esterni, servizi, PAM, D-Bus,
USB o comandi di sistema. Emette soltanto JSON sul terminale; non crea log,
backup o file. I dati aperti usano `O_NOATIME`; gli antenati sono aperti senza
seguire symlink. Non ci sono parametri, selezione di root, retry o percorsi
presi dagli stati. I file di test usano esclusivamente directory sintetiche.

Da una **shell root già disponibile**, ottenuta tramite un percorso password
indipendente dal fingerprint e senza cambiare la configurazione, eseguire:

```bash
/usr/bin/python3 -I -B /home/guido/Repository/goodix-27c6-5125_private/development/migration/patched-host-to-combined/inventory.py
```

Non anteporre `sudo`: il sudo corrente seleziona D285 e può avviare il sensore
durante l'autenticazione. Lo script non acquisisce privilegi e non autentica.
Se non è disponibile una shell root con accesso password indipendente, fermarsi
e riportarlo; non modificare PAM/sudoers, non usare pkexec o provare il sensore
per ottenere il report. `-I -B` isola Python da moduli/configurazioni utente e
disabilita la scrittura di bytecode. Il comando funziona da qualsiasi directory.

Il solo output da restituire all'AI è il JSON completo. L'exit zero significa
che il report è stato raccolto, non che l'inventario o la migrazione sono PASS.
`UNKNOWN_STOP` segnala un errore, un tipo/percorso non sicuro o il superamento
di un limite; anche `ABSENT` va interpretato in review. Non riprovare con chmod,
nuovi privilegi o rimozione di file. Interrompere in caso di richieste di
autenticazione, attivazione sensore o comportamento diverso dalla sola stampa.

Le letture sono elencate integralmente nelle costanti e in `collect()`:

- sudoers e sudo.conf: metadata e digest; dai frammenti sudoers soltanto scope
  e selettori PAM, oltre alle direttive include. È una lettura lessicale,
  **non una valutazione della policy effettiva**: include esterni/custom richiedono
  review successiva; non vengono seguiti automaticamente.
- D285/D293/B5/D297 e login-early/login-three: soli campi software espliciti;
  pin/path template contenuti nello state D285 esclusi, chiavi sconosciute
  escluse. Nessun `source`/eval degli stati. Hash delle copie software di rollback.
- Cinque runtime storici già individuati: soli file software nominati,
  massimo 32 MiB ciascuno; stati testuali massimo 64 KiB.
- Template, materiale protetto e staging: esclusivamente path, tipo, owner,
  mode, dimensione e mtime. **Nessun contenuto, digest biometrico, PSK, manifest
  di materiali o capture viene aperto o esportato.** L'inventario delle directory
  è limitato a 128 entry per directory, profondità esplicita e budget di righe.
- Backup authselect, state KScreenLocker e directory del modulo SELinux B5:
  metadata; dei due backup PAM KScreenLocker soltanto digest software.

Nessun apply/rollback di migrazione viene consegnato prima della review di
queste letture. Il rollback dello script non è applicabile: non modifica il
sistema. D285 funzionante e tutti gli overlay restano presenti.

Verifica offline eseguita: otto test sintetici PASS, inclusi assenza di scritture
e variazioni atime, esclusione di contenuti/pin protetti, rifiuto di symlink,
hardlink e FIFO, limiti, errori leggibili e invocazione reale da `/tmp` rifiutata
senza root. Comando di sviluppo, da utente normale:

```bash
python3 -I -B development/migration/patched-host-to-combined/test_inventory.py -v
```

La ricostruzione e i limiti sono in [INVENTORY-REVIEW.md](INVENTORY-REVIEW.md);
il manuale tecnico rimane la fonte narrativa canonica. Dopo il report umano si
decideranno apply/recovery, baseline compatibile e riproduzione candidate; non
eseguire vecchi uninstall o installazioni mentre l'inventario è incompleto.
