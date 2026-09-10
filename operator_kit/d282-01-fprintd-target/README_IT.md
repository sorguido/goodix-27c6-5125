<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/01 — fprintd target con staging reversibile

## Stato e scopo

Questo kit è **solo candidato per review**. Non esistono baseline approvata,
grant o autorizzazione live D282/01. Il preflight è offline e non enumera USB;
le modalità candidate/live non devono essere avviate finché una review
AI-PM indipendente e una successiva Human Gate non abbiano autorizzato
esplicitamente una singola run su un full SHA.

La futura run copre soltanto il vero `fprintd-1.94.5-5.fc44.x86_64` con il
driver Goodix `27c6:5125`: enrollment dell'indice destro, FP3 SIGFM nello
storage isolato, restart del daemon, verify dello stesso dito, un verify con
indice sinistro atteso no-match, delete e rollback. PAM, login e sudo come
fattore di autenticazione sono fuori scope.

```text
D282_01_HUMAN_GATE_READINESS=READY
CURRENT_LIVE_AUTHORIZED=false
CURRENT_PRIVILEGED_INSTALL_AUTHORIZED=false
APPROVED_BASELINE=NONE
GRANT_CREATED=false
LIVE_EXECUTION_PERFORMED=false
DIFFERENT_FINGER_NO_MATCH=UNPROVEN_LIVE
SECOND_SENSOR_REACHING_ACTION_COUNT=0
```

## Perché VERIFY e politica anti-retry

Nel sorgente esatto Fedora, `fprintd-verify` carica la gallery. Se esiste un
solo template ne seleziona il dito e chiama `fp_device_verify()`, non
`fp_device_identify()`. In caso `FP_DEVICE_RETRY`, `verify_cb()` rilancia
formalmente `fp_device_verify()` nello stesso open epoch senza effettuare da
sé open/close.

La fork D282 aggiunge VERIFY al core SIGFM e gli assegna lo stesso profilo
Goodix `SINGLE_ACQUISITION` già provato live per IDENTIFY. Dopo il primo
dispatch, `production_action_consumed` resta impostato per tutta la open epoch:
un secondo VerifyStart, incluso quello automatico di fprintd dopo extraction
failure, è respinto prima di nuova generazione, TLS o submit USB. Non viene
aggiunto alcun comando o lifecycle sensor-reaching.

Il no-match è un risultato terminale normale: una sola callback e nessun
retry. Il client `fprintd-verify` restituisce exit code `1` per no-match; il
launcher lo richiede assieme alla singola riga
`Verify result: verify-no-match (done)`.

## Sequenza futura e contabilità

Le phase sono fail-closed e la successiva parte solo dopo l'audit della
precedente:

1. **A:** stage temporaneo, start fprintd, enrollment indice destro (8
   contatti), verifica FP3, restart daemon, verify stesso indice destro e
   audit dei primi due epoch;
2. **B:** un solo verify con indice sinistro, no-match terminale e audit del
   terzo epoch;
3. **C:** delete del solo template D282, audit e rollback.

Il grant composto minimizza il rischio di ripetere gli otto contatti per un
errore host-side tardivo. Autorizza esattamente tre azioni biometriche: un
enrollment e due verify. Non autorizza retry. `fprintd-delete` esegue comunque
un `Claim/Release`: produce quindi un quarto open epoch esplicito, ma il
Goodix image device non espone `FP_DEVICE_FEATURE_STORAGE`; il sorgente esatto
fprintd elimina solo il file host, senza delete sensor-side, TLS o azione
biometrica. Il summary distingue `OPEN_EPOCH_COUNT=4` da
`CONSUMED_BIOMETRIC_ACTION_COUNT=3` e ricava tutti i contatori dai log
osservati.

`AUTHORIZED_BIOMETRIC_ACTION_MAX=3` descrive il limite del grant composto; non
è un contatore di esecuzione. `ACTION_ATTEMPT_COUNT`, gli epoch e tutti gli
altri contatori del risultato sono invece derivati esclusivamente dagli audit
autentici raccolti.

