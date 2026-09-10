<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/01 — fprintd target con staging reversibile

## Stato e scopo

L'attempt 03 D282/01 sulla baseline
`42903b70c89b2399bef35f4a4c7eb8c9dc5d04e5` ha completato l'enrollment
fprintd/SIGFM dell'indice destro (otto stage) e ha ottenuto `verify-match`
dello stesso indice dopo restart del daemon. La run si è fermata prima della
Phase B per un assert host-side stale: il launcher pretendeva sempre
`release_tail=1 single_terminal=1`, mentre il percorso `VerifyStop`/`Release`
del client fprintd ha prodotto la coppia coerente `0/0`, con prima immagine
acquisita, zero re-arm/retry e backend drenato/context chiuso. Cleanup, servizio,
staging, libreria di sistema e storage preesistente risultano ripristinati.

Il correttivo offline mantiene il profilo direct-enroll e sostituisce quel
grep rigido con un validatore tipizzato. Per VERIFY sono accettate soltanto le
coppie coerenti `release_tail/single_terminal` `0/0` oppure `1/1`; restano
obbligatori prima immagine singola, zero re-arm/retry/reopen/reset/clear-halt,
zero famiglie persistenti note, outstanding zero, backend drenato e context
chiuso. Driver, protocollo, fence per open epoch e numero di contatti non
cambiano.

La futura run copre soltanto il vero `fprintd-1.94.5-5.fc44.x86_64` con il
driver Goodix `27c6:5125`: enrollment dell'indice destro, FP3 SIGFM nello
storage isolato, restart del daemon, verify dello stesso dito, un verify con
indice sinistro atteso no-match, delete e rollback. PAM, login e sudo come
fattore di autenticazione sono fuori scope.

