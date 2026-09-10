<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/01 — fprintd target con staging reversibile

## Stato e scopo

La prima Human Gate D282/01 è chiusa come `FAIL_HOST_STAGING`: il grant è
consumato senza retry autorizzato, `fprintd` ha fallito con status 126 prima di
qualsiasi contatto o azione biometrica e il recovery manuale è stato attestato
completo. Questo kit correttivo è **solo candidato per review host-side**. Non
esistono baseline approvata, nuovo grant o autorizzazione live. Il preflight è
offline e non enumera USB; le modalità candidate/live non devono essere
avviate.

La futura run copre soltanto il vero `fprintd-1.94.5-5.fc44.x86_64` con il
driver Goodix `27c6:5125`: enrollment dell'indice destro, FP3 SIGFM nello
storage isolato, restart del daemon, verify dello stesso dito, un verify con
indice sinistro atteso no-match, delete e rollback. PAM, login e sudo come
fattore di autenticazione sono fuori scope.

```text
D282_01_ATTEMPT_01=FAIL_HOST_STAGING_CLOSED
D282_01_ATTEMPT_01_GRANT_CONSUMED=true
D282_01_ATTEMPT_01_RETRY_AUTHORIZED=false
D282_01_HUMAN_GATE_READINESS=NOT_READY
D282_01_EXIT_TRAP_SCOPE_CORRECTIVE=PASS
D282_01_SYSTEMD_SELINUX_STAGING_CORRECTIVE=IMPLEMENTED_PENDING_PRIVILEGED_HOST_TEST
FPRINTD_SYSTEMD_STAGING_START=NOT_RUN_REQUIRES_SEPARATE_PRIVILEGED_AUTHORIZATION
SELINUX_EXEC_DENIAL=NOT_PROVEN_CORRECTED
D282_01_TARGET_CARDINALITY_PRECONSUMPTION_GATE=PASS
D282_01_ENROLLMENT_IMPLICIT_RETRY_FENCE=PASS
EXTRA_ENROLLMENT_CONTACT_REQUESTED=false
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

Per enrollment la policy è ancora più stretta. Soltanto la sottoclasse USB
Goodix production abilita `enroll_processing_fail_closed`: dopo una
acquisizione sensor-side consumata, un fallimento di extraction o processing
del template termina l'action con errore device, senza `FP_DEVICE_RETRY`,
nuovo `AWAIT_FINGER_ON` o rearm. Gli altri image driver conservano la
semantica generica. Il launcher rifiuta inoltre qualunque apparente successo
se l'output di `fprintd-enroll` contiene un marker `enroll-retry-*`.

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
`/run/systemd/system`, e fa avviare direttamente a systemd
`/usr/libexec/fprintd` con il normale entrypoint SELinux `fprintd_exec_t`. Il
wrapper `/run/.../launch-fprintd` dell'attempt 01 è stato rimosso. Il drop-in
imposta `LD_LIBRARY_PATH`, `FP_DRIVERS_ALLOWLIST` e uno `StateDirectory`
isolato, ma mantiene `ExecStart=/usr/libexec/fprintd`. `/proc/<pid>/exe` deve
risolvere a quel path e `/proc/<pid>/maps` deve mostrare esattamente la
candidate. Nessun `ldconfig` e nessun overwrite sotto `/usr/lib64`.

Prima dello staging, `d282_storage_inventory.py` inventaria read-only
`/var/lib/fprint`: esistenza, tipo, uid/gid, mode, dimensione, SHA-256 e label
SELinux. I dati restano nella directory privata dei risultati e non entrano
nell'export. Lo storage usato da fprintd è una directory D282 univoca sotto
`/var/lib/fprint`, passata come `STATE_DIRECTORY`; eventuali utenti/template
preesistenti restano fuori da quel root. Collisioni e symlink falliscono
chiusi.

Il grant viene prima validato senza mutarlo. Collisioni, stato iniziale del
servizio, libreria di sistema e relativo hash, precondizioni SELinux, snapshot
della unit, inventario storage e cardinalità passiva esatta di un solo
`27c6:5125` letta da `/sys/bus/usb/devices` devono passare mentre
`GRANT_CONSUMED=false`. Il trap è già attivo per snapshot e inventario. Solo
dopo questi gate viene preparato il namespace one-shot e il claim è acquisito
con `mkdir` atomica; da `GRANT_CONSUMED=true` il launcher entra subito nello
staging. Dopo lo start del daemon la stessa cardinalità viene verificata di
nuovo come fence anti-TOCTOU. Un rifiuto precedente al consumo stampa anche il
conteggio autentico `TARGET_PRECONSUMPTION_MATCH_COUNT` e
`REAL_USB_ENUMERATION_ATTEMPTED=false` e `LIVE_EXECUTION_PERFORMED=false`.

Il trap di rollback è installato prima della prima mutazione di staging.
`cleanup_live()` è top-level e usa solo stato globale `live_*`, che resta
valido anche quando `run_authorized_live()` termina per `set -e`; non dipende
più da variabili `local` fuori scope. Rimuove soltanto runtime, drop-in e
storage con nomi D282 risolti in anticipo,
ripristina lo stato active/inactive del servizio, confronta unit, libreria di
sistema e inventario preesistente. Un confronto fallito imposta
`ROLLBACK_COMPLETE=false`, stampa istruzioni di recovery e vieta altre action.
L'FP3 autentico esiste soltanto nello storage D282 isolato durante le phase A
e B. Viene eliminato dalla phase C o dal rollback e non viene copiato in
`private/`; l'export contiene soltanto `operator.log` e `summary.env`,
verificati byte per byte, quindi `TEMPLATE_INCLUDED_IN_EXPORT=false`.

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

Il preflight include un vero sottoprocesso Bash per il trap e una verifica di
sintassi del drop-in con `systemd-analyze`; non avvia il servizio. La prova del
vero start di sistema con SELinux Enforcing richiede una futura autorizzazione
privilegiata separata e deve avvenire senza rendere raggiungibile il Goodix.
Fino ad allora `D282_01_HUMAN_GATE_READINESS=NOT_READY`.

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