Qualunque errore in A o B termina subito in cleanup; non si ripete il touch e
non parte la phase successiva. `timeout --signal=INT --kill-after=20s` è solo
un limite host. Un timeout/cancel non autorizza retry.

## Staging e storage

La libreria di sistema non viene sostituita. Da uno snapshot Git del full SHA
si costruisce `libfprint-2.so.2.0.0`, si hashano libreria e dipendenze e si
verificano NEVRA, ABI, SONAME, assenza RPATH e simboli vietati. La futura run
crea una directory privata sotto `/run`, un drop-in runtime sotto
`/run/systemd/system`, e avvia `/usr/libexec/fprintd` con `LD_LIBRARY_PATH`
puntato alla candidate. `/proc/<pid>/maps` deve mostrare esattamente quella
libreria. Nessun `ldconfig` e nessun overwrite sotto `/usr/lib64`.

Prima dello staging, `d282_storage_inventory.py` inventaria read-only
`/var/lib/fprint`: esistenza, tipo, uid/gid, mode, dimensione, SHA-256 e label
SELinux. I dati restano nella directory privata dei risultati e non entrano
nell'export. Lo storage usato da fprintd è una directory D282 univoca sotto
`/var/lib/fprint`, passata come `STATE_DIRECTORY`; eventuali utenti/template
preesistenti restano fuori da quel root. Collisioni e symlink falliscono
chiusi.

Il grant viene prima validato senza mutarlo. Collisioni, stato iniziale del
servizio, libreria di sistema e relativo hash, precondizioni SELinux, snapshot
della unit e inventario storage devono passare mentre
`GRANT_CONSUMED=false`. Il trap è già attivo per snapshot e inventario. Solo
dopo questi gate viene preparato il namespace one-shot e il claim è acquisito
con `mkdir` atomica; da `GRANT_CONSUMED=true` il launcher entra subito nello
staging. Un rifiuto precedente stampa anche
`REAL_USB_ENUMERATION_ATTEMPTED=false` e `LIVE_EXECUTION_PERFORMED=false`.

Il trap di rollback è installato prima della prima mutazione di staging.
Rimuove soltanto runtime, drop-in e storage con nomi D282 risolti in anticipo,
ripristina lo stato active/inactive del servizio, confronta unit, libreria di
sistema e inventario preesistente. Un confronto fallito imposta
`ROLLBACK_COMPLETE=false`, stampa istruzioni di recovery e vieta altre action.
Il materiale FP3 autentico resta sotto `private/`; l'export copia soltanto
`operator.log` e `summary.env` verificandone l'identità byte per byte.

## Prerequisiti e comandi offline

- branch `development`, worktree live-critical pulito per la preparazione;
- Flatpak SDK `org.freedesktop.Sdk//25.08` già installato;
- RPM OpenCV 4.13 Fedora 44 già disponibili e verificabili con
  `operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256`;
- pacchetto esatto `fprintd-1.94.5-5.fc44.x86_64` per ABI/runtime.

Solo il preflight seguente è eseguibile nello stato corrente e deve essere
avviato come utente non privilegiato:

```bash
operator_kit/d282-01-fprintd-target/run-d282-01.sh \
  --offline-preflight /percorso/agli/opencv-rpms
```

Le modalità `--prepare-candidate`, `--run-authorized-live` e
`--export-results` documentano il percorso futuro ma non sono autorizzate ora.
Il kit non crea grant. Un eventuale grant esterno one-shot dovrà contenere
esattamente quattro righe (`D282_01_BASELINE_SHA`, `D282_01_OPERATION`,
`D282_01_GRANT_ID`, `D282_01_USER`), avere permessi privati ed essere legato
alla candidate hash-pinned. La directory di consumo rende impossibile il
riuso dello stesso ID.

## Stop condition

Fermarsi senza eseguire alcuna azione se baseline/origin, pacchetto, ABI,
manifest, unit, servizio, storage, SELinux, cardinalità target, mapping della
libreria o grant non coincidono. I rifiuti host-only precedenti al claim non
consumano il grant. Dopo il consumo, ogni failure provoca solo
cleanup/rollback con `RETRY_AUTHORIZED=false`: non creare un altro grant e non
ripetere la run. Non usare comandi USB improvvisati.