```text
D282_01_ATTEMPT_01=FAIL_HOST_STAGING_CLOSED
D282_01_ATTEMPT_01_GRANT_CONSUMED=true
D282_01_ATTEMPT_01_RETRY_AUTHORIZED=false
D282_01_BIOMETRIC_HUMAN_GATE_READINESS=HUMAN_REQUIRED_THEN_DIRECT_OPERATOR_RUN
D282_01_EXIT_TRAP_SCOPE_CORRECTIVE=PASS
D282_01_SYSTEMD_SELINUX_STAGING_CORRECTIVE=VERIFIED_PRIVILEGED_HOST
D282_01_SELINUX_WRAPPER_FAILURE=RESOLVED
FPRINTD_SYSTEMD_STAGING_START=VERIFIED_PRIVILEGED_HOST
SELINUX_EXEC_DENIAL=false
D282_01_PRIVILEGED_STAGING_PROBE=ACCEPTED_CLOSED
D282_01_PRIVILEGED_STAGING_PROBE_RESULT=PASS
D282_01_PRIVILEGED_STAGING_PROBE_EXECUTED=true
D282_01_PRIVILEGED_STAGING_PROBE_WAS_AUTHORIZED=true
D282_01_PRIVILEGED_STAGING_PROBE_CURRENTLY_AUTHORIZED=false
D282_01_PRIVILEGED_STAGING_PROBE_GRANT_CONSUMED=true
D282_01_PRIVILEGED_STAGING_PROBE_RETRY_AUTHORIZED=false
D282_01_PRIVILEGED_STAGING_PROBE_SERVICE_STATE_CORRECTIVE=PASS
D282_01_ATTEMPT_02=FAIL_FPRINTD_IDENTIFY_TO_ENROLL_SAME_EPOCH_FENCE
D282_01_ATTEMPT_02_BASELINE_SHA=cc2452e52809d2adeccce83a9fe493a241770832
D282_01_ATTEMPT_02_GRANT_CONSUMED=true
D282_01_ATTEMPT_02_RETRY_AUTHORIZED=false
D282_01_ATTEMPT_02_FIRST_CONTACT_ACTION=IDENTIFY
D282_01_ATTEMPT_02_ACTUAL_ENROLL_SENSOR_ACQUISITION_COUNT=0
D282_01_ATTEMPT_02_SECOND_SENSOR_REACHING_ACTION_COUNT=0
D282_01_ATTEMPT_03=FAIL_POST_PHASE_A_STALE_VERIFY_AUDIT_ASSERT
D282_01_ATTEMPT_03_BASELINE_SHA=42903b70c89b2399bef35f4a4c7eb8c9dc5d04e5
D282_01_ATTEMPT_03_ENROLLMENT_CLIENT_RESULT=COMPLETED_OPERATOR_CONTEXT_ATTESTED
D282_01_ATTEMPT_03_SAME_FINGER_VERIFY_CLIENT_RESULT=MATCH_OPERATOR_CONTEXT_ATTESTED
D282_01_ATTEMPT_03_VERIFY_RELEASE_TAIL=0
D282_01_ATTEMPT_03_VERIFY_SINGLE_TERMINAL=0
D282_01_ATTEMPT_03_PHASE_B_STARTED=false
D282_01_ATTEMPT_03_DIFFERENT_FINGER_SENSOR_ACQUISITION_COUNT=0
D282_01_VERIFY_AUDIT_COHERENT_CLOSE_PAIR=ZERO_ZERO_OR_ONE_ONE
D282_01_DIRECT_ENROLL_PROFILE=PASS_OFFLINE_NORMAL_AND_ASAN_UBSAN
D282_01_IDENTIFY_FEATURE_ADVERTISED=false
D282_01_VERIFY_FEATURE_ADVERTISED=true
MANUAL_PRESTOP_REQUIRED=false
PROBE_INITIAL_ACTIVE_ACCEPTED=true
PROBE_INITIAL_INACTIVE_ACCEPTED=true
ACTIVE_SUCCESS_FINAL_ACTIVE=PASS
ACTIVE_FAILURE_FINAL_ACTIVE=PASS
INACTIVE_SUCCESS_FINAL_INACTIVE=PASS
INACTIVE_FAILURE_FINAL_INACTIVE=PASS
D282_01_TARGET_CARDINALITY_PRECONSUMPTION_GATE=PASS
D282_01_ENROLLMENT_IMPLICIT_RETRY_FENCE=PASS
EXTRA_ENROLLMENT_CONTACT_REQUESTED=false
CURRENT_PRIVILEGED_INSTALL_AUTHORIZED=false
USER_APPROVED_BASELINE_REQUIRED=false
GRANT_REQUIRED=false
AUTHORIZATION_CREDENTIAL_REQUIRED=false
AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
LIVE_EXECUTION_PERFORMED=false
REAL_USB_ENUMERATION_ATTEMPTED=false
REAL_SENSOR_ACCESSED=false
DIFFERENT_FINGER_NO_MATCH=UNPROVEN_LIVE
SECOND_SENSOR_REACHING_ACTION_COUNT=0
```

## Perché VERIFY e politica anti-retry

Nel flusso enrollment, diversamente da `fprintd-verify`, il sorgente esatto
fprintd chiama prima `fp_device_identify()` se il device pubblicizza IDENTIFY.
Il callback no-match emette `enroll-stage-passed` e chiama poi
`fp_device_enroll()` senza chiudere il device. Questo comportamento ha causato
l'attempt 02: il primo contatto era IDENTIFY e il successivo ENROLL è stato la
seconda action dello stesso open epoch. Il profilo build-only
`GOODIX_D282_DIRECT_ENROLL_PROFILE` rimuove esclusivamente il feature bit
IDENTIFY dalla candidate del kit e conserva VERIFY; non cambia protocollo,
limiti di contatto o fence production.

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

Il launcher impone tecnicamente esattamente tre azioni biometriche: un
enrollment e due verify, senza loop o retry automatici/impliciti.
`fprintd-delete` esegue comunque
un `Claim/Release`: produce quindi un quarto open epoch esplicito, ma il
Goodix image device non espone `FP_DEVICE_FEATURE_STORAGE`; il sorgente esatto
fprintd elimina solo il file host, senza delete sensor-side, TLS o azione
biometrica. Il summary distingue `OPEN_EPOCH_COUNT=4` da
`CONSUMED_BIOMETRIC_ACTION_COUNT=3` e ricava tutti i contatori dai log
osservati.

`BIOMETRIC_ACTION_MAX=3` descrive il limite tecnico dell'invocazione; non è un
contatore di esecuzione. `ACTION_ATTEMPT_COUNT`, gli epoch e tutti gli
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

Collisioni, stato iniziale del servizio, libreria di sistema e relativo hash,
precondizioni SELinux, snapshot della unit, inventario storage e cardinalità
passiva esatta di un solo `27c6:5125` letta da `/sys/bus/usb/devices` devono
passare prima dello staging. Il trap è già attivo per snapshot e inventario.
Dopo lo start del daemon la stessa cardinalità viene verificata di nuovo come
fence anti-TOCTOU. Un rifiuto precedente allo staging stampa il conteggio
autentico `TARGET_PRECONSUMPTION_MATCH_COUNT`,
`REAL_USB_ENUMERATION_ATTEMPTED=false` e
`LIVE_EXECUTION_PERFORMED=false`. Nessun file/token/grant o approvazione dello
SHA partecipa alla safety; lo SHA è registrato soltanto come provenance.

Il trap di rollback è installato prima della prima mutazione di staging.
`cleanup_live()` è top-level e usa solo stato globale `live_*`, che resta
valido anche quando il percorso live termina per `set -e`; non dipende
più da variabili `local` fuori scope. Rimuove soltanto runtime, drop-in e
storage con nomi D282 risolti in anticipo,
ripristina lo stato active/inactive del servizio, confronta unit, libreria di
sistema e inventario preesistente. Un confronto fallito imposta
`ROLLBACK_COMPLETE=false`, stampa istruzioni di recovery e vieta altre action.
L'FP3 autentico esiste soltanto nello storage D282 isolato durante le phase A
e B. Viene eliminato dalla phase C o dal rollback e non viene copiato in
`private/`; l'export contiene soltanto `operator.log` e `summary.env`,
verificati byte per byte, quindi `TEMPLATE_INCLUDED_IN_EXPORT=false`.

## Probe privilegiato systemd/SELinux storico, separato dalla live

La modalità storica è `--run-authorized-staging-probe` e accettava
esclusivamente un grant one-shot con operation:

```text
D282_01_PRIVILEGED_SYSTEMD_SELINUX_STAGING_PROBE
```

La preparazione usa `--prepare-staging-probe-candidate <full-SHA>` e produce
una candidate distinta, hash-pinned e ABI-compatible con il vero
`/usr/libexec/fprintd`. La run storica del probe è chiusa: candidate e grant
consumati non autorizzano alcuna ripetizione né la live biometrica.

Il probe riusa il meccanismo production-shaped che interessa il blocker:
vero systemd, `ExecStart=/usr/libexec/fprintd`, drop-in sotto
`/run/systemd/system`, `LD_LIBRARY_PATH` verso il runtime candidato,
`StateDirectory` isolato sotto `/var/lib/fprint`, label SELinux e lo stesso
`cleanup_live()` top-level. Richiede SELinux `Enforcing`, accetta e registra
prima del consumo lo stato servizio `active` oppure `inactive`, verifica
`ExecMainStatus=0`, `/proc/<pid>/exe`, l'unico path
libfprint mappato in `/proc/<pid>/maps`, le variabili effettive in
`/proc/<pid>/environ`, hash della libreria di sistema, inventario storage e
rollback completo.

Il Goodix reale non è raggiungibile dal percorso del probe per difesa in
profondità:

- la libfprint probe è costruita con il solo driver `virtual_image`;
- l'overlay D281 elimina a compile time creazione ed enumerazione del
  `GUsbContext`, e l'artefatto è riauditato prima del consumo del grant;
- il binario candidato non contiene il driver Goodix né simboli Goodix/TLS;
- `FP_VIRTUAL_IMAGE` viene esplicitamente rimosso, quindi non esiste neppure
  un endpoint virtuale su cui eseguire un'azione;
- il servizio ha `PrivateDevices=yes`, `DevicePolicy=closed` e nessun
  `DeviceAllow`; dopo lo start il probe richiede zero fd `/dev/bus/usb`;
- il probe non chiama client enroll/verify/identify/delete, PAM, PSK o TLS.

Ne consegue il contratto invariabile del probe:

```text
REAL_USB_ENUMERATION_ATTEMPTED=false
REAL_SENSOR_ACCESSED=false
BIOMETRIC_ACTION_COUNT=0
FINGER_CONTACT_COUNT=0
LIVE_EXECUTION_PERFORMED=false
```

La run storica conservava un grant a quattro righe; `D282_01_USER`
lega l'identità dell'operatore ma non viene passato ad alcuna azione
biometrica. Operation e grant ID del probe erano distinti da quelli della live
storica. Tutti i gate fallibili
(baseline/manifest/artefatti, audit USB/Goodix, ABI, grant, collisioni,
stato servizio `active|inactive`, libreria/hash, SELinux Enforcing, result
sink, snapshot unit e inventario storage) precedono il claim atomico. Dopo il
consumo ogni failure attraversa il rollback e resta `RETRY_AUTHORIZED=false`.

Non è richiesto alcun pre-stop manuale. Se lo stato iniziale è `active`, solo
dopo il consumo il launcher ferma internamente fprintd, ricarica systemd e
avvia l'istanza staged; se è `inactive`, salta il primo stop e avvia
direttamente l'istanza staged dopo il daemon-reload. Il cleanup ferma sempre
l'istanza staged, rimuove drop-in/runtime/storage, ricarica systemd e riavvia
il daemon normale soltanto nel caso iniziale `active`. Infine rilegge lo stato
reale e richiede uguaglianza esatta con quello iniziale. Il summary contiene
`SERVICE_INITIAL_STATE`, `SERVICE_FINAL_STATE` e
`SERVICE_STATE_RESTORED`; una divergenza rende `ROLLBACK_COMPLETE=false` e
`RECOVERY_REQUIRED=true`.

La run privilegiata reale ha verificato con SELinux Enforcing start
systemd, `ExecMainStatus=0`, exe e mapping libfprint esatti, storage isolato,
zero fd USB, zero Goodix/sensore/biometria e rollback `active → active`.
System lib e storage preesistente sono invariati. Il successivo stato
`inactive/dead` è il normale auto-exit di fprintd inutilizzato, confermato dal
sorgente Fedora e dall'opzione `--no-timeout`; non invalida il rollback già
osservato. La directory padre vuota `/run/goodix-d282-01` è housekeeping non
bloccante.

## Prerequisiti e comando operativo corrente

- branch `development`, worktree live-critical pulito per la preparazione;
- Flatpak SDK `org.freedesktop.Sdk//25.08` già installato;
- RPM OpenCV 4.13 Fedora 44 già disponibili e verificabili con
  `operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256`;
- pacchetto esatto `fprintd-1.94.5-5.fc44.x86_64` per ABI/runtime.

Il preflight seguente resta eseguibile come utente non privilegiato e non
raggiunge USB:

```bash
operator_kit/d282-01-fprintd-target/run-d282-01.sh \
  --offline-preflight /percorso/agli/opencv-rpms
```

Il preflight include un vero sottoprocesso Bash per il trap, costruisce e
audita realmente anche la candidate virtual-only e verifica la sintassi di
entrambi i profili drop-in con `systemd-analyze`; non avvia il servizio. La
prova privilegiata del vero start è già chiusa separatamente e non deve essere
ripetuta.

La normale run factory-preserving è direttamente eseguibile dall'operatore,
senza preparare candidate, grant, authorization file o approvare manualmente
uno SHA:

```bash
operator_kit/d282-01-fprintd-target/run-d282-01.sh \
  --operator-run /tmp/goodix-opencv-4.13-rpms
```

Il comando va avviato come utente normale. Costruisce la candidate dal `HEAD`
pulito e allineato a `origin/development`, mostra il budget fisico, chiede di
digitare `ESEGUI`, invoca visibilmente `sudo` solo per staging/live/rollback e
infine esporta automaticamente `operator.log` e `summary.env` in una directory
`/tmp/goodix-d282-01-export.*` posseduta dall'operatore. Lo SHA e il manifest
restano dati di provenance/integrità. Le modalità low-level e probe
sono interne o storiche e non sono il percorso operativo corrente.

## Stop condition

Fermarsi senza eseguire alcuna azione se baseline/origin, pacchetto, ABI,
manifest, unit, servizio, storage, SELinux, cardinalità target o mapping della
libreria non coincidono. Dopo l'inizio dello staging, ogni failure provoca
solo cleanup/rollback; non esiste alcun retry automatico o implicito. Se la
run fallisce, non ripeterla: conservare ed allegare l'export prodotto. Non
usare comandi USB improvvisati.
