# Goodix 27c6:5125 — manuale tecnico

## Stato del progetto

Il progetto studia il sensore Goodix USB `27c6:5125` del Huawei MateBook D15 /
BohrD-WDH9D con un vincolo assoluto: preservare firmware, identità,
configurazione factory, stato persistente/secure e compatibilità con Windows.

Il branch Git operativo canonico per il loop autonomo è `development`. `main`
e `bakcup_pre_agentic_mode` sono read-only per l'agente; i riferimenti storici
a esecuzioni e baseline avvenute su altri branch restano invariati.

```text
GIT_CANONICAL_BRANCH=development
MAIN_BRANCH_POLICY=READ_ONLY
BACKUP_BRANCH_POLICY=READ_ONLY
```

### Stato corrente D279/10 — enrollment OEM completo target-local osservato

**Integrazione offline del 4 settembre 2026.** Su autorizzazione esplicita
dell'Utente, D279/07 fissa `/var/lib/goodix-5125-poc` come directory production
dei cinque input privati: conserva `target-material-manifest.json`,
`transport-material.bin` e `target-config-90.bin`, aggiunge `gfusb.dll` e
`fdt-cache.bin`, richiede directory `root:root 0700` e file `root:root 0600`.
L'API espone questi path senza discovery/I/O; il loader verifica directory
comune, parent diretto e stabilità pre/post. I reader ora controllano anche il
GID root, correggendo il precedente contratto incompleto UID+mode.

L'identità runtime è stata verificata per quanto consentito sul Fedora 44
reale: `fprintd-1.94.5-5.fc44.x86_64` non imposta `User=`, `Group=` o
`DynamicUser=`, quindi gira come root. `ProtectSystem=strict` rende il layout
read-only ma visibile: il DAC `0700/0600` è compatibile con la lettura root.
La policy SELinux installata concede a `fprintd_t` la lettura di
`fprintd_var_lib_t`, non un allow file equivalente per il tipo generico
`var_lib_t` quando SELinux è attivo.

Il primo probe manuale autorizzato si è fermato fail-closed su
`FILE_ASSENTE_O_NON_REGOLARE_gfusb.dll`, senza leggere contenuti, avviare
fprintd o accedere a USB. È evidenza attesa di layout non provisionato, non di
incompatibilità runtime. Il sequencing originale era però subottimale: fermava
la scansione al primo assente e non emetteva l'esito ambiente già calcolato.

Il corrective D279/07 separa ora environment-only, provisioning e probe full
post-provision. La review esterna aveva inoltre rilevato una reale asimmetria:
il provisioning `95c5346` applicava sempre i tool SELinux anche con Disabled.
Ora Disabled salta integralmente `semanage`, `restorecon`, `matchpathcon`,
`chcon`, mapping e verifica label; Enforcing/Permissive conserva i mapping
`fprintd_var_lib_t` limitati ai sei path. Il test a sentinella dimostra che
nessun mutator SELinux viene chiamato nel ramo Disabled.

Il controllo autonomo non privilegiato aveva prodotto
`REAL_TARGET_ENVIRONMENT=PASS` con SELinux allora osservato `Disabled`, senza
accedere al layout. Successivamente l'Utente ha eseguito manualmente il
provisioning e il probe full autorizzati. Entrambe le run hanno rilevato lo
stato reale corrente `Enforcing`: il provisioning ha quindi applicato e
verificato il percorso `fprintd_var_lib_t`, preservato i primi tre input e
installato `gfusb.dll` e `fdt-cache.bin`; il probe ha confermato policy di
lettura, label, identità root, sandbox e metadata `0700/0600`.

Il risultato conclusivo è `REAL_TARGET_COMPATIBILITY=PASS` e chiude il gate
D279/07 per il layout production. Le operazioni protette sono state compiute
solo dall'operatore nell'ambito dell'autorizzazione dichiarata; l'AI non ha
usato sudo né letto gli input. fprintd non è stato avviato e USB/live non sono
stati toccati. D279/08 ha assunto il successivo boundary offline.

D279/08 ha ora completato quel collegamento offline. Nel lifecycle standard
libfprint 1.94.100 il core apre necessariamente `GUsbDevice` prima della vfunc;
il driver carica quindi immediatamente l'owner dai cinque path D279/07 e solo
dopo reclama l'interfaccia 0. Nessun submit avviene durante open. Owner, secure
view, FDT12 e audit appartengono allo stesso `GoodixDeviceContext`; close e
ogni failure tentano il release del claim una sola volta, poi cancellano le
view e liberano l'owner anche se libgusb segnala errore. Due open consecutivi
sullo stesso oggetto creano due epoch distinte.

Le prove D279/08 erano soltanto sintetiche: 21/21 test normali e sanitizer,
9/9 regressione material owner e build/registry Fedora 44 `PASS`, senza input
production o USB reale.

D279/09 ha ora sostituito l'arm host-only della sottoclasse USB con la catena
production `pre-session RX sync quiet → GoodixSecureSession → TLS retained →
GoodixPostTlsLifecycle`. Il primo protocol OUT è irraggiungibile prima del
quiet boundary; failure/cancellation completano il corretto punto libfprint e
avvelenano l'epoch. Dopo la costruzione dei consumer, la glue cancella secure
descriptor e FDT12 borrowed mentre mantiene il solo owner fino a close.

Questo collegamento è volutamente bounded: capture/identify sono cablati
offline, ma l'enrollment viene rifiutato con `NOT_SUPPORTED` prima della
generation e con zero submit. Fedora 44 richiede per default cinque stage in
una sola activation, mentre quel lifecycle locale termina al secondo B0. La
successiva evidenza D279/10 attempt 02 ha superato questo limite storico e
misurato 21 stage OEM primari; il sender Linux resta però ancora bounded al
secondo B0. La suite è ora 25/25 normale e sanitizer, con regressione D278
24/24 normale/sanitizer e
build Fedora 44 e builder adapter D278/13 unapproved host-only `PASS`. I due
builder D278 interessati sono stati corretti per linkare le dipendenze runtime
introdotte da D279/08; non è cambiato il protocollo né è stata abilitata una
baseline live.
D279/09 non autorizza installazione, fprintd o live.

D279/10 è stato ripianificato offline senza estendere il sender Linux. Il Kit
Windows/OEM passivo ora cattura dall'avvio del wizard alla conferma reale della
prima impronta registrata, poi conserva cinque secondi di tail terminale. Il
numero di contatti non è assunto: l'operatore risponde soltanto tramite menu
numerici e il parser conta tutti i lifecycle esatti osservati. Il terzo B0 è
una milestone metadata-only e non è più uno stop condition. Il default
libfprint di cinque stage non entra nel criterio di closure.

Il marker globale è stato rimosso. Ogni invocazione live futura usa un
`authorized_attempt_id` distinto e crea directory/lock con protezione
anti-riuso per-attempt; un failure non rende inutilizzabile il Kit e non genera
retry automatici. Lo stato finale classifica se una nuova run pre-attach è
ragionevole senza restore oppure se, dopo attach/wizard, lo snapshot VM deve
essere ripristinato. La procedura preferita fotografa VM, repository e Kit già
qualificato; prima del restore vanno esportate fuori dalla VM sia `raw/` sia
`sanitized/` dell'attempt.

La review sensor-side impedisce un claim di assenza certa di persistenza per
il completamento OEM. Le famiglie persistenti note sono
`0xE0/0xA4/0xF0/0xF4`; la superficie statica `gfusb.dll` espone inoltre API e
messaggi PBA di add/update/delete template e scrittura su flash. Non è provato
che il normale percorso Windows Hello/WBDI non raggiunga capacità equivalenti,
e il traffico cifrato rende insufficiente l'assenza delle famiglie visibili.
Lo snapshot copre solo la mutazione host-side, non il sensore.

L'Utente ha ora autorizzato il normale workflow OEM Windows Hello anche se
comportasse persistenza template sensor-side, precisando che il sensore era già
stato usato per anni con impronte Windows e non è factory-virgin. L'authority
V2 registra quindi `possible_sensor_side_template_persistence_accepted=true`.
La deroga è limitata al workflow OEM: restano vietati flash/IAP, ClearApp, PSK
provisioning/substitution, OTP/factory writes, modifiche persistenti
VID:PID/mode e comandi Goodix manuali/manutentivi. Non è autorizzata una nuova
run live.

La prima qualificazione Windows della versione full-enrollment, eseguita
dall'Utente su clone fresco `cc8754e`, ha confermato precondizioni e self-test
ma ha trovato un failure host-side reale: PowerShell Desktop 5.1 promuoveva lo
stderr ordinario di `unittest -q` a `NativeCommandError` sotto
`$ErrorActionPreference=Stop`, prima della lettura di `$LASTEXITCODE`.

Il corrective usa ora un wrapper circoscritto: solo durante l'invocazione
nativa applica `Continue`, cattura stdout/stderr, salva l'exit code e ripristina
sempre la policy globale in `finally`. La qualifica V3 prova esplicitamente
`stderr + exit 0` e un exit nonzero intenzionale `7`, quindi non indebolisce il
controllo del risultato della suite. Sedici fixture sintetiche passano su Linux
senza leggere capture autentiche. Il relativo corrective è poi entrato nella
baseline `7d0c9bd3c638a1ab5d180b03eb969bd1dd840813` usata dall'attempt 02;
l'output separato della ripetizione `NativeQualificationOnly` non è parte
dell'evidence commit, ma non è più il boundary tecnico corrente.

Il primo live attempt full-enrollment è stato poi eseguito dall'Utente e
preservato integralmente nel commit `98ec62b`, attempt
`D27910_20260905_ATTEMPT01`. È terminato fail-closed dopo attach ma prima del
wizard e dei contatti: observer `MALFORMED_A0`, capture arrestata, zero retry e
restore richiesto per stato prudenzialmente incerto.

L'analisi diretta autorizzata del raw finalizzato, hash
`557ff136e5a1d383f7413ca24d731eeae32d2b377e61003846b034ecda991743`,
identifica quattro occorrenze agli indici pacchetto `25/29/37/45` del frame
byte-identico `a0 08 00 a8 01 05 00 00 00 00 00 88`: A0 OUT completo,
outer 12 byte, inner 5, non troncato. Il trailer `0x88` non soddisfa il checksum
generico (`0x8d`, non `0xaa`); il census sanitizzato D230 conserva lo stesso
payload corto `0000000088` nella reference OEM positiva, mentre D273 conferma
la forma metadata 10 volte nella reference positiva e 8 nella zero-finger. Il
driver prosegue normalmente. È quindi una forma OEM control-specific valida mancante
dal parser D274, non un frame realmente malformato né un artefatto del pcap in
scrittura. Il trigger effettivo dell'observer è il primo, packet `25`; le altre
tre occorrenze erano latenti dietro il fail immediato.

Il corrective allowlista esclusivamente quel frame completo, direction OUT e
byte-esatto prima del checksum generico. Una variante `...89` resta
`MALFORMED_A0`; nessun failure generico è degradato a `PENDING`. Sul raw
autentico il parser corretto produce 75 eventi, quattro
`OEM_FIXED_CONTROL_01`, zero errori e observer `OBSERVING`, coerente con lo
stop pre-wizard. Ora passano 18 fixture D279 e 79 test D274+D279 complessivi.

Il secondo live attempt è stato quindi eseguito dall'Utente sulla baseline
`7d0c9bd3c638a1ab5d180b03eb969bd1dd840813` e preservato nel commit
`6c1564b6e7f58a5694113ffcb2e35f9ea0847c7e`, attempt
`D27910_20260905_ATTEMPT02`. Il finalizer ha chiuso `PASS` la prima
registrazione OEM: 22 contatti dichiarati dall'operatore, 21 lifecycle wire
primari completi, milestone terzo B0 osservata, zero contraddizioni finali,
zero retry e zero sender Goodix del Kit.

L'audit diretto dell'intero pcapng hash-gated
`3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab`
ricostruisce 924 pacchetti, 912 pacchetti target e 442 frame target. Tutti i 21
IRQ2, i 21 `0x22 [01 00]` e i 21 ACK `0x22/01` appartengono a lifecycle
completi: non esiste un 22º prefisso parziale. Poiché `operator_events.json`
conserva solo il totale e non i timestamp per contatto, il delta è classificato
semplicemente `1 operator contact without complete wire acquisition lifecycle`;
il contatto specifico non è localizzabile. Il gap più lungo, dopo il ciclo 9,
è solo un candidato non probante.

Il primo ciclo usa una transizione distinta con NAV; i cicli 2–20 ripetono
`primary B0 → 0x34 → 0x36/IRQ0100 → 0x20/auxiliary B0 → 0x34/IRQ0200 → 0x32`;
il ciclo 21 omette il re-arm terminale. Si osservano quindi 21 stage primari,
20 re-arm inter-ciclo, 21 finger-up IRQ0200 e 43 B0 fingerprint-shape totali:
uno nel bootstrap, 21 primari e 21 ausiliari. La forma cifrata non permette di
promuovere i B0 ausiliari a score di qualità, template o stage operatore.

La finalizzazione target-visibile termina a packet 921 con l'ultimo IRQ0200.
Un bulk-IN pendente completa a zero byte al packet 923; la conferma UI arriva
2,372 s dopo e 11,370 s dopo l'ultimo frame. Non esistono frame né pacchetti
target post-UI nei successivi 5,167 s. Non compare un distinto comando A0 di
commit: non è possibile distinguere commit cifrato, implicito sensor-side e
persistenza host-side.

Nessuna famiglia nota `0xE0/0xA4/0xF0/0xF4` è visibile, ma ciò non esclude
persistenza template sensor-side. La nuova evidenza non autorizza ulteriori
live. Il boundary corrente torna offline: estendere il lifecycle Linux e il
contratto libfprint/NBIS a 21 stage primari, mantenendo `0x20` come transizione
interna e modellando la chiusura senza re-arm. L'audit metadata-only dedicato
passa 3/3 e la regressione combinata D274+D279 passa 112/112; `captures/` resta
byte-identico all'evidence commit.

D279/06 aveva immediatamente prima composto i cinque input espliciti in un
solo `GoodixRuntimeMaterial`: valida prima PE/cache, crea un solo
`GoodixTargetMaterial`, lega i seed, conserva soltanto una view secure
non-owning e FDT12, poi cancella tutti gli intermedi. Al free cancella
descriptor/FDT e delega al singolo owner esistente il cleanse di PSK,
validator e CONFIG90. D279/06 non selezionava ancora path production; quella
limitazione storica è superata dalla sola selezione offline D279/07. Il modulo
non ha USB o protocollo.

La prova completa usa cinque file sintetici 0600; al milestone D279/06
verificava composizione e teardown in otto test normali e ASan/UBSan, ora nove
con il layout production D279/07. La source map Fedora 44 compila il nuovo
owner. Il limite storico su `img_open` e claim è superato da D279/08; i test
AI non leggono input autentici.

D279/05 aveva immediatamente prima esteso i provider con
un reader read-only di due soli path espliciti. Richiede regular file con uid,
mode `0600` e size esatti, usa `O_NOFOLLOW|O_CLOEXEC`, confronta identità,
size, mtime nanosecond e metadata via `fstat` pre/post, cancella ogni buffer e
pubblica seed A/B e FDT12 soltanto dopo la validazione di entrambi gli input.
La policy D279/05 richiedeva uid 0; D279/07 ha aggiunto anche il GID 0. I test
usano soltanto file sintetici temporanei con uid/gid correnti. D279/05 non
hard-codava o scopriva path production; D279/07 ha poi aggiunto esclusivamente
il layout autorizzato. Nessun input autentico è stato aperto.

D279/04 aveva immediatamente prima aggiunto al dominio
`libfprint-driver/` i provider inerti che mancavano al futuro lifecycle
production: estrazione bounded dei due seed D190 da byte PE hash-pinned e del
seed FDT12 da byte cache legati a hash, CRC-32/MPEG-2, OTP64 e layout esatto.
Ogni failure azzera gli output; i seed produttore hanno cleanse esplicito. Il
modulo non apre file, non scopre path, non carica/esegue il PE, non offre
subprocess o write e non contiene API USB.

La porzione PE è adattata direttamente dalla reference project-owned
BSD-2-Clause D190, non dal successivo port C GPL. La porzione FDT è nuova
espressione locale dei fatti neutrali D255/D261. La source map Fedora 44 ora
compila provider, binder e loader protetto nello stesso driver registrato.
Cinque test sintetici normali e ASan/UBSan passano; la build esatta
`libfprint-2.so.2.0.0` e registry continua a passare. I pin production sono
compilati, ma nessun PE/cache/secret autentico è stato letto.

D279/03 aveva immediatamente prima applicato la decisione
D279/02 sul target production Fedora 44 /
`libfprint-1.94.100-1.fc44.x86_64`: l'extractor dell'image path Goodix
`27c6:5125` / `GF_ST411SEC_APP_12509` è **NBIS**, non SIGFM.

Il path 1.94.100 è NBIS-only (`fp_image_detect_minutiae`, `FPI_PRINT_NBIS`,
`fpi_print_bz3_match`). `FpImage::ppmm` è consumato solo da
`combined_minutia_quality()` per il raggio del vicinato di reliability; le
minutiae e Bozorth3 usano coordinate pixel. La reliability calcolata viene
scartata in `minutiae_to_xyt()` prima del matcher. Non esiste default/fallback
codice di `ppmm`: resta `0.0` per zero-init, come nella quasi totalità dei
driver upstream. Quindi `TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN` **non** rende
NBIS ineseguibile e **non** autorizza a inventare un DPI. Il raster live-proven
`80x64` supera il blocksize minimo 8; la sufficienza biometrica (≥10 minutiae,
soglia Bozorth) resta non provata.

SIGFM resta la selezione storica della build host-only basata sul fork
Rockytkg. La build target 1.94.100 omette soltanto quel selettore tramite una
define scoped al driver e usa NBIS nativo; non porta SIGFM, OpenCV o nuovi tipi
print.

Il registry Meson standard ora genera
`fpi_device_goodix_27c6_5125_get_type()`. La sottoclasse USB espone un solo
`FpIdEntry`, `27c6:5125`, riusa lo stesso `GoodixDeviceContext` D278 e compare
una sola volta nel tool `fprint-list-supported-devices`. La reference esatta
compila `libfprint-2.so.2.0.0` e il tool registry nel Freedesktop SDK 25.08
contro il runtime Fedora `libgusb.so.2`, senza enumerare o aprire USB.

Il gate locale D270/D271 è riallineato: NBIS non è più bloccato, ma lo stato
fisico resta `UNKNOWN` e `FpImage::ppmm` non viene assegnato. Questa closure non
prova enrollment, matching, fprintd, FAR/FRR o qualità biometrica e non rende
ancora operativo il lifecycle `img_open` production. D278/14 resta chiuso e
non è autorizzata alcuna nuova run live.

```text
D279_07_OUTCOME=PASS
D279_07_BASELINE=ba8750874df3f7c38d515be7d6b0412a5f0ab478
D279_07_CORRECTIVE_BASELINE=95c5346dcb2938bca0d1af364daef94948866bd2
D279_07_EXECUTABLE_CLOSURE=PASS_REAL_TARGET_LAYOUT_PROVISIONING_AND_METADATA_POLICY_PROBE
PRODUCTION_LAYOUT=/var/lib/goodix-5125-poc
PRODUCTION_LAYOUT_DIRECTORY=root:root_0700
PRODUCTION_LAYOUT_FILES=root:root_0600
PRODUCTION_LAYOUT_FILE_COUNT=5
FPRINTD_RUNTIME_IDENTITY=root:root
FPRINTD_PROTECT_SYSTEM_STRICT_READ_COMPATIBLE=true
SELINUX_REQUIRED_LAYOUT_TYPE_WHEN_ACTIVE=fprintd_var_lib_t
SELINUX_CURRENT_ENFORCEMENT=Enforcing
SELINUX_PROVISIONING=REQUIRED_FPRINTD_VAR_LIB_T_COMPLETED
REAL_TARGET_ENVIRONMENT=PASS
FIRST_HUMAN_PROBE_RESULT=EXPECTED_INCOMPLETE_LAYOUT_GFUSB_DLL_ABSENT
LAYOUT_PROVISIONING_STATE=COMPLETE_METADATA_ONLY
REAL_TARGET_COMPATIBILITY=PASS
PRODUCTION_LAYOUT_PROVISIONED=true
D279_08_OUTCOME=READY_OFFLINE
D279_08_BASELINE=9d601d2db2848b624c6345dd5b2ad545704d6bbd
D279_08_EXECUTABLE_CLOSURE=PASS_OFFLINE_SYNTHETIC_OPEN_CLOSE_AND_FEDORA44_BUILD
PRODUCTION_RUNTIME_MATERIAL_OWNED_PER_OPEN_EPOCH=true
PRODUCTION_USB_INTERFACE_0_CLAIMED_PER_OPEN_EPOCH=true
PRODUCTION_IMG_OPEN_USB_SUBMIT_COUNT=0
D279_08_PRODUCTION_ACTIVATION_SECURE_GRAPH_WIRED=false
D279_09_OUTCOME=READY_OFFLINE_BOUNDED_NON_ENROLL
D279_09_BASELINE=81b01731f37b23618413c31e1cde31aeeed1152d
D279_09_EXECUTABLE_CLOSURE=PASS_OFFLINE_SYNTHETIC_ACTIVATION_AND_FEDORA44_BUILD
PRODUCTION_CAPTURE_IDENTIFY_ACTIVATION_GRAPH_WIRED=true
PRODUCTION_PRE_SESSION_RX_SYNC_REQUIRED=true
PRODUCTION_RUNTIME_HANDOFF_VIEWS_CLEARED=true
PRODUCTION_ENROLLMENT_ENABLED=false
PRODUCTION_ENROLLMENT_REJECTION_SUBMIT_COUNT=0
D279_10_OUTCOME=ATTEMPT02_COMPLETE_OEM_ENROLLMENT_ANALYZED
D279_10_REPLAN_BASELINE=fc2172f9973ea5a13f067dc3abfd98881c274efa
D279_10_EXECUTABLE_CLOSURE=PASS_LINUX_SYNTHETIC_AND_REAL_EVIDENCE_AUDIT
D279_10_SYNTHETIC_TESTS=18/18_PASS
D279_10_WINDOWS_NATIVE_CC8754E=FAIL_NATIVE_COMMAND_ERROR_ON_UNITTEST_STDERR
D279_10_WINDOWS_NATIVE_STDERR_CORRECTIVE=APPLIED_AND_USED_BY_ATTEMPT02_BASELINE
D279_10_WINDOWS_NATIVE_QUALIFICATION_SCHEMA=V3
D279_10_ATTEMPT01_EVIDENCE_COMMIT=98ec62bea75d7764e44296a1d70da7a2f06609c5
D279_10_ATTEMPT01_RESULT=FAIL_CLOSED_PRE_WIZARD_ZERO_CONTACTS
D279_10_ATTEMPT01_FAILURE=MALFORMED_A0_FALSE_POSITIVE_ON_OEM_FIXED_CONTROL_01
D279_10_ATTEMPT01_FRAME_INDICES=25,29,37,45
D279_10_ATTEMPT01_FRAME_CLASS=VALID_OEM_CONTROL_SPECIFIC_A0
D279_10_ATTEMPT01_INCREMENTAL_PCAP_ARTIFACT=false
D279_10_OEM_FIXED_CONTROL_01_EXACT_ALLOWLIST=true
D279_10_OEM_FIXED_CONTROL_01_NEAR_MISS_FAIL_CLOSED=true
D279_10_ATTEMPT02_EVIDENCE_COMMIT=6c1564b6e7f58a5694113ffcb2e35f9ea0847c7e
D279_10_ATTEMPT02_RESULT=PASS_COMPLETE_UI_CONFIRMED
D279_10_ATTEMPT02_CAPTURE_SHA256=3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab
D279_10_ATTEMPT02_OPERATOR_CONTACT_COUNT=22
D279_10_ATTEMPT02_PRIMARY_ACQUISITION_STAGE_COUNT=21
D279_10_ATTEMPT02_UNMATCHED_CONTACT_COUNT=1
D279_10_ATTEMPT02_UNMATCHED_CONTACT_IDENTITY=UNKNOWN_NO_PER_CONTACT_TIMESTAMPS
D279_10_ATTEMPT02_INTER_CYCLE_REARM_COUNT=20
D279_10_ATTEMPT02_FINGER_UP_IRQ0200_COUNT=21
D279_10_ATTEMPT02_FINGERPRINT_SHAPE_B0_COUNT=43
D279_10_ATTEMPT02_TERMINAL_TARGET_FRAME=921_IRQ0200
D279_10_ATTEMPT02_POST_UI_TARGET_FRAME_COUNT=0
D279_10_ATTEMPT02_POST_UI_TARGET_PACKET_COUNT=0
D279_10_ATTEMPT02_KNOWN_PERSISTENT_FAMILY_COUNT=0
D279_10_PASSIVE_OEM_OBSERVER=true
D279_10_WORKFLOW=FULL_FIRST_OEM_ENROLLMENT_UI_CONFIRMED_PLUS_TERMINAL_TAIL
D279_10_CONTACT_COUNT_ASSUMED=false
D279_10_THIRD_B0_ROLE=MILESTONE_ONLY
D279_10_OPERATOR_INPUTS=NUMERIC_ONLY
D279_10_GLOBAL_MARKER=false
D279_10_ATTEMPT_SCOPED_ANTI_OVERWRITE=true
D279_10_AUTOMATIC_RETRY_COUNT=0
D279_10_SNAPSHOT_PRERUN_PREFERRED=true
D279_10_EXPORT_BEFORE_RESTORE=RAW_AND_SANITIZED_OUTSIDE_VM
D279_10_SENSOR_SIDE_TEMPLATE_PERSISTENCE=NOT_EXCLUDED_BUT_OEM_WORKFLOW_ACCEPTED_BY_USER
D279_10_LIVE_AUTHORITY_TEMPLATE_CLOSED=true
D279_10_LIVE_AUTHORIZED=false
D279_10_HOST_VM_ENROLLMENT_MUTATION=ACCEPTED_BY_USER_SNAPSHOT_MANAGED
D279_11_OUTCOME=READY_OFFLINE_MODEL
D279_11_CONFIGURABLE_STAGE_PROFILES_TESTED=2,3,21
D279_11_ATTEMPT02_OBSERVED_STAGE_COUNT=21
D279_11_OEM_UNIVERSAL_STAGE_COUNT_CLAIM=false
D279_11_PRIMARY_B0_LIBFPRINT_STAGE_EVENT=true
D279_11_AUXILIARY_B0_PROTOCOL_INTERNAL_APPLICATION_SEMANTICS=UNDETERMINED
D279_11_PRIMARY_FPIMAGE_DELIVERY_PROFILES=2,3,21
D279_11_AUXILIARY_B0_FPIMAGE_DELIVERY_COUNT=0
D279_11_FEDORA44_LIBFPRINT_1_94_100_NBIS_BUILD=PASS
D279_11_PRODUCTION_ENROLLMENT_ENABLED=false
D279_11_SENSOR_REACHING_CODE_CHANGED=false
D279_06_OUTCOME=READY
D279_06_BASELINE=91d62a6ef775f03ec6a38d1d6febb68d216aaa86
D279_06_EXECUTABLE_CLOSURE=PASS_OFFLINE_SYNTHETIC_FULL_COMPOSITION
SINGLE_TARGET_MATERIAL_OWNER=true
SECURE_VIEW_NON_OWNING=true
FDT_SEED_SAME_OWNER=true
D279_05_OUTCOME=READY
D279_05_BASELINE=8f11ad0997451ff1ce06f8daf8dabe41f694cca8
D279_05_EXECUTABLE_CLOSURE=PASS_OFFLINE_SYNTHETIC_FILES
PRIVATE_INPUT_READER_LGPL=true
OUTPUT_PUBLICATION=ATOMIC_AFTER_BOTH_INPUTS_VALIDATE
D279_04_OUTCOME=READY
D279_04_BASELINE=c48acb4bacfb6a3ccfd2c45b60733be1ce4075db
D279_04_EXECUTABLE_CLOSURE=PASS_OFFLINE
PE_PRODUCER_PROVIDER_LGPL=true
FDT_SEED_PROVIDER_LGPL=true
PRODUCTION_PINS_COMPILED=true
AUTHENTIC_PROTECTED_INPUTS_EXECUTED=false
D279_03_OUTCOME=READY
D279_03_BASELINE=3c8b846c4dd0ffbb493f11590f3c5d6c7f647692
EXECUTABLE_CLOSURE=PASS_OFFLINE
EXTRACTOR_DECISION=NBIS
DECISION_CLASS=ARCHITECTURAL_TECHNICAL
NBIS_PIPELINE_COMPATIBLE=true
NBIS_BIOMETRICALLY_VALIDATED=false
SIGFM_PIPELINE_COMPATIBLE=false
SIGFM_BIOMETRICALLY_VALIDATED=false
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
PPMM_EVIDENCE_CLASS=UNKNOWN
NBIS_80X64_COMPATIBILITY=CONDITIONAL
SIGFM_TARGET_SPECIFIC_NECESSITY=NOT_PROVEN
BIOMETRIC_VALIDATION_PENDING=true
TARGET_REAL_DECODED_RASTER_DATASET_IN_REPOSITORY=false
BIOMETRIC_MATCHER_BENCHMARK_READY=false
TARGET_OS=Fedora_44_x86_64
TARGET_LIBFPRINT_VERSION=1.94.100
TARGET_LIBFPRINT_PACKAGE=libfprint-1.94.100-1.fc44.x86_64
TARGET_LIBFPRINT_REFERENCE=reference/libfprint-fedora44-1.94.100/source
ROCKYTKG_LIBFPRINT_IS_PRODUCTION_TARGET=false
TARGET_1_94_100_IMAGE_PATH=NBIS_ONLY_VERIFIED
TARGET_GOODIX_ALGORITHM=NBIS
HOST_ONLY_HISTORICAL_GOODIX_ALGORITHM=SIGFM
PRODUCTION_USB_ID_27C6_5125_REGISTERED=true
LIBFPRINT_1_94_100_PRODUCTION_SHAPED_BUILD=PASS
FPIMAGE_PPMM_ASSIGNED=false
FPRINTD_OPERATIONAL_PATH_PROVEN=false
D279_01_OUTCOME=BLOCKED
D278_14_CLOSED_LIVE=true
REAL_USB_ACCESS=OPERATOR_OEM_PASSIVE_CAPTURE_ATTEMPT02
REAL_USB_OPEN=OEM_DRIVER_NOT_KIT_SENDER
REAL_USB_CLAIM=OEM_DRIVER_NOT_KIT_SENDER
REAL_USB_SUBMIT=OEM_DRIVER_NOT_KIT_SENDER
LIVE_EXECUTION_PERFORMED=true
CURRENT_LIVE_AUTHORIZED=false
VISIBLE_KNOWN_PERSISTENT_COMMAND_FAMILY_COUNT=0
FACTORY_STATE_MUTATION=NOT_DETERMINABLE_FROM_VISIBLE_FAMILIES_OR_TAIL
WIRE_PROTOCOL_SEMANTICS_CHANGED=false
D278_14_RERUN_REQUIRED=false
D278_14_RERUN_AUTHORIZED=false
NEXT_PRIMARY_BOUNDARY=OFFLINE_CONTEXT_FIRST_ARM_HANDOFF_TO_PARAMETRIC_ENROLLMENT_GRAPH_WITH_LIBFPRINT_CALLBACKS_AND_GATE
REAL_PATH_PROVISIONING=PASS_AUTHORIZED_OPERATOR
NEXT_LIVE_PREREQUISITE=OFFLINE_IMPLEMENTATION_REVIEW_THEN_FULL_SHA_BASELINE_APPROVAL_AND_EXPLICIT_SINGLE_SHOT_AUTHORIZATION
```

### D279/10 — Kit passivo per il primo enrollment OEM completo

Il metodo non generalizza il sender Linux e non invia wire command. USBPcap è
avviato prima dell'attach; observer e capture restano attivi per tutti i
contatti richiesti dall'UI Windows. La conferma numerica dell'operatore che
l'impronta è realmente registrata è l'authority terminale, seguita da un tail
host di cinque secondi. Il finalizer verifica pcap finalizzato, SHA-256, eventi
operatore e tail, conta dinamicamente i lifecycle
`IRQ2 → 0x22 → ACK 0x01 → B0` e conserva il terzo come sola milestone.

Il launcher applica full SHA, branch `development`, live-critical set pulito,
assenza target same-run prima di attempt/capture/attach, output CreateNew
scoped a un `attempt_id`, deadline 1200 s, cleanup e output metadata-only. Ogni
prompt è numerico. Nessun failure avvia retry: lo stato suggerisce no-restore
soltanto prima di attach/wizard e richiede altrimenti il restore dello snapshot.
Un restore è vietato operativamente finché `raw/` e `sanitized/` non sono stati
esportati fuori dalla VM/snapshot.

Le possibili mutazioni host-side e sensor-side del solo workflow OEM sono state
accettate esplicitamente dall'Utente; la prima è snapshot-manageable, mentre la
seconda resta non escludibile ma riguarda un sensore già storicamente enrolled.
La decisione non autorizza una nuova run né i comandi manutentivi esclusi.

L'attempt 01 si è fermato prima del wizard per quattro frame OEM fissi control
`0x01` completi che D274 sottoponeva erroneamente al checksum generico. La forma
esatta è ora allowlistata; strict final e growing parse concordano, mentre ogni
near-miss resta fail-closed.

L'attempt 02 ha poi osservato l'intero enrollment: 21 stage primari completi,
20 re-arm, una transizione NAV specifica del primo ciclo e un ciclo terminale
senza re-arm. Il contatto operatore extra non è localizzabile perché manca la
telemetria per-contact e non esiste un lifecycle wire parziale. La sequenza
target termina prima della conferma UI e il tail post-UI resta senza pacchetti.
L'assenza visibile delle famiglie persistenti note non esclude persistenza
sensor-side. Report:
`analysis/D279/D279_10_attempt02_full_enrollment_analysis.md` e
`analysis/D279/D279_10_attempt02_full_enrollment_audit.json`.

### D279/11 — oracle enrollment parametrico host-only

Il primo modello post-ATTEMPT02 è intenzionalmente separato dal sender:
`goodix_enrollment_model.[ch]` accetta una sequenza metadata-only e verifica le
tre forme osservate (prima con NAV, ripetute con re-arm, terminale senza
re-arm). Il conteggio richiesto è configurazione esplicita; le fixture coprono
2, 3 e il profilo target-local osservato di 21 stage. Quest'ultimo non viene
promosso a costante OEM universale.

Soltanto il B0 primario che segue `0x22` produce il callback di avanzamento
libfprint-oriented. Il B0 cifrato successivo a `0x20` viene consumato nella
transizione interna e contato separatamente: il modello non gli attribuisce
un'immagine accettata, ma non esclude né nega possibili ruoli quality/template/
NBIS, che restano semanticamente indeterminati. Eventi fuori ordine chiudono
l'istanza senza retry.

La seam distingue ora stage primari osservati da stage consegnati. Con il flag
esplicito di deferral, l'ultimo `FpImage` conserva provenienza dal B0 primario
ma viene consegnato solo all'IRQ0200 terminale: il caller può notificare
finger-up prima che l'estrazione asincrona concluda l'enrollment. Questo evita
la race reale riprodotta in cui libfprint tentava la deactivation mentre era
ancora in `AWAIT_FINGER_OFF`; non attribuisce contenuto immagine all'IRQ.

Il modulo non dipende da USB, TLS o backend, non è collegato ai vfunc e non
modifica il lifecycle sensor-reaching D275. Enrollment production resta quindi
respinto prima di ogni submit. Sei test passano sia normal sia ASan/UBSan per
i tre profili, separazione primary/auxiliary, callback failure e fail-closed
con diagnostica expected/actual. La seam
`goodix_enrollment_pipeline.[ch]` aggiunge il vero mapping `u16 → FpImage`:
consegna 2/3/21 immagini primarie transfer-none, zero immagini ausiliarie e
rifiuta raster fuori posizione e rilascia immediatamente l'immagine terminale
pending se la transizione fallisce. Cinque test aggiuntivi passano normal e
ASan/UBSan; la classe 27c6:5125 pubblica ora la policy target-local di 21 stage
osservata in ATTEMPT02, mentre l'oracle generico resta parametrico. Una vera
operazione asincrona `FpImageDevice` attraversa 21 progress e un solo
completion con ordering terminale corretto; usa il double SIGFM del test
harness e non prova NBIS né qualità biometrica. La suite completa è 25/25
normal e ASan/UBSan e la build Fedora 44/libfprint 1.94.100 con NBIS resta
verde senza enumerazione USB. Enrollment production resta respinto prima di
ogni submit finché il lifecycle sensor-reaching non è integrato e revisionato.
Il nuovo `goodix_enrollment_command_plan.[ch]` compone oracle e pipeline senza
serializzare: per il profilo 21 produce 125 intenti tipizzati, con conteggi
enrollment-only `0x20×21`, `0x22×21`, `0x32×21`, `0x34×41`, `0x36×20` e
`0x50×1`, coerenti con ATTEMPT02 una volta esclusi bootstrap e re-entry. Le
classi body distinguono semplici, FDT e FDT+timestamp, ma non espongono bytes,
builder A0 o backend; i due test passano normal e ASan/UBSan e gli audit
restano a zero serializzazioni, submit e retry. Il confine successivo è il
contratto per-ciclo delle tabelle FDT e dei timestamp, non ancora il sender.
`goodix_enrollment_command_body.[ch]` chiude ora la parte strutturale di tale
contratto: body interni da 2/14/16 byte, binding fail-closed a stage e ruolo
`STAGE_UP`/`STAGE_AUX_SCAN`/`TRANSITION_DOWN`, timestamp obbligatorio solo per
`0x32` e clear esplicito. Non costruisce A0/fixed64 e non ha backend. Tutti gli
otto purpose sono coperti; stage stale, ruolo errato, timestamp mancante e
materiale superfluo falliscono. Resta da derivare dinamicamente la corretta
tabella per ruolo dagli IRQ del singolo ciclo e da inserirla in un adapter
lifecycle iterativo mantenendo il gate production.
Report:
`analysis/D279/D279_11_configurable_enrollment_model.md`.

### D279/12 — derivazione FDT dinamica target-local

Il riesame hash-gated del raw ATTEMPT02 aggiunge solo relazioni booleane al
JSON sanitizzato: tutti i 41 `0x34` equivalgono alla trasformazione up
dell'IRQ2 dello stesso stage; tutti i 20 `0x36` enrollment equivalgono alla
trasformazione down dell'IRQ0200 dello stage precedente e differiscono dalla
tabella `0x34` corrente; tutti i 21 `0x32` equivalgono alla trasformazione down
dell'IRQ0200 dello stesso stage. I due `0x32` del primo ciclo condividono la
tabella ma hanno timestamp distinti. Nessun byte tabellare viene esportato.

`goodix_enrollment_fdt_state.[ch]` implementa queste relazioni con stage
consecutivi, retention della sola latest-down e output material tipizzato per
il body contract. La fixture percorre i 21 stage osservati; 2/2 test passano
normal e ASan/UBSan, l'audit autentico passa 3/3 e `captures/` resta invariato.
Il modulo non contiene A0, backend, retry o submit e non modifica il gate
production. Il B0 ausiliario resta semanticamente indeterminato. Report:
`analysis/D279/D279_12_target_local_dynamic_fdt_derivation.md`.

### D279/13 — adapter lifecycle enrollment iterativo

`goodix_enrollment_lifecycle_adapter.[ch]` compone oracle parametrico, stato
FDT e body contract in transazioni `observe → prepare → commit`. IRQ FDT e
raster primario sono payload tipizzati; un comando preparato resta in cache,
incluso il timestamp `0x32`, fino al commit esatto. Osservazioni con comando
pending e commit discordanti falliscono chiuso, senza retry.

I profili sintetici 2/3/21 passano 3/3 normal e ASan/UBSan. Nel profilo
ATTEMPT02 vengono prodotti e committati offline 125 body interni, con 21
timestamp e 21 immagini, ma 21 resta il valore target-local osservato e non
una costante OEM universale. Il modulo non contiene A0, backend o submit;
l'enrollment production resta esplicitamente disabilitato. La build Fedora 44
production-shaped con registry standard e NBIS passa senza enumerazione/open/
claim/submit USB. Il B0 ausiliario rimane semanticamente indeterminato,
incluso l'eventuale ruolo in quality, template o NBIS. Report:
`analysis/D279/D279_13_iterative_enrollment_lifecycle_adapter.md`.

### D279/14 — binding inbound post-TLS enrollment

`goodix_enrollment_post_tls_events.[ch]` traduce frame A0 completi già
decifrati nell'evento esatto atteso dall'adapter. Sono ammessi soltanto ACK con
echo/status esatti, IRQ2/IRQ0100/IRQ0200 con control/id/flags target-local e il
NAV OEM no-check 2417/2410 con control `0x50` e marker `0x88`. Raster primario
già decodificato e B0 ausiliario opaco hanno API distinte.

La sequenza completa passa per profili 2/3/21, normal e ASan/UBSan; il profilo
ATTEMPT02 conta 188 A0 inbound, di cui 125 ACK, 62 IRQ e un NAV. Echo e flags
errati falliscono chiuso. Il binding non include builder A0, fixed64, backend
o submit; la build Fedora 44 con registry standard/NBIS passa e il gate
enrollment production resta invariato. Il B0 ausiliario è
trattato come transizione protocol-internal, ma la sua eventuale utilità per
quality, template o NBIS resta non determinata. Report:
`analysis/D279/D279_14_inbound_post_tls_enrollment_events.md`.

### D279/15 — reassembly B0 bounded e contenuto ausiliario preservato

Il binding inbound ricompone ora un messaggio plaintext B0 dalla lunghezza
dichiarata entro 8192 byte. Il primario mantiene il contratto decoder esatto
7693 e produce il raster canonico. L'ausiliario viene consegnato completo e
invariato a un callback opaco obbligatorio prima della transizione: non viene
decodificato, scartato né dichiarato inutile a quality/template/NBIS.

La lunghezza wire cifrata 7726 osservata per entrambi i B0 in ATTEMPT02 è solo
compatibile con una forma simile; non dimostra una lunghezza plaintext OEM
universale, quindi il ramo ausiliario resta declared-length e bounded. La
regressione frammenta entrambi i messaggi, usa un primario CRC-valido e un
ausiliario volutamente non valido come immagine per provarne la consegna
opaca. Lunghezza primaria errata fallisce chiuso. 5/5 test passano normal e
ASan/UBSan, senza A0 build, backend o submit. Report:
`analysis/D279/D279_15_bounded_b0_plaintext_delivery.md`.

### D279/16 — serializer outbound enrollment-only

`goodix_enrollment_outbound_frame.[ch]` ri-valida un comando preparato e
costruisce il relativo A0 fixed64 con allowlist chiusa
`0x20/0x22/0x32/0x34/0x36/0x50`. Non contiene backend o submit API e non
ammette le famiglie persistenti note. L'assenza di tali famiglie non dimostra
assenza di mutazioni sensor-side nel workflow OEM; definisce soltanto il
confine del nuovo serializer.

Tutti gli otto purpose passano round-trip parser/body/padding fixed64; un body
manomesso fallisce prima del build. 2/2 test passano normal e ASan/UBSan. Il
gate production continua a rifiutare enrollment prima dell'attivazione.
Report: `analysis/D279/D279_16_enrollment_outbound_serializer.md`.

### D279/17 — transazione OUT sintetica completion-gated

`goodix_enrollment_outbound_transaction.[ch]` aggiunge uno sink astratto e un
solo OUT pending. Il planner viene committato esclusivamente dopo completion
positiva con la stessa generation; fino a quel momento l'ACK non è accettato.
Doppio OUT, inbound anticipato, generation stale ed errore transport sono
terminali e non generano retry.

I profili 2/3/21 passano ora ogni comando attraverso la transazione; il profilo
ATTEMPT02 esegue offline 125 build/sink/completion/commit. La suite combinata
passa 7/7 normal e ASan/UBSan e prova stale generation e ACK anticipato senza
commit. Il modulo non dipende dal backend USB reale e il gate production
continua a rifiutare enrollment. Report:
`analysis/D279/D279_17_completion_gated_synthetic_out.md`.

### D279/18 — binding dormant a GoodixFpiUsbBackend

`goodix_enrollment_fpi_usb_binding.[ch]` adatta lo sink e la completion della
transazione al backend USB esistente. La costruzione non invia; il test usa
obbligatoriamente la seam asincrona host-only, verifica stale generation senza
commit e completion corretta con un commit, con `real_submit_count=0`.

Il modulo è sensor-reaching se un futuro caller lo invoca senza seam. Oggi non
esiste alcun caller production e `goodix_fpimage_device_activate()` respinge
ancora `FPI_DEVICE_ACTION_ENROLL` prima di iniziare la generation. Il binding
non va reso raggiungibile prima di chiudere cancellation/drain/ownership e di
una nuova review esplicita. 8/8 test combinati passano normal e ASan/UBSan.
Report: `analysis/D279/D279_18_dormant_fpi_usb_enrollment_binding.md`.

### D279/19 — cancellation terminale e drain OUT del binding

Il binding dormant annulla prima il backend, porta la transazione in stato
terminale senza retry e vieta la propria distruzione finché l'OUT fisico resta
outstanding. Una completion tardiva della stessa generation dopo cancellation
chiude il drain host ma non può committare il planner. La cancellazione è
idempotente e l'audit distingue una sola transizione terminale.

La regressione con backend/router host-only e seam asincrona passa 9/9 sia
normal sia ASan/UBSan: prima della completion `can_free=false`, dopo la
completion cancellata `can_free=true`, commit lifecycle zero e submit USB reale
zero. La build Fedora 44/libfprint 1.94.100 con registry standard e NBIS resta
verde senza enumerazione/open/claim/submit USB. Non esiste ancora un owner nel
device context e nessun caller production;
`goodix_fpimage_device_activate()` continua quindi a respingere enrollment
prima della generation. Il successivo confine offline è l'ownership dormant
nel context con lo stesso activation gate, non l'abilitazione live. Il profilo
resta configurabile: 21 è soltanto il numero target-local osservato in
ATTEMPT02. I B0 ausiliari restano consegnati opacamente e la loro semantica
quality/template/NBIS non è determinata. Report:
`analysis/D279/D279_19_enrollment_binding_cancellation_drain.md`.

### D279/20 — ownership dormant nel device context

`GoodixDeviceContext` può ora adottare, solo durante un operator epoch
host-only esplicito, un binding enrollment già costruito. L'adozione fallisce
se backend o generation non coincidono, se il context è fenced/terminale, se
esiste già un binding o se TLS, secure session o lifecycle post-TLS legacy sono
ancora owner del callback OUT. Il context non costruisce il grafo e non invoca
submit: conserva soltanto ownership, cancellation e teardown.

Una costruzione riuscita del binding trasferisce anche ownership dell'intero
`GoodixEnrollmentPostTlsEvents`; il teardown è quindi autosufficiente. Il
terminal fence cancella il binding e il context verifica il drain backend e
del binding prima di liberare nell'ordine binding → backend → router. La
regressione lascia un OUT sintetico pending, ferma l'epoch, osserva zero commit,
completa il drain cancellato e distrugge il context. La suite `FpImageDevice`
passa 26/26 normal e ASan/UBSan; la suite enrollment passa 9/9 in entrambe le
modalità. La build Fedora 44/libfprint 1.94.100 con registry standard/NBIS
passa, senza warning nuovi e con zero enumerazione/open/claim/submit USB.

Il gate production che rifiuta `FPI_DEVICE_ACTION_ENROLL` prima della
generation è invariato e non esiste un caller production dell'API di adozione.
Il prossimo confine è progettare offline l'handoff esclusivo dal secure/post-
TLS graph all'enrollment e le callback libfprint, mantenendo il gate; non è
ancora autorizzata alcuna attivazione live. Il conteggio rimane configurabile:
21 indica soltanto gli stage riusciti osservati in ATTEMPT02. I B0 ausiliari
restano preservati opacamente e la loro semantica quality/template/NBIS non è
determinata. Report:
`analysis/D279/D279_20_dormant_device_context_enrollment_ownership.md`.

### D279/21 — handoff backend dopo il primo arm post-TLS

Un handoff diretto dalla secure session al modello enrollment sarebbe
incompleto: il modello D279/11 inizia dal primo IRQ2, mentre il target osservato
richiede prima il bootstrap post-TLS fino all'arm `0x32/ACK`. Il lifecycle
legacy offre ora un callback opzionale configurabile soltanto prima dello
start. Dopo l'ACK del primo arm verifica OUT zero, rilascia il proprio callback
backend, entra in STOP e invoca il nuovo owner prima del primo IRQ2. Il path
default a due acquisizioni resta invariato.

La regressione percorre il bootstrap host-only di nove comandi, verifica otto
ACK più la risposta AF, zero immagini/finger event, handoff singolo e backend
drenato. Un callback nuovo viene installato durante l'handoff e riceve due
completion sintetiche, una anche dopo il free del lifecycle precedente: ciò
prova che il vecchio owner non cancella il callback successivo. Il rifiuto del
successore porta invece a terminal fence senza retry. La suite passa 10/10
normal e ASan/UBSan, con submit reale zero. La build Fedora 44/libfprint
1.94.100 con registry standard e NBIS resta verde senza enumerazione/open/
claim/submit USB.

Questo confine non afferma che i due re-entry OEM osservati dopo le lunghe pause
di ATTEMPT02 siano sempre necessari né sempre evitabili: un avvio Linux
immediato non è stato provato live. Il prossimo step offline può collegare
questo callback all'ownership context e al grafo enrollment parametrico con
callback libfprint, mantenendo il gate production. `21` resta il solo conteggio
target-local osservato; i B0 ausiliari restano opachi con semantica quality/
template/NBIS non determinata. Report:
`analysis/D279/D279_21_first_arm_backend_handoff.md`.

### D279/07 — layout production e identità runtime fprintd

`goodix_runtime_material_paths_production()` rende canonici i cinque path
autorizzati; la policy e i loader impongono directory uid/gid/mode
`0:0/0700`, file `0:0/0600`, parent diretto e controlli pre/post. Nove test
sintetici normali e ASan/UBSan passano; la regressione D278 passa 63/63 in
entrambe le modalità e la build/registry Fedora 44 resta verde.

Il Real Target Compatibility Gate è stato chiuso dal provisioning e dal probe
full eseguiti manualmente dall'Utente: layout completo, metadata reali,
identità root, sandbox e mapping/label/allow `fprintd_var_lib_t` con SELinux
`Enforcing` sono `PASS`. Il probe non ha letto contenuto né avviato fprintd;
USB è rimasto non acceduto. Il provisioning separato ha verificato i pin, non
ha sovrascritto i tre file esistenti e ha installato i due mancanti. Report:
`analysis/D279/D279_07_offline_production_layout_and_fprintd_identity_gate.md`.

### D279/08 — binding production `img_open` / `img_close`

La sottoclasse USB ora istanzia l'owner unico D279/06 dai path D279/07 prima
del claim dell'interfaccia 0. Il core libfprint ha già aperto `GUsbDevice` prima
della vfunc, vincolo verificato sul sorgente e nella build target; il driver
non introduce open/close paralleli. Close, failure e cancellation convergono
su un solo tentativo di release e sul cleanse/free garantito; il path virtuale
resta senza filesystem o USB.
Tre test specifici con seam sintetiche verificano ordine, due epoch e failure,
mentre la suite completa passa normale e ASan/UBSan. Report:
`analysis/D279/D279_08_offline_production_open_close_binding.md`.

### D279/09 — activation production bounded

La vfunc USB avvia ora il pre-session RX sync e, soltanto dopo il quiet PASS,
costruisce secure session, TLS retained e lifecycle post-TLS usando l'owner
della open epoch. Le view borrowed vengono cancellate dopo l'handoff; errori
asincroni raggiungono `activate_complete(error)` o `session_error(error)` in
base allo stato reale del framework. Il path virtuale e quello operator D278
restano separati.

L'enrollment non è dichiarato risolto: viene respinto prima di generation e
submit perché libfprint richiede cinque stage mentre APP12509 è provato solo
fino al secondo B0. Nessuna scelta automatica di due stage e nessuna
generalizzazione del terzo ciclo sono state introdotte. Il gate enrollment non
maschera uno sticky poison preesistente: l'errore terminale dell'open epoch ha
precedenza e non genera nuovi submit. Report:
`analysis/D279/D279_09_offline_production_activation_binding.md`.

### D279/06 — owner unico dei materiali runtime

`goodix_runtime_material.[ch]` mantiene la lifetime delle view coerente con una
open epoch, senza duplicare PSK/validator/CONFIG90. La suite osserva cleanse
dei buffer PE/cache, dei due seed produttore, del descriptor, di FDT12 e dei
tre oggetti protetti al teardown. L'audit passato al loader deve vivere almeno
quanto l'owner. D279/07 ha chiuso path, provisioning e compatibilità target;
D279/08 ha poi collegato owner e claim alla sottoclasse USB e D279/09 ha
cablato l'activation secure bounded. Ogni esecuzione fprintd/live resta
aperta. Report:
`analysis/D279/D279_06_offline_open_epoch_material_owner.md`.

### D279/05 — reader dei due input privati PE/cache

`goodix_runtime_extract_inputs_from_files()` risolve il boundary filesystem
senza un path searcher e senza toccare USB o i tre file del loader protetto.
Il test roundtrip prova due file sintetici 0600; una seam post-read cambia i
metadata e dimostra rifiuto, output tutti zero e cleanse del buffer già
allocato. D279/06 ha poi composto l'owner dell'intera open epoch e D279/07 ha
aggiunto GID e directory production senza duplicare secret o state machine.
Report:
`analysis/D279/D279_05_offline_private_runtime_input_reader.md`.

### D279/04 — provider inerti PE/FDT nel dominio LGPL

`libfprint-driver/goodix_runtime_inputs.[ch]` riceve soltanto array di byte
caller-owned. Il parser PE valida hash, header, section table, file-backed RVA
e unicità del pattern produttore prima di restituire due seed da sei byte. Il
provider cache verifica hash intero, CRC memorizzato little-endian, hash OTP64,
offset FDT12 e presenza del seed. Errori e output sono fail-closed.

`libfprint-driver/tests/run_goodix_runtime_inputs_test.sh` usa solo fixture
sintetiche nel Freedesktop SDK 25.08 senza rete e passa in modalità normale e
ASan/UBSan. La successiva build Meson production-shaped include anche binder,
loader protetto e provider, ma non li collega ancora a `img_open`: file
ownership/TOCTOU, vita delle view, claim/release USB e cleanup di close sono il
boundary successivo. Report:
`analysis/D279/D279_04_offline_lgpl_runtime_input_providers.md`.

### D279/03 — registrazione e build production-shaped con NBIS

D279/03 chiude offline il boundary di registry: la source map 1.94.100 usa i
sorgenti canonici LGPL in `libfprint-driver/`, dichiara la dipendenza OpenSSL
già necessaria al TLS nativo e registra il tipo tramite il meccanismo standard
`supported_drivers`/`fpi-drivers.c`. Non esiste un registrar custom e non viene
creato un secondo backend, router, TLS o lifecycle.

Il runner
`libfprint-driver/tests/run_goodix_fedora44_registration_test.sh` costruisce i
target `fprint-2` e `fprint-list-supported-devices`, verifica simbolo, define
NBIS, ID unico e output registry. L'host non ha `libgusb-devel`: il runner usa
un header ABI compile-only dedicato e collega il vero runtime Fedora 0.4.9. La
generazione GIR completa non è parte della closure perché manca anche
`GUsb-1.0.gir`; libreria e registry production-relevant compilano.

Il limite corrente è esplicito: la classe è registrata, ma `img_open` conserva
ancora il comportamento host-only e non configura autonomamente claim USB,
materiale protetto e secure-session D278. Installazione, fprintd e qualunque
esecuzione sensor-reaching restano fuori scope e non autorizzati. Report:
`analysis/D279/D279_03_offline_fedora44_production_usb_registration_NBIS.md`.

### D279/01 — BLOCKED storico: incompatibilità extractor prima della decisione D279/02

**Audit offline del 2 settembre 2026.** D279/01 è iniziato sulla baseline
`f609c865f760768edb6a9e404b863ccd0569e1c8` per integrare il driver nel source
target `reference/libfprint-fedora44-1.94.100/source`. Si è arrestato prima di
modificare codice o Meson: 1.94.100 è NBIS-only, la classe Goodix selezionava
SIGFM, e il contratto canonico D269–D271 trattava ancora `ppmm` ignoto come
veto NBIS. Portare SIGFM era fuori scope. I documenti D279/01, lasciati
inizialmente non committati per review umana, sono stati poi integrati in
`924774e9bd7ea10eabdfd540bf8a4be9b8413c99`. D279/02 ha poi chiuso la decisione
extractor; alla fine di quello step la registrazione restava non eseguita.
D279/03 la chiude successivamente senza cambiare l'esito storico D279/01.

```text
D279_01_OUTCOME=BLOCKED
D279_01_BASELINE=f609c865f760768edb6a9e404b863ccd0569e1c8
D279_01_DOCS_COMMITTED_AS=924774e9bd7ea10eabdfd540bf8a4be9b8413c99
TARGET_1_94_100_IMAGE_PATH=NBIS_ONLY_VERIFIED
D279_01_CURRENT_GOODIX_ALGORITHM=SIGFM
D279_01_PRODUCTION_USB_ID_27C6_5125_REGISTERED=false
HISTORICAL_NEXT_PRIMARY_BOUNDARY_AFTER_D279_01=OFFLINE_FEDORA44_LIBFPRINT_1_94_100_EXTRACTOR_COMPATIBILITY_DECISION
```

### Stato corrente post-D278/14 — CLOSED_LIVE: doppia acquisizione native C target-proven

**Closure canonica del 1 settembre 2026.** D278/14 è chiuso con esito live
`PASS` sul target reale `27c6:5125` / `GF_ST411SEC_APP_12509`. La dodicesima
autorizzazione one-shot, eseguita sulla baseline
`5b7b8415d57a474ae9915a4e46954a7afaafe327` con binario SHA-256
`7f9ecad1097c279d54c6ba7f61be9e00c7ef1e5edd6b9362f72320dcf8e34379`,
ha completato nello stesso percorso nativo C:

`reentry A2 -> A8 -> E4 -> cold-start -> D1 -> TLS -> D4 -> AF ->
fresh-FDT -> primo IRQ2 -> 0x22 -> primo B0/decode/FpImage ->
0x34 -> IRQ0200 -> 0x20/B0 -> NAV -> fresh-down -> rearm 0x32 ->
secondo IRQ2 -> 0x22 -> secondo B0/decode/FpImage -> STOP`.

La run ha usato un solo open/claim USB, un solo backend/router/reader fisico,
una sola sessione TLS e un solo secret handoff; ha chiuso con zero retry,
reopen, reset, clear-halt, terzo ciclo e scritture persistenti. Entrambi i
raster target sono stati decodificati e consegnati alla pipeline immagine.

```text
D278_14_LIVE_RESULT=PASS
D278_14_FINAL_BASELINE=5b7b8415d57a474ae9915a4e46954a7afaafe327
D278_14_FINAL_BINARY_SHA256=7f9ecad1097c279d54c6ba7f61be9e00c7ef1e5edd6b9362f72320dcf8e34379
D278_14_TOTAL_LIVE_ATTEMPTS=12
D278_14_TOTAL_CONSUMED_AUTHORIZATIONS=12
D278_14_CLOSED_LIVE=true
LINUX_FIRST_IMAGE_PIPELINE_LIVE_PROVEN=true
LINUX_SECOND_IMAGE_PIPELINE_LIVE_PROVEN=true
SECOND_IMAGE_RASTER_TARGET_PROVEN=true
TWO_ACQUISITION_REARM_LIVE_PROVEN=true
SAME_GOODIX_DEVICE_CONTEXT_LIVE_PROVEN=true
SINGLE_USB_BACKEND_OWNER_LIVE_PROVEN=true
SINGLE_USB_ROUTER_LIVE_PROVEN=true
SINGLE_PHYSICAL_IN_OWNER_LIVE_PROVEN=true
SAME_TLS_SESSION_THROUGH_SECOND_IMAGE_LIVE_PROVEN=true
SINGLE_SECRET_HANDOFF_LIVE_PROVEN=true
THIRD_CYCLE_COMMAND_COUNT=0
RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
BACKEND_DRAINED=true
CLEANUP_COMPLETE=true
CURRENT_LIVE_AUTHORIZED=false
D278_14_RERUN_REQUIRED=false
```

Le sezioni cronologiche D278 precedenti restano nel manuale come **storia
probatoria**: i loro marker `false`/`UNOBSERVED` descrivono correttamente ciò
che era noto a quel momento, ma non rappresentano più lo stato corrente quando
sono esplicitamente marcati come superati dalla closure D278/14 live #12.

D278/09 preserva la conclusione D278/08: la recovery OEM pre-D1 è risolta ma
non factory-preserving e non è un candidato Linux. Aggiunge un candidato
progettuale distinto, deliberatamente bounded: exact A2 sensor-only `{01 14}`
una sola volta, seguito esclusivamente da ACK e typed A2 strict. La singola
live D278/09 è consumata e ha provato che A2 viene accettato nel current
re-entry context con ACK `0x07` e typed target-pinned. La successiva singola
live D278/10, anch'essa consumata e non ripetibile, ha completato nella stessa
open epoch exact A2 `{01 14}` e A8: entrambi hanno prodotto ACK `0x07` e typed
strict, con A8 byte-identical a `GF_ST411SEC_APP_12509`. Non sono comparsi
frame inattesi e non sono stati eseguiti E4, TLS, retry, reopen, reset,
clear-halt o write persistenti.

D278/11 promuove quindi A2 a policy di recovery del progetto provata efficace
per ristabilire A8 nel target/context corrente e la integra come prefisso del
secure-session nativo completo. Dopo la closure host-only, la singola live
D278/11 sulla baseline
`b704d52ccc292c4fc669373c7eb8d8b296518ff7` ha attraversato l'intera catena
reentry-prefixed fino al TLS 1.2 PSK con esito `PASS`; la one-shot è consumata
e non autorizza rerun. La fase
`REENTRY_RECOVERY_A2` resta semanticamente distinta da
`OEM_COLD_START_A2_1/2`; il meccanismo causale, la necessità universale e la
nonmutazione NVM assoluta restano non provati.

D278/12 collega poi, esclusivamente host-only, lo `STOP` del secure-session al
lifecycle D4→AF→fresh-FDT→prima acquisizione→release→rearm→seconda acquisizione
nel medesimo `GoodixDeviceContext`, backend, router, generation e oggetto TLS.
Il passaggio di ownership è callback-driven e avviene solo a egress TLS
drenato; non introduce polling, secondo reader, seconda sessione TLS o reopen.

D278/13 chiude il successivo gap di binding senza creare un altro stack: un
adapter GPL operator-only costruisce la shell non registrata sul `GUsbDevice`
già selezionato, apre una sola epoch del medesimo `GoodixDeviceContext` e gli
consegna il loader protetto D278/02 e il seed FDT canonico read-only. Il driver
LGPL continua a possedere l'unico backend/router/reader, secure-session, TLS e
lifecycle post-TLS. L'entrypoint è stato eseguito soltanto con peer e materiale
sintetici; il binario live-shaped ordinario ha baseline `UNAPPROVED_FOR_LIVE`
e il suo gate ha arrestato l'esecuzione prima di secret, cache e contesto USB.
Il correttivo revisionato rispetto alla baseline AI-PM
`8abab4a96075ef4057226ef0c5077f483a7636c0` chiude due gap host-side senza
creare D278/14: un build con SHA pieno usa soltanto lo snapshot Git dell'esatto
commit dopo verifica HEAD e pulizia del set live-critical, mentre un ticket
esplicito `0600` lega SHA/operation/nonce ed è reclamato atomicamente una sola
volta prima di qualunque materiale protetto, cache o GUsb. Il precedente token
statico era riutilizzabile e non costituiva da solo un single-shot meccanico.

D278/14 ha richiesto **quattro live autorizzate separate**, tutte consumate. La
prima, sulla baseline `2172e750ae7c100a3a891ba25d0797286230a4ab`, è fallita
nell'assert di `fp_device_set_property()` durante il binding USB del `FpDevice`
(`SIGABRT`, exit 134): la classe comune era `FP_DEVICE_TYPE_VIRTUAL` ma il
costruttore assegnava un `fpi-usb-device` non nullo. `begin_operator_epoch`,
A2/A8, TLS e post-TLS non sono stati raggiunti. Il core dump osservato non è
stato letto, copiato o incluso nel review set.

La seconda live, sulla baseline
`fceae05d9ff3ed14348f9031706e70d5a808ff91` con binario
`de935e0a3fc89a345a2bad624ba3d218f51ab036597d13566d985efbada4f270`, ha
inviato il comando A2 e ricevuto il suo ACK, ma non ha mai sottomesso un
secondo IN fisico, quindi la risposta tipata A2 non era osservabile. La run è
terminata per `ONE_SHOT_DEADLINE` con trace `REENTRY_RECOVERY_A2>TERMINAL`.
Il dito non è stato appoggiato perché la run non ha mai raggiunto A8, TLS,
post-TLS o acquisizione. Cleanup e zeroizzazione secret di progetto sono
completati.

Il **correttivo #1** host-only ha aggiunto una sottoclasse `USB` sottilissima
usata solo da `goodix_fpimage_device_new_for_usb()`, con lo stesso
`GoodixDeviceContext` e nessun nuovo protocollo/backend/router/TLS/lifecycle.
Il costruttore e la validazione avvengono dopo selezione target e prima di
open/claim. Il **correttivo #2** host-only ha registrato su `GoodixFpiUsbBackend`
il callback `in_completed` per il re-arm condizionato della ricezione, rendendo
convergente il percorso sintetico e quello USB reale; la funzione
`goodix_device_context_complete_receive()` resta solo injection seam per
host/test. La regressione esercita `goodix_fpi_usb_backend_complete_receive()`
dal livello backend, dimostrando re-arm del secondo IN e avanzamento a A8.

La **micro-correttiva #3** corregge il resoconto storico, rende i messaggi
operatore in italiano con banner delimitati da `======================`,
monitora la `GoodixPostTlsPhase` reale per decidere quando richiedere
l'appoggio/ritiro del dito, e aggiunge la telemetria di stop limitata
(`observed_*`, `*_at_stop`, `stop_time_ms`) senza mai esporre PSK, OTP, CONFIG90,
FDT, immagini o nonce. La chiusura pre-live canonica esegue automaticamente la
prova host-only del prompt tracker.

Il terzo tentativo live, sulla baseline
`87c1bf89d0ba28497313f4bb75a8de4bbdb37b75`, ha ricevuto come primo frame un
A0/A2 typed-shaped con body di tre byte prima di qualunque ACK ed è terminato
fail-closed. L'hash del body non è stato registrato: il match con il pin A2 è
quindi `UNKNOWN`. È una forte ipotesi, non una prova, che il frame fosse il
typed A2 lasciato non letto dal tentativo #2, nel quale l'ACK era arrivato ma
non era stato sottomesso il secondo IN. Il router preserva l'ordine dei byte e
può estrarre più frame da una completion, quindi non emerge riordinamento
software.

Il **correttivo #4** separa esito STOP e terminale e rende esatto il formato
dei banner. Il **correttivo #5** era una tolleranza host-only per un solo typed
A2 pinned pre-ACK; non è mai stato validato live ed è ora
`SUPERSEDED_BEFORE_NEXT_LIVE`.

Il quarto tentativo, sulla baseline
`7ce15fa72d0806f34202d2603ef397a740453c63`, ha ricevuto prima un ACK A2
accettato e, sul secondo IN riarmato, un altro frame ACK A2 valido-shaped. È
terminato fail-closed in 158 ms come `ACK_SHAPE_MISMATCH`, prima di A8/TLS. La
sequenza tentativi #2–#4 sostiene fortemente un modello di residui RX tra
sessioni, ma non prova la provenienza esatta di alcun frame:

```text
attempt #2: ACK corrente letto; typed A2 non letto perché manca il secondo IN
attempt #3: primo IN typed-shaped pre-ACK; l'ACK corrente può restare non letto
attempt #4: primo IN ACK accettato; secondo IN secondo ACK valido-shaped
INTER_SESSION_RX_RESIDUE_OBSERVED_DIRECTLY=false
INTER_SESSION_RX_RESIDUE_MODEL=STRONG_HYPOTHESIS
NEW_OPEN_CLAIM_IMPLIES_EMPTY_RX=DISPROVEN_AS_SAFE_ASSUMPTION
BACKEND_DRAINED_IMPLIES_DEVICE_RX_EMPTY=false
```

Il **correttivo #6** sostituisce la tolleranza sintomatica con un confine
strutturale `PRE_SESSION_RX_SYNC` nello stesso `GoodixDeviceContext` e nello
stesso `GoodixFpiUsbBackend`. Dopo open/claim e inizio generation, il backend
mantiene un solo IN bulk temporizzato da 250 ms, mette in quarantena senza
parsing/log raw ogni completion non vuota e ri-arma entro 16 completion,
65536 byte e 2000 ms. Solo il timeout reale GUsb
`G_USB_DEVICE_ERROR_TIMED_OUT`, senza dati e con backend drenato, stabilisce il
quiet boundary. Errori diversi o limiti superati falliscono chiuso; ogni OUT e
lo start del secure-session sono vietati prima del PASS. Dopo il PASS torna
l'ordine strict `ACK -> typed A2 -> A8`; typed pre-ACK e ACK duplicato sono
terminali.

Lo stesso correttivo consolida il launcher tracciato: la preparazione
`--prepare-approved-live <FULL_SHA>` costruisce dallo snapshot Git approvato e
scrive una state con baseline/build/hash; `--run-approved-live <BUILD> --grant
<FILE>` valida state, HEAD, hash e grant, consuma atomicamente l'ID una sola
volta, crea un ticket runtime e usa il binario preparato senza rebuild. Il
vecchio `--live-integrated-once` diretto è chiuso. Nessun grant live è stato
creato e nessuna esecuzione live è autorizzata da questo correttivo.

Il **correttivo #6a** (host-only) indurisce il workflow operatore per
l'esecuzione reale sotto sudo: la root canonica viene determinata senza
invocare Git, quindi ogni chiamata Git del percorso di validazione usa
`-c safe.directory=<canonical-root>` senza configurazione globale; il grant
esterno è accettato se di proprietà di `SUDO_UID` (oltre a root/EUID) con
permessi `0600` o più restrittivi; il marker di grant consumato è spostato
sotto `/var/tmp/goodix-d278-14-consumed-grants` per sopravvivere al cleanup di
`/tmp` e a un reboot. La chiusura pre-live `--host-only-prelive` asserisce
tutti i marker corrispondenti.

```text
CONTROLLED_RISK_EXPLORATORY_RECOVERY_CANDIDATE=A2_SENSOR_ONLY_EXACT_01_14
OEM_RECOVERY_EQUIVALENCE=false
A2_RISK_PROBE_IMPLEMENTED=true
A2_RISK_PROBE_LIVE_CAPABLE=true
A2_RISK_PROBE_LIVE_EXECUTED=true
A2_SENSOR_ONLY_ACCEPTED_IN_CURRENT_CONTEXT=true
D278_09_ONE_SHOT_CONSUMED=true
D278_09_RERUN_AUTHORIZED=false
A2_A8_REENTRY_PROBE_IMPLEMENTED=true
A2_A8_REENTRY_PROBE_LIVE_CAPABLE=true
A2_A8_REENTRY_PROBE_LIVE_EXECUTED=true
D278_10_LIVE_OUTCOME=PASS
D278_10_ONE_SHOT_CONSUMED=true
D278_10_RERUN_AUTHORIZED=false
SAME_SESSION_A2_THEN_A8_APP12509_TARGET_PROVEN=true
A2_SENSOR_ONLY_REENTRY_RECOVERY_EFFECTIVE_FOR_A8_ON_CURRENT_TARGET_CONTEXT=true
PROJECT_REENTRY_RECOVERY_CANDIDATE=PROVEN_EFFECTIVE_FOR_A8_ON_CURRENT_TARGET_CONTEXT
A2_REENTRY_RECOVERY_CAUSAL_MECHANISM=UNKNOWN
REENTRY_RECOVERY_A2_OEM_EQUIVALENCE=false
REENTRY_RECOVERY_A2_PROJECT_POLICY=true
NATIVE_SECURE_SESSION_REENTRY_PREFIX_IMPLEMENTED=true
NATIVE_SECURE_SESSION_REENTRY_PREFIX_HOST_ONLY_PROVEN=true
D278_11_LIVE_OUTCOME=PASS
D278_11_ONE_SHOT_CONSUMED=true
D278_11_RERUN_AUTHORIZED=false
REENTRY_PREFIXED_NATIVE_SECURE_SESSION_TARGET_PROVEN=true
REENTRY_RECOVERY_A2_TO_TLS_TARGET_PROVEN=true
NATIVE_TLS12_PSK_HANDSHAKE_WITH_REENTRY_RECOVERY_TARGET_PROVEN=true
POST_TLS_TWO_ACQUISITION_NATIVE_C_INTEGRATION_IMPLEMENTED=true
REENTRY_PREFIXED_NATIVE_C_TO_SECOND_B0_HOST_ONLY_PROVEN=true
SAME_OPEN_EPOCH_USB_OWNER_HOST_ONLY_PROVEN=true
SAME_TLS_SESSION_THROUGH_SECOND_B0_HOST_ONLY_PROVEN=true
INTEGRATED_PATH_LIVE_CAPABLE_IMPLEMENTED=true
LIVE_CAPABLE_INTEGRATED_PATH_HOST_ONLY_PROVEN=true
SAME_GOODIX_DEVICE_CONTEXT=true
SINGLE_USB_BACKEND_OWNER=true
SINGLE_USB_ROUTER=true
SINGLE_PHYSICAL_IN_OWNER=true
SINGLE_TLS_OBJECT=true
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
REAL_PRODUCTION_SECRET_READ=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
LIVE_BASELINE_BINDING_GUARD_IMPLEMENTED=true
LIVE_BASELINE_BINDING_GUARD_HOST_ONLY_PROVEN=true
ONE_AUTHORIZATION_ONE_ATTEMPT_GUARD_IMPLEMENTED=true
ONE_AUTHORIZATION_ONE_ATTEMPT_GUARD_HOST_ONLY_PROVEN=true
SECOND_USE_OF_AUTHORIZATION_REJECTED=true
REAL_SUDO_GIT_SAFE_DIRECTORY_HOST_ONLY_PROVEN=true
SUDO_OPERATOR_OWNED_GRANT_ACCEPTED_HOST_ONLY=true
UNRELATED_GRANT_OWNER_REJECTED_HOST_ONLY=true
PERSISTENT_ONE_SHOT_GRANT_CLAIM_HOST_ONLY_PROVEN=true
GENERIC_BASELINE_BOUND_OPERATOR_WORKFLOW_HOST_ONLY_PROVEN=true
DIRECT_UNPREPARED_LIVE_PATH_REJECTED=true
PRE_SESSION_RX_SYNC_CORE_RETAINED=true
STRICT_A2_ACK_THEN_TYPED_RETAINED=true
D278_14_TOTAL_LIVE_ATTEMPTS=12
D278_14_TOTAL_CONSUMED_AUTHORIZATIONS=12
D278_14_HISTORY_CORRECTED=true
D278_14_ATTEMPT_1_BASELINE=2172e750ae7c100a3a891ba25d0797286230a4ab
D278_14_ATTEMPT_1_OUTCOME=FAIL_HOST_BINDING_BEFORE_PROTOCOL
D278_14_ATTEMPT_1_FIRST_FAILURE_BOUNDARY=FPDEVICE_USB_BINDING_CONSTRUCTION
D278_14_ATTEMPT_1_PROCESS_EXIT_CODE=134
D278_14_ATTEMPT_1_PROCESS_TERMINATION=SIGABRT
D278_14_ATTEMPT_1_A2_REACHED=false
D278_14_ATTEMPT_1_TLS_REACHED=false
D278_14_ATTEMPT_1_POST_TLS_REACHED=false
D278_14_ATTEMPT_1_CORE_DUMP_CREATED=OBSERVED
D278_14_ATTEMPT_1_AUTHORIZATION_CONSUMED=true
D278_14_ATTEMPT_2_BASELINE=fceae05d9ff3ed14348f9031706e70d5a808ff91
D278_14_ATTEMPT_2_BINARY_SHA256=de935e0a3fc89a345a2bad624ba3d218f51ab036597d13566d985efbada4f270
D278_14_ATTEMPT_2_OUTCOME=FAIL_RECEIVE_REARM_HOST_PLUMBING
D278_14_ATTEMPT_2_FAILURE_CLASS=ONE_SHOT_DEADLINE
D278_14_ATTEMPT_2_PHASE_TRACE=REENTRY_RECOVERY_A2>TERMINAL
D278_14_ATTEMPT_2_SECURE_COMMAND_COUNT=1
D278_14_ATTEMPT_2_ACK_COUNT=1
D278_14_ATTEMPT_2_TYPED_COUNT=0
D278_14_ATTEMPT_2_PHYSICAL_IN_SUBMIT_COUNT=1
D278_14_ATTEMPT_2_PHYSICAL_OUT_SUBMIT_COUNT=1
D278_14_ATTEMPT_2_REENTRY_A2_RESULT=FAIL_CLOSED
D278_14_ATTEMPT_2_A8_REACHED=false
D278_14_ATTEMPT_2_TLS_REACHED=false
D278_14_ATTEMPT_2_POST_TLS_REACHED=false
D278_14_ATTEMPT_2_FIRST_ACQUISITION_REACHED=false
D278_14_ATTEMPT_2_SECOND_ACQUISITION_REACHED=false
D278_14_ATTEMPT_2_USB_OPEN_COUNT=1
D278_14_ATTEMPT_2_USB_CLAIM_COUNT=1
D278_14_ATTEMPT_2_USB_RELEASE_COUNT=1
D278_14_ATTEMPT_2_USB_CLOSE_COUNT=1
D278_14_ATTEMPT_2_BACKEND_DRAINED=true
D278_14_ATTEMPT_2_CLEANUP_COMPLETE=true
D278_14_ATTEMPT_2_PROJECT_SECRET_ZEROIZED=true
D278_14_ATTEMPT_2_CORE_DUMP_LIMIT=0
D278_14_ATTEMPT_2_RETRY_COUNT=0
D278_14_ATTEMPT_2_REOPEN_COUNT=0
D278_14_ATTEMPT_2_DEVICE_RESET_COUNT=0
D278_14_ATTEMPT_2_CLEAR_HALT_COUNT=0
D278_14_ATTEMPT_2_PERSISTENT_DEVICE_WRITE_COUNT=0
D278_14_ATTEMPT_2_ROOT_CAUSE=REAL_USB_BACKEND_COMPLETION_BYPASSES_CONTEXT_RECEIVE_REARM_FOLLOWUP
D278_14_ATTEMPT_3_BASELINE=87c1bf89d0ba28497313f4bb75a8de4bbdb37b75
D278_14_ATTEMPT_3_BINARY_SHA256=346aadf64c49b6757c236a097264465ef4de130798aa82109056604930162d90
D278_14_ATTEMPT_3_OUTCOME=FAIL_PRE_ACK_TYPED_A2
D278_14_ATTEMPT_3_FAILURE_CLASS=INTEGRATED_PATH_TERMINAL
D278_14_ATTEMPT_3_PHASE_TRACE=REENTRY_RECOVERY_A2>TERMINAL
D278_14_ATTEMPT_3_SECURE_COMMAND_COUNT=1
D278_14_ATTEMPT_3_ACK_COUNT=0
D278_14_ATTEMPT_3_TYPED_COUNT=0
D278_14_ATTEMPT_3_PHYSICAL_IN_SUBMIT_COUNT=1
D278_14_ATTEMPT_3_PHYSICAL_OUT_SUBMIT_COUNT=1
D278_14_ATTEMPT_3_PHYSICAL_IN_COMPLETION_COUNT=1
D278_14_ATTEMPT_3_PHYSICAL_OUT_COMPLETION_COUNT=1
D278_14_ATTEMPT_3_PROTOCOL_FAILURE_KIND=TYPED_SHAPE_MISMATCH
D278_14_ATTEMPT_3_OBSERVED_OUTER_TYPE=0xA0
D278_14_ATTEMPT_3_OBSERVED_A0_CONTROL=0xA2
D278_14_ATTEMPT_3_OBSERVED_BODY_LENGTH=3
D278_14_ATTEMPT_3_OBSERVED_ACK_ECHO=UNAVAILABLE
D278_14_ATTEMPT_3_OBSERVED_ACK_STATUS=UNAVAILABLE
D278_14_ATTEMPT_3_A8_REACHED=false
D278_14_ATTEMPT_3_TLS_REACHED=false
D278_14_ATTEMPT_3_POST_TLS_REACHED=false
D278_14_ATTEMPT_3_STOP_TIME_MS=145
D278_14_ATTEMPT_3_BACKEND_DRAINED=true
D278_14_ATTEMPT_3_CLEANUP_COMPLETE=true
D278_14_ATTEMPT_3_PROJECT_SECRET_ZEROIZED=true
D278_14_ATTEMPT_3_RETRY_COUNT=0
D278_14_ATTEMPT_3_REOPEN_COUNT=0
D278_14_ATTEMPT_3_DEVICE_RESET_COUNT=0
D278_14_ATTEMPT_3_CLEAR_HALT_COUNT=0
D278_14_ATTEMPT_3_PERSISTENT_DEVICE_WRITE_COUNT=0
D278_14_ATTEMPT_3_CORE_DUMP_LIMIT=0
D278_14_ATTEMPT_4_BASELINE=7ce15fa72d0806f34202d2603ef397a740453c63
D278_14_ATTEMPT_4_BINARY_SHA256=01f6e3ff9cc023ade55d69f94108d8546d0ee321b90475aa43b1128f6255089e
D278_14_ATTEMPT_4_OUTCOME=FAIL_DUPLICATE_A2_ACK_AFTER_REARM
D278_14_ATTEMPT_4_FAILURE_CLASS=INTEGRATED_PATH_TERMINAL
D278_14_ATTEMPT_4_PHASE_TRACE=REENTRY_RECOVERY_A2>TERMINAL
D278_14_ATTEMPT_4_SECURE_COMMAND_COUNT=1
D278_14_ATTEMPT_4_ACK_COUNT=1
D278_14_ATTEMPT_4_TYPED_COUNT=0
D278_14_ATTEMPT_4_PHYSICAL_SUBMIT_COUNT=3
D278_14_ATTEMPT_4_PHYSICAL_IN_SUBMIT_COUNT=2
D278_14_ATTEMPT_4_PHYSICAL_OUT_SUBMIT_COUNT=1
D278_14_ATTEMPT_4_PHYSICAL_IN_COMPLETION_COUNT=2
D278_14_ATTEMPT_4_PHYSICAL_OUT_COMPLETION_COUNT=1
D278_14_ATTEMPT_4_PROTOCOL_FAILURE_KIND=ACK_SHAPE_MISMATCH
D278_14_ATTEMPT_4_OBSERVED_OUTER_TYPE=0xA0
D278_14_ATTEMPT_4_OBSERVED_A0_CONTROL=0xB0
D278_14_ATTEMPT_4_OBSERVED_ACK_ECHO=0xA2
D278_14_ATTEMPT_4_OBSERVED_ACK_STATUS=0x01
D278_14_ATTEMPT_4_OBSERVED_BODY_LENGTH=2
D278_14_ATTEMPT_4_REENTRY_PRE_ACK_TYPED_OBSERVED=false
D278_14_ATTEMPT_4_REENTRY_PRE_ACK_TYPED_DISCARD_COUNT=0
D278_14_ATTEMPT_4_A8_REACHED=false
D278_14_ATTEMPT_4_TLS_REACHED=false
D278_14_ATTEMPT_4_POST_TLS_REACHED=false
D278_14_ATTEMPT_4_STOP_TIME_MS=158
D278_14_ATTEMPT_4_BACKEND_DRAINED=true
D278_14_ATTEMPT_4_CLEANUP_COMPLETE=true
D278_14_ATTEMPT_4_PROJECT_SECRET_ZEROIZED=true
D278_14_ATTEMPT_4_RETRY_COUNT=0
D278_14_ATTEMPT_4_REOPEN_COUNT=0
D278_14_ATTEMPT_4_DEVICE_RESET_COUNT=0
D278_14_ATTEMPT_4_CLEAR_HALT_COUNT=0
D278_14_ATTEMPT_4_PERSISTENT_DEVICE_WRITE_COUNT=0
D278_14_ATTEMPT_4_CORE_DUMP_LIMIT=0
INTER_SESSION_RX_RESIDUE_OBSERVED_DIRECTLY=false
INTER_SESSION_RX_RESIDUE_MODEL=STRONG_HYPOTHESIS
NEW_OPEN_CLAIM_IMPLIES_EMPTY_RX=DISPROVEN_AS_SAFE_ASSUMPTION
BACKEND_DRAINED_IMPLIES_DEVICE_RX_EMPTY=false
PRE_ACK_TYPED_A2_OBSERVED=true
PRE_ACK_TYPED_A2_PIN_MATCH=UNKNOWN
STALE_TYPED_FROM_ATTEMPT_2=STRONG_HYPOTHESIS_NOT_PROVEN
D278_14_CORRECTIVE_1=FPDEVICE_USB_BINDING_CONSTRUCTION
D278_14_CORRECTIVE_1_BASELINE=fceae05d9ff3ed14348f9031706e70d5a808ff91
D278_14_CORRECTIVE_1_OUTCOME=PASS_HOST_ONLY
D278_14_CORRECTIVE_2=IN_COMPLETION_REARM_UNIFICATION
D278_14_CORRECTIVE_2_BASELINE=fceae05d9ff3ed14348f9031706e70d5a808ff91
D278_14_CORRECTIVE_2_OUTCOME=PASS_HOST_ONLY
D278_14_CORRECTIVE_2_ROOT_CAUSE=REAL_USB_BACKEND_COMPLETION_BYPASSES_CONTEXT_RECEIVE_REARM_FOLLOWUP
D278_14_CORRECTIVE_2_FIX=IN_COMPLETED_CALLBACK_UNIFIES_REAL_AND_SYNTHETIC_PATHS
CORE_IN_REARM_CORRECTIVE_RETAINED=true
D278_14_CORRECTIVE_5_STATUS=SUPERSEDED_BEFORE_NEXT_LIVE
D278_14_CORRECTIVE_5_LIVE_VALIDATION_PERFORMED=false
CORRECTIVE_5_RUNTIME_TOLERANCE_RETIRED=true
STRICT_A2_ACK_THEN_TYPED_RESTORED=true
PRE_SESSION_RX_SYNC_IMPLEMENTED=true
PRE_SESSION_RX_CLEAN_QUIET_BOUNDARY_HOST_ONLY_PROVEN=true
PRE_SESSION_RX_RESIDUE_CHAIN_QUARANTINED_HOST_ONLY_PROVEN=true
PRE_SESSION_RX_MULTI_FRAME_COMPLETION_QUARANTINED_HOST_ONLY_PROVEN=true
PRE_SESSION_RX_NON_TIMEOUT_ERROR_FAIL_CLOSED=true
PRE_SESSION_RX_BOUNDS_FAIL_CLOSED=true
PRE_SESSION_RX_OUT_BEFORE_SYNC_REJECTED=true
PRE_SESSION_RX_SECURE_START_BEFORE_SYNC_REJECTED=true
NO_PARALLEL_RX_DRAIN_STACK=true
GENERIC_BASELINE_BOUND_OPERATOR_WORKFLOW_HOST_ONLY_PROVEN=true
DIRECT_UNPREPARED_LIVE_PATH_REJECTED=true
SYNTHETIC_AND_REAL_IN_COMPLETION_FOLLOWUP_UNIFIED=true
BACKEND_LEVEL_A2_ACK_COMPLETION_REARMS_NEXT_IN=true
BACKEND_LEVEL_A2_TYPED_COMPLETION_ADVANCES_TO_A8=true
FPDEVICE_USB_BINDING_CORRECTED=true
FPDEVICE_TRANSPORT_TYPE_USB_COMPATIBLE=true
NON_NULL_GUSBDEVICE_FPDEVICE_BINDING_HOST_ONLY_PROVEN=true
PHYSICAL_CONSTRUCTOR_BEFORE_USB_OPEN_CLAIM=true
FPDEVICE_USB_BINDING_CONSTRUCTION_HOST_ONLY=PASS
OPERATOR_MESSAGES_LANGUAGE=ITALIAN
OPERATOR_ACTION_BANNERS_IMPLEMENTED=true
OPERATOR_PROMPTS_RUNTIME_STATE_DRIVEN=true
OPERATOR_PROMPT_SEQUENCE_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_SUCCESS_FAILURE_EXCLUSIVE=true
OPERATOR_PROMPT_DUPLICATE_SUPPRESSION_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_STOP_THEN_TERMINAL_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_TERMINAL_THEN_STOP_HOST_ONLY_PROVEN=true
OPERATOR_ACTION_BANNER_FORMAT_EXACT=true
OPERATOR_ACTION_BANNER_MACHINE_PREFIX=false
OPERATOR_PROMPT_PRELIVE_GATED=true
BOUNDED_STOP_TELEMETRY_COMPLETE=true
SENSITIVE_TELEMETRY_EXPOSURE=false
NO_PARALLEL_STACK=true
MAX_PHYSICAL_IN_OUTSTANDING=1
RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
REAL_USB_ACCESS=false
REAL_USB_SUBMIT=0
REAL_PRODUCTION_SECRET_READ=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
```

Sul target APP12509 (firmware `GF_ST411SEC_APP_12509`) risultano ora **chiusi
live** i seguenti confini:

```text
A8
exact A2 sensor-only nel current re-entry context
E4
TLS 1.2 PSK
D4
AF
bounded fresh-FDT arm path
IRQ2
0x22
ACK 0x22
first B0
first image decode
raster 80x64
IRQ 0x0200 dopo 0x34
post-up 0x20
post-up B0 / NAV 0x50
re-arm 0x32 con down-table derivata
secondo IRQ2
secondo 0x22
ACK 0x22 secondo ciclo
secondo B0
STOP_AFTER_SECOND_IMAGE
```

Evidenza target-specific live già consolidata:

```text
IMAGE_0X88_NO_CHECK_TARGET_PROVEN=true
IMAGE_RECORD_CRC_LIVE_PROVEN=true
FIRST_IMAGE_DECODE_LIVE_PROVEN=true
FIRST_IMAGE_RECEIVED=true
D267_01_CAUSE=STRONG_CAUSAL_INFERENCE
D268_RETRY_AUTHORIZED=false
LINUX_FIRST_IMAGE_LIVE_OBSERVED=true
LINUX_IRQ0200_AFTER_0X34=OBSERVED
LINUX_SECOND_IRQ0002=OBSERVED
LINUX_SECOND_0X22=OBSERVED
LINUX_SECOND_B0_LIVE_OBSERVED=true
STOP_AFTER_SECOND_IMAGE_LIVE=PASS
FDT_TABLE_MISMATCH_CAUSALITY=LIVE_VALIDATED
TARGET_DEVICE_TIMEOUT=UNKNOWN
LIVE_AUTHORIZED=false
PERSISTENT_DEVICE_WRITE_COUNT=0
HOST_CACHE_WRITE_COUNT=0
RETRY_COUNT=0
TRANSPORT_REOPEN_AFTER_TLS=false
USB_TRANSPORT_SESSION_COUNT=1
TLS_SERVER_HANDSHAKE_COUNT=1
SECRET_BOUNDARY_HANDOFF_COUNT=1
PRESERVED_D275_COUNTER_SCOPE=ONE_BOUNDED_RUN_TO_SECOND_B0_NOT_CROSS_ACTIVATION_POLICY

LIVE_EVIDENCE_CONSOLIDATED_IN_REPOSITORY=true
CANONICAL_REPOSITORY_EVIDENCE_RECORD=analysis/D275/D275_04_second_b0_live_closure.json
HOST_MACHINE_REPORT_PATH=/var/lib/goodix-5125-poc/d261-results/d275-second-b0-final.json
RAW_D275_POST_CORRECTIVE_REPORT_VERSIONED=false
CANONICAL_PRIVATE_RAW_EVIDENCE_ROOT=captures/

D277_02_LIVE_RESULT=PASS
NATIVE_FPI_USB_A8_PATH_TARGET_PROVEN=true
NATIVE_FPI_USB_A0_ROUTER_TARGET_PROVEN=true
APP12509_NATIVE_IDENTITY_REVALIDATED=true
TLS_NOT_EXERCISED=true
E4_NOT_EXERCISED=true
FINGER_PATH_NOT_EXERCISED=true
IMAGE_PATH_NOT_EXERCISED=true

D278_01_INITIAL_IMPLEMENTATION_HOST_ONLY=PASS
D278_01_INITIAL_IMPLEMENTATION_COMMIT=0efa30f681e0a3aa284565ce581536ad00606c39
D278_01_INITIAL_IMPLEMENTATION_CI_RUN=33237274978
D278_01_INITIAL_IMPLEMENTATION_CI_RESULT=PASS
D278_01_D1_TLS_GATE_CORRECTIVE_COMMIT=5030c66e67db5a7f6cedfbf3bb0deeec107e79db
D278_01_D1_TLS_GATE_AI_PM_REVIEW=PASS
D278_01_D1_TLS_GATE_CI=PASS
D278_01_D1_TLS_GATE_CI_RUN=33239781874
D278_01_D1_TLS_GATE_MERGED_MAIN=52e190b2ceaee0e8de618accd4da9fadbad54115
NATIVE_SECURE_SESSION_CHAIN_HOST_ONLY_PROVEN=true
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
NATIVE_PRE_D1_SEQUENCE_HOST_ONLY_PROVEN=true
NATIVE_D1_B0_TLS_TRANSITION_HOST_ONLY_PROVEN=true
NATIVE_TLS12_PSK_HANDSHAKE_HOST_ONLY_PROVEN=true
NATIVE_B0_FIXED64_EGRESS_HOST_ONLY_PROVEN=true
NATIVE_TLS_RECORD_PACING_HOST_ONLY_PROVEN=true

D278_02_OUTCOME=READY
D278_02_ADVANCEMENT=REAL_EXECUTION_COMPLETED_AUTHENTIC_PROTECTED_MATERIAL_PREFLIGHT_WITH_E4_BINDING_MATCH_AND_ZERO_USB_ACCESS
D190_EXPRESSION_PROVENANCE_GATE=PASS
NATIVE_D190_E4_BINDER_KAT_PROVEN=true
D190_FIVE_INDEPENDENT_KATS=PASS
PE_CANONICAL_HASH_GATE=PASS
DLL_LOADED_OR_EXECUTED=false
NATIVE_PROTECTED_MATERIAL_LOADER_HOST_ONLY_PROVEN=true
PROTECTED_MATERIAL_NEGATIVE_MATRIX=PASS
PRODUCTION_MATERIAL_POLICY_UID=0
PRODUCTION_MATERIAL_POLICY_MODE=0600
PROJECT_OWNED_ZEROIZATION=PROVEN_TO_IMPLEMENTATION_BOUNDARY
OPENSSL_INTERNAL_ZEROIZATION_ASSERTED=false
E4_DERIVED_FROM_SAME_PSK_AS_TLS=true
D278_02_LIVE_CAPABLE_HARNESS_IMPLEMENTED=true
D278_02_LIVE_HARNESS_BUILD=PASS
D278_02_LIVE_HARNESS_EXECUTED=false
D278_02_PHASE_WATCHDOG_HOST_ONLY_PROVEN=true
D278_02_NORMAL=PASS
D278_02_ASAN_UBSAN=PASS
D278_02_DETERMINISM_RUNS=2
D278_02_TEST_COUNT_PER_BINARY_RUN=62
PRODUCTION_POLICY_CANONICAL_PIN_MATRIX=PASS
AI_PM_INITIAL_REVIEW=FAIL_CORRECTIVE_REQUIRED
INITIAL_REVIEW_BLOCKER=CANONICAL_A2_RESPONSE_SHA256_PRODUCTION_PIN_MISMATCH
CANONICAL_A2_SHA256_EXPECTED=39e469ce5a5ba3136c4a44381f2e4183dca275257adfcf3c0025094f05c022f5
CANONICAL_A2_SHA256_IMPLEMENTED_AFTER_FIX=39e469ce5a5ba3136c4a44381f2e4183dca275257adfcf3c0025094f05c022f5
D278_02_CANONICAL_A2_CORRECTIVE_AI_PM_REVIEW=PASS
AI_PM_REVIEWED_MAIN_BASELINE=01b2379395b59219112236a6387bee9e5bd47bbf
CORRECTIVE_CI_RUN=33252621869
CORRECTIVE_CI=PASS
PROTECTED_PREFLIGHT_FAILURE_OBSERVABILITY=PASS
PROTECTED_PREFLIGHT_REDACTION=PASS
NO_SECRET_BYTES_IN_FAILURE_TELEMETRY=PASS
D278_02_MICRO_CORRECTIVE_AI_PM_REVIEW=PASS
D278_02_MICRO_CORRECTIVE_MERGED_MAIN=1d25abc7b4a99ea1719cc4381d6f780501483209
D278_02_POST_MERGE_CI_RUN=33255017404
D278_02_POST_MERGE_CI=PASS
D278_02_NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_THEN_EXPLICITLY_AUTHORIZED_SINGLE_SHOT_NATIVE_TARGET_SECURE_SESSION
TARGET_PROTECTED_MATERIAL_PREFLIGHT_EXECUTED=true
TARGET_PROTECTED_MATERIAL_PREFLIGHT=PASS
TARGET_E4_BINDING_PREFLIGHT=PASS
TARGET_MATERIAL_PREFLIGHT_FAILURE_STAGE=NONE
TARGET_MATERIAL_PREFLIGHT_FAILURE_CLASS=none
TARGET_MATERIAL_PREFLIGHT_RC=0
TARGET_MATERIAL_PREFLIGHT_REAL_USB_ACCESS=0
TARGET_MATERIAL_PREFLIGHT_USB_OPEN_COUNT=0
TARGET_MATERIAL_PREFLIGHT_USB_CLAIM_COUNT=0
TARGET_MATERIAL_PREFLIGHT_REAL_USB_SUBMIT_COUNT=0
TARGET_MATERIAL_PREFLIGHT_RETRY_COUNT=0
TARGET_MATERIAL_PREFLIGHT_DEVICE_RESET_COUNT=0
TARGET_MATERIAL_PREFLIGHT_PERSISTENT_DEVICE_WRITE_COUNT=0
TARGET_MATERIAL_PREFLIGHT_PROJECT_SECRET_ZEROIZED=true
TARGET_E4_NATIVE_LIVE_PROVEN=false
TARGET_TLS_NATIVE_LIVE_PROVEN=false
D278_02_LIVE_EXECUTION_PERFORMED=false
D278_02_D4_REACHABLE=false
D278_02_REAL_USB_ACCESS=0
D278_02_REAL_USB_SUBMIT=0
D278_02_APPLICATION_DATA_COUNT=0

D278_03_BASELINE_HEAD=843290e7790d7930bb136d91510a3db9d3a97027
AI_PM_STATIC_PRELIVE_REVIEW=PASS
D278_03_PRELIVE_EXISTING_LAUNCHER_SUFFICIENT=true
D278_03_PRELIVE_LIVE_CRITICAL_CODE_CHANGE_REQUIRED=false
D278_03_PRELIVE_EXECUTION_ENVIRONMENT=OPERATOR_FEDORA_HOST
D278_03_EXECUTABLE_CLOSURE=PASS_HOST_ONLY
D278_03_D278_02_RUNNER=PASS
D278_03_D278_01_D1_TLS_RUNNER=PASS
D278_03_PRELIVE_LAUNCHER_SHA256=a48488b0817256d896a77bf2ac037ff5bef10524dd9c018f31d1c2bb5d3a251a
D278_03_PRELIVE_OPERATOR_PROCEDURE_PREPARED=true
D278_03_PRELIVE_OPERATOR_STOP_GATE_PRESENT=true
D278_03_LIVE_EXECUTION_PERFORMED=true
D278_03_LIVE_RUN_COUNT=1  # prima single-shot; la seconda è tracciata dai marker D278_03_SECOND_SINGLE_SHOT_*
D278_03_LIVE_RUN_COUNT_TOTAL=2
D278_03_LIVE_RESULT=FAIL_E4_PROTOCOL_GATE
D278_03_LIVE_AUTHORIZATION_CONSUMED=true
D278_03_A8_NATIVE_LIVE=PASS
D278_03_E4_OUT_NATIVE_LIVE=SENT
D278_03_E4_ACCEPTED_ACK=false
D278_03_TLS_REACHED=false
D278_03_USB_OPEN_COUNT=1
D278_03_USB_CLAIM_COUNT=1
D278_03_USB_RELEASE_COUNT=1
D278_03_USB_CLOSE_COUNT=1
D278_03_RETRY_COUNT=0
D278_03_TRANSPORT_REOPEN_COUNT=0
D278_03_DEVICE_RESET_COUNT=0
D278_03_PERSISTENT_DEVICE_WRITE_COUNT=0
D278_03_PROJECT_SECRET_ZEROIZED=true
D278_03_BACKEND_DRAINED=true
D278_03_TERMINAL_CLEANUP_COMPLETED=true
D278_03_NATIVE_ACK_POLICY_CORRECTIVE_REQUIRED=true
D278_03_ACK_POLICY_AUTHORITY=D238
D278_03_ACK_POLICY_CORRECTIVE_HOST_ONLY=PASS
CURRENT_RUN_E4_ACK_07_NOT_DIRECTLY_TELEMETRIZED=true
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
TARGET_E4_NATIVE_LIVE_PROVEN=false
TARGET_TLS_NATIVE_LIVE_PROVEN=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
D278_03_ACK_POLICY_CORRECTIVE_AI_PM_REVIEW=PASS
D278_03_POST_CORRECTIVE_BASELINE=4e5d74770bce6e0a9de929b19279038827abff8c
D278_03_POST_CORRECTIVE_EXECUTABLE_CLOSURE=PASS_HOST_ONLY
D278_03_POST_CORRECTIVE_LAUNCHER_SHA256=bf7a1b0dae42d1c17b613c3f03338d10c3448be622e8bc46383f1923f56f192d
D278_03_PRE_CORRECTIVE_LAUNCHER_RETIRED=true
D278_03_POST_CORRECTIVE_TEST_RUNTIME=FREEDESKTOP_SDK_25_08
D278_03_POST_CORRECTIVE_ARTIFACT_STORAGE=OPERATOR_FEDORA_HOST_TMP
D278_03_POST_CORRECTIVE_LOCAL_ARTIFACT_VERIFICATION=PASS
D278_03_POST_CORRECTIVE_BUILD_EXISTS=true
D278_03_POST_CORRECTIVE_LAUNCHER_EXISTS=true
D278_03_POST_CORRECTIVE_D278_02_LOG_EXISTS=true
D278_03_POST_CORRECTIVE_FOCUSED_LOG_EXISTS=true
D278_03_POST_CORRECTIVE_LOG_CONTENT_AI_PM_REVIEW=PASS
D278_03_POST_CORRECTIVE_LAUNCHER_SHA256_LOCAL_VERIFIED=bf7a1b0dae42d1c17b613c3f03338d10c3448be622e8bc46383f1923f56f192d
D278_03_POST_CORRECTIVE_HOST_NATIVE_LAUNCHER_CHECK=PASS
D278_03_POST_CORRECTIVE_HOST_NATIVE_LDD=PASS
D278_03_POST_CORRECTIVE_HOST_NATIVE_SELF_TEST=PASS
D278_03_POST_CORRECTIVE_HOST_NATIVE_SELF_TEST_RC=0
D278_03_POST_CORRECTIVE_HOST_NATIVE_SELF_TEST_REAL_USB_ACCESS=0
D278_03_SECOND_SINGLE_SHOT_AUTHORIZED_AND_EXECUTED=true
D278_03_SECOND_SINGLE_SHOT_RUN_COUNT=1
D278_03_SECOND_SINGLE_SHOT_REPOSITORY_HEAD_AT_AUTHORIZATION=5fbbe3f37d09d2b9f41e4a3906a2a759e8122f21
D278_03_SECOND_SINGLE_SHOT_LIVE_CRITICAL_BASELINE=4e5d74770bce6e0a9de929b19279038827abff8c
D278_03_SECOND_SINGLE_SHOT_LAUNCHER_SHA256=bf7a1b0dae42d1c17b613c3f03338d10c3448be622e8bc46383f1923f56f192d
D278_03_SECOND_SINGLE_SHOT_LIVE_RC=1
D278_03_SECOND_SINGLE_SHOT_LIVE_LOG=/tmp/d278_03_native_secure_session_second_single_shot_20260829.log
D278_03_SECOND_SINGLE_SHOT_LIVE_LOG_SHA256=647b3c21f6954440fa29e54d6d31c29647d4d8434d08bc46f73dae1d8c553c5a
D278_03_SECOND_SINGLE_SHOT_RESULT=FAIL_SECURE_SESSION_TERMINAL_AT_A8
D278_03_SECOND_SINGLE_SHOT_PHASE_TRACE=A8,TERMINAL
D278_03_SECOND_SINGLE_SHOT_COMMAND_COUNT=1
D278_03_SECOND_SINGLE_SHOT_ACK_COUNT=0
D278_03_SECOND_SINGLE_SHOT_TYPED_RESPONSE_COUNT=0
D278_03_SECOND_SINGLE_SHOT_PROTOCOL_FAILURE_PHASE=A8
D278_03_SECOND_SINGLE_SHOT_PROTOCOL_FAILURE_KIND=TYPED_SHAPE_MISMATCH
D278_03_SECOND_SINGLE_SHOT_OBSERVED_OUTER_TYPE=160
D278_03_SECOND_SINGLE_SHOT_OBSERVED_A0_CONTROL=228
D278_03_SECOND_SINGLE_SHOT_OBSERVED_BODY_LENGTH=41
D278_03_SECOND_SINGLE_SHOT_LOCAL_E4_BINDING_MATCH=true
D278_03_SECOND_SINGLE_SHOT_LIVE_E4_TYPED_MATCH=NOT_REACHED
D278_03_SECOND_SINGLE_SHOT_TLS_ESTABLISHED=false
D278_03_SECOND_SINGLE_SHOT_D4_REACHABLE=false
D278_03_SECOND_SINGLE_SHOT_RETRY_COUNT=0
D278_03_SECOND_SINGLE_SHOT_TRANSPORT_REOPEN_COUNT=0
D278_03_SECOND_SINGLE_SHOT_DEVICE_RESET_COUNT=0
D278_03_SECOND_SINGLE_SHOT_PERSISTENT_DEVICE_WRITE_COUNT=0
D278_03_SECOND_SINGLE_SHOT_PROJECT_SECRET_ZEROIZED=true
D278_03_SECOND_SINGLE_SHOT_BACKEND_DRAINED=true
D278_03_SECOND_SINGLE_SHOT_TERMINAL_CLEANUP_COMPLETED=true
D278_03_SECOND_SINGLE_SHOT_LIVE_AUTHORIZATION_CONSUMED=true
D278_03_SECOND_SINGLE_SHOT_DO_NOT_RUN_AGAIN=true
D278_04_OUTCOME=READY_FOR_AI_PM_REVIEW
D278_04_ADVANCEMENT=ARCHITECTURAL_BOUNDARY_PROVEN_AND_TARGET_REENTRY_PHENOMENON_OBSERVED
HOST_ASYNC_TRANSFER_DRAIN=PROVEN_HOST_ONLY
CROSS_SESSION_FRAME_PROVENANCE=ABSENT_AS_HOST_GUARANTEE
DEVICE_PROTOCOL_QUIESCENCE=UNRESOLVED
PRE_A8_REENTRY_SYNCHRONIZATION=UNRESOLVED
CROSS_SESSION_REENTRY_ARCHITECTURAL_GAP=PROVEN
TARGET_UNEXPECTED_PRIOR_PHASE_SHAPE_AT_REENTRY=OBSERVED
OBSERVED_REENTRY_FRAME_OUTER=0xA0
OBSERVED_REENTRY_FRAME_CONTROL=0xE4
OBSERVED_REENTRY_FRAME_BODY_LENGTH=41
OBSERVED_REENTRY_FRAME_MATCHES_CANONICAL_E4_CONTROL_AND_LENGTH=true
CROSS_SESSION_RX_RESIDUAL_TARGET_HYPOTHESIS=STRONGLY_LIVE_CORROBORATED
CROSS_SESSION_RX_RESIDUAL_CAUSAL_IDENTITY=UNPROVEN
H6_CROSS_SESSION_RX_RESIDUAL_CURRENT_EXPLANATION=STRONGLY_LIVE_CORROBORATED_CAUSAL_IDENTITY_UNPROVEN
ACK_POLICY_CORRECTIVE_REFUTED=false
ACK_POLICY_CORRECTIVE_LIVE_RETESTED=false
SAFE_READ_ONLY_RESYNC_DESIGN=NOT_IMPLEMENTED_DESIGN_REVIEW_REQUIRED
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
D278_05_OUTCOME=READY
D278_05_EXECUTABLE_CLOSURE=PASS_HOST_ONLY
D278_05_AI_PM_CORRECTIVE_REQUIRED=RESOLVED
POST_A8_WIRE_CAUSAL_PROVENANCE=UNAVAILABLE
PRECOMMAND_FRAME_EXCLUDES_CURRENT_HOST_COMMAND_CAUSATION=true
PRECOMMAND_FRAME_PREVIOUS_SESSION_IDENTITY=UNPROVEN
OEM_PRE_D1_FAILURE_RECOVERY=UNRESOLVED
POISON_AFTER_NONQUIESCENT_TERMINAL_MUST_BE_STICKY=true
AUTOMATIC_REENTRY_FROM_POISONED=false
ACTIVATING_CANCEL_NONQUIESCENT_POISONS_OPEN_EPOCH=true
ACTIVATING_CANCEL_FRAMEWORK_ERROR=G_IO_ERROR_CANCELLED
ACTIVATION_COMPLETION_EXACTLY_ONCE=PASS
SECOND_ACTIVATION_FROM_POISONED_REJECTED=PASS
NEW_GENERATION_AFTER_POISON_COUNT=0
NEW_BACKEND_COMMAND_AFTER_POISON_COUNT=0
NEW_REAL_USB_SUBMIT_AFTER_POISON_COUNT=0
FUTURE_ZERO_OUT_PRECOMMAND_DIAGNOSTIC=JUSTIFIED_FOR_SEPARATE_REVIEW
D278_05_ZERO_OUT_DIAGNOSTIC_IMPLEMENTED=false
D278_06_OUTCOME=READY
D278_06_EXECUTABLE_CLOSURE=PASS_HOST_ONLY
D278_06_ZERO_OUT_OBSERVER_IMPLEMENTED=true
D278_06_LIVE_CAPABLE_LAUNCHER_IMPLEMENTED=true
D278_06_LIVE_CAPABLE_LAUNCHER_EXECUTED=true
D278_06_LIVE_EXECUTION_PERFORMED=true
D278_06_LIVE_EXECUTION_COUNT=1
D278_06_LIVE_BASELINE=1682e01bcc2817f5a0b5028ab6bf4bcac32a61d0
D278_06_LIVE_OUTCOME=VALID_SINGLE_SHOT_TIMEOUT_NO_DATA
D278_06_HYPOTHESIS_RESULT=NO_PRECOMMAND_DATA_OBSERVED_WITHIN_1000MS
D278_06_PHYSICAL_BULK_IN_SUBMIT_COUNT=1
D278_06_PHYSICAL_BULK_IN_COMPLETION_COUNT=1
D278_06_RECEIVED_BYTE_COUNT=0
D278_06_GOODIX_BULK_OUT_SUBMIT_COUNT=0
D278_06_GOODIX_COMMAND_COUNT=0
D278_06_TLS_HANDSHAKE_COUNT=0
D278_06_COMPLETION_CLASS=TIMEOUT_NO_COMPLETE_DATA
D278_06_TIMEOUT_COUNT=1
D278_06_FRAME_CLASS=NOT_OBSERVED
D278_06_USB_OPEN_COUNT=1
D278_06_USB_CLAIM_COUNT=1
D278_06_USB_RELEASE_COUNT=1
D278_06_USB_CLOSE_COUNT=1
D278_06_BACKEND_DRAINED=true
D278_06_CLEANUP_COMPLETED=true
D278_06_RETRY_COUNT=0
D278_06_REOPEN_COUNT=0
D278_06_DEVICE_RESET_COUNT=0
D278_06_CLEAR_HALT_COUNT=0
D278_06_PERSISTENT_DEVICE_WRITE_COUNT=0
D278_06_GOODIX_BULK_OUT_SUBMIT_MAX=0
D278_06_PHYSICAL_BULK_IN_SUBMIT_MAX=1
D278_06_PHYSICAL_BULK_IN_COMPLETION_MAX=1
D278_06_SECOND_RECEIVE_PATH_PRESENT=false
D278_06_CURRENT_HOST_DESCRIPTOR_GATE=EXACTLY_ONE_27C6_5125
D278_06_PRIOR_TARGET_FIRMWARE_PROOF=D277_02_APP12509
D278_06_CURRENT_APP12509_FIRMWARE_READBACK=NOT_PERFORMED_CAUSAL_CUT
D278_06_FUTURE_SINGLE_SHOT_ZERO_OUT_LIVE_READY_FOR_AI_PM_REVIEW=false
D278_06_CURRENT_LIVE_AUTHORIZED=false
D278_06_READY_FOR_LIVE=false
D278_06_RETRY_AUTHORIZED=false
D278_06_DO_NOT_RUN_EQUIVALENT_OBSERVATION_AGAIN=true
IMMEDIATE_PRECOMMAND_BACKLOG_WITHIN_1000MS=NOT_OBSERVED
DEVICE_PROTOCOL_QUIESCENCE_PROVEN=false
APP12509_READY_FOR_A8_PROVEN=false

D278_07_OUTCOME=BLOCKED
D278_07_ADVANCEMENT=NEW_STATIC_TARGET_SPECIFIC_A8_FAILURE_POLICY_CLOSED_AND_E4_TARGET_EDGE_ISOLATED_AS_THE_REMAINING_BOUNDARY
D278_07_EXECUTABLE_CLOSURE=ANALYSIS_ONLY
OEM_PRE_D1_FAILURE_RECOVERY=UNRESOLVED
OEM_A8_FAILURE_POLICY=RESOLVED
OEM_E4_FAILURE_POLICY=UNRESOLVED
OEM_USES_A2_SENSOR_ONLY_AS_PRE_A8_FAILURE_RECOVERY=false
A2_HOST_SEMANTICS=CONVERGED_SENSOR_ONLY_RESET
A2_PRE_A8_RECOVERY_LIVE_JUSTIFIED=false
D278_07_RECOVERY_CANDIDATE_IMPLEMENTED_HOST_ONLY=false
D278_07_REAL_USB_ACCESS=false
D278_07_LIVE_EXECUTION_PERFORMED=false
D278_07_CURRENT_LIVE_AUTHORIZED=false
D278_07_READY_FOR_LIVE=false
D278_07_RETRY_AUTHORIZED=false

D278_08_OUTCOME=READY
D278_08_ADVANCEMENT=NEW_STATIC_TARGET_SPECIFIC_DIRECT_E4_EDGE_AND_PERSISTENT_PROVISIONING_FAILURE_FALLBACK_RESOLVED
D278_08_EXECUTABLE_CLOSURE=ANALYSIS_ONLY
D278_08_BASELINE=4c73dcdaad5df9f9a429626109a4be2a3b1a8b19
OEM_PRE_D1_FAILURE_RECOVERY=RESOLVED
OEM_A8_FAILURE_POLICY=RESOLVED
OEM_E4_FAILURE_POLICY=RESOLVED
OEM_USES_A2_SENSOR_ONLY_AS_PRE_A8_FAILURE_RECOVERY=false
A2_PRE_A8_RECOVERY_LIVE_JUSTIFIED=false
A8_RETRY_BOUND_RUNTIME_VALUE=UNKNOWN_CONFIG_BYTE_AT_OFFSET_0x45A
PROJECT8_E4_SENDER_RESOLVED=true
PROJECT8_E4_INDIRECT_EDGE_RESOLVED=true
PROJECT8_E4_FAILURE_RETURN_PROPAGATION_RESOLVED=true
PROJECT8_E4_RETRY_BOUND_RESOLVED=true
PROJECT8_E4_PRE_FAILURE_PERSISTENT_WRITE_REACHABLE=true
PROJECT8_E4_POST_FAILURE_PERSISTENT_WRITE_REACHABLE=true
PROJECT8_E4_FAILURE_PATH_FACTORY_PRESERVING=false
LINUX_SAFE_E4_RECOVERY_CANDIDATE=false
D278_08_REAL_USB_ACCESS=false
D278_08_LIVE_EXECUTION_PERFORMED=false
D278_08_CURRENT_LIVE_AUTHORIZED=false
D278_08_READY_FOR_LIVE=false
D278_08_RETRY_AUTHORIZED=false
NEXT_PRIMARY_BOUNDARY=OFFLINE_DATAFLOW_CLASSIFICATION_OF_PRODUCTION_WRITE_KEY_E0_PAYLOAD_AND_PERSISTENT_DESTINATION
```

D276/01 non riapre né estende il confine live D275. Chiude invece offline il
boundary architetturale `LOCAL_LIBFPRINT_DEVICE_GLUE`: la topologia production
scelta è un driver `FpImageDevice` nativo C, in-process e LGPL, implementato in
modo indipendente con provenance controllata. Una singola istanza
`GoodixDeviceContext`, con lifetime `img_open → img_close`, possiede il claim
USB, l'unico bulk-IN reader, il router A0/B0, TLS/secret e l'unico lifecycle
Goodix/FDT. D275 prova un solo oggetto/handshake TLS e un handoff del secret nel
solo run bounded fino al secondo B0; non prova il riuso della stessa sessione
TLS fra più activation libfprint. Il runtime Python GPL resta oracle
comportamentale black-box per test sintetici, non dipendenza runtime e non
sorgente da tradurre nel dominio LGPL.

```text
PRODUCTION_LIBFPRINT_TOPOLOGY=NATIVE_IN_PROCESS_C_LGPL_CLEANROOM
REJECTED_TOPOLOGIES=GPL_OUT_OF_PROCESS_HELPER_WITH_IPC,PYTHON_EMBEDDED_IN_LIBFPRINT
DECISION_CONFIDENCE=HIGH
USB_TRANSPORT_OWNER=GOODIX_FPIMAGE_DEVICE_OPEN_EPOCH_CONTEXT
TLS_SESSION_OWNER=GoodixDeviceContext
SECRET_BOUNDARY_OWNER=GoodixDeviceContext
TLS_SESSION_LIFETIME_ACROSS_LIBFPRINT_ACTIVATIONS=UNRESOLVED
SECRET_HANDOFF_POLICY=ONE_HANDOFF_PER_TLS_SESSION
CROSS_ACTIVATION_TLS_REUSE_TARGET_PROVEN=false
FDT_LIFECYCLE_OWNER=GOODIX_FPIMAGE_DEVICE_OPEN_EPOCH_CONTEXT
LIBFPRINT_EVENT_CONTEXT_MODEL=ONE_GLIB_MAIN_CONTEXT_WITH_ASYNC_FPI_USB_TRANSFER_AND_ONE_PHYSICAL_IN_READER
CANCELLATION_MODEL=HOST_IO_CANCEL_AND_DRAIN_INVALIDATE_GENERATION_MARK_PROTOCOL_SESSION_POISONED_QUIESCENCE_UNKNOWN_NO_MASKED_RESUME
HOST_ONLY_TERMINAL_CLEANUP=PROVEN_IN_EXISTING_BOUNDED_RUNTIME
LIBFPRINT_CANCEL_DEVICE_SIDE_PROTOCOL=UNPROVEN
DEVICE_SIDE_CANCEL_COMMAND=NONE_PROVEN
NO_UNPROVEN_CANCEL_COMMAND_ALLOWED=true
PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL=UNRESOLVED
GOODIX_RELEASE_TAIL_ORDER=FINGER_IMAGE_0X34_EXACT_ACK_IRQ0200_DERIVE_VALIDATE_DOWN_TABLE_0X20_EXACT_ACK_POST_UP_B0_CONSUME_DISCARD_0X50_EXACT_ACK_NAV_CONSUME_GOODIX_RELEASE_TAIL_COMPLETE_FINGER_OFF_REPORT_FALSE
FINGER_OFF_REPORT_POINT=AFTER_GOODIX_RELEASE_TAIL_COMPLETE
POST_UP_B0_DELIVERED_TO_LIBFPRINT=false
AWAIT_FINGER_ON_GATES=REARM_0X32_ONLY
AWAIT_FINGER_ON_DOES_NOT_GATE=POST_UP_0X20,POST_UP_B0,NAV_0X50
NON_ENROLL_FINGER_OFF_REENTRANCY=SYNCHRONOUS_DEACTIVATE_ALLOWED_AFTER_RELEASE_TAIL_NO_SUBSEQUENT_GOODIX_COMMAND
ENROLL_REARM_GATE=AWAIT_FINGER_ON_AND_GOODIX_RELEASE_TAIL_COMPLETE_AND_FRESH_SAME_CYCLE_DOWN_TABLE
LIBFPRINT_ENROLLMENT_AGGREGATION=FRAMEWORK_OWNED_VERIFIED
PROJECT_EXTRA_FPIMAGE_AGGREGATOR_REQUIRED=false
LOCAL_LIBFPRINT_DEVICE_GLUE=IMPLEMENTED_HOST_ONLY_EXECUTABLY_CLOSED
LOCAL_LIBFPRINT_DEVICE_GLUE_SLICE_1=IMPLEMENTED_CORRECTIVE_EXECUTABLY_CLOSED_HOST_ONLY
LOCAL_LIBFPRINT_DEVICE_GLUE_ARCHITECTURE=CLOSED_D276_01
D276_02_OUTCOME=READY
FPIMAGE_DEVICE_REAL_FRAMEWORK_USED=true
IN_MEMORY_BACKEND_ONLY=true
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
D276_02_HOST_ONLY_EXECUTABLE_VALIDATION=PASS_CLEAN_TREE
D276_02_CI_VALIDATED_COMMIT=87d4aacec23b5415cca5de73e0dfeb83ffe65bab
D276_02_GITHUB_ACTIONS_RUN=33165906857
D276_02_NORMAL_TEST_RUN=PASS
D276_02_SANITIZER_TEST_RUN=PASS
D276_02_DETERMINISM_RUNS=2
GPL_TO_LGPL_CODE_COPY_ALLOWED=false
MECHANICAL_TRANSLATION_ALLOWED=false
CLEANROOM_NATIVE_REIMPLEMENTATION_REQUIRED_IF_SELECTED=true
CLEANROOM_LABEL=PROJECT_ENGINEERING_PROVENANCE_CONTROL_NOT_LEGAL_CONCLUSION
ENROLLMENT_STAGE_POLICY=NOT_SELECTED
GOODIX_USB_ROUTER_IMPLEMENTED=true
A0_B0_INCREMENTAL_PARSER=PASS_HOST_ONLY
A0_B0_DEMUX=PASS_HOST_ONLY
B0_SPLIT_ACROSS_RECEIVES=PASS_HOST_ONLY
GBytes_CALLBACK_OWNERSHIP=TRANSFER_NONE_BORROWED_DURING_CALLBACK
DELIVERY_ORDER_PRESERVED=true
DELIVERY_EXACTLY_ONCE=true
PHYSICAL_RECEIVE_OWNER_COUNT=1
MAX_OUTSTANDING_RECEIVES=1
SECOND_READER_API_PATH=ABSENT
STALE_GENERATION_CALLBACK=IGNORED
CANCEL_TERMINAL_FENCE=PASS_HOST_ONLY
D276_03_OUTCOME=READY
D276_03_EXECUTABLE_CLOSURE=PASS_HOST_ONLY
D276_03_CORRECTIVE_RUNTIME_COMMIT=d8ddaa72835662a92db857f55551810649a2b1c5
D276_03_CI_VALIDATED_COMMIT=49e7e9d108d14fc7a9910d97022cd4baa829c5e4
D276_03_MERGED_MAIN_COMMIT=474aa2b931977a2c748098c4e510764ad7ee7f42
D276_03_GITHUB_ACTIONS_PUSH_RUN=33184060807
D276_03_GITHUB_ACTIONS_PR_RUN=33184064239
D276_03_GITHUB_ACTIONS_RESULT=PASS
D276_03_NORMAL_TEST_RUN=PASS
D276_03_SANITIZER_TEST_RUN=PASS
D276_03_DETERMINISM_RUNS=2
D276_03_ROUTER_TESTS_PER_NORMAL_RUN=8/8_PASS
D276_03_ROUTER_TESTS_PER_SANITIZER_RUN=8/8_PASS
D276_02_FPIMAGE_REGRESSION_NORMAL=PASS
D276_02_FPIMAGE_REGRESSION_SANITIZER=PASS
D276_04_OUTCOME=READY
D276_04_EXECUTABLE_CLOSURE=PASS_HOST_ONLY
D276_04_EXECUTOR_STATUS=CLOSED
D276_04_AI_PM_REVIEW=PASS
GOODIX_DEVICE_CONTEXT_OWNS_ROUTER_TLS_BACKEND=true
ROUTER_B0_TO_TLS_INTEGRATION=PASS
TLS_POST_HANDSHAKE_APPLICATION_DATA=PASS
TLS_OUT_BACKEND_PATH=PASS
NATIVE_TLS_PROVIDER=OPENSSL
TLS_1_2_PSK_HANDSHAKE_SYNTHETIC=PASS
SECRET_HANDOFF_COUNT=1
PROJECT_OWNED_SECRET_COPY_ZEROIZED=true
OPENSSL_INTERNAL_SECRET_COPY_ZEROIZATION=NOT_ASSERTED
SECOND_SECRET_HANDOFF_REJECTED=true
FPI_USB_BACKEND_COMPILED=true
REAL_USB_TRANSFER_SUBMIT_COUNT=0
MAX_OUTSTANDING_BULK_IN=1
SECOND_READER_API_PATH=ABSENT
D276_04_CI_VALIDATED_COMMIT=d10155076b7f46e7897c9df65a910a125b4575b4
D276_04_GITHUB_ACTIONS_PUSH_NATIVE=33197044447
D276_04_GITHUB_ACTIONS_PUSH_NATIVE_RESULT=PASS
D276_04_GITHUB_ACTIONS_PUSH_ROUTER=33197044428
D276_04_GITHUB_ACTIONS_PUSH_ROUTER_RESULT=PASS
D276_04_GITHUB_ACTIONS_PR_NATIVE=33197046858
D276_04_GITHUB_ACTIONS_PR_NATIVE_RESULT=PASS
D276_04_GITHUB_ACTIONS_PR_ROUTER=33197046876
D276_04_GITHUB_ACTIONS_PR_ROUTER_RESULT=PASS
GITHUB_ACTIONS_CONFIRMATION=PASS
OUTCOME=READY
ADVANCEMENT=NATIVE_TLS_1_2_PSK_MEMORY_BIO_AND_ASYNC_FPI_USB_BACKEND_HOST_ONLY_INTEGRATION_VALIDATED_WITH_SINGLE_GENERATION_AUTHORITY_AND_CALLBACK_DRIVEN_CANCEL_DRAIN
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=HARDWARE_EQUIVALENCE_UNPROVEN;PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL_UNRESOLVED;DEVICE_SIDE_CANCEL_COMMAND_NONE_PROVEN;TARGET_DEVICE_TIMEOUT_UNKNOWN;TLS_SESSION_LIFETIME_ACROSS_LIBFPRINT_ACTIVATIONS_UNRESOLVED;ENROLLMENT_STAGE_POLICY_NOT_SELECTED;ORIENTATION_CONTRACT_UNRESOLVED;POLARITY_CONTRACT_UNRESOLVED;TARGET_APP12509_PHYSICAL_PPMM_UNKNOWN
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_MAIN_a0b849d563a1c3619aed11b3dbefad1bb4bb30ec_PLUS_CI_VALIDATED_COMMIT_d10155076b7f46e7897c9df65a910a125b4575b4_PLUS_GITHUB_ACTIONS_PUSH_NATIVE_33197044447_PUSH_ROUTER_33197044428_PR_NATIVE_33197046858_PR_ROUTER_33197046876_PLUS_PR_31_BRANCH_codex/correggi-la-chiusura-dopo-il-merge-d276/04
NEXT_PRIMARY_BOUNDARY=AI_PM_NEXT_STEP_SELECTION_AFTER_D277_01_CLOSURE
LIVE_AUTHORIZED=false
```

D277/01 ha costruito e verificato host-only un harness C test-only con binding
effimero `FpDevice`/`GUsbDevice`, percorso obbligato
`FpiUsbTransfer → GoodixFpiUsbBackend → GoodixUsbRouter` e un solo frame A8
immutabile. Le regressioni D277, D276/02, D276/03 e D276/04 sono PASS normal e
ASAN/UBSAN; i file production D276/04 sono rimasti byte-identici alla baseline
approvata `95f40ca791011d637e2040a87014bbb8e946275e`.

La singola run D277/01 non ha però raggiunto il bus protocollo: il target
univoco `27c6:5125` (bus 1, address 4, port 7) ha fallito al primo
`g_usb_device_open()`, prima di claim e di qualsiasi submit IN/OUT. Il nodo
`/dev/bus/usb/001/004` era osservato `root:root` `0664`, senza ACL aggiuntive;
l'esecutore uid 1000 non aveva write permission. Il nesso con l'open failure è
una strong inference perché il `GError` non è stato serializzato. Nessun sudo,
cambio udev, retry, reopen o reset è stato eseguito. L'autorizzazione è stata
consumata conservativamente sul tentativo di open e resta falsa.

Il primo correttivo host-only D277/01 ha aggiunto a `tools/d277_native_a8_once.c`
un permission preflight read-only che risolve il device node
`/dev/bus/usb/BBB/DDD`, ne riporta uid/gid/mode e gruppi dell'esecutore, e
consulta `access(W_OK)` per bloccare prima di `g_usb_device_open()` quando il
nodo non è scrivibile (`BLOCKED_ENVIRONMENT_USB_NODE_NOT_WRITABLE`). Il runtime
continua a usare `access(W_OK)` perché riflette i permessi effettivi del
processo, inclusi ACL impliciti; i test mode/uid/gid sono invece eseguiti su
un helper puro deterministico che non dipende dall’uid della CI. ACL parsing
non è stato implementato; la decisione è documentata nel sorgente.

Un secondo correttivo host-only è stato necessario perché la CI GitHub Actions
run 33206366417 falliva sotto `root`: i test con fixture temporanee assumevano
che `chmod 0444` rendesse `access(W_OK)` false, il che non vale per `root`.
I test sono stati corretti per confrontare il risultato di `d277_check_device_node()`
direttamente con `access(2)`, senza imporre semantica non privilegiata. È stato
inoltre corretto il campo `device_contact_or_real_submit_occurred`, prima
hard-coded a `false`, perché sia derivato dai contatori della run corrente
(`open_count > 0 || claim_count > 0 || real_submit_count > 0`) e sia
accompagnato da un test host-only dell’helper puro.

La GitHub Actions run 33207424835 sul commit
`d9336c6e033d736a794dae3486ae84c33c412b01` è risultata `PASS`, concludendo
D276/04 normal+sanitizer, D276/02 e D276/03 regressions, D277/01 15/15 normal,
D277/01 15/15 ASAN/UBSAN, live harness build e static safety audit, con
`REAL_USB_TRANSFER_SUBMIT_COUNT=0` e `LIVE_AUTHORIZED=false`. La review AI-PM
tecnica del correttivo è `PASS`. D277/01 è quindi chiuso host-only; il percorso
nativo A8/A0 su target reale resta non provato. I file production D276/04
restano byte-identici alla baseline approvata
`95f40ca791011d637e2040a87014bbb8e946275e`.

```text
D277_01_OUTCOME=BLOCKED_ENVIRONMENT_USB_OPEN_FAILED
D277_01_HOST_ONLY_CORRECTIVE=CLOSED
D277_01_EXECUTABLE_CLOSURE=PASS_HOST_ONLY
D277_01_CI_CONFIRMATION=PASS
D277_01_AI_PM_TECHNICAL_REVIEW=PASS
D277_01_DEVICE_SIDE_ADVANCEMENT=NONE
PREVIOUS_LIVE_ATTEMPT_TERMINATED=true
LIVE_AUTHORIZATION_CONSUMED=true
AUTHORIZATION_CONSUMPTION_POLICY=CONSERVATIVE_ON_FIRST_TARGET_OPEN_ATTEMPT
DEVICE_CONTACT_OR_REAL_SUBMIT_OCCURRED=false
CURRENT_LIVE_AUTHORIZED=false
NEW_USER_AUTHORIZATION_REQUIRED_FOR_ANY_NEW_OPEN_CLAIM_OR_SUBMIT=true
LIVE_AUTHORIZED=false
USB_OPEN_ATTEMPT_COUNT=1
USB_OPEN_COUNT=0
USB_CLAIM_COUNT=0
A8_COMMAND_SUBMIT_COUNT=0
NATIVE_FPI_USB_A8_PATH_TARGET_PROVEN=false
NATIVE_FPI_USB_A0_ROUTER_TARGET_PROVEN=false
HARDWARE_EQUIVALENCE=UNPROVEN
PERSISTENT_DEVICE_WRITE_COUNT=0
RETRY_COUNT=0
TRANSPORT_REOPEN_COUNT=0
NEXT_PRIMARY_BOUNDARY=AI_PM_NEXT_STEP_SELECTION_AFTER_D277_01_CLOSURE
NEXT_LIVE_REQUIREMENT=HOST_PERMISSION_REVIEW_PLUS_NEW_EXPLICIT_AUTHORIZATION
```

### D277/02 — prova nativa A8/A0 su target reale

Dopo il correttivo host-only D277/01, l'Utente ha autorizzato una singola run
live D277/02. Il prerequisito ambientale è stato soddisfatto con una ACL
named-user temporanea e solo sul nodo corrente (`user:guido:rw-` su
`/dev/bus/usb/001/004`), applicata e rimossa manualmente dall'operatore; nessuna
regola udev persistente, nessun cambio di owner/mode globale, nessun `sudo`
dell'esecutore.

La run ha aperto e reclamato il target `27c6:5125` (bus 1, address 4, port 7),
ha sottomesso l'exact A8 `a00600a6a803000000ff`, ha ricevuto un ACK logico A8
e una risposta tipata con firmware `GF_ST411SEC_APP_12509`, e ha rilasciato e
chiuso il dispositivo. I contatori di sicurezza sono tutti zero: retry, reopen,
reset, cancel device-side, secret, TLS, finger-wait, image, scritture persistenti.

```text
D277_02_LIVE_RESULT=PASS
D277_02_DEVICE_SIDE_ADVANCEMENT=NATIVE_A8_A0_TARGET_PROOF
NATIVE_FPI_USB_A8_PATH_TARGET_PROVEN=true
NATIVE_FPI_USB_A0_ROUTER_TARGET_PROVEN=true
APP12509_NATIVE_IDENTITY_REVALIDATED=true
A8_TX_HEX=a00600a6a803000000ff
A8_FIRMWARE=GF_ST411SEC_APP_12509
USB_OPEN_ATTEMPT_COUNT=1
USB_OPEN_COUNT=1
USB_CLAIM_COUNT=1
A8_COMMAND_SUBMIT_COUNT=1
BULK_IN_SUBMIT_COUNT=2
A8_LOGICAL_ACK_COUNT=1
A8_TYPED_RESPONSE_COUNT=1
MAX_OUTSTANDING_BULK_IN=1
SECOND_READER_API_PATH=ABSENT
RETRY_COUNT=0
TRANSPORT_REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
DEVICE_SIDE_CANCEL_COMMAND_COUNT=0
SECRET_MATERIALIZATION_COUNT=0
TLS_HANDSHAKE_COUNT=0
FINGER_WAIT_COUNT=0
IMAGE_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
HOST_CACHE_WRITE_COUNT=0
USB_RELEASE_COUNT=1
USB_CLOSE_COUNT=1
TERMINAL_CLEANUP_COMPLETED=true
LIVE_AUTHORIZATION_CONSUMED=true
CURRENT_LIVE_AUTHORIZED=false
NEW_USER_AUTHORIZATION_REQUIRED_FOR_ANY_NEW_OPEN_CLAIM_OR_SUBMIT=true
```

La prova target-proven è limitata al percorso A8/A0 bounded:

```text
real Goodix 27c6:5125
-> GUsb/libfprint-owned USB device
-> FpiUsbTransfer / GoodixFpiUsbBackend
-> GoodixUsbRouter A0 path
-> exact A8 request
-> logical A8 ACK
-> typed A8 firmware response
```

Limiti espliciti non risolti da D277/02:

```text
TLS_NOT_EXERCISED=true
E4_NOT_EXERCISED=true
FINGER_PATH_NOT_EXERCISED=true
IMAGE_PATH_NOT_EXERCISED=true
```

Chiusura D277/02:

```text
OUTCOME=READY
ADVANCEMENT=NATIVE_A8_A0_TARGET_PROVEN_ON_REAL_APP12509
EXECUTABLE_CLOSURE=NOT_APPLICABLE
RESIDUAL_BLOCKER_OR_RISK=GLOBAL_HARDWARE_EQUIVALENCE_UNPROVEN;PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL_UNRESOLVED;TLS_LIFETIME_ACROSS_ACTIVATIONS_UNRESOLVED;ENROLLMENT_STAGE_POLICY_UNRESOLVED;ORIENTATION_POLARITY_PPMM_UNRESOLVED;PRODUCTION_LIBFPRINT_FPRINTD_INTEGRATION_NOT_YET_PROVEN;FUTURE_LIVE_RUNS_REQUIRE_FRESH_HOST_PERMISSION_PREFLIGHT_AND_NEW_EXPLICIT_AUTHORIZATION
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_2a6c19a7e8a6199178fe7ac16e63d4cec495e22b_PLUS_HEAD_87209c9b20b7b708ebc607724209be69733297c8_PLUS_analysis/D277/D277_02_native_a8_real_usb.md_PLUS_analysis/D277/D277_02_native_a8_real_usb.json_PLUS_Goodix_27c6_5125_manuale_tecnico.md
NEXT_PRIMARY_BOUNDARY=AI_PM_NEXT_STEP_SELECTION_AFTER_D277_02_CLOSURE
```

Dopo la run l'operatore ha rimosso la ACL temporanea; il check effettivo ha
prodotto `WRITE_ACCESS_REMOVED`. I file production D276/04 restano
byte-identici alla baseline approvata
`95f40ca791011d637e2040a87014bbb8e946275e`.

### D278/01 — catena secure-session nativa C/LGPL, solo host-only

D278/01 estende il confine nativo già target-proven A8/A0 senza eseguire nuovo
hardware. La nuova state machine indipendente LGPL, posseduta dal medesimo
`GoodixDeviceContext`, impone esattamente:

```text
A8 -> E4 -> A2_1 -> CHIP_82 -> OTP_A6 -> A2_2 -> MODE_70
-> DAC_220 -> DAC_236 -> DAC_238 -> DAC_23A -> CONFIG_90
-> D1 -> B0/TLS 1.2 PSK -> TLS ESTABLISHED -> STOP
```

Il codec A0 valida type, length LE16, tag esterno, control, length interno e
checksum additivo; D1 conserva wire control `D1` e checksum seed `D0`. I golden
vector A8 `a00600a6a803000000ff`, E4
`a00c00ace40900030002bb00000000fd` e D1
`a00600a6d103000000d7` passano normal e sanitizer. La policy ACK originaria
D278/01, oggi superata per la semantica ACK da D238 e dal correttivo post-live
D278/03, era phase-specific ma ammetteva `0x01|0x07` soltanto per A8 ed
esattamente `0x01` per E4..90. La policy C canonica corrente ammette invece
esclusivamente `0x01|0x07` per ogni fase ACK-bearing, preservando echo esatto,
body di due byte e il contratto ACK+typed oppure ACK-only specifico della fase.
Nella matrice D238 da E4 in avanti, `0x07` resta osservato live direttamente
soltanto per E4 e A2_1; sulle fasi successive l'ammissione è la bounded
transport/session inference D238. D1 non
ammette A0 e richiede come prima classe B0/TLS ClientHello. Il passaggio
D1→TLS non deriva dal solo successo di `goodix_tls_server_push()`: avviene una
sola volta soltanto dopo che OpenSSL ha elaborato abbastanza ClientHello da
produrre il primo flight server. Frammenti TLS incompleti restano in D1 senza
egress; un errore della push prevale su qualsiasi alert sincrono e chiude la
sessione.

Il material boundary riceve in memoria identity APP12509, validator/pin E4,
pin A2/82/A6, quattro DAC, CONFIG_90 con hash/finalizer/correlazione e PSK da
32 byte. Nessun file, capture, PE o store viene aperto dal protocol engine. Il
raw CONFIG_90 target non è leggibile nell'ambiente corrente e i raw typed body
target non sono incorporati: l'esecuzione host-only usa fixture esplicitamente
sintetiche e non dichiara match con gli hash target. I pin canonici D232
restano invariati.

Il backend è ora single-OUT-in-flight anche nella stessa generation e notifica
il completion catturando la generation; un response contract non avanza dal
solo submit. Gli A0 restano alla lunghezza logica non padded. Ogni record TLS
uscente è un B0 distinto, spezzato in submission fisiche da 64 byte con tail
finale zero-initialized; record distinti non sono coalesciuti e sono separati da
un'azione scheduler da 10 ms. Scheduler, queue, callback e completion sono
posseduti dalla stessa generation e diventano inerti su cancel/fence/teardown.
La telemetria audit è osservativa e opzionale: il pacing usa stato operativo
interno, non i contatori audit. I test coprono anche completion OUT sincrono del
seam e risposta typed duplicata prima del completion fisico, che fallisce
chiusa.

Il peer sintetico asincrono attraversa il vero sequencer, router, backend e
`GoodixTlsServer`, completa una vera handshake OpenSSL TLS 1.2
`PSK-AES128-GCM-SHA256` con identity `Client_identity`, un handoff secret e
zeroizzazione della copia project-owned. La suite D278 passa 10/10 normal e 10/10
ASAN/UBSAN. Il decimo gruppo usa un client OpenSSL reale e prova split
deterministici dopo il solo header record e nel body ClientHello, completamento
con avanzamento singolo, e TLS malformato fail-closed. Passano inoltre D276/02 15/15, D276/03 8/8, D276/04 5/5 e D277
15/15 sia normal sia sanitizer. LeakSanitizer è disabilitato perché non
disponibile sotto il boundary Flatpak/bwrap ptrace; ASAN address checks e UBSAN
restano attivi. Il checkpoint iniziale `0efa30f681e0a3aa284565ce581536ad00606c39` ha
GitHub Actions PASS nella run `33237274978`; questa evidenza precede la
correzione del gate. La correzione
`5030c66e67db5a7f6cedfbf3bb0deeec107e79db` ha review AI-PM PASS, CI PASS
nella run `33239781874` ed è confluita su main con merge
`52e190b2ceaee0e8de618accd4da9fadbad54115`.

```text
D278_01_INITIAL_IMPLEMENTATION_HOST_ONLY=PASS
D278_01_INITIAL_IMPLEMENTATION_COMMIT=0efa30f681e0a3aa284565ce581536ad00606c39
D278_01_INITIAL_IMPLEMENTATION_CI_RUN=33237274978
D278_01_INITIAL_IMPLEMENTATION_CI_RESULT=PASS
D278_01_D1_TLS_GATE_CORRECTIVE_COMMIT=5030c66e67db5a7f6cedfbf3bb0deeec107e79db
D278_01_D1_TLS_GATE_AI_PM_REVIEW=PASS
D278_01_D1_TLS_GATE_CI=PASS
D278_01_D1_TLS_GATE_CI_RUN=33239781874
D278_01_D1_TLS_GATE_MERGED_MAIN=52e190b2ceaee0e8de618accd4da9fadbad54115
NATIVE_SECURE_SESSION_CHAIN_HOST_ONLY_PROVEN=true
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
NATIVE_PRE_D1_SEQUENCE_HOST_ONLY_PROVEN=true
NATIVE_D1_B0_TLS_TRANSITION_HOST_ONLY_PROVEN=true
NATIVE_TLS12_PSK_HANDSHAKE_HOST_ONLY_PROVEN=true
NATIVE_B0_FIXED64_EGRESS_HOST_ONLY_PROVEN=true
NATIVE_TLS_RECORD_PACING_HOST_ONLY_PROVEN=true
PHYSICAL_RECEIVE_OWNER_COUNT=1
MAX_OUTSTANDING_BULK_IN=1
MAX_OUTSTANDING_BULK_OUT=1
RETRY_COUNT=0
TRANSPORT_REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
D4_REACHABLE=false
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
CURRENT_LIVE_AUTHORIZED=false
NEXT_PRIMARY_BOUNDARY=D278_02_NATIVE_TARGET_MATERIAL_AND_LIVE_CAPABLE_HARNESS_PREPARATION
```

### D278/02 — boundary nativo dei materiali, harness secure-session live-capable e preflight materiali protetti autentico

D278/02 chiude il boundary preparatorio che D278/01 lasciava aperto. La
preparazione host-only e il ramo `--self-test` non contattano il sensore né
leggono lo store protetto reale; in seguito l'operatore ha eseguito il solo
preflight read-only dei materiali autentici. Il nuovo loader
LGPL applica sui tre file target policy produttiva uid 0/mode 0600,
`O_RDONLY|O_CLOEXEC|O_NOFOLLOW`, `fstat` pre/post, tipo/owner/mode/lunghezza,
device/inode, hash, magic/layout PSK e contratti CONFIG90
finalizer/DAC. Il validator E4 è derivato in memoria dalla stessa PSK poi
consegnata al server TLS; nessun validator persistente viene creato.

La primitive D190 LGPL e il parser PE GPL sono adattamenti bounded della
reference locale BSD-2-Clause al commit storico
`b475a6eca72e340816779afae917334a6146c986`. I cinque validator indipendenti
sono golden evidence fissa. La DLL canonica
`analysis/D230/work/GoodixExport/gfusb.dll` è accettata solo con size 5771496 e
SHA-256 `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`;
viene letta come byte inerti e non caricata, eseguita o passata a Wine.

Il nuovo harness GPL usa la stessa composizione in modalità sintetica e nella
futura modalità live: `GoodixSecureSession`, `GoodixUsbRouter`,
`GoodixTlsServer`, `GoodixFpiUsbBackend`, una generation, un receive owner e al
massimo un IN/OUT fisico in flight. Il watchdog GLib è phase-aware, reinvalidato
ad ogni progresso e terminalmente fenced. STOP/cancel precedono il drain;
sessione, backend e router vengono liberati soltanto dopo drain.

La suite contiene 62 casi: 6 D190, 6 PE, 23 loader, 7 preflight-observability e 20 harness/watchdog/telemetria. Due
invocazioni consecutive del runner hanno eseguito ciascuna 62/62 normal e
62/62 ASAN/UBSAN PASS, compilato il binding libfprint/GUsb completo ed eseguito
soltanto `--self-test`, che termina intenzionalmente sul watchdog A8 con cleanup
completo e contatori USB reali a zero. Il ramo live non è stato eseguito;
il protected preflight autentico è stato invece eseguito dall'operatore
(29 agosto 2026) in modalità `--material-preflight-only` con zero USB.

Il correttivo D278/02 ha corretto il pin A2 della policy produttiva in
`goodix_target_material_policy_production()`: il valore canonico, verificato in
`analysis/D232/D232_target_material_manifest.json`, è
`39e469ce5a5ba3136c4a44381f2e4183dca275257adfcf3c0025094f05c022f5`.
È stato aggiunto un test indipendente che confronta tutti i pin critici della
policy produttiva con costanti attese ricavate dalle evidenze canoniche.

La review AI-PM del correttivo A2 è `PASS`; il correttivo è confluito su main
come `01b2379395b59219112236a6387bee9e5bd47bbf` e la CI `33252621869` è
PASS. Il micro-correttivo di osservabilità ha superato la review AI-PM
(`PASS`), è confluito su main con merge
`1d25abc7b4a99ea1719cc4381d6f780501483209` e la CI post-merge `33255017404`
è `PASS`; rende il preflight osservabile senza segreti: il JSON espone coppie
stabili `failure_stage` e `failure_class` per policy/argomenti, open, metadata,
read, content, PE/DLL, binding E4 ed export/state, senza propagare messaggi
GError liberi. I test usano solo fixture sintetiche. Il preflight autentico è
stato eseguito dall'operatore il 29 agosto 2026 con `PASS`, zero USB e
`e4_binding_match=true`; nessuna run USB/live è autorizzata.

```text
OUTCOME=READY
ADVANCEMENT=REAL_EXECUTION_COMPLETED_AUTHENTIC_PROTECTED_MATERIAL_PREFLIGHT_WITH_E4_BINDING_MATCH_AND_ZERO_USB_ACCESS
EXECUTABLE_CLOSURE=PASS
MATERIAL_INVALID_BLOCKS_BEFORE_USB_OPEN=PASS
SYNTHETIC_SINGLE_OPEN_CLAIM_EPOCH=PASS
PHYSICAL_RECEIVE_OWNER_COUNT=1
MAX_PHYSICAL_IN_OUTSTANDING=1
MAX_PHYSICAL_OUT_OUTSTANDING=1
SECOND_READER_API_PATH=ABSENT
RETRY_COUNT=0
TRANSPORT_REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
D4_REACHABLE=false
APPLICATION_DATA_COUNT=0
PROJECT_SECRET_ZEROIZATION=PASS_TO_IMPLEMENTATION_BOUNDARY
OPENSSL_INTERNAL_ZEROIZATION_ASSERTED=false
D278_02_TEST_COUNT_PER_BINARY_RUN=62
PRODUCTION_POLICY_CANONICAL_PIN_MATRIX=PASS
AI_PM_INITIAL_REVIEW=FAIL_CORRECTIVE_REQUIRED
INITIAL_REVIEW_BLOCKER=CANONICAL_A2_RESPONSE_SHA256_PRODUCTION_PIN_MISMATCH
CANONICAL_A2_SHA256_EXPECTED=39e469ce5a5ba3136c4a44381f2e4183dca275257adfcf3c0025094f05c022f5
CANONICAL_A2_SHA256_IMPLEMENTED_AFTER_FIX=39e469ce5a5ba3136c4a44381f2e4183dca275257adfcf3c0025094f05c022f5
D278_02_CANONICAL_A2_CORRECTIVE_AI_PM_REVIEW=PASS
AI_PM_REVIEWED_MAIN_BASELINE=01b2379395b59219112236a6387bee9e5bd47bbf
CORRECTIVE_CI_RUN=33252621869
CORRECTIVE_CI=PASS
PROTECTED_PREFLIGHT_FAILURE_OBSERVABILITY=PASS
PROTECTED_PREFLIGHT_REDACTION=PASS
NO_SECRET_BYTES_IN_FAILURE_TELEMETRY=PASS
D278_02_MICRO_CORRECTIVE_AI_PM_REVIEW=PASS
D278_02_MICRO_CORRECTIVE_MERGED_MAIN=1d25abc7b4a99ea1719cc4381d6f780501483209
D278_02_POST_MERGE_CI_RUN=33255017404
D278_02_POST_MERGE_CI=PASS
TARGET_PROTECTED_MATERIAL_PREFLIGHT_EXECUTED=true
TARGET_PROTECTED_MATERIAL_PREFLIGHT=PASS
TARGET_E4_BINDING_PREFLIGHT=PASS
TARGET_MATERIAL_PREFLIGHT_FAILURE_STAGE=NONE
TARGET_MATERIAL_PREFLIGHT_FAILURE_CLASS=none
TARGET_MATERIAL_PREFLIGHT_RC=0
TARGET_MATERIAL_PREFLIGHT_REAL_USB_ACCESS=0
TARGET_MATERIAL_PREFLIGHT_USB_OPEN_COUNT=0
TARGET_MATERIAL_PREFLIGHT_USB_CLAIM_COUNT=0
TARGET_MATERIAL_PREFLIGHT_REAL_USB_SUBMIT_COUNT=0
TARGET_MATERIAL_PREFLIGHT_RETRY_COUNT=0
TARGET_MATERIAL_PREFLIGHT_DEVICE_RESET_COUNT=0
TARGET_MATERIAL_PREFLIGHT_PERSISTENT_DEVICE_WRITE_COUNT=0
TARGET_MATERIAL_PREFLIGHT_PROJECT_SECRET_ZEROIZED=true
TARGET_E4_NATIVE_LIVE_PROVEN=false
TARGET_TLS_NATIVE_LIVE_PROVEN=false
D278_02_LIVE_EXECUTION_PERFORMED=false
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
CURRENT_LIVE_AUTHORIZED=false
D278_02_NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_THEN_EXPLICITLY_AUTHORIZED_SINGLE_SHOT_NATIVE_TARGET_SECURE_SESSION
```

Riesame metodologico preparato, non eseguito come live: (1) rispetto a D277/02
cambiano materialmente il boundary protetto, il binder PSK→E4 condiviso con
TLS, la composizione completa e il watchdog; (2) l'ipotesi futura è
APP12509 `A8→E4 MATCH→A2→82→A6→A2→70→80x4→90→D1→TLS→STOP` senza D4 o
persistenza; (3) al primo fallimento si ferma, registra fase/classe redatta,
non ritenta/riapre/resetta, drena, azzera e torna ad AI-PM.

Il boundary successivo a D278/02 era la review pre-live del live-critical set
e, soltanto dopo approvazione esplicita di uno SHA live-critical, una eventuale
autorizzazione single-shot separata dell'Utente per la native target
secure-session; tale stato storico è stato poi superato dalla singola run
D278/03 descritta sotto. La review AI-PM del micro-correttivo è `PASS` e il preflight
autentico dei materiali protetti è `PASS` (29 agosto 2026, zero USB). La live
secure-session resta una decisione futura separata. D278/02 non auto-approva
una baseline e non autorizza una run.

#### Preflight autentico dei materiali protetti — 29 agosto 2026

L'operatore ha eseguito una sola volta `--material-preflight-only` dalla root
canonica del repository, leggendo i file `root:root` `0600` con i privilegi
host necessari a quel solo scopo; tale privilegio non costituisce autorizzazione
USB/live. Il preflight ha verificato il percorso produttivo di caricamento e
validazione dei materiali autentici e il binding D190 PSK→E4, ottenendo
`failure_stage=NONE`, `preflight_passed=true`, `failure_class=none`,
`e4_binding_match=true`, `project_secret_zeroized=true`, `PREFLIGHT_RC=0`,
`usb_open_count=0`, `usb_claim_count=0`, `real_usb_submit_count=0`,
`command_count=0`, `tls_handshake_count=0`, `persistent_device_write_count=0`
e `retry_count=0`. L'evidenza redatta è in
`analysis/D278/D278_02_operator_protected_material_preflight_20260829.json`.

Questo PASS prova che il materiale reale supera il boundary protetto nativo con
E4 binding `MATCH` e zero accesso USB; non prova l'invio live nativo di E4, la
sua accettazione dal sensore, il completamento del pre-D1/D1, né il TLS nativo
live. La taxonomy probatoria resta distinta: `D277_02_TARGET_PROOF` (A8/A0/APP12509),
`D278_01_HOST_ONLY_PROOF` (secure-session sintetica host-only),
`D278_02_HOST_ONLY_PROOF` (loader/binder/PE/composizione/watchdog/telemetria
host-only) e `D278_02_AUTHENTIC_PROTECTED_MATERIAL_PREFLIGHT` (materiali autentici
PASS, E4 binding MATCH, zero USB). `TARGET_UNPROVEN` resta vero per E4, pre-D1,
D1 e TLS nativi live sul sensore.

### D278/03 — singola run live consumata, failure E4 e correttivo ACK offline

La review statica HIGH AI-PM della baseline
`843290e7790d7930bb136d91510a3db9d3a97027` è `PASS` e conclude che il
launcher D278/02 esistente è sufficiente: non serve un nuovo wrapper/operator
kit e non è richiesta alcuna modifica al live-critical code. D278/03 ha chiuso
il residuo eseguibile sul Fedora 44 dell'operatore, nello stesso clone e nello
stesso `/tmp` disponibile all'Utente.

Il runner D278/02 ha passato 62/62 casi normal e 62/62 ASAN/UBSAN, build del
binding live-capable e `--self-test`; il runner focalizzato D278/01 ha passato
10/10 normal e 10/10 ASAN/UBSAN, incluso il gate D1/ClientHello frammentato e
fail-closed. Il launcher preservato è
`/tmp/goodix-d278-03-prelive.a65WgM/d278_native_secure_session_once`, con
SHA-256 osservato
`a48488b0817256d896a77bf2ac037ff5bef10524dd9c018f31d1c2bb5d3a251a`.
Il path `/tmp` resta effimero e non è parte del review set.

Entrambi i primi avvii nel sandbox AI si sono fermati prima di build/test per
il blocco ambientale Flatpak/bwrap su `NETLINK_ROUTE`; per ciascun runner è
stato eseguito un solo rerun diagnostico identico fuori sandbox, riuscito.
Nessuna configurazione o flag è stata cambiata e non vi sono stati ulteriori
rerun. Tutta questa executable closure pre-live è rimasta host-only: zero
`sudo`, zero letture dello store protetto, zero USB e zero live.

Quella procedura è stata successivamente autorizzata ed eseguita esattamente
una volta sulla baseline live-critical approvata
`843290e7790d7930bb136d91510a3db9d3a97027`, con `main` revisionato
`a38fd26301069e4b2119e2d8cb342e0bcf8926a3` e launcher dello SHA-256 sopra
indicato. L'autorizzazione single-shot è consumata. La run ha completato A8,
inviato E4 e ha terminato sul primo frame IN di E4 prima di un ACK accettato:
`phase_trace=A8,E4,TERMINAL`, due comandi, un ACK, una risposta tipata, tre
completion IN e due OUT. TLS non è stato raggiunto.

Il cleanup è `PASS`: una open/claim/release/close, massimo un IN e un OUT,
zero retry, reopen, reset e scritture persistenti, secret project-owned
azzerato, backend drenato e cleanup terminale completato. D4, application data,
finger e image sono rimasti irraggiungibili. L'evidenza redatta è
`analysis/D278/D278_03_native_secure_session_live_result_20260829.json`.

Il riesame offline ha provato una divergenza del sequencer C rispetto
all'autorità D238: D278/01 ammetteva status ACK `0x01|0x07` solo ad A8 e
`0x01` nelle fasi successive, mentre D238 e il modello Python canonico
ammettono come soli successi `0x01|0x07` per ogni fase ACK-bearing. D236
corrobora causalmente il difetto: E4 `0x07` falliva come `unexpected_ack`, la
correzione storica raggiungeva `E4_MATCH`, e la diagnostica A2_1 osservava
direttamente status `0x07`. Il wording status-`0x01` di D232 resta evidenza
storica immutata ma è superato da D238 limitatamente alla semantica ACK.

La causa primaria è quindi
`CURRENT_NATIVE_C_REJECTED_A_PROVEN_SUCCESS_ACK_CLASS_AT_E4`, con confidenza
`HIGH_CAUSAL_HISTORICAL_CORROBORATION_BUT_CURRENT_STATUS_NOT_TELEMETRIZED`.
Lo status E4 della run corrente non era presente nel log: `0x07` è probabile,
non direttamente provato. Il correttivo C usa ora una tabella per fase che
ammette soltanto `0x01|0x07`, mantenendo echo esatto, body ACK di due byte,
risposte typed obbligatorie dove previste, fasi ACK-only e D1 diretto B0/TLS.
La prima failure protocollare strutturale è inoltre conservata in telemetria
redatta senza payload o materiale segreto.

Le suite host-only post-correttivo passano: secure-session 11/11 normal e
ASAN/UBSAN, D278/02 62/62 normal e ASAN/UBSAN, D276/02 15/15, D276/03 8/8,
D276/04 5/5 e D277 15/15, ciascuna normal e sanitizer. I test coprono E4 e
A2_1 `0x07`, `0x01` su tutte le classi, rifiuto di `0x02`, echo/shape errati,
contratti typed/ACK-only, D1/B0 e telemetria E4 `0x02` redatta. Il correttivo
non ha usato `sudo`, store protetto, USB reale o live.

```text
D278_03_OUTCOME=READY_FOR_AI_PM_REVIEW
D278_03_LIVE_EXECUTION_PERFORMED=true
D278_03_LIVE_RUN_COUNT=1  # prima single-shot
D278_03_LIVE_RUN_COUNT_TOTAL=2
D278_03_LIVE_RESULT=FAIL_E4_PROTOCOL_GATE
D278_03_LIVE_AUTHORIZATION_CONSUMED=true
D278_03_A8_NATIVE_LIVE=PASS
D278_03_E4_OUT_NATIVE_LIVE=SENT
D278_03_E4_ACCEPTED_ACK=false
D278_03_TLS_REACHED=false
D278_03_NATIVE_ACK_POLICY_CORRECTIVE_REQUIRED=true
D278_03_ACK_POLICY_AUTHORITY=D238
D278_03_ACK_POLICY_CORRECTIVE_HOST_ONLY=PASS
AI_PM_STATIC_PRELIVE_REVIEW=PASS
D278_03_PRELIVE_EXISTING_LAUNCHER_SUFFICIENT=true
D278_03_PRELIVE_LIVE_CRITICAL_CODE_CHANGE_REQUIRED=false
D278_03_D278_02_RUNNER=PASS
D278_03_D278_01_D1_TLS_RUNNER=PASS
D278_03_PRELIVE_OPERATOR_PROCEDURE_PREPARED=true
D278_03_PRELIVE_OPERATOR_STOP_GATE_PRESENT=true
D278_03_USB_OPEN_COUNT=1
D278_03_USB_CLAIM_COUNT=1
D278_03_USB_RELEASE_COUNT=1
D278_03_USB_CLOSE_COUNT=1
D278_03_RETRY_COUNT=0
D278_03_TRANSPORT_REOPEN_COUNT=0
D278_03_DEVICE_RESET_COUNT=0
D278_03_PERSISTENT_DEVICE_WRITE_COUNT=0
D278_03_PROJECT_SECRET_ZEROIZED=true
D278_03_BACKEND_DRAINED=true
D278_03_TERMINAL_CLEANUP_COMPLETED=true
CURRENT_RUN_E4_ACK_07_NOT_DIRECTLY_TELEMETRIZED=true
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
TARGET_E4_NATIVE_LIVE_PROVEN=false
TARGET_TLS_NATIVE_LIVE_PROVEN=false
D278_03_ACK_POLICY_CORRECTIVE_AI_PM_REVIEW=PASS
D278_03_POST_CORRECTIVE_BASELINE=4e5d74770bce6e0a9de929b19279038827abff8c
D278_03_POST_CORRECTIVE_EXECUTABLE_CLOSURE=PASS_HOST_ONLY
D278_03_POST_CORRECTIVE_LAUNCHER_SHA256=bf7a1b0dae42d1c17b613c3f03338d10c3448be622e8bc46383f1923f56f192d
D278_03_PRE_CORRECTIVE_LAUNCHER_RETIRED=true
D278_03_POST_CORRECTIVE_TEST_RUNTIME=FREEDESKTOP_SDK_25_08
D278_03_POST_CORRECTIVE_ARTIFACT_STORAGE=OPERATOR_FEDORA_HOST_TMP
D278_03_POST_CORRECTIVE_LOCAL_ARTIFACT_VERIFICATION=PASS
D278_03_POST_CORRECTIVE_BUILD_EXISTS=true
D278_03_POST_CORRECTIVE_LAUNCHER_EXISTS=true
D278_03_POST_CORRECTIVE_D278_02_LOG_EXISTS=true
D278_03_POST_CORRECTIVE_FOCUSED_LOG_EXISTS=true
D278_03_POST_CORRECTIVE_LOG_CONTENT_AI_PM_REVIEW=PASS
D278_03_POST_CORRECTIVE_LAUNCHER_SHA256_LOCAL_VERIFIED=bf7a1b0dae42d1c17b613c3f03338d10c3448be622e8bc46383f1923f56f192d
D278_03_POST_CORRECTIVE_HOST_NATIVE_LAUNCHER_CHECK=PASS
D278_03_POST_CORRECTIVE_HOST_NATIVE_LDD=PASS
D278_03_POST_CORRECTIVE_HOST_NATIVE_SELF_TEST=PASS
D278_03_POST_CORRECTIVE_HOST_NATIVE_SELF_TEST_RC=0
D278_03_POST_CORRECTIVE_HOST_NATIVE_SELF_TEST_REAL_USB_ACCESS=0
HISTORICAL_NEXT_PRIMARY_BOUNDARY_AFTER_D278_03_CORRECTIVE=AI_PM_REVIEW_OF_FINAL_DOCUMENTATION_THEN_SEPARATE_SECOND_SINGLE_SHOT_LIVE_AUTHORIZATION_DECISION  # decisione poi presa; seconda run eseguita e autorizzazione consumata
```

La procedura copiabile, lo STOP gate e la matrice della review pre-live restano
come provenance storica in
`analysis/D278/D278_03_native_secure_session_prelive_closure.md`. Il risultato
live e il riesame/correttivo sono nei due artefatti D278/03 post-live.

Quella decisione separata è stata poi presa: l'Utente ha autorizzato ed eseguito
esattamente **una seconda** single-shot sulla baseline post-corrective
`4e5d74770bce6e0a9de929b19279038827abff8c` con il launcher
`SHA256=bf7a1b0dae42d1c17b613c3f03338d10c3448be622e8bc46383f1923f56f192d`. La
run non ha ritestato E4: ha trasmesso il solo A8 (`command_count=1`) e si è
fermata `SECURE_SESSION_TERMINAL` già in fase A8, perché il primissimo frame IN
non era l'ACK A8 atteso. La telemetria completa, la lettura epistemica e le
conseguenze sono nella sezione D278/04 qui sotto, che è l'autorità corrente per
quella evidenza. L'autorizzazione live è consumata
(`D278_03_SECOND_SINGLE_SHOT_LIVE_AUTHORIZATION_CONSUMED=true`,
`RETRY_AUTHORIZED=false`, `DO_NOT_RUN_AGAIN=true`) e il correttivo ACK resta
quindi non ritestato live (`ACK_POLICY_CORRECTIVE_LIVE_RETESTED=false`) e non
refutato (`ACK_POLICY_CORRECTIVE_REFUTED=false`).

Riesame metodologico per qualunque futura proposta, qui non autorizzata:
(1) il cambiamento materiale è la riconciliazione della policy C a D238, non
la sola telemetria; (2) la nuova ipotesi è che il binding E4 autentico fosse
corretto e che il gate sia fallito per il rifiuto dello status di successo;
(3) se E4 fallisse ancora, `NO THIRD EQUIVALENT FULL RUN`: riesame offline
della telemetria strutturale e nuova diagnostica solo se progettata,
revisionata e autorizzata separatamente. Il punto (2) resta un'ipotesi non
verificata sul target: la seconda run è terminata prima di E4.

### D278/04 — boundary del protocol re-entry cross-session, riconciliato con la seconda single-shot live

L'audit statico/host-only D278/04 separa per la prima volta il drain dei
transfer host dalla provenance causale dei byte. D276 prova che un callback
della generation N non può consumare il token N+1 e che cancel/free attendono
il ritorno dei callback matching. Non prova invece che un transfer realmente
sottomesso nella generation N+1 non possa ricevere byte prodotti dal
device/controller/kernel prima della sua creazione. Quel callback possiede
correttamente il token N+1 e supera il generation fencing corrente; generation
significa ownership host del submit, non session ID wire o causalità device.

La ricostruzione storica nega tre equivalenze troppo forti. D245 non eseguiva
alcun read/drain prima di A8: inviava direttamente l'exact A8, leggeva ACK e
risposta tipata e bloccava E4 se il proprio buffer userspace conteneva byte
ulteriori. A8 resta un
`TARGET_LIVE_PROVEN_READ_ONLY_PRECONDITION_DISCRIMINATOR`, non un reset, flush,
wake, initializer o sincronizzatore cross-session provato. D266 risolveva il
demux command/event nello stesso router e nella stessa sessione, senza
provenance cross-open/process. D268–D275 raggiungevano entrambe le immagini con
una sola sessione USB, un solo oggetto/handshake TLS e zero reopen/retry: non
esercitavano re-entry dopo un abort.

Nel live entrypoint D278 il primo IN viene armato prima del submit A8. Il router
C azzera soltanto il proprio `GByteArray` a begin/cancel e il parser secure
attribuisce ogni A0 valido alla fase corrente, fallendo chiuso su echo,
control, shape o status inattesi. Una vecchia coppia A8 ACK + risposta
APP12509, se consegnata da un transfer nuovo mentre la nuova fase è A8, non
contiene un nonce/session ID che ne riveli l'origine. I test stale-generation
esistenti coprono callback host N, non
`NEW_CALLBACK_GENERATION_N_PLUS_1_RECEIVING_OLD_DEVICE_CAUSAL_DATA`.
Il harness D278 usa inoltre generation `1` a ogni nuovo processo, non un epoch
globale; renderla globalmente univoca non attribuirebbe comunque causalità ai
byte ricevuti.

La documentazione generale libusb conferma soltanto che cancel è asincrono,
che alcuni dati possono essere già stati trasferiti al momento del cancel e
che `close()` non invia richieste sul bus. `release_interface()` riporta
l'interfaccia al primo alternate setting, ma non documenta un reset della
state machine applicativa Goodix o una regola portabile sulla sorte di tutte le
risposte già prodotte. Queste sono
`EXTERNAL_GENERAL_USB_SEMANTICS`, non prova APP12509. La sorte di dati unread e
la quiescenza del protocollo dopo cancel/release/close/new open restano
target-specific `UNKNOWN/UNRESOLVED`.

Il gap architetturale è quindi `PROVEN`: è verificata staticamente l'assenza di
una garanzia host di cross-session frame provenance, mentre il fencing copre
correttamente il solo `OLD_CALLBACK_FROM_GENERATION_N`.

La seconda single-shot live D278/03 ha poi aggiunto il fatto che l'audit
statico non possedeva. In una **nuova** sessione, con una sola
open/claim/release/close, un solo OUT (`command_count=1`, il solo A8) e un solo
IN, quel primissimo IN non era l'ACK A8 atteso ma
`observed_outer_type=160` (`0xA0`), `observed_a0_control=228` (`0xE4`),
`observed_body_length=41`, senza campi ACK
(`observed_ack_echo=-1`, `observed_ack_status=-1`, `ack_count=0`,
`typed_response_count=0`). Il parser ha fallito chiuso con
`protocol_failure_kind=TYPED_SHAPE_MISMATCH` in `protocol_failure_phase=A8` e la
run si è chiusa a `phase_trace=A8,TERMINAL` con cleanup completo, zero
retry/reopen/reset, zero scritture persistenti e secret azzerato. Il
`control=0xE4` e la lunghezza di 41 byte coincidono con control e lunghezza
della typed response E4 canonica; il body completo non è stato telemetrizzato e
quindi non è stato verificato byte-exact. Il fenomeno del re-entry non è dunque
più soltanto un rischio architetturale: è **osservato sul target**.

L'identità causale resta però non provata. Il frame è stato rifiutato in fase A8
per control inatteso, quindi i 41 byte non sono stati confrontati con il
validator corrente; e nemmeno un confronto byte-esatto discriminerebbe, perché il
validator E4 deriva dal materiale protetto persistente pinnato per SHA-256 ed è
identico fra le run, senza componente per-run. Il wire A0 non porta nonce,
session ID, epoch o timestamp causale. Restano quindi compatibili, e non
discriminabili con questa telemetria, il residuo cross-session della typed
response E4 mai letta dalla prima run, un'emissione tardiva/non quiescente
device-side, un dato pending/bufferizzato endpoint/kernel/host-controller o
un'altra origine device-side non discriminabile. La prima spiegazione è la più
naturale e ora fortemente corroborata, non provata.

La catena epistemica canonica è pertanto:

```text
D278/04 static audit
  → gap architetturale host/device provenance (PROVEN staticamente)
  → seconda single-shot (autorizzazione consumata, nessun retry)
  → nuova sessione in A8 riceve A0/E4/body41
  → fenomeno target OBSERVED
  → causal identity con la precedente typed response E4 ancora UNPROVEN
```

La seconda run non ritesta il correttivo ACK: con un solo comando inviato non ha
raggiunto l'E4 della sessione corrente e non ha ricevuto alcun ACK. Il correttivo
non è né refutato né riprovato live, e per la prima run resta valida la causa ACK
C/D238 già documentata con status E4 corrente non telemetrizzato.

```text
H1_HISTORICAL_GENERIC_PRE_A8_DRAIN=DISPROVEN
H2_A8_CROSS_SESSION_SYNCHRONIZER=UNRESOLVED
H3_D266_CROSS_SESSION_PROVENANCE=DISPROVEN
H4_MULTI_IMAGE_CROSS_SESSION_REENTRY=DISPROVEN
H5_NATIVE_GENERATION_FENCING_SUFFICIENT=DISPROVEN
H6_CROSS_SESSION_RX_RESIDUAL_CURRENT_EXPLANATION=STRONGLY_LIVE_CORROBORATED_CAUSAL_IDENTITY_UNPROVEN
CROSS_SESSION_REENTRY_ARCHITECTURAL_GAP=PROVEN
TARGET_UNEXPECTED_PRIOR_PHASE_SHAPE_AT_REENTRY=OBSERVED
OBSERVED_REENTRY_FRAME_OUTER=0xA0
OBSERVED_REENTRY_FRAME_CONTROL=0xE4
OBSERVED_REENTRY_FRAME_BODY_LENGTH=41
OBSERVED_REENTRY_FRAME_MATCHES_CANONICAL_E4_CONTROL_AND_LENGTH=true
CROSS_SESSION_RX_RESIDUAL_TARGET_HYPOTHESIS=STRONGLY_LIVE_CORROBORATED
CROSS_SESSION_RX_RESIDUAL_CAUSAL_IDENTITY=UNPROVEN
ACK_POLICY_CORRECTIVE_REFUTED=false
ACK_POLICY_CORRECTIVE_LIVE_RETESTED=false
SAFE_READ_ONLY_RESYNC_DESIGN=NOT_IMPLEMENTED_DESIGN_REVIEW_REQUIRED
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
DO_NOT_RUN_AGAIN=true
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
TARGET_E4_NATIVE_LIVE_PROVEN=false
TARGET_TLS_NATIVE_LIVE_PROVEN=false
NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_OF_D278_04_POST_SECOND_LIVE_EVIDENCE_THEN_DESIGN_REVIEW_OF_BOUNDED_READ_ONLY_CROSS_SESSION_REENTRY_DISCRIMINATION
```

Non è giustificato né implementato alcun pre-A8 blind read, discard-until-A8,
timeout-drain, clear-halt, reset, reopen, retry o parser permissivo: un frame
inatteso resta evidenza finché non esiste un discriminante sicuro, e la seconda
run lo dimostra proprio conservandolo fail-closed invece di scartarlo. D278/04
lasciava quindi aperta una **design review** su una discriminazione read-only,
bounded e fail-closed del primissimo IN di una nuova sessione, senza comandi
aggiuntivi, reset/clear-halt/reopen/retry, parser permissivo o perdita di
evidenza; D278/05 qui sotto chiude quella review senza implementare una live.
Nessuna nuova run equivalente è ammessa: l'autorizzazione live è
consumata, `RETRY_AUTHORIZED=false` e una futura diagnostica richiederebbe
progettazione, review e autorizzazione separate. Il report canonico è
`analysis/D278/D278_04_cross_session_protocol_reentry_audit.md`.

### D278/05 — causal cut pre-OUT, recovery OEM e sticky `POISONED`

D278/05 ricostruisce separatamente i due terminal point. Nella prima
single-shot A8 OUT, ACK e typed APP12509 furono consumati; E4 OUT fu trasmesso
e il primo frame E4 venne consumato ma non accettato, mentre la typed E4 non fu
mai consumata. Essa è il candidato residuale più forte, senza prova che fosse
già prodotta o che il successivo `A0/E4/body41` fosse causalmente proprio quel
frame. Nella seconda single-shot il nuovo A8 era già stato trasmesso prima del
terminale: dopo quella run il set dei candidati comprende quindi anche ACK e
typed A8 correnti non letti. Un futuro A8 non potrebbe distinguere una coppia
A8 precedente da una corrente, perché A0/B0 non portano nonce, session ID,
epoch o timestamp causale:

```text
POST_A8_WIRE_CAUSAL_PROVENANCE=UNAVAILABLE
CROSS_SESSION_RX_RESIDUAL_CAUSAL_IDENTITY=UNPROVEN
```

Il causal cut valido è più debole: dopo nuovo open/claim, ma prima di qualunque
OUT della nuova command stream, un frame ricevuto non può essere causato da un
comando host corrente. Non ne segue che appartenga certamente alla sessione
precedente; restano possibili emissione autonoma o tardiva e buffering non
localizzato.

```text
PRECOMMAND_FRAME_EXCLUDES_CURRENT_HOST_COMMAND_CAUSATION=true
PRECOMMAND_FRAME_PREVIOUS_SESSION_IDENTITY=UNPROVEN
```

Un futuro diagnostico zero-OUT è metodologicamente diverso dalle due D278/03 e
merita review separata: un solo bulk-IN bounded prima di ogni OUT, al più un
frame completo, poi cleanup e stop. Un frame proverebbe dati disponibili prima
della causalità host-command corrente ma verrebbe consumato, non osservato con
un peek. Un timeout proverebbe soltanto assenza di un frame completo nel bound,
non FIFO vuota permanente, quiescenza APP12509 o readiness per A8. Frame
parziale/extra/concatenato è terminale; nessun loop o drain è ammesso.

```text
FUTURE_ZERO_OUT_PRECOMMAND_DIAGNOSTIC=JUSTIFIED_FOR_SEPARATE_REVIEW
PRECOMMAND_SILENCE_DOES_NOT_PROVE_DEVICE_PROTOCOL_QUIESCENCE=true
ZERO_OUT_DIAGNOSTIC_IMPLEMENTED=false
```

L'audit OEM locale non chiude la recovery pre-D1. Il cold-start Windows prova
la sequenza normale e D231 prova A2 `{01,14}` come reset volatile del sensore,
non il suo uso dopo failure A8/E4. `gfusb.dll` contiene retry generici, un
branch `SetDriverState` descritto come hard reset MCU, handler D0 e primitive
reset; manca però il call-flow dal failure A8/E4 alla policy superiore e manca
una capture/log target di init failure. D255/D256 prova cancel/re-entry nella
diversa fase FDT post-D1 senza reset USB osservato, non recovery da failure
pre-D1.

```text
OEM_PRE_D1_FAILURE_RECOVERY=UNRESOLVED
```

Infine l'audit del production-shaped C ha confermato una discrepanza reale:
`activate()` azzerava `terminal_fence` e `poisoned`, permettendo a una nuova
activation di cancellare il poison senza recovery dimostrata. Il correttivo
host-only ora fallisce chiuso all'ingresso di `activate()` quando il contesto è
poisoned, prima di generation, cancellable, backend command o submit USB; non
azzera più il poison. Il micro-correttivo successivo ha inoltre chiuso il path
cancellation durante `ACTIVATING`: `on_activation_cancellable_cancelled()`
marca ora sticky `poisoned`, perché il flusso corrente ha già raggiunto il
backend `arm` e `begin_generation()` e la quiescenza device-side non è provata.
Il framework continua a ricevere `G_IO_ERROR_CANCELLED` exactly-once; l'open
epoch resta poisoned fino a `img_close`, che distrugge il contesto.  Activation
pulite non cambiano comportamento.

```text
POISON_AFTER_NONQUIESCENT_TERMINAL_MUST_BE_STICKY=true
AUTOMATIC_REENTRY_FROM_POISONED=false
POISON_LIFETIME=REMAINDER_OF_OPEN_EPOCH_UNTIL_IMG_CLOSE
ACTIVATING_CANCEL_NONQUIESCENT_POISONS_OPEN_EPOCH=true
ACTIVATING_CANCEL_FRAMEWORK_ERROR=G_IO_ERROR_CANCELLED
ACTIVATION_COMPLETION_EXACTLY_ONCE=PASS
SECOND_ACTIVATION_FROM_POISONED_REJECTED=PASS
NEW_GENERATION_AFTER_POISON_COUNT=0
NEW_BACKEND_COMMAND_AFTER_POISON_COUNT=0
NEW_REAL_USB_SUBMIT_AFTER_POISON_COUNT=0
FPIMAGE_DEVICE_NORMAL=16/16_PASS
FPIMAGE_DEVICE_ASAN_UBSAN=16/16_PASS
D276_04_NORMAL_AND_ASAN_UBSAN=5/5_PASS_EACH
D276_03_ROUTER_NORMAL_AND_ASAN_UBSAN=8/8_PASS_EACH
REAL_USB_ACCESS=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
```

Il modello minimo distingue `CLEAN`, `POISONED`, il solo futuro e
non-production `REENTRY_OBSERVATION_CANDIDATE` e `TERMINAL`. Da `POISONED` sono
ammessi solo cleanup/drain host e close; sono vietati activation, generation,
command, submit, retry, TLS restart e reopen implicito. Nessun resume production
è autorizzato. Il report completo è
`analysis/D278/D278_05_cross_session_reentry_resolution.md`.

### D278/06 — observer precommand zero-OUT: closure host-only e live consumata

D278/06 ha implementato il diagnostico separato senza toccare il path
secure-session D278/03. `GoodixD278PrecommandObserver` espone un solo start,
ammette esclusivamente IN e classifica il buffer di una sola completion come
unità indivisibile. Timeout, errore, frame completo/parziale o concatenato sono
terminali; non esistono OUT, TLS, retry, reopen, reset, clear-halt o secondo
receive. La closure sintetica originaria resta `PASS_HOST_ONLY`.

La successiva review AI-PM ha approvato la baseline completa
`1682e01bcc2817f5a0b5028ab6bf4bcac32a61d0` per una sola live. Il target gate
ha verificato un unico `27c6:5125` riferendo la prova APP12509 pregressa
D277/02; la revisione firmware corrente non è stata riletta perché richiederebbe
A8 e contaminerebbe il causal cut.

La live ha sottomesso e completato un solo bulk-IN con timeout host 1000 ms,
ricevuto zero byte e terminato `TIMEOUT_NO_COMPLETE_DATA`. Open, claim, release
e close sono avvenuti una volta; cleanup e drain sono riusciti. Non vi sono
stati OUT Goodix, comandi, TLS, retry, reopen, reset, clear-halt o write
persistenti. L'autorizzazione è consumata e l'osservazione equivalente non va
ripetuta.

`VALID_SINGLE_SHOT_TIMEOUT_NO_DATA` è un risultato metodologicamente valido,
non un failure del launcher. Dimostra solo che nessun backlog precommand è
stato consegnato entro quella singola finestra. Non prova endpoint vuoto
permanente, assenza di emissioni tardive, quiescenza APP12509, identità di una
sessione precedente o readiness per A8.

```text
D278_06_OUTCOME=READY
D278_06_ADVANCEMENT=REAL_EXECUTION_COMPLETED_ONE_ZERO_OUT_ONE_IN_BOUNDED_OBSERVATION_WITH_NO_DATA_WITHIN_1000MS
D278_06_EXECUTABLE_CLOSURE=PASS_HOST_ONLY
HOST_ONLY_CLOSURE=PASS
LIVE_EXECUTION_RESULT=VALID_SINGLE_SHOT_TIMEOUT_NO_DATA
D278_06_LIVE_EXECUTION_PERFORMED=true
D278_06_LIVE_EXECUTION_COUNT=1
D278_06_LIVE_BASELINE=1682e01bcc2817f5a0b5028ab6bf4bcac32a61d0
D278_06_PHYSICAL_BULK_IN_SUBMIT_COUNT=1
D278_06_PHYSICAL_BULK_IN_COMPLETION_COUNT=1
D278_06_RECEIVED_BYTE_COUNT=0
D278_06_GOODIX_BULK_OUT_SUBMIT_COUNT=0
D278_06_GOODIX_COMMAND_COUNT=0
D278_06_TLS_HANDSHAKE_COUNT=0
D278_06_TIMEOUT_COUNT=1
D278_06_USB_OPEN_COUNT=1
D278_06_USB_CLAIM_COUNT=1
D278_06_USB_RELEASE_COUNT=1
D278_06_USB_CLOSE_COUNT=1
D278_06_BACKEND_DRAINED=true
D278_06_CLEANUP_COMPLETED=true
D278_06_RETRY_COUNT=0
D278_06_REOPEN_COUNT=0
D278_06_DEVICE_RESET_COUNT=0
D278_06_CLEAR_HALT_COUNT=0
D278_06_PERSISTENT_DEVICE_WRITE_COUNT=0
IMMEDIATE_PRECOMMAND_BACKLOG_WITHIN_1000MS=NOT_OBSERVED
DEVICE_PROTOCOL_QUIESCENCE_PROVEN=false
APP12509_READY_FOR_A8_PROVEN=false
D278_06_DO_NOT_RUN_EQUIVALENT_OBSERVATION_AGAIN=true
D278_06_CURRENT_LIVE_AUTHORIZED=false
D278_06_READY_FOR_LIVE=false
D278_06_RETRY_AUTHORIZED=false
```

Report completo: `analysis/D278/D278_06_zero_out_precommand_observation.md`.

### D278/07 — recovery OEM pre-D1: A8 risolta, E4 bloccata (stato storico, superato da D278/08)

D278/07 ha ricostruito offline `gfusb.dll` 1.1.125.14 distinguendo il project
target 8 dai percorsi generici. La policy A8 è target-specifica e chiusa:
`GetEvkVersionWithRetry` prova A8 fino al byte configurabile `N_CFG`, con
timeout response 500 ms; dopo l'esaurimento chiama `HardResetMcu`. Per project
8 l'hard reset non è supportato e il ramo invia A2 MCU-only `{02 14}`, quindi
prova una sola A8 finale. Un ulteriore failure diventa `0xffcffffd`, risale a
`_DeviceInit` e il loop esterno può ripetere l'intera init fino a `N_CFG`. Il
valore runtime concreto di `N_CFG` non è presente nel corpus.

Il sensor-only A2 `{01 14}` non appartiene a quel branch. La capture OEM
riuscita lo colloca dopo A8 ed E4 riuscite; quindi
`OEM_USES_A2_SENSOR_ONLY_AS_PRE_A8_FAILURE_RECOVERY=false` e nessun A2 pre-A8
live è giustificato.

Per E4 esiste una routine generica verificata che ritenta lo stesso send una
volta e poi restituisce `0xffdffffd`. Il target project 8 entra però nel ramo
`gfUpdatefirmware`: il grafo diretto non chiude il dispatch dall'update
all'esatto builder E4 osservato né il relativo return path di failure. Quel
wrapper comprende inoltre primitive clear/erase/update APP e reset MCU, quindi
non è un candidato Linux sicuro. La successful capture D255/D256 prova il wire
A8→E4→A2, ma non contiene failure A8/E4 né log OEM.

La recovery pre-D1 complessiva resta `UNRESOLVED`, non viene implementato alcun
candidato e non è autorizzata alcuna live. L'unico prossimo discriminante è
offline: risolvere lo slot indiretto/dataflow dal branch project 8
`init_MCU -> gfUpdatefirmware -> 0x1800656f4` all'esatto E4 e seguirne le due
uscite fino al return di `init_MCU`.

```text
OUTCOME=BLOCKED
ADVANCEMENT=NEW_STATIC_TARGET_SPECIFIC_A8_FAILURE_POLICY_CLOSED_AND_E4_TARGET_EDGE_ISOLATED_AS_THE_REMAINING_BOUNDARY
EXECUTABLE_CLOSURE=ANALYSIS_ONLY
CANONICAL_DOCUMENTATION=UPDATED
OEM_PRE_D1_FAILURE_RECOVERY=UNRESOLVED
OEM_A8_FAILURE_POLICY=RESOLVED
OEM_E4_FAILURE_POLICY=UNRESOLVED
OEM_USES_A2_SENSOR_ONLY_AS_PRE_A8_FAILURE_RECOVERY=false
A2_HOST_SEMANTICS=CONVERGED_SENSOR_ONLY_RESET
A2_PRE_A8_RECOVERY_LIVE_JUSTIFIED=false
D278_07_RECOVERY_CANDIDATE_IMPLEMENTED_HOST_ONLY=false
REAL_USB_ACCESS=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
```

Audit e matrice: `analysis/D278/D278_07_oem_pre_d1_recovery_audit.md` e
`analysis/D278/D278_07_oem_pre_d1_recovery_matrix.csv`.

### D278/08 — sender E4 project 8 e failure policy risolti; recovery OEM esclusa

D278/08 ha corretto il boundary storico D278/07. La policy A8 non viene
riaperta: resta risolta, bounded dal byte runtime
`N_CFG` ancora ignoto e non è un candidato Linux minimale perché include
retry annidati e A2 MCU-only `{02 14}`.

L'E4 del project 8 non è raggiunto da una callback o tabella indiretta dentro
`gfUpdatefirmware`. `init_MCU`, dopo il ritorno dell'updater e i suoi gate,
continua direttamente:

```text
project == 8 @ 0x18006abec
  -> gfUpdatefirmware 0x180064a18 @ 0x18006ac4c
  -> production process 0x18003c348 @ 0x18006ae04
  -> production_check_psk_is_valid 0x18003b514 @ 0x18003c499
  -> selector 0xbb020003 @ 0x18003b77b
  -> production_read_specific_data 0x18003cc90 @ 0x18003b780
  -> production_read_mcu 0x18003c7f4 @ 0x18003ce0c
  -> generic sender 0x18005c148 @ 0x18003c94c
```

Con `r8=0x0e`, `r9=0x02`, body length 8, la routine costruisce E4 con body
`03 00 02 bb 00 00 00 00`. I timeout statici sono 500 ms per ACK e 1000 ms
per typed response. Il sender ritenta immediatamente una sola volta se il
generic send ritorna zero; due zeri producono `0xffdffffd`. Errori di forma,
status o confronto del valore letto restano nonzero e risalgono al production
process.

Il production process ripete l'intera validazione al massimo due volte. Dopo
due failure non abortisce: chiama fino a due volte `0x18003cfd8`, identificata
ora correttamente come `production_write_key`, che raggiunge
`production_write_mcu` (`0x18003d8e0`) e il sender E0. Ogni write ha a sua
volta un solo retry del generic send. Ne risultano al massimo quattro E4 per
failure di trasporto prima del fallback e fino a quattro E0 nel fallback. Un
write riuscito è seguito da una nuova `production_check_psk_is_valid` a
`0x18003c6fb`; solo una revalidation E4 riuscita fa proseguire l'init. Se
entrambi i write sono accettati ma le relative revalidation falliscono per
trasporto, il massimo complessivo nel production process è otto E4. Il loop
write/recheck esaurito nonzero risale a `init_MCU`, `_DeviceInit` e al loop
esterno `InitThread` bounded da `N_CFG`.

Esiste anche rischio persistente prima dell'E4: il precedente
`gfUpdatefirmware` può raggiungere A4 Clear App e firmware update, benché la
capture successful D255/D256 abbia corroborato un singolo passaggio senza A4.
L'E4 in sé è read-only, ma il suo failure path diretto raggiunge provisioning
E0. Pertanto la policy è risolta come non factory-preserving e non è un
candidato Linux:

```text
OUTCOME=READY
ADVANCEMENT=NEW_STATIC_TARGET_SPECIFIC_DIRECT_E4_EDGE_AND_PERSISTENT_PROVISIONING_FAILURE_FALLBACK_RESOLVED
EXECUTABLE_CLOSURE=ANALYSIS_ONLY
CANONICAL_DOCUMENTATION=UPDATED
D278_08_BASELINE=4c73dcdaad5df9f9a429626109a4be2a3b1a8b19
OEM_A8_FAILURE_POLICY=RESOLVED
OEM_USES_A2_SENSOR_ONLY_AS_PRE_A8_FAILURE_RECOVERY=false
A2_PRE_A8_RECOVERY_LIVE_JUSTIFIED=false
A8_RETRY_BOUND_RUNTIME_VALUE=UNKNOWN_CONFIG_BYTE_AT_OFFSET_0x45A
PROJECT8_E4_SENDER_RESOLVED=true
PROJECT8_E4_INDIRECT_EDGE_RESOLVED=true
PROJECT8_E4_FAILURE_RETURN_PROPAGATION_RESOLVED=true
PROJECT8_E4_RETRY_BOUND_RESOLVED=true
PROJECT8_E4_PRE_FAILURE_PERSISTENT_WRITE_REACHABLE=true
PROJECT8_E4_POST_FAILURE_PERSISTENT_WRITE_REACHABLE=true
PROJECT8_E4_FAILURE_PATH_FACTORY_PRESERVING=false
OEM_E4_FAILURE_POLICY=RESOLVED
OEM_PRE_D1_FAILURE_RECOVERY=RESOLVED
LINUX_SAFE_E4_RECOVERY_CANDIDATE=false
REAL_USB_ACCESS=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
```

La conclusione D278/07 `UNRESOLVED` resta registrata come stato storico ma è
superata. Audit, grafo, edge machine-readable e verifica riproducibile:
`analysis/D278/D278_08_project8_e4_indirect_edge_audit.md`,
`analysis/D278/D278_08_project8_e4_failure_graph.md`,
`analysis/D278/D278_08_project8_e4_edges.csv` e
`analysis/D278/tools/verify_d278_08_static.py`.

### D278/09 — exact A2 sensor-only one-shot, closure host-only

D278/09 non riapre né trapianta la recovery OEM. D278/08 resta l'autorità sul
failure path E4: due check PSK falliti raggiungono
`production_write_key → production_write_mcu → E0`, mentre il surrounding
updater può raggiungere A4 Clear App e firmware update. Quella machinery resta
non factory-preserving e vietata.

Il candidato D278/09 è una decisione progettuale distinta. D231 lega nel
`gfusb.dll` 1.1.125.14 `gfresetMCUAndfingerprint(false,true,...)` al control A2
e body `{01 14}`: bit 0 reset sensore, bit 1 reset MCU, quindi `{02 14}` è una
primitiva diversa e non ammessa. La capture target D255/D256 ha già osservato
due exact `{01 14}` accettati con ACK e typed A2 sul nostro
`GF_ST411SEC_APP_12509`. Questo prova identità, semantica host e compatibilità
generale sul target, non l'uso nell'attuale re-entry/non-quiescenza.

La semantica è corroborata cross-version dal claim Rocky su `gfusb.dll`
1.1.125.13. Lo snapshot locale Rocky preservato contiene inoltre
`gx_dev_reset()` con `data[2] = {1,20}` e lo usa come SetIdle nell'init sensore.
È corroborazione esterna/implementativa, non prova primaria APP12509 e non
prova assoluta di nonmutazione NVM. Il report indipendente native 12509 nella
stessa Issue #1 corrobora uno stack Linux funzionante con firmware 12509
mantenuto, TLS, enrollment, match/no-match e PAM; non conferma però la
preservazione PSK, perché quella macchina riportava PSK assente (`status 0x01`)
e ne ha provisionata una nuova. Il commento non prova da solo una esecuzione
byte-exact A2; il collegamento al driver resta inferito.

```text
A2_SENSOR_ONLY_EXACT_BODY=01_14
A2_SENSOR_ONLY_HOST_SEMANTICS=CONVERGED_SENSOR_ONLY_RESET
A2_SENSOR_ONLY_ACCEPTED_ON_APP12509_PREVIOUSLY=true
A2_SENSOR_ONLY_PERSISTENT_MUTATION_EVIDENCE=false
A2_SENSOR_ONLY_DEVICE_NVM_NONMUTATION_ABSOLUTELY_PROVEN=false
ROCKY_12513_A2_SENSOR_ONLY_SEMANTICS_CORROBORATES_LOCAL=true
ROCKY_12513_A2_NVM_SAFETY_CLAIM=EXTERNAL_CORROBORATION_ONLY
INDEPENDENT_12509_STACK_SUCCESS=CORROBORATING_CONTEXT
INDEPENDENT_12509_EXACT_A2_EXECUTION=NOT_BYTE_EXACTLY_PROVEN_FROM_COMMENT_ALONE
HISTORICAL_PRE_LIVE_RESIDUAL_RISK_CLASS=CURRENT_REENTRY_CONTEXT_ONLY_WITH_DEVICE_SIDE_NVM_ABSOLUTE_PROOF_MISSING
CURRENT_RESIDUAL_RISK_CLASS=POST_A2_A8_REENTRY_BEHAVIOR_UNPROVEN_WITH_DEVICE_SIDE_NVM_ABSOLUTE_PROOF_MISSING
```

Il probe dedicato riusa `goodix_a0_build_frame()` e costruisce l'unico wire
`a0 06 00 a6 a2 03 00 01 14 f0`. Non istanzia `GoodixSecureSession`, router o
TLS e non legge PSK/store. Dopo l'unico OUT ammette al massimo due IN fisici:
ACK A2 strict con status `0x01|0x07`, poi typed A2 di tre byte con hash target
pinnato. Timeout in qualunque fase, typed missing dopo ACK, mismatch, E4/A8
inatteso, errore, callback stale o secondo start sono terminali; non esistono
discard, drain generico, retry, A8 o altro comando successivo.

```text
GOODIX_COMMAND_SUBMIT_MAX=1
GOODIX_BULK_OUT_SUBMIT_MAX=1
A2_SENSOR_ONLY_SUBMIT_MAX=1
PHYSICAL_BULK_IN_SUBMIT_MAX=2
PHYSICAL_BULK_IN_COMPLETION_MAX=2
A8_SUBMIT_MAX=0
E4_SUBMIT_MAX=0
A2_MCU_ONLY_SUBMIT_MAX=0
TLS_HANDSHAKE_COUNT=0
RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
```

Il launcher live-capable è compilato `UNAPPROVED_FOR_LIVE` e richiede, prima
della creazione del contesto GUsb, full SHA compile-time approvata, identica
full SHA runtime, token operatore e operation name D278/09 esatti. Non è stata
auto-selezionata una baseline. Il gate descriptor futuro richiede un solo
`27c6:5125` e dichiara separatamente prova APP12509 D277/02 pregressa,
precedente successo exact A2 e mancata rilettura firmware corrente: A8 non
contamina il probe.

Le suite focali della closure originaria passano 9/9 per due run normali
deterministiche e 9/9 ASAN/UBSAN; self-test, strict build, forbidden
call/control audit e gate pre-USB passano. La regressione
secure-session/codec passa 11/11 normal e 11/11 ASAN/UBSAN. Queste verifiche
erano host-only e non avevano creato contesti USB reali.

La successiva singola live autorizzata è stata eseguita una volta sulla
baseline `1c40f6b7b7282ca6e0a39a2c3e2d8672d9544dd6` ed è consumata. Ha
prodotto open/claim/release/close `1/1/1/1`, command/OUT `1/1`, IN
submit/completion `2/2`, ACK echo `0xA2`, status `0x07`, typed control `0xA2`,
body length 3 e target pin strict match. Timeout, retry, reopen, extra USB
reset, clear-halt, persistent write, TLS, frame inattesi e callback stale sono
zero; backend e cleanup sono completi.

```text
D278_09_LIVE_OUTCOME=PASS
D278_09_LIVE_BASELINE=1c40f6b7b7282ca6e0a39a2c3e2d8672d9544dd6
A2_SENSOR_ONLY_ACCEPTED_IN_CURRENT_CONTEXT=true
A2_SENSOR_ONLY_LIVE_ACK_ECHO=0xA2
A2_SENSOR_ONLY_LIVE_ACK_STATUS=0x07
A2_SENSOR_ONLY_LIVE_TYPED_CONTROL=0xA2
A2_SENSOR_ONLY_LIVE_TYPED_BODY_LENGTH=3
A2_SENSOR_ONLY_LIVE_TYPED_TARGET_PIN_MATCH=true
A2_SENSOR_ONLY_LIVE_RETRY_COUNT=0
A2_SENSOR_ONLY_LIVE_PERSISTENT_WRITE_COUNT=0
A2_SENSOR_ONLY_LIVE_CLEANUP_COMPLETE=true
D278_09_ONE_SHOT_CONSUMED=true
D278_09_RERUN_AUTHORIZED=false
CURRENT_REENTRY_CONTEXT_REJECTS_EXACT_A2_SENSOR_ONLY=false
CURRENT_REENTRY_CONTEXT_ACCEPTS_EXACT_A2_SENSOR_ONLY=true
```

`0x07` è classificato successo perché appartiene alla allowlist canonica e il
typed target-pinned successivo è strict match; non è disponibile una semantica
bit-level dimostrata. La live non prova nonmutazione NVM assoluta, readiness
A8, soluzione della re-entry, quiescenza permanente dell'endpoint o assenza di
emissioni tardive. `device_reset_count=0` esclude primitive USB/device-reset
aggiuntive, non il comando A2 sensor-only contato separatamente.

Riesame metodologico: (1) rispetto a D278/03 non si ripete A8/secure-session e
rispetto a D278/06 non si ripete il receive zero-OUT; si invia soltanto il noto
A2 sensor-only e si leggono le sue sole risposte bounded; (2) la nuova ipotesi
è l'accettazione dello stesso exact A2 nell'attuale stato contestuale; (3) un
nuovo failure non porta a resend o A8, ma a stop e analisi offline di un
discriminante diverso. Report completo:
`analysis/D278/D278_09_a2_sensor_only_risk_probe.md`.

### D278/10 — discriminante same-session A2→A8, closure host-only e singola live consumata

D278/10 mantiene congelati il probe A2 D278/09 e il secure-session D278/03.
Il path dedicato riusa l'exact A2 `a00600a6a203000114f0`, l'exact A8
target-proven `a00600a6a803000000ff` e il codec A0 canonico. Nella stessa open
epoch accetta soltanto A2 OUT, ACK A2 strict, typed A2 target-pinned, A8 OUT,
ACK A8 strict e typed A8 byte-identical a `GF_ST411SEC_APP_12509` incluso il
terminatore NUL, poi cleanup e stop.

A8 è irraggiungibile se ACK o typed A2 falliscono. Timeout, mismatch, frame
fuori fase, errore, callback stale o duplicata sono terminali; non esistono
drain, discard-until-expected, precommand observation, retry, secondo A2,
secondo A8, E4, secure session, TLS, reset, clear-halt o reopen.

```text
GOODIX_COMMAND_SUBMIT_MAX=2
GOODIX_BULK_OUT_SUBMIT_MAX=2
A2_SENSOR_ONLY_SUBMIT_MAX=1
A8_SUBMIT_MAX=1
PHYSICAL_BULK_IN_SUBMIT_MAX=4
PHYSICAL_BULK_IN_COMPLETION_MAX=4
E4_SUBMIT_MAX=0
A2_MCU_ONLY_SUBMIT_MAX=0
TLS_HANDSHAKE_COUNT=0
RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
```

La build ordinaria resta `UNAPPROVED_FOR_LIVE`. Il gate richiede prima della
creazione del contesto GUsb full SHA compile-time approvata, la stessa SHA
runtime, token D278/10 e operation name D278/10 esatti. D278/10 non sceglie
una baseline live e l'autorizzazione D278/09 non è trasferibile.

La matrice focalizzata originaria passa 14/14 per due run normali
deterministiche e 14/14 ASAN/UBSAN; strict build, self-test, launcher
live-capable, gate unapproved pre-USB e forbidden command/call/symbol audit
passano. Il self-test conferma 2 command/OUT, un A2, un A8, quattro IN,
entrambi i contratti ACK+typed e exact APP12509. Questa closure preparatoria
era host-only.

La successiva singola live è stata eseguita dall'operatore sulla baseline
approvata `529e98626421b3f3fc1e85f9a25c5e938b357482` ed è consumata. Una sola
open/claim/release/close ha trasmesso due comandi e due OUT: exact A2 `{01 14}`
ha ricevuto ACK `0x07` e typed A2 target-pinned strict; A8 ha poi ricevuto ACK
`0x07` e typed byte-identical a `GF_ST411SEC_APP_12509`. I quattro IN sono
stati tutti completati. Timeout, frame inattesi, callback stale, retry, reopen,
reset, clear-halt, write persistenti e TLS sono rimasti a zero; backend e
cleanup sono completi.

Il precedente `new open epoch → A8 → A0/E4-shaped` non si è ripetuto dopo il
completamento strict A2 nella stessa open epoch. È quindi provata l'efficacia
pratica di A2 per ristabilire A8 nel target/context corrente. Non sono provati
il meccanismo causale, una necessità universale, la safety su ogni firmware,
la nonmutazione NVM assoluta o la provenance causale assoluta dei byte.

```text
SAME_SESSION_A2_COMPLETION_PROVIDES_STRONGER_CAUSAL_ANCHOR_BEFORE_A8=true
POST_A2_A8_RESPONSE_CAUSAL_PROVENANCE_ABSOLUTE=false
A2_A8_REENTRY_PROBE_IMPLEMENTED=true
A2_A8_REENTRY_PROBE_LIVE_CAPABLE=true
A2_A8_REENTRY_PROBE_LIVE_EXECUTED=true
D278_10_LIVE_OUTCOME=PASS
D278_10_LIVE_BASELINE=529e98626421b3f3fc1e85f9a25c5e938b357482
D278_10_USB_OPEN_CLAIM_RELEASE_CLOSE=1/1/1/1
D278_10_GOODIX_COMMAND_COUNT=2
D278_10_PHYSICAL_IN_SUBMIT_COMPLETION=4/4
D278_10_A2_ACK_STATUS=0x07
D278_10_A2_TYPED_RESULT_CLASS=STRICT_MATCH
D278_10_A8_ACK_STATUS=0x07
D278_10_A8_TYPED_RESULT_CLASS=STRICT_MATCH
D278_10_A8_APP12509_PIN_MATCH=true
D278_10_UNEXPECTED_FRAME_COUNT=0
D278_10_RETRY_REOPEN_RESET_CLEAR_HALT_PERSISTENT_WRITE=0/0/0/0/0
D278_10_BACKEND_DRAINED=true
D278_10_CLEANUP_COMPLETED=true
D278_10_ONE_SHOT_CONSUMED=true
D278_10_RERUN_AUTHORIZED=false
A2_SENSOR_ONLY_ACCEPTED_IN_CURRENT_CONTEXT=true
SAME_SESSION_A2_THEN_A8_APP12509_TARGET_PROVEN=true
A2_SENSOR_ONLY_REENTRY_RECOVERY_EFFECTIVE_FOR_A8_ON_CURRENT_TARGET_CONTEXT=true
A2_REENTRY_RECOVERY_CAUSAL_MECHANISM=UNKNOWN
A2_DEVICE_NVM_NONMUTATION_ABSOLUTELY_PROVEN=false
WIRE_CAUSAL_PROVENANCE_ABSOLUTE=false
REAL_USB_ACCESS=true
LIVE_EXECUTION_PERFORMED=true
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
```

Report completo:
`analysis/D278/D278_10_same_session_a2_a8_reentry_discriminator.md`.

### D278/11 — prefisso re-entry recovery nel secure-session nativo, solo host-only

D278/11 integra nella state machine nativa esistente una fase iniziale
esplicita `REENTRY_RECOVERY_A2`, senza creare un secondo stack:

```text
REENTRY_RECOVERY_A2 {01 14}
→ A8 → E4 → OEM_COLD_START_A2_1 → 82 → A6
→ OEM_COLD_START_A2_2 → 70 → 80×4 → 90 → D1 → TLS → STOP
```

Il prefisso usa il builder A0 canonico, body exact `{01 14}`, allowlist ACK
`0x01|0x07` e lo stesso SHA-256 target-pinned della typed A2 D278/09–10. A8
resta pin byte-exact APP12509; E4, 82, A6, CONFIG90, D1/B0 e TLS conservano i
gate precedenti. La nomenclatura e la telemetria separano la policy progettuale
dalle due A2 OEM: `REENTRY_RECOVERY_A2_OEM_EQUIVALENCE=false` e
`REENTRY_RECOVERY_A2_PROJECT_POLICY=true`.

Timeout, ACK errato, typed mancante/mismatch o E4 inatteso durante il recovery
sono terminali prima di A8. Un failure A8 è terminale prima di E4. Ogni failure
successivo chiude senza retry, reopen, reset, clear-halt, fallback OEM o
primitive persistenti. Secondo start, completion duplicata e callback stale
non possono inviare un secondo A2/A8 o avanzare due volte.

Il command budget massimo è 14 A0 Goodix: un recovery A2, A8, E4, due A2 OEM,
82, A6, 70, quattro 80, 90 e D1. Nel peer OpenSSL deterministico host-only il
path completo esegue 18 IN e 19 OUT fisici (14 A0 più 5 chunk B0), con massimo
un IN e un OUT outstanding. I contatori phase-specific risultano recovery
`1/1/1/STRICT_MATCH`, A8 `1/1/1/pin=true` e A2 OEM submit `1/1`.

Le suite passano per due invocazioni consecutive: secure-session focalizzata
12/12 normal e 12/12 ASAN/UBSAN; composizione completa 62/62 normal e 62/62
ASAN/UBSAN. Sono coperti R1–R12, inclusi watchdog recovery, mismatch/timeout,
E4 inatteso, A8 failure, duplicate/stale, secondo start, failure nelle fasi
esistenti, regressione TLS e audit source/symbol delle primitive proibite. Il
launcher resta `UNAPPROVED_FOR_LIVE`; il gate D278/11 richiede full SHA
compile-time e runtime identiche più token/operation esatti e ferma la build
ordinaria prima di materiali protetti, contesto GUsb ed enumerazione.

```text
D278_11_BASELINE=529e98626421b3f3fc1e85f9a25c5e938b357482
NATIVE_SECURE_SESSION_REENTRY_PREFIX_IMPLEMENTED=true
NATIVE_SECURE_SESSION_REENTRY_PREFIX_HOST_ONLY_PROVEN=true
REENTRY_RECOVERY_A2_SUBMIT_MAX=1
A8_SUBMIT_MAX=1
E4_SUBMIT_MAX=1
A2_MCU_ONLY_SUBMIT_MAX=0
HOST_ONLY_FULL_PATH_GOODIX_COMMAND_SUBMIT_MAX=14
HOST_ONLY_FULL_PATH_PHYSICAL_IN_SUBMIT_COUNT=18
HOST_ONLY_FULL_PATH_PHYSICAL_OUT_SUBMIT_COUNT=19
MAX_PHYSICAL_IN_OUTSTANDING=1
MAX_PHYSICAL_OUT_OUTSTANDING=1
RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
FUTURE_REENTRY_PREFIXED_NATIVE_SECURE_SESSION_LIVE_READY_FOR_AI_PM_REVIEW=true
REAL_USB_ACCESS=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
```

Il report Git-native è
`analysis/D278/D278_11_reentry_prefixed_native_secure_session_host_only.md`.

La successiva esecuzione live D278/11, autorizzata come singola one-shot sulla
baseline completa `b704d52ccc292c4fc669373c7eb8d8b296518ff7`, ha chiuso il
confine target-specific che il report host-only lasciava aperto. L'esatta
traccia osservata è:

```text
REENTRY_RECOVERY_A2,A8,E4,OEM_COLD_START_A2_1,CHIP_82,OTP_A6,
OEM_COLD_START_A2_2,MODE_70,DAC_220,DAC_236,DAC_238,DAC_23A,
CONFIG_90,D1,TLS,STOP
```

La run ha prodotto `14` comandi Goodix, `13` ACK, `8` risposte tipate, un
handshake TLS e un solo handoff del secret; open/claim/release/close sono
ciascuno `1`. Il materiale posseduto dal progetto è stato zeroizzato, backend
e cleanup sono terminati correttamente. Retry, reopen, reset, clear-halt,
scritture persistenti, application data, finger, image sono rimasti a zero.
La run ha contato `26` submit IN fisici e `19` OUT fisici, con massimo uno
outstanding per direzione. Il riferimento sintetico aveva `18` IN e `19` OUT:
la differenza IN è frammentazione/completion fisica osservata e non modifica
la sequenza logica A0/B0, validata dal router incrementale. Non si promuovono
la causalità interna di A2, la sua necessità universale o una prova assoluta di
nonmutazione NVM.

```text
D278_11_LIVE_BASELINE=b704d52ccc292c4fc669373c7eb8d8b296518ff7
D278_11_LIVE_OUTCOME=PASS
D278_11_ONE_SHOT_CONSUMED=true
D278_11_RERUN_AUTHORIZED=false
D278_11_LIVE_COMMAND_COUNT=14
D278_11_LIVE_ACK_COUNT=13
D278_11_LIVE_TYPED_RESPONSE_COUNT=8
D278_11_LIVE_TLS_HANDSHAKE_COUNT=1
D278_11_LIVE_SECRET_HANDOFF_COUNT=1
D278_11_LIVE_PHYSICAL_IN_SUBMIT_COUNT=26
D278_11_LIVE_PHYSICAL_OUT_SUBMIT_COUNT=19
D278_11_LIVE_MAX_OUTSTANDING_IN=1
D278_11_LIVE_MAX_OUTSTANDING_OUT=1
REAL_USB_RX_FRAGMENTATION_DIFFERS_FROM_SYNTHETIC_REFERENCE=OBSERVED
LOGICAL_PROTOCOL_SEQUENCE_UNAFFECTED=true
REENTRY_PREFIXED_NATIVE_SECURE_SESSION_TARGET_PROVEN=true
REENTRY_RECOVERY_A2_TO_TLS_TARGET_PROVEN=true
NATIVE_TLS12_PSK_HANDSHAKE_WITH_REENTRY_RECOVERY_TARGET_PROVEN=true
```

### D278/12 — secure-session reentry-prefixed fino al secondo B0, composizione C host-only

D278/12 non esegue USB reale e non abilita il VID:PID production. Introduce un
lifecycle LGPL indipendente posseduto dal `GoodixDeviceContext` già esistente.
Al callback di fase `STOP`, e soltanto con coda TLS ed OUT drenati, il
secure-session cede il callback di completion dello stesso backend; lo stesso
oggetto `GoodixTlsServer` resta proprietario della decifratura B0 per tutto il
post-TLS. Gli A0 successivi sono instradati al lifecycle, mentre il plaintext
applicativo TLS è consegnato per callback, senza polling o flag globale.

```text
GoodixDeviceContext
  -> un GoodixFpiUsbBackend / un GoodixUsbRouter / una generation
  -> GoodixSecureSession: REENTRY_RECOVERY_A2 ... D1 -> TLS -> STOP
  -> handoff callback-driven a egress drenato
  -> GoodixPostTlsLifecycle: D4 -> AF -> fresh FDT -> IRQ2 -> 0x22
     -> first B0/image -> 0x34 -> IRQ0200 -> 0x20/post-up B0
     -> 0x50/NAV -> gate AWAIT_FINGER_ON + release + fresh down-table
     -> 0x32 -> second IRQ2 -> 0x22 -> second B0/image -> STOP
```

Il lifecycle deriva la FDT-up esclusivamente dall'IRQ `0x0002`/flags `0x003f`
del primo ciclo come coppie `0x80,((raw>>1)+0x1d)` e la down-table
esclusivamente dall'IRQ `0x0200`/flags `0` dello stesso ciclo come coppie
`0x80,(raw>>1)`. Overflow, shape/IRQ/flags errati, tabella stale, generation
stale o cancel sono terminali. Il rearm viene emesso esattamente una volta
solo dopo release completa, fresh down-table e stato framework
`AWAIT_FINGER_ON`; il post-up B0 è consumato e scartato e non raggiunge il
decoder immagine.

La soglia della risposta tipizzata `0x82` alimenta davvero la policy di
classificazione: vengono calcolati i delta assoluti dei sei word FDT tra prima
e seconda lettura e tra seconda e terza lettura. L'arm finale è ammesso solo
dopo entrambe le classificazioni nella generation corrente. La classe
within/outside resta telemetria host-side e non altera wire, payload o blocking,
coerentemente con il confine D259; il vettore D278/12 produce due classificazioni
within soglia `0x20` e zero outside.

Il decoder C clean-room accetta il contratto canonico
`7693 -> 7690 -> 7689 -> 5+7684 -> 7680+4`, applica il marker image-specific
`0x88`, CRC-32/MPEG-2 strict, unpack packed-12 e mapping wire→raster `80x64`.
Il plaintext immagine può essere frammentato dalle chiamate `SSL_read_ex`: il
lifecycle lo ricompone secondo la length dichiarata prima del decode e azzera
il buffer temporaneo. Nel `GoodixDeviceContext` entrambi i raster passano al
medesimo helper `goodix_fpimage_pipeline_new()` e quindi a un vero `FpImage`.
Orientation, polarity e ppmm fisico rimangono irrisolti.

La fixture composta completa un handshake OpenSSL TLS 1.2 PSK reale in memoria
attraverso il prefisso reentry, mantiene la stessa identità del TLS/backend e
invia cifrati bootstrap B0, prima immagine, post-up B0 e seconda immagine fino
allo stop. La fixture lifecycle separata varia i confini fisici (header/body
spezzati, ACK+typed concatenati e conteggi IN diversi da 18) preservando lo
stesso transcript logico. I test focalizzati passano normal e ASAN/UBSAN; le
regressioni secure-session D278/11, router, pipeline FpImage, D275 e shell
`FpImageDevice` passano. Nessun simbolo di reset/clear-halt, secondo TLS o
provenance GPL è raggiungibile dai nuovi moduli LGPL.

```text
D278_12_BASELINE=b704d52ccc292c4fc669373c7eb8d8b296518ff7
POST_TLS_TWO_ACQUISITION_NATIVE_C_INTEGRATION_IMPLEMENTED=true
REENTRY_PREFIXED_NATIVE_C_TO_SECOND_B0_HOST_ONLY_PROVEN=true
SAME_OPEN_EPOCH_USB_OWNER_HOST_ONLY_PROVEN=true
SAME_TLS_SESSION_THROUGH_SECOND_B0_HOST_ONLY_PROVEN=true
TLS_HANDSHAKE_COUNT_MAX=1
SECRET_HANDOFF_COUNT_MAX=1
TRANSPORT_REOPEN_COUNT=0
FIRST_IMAGE_PIPELINE_HOST_ONLY_PROVEN=true
SECOND_B0_LIFECYCLE_HOST_ONLY_PROVEN=true
SECOND_IMAGE_PIPELINE_HOST_ONLY_PROVEN=true
SECOND_IMAGE_RASTER_TARGET_PROVEN=false  # HISTORICAL_SCOPE; SUPERSEDED_BY_D278_14_LIVE_12_CURRENT_TRUE
RELEASE_TAIL_ORDER_HOST_ONLY_PROVEN=true
FRESH_SAME_CYCLE_DOWN_TABLE_GATE_HOST_ONLY_PROVEN=true
REARM_EXACTLY_ONCE_HOST_ONLY_PROVEN=true
THIRD_CYCLE_COMMAND_COUNT=0
PHYSICAL_RX_FRAGMENTATION_INVARIANCE_HOST_ONLY_PROVEN=true
MAX_PHYSICAL_IN_OUTSTANDING=1
MAX_PHYSICAL_OUT_OUTSTANDING=1
RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
ENROLLMENT_STAGE_POLICY=NOT_SELECTED
REAL_USB_ACCESS=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
FUTURE_REENTRY_PREFIXED_NATIVE_TWO_ACQUISITION_LIVE_READY_FOR_AI_PM_REVIEW=false
```

Il secondo B0 è target-proven dalla run D275/04, ma quella run non ha
serializzato o validato come evidenza una seconda raster. D278/12 prova invece
host-only che una seconda immagine sintetica valida attraversa decoder C e
pipeline `FpImage`; una prova target della seconda raster richiederebbe nuova
evidenza live separata e nuova autorizzazione, oggi assente. Il report
Git-native è
`analysis/D278/D278_12_reentry_secure_session_to_two_acquisition_host_only.md`.

### D278/13 — binding fisico-shaped dell'unico percorso integrato, pre-live host-only

Il gap architetturale residuo di D278/12 era nel punto di ingresso: la fixture
end-to-end componeva manualmente oggetti compatibili, mentre il tool live
storico D278/11 possedeva un harness distinto e terminava al TLS. D278/13 non
estende quel tool. Intendeva invece esporre una costruzione harness-only del
`GoodixFpImageDevice` non registrato su un `GUsbDevice` già selezionato e una
epoch operator bounded sul suo unico `GoodixDeviceContext`; la closure
host-only di quello step non esercitava però la property con un `GUsbDevice`
non nullo e non provava il binding fisico effettivo. Il context crea e
mantiene una sola istanza di:

```text
GoodixDeviceContext
  -> GoodixFpiUsbBackend -> GoodixUsbRouter -> un owner IN fisico
  -> GoodixSecureSession -> GoodixTlsServer (un handshake/un handoff)
  -> handoff dello stesso backend soltanto dopo drain TLS OUT
  -> GoodixPostTlsLifecycle -> decoder -> goodix_fpimage_pipeline_new()
  -> STOP dopo la seconda pipeline -> cancel/fence -> drain -> release/close
```

`tools/d278_integrated_path_once.c` è solo glue GPL: seleziona esattamente un
`27c6:5125`, applica open/claim/release/close, carica il materiale tramite gli
stessi `goodix_target_material_*` e `goodix_d190_pe_*` di D278/02, fornisce il
seed FDT12 dal blob raw privato canonico D255 con hash, layout, CRC e binding
OTP hash-gated, imposta il gate framework `AWAIT_FINGER_ON`, registra
telemetria bounded e delega ogni comando/protocollo/TLS/FDT/decode al context.
Non contiene costruttori di backend/router/TLS/session/lifecycle, un secondo
reader, retry, reopen, reset, clear-halt o famiglia di write persistente. La
shell resta assente da ogni id table production e non viene installata.

Il launcher realistico è:

```text
./operator_kit/d278-13-integrated-path-once.sh --host-only-prelive
```

Questa modalità ha eseguito dalla Git root 17/17 test normali e 17/17
ASAN/UBSAN, incluso il path integrato completo, e ha compilato/linkato il
binario GUsb live-shaped. L'entrypoint sintetico attraversa il prefisso
reentry, un handshake TLS 1.2 PSK OpenSSL reale in-process, lo stesso oggetto
TLS fino al secondo B0, entrambe le pipeline `FpImage`, release tail, fresh
same-cycle down-table e un solo rearm. Le cancellazioni durante secure-session
e post-TLS sono terminali e drenate. Run ripetute hanno mantenuto gli stessi
17 casi e gli stessi invarianti logici; gli seed casuali GLib non cambiano il
risultato.

Il percorso fisico-shaped D278/13 era soltanto compile/API closure: la
successiva live D278/14 ha dimostrato che non includeva la costruzione con
property `fpi-usb-device` non nulla e ha quindi invalidato quella executable
closure, senza invalidare il grafo context/backend/router/TLS/lifecycle.
Nel build ordinario il comando live ritorna codice `3` con
`LIVE_NOT_AUTHORIZED_OR_BASELINE_UNAPPROVED` prima di leggere materiale
protetto, blob cache o creare/enumerare il contesto GUsb. D278/13 non ha aperto,
enumerato o claimato il sensore, non ha letto secret reali, non ha eseguito USB
submit e non ha approvato una baseline live. Una futura run richiede review
AI-PM separata, SHA completo esplicitamente approvato e ticket operatore
single-shot; `READY_FOR_LIVE` resta false.

La review AI-PM della baseline pre-correttiva
`8abab4a96075ef4057226ef0c5077f483a7636c0` ha corretto due overclaim. Il
vecchio build incorporava lo SHA ricevuto dall'ambiente senza provare che i
sorgenti compilati gli corrispondessero; il vecchio token statico poteva essere
riusato. Lo stato corrente risolve entrambi senza modificare il grafo accettato.
Un build con SHA pieno richiede che il commit esista localmente, che `HEAD` sia
esattamente quello SHA e che launcher, build, adapter, sorgenti/header runtime e
supporto effettivamente usato dal build siano puliti. Il compilatore riceve poi
uno snapshot `git archive` di quel commit; il binario resta `.pending` e viene
rinominato nel nome operativo soltanto dopo una seconda verifica. Manuale,
report e test non esecutivi restano fuori dal set live-critical.

Il ticket non è un secret e non viene mai auto-creato dal launcher. Deve essere
un file regolare non-symlink dell'operatore, mode `0600`, in una directory dello
stesso operatore mode `0700`, con tre campi esatti: baseline SHA, operation
`D278_13_INTEGRATED_PATH_ONCE` e nonce. Dopo la validazione, il gate calcola un
SHA-256 del binding e reclama un marker redatto nella stessa directory tramite
`openat` con `O_CREAT|O_EXCL|O_NOFOLLOW`, mode `0600`. Il marker viene creato
prima di loader protetto, cache FDT e GUsb e non viene rimosso su failure: una
seconda use dello stesso ticket/nonce fallisce `ticket_already_consumed`. I test
gate-only sintetici provano anche doppio claim concorrente con esattamente un
vincitore, senza secret autentici o USB. I controlli statici restano soltanto
difesa in profondità.

La telemetria futura comprende open/claim/release/close, submit/completion e
massimi outstanding, trace delle fasi secure, contatori ACK/typed/reentry/A8/E4,
handshake/handoff/zeroizzazione, tutti i contatori post-TLS fino alla seconda
pipeline e cleanup. Non serializza raster, PSK, validator, OTP o seed FDT raw.
Il conteggio IN fisico non è congelato. Failure e cancellation applicano
generation fence, zero retry/reopen/reset/clear-halt e drain; ciò non dimostra
la quiescenza device-side dopo una cancellazione arbitraria.

```text
D278_13_BASELINE=78230ff1ebd4f1db5d5fd06fbfe6d41fa3a07eca
D278_13_CORRECTIVE_BASELINE=8abab4a96075ef4057226ef0c5077f483a7636c0
D278_13_ARCHITECTURE_RETAINED=true
NO_PARALLEL_STACK=true
INTEGRATED_PATH_LIVE_CAPABLE_IMPLEMENTED=true
LIVE_CAPABLE_INTEGRATED_PATH_HOST_ONLY_PROVEN=true
LIVE_BASELINE_BINDING_GUARD_IMPLEMENTED=true
LIVE_BASELINE_BINDING_GUARD_HOST_ONLY_PROVEN=true
LIVE_CRITICAL_DIRTY_SOURCE_REJECTED=true
ONE_AUTHORIZATION_ONE_ATTEMPT_GUARD_IMPLEMENTED=true
ONE_AUTHORIZATION_ONE_ATTEMPT_GUARD_HOST_ONLY_PROVEN=true
SECOND_USE_OF_AUTHORIZATION_REJECTED=true
SAME_GOODIX_DEVICE_CONTEXT=true
SINGLE_USB_BACKEND_OWNER=true
SINGLE_USB_ROUTER=true
SINGLE_PHYSICAL_IN_OWNER=true
SINGLE_TLS_OBJECT=true
TLS_HANDSHAKE_COUNT_MAX=1
SECRET_HANDOFF_COUNT_MAX=1
FIRST_IMAGE_PIPELINE_HOST_ONLY_PROVEN=true
SECOND_IMAGE_PIPELINE_HOST_ONLY_PROVEN=true
SECOND_IMAGE_RASTER_TARGET_PROVEN=false  # HISTORICAL_SCOPE; SUPERSEDED_BY_D278_14_LIVE_12_CURRENT_TRUE
RELEASE_TAIL_ORDER_HOST_ONLY_PROVEN=true
FRESH_SAME_CYCLE_DOWN_TABLE_GATE_HOST_ONLY_PROVEN=true
REARM_EXACTLY_ONCE_HOST_ONLY_PROVEN=true
THIRD_CYCLE_COMMAND_COUNT=0
PHYSICAL_RX_FRAGMENTATION_INVARIANCE_HOST_ONLY_PROVEN=true
RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL=UNRESOLVED
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
ENROLLMENT_STAGE_POLICY=NOT_SELECTED
REAL_USB_ACCESS=false
REAL_USB_SUBMIT=0
REAL_PRODUCTION_SECRET_READ=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
HISTORICAL_D278_13_EXECUTABLE_CLOSURE=INVALIDATED_BY_D278_14_NON_NULL_BINDING_GAP
```

Il review set canonico è descritto in
`analysis/D278/D278_13_integrated_path_live_capable_host_only_prelive.md`.

### D278/14 — cronologia iniziale: prime quattro live e correttivi host-only

> **Stato storico.** Questa sezione conserva la prima tranche della campagna
> D278/14. È superseded, per lo stato corrente, dalla closure live finale
> D278/14 del 1 settembre 2026: dodici tentativi consumati, ultimo tentativo
> `PASS` con due pipeline immagine target complete.

D278/14 ha richiesto quattro live autorizzate separate, tutte consumate. Il
primo tentativo, sulla baseline
`2172e750ae7c100a3a891ba25d0797286230a4ab`, è fallito nell'assert di
`fp_device_set_property()`: `fpi-usb-device` non nullo assegnato a una classe
`VIRTUAL`, exit `134`/`SIGABRT` prima dell'operator epoch e di qualunque
submit Goodix. Il core dump osservato non è stato ispezionato.

Il secondo tentativo, sulla baseline
`fceae05d9ff3ed14348f9031706e70d5a808ff91`, ha inviato A2 e ricevuto il suo
ACK, ma nessun secondo IN fisico è stato sottomesso perché il re-arm della
ricezione viveva in `goodix_device_context_complete_receive()`, che il
percorso USB reale non invoca. La run è terminata per `ONE_SHOT_DEADLINE` con
trace `REENTRY_RECOVERY_A2>TERMINAL`. Il dito non è stato appoggiato.

Il terzo tentativo, sulla baseline
`87c1bf89d0ba28497313f4bb75a8de4bbdb37b75`, ha ricevuto prima dell'ACK un
A0/A2 typed-shaped con body length `3` ed è terminato fail-closed in 145 ms.
Poiché la run non ha registrato l'hash del body, il match con il pin resta
`UNKNOWN`; l'origine come typed residuo del tentativo #2 è una forte ipotesi,
non una prova.

Il quarto tentativo sulla baseline
`7ce15fa72d0806f34202d2603ef397a740453c63` ha completato due IN: il primo ha
prodotto l'ACK A2 corrente accettato, il secondo un altro ACK A2 valido-shaped.
La run ha fallito chiuso come `ACK_SHAPE_MISMATCH` in 158 ms, prima di A8/TLS.
Il backend era drenato e il cleanup/zeroization erano completi, ma ciò non
dimostra che la coda RX device-side fosse vuota. La catena tentativi #2–#4
sostiene fortemente residui inter-sessione senza provarne la provenienza.

Il **correttivo #1** ha reso `GoodixFpImageDevice` base derivabile, mantenuto
la shell `VIRTUAL` e aggiunto un sottoclasse `USB` senza logica propria per il
solo costruttore fisico. Il **correttivo #2** ha registrato il callback
`in_completed` sul backend per unificare il re-arm della ricezione tra percorso
sintetico e USB reale. La **micro-correttiva #3** ha corretto il resoconto
storico, reso i messaggi operatore in italiano con banner delimitati, reso i
prompt guidati dalla fase post-TLS reale e aggiunto i campi di stop telemetry.
Il **correttivo #4** ha reso esatti i banner e mutuamente esclusivi gli esiti
STOP/terminale. Il **correttivo #5**, solo host-only, aveva introdotto lo
scarto di un typed A2 pinned pre-ACK; è stato superato prima di qualunque live.
Il **correttivo #6** lo rimuove, ripristina l'ordine A2 strict e introduce
`PRE_SESSION_RX_SYNC`: un unico IN temporizzato nel backend già posseduto dal
context mette in quarantena completion non vuote fino al quiet timeout GUsb,
con limiti 16/65536 byte/2000 ms e zero OUT prima del PASS. Lo stesso step
rende generiche la preparazione baseline-bound e la wrapper one-shot tracciata,
chiudendo il precedente ingresso live diretto non preparato.

Riesame metodologico prima di qualunque futura live: (1) rispetto al quarto
tentativo, il metodo cambia perché il quiet boundary passivo precede il primo
OUT invece di tollerare un frame durante la transazione A2; (2) l'ipotesi
nuova è che completion RX immediatamente disponibili seguite da un vero
timeout quiet separino in modo bounded eventuali residui inter-sessione senza
attribuirli; (3) se un futuro tentativo autorizzato fallisse ancora sul primo
A2, non si aggiungerebbe un'altra eccezione shape-specific né si ripeterebbe
la run: si riesaminerebbero semantica della coda endpoint/device ed evidenza
telemetrica del sync. Questo correttivo non autorizza tale live.

Le regressioni del correttivo #6 includono secure-session 24/24 normale e
24/24 sanitizer; il set completo è riportato nell'artefatto D278/14. L'adapter, il baseline
guard, il ticket single-shot, gli audit persistent-recovery, duplicate-stack e
legacy fallback restano verdi; la chiusura pre-live canonica esegue la prova
host-only del prompt tracker.

```text
D278_14_TOTAL_LIVE_ATTEMPTS=12
D278_14_TOTAL_CONSUMED_AUTHORIZATIONS=12
D278_14_HISTORY_CORRECTED=true
D278_14_ATTEMPT_1_BASELINE=2172e750ae7c100a3a891ba25d0797286230a4ab
D278_14_ATTEMPT_1_OUTCOME=FAIL_HOST_BINDING_BEFORE_PROTOCOL
D278_14_ATTEMPT_1_FIRST_FAILURE_BOUNDARY=FPDEVICE_USB_BINDING_CONSTRUCTION
D278_14_ATTEMPT_1_PROCESS_EXIT_CODE=134
D278_14_ATTEMPT_1_PROCESS_TERMINATION=SIGABRT
D278_14_ATTEMPT_1_A2_REACHED=false
D278_14_ATTEMPT_1_TLS_REACHED=false
D278_14_ATTEMPT_1_POST_TLS_REACHED=false
D278_14_ATTEMPT_1_CORE_DUMP_CREATED=OBSERVED
D278_14_ATTEMPT_1_AUTHORIZATION_CONSUMED=true
D278_14_ATTEMPT_2_BASELINE=fceae05d9ff3ed14348f9031706e70d5a808ff91
D278_14_ATTEMPT_2_BINARY_SHA256=de935e0a3fc89a345a2bad624ba3d218f51ab036597d13566d985efbada4f270
D278_14_ATTEMPT_2_OUTCOME=FAIL_RECEIVE_REARM_HOST_PLUMBING
D278_14_ATTEMPT_2_FAILURE_CLASS=ONE_SHOT_DEADLINE
D278_14_ATTEMPT_2_PHASE_TRACE=REENTRY_RECOVERY_A2>TERMINAL
D278_14_ATTEMPT_2_SECURE_COMMAND_COUNT=1
D278_14_ATTEMPT_2_ACK_COUNT=1
D278_14_ATTEMPT_2_TYPED_COUNT=0
D278_14_ATTEMPT_2_PHYSICAL_IN_SUBMIT_COUNT=1
D278_14_ATTEMPT_2_PHYSICAL_OUT_SUBMIT_COUNT=1
D278_14_ATTEMPT_2_REENTRY_A2_RESULT=FAIL_CLOSED
D278_14_ATTEMPT_2_A8_REACHED=false
D278_14_ATTEMPT_2_TLS_REACHED=false
D278_14_ATTEMPT_2_POST_TLS_REACHED=false
D278_14_ATTEMPT_2_FIRST_ACQUISITION_REACHED=false
D278_14_ATTEMPT_2_SECOND_ACQUISITION_REACHED=false
D278_14_ATTEMPT_2_USB_OPEN_COUNT=1
D278_14_ATTEMPT_2_USB_CLAIM_COUNT=1
D278_14_ATTEMPT_2_USB_RELEASE_COUNT=1
D278_14_ATTEMPT_2_USB_CLOSE_COUNT=1
D278_14_ATTEMPT_2_BACKEND_DRAINED=true
D278_14_ATTEMPT_2_CLEANUP_COMPLETE=true
D278_14_ATTEMPT_2_PROJECT_SECRET_ZEROIZED=true
D278_14_ATTEMPT_2_RETRY_COUNT=0
D278_14_ATTEMPT_2_REOPEN_COUNT=0
D278_14_ATTEMPT_2_DEVICE_RESET_COUNT=0
D278_14_ATTEMPT_2_CLEAR_HALT_COUNT=0
D278_14_ATTEMPT_2_PERSISTENT_DEVICE_WRITE_COUNT=0
D278_14_ATTEMPT_2_ROOT_CAUSE=REAL_USB_BACKEND_COMPLETION_BYPASSES_CONTEXT_RECEIVE_REARM_FOLLOWUP
D278_14_ATTEMPT_3_BASELINE=87c1bf89d0ba28497313f4bb75a8de4bbdb37b75
D278_14_ATTEMPT_3_BINARY_SHA256=346aadf64c49b6757c236a097264465ef4de130798aa82109056604930162d90
D278_14_ATTEMPT_3_OUTCOME=FAIL_PRE_ACK_TYPED_A2
D278_14_ATTEMPT_3_FAILURE_CLASS=INTEGRATED_PATH_TERMINAL
D278_14_ATTEMPT_3_PHASE_TRACE=REENTRY_RECOVERY_A2>TERMINAL
D278_14_ATTEMPT_3_SECURE_COMMAND_COUNT=1
D278_14_ATTEMPT_3_ACK_COUNT=0
D278_14_ATTEMPT_3_TYPED_COUNT=0
D278_14_ATTEMPT_3_PHYSICAL_IN_SUBMIT_COUNT=1
D278_14_ATTEMPT_3_PHYSICAL_OUT_SUBMIT_COUNT=1
D278_14_ATTEMPT_3_PHYSICAL_IN_COMPLETION_COUNT=1
D278_14_ATTEMPT_3_PHYSICAL_OUT_COMPLETION_COUNT=1
D278_14_ATTEMPT_3_PROTOCOL_FAILURE_KIND=TYPED_SHAPE_MISMATCH
D278_14_ATTEMPT_3_OBSERVED_OUTER_TYPE=0xA0
D278_14_ATTEMPT_3_OBSERVED_A0_CONTROL=0xA2
D278_14_ATTEMPT_3_OBSERVED_BODY_LENGTH=3
D278_14_ATTEMPT_3_OBSERVED_ACK_ECHO=UNAVAILABLE
D278_14_ATTEMPT_3_OBSERVED_ACK_STATUS=UNAVAILABLE
D278_14_ATTEMPT_3_A8_REACHED=false
D278_14_ATTEMPT_3_TLS_REACHED=false
D278_14_ATTEMPT_3_POST_TLS_REACHED=false
D278_14_ATTEMPT_3_STOP_TIME_MS=145
D278_14_ATTEMPT_3_BACKEND_DRAINED=true
D278_14_ATTEMPT_3_CLEANUP_COMPLETE=true
D278_14_ATTEMPT_3_PROJECT_SECRET_ZEROIZED=true
D278_14_ATTEMPT_3_RETRY_COUNT=0
D278_14_ATTEMPT_3_REOPEN_COUNT=0
D278_14_ATTEMPT_3_DEVICE_RESET_COUNT=0
D278_14_ATTEMPT_3_CLEAR_HALT_COUNT=0
D278_14_ATTEMPT_3_PERSISTENT_DEVICE_WRITE_COUNT=0
D278_14_ATTEMPT_3_CORE_DUMP_LIMIT=0
PRE_ACK_TYPED_A2_OBSERVED=true
PRE_ACK_TYPED_A2_PIN_MATCH=UNKNOWN
STALE_TYPED_FROM_ATTEMPT_2=STRONG_HYPOTHESIS_NOT_PROVEN
D278_14_CORRECTIVE_1=FPDEVICE_USB_BINDING_CONSTRUCTION
D278_14_CORRECTIVE_1_BASELINE=fceae05d9ff3ed14348f9031706e70d5a808ff91
D278_14_CORRECTIVE_1_OUTCOME=PASS_HOST_ONLY
D278_14_CORRECTIVE_2=IN_COMPLETION_REARM_UNIFICATION
D278_14_CORRECTIVE_2_BASELINE=fceae05d9ff3ed14348f9031706e70d5a808ff91
D278_14_CORRECTIVE_2_OUTCOME=PASS_HOST_ONLY
D278_14_CORRECTIVE_2_ROOT_CAUSE=REAL_USB_BACKEND_COMPLETION_BYPASSES_CONTEXT_RECEIVE_REARM_FOLLOWUP
D278_14_CORRECTIVE_2_FIX=IN_COMPLETED_CALLBACK_UNIFIES_REAL_AND_SYNTHETIC_PATHS
CORE_IN_REARM_CORRECTIVE_RETAINED=true
D278_14_CORRECTIVE_5_STATUS=SUPERSEDED_BEFORE_NEXT_LIVE
D278_14_CORRECTIVE_5_LIVE_VALIDATION_PERFORMED=false
CORRECTIVE_5_RUNTIME_TOLERANCE_RETIRED=true
STRICT_A2_ACK_THEN_TYPED_RESTORED=true
PRE_SESSION_RX_SYNC_IMPLEMENTED=true
PRE_SESSION_RX_CLEAN_QUIET_BOUNDARY_HOST_ONLY_PROVEN=true
PRE_SESSION_RX_RESIDUE_CHAIN_QUARANTINED_HOST_ONLY_PROVEN=true
PRE_SESSION_RX_MULTI_FRAME_COMPLETION_QUARANTINED_HOST_ONLY_PROVEN=true
PRE_SESSION_RX_NON_TIMEOUT_ERROR_FAIL_CLOSED=true
PRE_SESSION_RX_BOUNDS_FAIL_CLOSED=true
PRE_SESSION_RX_OUT_BEFORE_SYNC_REJECTED=true
PRE_SESSION_RX_SECURE_START_BEFORE_SYNC_REJECTED=true
NO_PARALLEL_RX_DRAIN_STACK=true
GENERIC_BASELINE_BOUND_OPERATOR_WORKFLOW_HOST_ONLY_PROVEN=true
DIRECT_UNPREPARED_LIVE_PATH_REJECTED=true
SYNTHETIC_AND_REAL_IN_COMPLETION_FOLLOWUP_UNIFIED=true
BACKEND_LEVEL_A2_ACK_COMPLETION_REARMS_NEXT_IN=true
BACKEND_LEVEL_A2_TYPED_COMPLETION_ADVANCES_TO_A8=true
FPDEVICE_USB_BINDING_CORRECTED=true
FPDEVICE_TRANSPORT_TYPE_USB_COMPATIBLE=true
NON_NULL_GUSBDEVICE_FPDEVICE_BINDING_HOST_ONLY_PROVEN=true
PHYSICAL_CONSTRUCTOR_BEFORE_USB_OPEN_CLAIM=true
FPDEVICE_USB_BINDING_CONSTRUCTION_HOST_ONLY=PASS
OPERATOR_MESSAGES_LANGUAGE=ITALIAN
OPERATOR_ACTION_BANNERS_IMPLEMENTED=true
OPERATOR_ACTION_BANNER_FORMAT_EXACT=true
OPERATOR_ACTION_BANNER_MACHINE_PREFIX=false
OPERATOR_PROMPTS_RUNTIME_STATE_DRIVEN=true
OPERATOR_PROMPT_SEQUENCE_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_SUCCESS_FAILURE_EXCLUSIVE=true
OPERATOR_PROMPT_DUPLICATE_SUPPRESSION_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_STOP_THEN_TERMINAL_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_TERMINAL_THEN_STOP_HOST_ONLY_PROVEN=true
OPERATOR_PROMPT_PRELIVE_GATED=true
BOUNDED_STOP_TELEMETRY_COMPLETE=true
SENSITIVE_TELEMETRY_EXPOSURE=false
D278_13_ARCHITECTURE_RETAINED=true
NO_PARALLEL_STACK=true
SINGLE_GOODIX_DEVICE_CONTEXT=true
SINGLE_USB_BACKEND_OWNER=true
SINGLE_USB_ROUTER=true
SINGLE_PHYSICAL_IN_OWNER=true
SINGLE_TLS_OBJECT=true
TLS_HANDSHAKE_COUNT_MAX=1
SECRET_HANDOFF_COUNT_MAX=1
THIRD_CYCLE_COMMAND_COUNT=0
RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
MAX_PHYSICAL_IN_OUTSTANDING=1
REAL_USB_ACCESS=false
REAL_USB_SUBMIT=0
REAL_PRODUCTION_SECRET_READ=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
RETRY_AUTHORIZED=false
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
```

Questo `REAL_USB_ACCESS=false` descrive il solo correttivo host-only, non la
live fallita già consumata. Una futura run sensor-reaching richiede commit e
push del correttivo, review AI-PM indipendente della nuova baseline,
autorizzazione esplicita dell'Utente e nuovo ticket/kit one-shot.

Il default locale libfprint `IMG_ENROLL_STAGES=5`, il modello offline bounded
`2..8` e la corroborazione esterna di otto capture non sono autorità di policy
per APP12509. Il futuro driver non deve essere registrato/abilitato come device
production finché la policy stage non è chiusa; l'aggregazione resta comunque
del framework. D276/02 ha implementato la shell `FpImageDevice` non registrata
con backend in-memory, esercitando il vero `FpImageDevice` libfprint 1.94.5;
la executable closure host-only è stata completata su clean checked-in tree
al commit `87d4aacec23b5415cca5de73e0dfeb83ffe65bab` tramite GitHub Actions
run 33165906857 (2 run deterministiche, 14/14 normal PASS, 14/14 ASAN/UBSAN PASS,
`CI_DIAGNOSTIC_PATCH=NONE`). La precedente indisponibilità di Flatpak/GLib-dev
nell'ambiente di rescue è una condizione storica superata. Un'eventuale conferma
Fedora futura è `OPTIONAL_NON_GATING`. Nessuna USB, sensore reale, TLS reale, PSK,
fprintd, registrazione VID production o mutazione persistente è stata usata o
eseguita.

D276/03 aggiunge ora `GoodixUsbRouter`, posseduto dal solo
`GoodixDeviceContext` dell'open epoch. Il modulo LGPL transport-agnostic espone
un solo completion point fisico, applica un parser incrementale comune
`type + length LE16 + byte header opaco + payload`, e consegna ai consumer logici A0 o B0 frame `GBytes` exactly-once e in ordine con contratto borrowed/transfer-none durante la callback; il consumer deve chiamare `g_bytes_ref()` per trattenere il frame. Il quarto byte
dell'header, i payload A0 e il record B0 restano opachi al router: ACK, IRQ2,
IRQ0200 e NAV sono soltanto fixture sintetiche dei consumer e non introducono
nuova semantica target-specific. Length zero, length oltre il bound host di
32768 byte, outer type estraneo e stream troncato chiudono il terminal fence.
Generation stale, callback post-cancel e feed post-fence non consegnano né
sottomettono altro; il cancel è esclusivamente cleanup host-side e non implica
un comando device-side, retry, recovery, reopen o TLS restart.

Il fake scheduler misura `PHYSICAL_RECEIVE_OWNER_COUNT=1` e
`MAX_OUTSTANDING_RECEIVES=1`; una seconda submission concorrente fallisce. I test GLib coprono anche un B0 con header — incluso il campo length LE16 — e body spezzati su più receive, senza delivery prima del completamento e con ricostruzione byte-identical. La CI validata esternamente dall’AI-PM sul commit
`49e7e9d108d14fc7a9910d97022cd4baa829c5e4` ha eseguito due run deterministiche:
ciascuna ha chiuso 8/8 test router normal e 8/8 ASAN/UBSAN, oltre alla regressione
`FpImageDevice` 14/14 normal e 14/14 sanitizer. Le run GitHub Actions push
33184060807 e PR 33184064239 sono entrambe PASS; il commit validato è stato
integrato in `main` da `474aa2b931977a2c748098c4e510764ad7ee7f42`. I test coprono inoltre chunk arbitrari, concatenazione, zero byte loss/duplicate, demux misto,
stale generation, cancellation sincrona durante delivery e transcript
malformati/troncati. D276/04 chiude ora il successivo confine host-only con OpenSSL 3 selezionato
come provider build-time unico. `GoodixTlsServer` è un server TLS 1.2 pure-PSK
in-process con BIO di memoria, suite `0x00a8`, identity esatta
`Client_identity`, un solo handoff e zeroizzazione `OPENSSL_cleanse`; non espone
socket o endpoint-read. Il peer sintetico in memoria completa l'handshake e i
casi terminali restano fenced senza restart.

Il correttivo D276/04 integra i moduli nell'unico `GoodixDeviceContext`: il
context possiede router, server TLS e backend FpiUsbTransfer insieme a generation,
cancellable activation-local e terminal fence. Il consumer A0 resta non-TLS;
il consumer B0 estrae soltanto il payload dal wrapper neutrale a quattro byte e
lo consegna al Memory-BIO. La state machine TLS distingue handshake,
application-data established e terminal, consegnando plaintext opaco
borrowed/transfer-none. L'output OpenSSL viene avvolto nel B0 canonico e passa
al path OUT dello stesso backend owner.

Il callback production `FpiUsbTransfer` usa un pending token con generation
catturata al submit; N-1 non può essere riattribuita a N. Il backend richiede
drain prima del free e usa un cancellable USB activation-local distinto da
quello dell'azione. Il compile
probe usa header libfprint 1.94.5 e `gusb.h` di sistema; lo stub è solo link-time,
nessun runtime device è eseguito. La copia secret posseduta dal progetto viene
pulita subito dopo l'unico handoff (o al teardown); la zeroizzazione di copie
interne OpenSSL non è asserita. Le suite D276/04 sono passate due volte normal e
ASAN/UBSAN; D276/02–03 restano PASS. La review AI-PM del commit tecnico
`d10155076b7f46e7897c9df65a910a125b4575b4` è `PASS`; le run Actions push
native/router `33197044447`/`33197044428` e PR native/router
`33197046858`/`33197046876` sono tutte `PASS`. La closure è
`PASS_HOST_ONLY`; equivalenza hardware, quiescenza device-side,
timeout target e lifetime TLS cross-activation restano non provati.

`HOST_MACHINE_REPORT_PATH` è il path previsto dal runtime D275 per il report
macchina finale; la sua esistenza corrente non è verificabile senza privilegi
elevati e non viene dichiarata. Il record consolidato nel repository è
`analysis/D275/D275_04_second_b0_live_closure.json`; le evidenze raw private
autentiche, quando presenti, vivono canonicamente in `captures/` e non sono
duplicate negli artefatti di review.

Il boundary Linux `u16/12-bit → libfprint` ha chiuso offline (post-D269/01
corrective) il solo contratto di **rappresentazione pixel** e l'adapter bounded:

```text
PIXEL_REPRESENTATION_CONTRACT=CLOSED_OFFLINE
INTENSITY_QUANTIZATION_CONTRACT=CLOSED_OFFLINE
LIBFPRINT_IMAGE_PIXEL_CONTRACT=PACKED_GRAYSCALE_U8_ONE_BYTE_PER_PIXEL
INTENSITY_MAPPING_DECISION=FIXED_LINEAR_FULL_RANGE_ROUND_NEAREST_12BIT_TO_8BIT
WINDOWS_CONTRACT_REUSED=false
U16_TO_LIBFPRINT_OWNER=LGPL_LIBFPRINT_DRIVER_GLUE
ADAPTER_IMPLEMENTATION_GATE=PASS
```

Il decoder GPL continua a produrre il raster canonico `80x64 u16` con valori
12-bit. Il nuovo helper LGPL lo valida e lo quantizza con
`round(sample × 255 / 4095)` in 5120 byte packed, senza normalizzazione
frame-local, I/O o persistenza. `ORIENTATION_CONTRACT=UNRESOLVED`: D269/01 non
applica flag, flip, rotate, transpose ulteriore o inversione di polarità.

Il primo tratto production-shaped del **full FpImage pipeline contract** è ora
chiuso offline da D270/01. Il glue LGPL alloca un vero `FpImage(80,64)` usando
il `fp_image_new()` della copia libfprint 1.94.5 locale, fa scrivere l'adapter
D269 direttamente nei 5120 byte posseduti dal GObject, preserva flags zero e
rilascia l'unico riferimento iniziale con finalizzazione verificata. Nessun
buffer pixel esterno deve sopravvivere al caller e lo stride resta implicito
pari alla width.

Il valore fisico `ppmm` target-specific resta `UNKNOWN` e viene rappresentato
da stato separato nel wrapper opaco: lo zero tecnico lasciato dalla
zero-initialization GObject non è una misura. Il gate D270 blocca NBIS con
`PHYSICAL_PPMM_REQUIRED`.

D271/01 chiude ora la **policy** extractor offline, non la validazione
biometrica. Il call-flow locale mostra che SIGFM copia i 5120 byte u8 senza
applicare `FpImage::flags`, estrae SIFT/OpenCV e richiede almeno 25 keypoint;
il matcher richiede almeno 5 match descrittore e vota la coerenza geometrica.
Il codice non prova una invarianza generale: la distanza tra coppie tollera
soltanto circa il 5%, non esistono test locali di rotazione/scala/polarità e
l'inversione di intensità non è gestita nel path SIGFM. L'esatta pipeline
Rockytkg `80x64` con SIGFM è corroborazione terza parte, inclusi threshold 20 e
enrollment 3--8 stage, non prova target-local né rende riusabile il preprocessing
GPL nel glue LGPL.

NBIS accetta strutturalmente `80x64` rispetto al suo blocksize minimo di 8 px,
ma oltre a consumare `ppmm` richiede almeno 10 minutiae per un punteggio Bozorth
non nullo; densità e qualità target-locali non sono provate. La policy è quindi
chiusa con SIGFM unico candidato da validare e NBIS bloccato, senza selezione
production e senza claim di qualità. Nessuna nuova fonte target-specific fissa
DPI, orientation o polarity. Pertanto:

D272/01 ha implementato due seam offline senza promuoverli a percorso live.
D273/01 ha ora chiuso staticamente il dataflow delle tabelle FDT e la semantica
del frame post-`0x50`, senza eseguire hardware. La tabella del `0x34` proviene
dalla globale volatile di sessione OEM `0x180580838`: il dispatcher IRQ2 la
aggiorna tramite `0x180029314`, che valida la base raw, deriva sei word con
offset contestuale e applica touchflag/policy mode-dependent. Il builder
FDT-up la copia poi direttamente nel body. Simmetricamente, il ramo normale
dell'IRQ `0x0200` aggiorna la tabella down `0x180580818` usata dal nuovo
`0x32`. Il valore catturato resta quindi un'istanza di sessione, non una
costante target; il requisito è usare la generation più recente prodotta
dall'IRQ dello stesso ciclo.

Nella capture storica D263 (analisi pre-D274/03, distinta dalla run D274/03), Packet 249 è una risposta **A0 NAV `0x50`**, non un B0/TLS: 2417 byte fisici e
outer dichiarati, inner 2410. `chicagoHUget_navdata` (`0x180067874`) usa mode 5
e copia il NAV buffer di sessione al caller. Il modello GPL ora lega ogni
tabella a IRQ sorgente e generation, usa la down table appena derivata per il
re-arm e valida la forma A0 2417/2410 della risposta NAV. Rimangono single
reader, ACK esatto `0x01`, zero retry/reopen/recovery e stop terminale.

Nella capture storica D263 (analisi pre-D274/03) la sola capture positiva
terminava dopo l'ACK del re-arm a packet 253 e il successivo
`IRQ2 → 0x22 → fingerprint B0` non era target-osservato: i componenti OEM
event-driven esistono, ma l'ownership dell'intero edge di seconda iterazione
non era univocamente chiusa dal call graph, e i timeout target restavano
ignoti. Il modello non era collegato al transport USB reale e nessuna allowlist
live era ampliata. D274/03 ha successivamente osservato il secondo edge di
acquisizione **live** nella run Windows OEM autorizzata separata (secondo B0 a
frame 249, stop `WIRE_DRIVEN`): lo stato corrente del secondo target cycle è
pertanto `OBSERVED_COMPLETE`, non più non-osservato. D268 resta terminale alla
prima immagine per il percorso legacy.

Una review AI-PM successiva ha inoltre corretto la policy ACK di quel modello:
`_command_ack()` accettava `0x01|0x07`, più permissivo dell'evidenza D263 in cui
ogni ACK del ciclo ha `status=0x01`. Il seam ora richiede echo esatto e
`status` esattamente `0x01` (`D272_ACK_STATUS_CONTRACT=CLOSED_OFFLINE_EXACT_0X01`).
Il set permissivo resta valido e invariato solo nelle fasi cold-start/pre-TLS,
dove `0x07` è realmente osservato live. Questa closure non riapre né attenua i
blocker D272 primari.

D275/01 promuove ora quel lifecycle nel vero owner Linux
`PersistentRuntimeCoordinator`, mantenendo lo stesso `RuntimeTransport`, la
stessa `Tls12PskServerSession`/`MemoryBioApplicationSessionAdapter`, un solo
handoff del boundary PSK e il solo cleanup terminale. Il first-image handoff usa
il decoder canonico e porta `FDT_ARMED_WAIT → FIRST_IMAGE_RECEIVED`; da lì il
runner D273 è collegato al transport produttivo, non ricopiato. Le generation
FDT sono possedute da `DerivedFdtTable`: la up-table arriva dall'IRQ `0x0002`
del ciclo corrente e la down-table dall'IRQ `0x0200` dello stesso ciclo. Tutti
gli ACK post-image richiedono echo esatto e status `0x01`; NAV accetta soltanto
il controllo `0x50` con forma 2417/2410. I B0 sono consumati solo negli stati
first acquisition, post finger-up e second acquisition; un B0 dove è atteso un
IRQ/NAV fallisce chiuso. Il percorso offline termina al secondo B0, senza
terzo ciclo, retry, reopen, persistenza o serializzazione biometrica.

La executable closure sintetica attraversa il vero coordinator tramite
`tools/d264_first_image_offline.py --terminal-boundary STOP_AFTER_SECOND_IMAGE`.
Questo prova l'integrazione offline, non una seconda acquisizione Linux live:
D268 resta l'autorità Linux live per la prima immagine, D273 per la
ricostruzione offline, D274/03 per il secondo edge Windows OEM live. Il timeout
semantico del device resta `UNKNOWN`, `LIVE_AUTHORIZED=false` e il prossimo
confine è review AI-PM, non esecuzione live automatica.

D275/02 qualifica **solo offline** il thin operator path live one-shot fino al
secondo B0. Il corrective pre-live Git-native chiude i gate host: l'authority
D275 è il commit SHA completo approvato (HEAD identico, worktree pulito,
live-critical set esatto, byte-identity rispetto al blob Git), non un manifesto
SHA-256 per-file e non il manifest storico D268. Il report vive solo in
`/var/lib/goodix-5125-poc/d261-results/d275-second-b0-final.json` e viene
pubblicato dopo la finalizzazione `STOP_AFTER_SECOND_IMAGE`; il path report
D268 non è toccato. Il marker è D275-specific
(`D275_SECOND_B0_SINGLE_USE_MARKER_V1`, fsync prima della capability). Il
live-critical set include `core/multiframe_validation.py` e i moduli
`binding_reference` raggiunti da `protected_runtime`. Il full test D268 sul
current HEAD che confronta il manifest frozen con file evoluti è
`EXPECTED_HISTORICAL_MANIFEST_GUARD`, non una regressione runtime né
`NOT_AVAILABLE`. La baseline live D268 resta frozen a
`c03d32e8647444495e6615e41c2839cbddd62143`. Il thin path
`operator_kit/d275-second-b0-once.sh` →
`tools/d275_live_second_b0_once.py` sopra lo stesso
`PersistentRuntimeCoordinator`. Il default storico D268 resta
`STOP_AFTER_FIRST_IMAGE`; D275 richiede esplicitamente
`--terminal-boundary STOP_AFTER_SECOND_IMAGE`. La modalità fake attraversa lo
stesso coordinator e chiude sinteticamente il secondo B0 con una sessione USB,
un oggetto/handshake TLS, un handoff PSK, zero retry/reopen/write e un cleanup.
Il live candidate richiede inoltre SHA completo approvato, worktree pulito,
marker D275 single-use e la frase gate esatta che dichiara VID:PID, one-shot,
no retry, factory-preserving, no enrollment e no third cycle. Il secondo B0 è
lo stop wire/state-driven; il comando candidato non è stato eseguito e nessuna
baseline D275 è auto-approvata.

Lo stato probatorio resta distinto: D268 è il first-image Linux live storico a
baseline frozen; D275/01 chiude offline il production path fino al secondo B0;
D275/02 qualifica offline il candidate operator path, senza nuova evidenza
device. Al termine di D275/02 `LINUX_SECOND_B0_LIVE_OBSERVED` restava `false`,
`LIVE_AUTHORIZED=false` e `TARGET_DEVICE_TIMEOUT=UNKNOWN`; la promozione a
`LINUX_SECOND_B0_LIVE_OBSERVED=true` avviene in D275/04.

### D275/03 — due live Linux, root-cause `0x34` e corrective offline

Due esecuzioni D275 sulla baseline approvata
`3443154184e138ba0b104669076132c27ace8255` hanno raggiunto la stessa traccia
terminale `... 0x32, 0x22, 0x34`, validato l'ACK `0x34/0x01` e poi terminato
fail-closed con `TimeoutError:libusb_bulk_timeout:0x81` durante la wait
`IRQ 0x0200`; retry, reopen e scritture persistenti sono rimasti a zero. Nel
primo tentativo il dito poteva essere stato sollevato prima del prompt 2/3. Nel
secondo l'operatore ha mantenuto il dito fino al prompt e lo ha sollevato solo
dopo: lo stesso timeout elimina il timing umano come spiegazione sufficiente.
Una terza esecuzione equivalente non è autorizzata.

Il call-flow prova anche che `0x34` è irraggiungibile prima di IRQ2, `0x22`,
ACK01, primo B0, plaintext accettato, decode raster e transizione
`FIRST_IMAGE_RECEIVED`. I valori finali D275
`first_image_received=false`, contatori first-image zero e
`raster_decode_count=0` erano quindi telemetry errata: il ramo multiframe non
incrementava i contatori monotoni, e il successivo `fail_closed()` sostituiva
lo stato lifecycle usato come proxy. D275/03 registra ora separatamente IRQ2,
ACK, B0 e decode; un failure successivo non cancella più le milestone già
raggiunte.

L'audit byte-level delle fonti APP12509 chiude inoltre un mismatch di protocollo
nella baseline live. Nei tre cicli positivi disponibili (uno D263 e due nella
capture D274/03), l'IRQ2 ha `touch_flags=0x003f` e l'OEM costruisce la tabella
up come sei coppie `80 || ((raw_word >> 1) + 0x1d)`. D274/03, per esempio,
riceve raw `ef00f000df00c800f400d100` ma invia nel body `0x34`
`0a01 || 80948095808c808180978085`; la baseline Linux passava invece i 12 byte
raw direttamente a `build_fdt_up()`. Analogamente l'IRQ0200 con touch zero è
trasformato in down-table `80 || (raw_word >> 1)` prima del re-arm `0x32`:
raw `5a017c01470162014d016501` diventa
`80ad80be80a380b180a680b2`.

Il corrective offline applica solo questi due contesti target-osservati e
fallisce chiuso per touch/mode diversi; source IRQ e generation restano
obbligatori. Il mismatch è `VERIFIED`; il suo ruolo causale nel mancato IRQ0200
è `STRONG_CAUSAL_INFERENCE`, non nuova osservazione device-side: entrambe le
live errate hanno ricevuto ACK ma nessun IRQ0200, mentre l'OEM usa la tabella
derivata e osserva IRQ0200. Nessuna live post-corrective è stata eseguita o
autorizzata.

La capture OEM non mostra altri comandi o transfer tra primo B0 e `0x34`.
Misura ACK `0x34` → IRQ0200 in 47,201 ms (D263) e 345,859 ms (D274/03), quindi
non sostiene che il timeout host Linux di 15 s sia troppo breve. Il
`SharedFrameRouter` conserva in coda un IRQ arrivato mentre il path command
attende l'ACK, usa un solo reader fisico e non presenta una lost-event window
nel call-flow o nei test di interleaving. Il solo errore libusb `-7` non prova
però che `transferred == 0`, perché il backend corrente non espone tale valore
nel failure: la presenza di byte parziali nella specifica live resta `UNKNOWN`,
senza corrective speculativo di chunking.

```text
FIRST_IMAGE_REACHED_IN_D275_LIVE=VERIFIED_FROM_CALL_FLOW
LINUX_0X34_ACK_REACHED=true
LINUX_IRQ0200_AFTER_0X34=OBSERVED_IN_D275_04
OPERATOR_TIMING_CONFOUND=ELIMINATED_BY_ATTEMPT_2
D275_LIVE_BASELINE_0X34_TABLE_EQUALS_OEM_REQUIRED_TABLE=false
CORRECTED_0X34_TABLE_EQUALS_OEM_CAPTURED_TABLE=true
RAW_IRQ_BASE_CAN_BE_USED_DIRECTLY_FOR_0X34=DISPROVEN
HOST_15S_TIMEOUT_PLAUSIBLY_TOO_SHORT=NO
EVENT_LOSS_RACE_FOUND=false
FDT_TABLE_MISMATCH_CAUSALITY=LIVE_VALIDATED
PROTOCOL_CORRECTIVE_IMPLEMENTED=true
LINUX_FIRST_IMAGE_LIVE_OBSERVED=true
LINUX_SECOND_IRQ0002=OBSERVED
LINUX_SECOND_0X22=OBSERVED
LINUX_SECOND_B0_LIVE_OBSERVED=true
STOP_AFTER_SECOND_IMAGE_LIVE=PASS
TARGET_DEVICE_TIMEOUT=UNKNOWN
THIRD_EQUIVALENT_LIVE_ATTEMPT_NOT_AUTHORIZED=true
LIVE_AUTHORIZED=false
PERSISTENT_DEVICE_WRITE_COUNT=0
HOST_CACHE_WRITE_COUNT=0
RETRY_COUNT=0
TRANSPORT_REOPEN_AFTER_TLS=false
USB_TRANSPORT_SESSION_COUNT=1
TLS_SERVER_HANDSHAKE_COUNT=1
SECRET_BOUNDARY_HANDOFF_COUNT=1
```

### D275/04 — closure della seconda acquisizione Linux live

D275/04 chiude formalmente il ciclo avviato con D275/03. Sulla baseline live
post-corrective `6eb60856fee7eed2c1765e5b1a11b492e99e42b0` è stata eseguita una
sola run live autorizzata e consumata, con esito
`PASS_STOP_AFTER_SECOND_IMAGE` e terminale `STOP_AFTER_SECOND_IMAGE`.

Provenance e record versionato:

```text
LIVE_EVIDENCE_CONSOLIDATED_IN_REPOSITORY=true
CANONICAL_REPOSITORY_EVIDENCE_RECORD=analysis/D275/D275_04_second_b0_live_closure.json
HOST_MACHINE_REPORT_PATH=/var/lib/goodix-5125-poc/d261-results/d275-second-b0-final.json
RAW_D275_POST_CORRECTIVE_REPORT_VERSIONED=false
CANONICAL_PRIVATE_RAW_EVIDENCE_ROOT=captures/
```

La baseline live post-corrective resta `6eb60856...`; il commit di closure
D275/04 attualmente su `main` e sotto review AI-PM è
`42819c05e2400591bb58168539aa0f54ca09509f`. L'eventuale commit del presente
correttivo finale sarà eseguito dall'Utente dopo la review.

Trace live osservata:

```text
0x36
0x50
0x36
0x82
0x20
0x36
0x32
0x22
0x34
0x20
0x50
0x32
0x22
```

Il percorso ha quindi superato: cold start, TLS 1.2 PSK, D4, AF, fresh FDT,
primo `IRQ 0x0002`, primo `0x22`, primo B0 / prima immagine, `0x34` con FDT-up
derivata OEM, `IRQ 0x0200`, post-up `0x20`, post-up B0 / NAV `0x50`, re-arm
`0x32` con down-table derivata, secondo `IRQ 0x0002`, secondo `0x22`, secondo
B0, stop `STOP_AFTER_SECOND_IMAGE` e cleanup.

La telemetria first-image corretta registra:

```text
first_image_irq2_observed_count=1
first_image_ack_validation_count=1
first_image_b0_count=1
first_image_raster_decode_count=1
first_image_received=true
image_command_attempt_count=2
```

Il `raster_decode_count=1` conta il primo B0 decodificato; il secondo B0 è
provato dal `phase_reached=STOP_AFTER_SECOND_IMAGE` e dal fatto che il runner
non può raggiungere quel terminale prima del secondo B0.

Gli invarianti factory-preserving sono rispettati:

```text
persistent_device_write_count=0
host_cache_write_count=0
retry_count=0
transport_reopen_after_tls=false
usb_transport_session_count=1
transport_cleanup_count=1
tls_server_session_object_count=1
tls_server_handshake_count=1
tls_close_count=1
second_server_session_created=false
second_psk_provisioning=false
secret_boundary_handoff_count=1
secret_boundary_zeroized=true
tls_uses_same_secret_boundary_object=true
terminal_cleanup_completed=true
```

La causalità del mismatch FDT è promossa da `STRONG_CAUSAL_INFERENCE` a
`LIVE_VALIDATED` sul target APP12509 per questo boundary e questo percorso:
prima del corrective due run fallivano entrambe dopo `0x34/ACK` con timeout su
`IRQ 0x0200`, il timing operatore era stato controllato nel secondo tentativo,
il timeout di 15 s non è plausibilmente troppo breve, una lost-event race non è
stata trovata e la tabella `0x34` della vecchia baseline era verificata
errata rispetto all'OEM; dopo il solo corrective di derivazione FDT e
telemetry, la stessa sequenza supera `IRQ 0x0200` e raggiunge il secondo B0.
La modifica telemetry non altera traffico o sequencing device-side.

`TARGET_DEVICE_TIMEOUT` resta `UNKNOWN`: il PASS non misura né chiude il
timeout semantico del device. `LIVE_AUTHORIZED=false` per qualsiasi nuova run;
non è autorizzato alcun terzo ciclo, enrollment, persistenza, timeout widening,
retry/reopen o marker rearm.

Closure v2.5 del presente correttivo documentale:

```text
OUTCOME=READY
ADVANCEMENT=NONE (correttivo di provenance/semantica Git/verifiche offline; la milestone live D275/04 resta chiusa invariata)
EXECUTABLE_CLOSURE=NOT_APPLICABLE
RESIDUAL_BLOCKER_OR_RISK=TARGET_DEVICE_TIMEOUT_UNKNOWN; evidenza raw D275 post-corrective non versionata in repository
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_6eb60856fee7eed2c1765e5b1a11b492e99e42b0_PLUS_D275_04_CLOSURE_COMMIT_42819c05e2400591bb58168539aa0f54ca09509f_ON_main_WITH_FILES_Goodix_27c6_5125_manuale_tecnico.md_analysis_D275_D275_04_second_b0_live_closure.md_analysis_D275_D275_04_second_b0_live_closure.json
```

### D275/02/operator path — UX poka-yoke italiana

Il candidato live D275/02 guida l'operatore con blocchi in italiano su `stderr`,
mentre il report macchina resta JSON parseabile su `stdout`.  La sequenza è:

1. `D275 — PREPARAZIONE` (dito lontano dal sensore) dopo i gate CLI/baseline
   iniziali e prima del primo accesso USB reale.
2. `D275 — AZIONE OPERATORE 1/3` (appoggia il dito) immediatamente prima della
   prima wait reale di `IRQ 0x0002` dopo il final arm.
3. `D275 — AZIONE OPERATORE 2/3` (solleva il dito) immediatamente prima della
   wait di `IRQ 0x0200` dopo `0x34/ACK01`.
4. `D275 — AZIONE OPERATORE 3/3` (appoggia di nuovo il dito) immediatamente
   prima della seconda wait di `IRQ 0x0002` dopo `0x32/ACK01`.
5. `D275 — TEST COMPLETATO` (puoi togliere il dito) solo dopo il vero secondo
   B0 e risultato `PASS_STOP_AFTER_SECOND_IMAGE`.

I prompt sono agganciati al contatore monotonico delle vere wait
`FIRST_IMAGE_IRQ2_TIMEOUT_MS` del production path (`core.persistent_runtime`);
non usano timer, sleep, `input()`, lettori extra o state machine parallele.
Ogni blocco ha almeno due righe completamente vuote prima del separatore
iniziale; non usa colori ANSI.

La modalità `--fake-live` attraversa lo stesso
`PersistentRuntimeCoordinator` con fixture sintetica e mostra la stessa
sequenza di blocchi, ciascuno con la riga
`SIMULAZIONE — NON TOCCARE IL SENSORE`; non accede USB, non materializza
secret reali, non attende input e non introduce sleep artificiali.  Serve da
rehearsal psicologica/operativa prima della live.

In caso di qualsiasi failure dopo l'avvio compare una sola volta
`D275 — TEST INTERROTTO` in italiano, con istruzione di togliere il dito, non
rilanciare il comando e inviare l'output alla review AI-PM.  La `failure_class`
macchina resta disponibile nel JSON finale.

Nel dominio LGPL, `goodix_sigfm_metrics.cpp` applica esclusivamente il mapping
D269, chiama il SIGFM locale, mantiene il gate `<25`, distingue score zero da
errore negativo e contiene le eccezioni C++/OpenCV al confine C. Raster, buffer
u8 e `SigfmImgInfo` sono solo in memoria; non esiste API di serializzazione.
Warning severi, ASan/UBSan e test double sintetico passano. D273 ha aggiunto un
harness synthetic-only per il vero SIGFM: adapter, wrapper e harness compilano
nello SDK Flatpak, mentre il vero `sigfm.cpp` si arresta su
`opencv2/core/mat.hpp` mancante. Né host né SDK installato espongono
`opencv4.pc`; la build/link reale è quindi `NOT_AVAILABLE` e
`EXECUTABLE_CLOSURE=FAIL`. Nessun pacchetto è stato installato. La fixture prova
soltanto plumbing, non qualità biometrica. (Narrazione superata da D274/03 Sessione 3: il real SIGFM build è stato chiuso host-only con OpenCV4-dev 4.5.4 installato via apt nel sandbox esecutore; vedi sotto «D274/03 parallel offline forward — Sessione 3: SIGFM / OpenCV4 real-build closure».)

```text
PIXEL_REPRESENTATION_CONTRACT=CLOSED_OFFLINE
INTENSITY_QUANTIZATION_CONTRACT=CLOSED_OFFLINE
FPIMAGE_OBJECT_CONSTRUCTION=CLOSED_OFFLINE
FPIMAGE_BUFFER_OWNERSHIP=CLOSED_OFFLINE
FPIMAGE_DIMENSION_CONTRACT=CLOSED_OFFLINE
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
UNKNOWN_PPMM_SEMANTICS=EXPLICITLY_BOUNDED
NBIS_PPMM_REQUIREMENT=REQUIRED_VERIFIED
NBIS_WITH_UNKNOWN_PPMM=BLOCKED
SIGFM_PPMM_REQUIREMENT=NOT_CONSUMED_VERIFIED
FEATURE_EXTRACTOR_POLICY=CLOSED_OFFLINE
SIGFM_STATUS=OFFLINE_METRIC_SEAM_SYNTHETIC_PASS_REAL_BUILD_CLOSED_HOST_ONLY_OPENCV4
SIGFM_EXCEPTION_CONTAINMENT=CLOSED_OFFLINE_AT_C_ABI
SIGFM_METRIC_PRIVACY_CONTRACT=CLOSED_OFFLINE_NO_SERIALIZATION
OPENCV4_DEV_ENVIRONMENT=AVAILABLE_HOST_ONLY_LIBOPENCV_DEV_4_5_4_VIA_APT
REAL_SIGFM_BUILD=PASS_HOST_ONLY_WITH_REAL_OPENCV4
REAL_SIGFM_LINK=PASS
REAL_SIGFM_POSITIVE_EXTRACT=PASS
REAL_SIGFM_MATCH_PATH=PASS
REAL_SIGFM_SYNTHETIC_RUNTIME=PASS
REAL_SIGFM_EXECUTABLE_CLOSURE=PASS_HOST_ONLY
REAL_SIGFM_SANITIZER_STATUS=PASS
LEAK_DETECTION=DISABLED
MEMORY_SAFETY_SCOPE=ASAN_UBSAN_RUNTIME_NO_DETECTED_ADDRESS_OR_UB_ERRORS_LEAKS_NOT_ASSESSED
NBIS_STATUS=BLOCKED_UNKNOWN_PHYSICAL_PPMM_AND_TARGET_LOCAL_MINUTIA_DENSITY_UNPROVEN
SIGFM_80X64_SUPPORT_STATUS=ARCHITECTURALLY_SUPPORTED_WITH_MIN_25_KEYPOINT_GATE_TARGET_QUALITY_UNPROVEN
NBIS_80X64_SUPPORT_STATUS=STRUCTURALLY_ACCEPTED_MIN_8PX_BLOCK_BUT_TARGET_USABILITY_BLOCKED
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
BIOMETRIC_QUALITY_STATUS=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED
MULTIFRAME_CAPTURE_LIFECYCLE_STATUS=LINUX_LIVE_SECOND_B0_OBSERVED_D275_04_TIMEOUTS_UNKNOWN
D272_ACK_STATUS_CONTRACT=CLOSED_OFFLINE_EXACT_0X01
UP_TABLE12_SOURCE=OEM_SESSION_GLOBAL_GF_FDT_UP_BASE_VA_0X180580838
UP_TABLE12_DERIVATION=IRQ_0X0002_RAW_BASE_VALIDATION_THEN_PER_WORD_HALF_PLUS_CONTEXT_OFFSET_ENCODING_AND_MODE_DEPENDENT_COMMIT_BY_0X180029314
UP_TABLE12_LIFETIME=VOLATILE_OEM_PROCESS_SESSION_GLOBAL_INITIALIZABLE_BY_CALLBACK_0X180028480_AND_UPDATED_BY_FDT_IRQ_HANDLING
UP_TABLE12_FRESHNESS_REQUIREMENT=0X34_MUST_CONSUME_THE_MOST_RECENT_VALID_IRQ_0X0002_DERIVED_TABLE_FROM_THE_SAME_FINGER_DOWN_CYCLE
POST_FIRST_IMAGE_0X34_STATUS=OBSERVED_BUILDER_AND_SESSION_TABLE_DATAFLOW_VERIFIED_STATICALLY
FINGER_UP_IRQ_0200_STATUS=OBSERVED_LIVE_AFTER_0X34_ACK_D275_04
POST_FINGER_UP_0X20_STATUS=OBSERVED_WITH_ACK_AND_POST_UP_B0_IMAGE_ROLE_STATICALLY_SUPPORTED_NO_QUALITY_CLAIM
POST_FINGER_UP_0X50_STATUS=OBSERVED_WITH_EXACT_ACK_AND_OEM_NAV_GETTER_VERIFIED
POST_0X50_RESPONSE_STATUS=OBSERVED_A0_0X50_NAV_RESPONSE_LENGTHS_2417_2410
D273_NAV_CLASSIFICATION_WIRE_CONTROL=EXACT_0X50
D273_0X51_NAV_ALIAS_ACCEPTED=false
GENERIC_WIRE_TO_LOGICAL_MASK_REMOVED=true
REARM_0X32_STATUS=OBSERVED_WITH_ACK_AND_CURRENT_IRQ0200_DERIVED_DOWN_TABLE_CONTRACT
SECOND_CYCLE_STATUS=OBSERVED_COMPLETE_LIVE_D275_04
FULL_FPIMAGE_PIPELINE_CONTRACT=PARTIALLY_CLOSED
LINUX_MULTIFRAME_RUNTIME=D275_04_LIVE_SECOND_B0_CLOSURE_REVIEW
LINUX_FIRST_IMAGE_LIVE_OBSERVED=true
LINUX_IRQ0200_AFTER_0X34=OBSERVED
LINUX_SECOND_IRQ0002=OBSERVED
LINUX_SECOND_0X22=OBSERVED
LINUX_SECOND_B0_LIVE_OBSERVED=true
STOP_AFTER_SECOND_IMAGE_LIVE=PASS
FDT_TABLE_MISMATCH_CAUSALITY=LIVE_VALIDATED
TARGET_DEVICE_TIMEOUT=UNKNOWN
LIVE_AUTHORIZED=false
PERSISTENT_DEVICE_WRITE_COUNT=0
HOST_CACHE_WRITE_COUNT=0
RETRY_COUNT=0
TRANSPORT_REOPEN_AFTER_TLS=false
USB_TRANSPORT_SESSION_COUNT=1
TLS_SERVER_HANDSHAKE_COUNT=1
SECRET_BOUNDARY_HANDOFF_COUNT=1
NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_D275_04_LIVE_CLOSURE
NEXT_BOUNDARY_PREREQUISITE=EXPLICIT_SEPARATE_AUTHORITY_FOR_ANY_FUTURE_LIVE_STEP
```

D274/01 prepara esclusivamente offline una superficie Windows/OEM distinta da
D268 per acquisire, in un eventuale step futuro e separatamente autorizzato, il
minimo bordo mancante `second IRQ2 → exact 0x22 → exact ACK 0x01 → second B0`.
Il kit non contiene un ramo capace di avviare una capture: la modalità reale è
hard-disabled nel sorgente prima di TShark, attach, prompt o altra azione
hardware. Self-test, preflight e simulazione pre-autorizzazione sono le sole
modalità eseguibili.

La provenienza della UI positiva storica resta ignota. La capture D263 deriva
dal corpus recuperato D230, che non conserva comando di acquisizione, marker o
workflow UI; D255 prova invece soltanto un percorso distinto Windows Hello
setup zero-finger. Il workflow futuro è quindi
`WINDOWS_HELLO_SETUP_CANDIDATE_NO_COMMIT`, non un'attribuzione retroattiva. Ogni
commit enrollment, mutazione account/PIN, terzo ciclo o retry è terminale e non
autorizzato.

Il sanitizer hash-gated riusa il framing USBPcap osservato, seleziona un unico
`27c6:5125`, richiede A8 APP12509 nella stessa capture e pubblica soltanto
indici, direzioni, wrapper, lunghezze, classe TLS esterna e timing. Non esporta
contenuti B0, plaintext, raster, hash biometrici o secret. La fixture pcapng
sintetica chiude l'intera sequenza e i failure richiesti; sulla capture storica
positiva il tool restituisce correttamente `MISSING_SECOND_IRQ2`, senza
promozione probatoria.

La deadline unica di 180 s è host-side: la capture positiva osserva 8,383 s
fra ACK del primo arm e ACK del re-arm, mentre D255 osserva circa 62,9 s da
attach-begin a UI-ready. Il margine non definisce una semantica timeout del
device, che resta `UNKNOWN`.

```text
D274_PRELIVE_WINDOWS_MULTIFRAME_EVIDENCE_KIT=READY_FOR_AI_PM_REVIEW
D274_REAL_CAPTURE_CAPABILITY=1
D274_HARD_DISABLED=true
D274_SECOND_CYCLE_TARGET_OBSERVATION=OBSERVED_COMPLETE
D263_CAPTURE_WORKFLOW_CLASS=UNKNOWN
WINDOWS_OEM_WORKFLOW_SELECTED=WINDOWS_HELLO_SETUP_CANDIDATE_NO_COMMIT
WINDOWS_ENROLLMENT_COMMIT_AUTHORIZED=false
WINDOWS_ACCOUNT_MUTATION_AUTHORIZED=false
WINDOWS_PIN_MUTATION_AUTHORIZED=false
D274_POSTPROCESSOR_STATUS=PASS_OFFLINE_HASH_GATED_SANITIZED
D274_EVIDENCE_SCHEMA_STATUS=PASS
D274_SYNTHETIC_SECOND_CYCLE_FIXTURE=PASS
D274_PRIVACY_CONTRACT=PASS_METADATA_ONLY_NO_B0_CONTENT
D274_FINGERPRINT_B0_CONTRACT=CLOSED_OFFLINE_STRUCTURAL_7726_TLS_APPLICATION_DATA
D274_GENERIC_B0_AS_FINGERPRINT_ACCEPTED=false
D274_OUTPUT_ROOT_PRIVACY_CONTRACT=CLOSED_OFFLINE_PREFLIGHT_POLICY
D274_CREDENTIAL_MUTATION_UI_TERMINAL=true
D274_UNKNOWN_MARKER_ACCEPTED=false
D274_FRAME_METADATA_SCHEMA=STRICT_ADDITIONAL_PROPERTIES_FALSE
D274_SCHEMA_INSTANCE_VALIDATION=PASS
D274_TLS_RECORD_LENGTH_ENDIAN=BIG_ENDIAN_NETWORK_ORDER
D274_GOODIX_B0_LENGTH_ENDIAN=LITTLE_ENDIAN
D274_REALISTIC_TLS_HEADER_1703031E25_ACCEPTED=true
D274_SYNTHETIC_LITTLE_ENDIAN_TLS_LENGTH_ACCEPTED=false
D274_TLS_ALERT_B0_AS_FINGERPRINT_ACCEPTED=false
D274_WRONG_LENGTH_B0_AS_FINGERPRINT_ACCEPTED=false
D274_OUTPUT_ROOT_PRIVACY_POLICY_SOURCE_CONTRACT=PASS
D274_BROAD_ACL_READ_ACCEPTED=false
D274_ACL_ALLOW_DISCRIMINATOR=AccessControlType
D274_ACL_IDENTITY_NORMALIZATION=SecurityIdentifier
WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=PASS
D274_LOCAL_SCHEMA_INTEGER_SEMANTICS=STRICT_INTEGER_ONLY
D274_RUNTIME_EVIDENCE_CONTRACT_VALIDATION=PASS_LOCAL_STRICT
D274_HOST_CAPTURE_DEADLINE_POLICY=EVIDENCE_BOUNDED_NOT_DEVICE_TIMEOUT_CLAIM
SECOND_CYCLE_STATUS=OBSERVED_COMPLETE_WIRE_DRIVEN
NEXT_PRIMARY_BOUNDARY=D274_03_OFFLINE_FINALIZER_CORRECTIVE_REVIEW
NEXT_BOUNDARY_PREREQUISITE=FORMAL_FREEZE_REVIEW_POST_OBSERVATION
D274_02_OPERATOR_PACKAGE=CLOSED
D274_02_WINDOWS_NATIVE_EXECUTION=COMPLETED
D274_02_WINDOWS_NATIVE_QUALIFICATION=PASS
D274_02_SELFTEST_NATIVE=PASS
D274_02_PREFLIGHT_NATIVE=PASS
D274_02_PREAUTHORIZATION_SIMULATION_NATIVE=PASS
D274_NATIVE_HARD_DISABLE_ADVERSARIAL_TEST=PASS
D274_01_NATIVE_POWERSHELL51_MODE_SELECTOR=PASS_NATIVE
D274_02_FINAL_REVIEW=PASS
D274_02_STATUS=CLOSED
CORRECTIVE_REQUIRED=false
D274_02_FINAL_INTEGRITY_MANIFEST_SELF_CONSISTENT=PASS
D274_02_CORRECTED_KIT_CANONICAL_PACKAGE_BYTE_IDENTITY=PASS
D274_SECOND_CYCLE_TARGET_OBSERVATION=OBSERVED_COMPLETE
SECOND_CYCLE_STATUS=OBSERVED_COMPLETE_WIRE_DRIVEN
D274_REAL_CAPTURE_CAPABILITY=1
D274_HARD_DISABLED=true
# I campi generici APPROVED_FOR_CAPTURE/BASELINE_APPROVED/LIVE_AUTHORIZED/READY_FOR_LIVE
# descrivono lo stato storico del template di autorizzazione baseline D274/01-era
# (pre-D274/03); la baseline D274/03 e' approvata a parte (D274_03_BASELINE_APPROVED=true).
APPROVED_FOR_CAPTURE=false
BASELINE_APPROVED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
# Lo stato LIVE_* descrive il template di autorizzazione della baseline (non eseguito via questo kit);
# la capture canonica D274/03 osservata è documentata nel blocco D274/03 corrente e nella sottosezione.
LIVE_EXECUTION=NOT_PERFORMED
D274_VM_ABSOLUTE_LOG_TIMESTAMPS_CROSS_SESSION_DURATION_AUTHORITY=false
```
D274/03 introduce una nuova authority separata, senza retro-modificare D274/01
o riaprire D274/02. La review AI-PM della prima baseline D274/03 ha individuato
cinque blocker pre-live: gate di assenza Goodix non causale nella stessa run,
categoria PIN ambigua, stop dipendente da conferma umana, finalizzazione raw
non provata e assenza di qualificazione nativa PowerShell 5.1. Il corrective
in-place li chiude offline senza eseguire hardware.

Il Kit corretto contiene launcher, runner, collector, observer passivo,
postprocessor, schema, authority template, marker e radici output con namespace
D274/03. La superficie rivolta all'operatore è in italiano. Il percorso futuro
è capace soltanto di osservazione passiva USBPcap/TShark del traffico prodotto
dal workflow OEM; non contiene un sender Goodix Python/libusb. È hard-gated da
authority separata, full commit SHA approvato, HEAD/branch/live-critical set,
ACL privata e marker `CreateNew` single-use. Inoltre verifica tramite PnP che
`VID_27C6&PID_5125` sia assente nella **stessa invocazione live**, prima di
marker, capture, attach e prompt dito; discovery indisponibile o target presente
falliscono chiuso senza mutare PnP. Il template consegnato ha tutti i gate live
a `false`, quindi il percorso non è eseguibile in questo step.

L'autenticazione `EXISTING_PIN_AUTHENTICATION` è ammessa soltanto come verifica
identità con PIN già configurato, digitato esclusivamente nella UI Windows. Il
Kit non legge, chiede, registra o serializza il valore PIN. Creazione/modifica
PIN, mutazioni account/credenziali, prerequisiti inattesi e commit enrollment
restano categorie terminali fail-closed.

L'observer e il sanitizer mantengono il prefisso completo necessario a
distinguere il re-arm dal primo arm, ma il boundary di successo termina al
minimo evento nuovo:
ACK `0x32` → secondo IRQ `0x0002` → secondo wire `0x22` → ACK echo `0x22` e
status esatto `0x01` → secondo B0 fingerprint strutturale → STOP. Non richiede
decode immagine e non esporta contenuto B0/TLS, raster, pixel o hash biometrici.
Lo stop è ora causato dall'osservazione wire-driven del secondo B0 nel pcapng
in crescita, non da `SECONDO_OK`. Il parser growing tollera soltanto il trailing
block pcapng incompleto; dopo stop e terminazione bounded, il postprocessor
strict hash-gated deve recuperare dal raw finalizzato lo stesso frame terminale,
altrimenti chiude `CAPTURE_FINALIZATION_LOST_TERMINAL_EVIDENCE`. Fixture
sintetiche e capture storica D263 verificano rispettivamente PASS e
`MISSING_SECOND_IRQ2`; nessuna è promossa a evidenza target del secondo ciclo.

È predisposto un package innocuo per qualificare nativamente su Windows, con
Goodix assente, self-test, preflight, simulazione pre-authority, selector 5.1,
gate same-run, contratto TShark/USBPcap, ACL/privacy/lingua e invocazione
avversaria con authority false. L'host AI Linux non dispone di Windows
PowerShell 5.1 e non può validare localmente quel runtime. L'operatore ha
eseguito le qualification su Windows 11 Home build 26200, Windows PowerShell
Desktop 5.1.26100.8655, sempre con Goodix assente dal guest e senza toccare
hardware.

La prima è fallita al parsing di `run-d274-03-native-qualification.ps1`, prima
del runtime, perché gli script con superficie italiana/non-ASCII erano salvati
UTF-8 senza BOM. Tutti i cinque `.ps1` sono ora UTF-8 con BOM (`EF BB BF`) e il
corrective è confermato dal campo: il parsing 5.1 passa e lo stage
`powershell_51` ha dato PASS.

La seconda, prima run realmente entrata in runtime, è fallita allo stage
`repository_and_goodix_absence` con `repository Git non individuabile`, benché il
repository fosse individuabile. La diagnostica manuale nello stesso clone isola
la causa: `git -C <package> rev-parse --show-toplevel` invocato direttamente
restituisce il toplevel corretto con `EXIT_DIRECT=0`, mentre lo stesso comando
inglobato in `| Select-Object -First 1` restituisce lo stesso path ma
`EXIT_PIPE=-1`. In Windows PowerShell 5.1 `$LASTEXITCODE` non è affidabile dopo
che un comando nativo è stato inglobato in una pipeline che interrompe
l'upstream. In quella run nessun controllo Goodix, ACL, TShark/USBPcap, selector
o gate same-run è stato raggiunto. Il corrective applica l'idioma sicuro in tutti
i siti realmente vulnerabili del Kit — invocazione nativa senza pipeline, exit
code catturato nello statement immediatamente successivo, fail-closed sulla
variabile catturata, trasformazione e validazione non-vuoto solo dopo — e lascia
invariata la semantica dei gate.

La run finale post-corrective ha restituito PASS in tutti gli stage nativi:
PowerShell 5.1, repository/assenza Goodix, self-test, selector 5.1, preflight,
simulazione pre-authority, gate assenza same-run, ordine causale, authority
false, privacy/lingua/runtime contract e assenza di capture/marker reali. Il
collector operator-supplied riporta privacy scan PASS e SHA-256 package
`5a498239c9988445deedd0732009a2766a5ac564756c7c581461708faa9eca87`.
Il package non è materialmente presente sull'host AI: l'agente non ne ha
ricalcolato i byte. La qualification chiude quindi come
`PASS_OPERATOR_SUPPLIED`. La successiva review AI-PM del freeze correttivo è
PASS e la baseline D274/03 è formalmente approvata sul commit completo
`ed87646fe54e01baaffe0b12fd4ec73ba3e20fd5`, registrato nel record separato
`analysis/D274/D274_03_baseline_approval.json`. Questa decisione non approva
capture né live: il template runtime resta chiuso e la prossima decisione è
un'authorization separata, esplicita e one-shot.

```text
D274_02_TECHNICAL_REGRESSION=false
D274_02_REOPEN_REQUIRED=false
D274_02_MANUAL_HISTORICAL_STATE_CLEANUP=COMPLETED
D274_03_CORRECTIVE_IMPLEMENTED_OFFLINE=true
D274_03_OPERATOR_LANGUAGE=ITALIAN
D274_03_OFFLINE_EXECUTABLE_CLOSURE=PASS_LINUX_OFFLINE_ONLY
D274_03_LIVE_BRANCH_GATE=main
D274_03_POWERSHELL51_ENCODING_CORRECTIVE=IMPLEMENTED_OFFLINE
D274_03_POWERSHELL51_BOM_CORRECTIVE=PASS
D274_03_PS1_ENCODING=UTF8_WITH_BOM
D274_03_FIRST_NATIVE_QUALIFICATION_RESULT=FAIL_PARSE_BEFORE_RUNTIME
D274_03_FIRST_NATIVE_QUALIFICATION_GOODIX_PRESENT=false
D274_03_FIRST_NATIVE_QUALIFICATION_POWERSHELL=5.1.26100.8655
D274_03_FIRST_NATIVE_QUALIFICATION_HARDWARE_TOUCHED=false
D274_03_POST_BOM_NATIVE_QUALIFICATION_RESULT=FAIL_REPOSITORY_STAGE
D274_03_POST_BOM_NATIVE_QUALIFICATION_POWERSHELL_51=PASS
D274_03_POST_BOM_GIT_EXIT_DIRECT=0
D274_03_POST_BOM_GIT_EXIT_PIPE=-1
D274_03_POST_BOM_NATIVE_QUALIFICATION_HARDWARE_TOUCHED=false
D274_03_LASTEXITCODE_CORRECTIVE=PASS_OFFLINE
D274_03_WINDOWS_NATIVE_QUALIFICATION=PASS_OPERATOR_SUPPLIED
WINDOWS_NATIVE_PACKAGE_SHA256=5a498239c9988445deedd0732009a2766a5ac564756c7c581461708faa9eca87
WINDOWS_NATIVE_PACKAGE_BYTES_REHASHED_BY_AGENT=false
WINDOWS_NATIVE_ALL_STAGES=PASS_OPERATOR_SUPPLIED
BASELINE_APPROVAL_BLOCKED_PENDING_NATIVE_QUALIFICATION=false
D274_03_REAL_CAPTURE_CAPABILITY=1_CURRENT_AUTHORITY_TEMPLATE
SOURCE_CONTAINS_FUTURE_LIVE_PATH=true
# Stato di autorizzazione/esecuzione live di baseline (template non eseguito via questo kit):
# i contatori REAL_* restano a zero per i tentativi UI non validi; la capture osservata è separata.
LIVE_PATH_EXECUTED=false
LIVE_PATH_AUTHORIZED=false
D274_03_FREEZE_REVIEW=PASS
FREEZE_BUNDLE_SHA256=d7e5db36a0efec05ab33c82c221beb42c91aea4772a059764930ead5d8ed1d6b
D274_03_BASELINE_APPROVAL_REVIEW_PENDING=false
D274_03_BASELINE_APPROVED=true
D274_03_APPROVED_BASELINE_FULL_SHA=ed87646fe54e01baaffe0b12fd4ec73ba3e20fd5
APPROVED_FOR_CAPTURE=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
LIVE_EXECUTION=NOT_PERFORMED
# Contatori dell'attivita' diretta di invio/osservazione USB del Kit operatore
# (observer passivo: nessun sender Python/libusb; i due tentativi UI non validi non
# hanno aperto USB ne' catturato). La run Windows OEM osservata ha svolto l'attivita'
# USB/finger/command sul target, ma il Kit non la misura separatamente e tali conteggi
# non sono enumerati qui come totali della run.
REAL_USB_OPEN_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
REAL_GOODIX_COMMAND_COUNT=0
D274_SECOND_CYCLE_TARGET_OBSERVATION=OBSERVED_COMPLETE
REAL_CAPTURE_COUNT=1
# Stato canonico della capture osservata (run live autorizzata separata):
D274_03_OBSERVED_TERMINAL_FRAME=249
D274_03_OBSERVER_STOP_TRIGGER=WIRE_DRIVEN
D274_03_AUTOMATIC_RETRY_COUNT=0
D274_03_CANONICAL_RAW_SHA256=5f11d06763d34531c72283a189a47d9bcd7c666a5fa3c043ec1371eddf107998
D274_03_THIRD_CYCLE_OBSERVED=false
D274_03_OFFLINE_FINALIZER_CORRECTIVE=IMPLEMENTED_OFFLINE_ON_PRESERVED_RAW
D274_03_NO_NEW_LIVE_RUN=true
D274_03_DEVICE_TIMEOUT_CLAIM=UNKNOWN
# I conteggi low-level USB/finger/command della run Windows OEM osservata non sono
# enumerati qui (observer passivo): vedere i contatori di attivita' diretta del Kit
# nello stato di template/autorizzazione. L'unica scrittura persistente e' nulla.
PERSISTENT_DEVICE_WRITE_COUNT=0
NEXT_PRIMARY_BOUNDARY=D274_03_OFFLINE_FINALIZER_CORRECTIVE_REVIEW
NEXT_BOUNDARY_PREREQUISITE=FORMAL_FREEZE_REVIEW_POST_OBSERVATION
```
### D274/03 offline finalizer corrective — chiusura su raw preservato

La seconda-ciclo observation Windows Hello è stata eseguita in una run live
autorizzata separata e il relativo raw canonico è preservato byte-identico in
`captures/D274_03/D27403_20260826T201852Z/raw/wire.pcapng`
(SHA-256 `5f11d06763d34531c72283a189a47d9bcd7c666a5fa3c043ec1371eddf107998`).

Lo stato di confine osservato è:

- secondo B0 fingerprint osservato (frame terminale 249);
- trigger di stop dell'observer `WIRE_DRIVEN`;
- `automatic_retry_count = 0`.

Il finalizer iniziale (Hy3) aveva prodotto un falso fallimento: il traffico
post-boundary OEM (0x34 / 0x36 / IRQ 0x0100 / 0x20 e un B0 isolato al frame
265) veniva promosso a terzo ciclo perché bastava un solo `IRQ 0x0002`,
`COMMAND 0x22` o `FINGERPRINT_B0` dopo il secondo boundary. Dopo il frame 249
non ricompare però la coppia ordinata `IRQ 0x0002 → COMMAND 0x22 (body 01 00)
→ ACK 0x22 status 0x01`, quindi il B0 isolato al frame 265 non costituisce un
terzo ciclo di acquisizione.

La regola corretta richiede un lifecycle di acquisizione ordinato e non
ambiguo, almeno:

    IRQ 0x0002
    → COMMAND 0x22 con body esatto 01 00
    → ACK echo 0x22 con status esatto 0x01
    → FINGERPRINT_B0

I quattro eventi non devono essere adiacenti: eventi non-lifecycle irrilevanti
sono ignorati. Il detector usa tre esiti espliciti. `NONE` comprende i frammenti
isolati prima dell'avvio di un candidato (`IRQ 0x0002` solitario, `COMMAND
0x22` solitario o `FINGERPRINT_B0` solitario); `COMPLETE` richiede l'intera
catena esatta sopra; `CONTRADICTION` si applica quando, dopo l'avvio con `IRQ
0x0002`, compare evidenza lifecycle ripetuta, fuori ordine o malformata. Sono
quindi terminali fail-closed almeno body `0x22` diverso da `01 00`, ACK `0x22`
con status diverso da `0x01` e `FINGERPRINT_B0` prematuro. La contraddizione
non azzera più silenziosamente il progresso: produce
`THIRD_CYCLE_PROTOCOL_CONTRADICTION`, `boundary_status=NOT_OBSERVED_COMPLETE`,
`stop_reason=FAIL_CLOSED` e `third_cycle_observed=false`. Il riarm
`0x32 → ACK 0x32/0x01` resta solo corroborante, non obbligatorio.

`verify_finalized_capture()` preserva sia `THIRD_CYCLE_OBSERVED` sia
`THIRD_CYCLE_PROTOCOL_CONTRADICTION` quando il raw finalizzato conserva il
secondo B0 terminale indicato dall'observer e contiene poi il relativo evento
post-boundary; non li rimappa a
`CAPTURE_FINALIZATION_LOST_TERMINAL_EVIDENCE`, che resta riservato alla perdita
reale della finalizzazione (raw troncato/illeggibile).

Una correzione successiva (v2) ha poi rafforzato il growing observer: un terzo
lifecycle genuino presente nello snapshot ispezionato fail-closed con
`THIRD_CYCLE_OBSERVED` e non viene mai promosso a segnale terminale di
osservazione riuscita.

La correzione e la chiusura sono state eseguite offline sul raw preservato; non
è stata richiesta né eseguita alcuna nuova capture live. Il risultato
sanitizzato è in
`captures/D274_03/D27403_20260826T201852Z/sanitized/D274_03_second_cycle_evidence.json`:
`boundary_status=OBSERVED_COMPLETE`, `stop_reason=SECOND_FINGERPRINT_B0`,
`failure_class=null`, `third_cycle_observed=false`, `second_b0_frame.frame=249`.

```text
D274_03_OFFLINE_FINALIZER_CORRECTIVE=IMPLEMENTED_OFFLINE_ON_PRESERVED_RAW
D274_03_SECOND_CYCLE_OBSERVED_WIRE_DRIVEN=true
D274_03_OBSERVED_TERMINAL_FRAME=249
D274_03_OBSERVER_STOP_TRIGGER=WIRE_DRIVEN
D274_03_AUTOMATIC_RETRY_COUNT=0
D274_03_CANONICAL_RAW_SHA256=5f11d06763d34531c72283a189a47d9bcd7c666a5fa3c043ec1371eddf107998
D274_03_THIRD_CYCLE_FALSE_POSITIVE_FIXED=true
D274_03_ORDERED_NON_ADJACENT_LIFECYCLE_DETECTOR=true
D274_03_THIRD_CYCLE_DETECTOR_RESULT=TRI_STATE_NONE_COMPLETE_CONTRADICTION
D274_03_THIRD_CYCLE_CONTRADICTION_FAIL_CLOSED=true
D274_03_THIRD_CYCLE_CONTRADICTION_FAILURE_CLASS=THIRD_CYCLE_PROTOCOL_CONTRADICTION
D274_03_GROWING_OBSERVER_FAIL_CLOSED=true
D274_03_AUTHORITATIVE_THIRD_CYCLE_PRESERVED=true
D274_03_FINALIZATION_LOSS_REMAINS_DISTINCT=true
D274_03_REAL_CAPTURE_REPROCESSED_OFFLINE=true
D274_03_NO_USB_ACCESS=true
D274_03_NO_NEW_LIVE_RUN=true
D274_03_OFFLINE_EXECUTABLE_CLOSURE=PASS_LINUX_OFFLINE_ONLY
```

La storia tecnica dettagliata prosegue nelle sezioni seguenti; le frasi riferite
a step passati (es. D257/D259/D264) sono da intendersi come stato di quel
momento, oggi superato.

Non esiste ancora un driver Linux funzionante. La progressione live ha però
chiuso i confini A8, E4 e TLS sul firmware 12509: D239 ha eseguito il cold-start
OEM fino al B0/TLS, D241 ha verificato l'ownership exactly-once e il
ClientHello TLS 1.2, D242–D244 hanno localizzato e controllato i timeout E4 e
D245 ha completato l'intero percorso A8→E4→pre-D1→D1→TLS senza retry. D246 ha
ora completato live anche il solo exchange D4 autorizzato: un tentativo e un
invio, ACK esatto `d4/01`, nessuna response tipizzata, nessun application data
e stop terminale `STOP_AFTER_D4`. Cleanup, zeroizzazione del secret, restore di
fprintd e reseal sono riusciti; le famiglie di scrittura persistente sono
rimaste a zero. La semantica D4 resta quella già provata staticamente,
`VOLATILE_SESSION_INITIALIZATION`, limitata al receiver APP12509 esatto. A8,
E4, TLS e D4 non sono più blocker aperti. D249 ha ora chiuso offline il
framing e parsing AF e, dopo la correzione di review, ha chiuso realmente nel
nuovo core GPL due replay sintetici bounded fino a `FIRST_IMAGE_RECEIVED`:
FDT fresh e cached POV, sopra un transport astratto e senza USB reale. D250 ha
poi eseguito una volta il boundary AF sul target: TLS e D4 sono riusciti, AF è
stato inviato una volta come 13 byte logici in una submission fisica da 64 byte
con tail zero, e il device ha restituito una A0/AE strutturalmente valida con
checksum valido e body da 16 byte. Il percorso fresh-FDT non era ancora
autorizzato live a quel punto (stato storico D256/D257, oggi superato dal bounded
fresh-FDT arm path provato live in D262): D256 ne ha chiuso il lifecycle
osservabile host/bus, mentre il corrective D257 ha dimostrato che il replay
precedente copriva soltanto una sottosequenza proiettata. D258 ha trovato nel `gfusb.dll` target
l'orchestratore completo `gf_update_all_base`: `0x50` e `0x20` sono acquisiti
prima del terzo sample ma classificati soltanto dopo, mentre `0x82` fornisce
nel secondo byte la soglia unsigned del confronto assoluto fra i word FDT
grezzi. Il corrective D259 ha ora confermato meccanicamente il riflesso causale
dei classificatori: la matrice è derivata dai compare/jump/call del disassembly
hash-gated e tutti i return osservabili convergono a successo, possono cambiare
soltanto basi RAM e dirty/cache host OEM, ma non tabella FDT, payload o
raggiungibilità del primo `0x32`, né aggiungono comandi/retry/recovery
device-side. La Classe A del classifier è quindi confermata. Il corrective ha
però falsificato la precedente readiness complessiva: il runtime sealed D245
crea il TLS server come locale e lo chiude nel `finally` di `tls_handshake()`,
senza esporre la stessa sessione al futuro consumer B0. L'adapter GPL e la
continuità handshake→B0→secondo record sono provati offline sulla stessa
`SSLObject`, e il replay consuma ora B0 subito dopo `0x20` e prima del terzo
`0x36`; il plumbing nel runtime live restava `UNIMPLEMENTED` (stato storico D259,
oggi superato: D260 ha chiuso il gap architetturalmente e D261/D262/D266/D267/D268
hanno poi eseguito il percorso live). D259 era pertanto bloccato prima della
live-readiness review e non autorizzato live.

D260 chiude ora quel gap **sul solo piano architetturale offline** nel dominio
GPL `core/`, senza modificare il runtime sealed. Un coordinator production-shaped
possiede una sola sessione transport simulata, un solo handoff di secret
sintetico, un solo server TLS e un solo handshake; il lifecycle TLS resta vivo
attraverso D4 plaintext A0, AF/AE e gli A0 FDT, poi consuma il B0 baseline sulla
stessa sessione prima del terzo `0x36`. ACK e IRQ `0x0100` passano da contratti
distinti. Il rehearsal unico `D1/B0 TLS → D4 → AF/AE → 36,50,36,82,20,36,32`
e i 15 failure richiesti passano offline con zero retry, recovery speciale,
cache write e famiglie persistenti. Le policy fisiche D4 e B0 sono chiuse; la
tail fisica dei futuri A0 FDT Linux resta esplicitamente astratta. Ne segue
`READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW=true`, mentre review operativa,
backend USB reale, secret reale, baseline approvata, kit e autorizzazione live
restano separati e tutti i flag live non qualificati restano false.

D261 chiude offline il successivo gap operativo senza eseguire USB reale. Il
raw D255 è stato ricensito per comando: tutti gli A0 FDT hanno submission da
64 byte; i sei byte nonzero fuori frame ricorrono agli stessi offset assoluti
`40..45` su comandi non correlati e cambiano nella capture D254, mentre il
finale `0x32` OEM usa tail interamente zero e riceve ACK. Il candidate Linux
usa quindi fixed-64 e zero-fill deterministico per
`36,50,36,82,20,36,32`, senza replay di residui. L'accettazione target è prova
primaria per `0x32`, ma resta una nuova ipotesi live per gli altri comandi e il
rischio principale della futura singola run. Il nuovo path GPL integra
cold-start APP12509, secret reale protetto con validazione E4 prima del medesimo
handoff TLS, cache hash/CRC/OTP-bound, adapter libusb esatto con un solo reader
EP81, preflight, marker single-use, restore e reporting. La review AI-PM ha poi
rilevato quattro overclaim operativi: parte della matrice failure era
assertion-only, la funzione Python live sostituiva l'intento CLI con una
costante interna, il reader rinnovava il timeout per ogni completion non
corrispondente e la safety della report directory veniva chiusa soltanto in
pubblicazione. Il corrective dello stesso D261 separa ora capability
CLI-intent e Live-I/O, valida il contenuto protetto prima del marker, applica
una deadline monotonic assoluta e anticipa i gate directory pre-side-effect.
Tutti i 24 failure, i 13 casi demux/deadline e il rehearsal transazionale
passano offline. La review successiva ha individuato una bounded import closure
incompleta e una lettura secret anticipata rispetto al failure config90, senza
osservare side effect a import-time. Il corrective finale dello stesso D261
include ora nel set baseline anche `core/__init__.py` e
`poc/goodix5125/tools/binding_reference/__init__.py`: la closure dinamica
bounded comprende 16 file Python, non omette file e rileva drift sintetico di
entrambi gli initializer. Un subprocess nuovo, non privilegiato e senza flag
live importa l'intera closure con zero tentativi USB, accessi al filesystem
protetto, istanziazioni/materializzazioni del real secret loader, mutazioni
fprintd e creazioni marker. Manifest, config90 e cache hash/layout/CRC vengono
ora validati prima di costruire o materializzare il secret reale; i rehearsal
offline iniettano esclusivamente una boundary sintetica via Protocol e non
tentano alcun fallback real→synthetic. La suite completa passa offline; i
contatori reali USB/secret/comandi/marker/fprintd restano zero. Lo stato massimo
è `READY_FOR_BASELINE_APPROVAL_REVIEW=false` e
`OPERATIONAL_REVIEW_PENDING_APPROVED_BASELINE=false`; Utente e AI-PM hanno ora
approvato il full commit SHA `e9073a171697bd68dd2debabb851f23d007bf718` come
baseline live-critical immutabile, promuovendo la readiness a review operativa
(`READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW=true`, `READY_FOR_FDT_LIVE_REVIEW=true`),
ma `READY_FOR_FDT_LIVE=false`: approvazione baseline ≠ autorizzazione hardware.

D262 esegue la final execution-readiness review offline del bounded fresh-FDT arm
sulla baseline approvata `e9073a171697bd68dd2debabb851f23d007bf718`, senza modificare
nessun file live-critical (`D262_LIVE_CRITICAL_MODIFICATION_COUNT=0`). Il kit operatore
D261 è riusato in `--dry-run` da cwd realistico (PASS, zero USB/secret/marker/command/
fprintd reali); il verifier conferma che tutti i 17 blob del live-critical set sono
byte-identici alla baseline. La full suite offline (238 test) PASSa; il rehearsal
conferma che il runtime giunge solo a `STOP_AFTER_FDT_ARM_ACK` con traccia FDT
`0x36,0x50,0x36,0x82,0x20,0x36,0x32`, zero retry, zero famiglie persistenti, zero
A2/`0x70` di recovery, `0x22`/post-finger/enrollment/matching irraggiungibili. Rischio
live invariato: l'accettazione della zero-tail per `0x32` è provata
(`PRIMARY_TARGET_PROVEN_AND_ACK_ACCEPTED`), mentre per `0x36/0x50/0x82/0x20`
resta `EVIDENCE_SUPPORTED_DETERMINISTIC_CANDIDATE` /
`UNPROVEN_LIVE_HYPOTHESIS`. Lo stato era
`READY_FOR_D262_OPERATOR_EXECUTION_REVIEW=true`, `READY_FOR_D262_OPERATOR_EXECUTION=false`,
`READY_FOR_FDT_LIVE=false`: nessuna esecuzione hardware né autorizzazione implicita.

D264/01 riesamina quindi offline il rischio terminale dopo la prima immagine. La
continuazione Windows osservata (`0x34 → IRQ 0x0200 → 0x20 → seconda immagine →
re-arm`) è un workflow positivo, non prova un requisito device-side per lo stop.
`0x34` resta verificato come arm finger-up/continuation primitive e non è provato
come cancel/disarm/restore. D256 prova quiescenza host/bus e successiva re-entry
con nuovo `0x32` senza restore USB esplicito; D262 prova inoltre il successivo
cold-start bounded con A2 reset sensore volatile. Lo stato interno post-image
resta `UNKNOWN`, ma non esiste evidenza di write NVM o di stato persistente/non
recuperabile: il rischio è classificato `ACCEPTABLY_BOUNDED`, soltanto per una
successiva review di operationalization **offline**. `0x22` zero-tail e first
image restavano non live-proven a quel punto (stato storico D264, oggi superseded
da D267 + D268: IRQ2→`0x22`→ACK e primo B0 + decode raster `80x64` sono ora
chiusi live); nessuna readiness/autorizzazione/baseline live era approvata allora. L'audit timestamp della capture primaria misura ACK `0x32`→IRQ2 in
7108,212 ms: il timeout D263 di 5000 ms contraddiceva il path osservato ed è
corretto minimamente a una deadline host assoluta di 15000 ms, senza asserire
una lifetime interna del device.

D264/02 ha chiuso l'executable closure del candidate first-image **soltanto
offline**. Una rehearsal operatore synthetic-only preserva come default
`STOP_AFTER_FDT_ARM_ACK` e raggiunge `STOP_AFTER_FIRST_IMAGE` esclusivamente
con opt-in esplicito, attraversando il coordinatore pubblico, la deadline IRQ2
assoluta di 15000 ms, il candidate fixed64 `0x22`, il primo B0, il decode in
memoria e il cleanup host indipendente/fail-closed. Nessun live è stato
eseguito. Il launcher reale D261 resta distinto e arm-only: invoca ancora il
default del coordinatore e non può raggiungere il boundary first-image.
Pertanto `FIRST_IMAGE_LIVE_OPERATOR_WIRING=NOT_IMPLEMENTED` e la baseline
approval non è ancora raggiungibile; prima servirà un successivo step offline
di wiring e review del percorso reale protetto. Il primo candidate D264/03 era
soltanto uno skeleton parzialmente production-shaped: un callback `preflight`
opaco, una capability live-I/O non derivata formalmente dal marker, ownership
secret ambigua e una failure matrix più ampia dei test. Il corrective della
review AI-PM chiude questi difetti e quindi chiude il wiring pre-live sul solo
piano offline: il nuovo launcher production-shaped è
raggiungibile dalla shell esclusivamente con `--dry-run`, mentre ogni altra
invocazione termina `HARD_DISABLED_D264_03` prima di secret, marker, fprintd,
USB o comandi. La control flow futura usa capability e marker namespace
dedicati D265-future, guard baseline full-SHA e byte identity, dipendenze
pericolose iniettate e adapter futuro concreto, coordinator reale con opt-in esplicito
`STOP_AFTER_FIRST_IMAGE`, cleanup e restore indipendenti. Il path D261 e il suo
marker consumato restano invariati e arm-only. Ne segue
`FIRST_IMAGE_PRELIVE_OPERATOR_WIRING=IMPLEMENTED_OFFLINE`; non segue alcuna
approvazione baseline, autorizzazione o prova live. Il secondo corrective
centralizza poi capability D261/future in un'authority fissa non sostituibile
da callback, rende interna la tuple future-live canonica (18 file, incluso il
modulo operatore D261 importato), separa i due file del gate offline e lega
transaction, report futuro e marker preflight concreti nell'adapter.
D265/01 materializza ora, ancora **OFFLINE ONLY**, il kit operatore manuale
`operator_kit/d265-first-image-once.sh` → `tools/d265_live_first_image_once.py`.
Il surface ha esattamente dry-run e flag live futuro; il comando canonico è
`sudo env D265_APPROVED_LIVE_BASELINE_SHA=<FULL_APPROVED_SHA> ./operator_kit/d265-first-image-once.sh --i-authorize-one-d265-first-image-live-attempt`,
così sudo mantiene il proprio prompt password e `/usr/bin/env` trasporta la
baseline al processo root senza password handling. HEAD/worktree/path-set e
byte identity sono esatti. L’autorità D265 contiene 20 file: i 18 transitivi già
rivalutati in D264/03 più launcher e tool realmente raggiungibili. L'interazione
umana è interamente italiana e la richiesta dito nasce una volta sola, tramite
decorator host-side, immediatamente prima del vero `wait_event(15000)` dopo ACK
`0x32`, non durante cold-start/TLS/D4/AF/FDT. La telemetria non usa default
inventati: tracker di fase, audit del coordinator preservato anche su failure e
contatori monotoni IRQ2/ACK/B0 distinguono osservato, non raggiunto e ignoto. La
precedente autorizzazione non consumata non è trasferita: review AI-PM, merge,
approvazione del nuovo SHA e nuova autorizzazione restano quattro gate distinti.
`READY_FOR_LIVE=false`, `BASELINE_APPROVED=false`, `LIVE_AUTHORIZED=false`;
`0x22` fixed64 e prima immagine restavano non live-proven a quel punto (stato storico D265/01, oggi superseded da D267 + D268: IRQ2→`0x22`→ACK e primo B0 +
decode raster `80x64` sono ora chiusi live).

D265/02 chiude il successivo live one-shot, eseguito sulla baseline approvata
`2e57aa95cbe7d5eb468c12882cfa3a1a4d457e6d`, come `FAIL_CLOSED` prima di
`0x22`. L'unica autorizzazione è consumata e D265/02 non deve essere ripetuto.
La run ha aperto una sola sessione USB/transport e una sola TLS, ha completato
un handshake, materializzato il secret una volta e armato FDT una volta; dopo
la richiesta dito il runtime ha terminato con
`TimeoutError:libusb_bulk_timeout:0x81`. Nessun IRQ2 è stato consegnato al
runtime, nessun `0x22` è stato tentato o validato, nessun primo B0 è stato
ricevuto e non vi sono stati retry, recovery, reopen, write persistenti o
comandi post-image vietati. Cleanup host completato e secret zeroizzato sono
osservati; il report protetto conferma fail-closed, timeout, zero retry,
preflight della destinazione superato e trasferimento dell'ownership del
secret al coordinator, ma non prova direttamente il restore di fprintd.

L'audit byte-level della baseline prova un difetto software deterministico:
`SharedFrameRouter.receive_event()` seleziona soltanto i frame riconosciuti da
`_is_irq100()`, cioè A0 `control=0x36` con dati iniziali `00 01`, mentre il
first-image runtime attende un evento FDT IRQ `0x0002`. Un IRQ2 fisicamente
ricevuto verrebbe quindi lasciato nella vista non-event e la wait continuerebbe
fino al timeout; anche l'assenza fisica di IRQ2 produce timeout. Di conseguenza
l'emissione IRQ2 device-side durante D265/02 resta **UNDETERMINED**: il live ha
localizzato la failure nel delivery software pre-`0x22`, ma non ha provato né
smentito l'accettazione target di `0x22` fixed64 o la first image. Lo stato
interno device post-run resta `UNKNOWN`; `READY_FOR_LIVE=false`,
`LIVE_AUTHORIZED=false` e nessuna nuova baseline è approvata.

D266/01 corregge offline la classe di delivery nel router concreto. La review
AI-PM è conclusa con `PASS` e il fix è accettato. Il
predicato ad hoc `_is_irq100()` è sostituito da un classificatore FDT
strutturale che riusa `parse_fdt_event()`: sono eventi soltanto frame A0 con
una delle coppie control/IRQ target-specific osservate
`{0x32/0x0002, 0x34/0x0200, 0x36/0x0100}`. ACK `0xB0`, B0/TLS, risposte
normali e altre combinazioni FDT restano nella vista command. Test offline sul
`SharedFrameRouter` concreto provano IRQ100 e IRQ2 exactly-once, interleaving
nelle due viste senza perdita/duplicazione, deadline assoluta e divieto di un
secondo reader fisico. Una rehearsal sintetica attraversa
`SharedFrameRouter → _RouterEventSource → first-image runtime`: IRQ2 abilita
esattamente un tentativo `0x22`, mentre il timeout senza IRQ2 ne abilita zero.
Nessun hardware, secret reale, marker, fprintd o write persistente è stato
toccato. La correzione rimuove il blocker software noto ma non dimostra che
IRQ2 sia stato fisicamente emesso in D265/02, né prova live `0x22` o la prima
immagine. D266/02 ha però falsificato la readiness del percorso operatore sulla
nuova base: il dry-run ufficiale D265 termina fail-closed perché il suo manifest
storico conserva l'hash pre-fix di `core/usb_runtime.py`, mentre il worktree usa
correttamente il blob D266/01 accettato. I test router 8/8 e la suite mirata
37/37 restano verdi, ma l'executable closure operatore è `FAIL`. Non è stata
retro-modificata l'autorità storica né applicato un corrective live-critical
nello step di ratifica. La review AI-PM classifica quindi D266/02 come
`PASS_AS_FAIL_CLOSED_AUDIT`: il failure è l'atteso rifiuto di una authority
D265 storica e stale dopo la patch router accettata, non un difetto del gate.

D266/03 chiude ora **offline** quel corrective senza cambiare il router e senza
riaprire D265. Il nuovo candidate `operator_kit/d267-first-image-once.sh` →
`tools/d267_live_first_image_once.py` ha flag, environment, capability/nonce,
marker e report D267 distinti. La sua authority deriva dalla call graph reale
ed è composta da 20 file; include `core/usb_runtime.py` al blob post-D266
`c4e62b07…`, ma ha `baseline_approved=false`. Il verifier live richiede un full
SHA lowercase, `HEAD` uguale allo SHA approvato, worktree pulito, path-set
esatto e identità commit/worktree di ogni file, senza affidarsi ai soli hash
del manifest. Il dry-run da `/tmp` passa senza costruire dipendenze production
e con USB, secret, comandi, marker, fprintd, TLS live e write persistenti tutti
a zero. I 21 nuovi unittest, i test router 8/8 e la suite mirata 37/37 passano;
la regressione 303 = 299 PASS, 1 FAIL, 3 ERROR riproduce soltanto i quattro
esiti D261/pytest già noti. Ne segue
`D267_OPERATOR_CANDIDATE_READY_OFFLINE=true` e
`READY_FOR_NEW_BASELINE_APPROVAL_REVIEW=true`, non un'approvazione o
autorizzazione: `BASELINE_APPROVED_FOR_NEW_ATTEMPT=false`,
`LIVE_AUTHORIZED=false`, `READY_FOR_LIVE=false` e
`D265_02_RETRY_AUTHORIZED=false`.

**Chiusure storiche D261/D262, entrambe precedenti a D267.** Il
micro-corrective 3 D261 aveva chiuso il minting D261/future dietro seam private
post-durable-claim, impedito report/restore prima dei rispettivi preflight/start,
riallineato il contesto operatore future a D261 (`SUDO_UID` nonzero) e reso il
writer marker future robusto agli short-write. La successiva run D262 era stata
eseguita una sola volta con esito `PASS_STOP_AFTER_FDT_ARM_ACK`: nessuna
interazione dito, retry, write persistente, cache write o recovery A2/`0x70`;
una sola sessione USB e un solo handshake/server TLS; cleanup, restore e
zeroizzazione completati. La traccia
`0x36,0x50,0x36,0x82,0x20,0x36,0x32` aveva ritirato per il target primario il
rischio zero-tail dei comandi FDT raggiunti. Il marker era consumato e `0x22`
non era stato raggiunto. Questi sono antecedenti storici, non eventi successivi
a D267.

D267/01 è stato poi eseguito manualmente una sola volta sulla baseline
approvata `219c038600deb87da1cd93340b9bd07c14e1f5fe`. Il router corretto ha
consegnato live IRQ2; il runtime ha inviato esattamente un `0x22` fixed64
zero-tail, ne ha validato l'ACK target e ha ricevuto il primo B0. La run si è
quindi fermata fail-closed in
`RuntimeFailure:first_image_decode_failed`, senza retry, recovery, reopen,
write persistenti o comandi post-image vietati. Cleanup host e zeroizzazione
del secret sono completati. Sono pertanto live-proven delivery IRQ2, invio e
accettazione target di `0x22`, e arrivo del primo B0; non sono provati decode
né first image. L'autorizzazione D267/01 è consumata e un secondo tentativo non
è autorizzato.

D267/02 localizza offline l'emettitore in
`PersistentRuntimeCoordinator._run_first_image_terminal()`: il B0 supera outer
framing e il distinto catch TLS, poi ogni eccezione di
`parse_image_payload(bytes(plaintext))` viene appiattita in
`first_image_decode_failed`. Il parser richiede plaintext da 7693 byte,
payload image cmd0=2 con data da 7689 byte, prefix da 5 byte, record da 7684
byte e CRC-32/MPEG-2 valido. L'eccezione interna e i metadata sanitizzati non
sono stati conservati dalla baseline eseguita, quindi non è possibile
distinguere a posteriori header/lunghezza/checksum/control/POV/CRC. Il mismatch
più concreto da riesaminare è la policy image-specific `0x88`: Python è strict,
mentre DLL locale e Rocky ammettono il marker no-check; senza il trailer live
questa resta un'ipotesi `MEDIUM`, non un fatto. Stato:
`OUTCOME=D267_02_DECODE_FAILURE_BOUNDED_BUT_NOT_LOCALIZED`,
`READY_FOR_DECODE_CORRECTIVE_REVIEW=false`, `LIVE_AUTHORIZED=false` e
`READY_FOR_LIVE=false`.

D267/03 implementa ora il corrective **solo offline**. Il parser conserva un
record metadata-only con stage, lunghezze, classe major/control, POV, classe
trailer, esito checksum, lunghezza/CRC del record, classe eccezione e shape di
successo; il runtime lo mantiene anche dopo la zeroizzazione del plaintext e il
report/riepilogo operatore lo espone senza B0, plaintext, image bytes, raster,
pixel o hash sensibili. Nove fixture sintetiche distinguono success, envelope
troncato, declared-length mismatch, control inatteso, POV, checksum ordinario,
trailer `0x88`, record length e record CRC. `0x88` è soltanto riconosciuto:
resta soggetto al checksum additivo strict e non abilita alcun bypass. Il
manifest live-critical D266/03 resta storico; il dry-run usa un nuovo manifest
D267/03 con `baseline_approved=false`. Nessuna semantica decoder o wire cambia,
nessun live è autorizzato. Stato corrente:
`OUTCOME=D267_03_DECODE_DIAGNOSTIC_CORRECTIVE_READY_OFFLINE`,
`OBSERVABILITY_CHANGE=YES`, `DECODER_SEMANTIC_CHANGE=NO`, `WIRE_CHANGE=NO`,
`0X88_DIAGNOSTICALLY_RECOGNIZED=true`, `0X88_BYPASS_ENABLED=false`,
`LIVE_AUTHORIZED=false` e `READY_FOR_LIVE=false`.

La review AI-PM ha accettato D267/03 come corrective di sola osservabilità.
D267/04 ha quindi riesaminato staticamente il percorso OEM locale prima di
modificare l'acceptance. Il B0 viene consegnato al TLS engine e il plaintext
prodotto viene reinoltrato a `0x18005f098`; qui struttura e lunghezza sono
validate, il trailer `0x88` salta direttamente la verifica additiva e il ramo
`major == 2` consegna al consumer `data+5` per `declared_length-6`, cioè il
record immagine da 7684 byte del contratto corrente. Questo collegamento OEM
locale diretto supera il gate semantico; Rocky lo corrobora senza costituire la
base primaria. `parse_payload()` resta globalmente strict, mentre il solo
`parse_image_payload()` accetta `0x88` dopo framing, classificazione image,
lunghezza record e rifiuto POV. Il CRC-32/MPEG-2 del record resta obbligatorio
e fail-closed. Il trailer effettivo di D267/01 non fu conservato e resta
`UNKNOWN`: il corrective non identifica quindi la causa reale della run.
Nessun percorso wire/USB/TLS/FDT/IRQ2/`0x22`/ACK/B0, retry o write persistente
è cambiato; il dry-run del Kit Operatore resta offline, con manifest non
approvato e contatori sensor-reaching a zero. Stato corrente:
`SEMANTIC_CORRECTIVE_GATE=PASS`, `DECODER_SEMANTIC_CHANGE=YES`,
`DECODER_SEMANTIC_CHANGE_SCOPE=IMAGE_ADDITIVE_CHECKSUM_0X88_ONLY`,
`IMAGE_RECORD_CRC_POLICY_CHANGE=NO`, `WIRE_CHANGE=NO`,
`LIVE_AUTHORIZED=false` e `READY_FOR_LIVE=false`.

D268/01 sostituisce ora il surface operativo corrente senza eseguire hardware.
Il manifest D267/03, retro-modificato in D267/04 con l'hash del decoder nuovo,
è stato ripristinato byte-identico al commit
`42af60107cf21eb610de867a6de05b774ec1e37f` e torna a essere uno snapshot
storico immutabile; il decoder D267/04 corrente appartiene esclusivamente alla
nuova authority D268. Launcher, tool, flag, capability/nonce, marker e report
D268 sono distinti da D267. Il Kit espone in italiano lo stage e la classe
della failure, classe trailer, policy/esito checksum, CRC record e shape di
successo, senza B0, plaintext, immagine, raster, pixel o secret. Il dry-run
reale passa dalla root e da `/tmp` con zero USB, secret, comandi, marker,
fprintd, TLS live e write persistenti. Lo stato massimo resta
`BASELINE_APPROVED=false`, `LIVE_AUTHORIZED=false`, `READY_FOR_LIVE=false`:
la diagnostica è live-ready ma non è stata eseguita, e la prima immagine non è
ancora live-proven. Ogni test hardware futuro del progetto deve passare
esclusivamente da un Kit Operatore dedicato, con interazione e messaggi in
italiano; niente invocazione Python, comando USB manuale o bypass del launcher.

D268 (run live one-shot) è stata eseguita una sola volta, esclusivamente tramite
il Kit Operatore D268, sulla baseline approvata
`c03d32e8647444495e6615e41c2839cbddd62143`, con un solo tentativo autorizzato e
consumato. L'esito terminale è `PASS_STOP_AFTER_FIRST_IMAGE`: la run ha aperto
una sola sessione USB/transport e una sola TLS, ha completato handshake,
materializzato il secret una volta, armato FDT, consegnato IRQ2, inviato e
ACK-validato un `0x22` fixed64, ricevuto il primo B0 e decodificato con successo
il primo payload immagine. Il boundary first-image è quindi ora **chiuso live**
sul target APP12509.

L'evidenza target-specific appena acquisita è:

```text
FIRST_B0_COUNT=1
FIRST_IMAGE_DECODE_STATUS=SUCCESSFUL_RASTER_DECODE
FIRST_IMAGE_DECODE_STAGE=successful_raster_decode
FIRST_IMAGE_PAYLOAD_TRAILER_CLASS=0X88
FIRST_IMAGE_PAYLOAD_CHECKSUM_POLICY=NO_CHECK_0X88_ACCEPTED
FIRST_IMAGE_PAYLOAD_CHECKSUM_MATCH=False
FIRST_IMAGE_RECORD_CRC_MATCH=True
FIRST_IMAGE_RASTER_SHAPE=[80, 64]
```

La semantica image `0x88` è ora **target-proven** (non più soltanto
corroborazione statica/OEM/third-party): il trailer `0x88` salta il verifier
additivo, il checksum additivo risulta non coincidente, ma il CRC-32/MPEG-2 del
record è valido e il raster `80x64` è decodificato con successo. La run ha
mantenuto retry, recovery, reopen, write persistenti e comandi post-image vietati
tutti a zero; cleanup host e zeroizzazione secret sono osservati. Il ripristino
fprintd è classificato
`FPRINTD_RESTORE_CALLBACK_COMPLETED_WITHOUT_EXCEPTION=VERIFIED_BY_CONTROL_FLOW`
(il `finally` lo richiama e, se sollevasse eccezione, la run non restituirebbe
`PASS_STOP_AFTER_FIRST_IMAGE`); resta invece
`EXTERNAL_FPRINTD_FINAL_STATE=NOT_INDEPENDENTLY_OBSERVED`, poiché il control-flow
esclude un cleanup incompleto ma non osserva lo stato esterno finale del servizio.
Il marker D268 è consumato e la run non deve essere ripetuta: ogni futuro live
resta un gate separato, esclusivamente tramite Kit Operatore dedicato in italiano,
nuova baseline e nuova autorizzazione esplicita.

Aggiornando lo stato canonico, risultano ora **chiusi live** sul target APP12509:
A8, E4, TLS 1.2 PSK, D4, AF, il bounded fresh-FDT arm path, IRQ2, `0x22`, l'ACK
`0x22`, il primo B0, il decode della prima immagine e il raster `80x64`. I vecchi
blocker D252/D253/D259/D264 (seed/freschezza/restore/router) restano storia,
superati da D262/D266/D267/D268 e marcati come tali dove pertinenti.

La causalità storica D267/01 resta distinta e va classificata con la giusta
precisione epistemica. In D267/01 sono **osservati** la ricezione del primo B0 e
il fallimento `first_image_decode_failed`; il trailer effettivo di quella run non
fu conservato e resta `UNKNOWN`. In D268 sono **osservati target-specific live**
il trailer `0x88`, il mismatch del checksum additivo e il CRC record valido; è in
oltre **verificato** (da D267/04 sul call-flow OEM locale) che il vecchio parser
strict additivo è incompatibile con `0x88`. Ne segue che la causa di D267/01 è
una **inferenza causale forte** (`D267_01_CAUSE=STRONG_CAUSAL_INFERENCE`), non un'
osservazione retroattiva del trailer `0x88`: D267/01 non viene perciò riscritto
come se avesse registrato `0x88` allora — si registra soltanto la causalità
corroborata dalla nuova evidenza D268.

D250 aveva chiuso offline il boundary minimo exactly-one AF. L'audit
riproducibile della capture primaria ha isolato `D4/ACK d4-01 → AF → AE`:
request logica 13 byte, submission OEM da 64 byte, risposta AE diretta da 24
byte con 16 byte di stato, nessun ACK AF e 58,365 ms osservati tra ACK D4 e AF
OUT. La tail OEM AF contiene 51 byte fuori dalla lunghezza dichiarata, con sei
byte opachi nonzero identici nelle cinque occorrenze; il candidate non li
replayava e usava una tail deterministica zero. La run D250 ha ora provato sul
target APP12509 che questa zero-tail viene accettata fino a OUT completion e a
una risposta AE strutturalmente valida: `D250_AF_ZERO_TAIL_DEVICE_ACCEPTANCE`
e `D250_AF_ZERO_TAIL_STRUCTURAL_AE_RESPONSE` sono `LIVE_PROVEN`. Non è invece
provata l'equivalenza byte-per-byte o semantica universale con i sei byte opachi
nonzero della tail OEM. La run si è fermata fail-closed perché il validator
promuoveva il byte 0, osservato a `1` nelle cinque capture OEM, a una presunta
versione obbligatoria. Il contatore `af_response_count` veniva incrementato
solo dopo quel controllo: il valore live `0` è quindi un difetto di
osservabilità, non assenza di risposta. Il byte 0 live non è stato persistito ed
è `LOST_BY_OBSERVABILITY_GAP`. Cleanup, reseal, zeroizzazione del secret e
restore fprintd/segnali sono riusciti; retry, write persistenti e application
data sono rimasti a zero. Il marker D250 è consumato.

D251 ha poi eseguito una volta il candidate corretto sulla baseline approvata
`f07352ce085651568a9aedbf04b097df91d7c0bb`. TLS e D4 sono riusciti; AF è stato
inviato una volta con la zero-tail già accettata dal target e ha ricevuto una
sola A0/AE strutturalmente valida. Lo stato live è `byte0=0`, ancora opaco e
non una “versione 0”, con `flags=0x02`: TLS connected vero, POV-valid e locked
falsi, bit ignoti zero. D251 ha terminato a `STOP_AFTER_AF`; retry, famiglie di
scrittura persistente e application data sono rimasti a zero, mentre cleanup,
zeroizzazione secret, restore fprintd/segnali e reseal sono riusciti. Il marker
D251 è consumato. `POV_VALID=false` seleziona il percorso fresh-FDT; D2 non è
selezionato da questo stato.

D252 ha riesaminato offline quel percorso senza hardware. La capture target
prova che la tabella FDT-down è appresa dinamicamente dagli IRQ `0x0100` prodotti
da tre `0x36`, ma non chiude la provenienza/freschezza della tabella seed del
primo `0x36` per il cold-start corrente. Tutti i tre `0x32` usano la tabella
finale nella stessa sessione; dopo l'unico IRQ finger-down catturato il comando
target successivo è wire `0x22 [01 00]`, non il `0x20` del modello Rocky/D249.
Soprattutto, nessun cancel/disarm/restore post-FDT è provato: `0x34` arma
finger-up e `gfOnCancel` cancella una richiesta host, mentre A2/`0x70` non sono
osservati come restore FDT. Perciò `D252_LIVE_BOUNDARY=BLOCKED` e non esiste un
operator kit D252.

D253 ha chiuso offline la distinzione immagine target e ha corretto il modello
corrente: `0x20` e `0x22` sono entrambi SetMode Image con `more=0`, ma usano
rispettivamente `cmd1=0` nei due contesti baseline/no-finger catturati e
`cmd1=1` subito dopo IRQ finger-down `0x0002`. Il core invia ora exact wire
`0x22 [01 00]` dopo IRQ2, valida ACK echo `22` e impedisce un secondo tentativo
post-IRQ in caso di failure. L'audit dataflow ha però delimitato, non chiuso,
il bootstrap: `gfusb.dll` riceve il primo seed tramite un callback host che
copia 12 byte nella globale FDT, ma il chiamante e la sorgente ultima sono
esterni al DLL disponibile. Nessun `goodix.dat` OEM è presente; il path OEM
osservato confronta soltanto il prefisso OTP e non prova una table FDT. Inoltre
non esiste ancora cancel/restore device-side deterministico. D253 resta quindi
`BLOCKED`, richiede evidenza primaria esterna mirata e non crea un kit live.

D254 ha acquisito e parsato offline le fonti pubbliche richieste senza hardware
locale. Il WBDI di `yanxinwu946/goodix-5125-linux` è in realtà `27c6:5110`,
firmware `GF_ST411SEC_APP_12117`: mostra un cache OTP-bound da 13520 byte e tre
stage FDT riusciti con NAV e immagine base intercalati, ma non è prova diretta
APP12509. Lo stesso repository espone una costante claimed-12509
`b3b3...b7b7`, diversa dal seed target `adad...b2b2`, senza capture wire che ne
provi la derivazione. La capture pubblica Issue #63 è `27c6:5125`, firmware
ignoto: in 21 eventi IRQ2 usa sempre `0x22 [01 00]`, corroborando il modello
corrente, e mostra su 22 comandi `0x36` residui fisici agli stessi offset
40–45 del target, con valori diversi. Non contiene cold-start, cancel senza
dito o restore. D254 aveva quindi lasciato bootstrap e restore aperti e aveva
indicato come prossima evidenza una traccia Windows APP12509 da cold-start fino
ad arm, cancel senza dito e re-entry. D255 ha ora acquisito e recuperato quella
traccia. D256 ne ha poi esaurito offline i metadati USBPcap: il bootstrap/seed
è corroborato sul target e il nuovo arm viene accettato senza reset,
re-enumerazione o restore USB esplicito osservato. Il corrective D256 ha inoltre
esaurito la seconda cancellazione della stessa capture: il pending bulk-IN del
nuovo arm termina cancellato al frame finale `218`, seguito da 491,125998
secondi fino al marker host di finalizzazione senza altri packet. Il contratto
terminal-stop host/bus è quindi chiuso, path-bounded, come quiescenza USB; il
disarm, la lifetime e lo stato FDT interno restano non osservati.

D255 ha completato la singola acquisizione richiesta sulla baseline approvata
`f01b81d629ffe8af5eecb92ca93968045d5345ce`. La run canonica
`captures/D255_20260822T205631772Z_85c8c41f/` contiene un pcapng USBPcap da
27.684 byte, SHA-256 `802370d6...cc63337c`, con 218 frame leggibili e primo
frame `1`. Cold attach, UI ready, cancel e re-entry sono stati completati senza
dito. Il launcher ha fallito soltanto dopo `OPERATOR_PHASES_COMPLETE`: Windows
PowerShell 5.1 ha esposto `$null` per `ExitCode` sul `Process` creato con
`Start-Process -PassThru -NoNewWindow` e redirect, pur con processo terminato e
stderr TShark `218 packets captured`. È un failure di finalizzazione host-side,
non un failure di acquisizione.

Il recovery offline ha verificato hash, dimensione, leggibilità, 218 frame e
ordine univoco dei marker senza cambiare hash, size o mtime del raw. Gli
snapshot `run_clock_end`, `guest_topology_after_capture`, cache/log after e il
manifest originale non erano stati prodotti prima del falso failure e sono
`NOT_RECOVERABLE_RETROACTIVELY`; non sono stati ricreati dallo stato corrente.
Il manifest nuovo è esplicitamente `RECOVERED_ARTIFACT`. Il postprocessor reale
accetta questa provenance mantenendo i gate wire: descriptor e primo A8
APP12509 cadono, in quest'ordine, dentro i marker dell'attach manuale. La
capture prova cold attach target-specific, tre `0x36`, match primo seed/cache,
zero IRQ dito/`0x22`/image path nella finestra operatore, re-entry OEM e nuovo
`0x32` accettato. D256 ha chiarito il limite dell'assenza di log/snapshot
`after`: sul bus non compare alcun packet target durante l'intervallo cancel;
dopo l'inizio della re-entry compare una completion bulk-IN cancellata della
richiesta pendente, quindi il medesimo device `1:2` continua sugli endpoint
`01/81` e accetta il nuovo `0x32`. Non compaiono abort/reset, control transfer,
descriptor replay, reconfiguration o re-enumeration. Questo prova re-entry e
re-arm senza restore USB esplicito come prerequisito osservato, ma non prova
`DEVICE_FDT_DISARM_PROVEN` o la lifetime del prior arm. Il secondo cancel chiude
separatamente il comportamento bus: zero packet nell'intervallo operatore, una
sola completion bulk-IN cancellata host-side al frame finale `218`, quindi zero
packet target e totali per il resto della capture fino al duration boundary.
Questo prova la quiescenza USB osservata, non lo stato volatile interno del
sensore. Non è richiesta una nuova capture live equivalente.

Le note successive sulle revisioni del kit e sui precedenti failure sono
provenance storica, superata per lo stato corrente dalla run acquisita e dal
recovery appena descritto.

La terza review AI-PM ha corretto due overclaim residui. Con Goodix assente dal
guest, la UI fingerprint può legittimamente essere nascosta o indisponibile:
pre-attach si verificano perciò soltanto pagina Sign-in options, stato account,
enrollment incompleto, divieto di nuovo PIN e stato PIN esplicito. La
disponibilità sensor-dependent resta `UNKNOWN_BEFORE_ATTACH`; non è un gate di
autorizzazione. Il vero path Settings → Sign-in options → Fingerprint
recognition → Set up/Add a fingerprint viene verificato solo dopo capture
attiva, singolo attach, PnP guest, A8 APP12509 wire-derived e bootstrap passivo.

Il primo preflight nella VM reale ha poi osservato un ulteriore difetto locale
dello stesso D255: self-test `PASS`, zero azioni hardware, autorizzazione non
consumata, una sola `USBPcap1` e cache leggibile in
`C:\ProgramData\Goodix`, ma nessun `goodix*.log`/`wbdi*.log`. L'esistenza di un
log OEM non era mai stata provata come prerequisito e non protegge alcun gate
live-critical. La correzione rende quindi log OEM e cache Goodix fonti
opzionali e indipendenti, classificate `PRESENT|ABSENT`; restano terminali prima
dell'autorizzazione soltanto i path esplicitamente forniti ma illeggibili.

La successiva prima invocazione del ramo live sulla baseline approvata
`74a1ebda24166ac026ef7ed55c15f0d21e4593e3` non ha però superato il setup
pre-autorizzazione: PowerShell ha rifiutato `-Candidates @()` sulla funzione
`Write-OemLogSnapshot` con
`ParameterArgumentValidationErrorEmptyArrayNotAllowed`. Il binding è fallito
prima di entrare nella funzione e prima del confronto con la stringa di
autorizzazione; `$script:AuthorizationConsumed = $true`, il record
`authorization_consumed.json` e `Start-Process` sono tutti successivi nel
control flow. Il tentativo non ha quindi consumato l'autorizzazione, aperto USB,
avviato TShark né raggiunto l'attach host→VM.

La correzione di classe dello stesso D255 marca esplicitamente con
`AllowEmptyCollection` le collezioni di log, cache e setup che possono essere
vuote, e serializza gli snapshot senza righe come JSON letterale `[]`. Le liste
di interfacce restano semanticamente non vuote nel live, ma il binding permette
ora alla funzione di produrre un failure D255 esplicito invece dell'errore
generico del binder. Il nuovo `-PreAuthorizationSimulationOnly` rifiuta
autorizzazione, TShark, selettori e path reali, crea solo fixture sintetiche e
chiama la stessa `Invoke-D255PreAuthorizationEvidenceSetup` del ramo live fino
al boundary immediatamente precedente all'autorizzazione/capture. Copre sia
zero log sia log presente e un audit separato con zero cache root; non usa PnP,
USB o hardware. La suite offline verifica struttura e condivisione del ramo,
ma `pwsh` non è disponibile sull'host Linux: le due modalità sintetiche devono
ancora essere eseguite nativamente in Windows prima di dichiarare il kit pronto
per l'operatore.

La successiva singola run autorizzata sulla baseline
`999483362af23f67790eb6e54f4c02bb48bd6cd5` ha superato quel setup, consumato
l'autorizzazione e avviato TShark su `USBPcap1`, ma si è fermata prima del
prompt di attach perché il launcher pretendeva `wire.pcapng` già creato dopo
un grace period fisso di due secondi. Il processo TShark era ancora vivo;
Goodix non è mai stato collegato al guest e non è avvenuta alcuna azione
sensor-reaching. Una verifica successiva in sola lettura ha osservato il file,
ancora a zero byte, comparso diversi secondi dopo il controllo. È quindi
osservata una race di materializzazione/buffering host-side, non un failure
device-side o una prova di processo TShark non sano.

La correzione corrente elimina soltanto quel requisito pre-attach. Dopo il
breve grace period la readiness significa
`TSHARK_PROCESS_STARTED=true`, `TSHARK_PROCESS_ALIVE=true` e
`GOODIX_PRESENT_IN_GUEST=false`; il nuovo marker
`CAPTURE_PROCESS_STARTED` e il marker compatibile `CAPTURE_STARTED` non
dichiarano file, frame o pcapng valido. Dopo attach e bootstrap passivo il file
deve essere materializzato. Al termine restano obbligatori exit code TShark
zero, pcapng presente e non vuoto e readback TShark di almeno un frame prima di
`CAPTURED_PENDING_OFFLINE_VALIDATION`. I failure TShark includono exit code se
disponibile, command/arguments redatti, stato del path e stdout/stderr redatti.
L'audit locale conserva il timer bounded e il deadline PnP post-attach perché
proteggono rispettivamente durata della capture e vera enumerazione del target;
non esistono altri gate file/processo host-side equivalenti da rimuovere.

Il gate post-attach accetta solo `READY_WAITING_FOR_FINGER`, `UI_UNAVAILABLE`,
`NEW_PIN_REQUIRED` o `UNEXPECTED_PREREQUISITE`. Solo il primo entra nelle due
cancellazioni senza dito; gli altri chiudono la restore phase senza retry,
mutazione account/PIN, UI alternativa, recognition, dito o detach. Il timer
bounded completa comunque la capture: descriptor/A8, cache, primo `0x36` e
bootstrap restano sanitizzabili come
`PARTIAL_BOOTSTRAP_ONLY_UI_UNAVAILABLE`, con
`BOOTSTRAP_EVIDENCE_PRESERVED=true` e
`RESTORE_EVIDENCE_ACQUIRED=false`.

La re-entry OEM e perfino un nuovo `0x32` accettato provano soltanto che una
nuova sessione/arm è accettata; non osservano necessariamente la vita del prior
arm né un disarm FDT. Il sanitizer separa quindi cancel host, comandi wire,
close/D0Exit/D0Entry, re-entry, nuovo arm, cancel device-side e lifetime del
prior arm. Senza comando/transizione target-specific semanticamente chiusa,
`DEVICE_FDT_DISARM_PROVEN=false`, `RESTORE_CLOSED=false` e
`RESTORE_CLOSURE_DECISION=AI_PM_REVIEW_REQUIRED`. Ogni IRQ finger-down
`0x0002`, `0x22 [01 00]` o image path nella finestra operatore invalida la
restore evidence. La correzione resta pronta soltanto per review AI-PM, non per
una run operatore; nessuna autorizzazione live è implicita.

D247 cambia inoltre la strategia implementativa, senza modificare il confine
hardware: fino a D246 il codice di progetto è rimasto BSD-2-Clause e clean-room
rispetto a Rockytkg; dalla baseline post-D247 il futuro core userspace e i tool
collegati sono `GPL-2.0-or-later`, con riuso diretto Rocky consentito nel solo
dominio GPL quando licenza e provenance sono verificate. La validazione
factory-preserving sul target 12509 resta indipendente e obbligatoria. Il futuro
driver/glue libfprint è un dominio separato `LGPL-2.1-or-later`. D247 non ha
importato codice funzionale esterno e non ha eseguito AF/FDT/capture o hardware.
La verifica GitHub autenticata fornita dall'AI Supervisor ha poi chiuso il
blocker di provenance sulla baseline Rocky
`227eba219fa9e3fbac5bd59aca79f624f67cd11b` del 2026-08-17; D247 è quindi
`READY`. La verifica è esterna al workspace Codex ed è registrata come tale.
Resta obbligatoria la verifica puntuale di diritti, SPDX e componenti terzi per
ogni file che un futuro step deciderà effettivamente di importare.

D248 ha consolidato esclusivamente l'organizzazione del repository, senza
modificare runtime o confine hardware. Cache Python versionate e due backup
`.orig` generati sono stati rimossi dopo audit; i contenuti dei backup restano
ricostruibili dal commit storico `1c66b43c63e21e2dc4547a903154167233731fdd`
e non avevano riferimenti. `src/`, `tests/` e `poc/` rimangono congelati nelle
posizioni storiche per preservare riproducibilità e import della catena
D232–D246. Il nuovo sviluppo post-D247 continua invece nei domini `core/`,
`tools/` e `libfprint-driver/` definiti dalla mappa licenze.

| Area | Stato | Risultato |
| --- | --- | --- |
| Framing USB A0/B0 | confermato | endpoint, chunk da 64 byte, checksum e correlazione sono noti |
| TLS 1.2 PSK | handshake completo verificato live in D245 | D241 aveva provato il server flight; D245 ha completato il handshake sul target e si è fermato prima di D4 |
| Configurazione `0x80`/`0x90` | confermata per i path studiati | effetti volatili per quelle sole operazioni |
| A2 e `0x70` | convergenza host-side D231 | reset solo sensore e set-mode idle; corpi resident ancora assenti |
| Readback resident arbitrario | esaurito nel corpus locale | nessun path host-side safe trovato da D230 |
| Exact OEM replay | implementato e revisionato offline in D232 | state machine single-shot e oracle sintetico; live compilato fuori e D233 non autorizzato |
| Binding D190 PSK→E4 | reference recuperata e verificata | cinque KAT OEM-attributed non circolari e PE canonico hash-gated |
| Backend/orchestratore D233 | verificato offline, hard-disabled | schema candidate distinto; D234 e rischio operatore non autorizzati |
| Entrypoint production D235 | composto e verificato offline, hard-disabled | path reali deterministici, mapping terminale e restore collegati; D236 non autorizzato |
| Evidenza live D236 | parziale, non è un cold-start riuscito | E4 binding reale `match`; primo A2 trasmesso; ACK reale `B0/A2/07`; zero TLS/retry/persistent-write |
| Consolidamento D238 | verificato offline, source-sealed | policy ACK unica, replay pre-D1 completo con `0x01` e `0x07`, osservabilità redatta e unico kit operatore |
| Evidenza live D239 | pre-D1 integralmente superato su 12509 | 12 comandi, E4 `match`, D1 seguito da B0/TLS diretto di 52 byte; stop host-side `unexpected_data` |
| Transizione TLS D241 | live single-shot consumato, fail-closed | handoff e PSK object binding verificati; timeout dopo server flight; zero D4/app-data/retry |
| Run live D242 | fail-closed al primo E4 | OUT E4 completato, bulk IN in timeout senza frame completo; binding/TLS/pacing non raggiunti; cleanup/restore/reseal riusciti |
| Run live D243 | fail-closed al primo E4 | A0 corto ripristinato; OUT E4 completato e stesso timeout bulk IN; zero binding/TLS/retry; cleanup/restore/reseal riusciti |
| Run live D244 | fail-closed al primo E4 | fresh host boot documentato e controllo valido; OUT E4 completato, bulk IN timeout; nessuna prova di perdita elettrica sensore; zero retry e cleanup/reseal riusciti |
| Run live D245 A8→E4→TLS | successo, consumata | ACK A8 `07`, FW12509 esatto, E4 `match`, pre-D1/D1 e handshake TLS completi; stop prima di D4, zero retry/app-data/persistent-write |
| Run live D246 TLS→D4 | successo, consumata | handshake TLS completo; D4 attempt/send `1/1`, ACK `01`, nessuna response/app-data/retry/write persistente; `STOP_AFTER_D4`, cleanup/restore/reseal riusciti |
| Run live D250 D4→AF | eseguita una volta, marker consumato, fail-closed nel validator | TLS e D4 riusciti; AF logical 13 / physical 64 zero-tail inviato una volta; A0/AE strutturalmente valida con body 16; byte0 perduto dalla telemetria; zero retry/write/app-data; cleanup/restore/reseal riusciti |
| Run live D251 D4→AF | successo, consumata | exactly-one AF/AE; byte0 opaco `0`, flags `0x02`, POV false/TLS true/locked false, zero retry/write/app-data, cleanup/restore/reseal riusciti, `STOP_AFTER_AF` |
| Boundary storica D252 fresh-FDT | blocker originario, parzialmente superseded da D262 | seed/freschezza e restore erano aperti; D262 ha poi provato live l'intero bounded fresh-FDT arm path che consuma il seed, quindi la provenienza ultima non è più blocker operativo per quel path; restore/lifetime restano gap di conoscenza |
| Boundary storica D253 seed/restore/`0x22` | HISTORICAL / SUPERSEDED BY D267+D268 | a D253 `0x22` e first-image non erano ancora live-proven e restavano blocker della sola boundary first-image; tali confini sono oggi chiusi live da D267 (IRQ2→`0x22`→ACK) e D268 (primo B0 + decode raster `80x64`) |
| Audit esterno D254 | bloccato offline, nessun kit live | cache/layout OEM 5110/12117 e capture Issue63 riducono bootstrap e corroborano IRQ2→`0x22`/tail; seed APP12509 e no-finger restore restano non chiusi |
| Acquisizione Windows D255 | capture riuscita e run consumata; finalizzazione host-side recuperata offline | 27.684 byte/218 frame, cold attach APP12509, fasi zero-finger complete, seed/cache match; snapshot after non recuperabili e restore non chiuso; nessuna nuova capture richiesta |
| Contratto lifecycle D256 | audit offline completo dei packet USBPcap D255, incluso corrective terminal-cancel | primo cancel: re-entry e nuovo `0x32` accettato senza restore USB esplicito; secondo cancel: zero packet nell'intervallo, pending bulk-IN cancellato al frame finale `218`, zero packet residui e quiescenza USB host/bus provata; disarm/lifetime/stato FDT interno non osservati |
| Candidate fresh-FDT D257 | BLOCKED exact offline; nessun backend/kit live | replay proiettato storico PASS; sequenza esatta D255 `36,50,36,82,20,36,32`, ma gate host dinamici NAV/delta/baseline non derivabili; first-`0x36` single-shot fail-closed; freshness non è il solo blocker |
| Chiusura gate host D258 | avanzamento offline, candidate ancora BLOCKED | orchestratore target in `gfusb.dll`; gate `0x82` chiuso e implementato; `0x50`/`0x20` corretti come input a classificatori post-stage2 ancora non riproducibili; timeout per comando; zero hardware |
| Corrective contratto minimo D259 | BLOCKED sul plumbing TLS runtime; live non autorizzato | Classe A confermata meccanicamente dal CFG; replay B0 ordinato subito dopo `0x20`, same-`SSLObject` e continuità TLS PASS offline; il runtime sealed D245 chiude e non espone l'engine, quindi `READY_FOR_FDT_LIVE_REVIEW=false` |
| Runtime persistente D260 | architecture readiness PASS offline; operational/live false | nuovo coordinator GPL con un server/sessione/handshake TLS, D4 A0 plaintext, EventSource separato e minimal FDT continuo; 15 failure contenuti, `src/`/launcher storici invariati; physical FDT A0 ancora astratto |
| Corrective readiness D261 | PASS offline per baseline-approval; operational review promosso, live false | closure import 16/16 e import purity PASS; non-secret prima del secret; capability CLI-intent/Live-I/O distinte, 24 failure e 13 casi demux execution-derived; 238 test PASS, full commit SHA `e9073a171697bd68dd2debabb851f23d007bf718` approvato da Utente e AI-PM, zero-tail per comando resta rischio live |
| Kit D265/01 first-image | PASS offline; live successivamente eseguito in D265/02 | operator path one-shot, prompt immediatamente prima della wait IRQ2 e telemetria truth-preserving; baseline eseguita poi fissata a `2e57aa95cbe7d5eb468c12882cfa3a1a4d457e6d` |
| Run live D265/02 first-image | fail-closed pre-`0x22`, autorizzazione consumata | una USB/sessione/TLS/handshake e un arm finale; timeout EP81, zero IRQ2 consegnati/`0x22`/B0/retry/recovery/reopen/write; difetto router IRQ2 provato sulla baseline, emissione fisica IRQ2 non determinabile |
| Corrective D266/01 router eventi | PASS offline; review AI-PM PASS, fix accettato, live false | classifier FDT strutturale condiviso con il parser canonico; IRQ100/IRQ2, command routing, interleaving, deadline, single-reader e seam sintetico IRQ2→un `0x22` PASS sul router concreto; nessuna nuova evidenza device-side |
| Closure D266/02 post-review | CORRECTIVE REQUIRED; baseline-readiness false | test router 8/8 e mirati 37/37 PASS; regressione 282 = 278 PASS, 1 FAIL, 3 ERROR invariata; dry-run D265 fail-closed sul solo hash pre-D266 di `core/usb_runtime.py` nel manifest storico, con tutti i contatori reali a zero |
| Corrective D266/03 authority D267 | PASS offline; pronto per review di una nuova baseline, live false | D265 immutabile e retry vietato; nuova authority D267 di 20 file con capability/marker/report/flag distinti, router post-fix incluso, verifier Git full-SHA/HEAD/clean/path/byte identity, dry-run esterno zero-side-effect e 21 unittest PASS |
| Run live D267/01 first B0 | fail-closed nel decoder, autorizzazione consumata | IRQ2 consegnato, un `0x22` fixed64 inviato e ACK-validato, primo B0 ricevuto; zero retry/recovery/reopen/write/comandi post-image; decode e first image non provati |
| Analisi D267/02 decoder | failure bounded offline, subpredicato live non recuperabile | emettitore esatto `persistent_runtime.py:444`; TLS consumption superato per call-flow, poi catch opaco su `parse_image_payload`; fixture 7693→7684→80x64 PASS, mismatch `0x88` candidato MEDIUM; manca diagnostica sanitizzata length/header/checksum/CRC |
| Corrective D267/03 decode observability | READY offline, live false | diagnostica sanitizzata per nove classi; report/audit preservano lo stage interno; `0x88` visibile ma strict e senza bypass; acceptance e wire invariati; D209/D210 non presenti e non re-queryable |
| Audit/corrective D267/04 `0x88` image no-check | READY offline, live false | gate PASS su call-flow OEM TLS-plaintext→parser→major 2→record 7684; bypass additivo solo image dopo gate strutturali/POV; parser generico e CRC record strict; trailer D267/01 ancora unknown |
| Kit D268/01 first-image con decoder D267/04 | READY offline, poi run live eseguita una sola volta | nuovo namespace one-shot e authority corrente di 20 file; manifest D267/03 ripristinato storico; diagnostica typed/sanitized esposta in italiano; dry-run root e `/tmp` zero-side-effect; run D268 conclusa `PASS_STOP_AFTER_FIRST_IMAGE` sulla baseline `c03d32e...` |
| Run live D268 first-image (Kit D268/01) | successo, marker D268 consumato | IRQ2 consegnato, `0x22` ACK-validato, primo B0 e decode raster `80x64` PASS; trailer `0x88` no-check target-proven, checksum additivo mismatch, CRC record valido; zero retry/recovery/reopen/write/comandi post-image; cleanup e zeroizzazione riusciti; restore callback completata senza eccezione; stato esterno finale fprintd non osservato indipendentemente |
| Codec immagine | confermato offline + CRC record validato live + decode eseguito live | record 7684 byte → raster u16 `80x64` (CRC-32/MPEG-2 record valido e raster `80x64` live-proven in D268) |
| D269/01 adapter Linux/libfprint | READY offline; pixel+intensity CLOSED; full pipeline NOT_YET_CLOSED; live false | API locale libfprint 1.94.5 auditata: `FpImage` è packed grayscale u8, 1 B/pixel, `width*height`; mapping Linux fixed full-range `round(v*255/4095)` nel glue LGPL, test sintetici PASS; `FpImage::ppmm` auditato: NBIS lo consuma, SIGFM no, valore fisico APP12509 UNKNOWN (500 DPI Rockytkg = terza parte); orientation/polarity non inventate; prossimo boundary `LIBFPRINT_IMAGE_PIPELINE_INTEGRATION_OFFLINE` con prerequisito ppmm |
| D270/01 costruzione FpImage reale | READY offline; object/ownership/dimensions CLOSED; full pipeline PARTIALLY_CLOSED; live false | helper LGPL opaco costruisce `FpImage(80,64)` reale e object-owned dal raster sintetico via adapter D269; weak-finalization, strict build, ASan/UBSan, root/external-cwd e symbol audit PASS; ppmm fisico separato `UNKNOWN`, NBIS fail-closed, SIGFM ppmm-independent ma non selezionato; orientation/polarity ancora unresolved |
| D271/01 policy feature extractor | READY offline; policy CLOSED; full pipeline PARTIALLY_CLOSED; live false | call-flow extractor/template/matcher/enrollment locale ricostruito; SIGFM unico `CANDIDATE_FOR_VALIDATION` con input 80×64 strutturalmente supportato ma gate ≥25 keypoint e qualità target ignota; NBIS strutturalmente accetta 80×64 ma resta `BLOCKED` per ppmm ignoto e requisito ≥10 minutiae non provato; orientation/polarity unresolved, nessun claim da fixture sintetiche o Rocky |
| D272/01 pre-live multi-frame + metriche SIGFM | BLOCKED per live/executable closure; avanzamento offline reale; live false | ordine OEM corretto con `0x50` obbligatorio; modello bounded 2–8 sample, single-reader e fail-closed PASS sintetico; seam SIGFM LGPL con mapping D269, gate 25, score/error ed exception containment PASS su double; origine/freshness tabella `0x34`, seconda iterazione target e build SIGFM reale bloccata da OpenCV4-dev assente; policy ACK del ciclo corretta post-review AI-PM da `0x01|0x07` a `status` esatto `0x01` (`D272_ACK_STATUS_CONTRACT=CLOSED_OFFLINE_EXACT_0X01`), blocker primari invariati |
| D273/01 closure post-first-image + SIGFM reale | PARTIAL CLOSURE offline; live false; executable closure globale FAIL_NOT_AVAILABLE | dataflow up/down OEM chiuso: IRQ2 aggiorna up globale di sessione consumata da `0x34`, IRQ0200 aggiorna down consumata da re-arm `0x32`; packet 249 chiuso come A0 NAV `0x50` 2417/2410; modello corretto con source IRQ/generation e timestamp per transizione; seconda iterazione target e timeout non osservati; host e SDK senza OpenCV4-dev, vero `sigfm.cpp` non compilabile, nessuna installazione |
| D274/01 Kit Windows/OEM pre-live | READY offline; hard-disabled; live false | sanitizer metadata-only, target/A8/hash/schema/privacy gate e fixture sintetica del secondo ciclo PASS; capture storica termina a ACK re-arm e resta `MISSING_SECOND_IRQ2`; workflow candidato no-commit, nessuna attribution retroattiva |
| D274/02 qualificazione nativa Windows | CLOSED / PASS; tre run storiche preservate; live false | run 1 FAIL source-scan `-f`, run 2 FAIL `.Count` sotto PowerShell 5.1, run 3 PASS nativo completo dopo corrective; nessuna regressione tecnica e nessuna riapertura |
| D274/03 Kit one-shot secondo ciclo | Windows native qualification PASS operator-supplied; baseline/capture/live false; freeze/review AI-PM pending | runner futuro vincolato a `main`; BOM UTF-8 e `$LASTEXITCODE` corretti; literal `$TsharkPath` non interpolato sotto StrictMode e privacy contract verificato nei reali owner observer/postprocessor; run finale PowerShell Desktop 5.1 tutti-stage PASS con Goodix assente, zero capture/USB/dito/comandi/retry/write; SHA package operator-supplied `5a498239…9eca87`, byte non ricalcolati dall'agente; D263 resta negativa |
| D275/01 production multiframe Linux | READY offline; live false | `PersistentRuntimeCoordinator` chiude il secondo B0 sullo stesso transport/TLS/PSK; allowlist post-image `0x34,0x20,0x50,0x32,0x22`; zero retry/reopen/write; terzo ciclo irraggiungibile |
| D275/02 Linux second-B0 live one-shot | READY offline; candidate live pending AI-PM; live false | authority Git SHA sul live-critical set (21 file, incluso `multiframe_validation` e `binding_reference`); report/marker D275 distinti; publish dopo `STOP_AFTER_SECOND_IMAGE`; UX operatore poka-yoke italiana su `stderr` con JSON macchina su `stdout`; fake-live rehearsal visiva hardware-inert; D268 storico frozen `c03d32e...`; nessuna USB reale |
| D275/03 post-live root-cause `0x34 → IRQ0200` | corrective offline; due run live storiche fail-closed; nuova live false | tentativo 2 elimina timing operatore; prima immagine provata dal call-flow e telemetry monotona corretta; baseline Linux passava raw IRQ2 nel `0x34`, mentre tre cicli OEM APP12509 provano `80 || ((raw>>1)+0x1d)` con touch `0x003f`; down-table IRQ0200 corretta a `80 || (raw>>1)`; timeout 15 s non corto, lost-event race non trovata; causalità mismatch `STRONG_CAUSAL_INFERENCE`; terza run equivalente vietata |
| D275/04 closure secondo B0 Linux live | CLOSED / PASS; una sola run live autorizzata e consumata; nessuna nuova live autorizzata | `PASS_STOP_AFTER_SECOND_IMAGE` sulla baseline `6eb60856...`; closure consolidata nel commit `42819c05...`; trace `0x36,0x50,0x36,0x82,0x20,0x36,0x32,0x22,0x34,0x20,0x50,0x32,0x22`; FDT-up/down derivate OEM; `IRQ 0x0200`, secondo `IRQ2`, secondo `0x22`, secondo B0 e stop wire-driven osservati; causalità FDT promossa a `LIVE_VALIDATED`; zero retry/reopen/write persistente; `TARGET_DEVICE_TIMEOUT=UNKNOWN`; prossimo boundary review AI-PM D275/04, nessuna autorizzazione live implicita |
| D276/01 architettura production `FpImageDevice` | READY / CLOSED_OFFLINE; corrective documentation-only; live false | preservata `NATIVE_IN_PROCESS_C_LGPL_CLEANROOM`/confidence `HIGH`; release tail corretto fino a NAV prima del finger-off, post-up B0 mai consegnato a libfprint e solo re-arm `0x32` gated da `AWAIT_FINGER_ON`; reentrancy/deactivate esplicitata; `GoodixDeviceContext` owner TLS/secret ma lifetime TLS cross-activation irrisolto; cancel device-side e quiescenza production arbitraria non provati, policy conservativa `POISONED/QUIESCENCE_UNKNOWN`; reimplementazione indipendente con provenance controllata, non conclusione legale |
| D276/02 shell `FpImageDevice` host-only | READY / PASS_HOST_ONLY; validation clean-tree GitHub Actions run 33165906857 (commit 87d4aace...); 2 run deterministiche (14/14 normal PASS, 14/14 ASAN/UBSAN PASS); live false | shell C/LGPL non registrata con backend in-memory che esercita il vero `FpImageDevice` 1.94.5; correzioni: cancellazione `ACTIVATING` collegata al cancellable dell'azione, `GError` owned ai confini, deactivation trattenibile, generation token per eventi fake, re-arm exactly-once per generation, launcher con timeout e propagazione failure; nessun USB/TLS/secret/fprintd/VID:PID usato; unresolved production/device quiescence e TLS session lifetime invariati; prossimo boundary D276/03 |
| D276/03 router A0/B0 single-receive | READY / PASS_HOST_ONLY; CI clean-tree PASS; merge main 474aa2b9...; live false | nuovo router C/LGPL transport-agnostic posseduto dall’open epoch, parser incrementale comune A0/B0, demux in-order/exactly-once con `GBytes`, un solo completion point e massimo una receive fake outstanding; malformed/truncated fail-closed, generation stale e callback post-cancel ignorate; nessun USB/TLS/secret/VID:PID; prossimo boundary D276/04 host-only |
| D276/04 TLS/backend FpiUsbTransfer | READY / PASS_HOST_ONLY; AI-PM+CI PASS; live false | unico context owner di router/TLS/backend, A0 bypass non-TLS, B0→Memory-BIO, TLS OUT sul medesimo backend, generation unica e cancel/drain callback-driven; nessun submit reale; equivalenza hardware e quiescenza device restano irrisolte |
| D277/01 native A8 reale | BLOCKED_ENVIRONMENT_USB_OPEN_FAILED; PASS_HOST_ONLY / FAIL_TARGET_LIVE; autorizzazione consumata | harness-only `FpDevice`/`GUsbDevice` con A8 immutabile e backend/router production-shape; target unico 1:4 port 7, ma open fallito prima di claim/submit; nodo `root:root` 0664 senza ACL e user privo di write permission, causa strong inference; A8 count 0, zero retry/reopen/reset/write; storico preservato |
| D277/02 native A8 reale | PASS; una sola run live autorizzata e consumata; autorizzazione corrente falsa | target `27c6:5125` 1:4 port 7 aperto/reclamato, exact A8 `a00600a6a803000000ff`, ACK logico e risposta tipata con firmware `GF_ST411SEC_APP_12509`; max un bulk-IN outstanding, second reader assente; prerequisito host ACL temporanea named-user applicata e rimossa dall'operatore, nessuna udev/owner/mode/sudo; zero retry/reopen/reset/secret/TLS/image/persistent write; prossimo boundary review AI-PM, nuova autorizzazione esplicita richiesta |

## Fonti e confini di pubblicazione

Il repository privato è il workspace canonico di sviluppo. Il repository
pubblico è una superficie di pubblicazione congelata: non viene sincronizzato
da D247 e potrà ricevere soltanto un export futuro, separato, sanitizzato e
auditato. Un working tree pulito/equivalente non rende pubblicabile la history
privata; capture, DLL, firmware, secret o dati biometrici transitati nella
storia richiedono clean export, nuova storia o filtro dedicato.

Le evidenze autentiche private hanno sede canonica in `<git-root>/captures/` e
possono essere versionate nel repository privato per renderle disponibili agli
strumenti autorizzati sul remoto privato. Bundle ed export pubblici escludono il
raw; la futura pubblicazione richiede sanitizzazione esplicita di contenuto e
history. Non esiste sincronizzazione automatica privato→pubblico.

La root contiene soltanto fonti canoniche, licenze, linee guida e directory di
progetto. Gli output Dxxx sono step-local e non cumulativi in
`analysis/Dxxx/`, inclusi bundle e checksum; `analysis/README.md` è il solo
indice sintetico e non sostituisce questo manuale. Il manifest
`analysis/D248/D248_binary_relocation_manifest.json` fissa blob Git, SHA-256,
dimensione, destinazione e riferimenti dei bundle storici in root. Le undici
coppie D230–D238 possono essere spostate insieme in una fase meccanica
byte-preserving. La coppia D239 resta invece intenzionalmente in root perché il
controllo offline D245 apre quel path per verificare i launcher storici: la
riproducibilità prevale su una root solo esteticamente perfetta. Rimuovere
l'eccezione richiede uno step futuro che migri esplicitamente la dipendenza
D245 e ne verifichi nuovamente l'executable closure. La relocation di layout
non cambia stato tecnico né autorizzazioni live.

Le categorie restano distinte:

- capture Windows, `gfusb.dll`, APP12509 ed evidenza live locale sono evidenza
  privata target-specific e autorità primaria per il comportamento sul target;
- codice esterno Rockytkg verificato GPL può essere una fonte implementativa
  riusabile in `core/`/`tools/`, con attribution e ledger, ma non prova safety;
- materiale OEM/proprietario, secret, capture e dati biometrici non sono
  redistribuibili e non ricevono una licenza open source per collocazione;
- documentazione e codice pubblicabile seguono la mappa file/directory in
  `docs/LICENSING_AND_PROVENANCE.md`.

Il corpus D230 è `GoodixExport.zip`, indicato dall'operatore come corpus privato
recuperato e già provenance-validato, SHA-256
`2b76e294059fcfa2f32a6e75d92d04731b41a01bd3221852b5584ce409a3e45e`.
Contiene `gfusb.dll` SHA-256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`
e una capture recuperata SHA-256
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`.
La prima capture resta definitivamente perduta e non è sostituita da riepiloghi.

La testimonianza indipendente di `mkl-corbachoh` nella issue GitHub #1 (https://github.com/Rockytkg/goodix-linux-27c6-5125/issues/1) resta
classificata `EXTERNAL_THIRD_PARTY_LIVE_CORROBORATION`. Sul proprio target
riferisce `27c6:5125`, chip `0x2504`, firmware nativo 12509 preservato,
TLS-PSK, enrollment, verifica same/different-finger, autenticazione PAM e
nessun firmware flash. Riferisce però anche `MCU read 0xBB010003 status 0x01`,
quindi assenza di dati PSK preesistenti, e provisioning una tantum di una nuova
PSK; riporta inoltre la coesistenza di eventi FDT plaintext e frame immagine
protetti TLS. È corroborazione esterna utile, ma non prova primaria del nostro
target, non prova la preservazione della PSK Windows/factory preesistente e non
autorizza automaticamente alcuna futura operazione live.

### Rockytkg — snapshot locale implementativo canonico

Il riferimento operativo unico è lo snapshot versionato
`<git-root>/Rockytkg/`; la sua scheda canonica è
`Rockytkg/PROVENANCE.md`. Il repository online
`Rockytkg/goodix-linux-27c6-5125` registra l'origine ma non è una dipendenza del
workflow ordinario. La Issue #1 resta una fonte esterna distinta e non è
incorporata da un normale snapshot Git.

La baseline preservata è il commit
`227eba219fa9e3fbac5bd59aca79f624f67cd11b`: il `LICENSE` assegna
GPL-2.0-or-later al codice originale, LGPL-2.1-or-later a `src/goodixgf.c`,
lascia `libfprint/` ai termini upstream ed esclude dalla blanket license il
firmware vendor. Gli header campionati confermano GPL per
`goodix_capture.c`, `goodix_init.c`, `goodix_tls.c` e LGPL per `goodixgf.c`;
il copyright repository-level indica `liushicong (Rockytkg)` senza implicare
titolarità su ogni riga o contributo terzo. Il tree upstream preservato è
`6dda93a960ceddb085c59b5382df47ecc5d56a39`; il gitlink upstream originario di
`libfprint` è `7ebe0c809b4d1df3400e84299a4ec4acdea84590`, mentre nello snapshot locale
`Rockytkg/libfprint/` è materializzato come file normali, senza submodule attivo
o `.git` annidata.

Preservazione non equivale a diritto di riuso: ogni import richiede audit
file-specifico e registrazione nel ledger. Il codice originale Rocky è GPL,
`src/goodixgf.c` è LGPL, `libfprint/` conserva i termini third-party e
`firmware/st411sec_app.bin` più i byte firmware in `include/goodix_fw.h` sono
materiale vendor fuori dalla blanket GPL/LGPL. Lo snapshot e il materiale
vendor non confluiscono automaticamente nel repository pubblico.

La issue Rocky #1 verificata chiarisce inoltre che la validazione hardware
diretta dell'autore riguarda un'unità 12508, non un 12509 non modificato. Il
codice Rocky è quindi una fonte implementativa autorizzata, ma resta
corroborazione esterna e non prova primaria della preservazione factory/PSK o
del comportamento APP12509. Questi due ruoli non vanno confusi; ogni futuro
import richiede comunque verifica file-specifica di diritti e SPDX.

#### Issue #1 — corroborazione terza parte (THIRD_PARTY_CORROBORATION, non prova locale)

D274/03 forward-analysis registra come corroborazione esterna il report di un
terzo utente (`mkl-corbachoh`) su Huawei MateBook con Goodix `27c6:5125`, chip ID
`0x2504`, firmware nativo `GF_ST411SEC_APP_12509` mantenuto, TLS-PSK riuscito,
enrollment fprintd con 8 capture, verify-match sul dito registrato,
verify-no-match su dito diverso e autenticazione PAM funzionante. Questo è
**corroborazione implementativa**, non autorità probatoria per APP12509 sul nostro
target. In particolare il test terza parte **NON preservava una PSK Windows
esistente**: il dispositivo riportava PSK assente (status `0x01`) ed è stata
provisionata una nuova PSK una volta. Pertanto non dimostra la preservazione
della PSK Windows/factory. Il maintainer Rockytkg ha inoltre chiarito che
l'upstream considera ancora 12509 come firmware diverso da 12508 e quindi può
entrare nel percorso ClearApp/firmware-update; non possiede un global
no-write/read-only init mode; e considera un percorso 12509
keep-current-firmware + no-write una direzione sensata. Per il nostro progetto
restano invariati gli invarianti: nessun flash/IAP/ClearApp, nessun provisioning
o overwrite PSK, nessuna scrittura persistente, preservazione Windows/factory
state. Nessuna di queste affermazioni terze parti promuove un fatto del target
locale.

## Architettura

```text
Windows Biometric Framework
        |
EngineAdapter.dll / AlgoChicago.dll
        |
gfusb.dll (UMDF NativeUSB, A0/B0, TLS)
        |
Goodix MCU: APP ST411/12509 + resident code non disponibile
```

Il target dichiara `GF_ST411SEC_APP_12509`. L'APP mappata disponibile inizia a
`0x0802c000`; il codice resident necessario per interpretare A2 e `0x70` è sotto
questo indirizzo.

### Architettura software e licensing boundary post-D276/01

```text
GPL userspace core di ricerca / oracle comportamentale
  transport + protocol + TLS + FDT + capture + image
      |
      | solo fatti/spec neutra + test black-box; nessun link/copia/traduzione
      v
LGPL native FpImageDevice driver (production topology)
  GoodixDeviceContext per open epoch
    ├── unico claim/owner USB e unico bulk-IN reader
    ├── unico router A0/B0
    ├── GoodixSecureSession A8→E4→pre-D1→D1→TLS→STOP, senza D4
    ├── GoodixTlsServer OpenSSL TLS 1.2 PSK Memory-BIO + ScopedSecret one-handoff
    ├── GoodixFpiUsbBackend async; one-IN/one-OUT, completion generation-captured
    ├── B0 egress fixed64 zero-tail + pacing 10 ms generation-owned
    ├── unico lifecycle Goodix/FDT
    └── adapter FpImage 80x64 già LGPL
```

L'architettura post-D247 è stata adottata precisamente per consentire il riuso diretto, l'adattamento e l'integrazione nel core/ e nei tools/ GPL del codice Rockytkg compatibile GPL, preservandone licenza, attribuzione e provenienza. Analogamente, codice Rockytkg specificamente disponibile sotto licenza LGPL compatibile può essere valutato per libfprint-driver/.

Il licensing boundary non vieta quindi il riuso di Rockytkg: impedisce soltanto che espressione GPL-only venga trasferita dal dominio GPL al driver upstream-facing LGPL. Tale passaggio è possibile solo in presenza di dual licensing o di una licenza alternativa compatibile concessa da tutti i titolari pertinenti; in assenza, l'implementazione LGPL deve essere indipendente e basata su specifiche, fatti di protocollo, test ed evidenza, non sull'espressione GPL-only.

D276/01 seleziona per production la topologia nativa C/LGPL in-process. Un
helper GPL out-of-process resta tecnicamente possibile come harness di ricerca,
ma non come device glue: IPC, propagazione cancel, crash/restart e packaging
dividerebbero il lifecycle fra due owner e renderebbero possibile un reopen
implicito. Python embedded è escluso per GIL, teardown, failure containment,
packaging e confine GPL/LGPL. La scelta ha confidenza `HIGH` e non dipende da
orientation, polarity, ppmm o qualità biometrica.

Il `GoodixDeviceContext` production vive da `img_open` a `img_close` e usa il
`GUsbDevice` fornito da `fpi_device_get_usb_device()`: possiede il claim
dell'interfaccia, ma non crea un secondo handle USB. Solo il router può
sottomettere un bulk-IN fisico; ACK, eventi/NAV A0 e B0 TLS/immagine sono
demultiplexati dopo lo stesso parser. Waiter e code logiche non leggono mai
l'endpoint e il TLS consuma/produce soltanto byte B0 consegnati dal router.
Tutte le notifiche `fpi_image_device_*` avvengono nel GLib main context
proprietario mediante transfer asincroni `FpiUsbTransfer`, senza reader thread
bloccante.

#### Mapping production Goodix ↔ FpImageDevice 1.94.5

| Evento | API libfprint verificata | Regola di ownership/teardown |
| --- | --- | --- |
| open | `img_open` → `fpi_image_device_open_complete()` | crea il contesto e reclama l'interfaccia; il context possiede TLS/secret, con un handoff per sessione TLS, ma la policy di lifetime cross-activation resta irrisolta; failure pulisce senza retry |
| activate | `activate` → `fpi_image_device_activate_complete()` | da contesto pulito crea generation e `GCancellable` locali e completa success solo dopo arm valido; da `POISONED` fallisce prima di generation/backend/submit |
| framework pronto | `change_state(AWAIT_FINGER_ON)` | gatea soltanto il re-arm `0x32`, insieme a `GOODIX_RELEASE_TAIL_COMPLETE` e down-table fresca same-cycle; nessun contatore stage driver |
| IRQ finger-down `0x0002` | `fpi_image_device_report_finger_status(dev, TRUE)` | l'API pubblica `PRESENT` e porta il framework in `CAPTURE`; callback stale non produce comandi |
| B0 immagine | helper LGPL → `fpi_image_device_image_captured()` | consegna una `FpImage(80,64)`, flags zero e ppmm semanticamente ignoto; parse/CRC/shape failure è terminale |
| IRQ finger-up `0x0200` e release tail | down-table → `0x20`/ACK → B0 discard → `0x50`/ACK → NAV → `GOODIX_RELEASE_TAIL_COMPLETE` → `fpi_image_device_report_finger_status(dev, FALSE)` | il B0 post-up non è mai consegnato via `fpi_image_device_image_captured()`; `0x20`/B0/`0x50` non sono gated da `AWAIT_FINGER_ON`; finger-off è notificato solo a tail completo, salvo cancellation già intervenuta |
| deactivate/cancel | `deactivate` → completion phase-correct | cancella/draina solo I/O host e invalida generation; nessun cancel device-side provato. Se non quiescente: sessione `POISONED/QUIESCENCE_UNKNOWN`, nessun resume/recovery/retry/TLS restart/reopen automatico |
| errore sessione | `fpi_image_device_session_error()` | marca l'open epoch `POISONED`, cleanup exactly-once; una nuova activation non maschera l'errore |
| close | `img_close` → `fpi_image_device_close_complete()` | fence, drain, chiusura TLS, zeroizzazione secret, release claim; nessun recovery A2/`0x70` |

`FpImageDevice` e `GoodixLifecycle` sono le sole due state machine legittime e
non duplicate: la prima possiede azione, stato dito, estrazione, matching e
aggregazione enrollment; la seconda possiede soltanto sequenza wire e
freschezza FDT. L'ordine target-proven del rilascio è:

```text
finger image -> 0x34/ACK -> IRQ0200 -> derive/validate down table
-> 0x20/exact ACK -> consume/discard post-up B0
-> 0x50/exact ACK -> consume NAV -> GOODIX_RELEASE_TAIL_COMPLETE
-> report_finger_status(FALSE)
```

Il gate `AWAIT_FINGER_ON + GOODIX_RELEASE_TAIL_COMPLETE + fresh same-cycle
down-table` autorizza esclusivamente il successivo `0x32`. Impedisce capture
anticipata durante l'estrazione SIGFM e perdita di un IRQ2 quando il framework
non è pronto, senza trattenere il release tail corrente dietro lo stato
`AWAIT_FINGER_ON`.

La cancellazione libfprint dell'azione porta al `deactivate`; un cancellable
USB activation-local, distinto dal cancellable dell'azione, è usato dai
transfer. `deactivate` chiude prima il terminal fence e richiede la cancellazione
host, ma i token IN/OUT restano pending finché i rispettivi callback asincroni
non rientrano. Durante questo intervallo il backend è fenced ma non drained:
nessun submit o delivery è ammesso, una nuova generation fallisce chiusa e la
deactivation non completa. Il callback matching, incluso
`G_IO_ERROR_CANCELLED`, rilascia esattamente il proprio token senza consegnare
byte; il callback finale notifica il drain una sola volta e solo allora il
context può completare la deactivation. Un callback stale non può rilasciare il
token della generation corrente. `HOST_ASYNC_IO_DRAIN=PROVEN_HOST_ONLY`; il
risultato prova lifetime e drain host, non la quiescenza del protocollo
device-side. Non esiste un comando cancel device-side provato e non
ne è ammesso uno non compreso. Se il lifecycle non è quiescente, la sessione di
protocollo diventa `POISONED/QUIESCENCE_UNKNOWN`: nessun resume mascherato nella
stessa sessione, recovery, reset, retry, TLS restart o reopen automatico.
D278/05 rende questo poison concretamente sticky per il restante open epoch:
una nuova `activate()` fallisce prima di creare una generation o raggiungere il
backend, e solo `img_close` distrugge il contesto. La
quiescenza production dopo cancel arbitrario resta `UNRESOLVED` (`DEVICE_PROTOCOL_QUIESCENCE=UNRESOLVED`) e un normale
lifecycle framework futuro richiede una policy esplicita. Timeout, TLS,
frame/ACK/CRC o lifecycle inattesi sono fail-closed e non invocano
`fpi_image_device_retry_scan()`.

D278/04 precisa il limite di questa garanzia: il fencing copre
`OLD_CALLBACK_FROM_GENERATION_N`, perché quel callback non può consumare il
token N+1. Non copre la diversa classe
`NEW_CALLBACK_GENERATION_N_PLUS_1_RECEIVING_OLD_DEVICE_CAUSAL_DATA`: se un
transfer nuovo ricevesse byte prodotti prima della propria generation, i
check host vedrebbero correttamente N+1. Né la generation né il frame A0/B0
contengono provenance cross-open/process. `goodix_usb_router_begin_generation`
svuota il solo buffer di riassemblaggio userspace; non asserisce la coda
endpoint o lo stato del protocollo device. Questo boundary è provato
staticamente e la seconda single-shot D278/03 ne ha osservato il fenomeno sul
target APP12509 — nuova sessione in fase A8, primo IN `A0/E4/body41` — senza
però provare che quei byte fossero causalmente la typed response E4 della run
precedente.

La cancellazione prima di `activate_complete(NULL)` termina invece la fase con
`fpi_image_device_activate_complete(..., G_IO_ERROR_CANCELLED)`: in quel punto
la base non ha ancora marcato il device attivo e `deactivate_complete()` non è
valido. Lo stesso principio phase-specific vale per open. Inoltre
`report_finger_status(FALSE)` può provocare sincronicamente `change_state` o
`deactivate`: nel non-enroll la deactivation è immediata; nell'enroll il nuovo
`AWAIT_FINGER_ON` compare solo dopo finger-off e minutiae completion, in
qualunque ordine. Il release tail deve quindi essere completo prima della
callback e nessun comando Goodix può essere inviato dopo di essa nella stessa
stack frame. Il solo `0x32` è una continuazione separata che ricontrolla i tre
gate, generation e terminal fence. Se cancellation è già intervenuta, prevale
il fence e il tail non viene proseguito.

La provenance-controlled independent reimplementation richiede: specifica neutra derivata da evidenza
canonica; SPDX/autore/fonti per ogni file; implementazione indipendente contro
API libfprint e primitive GLib/TLS; confronto black-box di transcript sintetici
con il runtime Python; nessuna consultazione/copia/traduzione del core GPL
durante il slice LGPL; golden vector senza secret/biometrica; review provenance
per slice. Un eventuale riuso di `Rockytkg/src/goodixgf.c`, LGPL, richiede audit
e ledger per-file; D276 non importa codice. Il suo `500 DPI`, flag inverted,
policy dinamica `3..8`, worker blocking e dipendenze dal core Rocky GPL non
sono adottati. `GPL_TO_LGPL_CODE_COPY_ALLOWED=false` e
`MECHANICAL_TRANSLATION_ALLOWED=false`; questa etichetta è controllo
ingegneristico di provenance, non conclusione o garanzia legale
(`CLEANROOM_LABEL=PROJECT_ENGINEERING_PROVENANCE_CONTROL_NOT_LEGAL_CONCLUSION`).

Roadmap corrente:

```text
D276/01 -> architettura production e ownership CLOSED_OFFLINE
D276/02 -> shell FpImageDevice + backend in-memory + test seams CLOSED_HOST_ONLY
         -> executable validation GitHub Actions PASS_CLEAN_TREE
D276/03 -> router A0/B0 clean-room con una sola receive + transcript sintetici CLOSED_PASS_HOST_ONLY
D276/04 -> B0→TLS + TLS OUT + FpiUsbTransfer; generation authority context-only e callback drain CLOSED / PASS_HOST_ONLY, AI-PM+CI PASS
D277/01 -> harness nativo A8 PASS_HOST_ONLY; singola run BLOCKED a USB open prima di claim/submit; storico preservato
D277/02 -> prova nativa A8/A0 su target reale PASS; exact A8 → ACK → risposta tipata APP12509; autorizzazione consumata
D278/01 -> secure-session A8→E4→pre-D1→D1→TLS→STOP PASS_HOST_ONLY; target proof resta falsa oltre A8/A0
D278/02 -> binder D190 + PE + protected-material loader + harness/watchdog live-capable PASS_HOST_ONLY; authentic protected-material preflight PASS (E4 binding MATCH, zero USB); live non eseguita
review   -> AI-PM valuta review set e baseline SHA; ogni nuova run richiede approvazione/autorizzazione esplicite
```

Stato rescue D276/02 (28 agosto 2026): il WIP è classificato **B**. La shell è
salvabile e continua a usare il vero `FpImageDevice` 1.94.5. Il rescue ha
corretto fake/test e semantiche asincrone (cancellazione `ACTIVATING` collegata al
cancellable libfprint, ownership `GError` trasferita ai confini, deactivation
fake trattenibile, generation token per callback, re-arm exactly-once per
generation, avvelenamento `POISONED` per cancel non-quiescente, launcher con
propagazione failure). La successiva validazione GitHub Actions sul clean
checked-in tree (commit `87d4aacec23b5415cca5de73e0dfeb83ffe65bab`, run 33165906857)
ha ora chiuso la executable closure host-only.

```text
OUTCOME=READY
ADVANCEMENT=HOST_ONLY_EXECUTABLE_VALIDATION_PASS_CLEAN_TREE
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
RESIDUAL_BLOCKER_OR_RISK=PRODUCTION_DEVICE_QUIESCENCE_AFTER_ARBITRARY_CANCEL_UNRESOLVED;TLS_SESSION_LIFETIME_ACROSS_LIBFPRINT_ACTIVATIONS_UNRESOLVED;ENROLLMENT_STAGE_POLICY_NOT_SELECTED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_MAIN_54fa55835ec5192aa794c1302d2e4a7e2fab0fcf_PLUS_VALIDATED_CHECKED_IN_TREE_87d4aacec23b5415cca5de73e0dfeb83ffe65bab_PLUS_BRANCH_d276-02-github-actions-validation_DOCUMENTATION_CLOSURE

WIP_CLASSIFICATION=B
LOCAL_LIBFPRINT_DEVICE_GLUE_SLICE_1=IMPLEMENTED_CORRECTIVE_EXECUTABLY_CLOSED_HOST_ONLY
FPIMAGE_DEVICE_REAL_FRAMEWORK_USED=true
IN_MEMORY_BACKEND_ONLY=true
GERROR_OWNERSHIP_AUDIT=CORRECTED_AND_HOST_ONLY_VALIDATED
ACTIVATING_CANCEL_PHASE_CORRECT=HOST_ONLY_VALIDATED
DEACTIVATING_TEST_OBSERVABLE_AND_BOUNDED=true
NONQUIESCENT_CANCEL_POISON_POLICY=IMPLEMENTED_HOST_ONLY_VALIDATED
OLD_GENERATION_CALLBACK_TEST=REAL_N_MINUS_1_TOKEN
REARM_EXACTLY_ONCE=IMPLEMENTED_PER_GENERATION
ENROLLMENT_STAGE_POLICY=NOT_SELECTED
NORMAL_TEST_RUN=PASS
SANITIZER_TEST_RUN=PASS
DETERMINISM_RUNS=2
D276_02_HOST_ONLY_EXECUTABLE_VALIDATION=PASS_CLEAN_TREE
LIVE_AUTHORIZED=false
NEXT_PRIMARY_BOUNDARY=D276_03_A0_B0_CLEANROOM_SINGLE_RECEIVE_SYNTHETIC_TRANSCRIPTS
```

La executable closure host-only è stata validata su clean checked-in tree al
commit `87d4aacec23b5415cca5de73e0dfeb83ffe65bab` tramite la run GitHub Actions
33165906857. Il workflow ha eseguito due volte il launcher checked-in: in entrambe
le iterazioni, 14/14 test normal e 14/14 test ASAN/UBSAN sono risultati PASS
senza diagnostic patch (`CI_DIAGNOSTIC_PATCH=NONE`). La precedente mancanza di
Flatpak/GLib-dev nell'ambiente di rescue è una condizione storica superata.
Un'eventuale conferma Fedora futura è `OPTIONAL_NON_GATING` e non costituisce un
gate retroattivo. Nessun sensore Goodix reale, USB, TLS reale, PSK, fprintd,
registrazione VID production o mutazione persistente è stato usato.

Il corrective post-merge D276/04 stabilisce inoltre
`GENERATION_AUTHORITY=GOODIX_DEVICE_CONTEXT_SINGLE_SOURCE`: a ogni activation il
context crea un token non-zero e lo fornisce esplicitamente a router e backend.
Il router non mantiene un contatore concorrente; `cancel()` chiude fence,
receive e parser pending senza mutare il token. Il terminal fence del context
cancella TLS e backend, e soltanto il backend cancella il router, eliminando il
doppio cancel. Una regressione integrata host-only attraversa activation N,
teardown, activation N+1, callback tardiva N e callback valida N+1: la stale è
ignorata senza consumare la receive corrente e N+1 viene consegnata, con massimo
una receive logica outstanding. Il test router copre anche due cancel
consecutivi senza mutazione generation. I workflow corretti aggiungono
`ca-certificates` pre-checkout a D276/04 e `libssl-dev`/`libgusb-dev` alla
regressione D276/03. Le Actions push e PR del corrective sul commit CI-validato
`d10155076b7f46e7897c9df65a910a125b4575b4` sono tutte `PASS`; la review AI-PM
è `PASS` e la closure eseguibile finale è `PASS_HOST_ONLY`. Restano
irrisolte la quiescenza reale dopo cancel arbitrario e la lifetime TLS tra
activation; il test non prova equivalenza hardware.

D276/04 ha chiuso la subdecisione provider su **OpenSSL 3**: il supporto server
TLS 1.2 pure-PSK, BIO di memoria, callback PSK e cleanup esplicito soddisfa il
contratto senza helper, socket, thread, processo, `dlopen` o fallback. La
dipendenza `libssl-dev` è esplicita nel workflow. La scelta non risolve né
modifica lifetime TLS cross-activation o quiescenza dopo cancel arbitrario.


## Trasporto USB

L'interfaccia usa bulk OUT `0x01` e bulk IN `0x81`, max packet 64. Interrupt IN
`0x82` è presente ma non è una superficie host→device del protocollo ricostruito.
EP0 è usato per enumerazione/configurazione USB standard.

Il frame A0 ha magic `0xa0`, lunghezza LE16 e tag esterno additivo. Il payload
interno contiene control, lunghezza e checksum. Alcuni builder 5125 calcolano il
checksum in coordinate pre-OR: il control logico e quello wire vanno conservati
separatamente. Non è corretto dedurre sempre il logico con `wire & 0xfe`.

B0 avvolge direttamente un record TLS completo con header Goodix di quattro
byte; non aggiunge cifratura o compressione.

Le lunghezze dichiarate A0/B0 descrivono soltanto il frame logico. Nella capture
D175 tutte le 56 submission bulk OUT A0/B0 osservate sono staging buffer host
da 64 byte; la tail dell'ultimo blocco è fuori dalla lunghezza dichiarata e,
nei B0 del server flight esaminati, è nonzero. I byte del frame costruito, i
byte USB richiesti e quelli completati sono quindi misure distinte. Questa
osservazione host-side **non** prova che una tail A0 artificialmente zero-filled
sia device-side equivalente: il contenuto semanticamente rilevante della tail
Windows resta non noto. La run D242 ha mostrato che il padding zero generico
coincide temporalmente con la perdita di responsività E4 già superata live in
D239/D241; la run D243 ha poi mostrato che rimuoverlo non è sufficiente a
recuperare quel path.

Lo stato canonico è perciò:

```text
D243_A0_FIXED64_CAUSAL_STATUS=FALSIFIED_AS_SUFFICIENT_EXPLANATION_BY_D243_LIVE
D244_A0_FIXED64_DEVICE_EQUIVALENCE_STATUS=UNRESOLVED
D244_B0_FIXED64_DEVICE_EQUIVALENCE_STATUS=NOT_YET_LIVE_REACHED
```

La claim `OEM_COMMON_A0_B0_TRANSPORT_CONTRACT_VERIFIED` resta ritirata come
claim device-side. D243/D244 invia gli A0 in chunk logici `<=64`, con ultimo OUT
corto e completion richiesta pari alla lunghezza del chunk. Solo B0/TLS usa
staging fisico da 64 byte, tail zero-initialized e completion esattamente 64.
La sola eccezione D246 è il frame D4 byte-exact
`a00600a6d403000000d3`: la capture primaria mostra una submission fisica da 64
byte con tail interamente zero. Questa evidenza non generalizza il fixed-64 ad
altri A0.
Un flag
`server_hello_sent` prova al massimo emissione e wrapping; la trasmissione
completa richiede completion USB full-length per ogni blocco richiesto.

## Sicurezza e TLS

Il profilo noto è TLS 1.2 pure PSK, suite `0x00a8`, identity
`Client_identity`, dispositivo client e host server. Il materiale autentico del
laptop originale ha prodotto una singola E4 read-only `MATCH`, ma questo non
costituisce una procedura generale di provisioning.

D241 ha inoltre verificato il binding di ownership: il medesimo oggetto
`SecretBuffer` validato da E4 è stato consegnato al server TLS, senza copia o
sostituzione intermedia. Questo prova l'identità dell'oggetto e il percorso
runtime, non prova da solo che il dispositivo abbia completato la derivazione
crittografica o accettato il server flight.

D231 conferma nella DLL che il plaintext DPAPI viene copiato nell'area PSK
runtime e passato direttamente al setup TLS senza un secondo KDF OEM. Il
materiale è portabile solo perché recuperato legittimamente dalla macchina
originale; questa conclusione non autorizza PSK zero, sostitutive o cross-device.

`PSK_PORTABILITY_STATUS=PSK_PORTABILITY_PROVEN` con
`PORTABILITY_SCOPE=ORIGINAL_DEVICE_AND_LEGITIMATELY_EXPORTED_MACHINE_BOUND_MATERIAL_ONLY`.
Non è richiesto un challenge Windows-only dopo il recupero legittimo e lo
stesso materiale può essere riusato su Linux senza riprovisionare il sensore.

Nessun secret deve essere stampato, copiato o incluso negli artefatti. Un futuro
test hardware richiede autorizzazione separata, fail-closed e con ripristino del
servizio Windows/Linux previsto.

## Lifecycle osservato

La capture recuperata contiene il cold-start:

```text
E4 → A2 → 82 → A6 → A2 → 70 → 80×4 → 90 → D1 → B0
```

L'ordine è osservato, non dimostrato come insieme causale minimo. D231 chiude la
semantica host-side di A2 e `0x70` per il replay OEM esatto; non trasforma la
sequenza in una ricetta generale né dimostra i body resident istruzione per
istruzione.

### Lifecycle ACK/risposta consolidato in D238

La capture primaria locale `rilevamento.pcapng` (SHA-256
`50071c0f...19c184b`, già classificata storicamente nel filone D175) mostra
status ACK `0x01` in tutte le undici fasi pre-D1 che producono ACK. E4, A2,
`0x82`, A6 e `0x90` hanno poi una risposta A0 distinta con lo stesso control;
`0x70` e le quattro `0x80` sono ACK-only. D1 non ha ACK A0: la risposta attesa è
direttamente B0 con ClientHello TLS.

| Fase | Control | ACK ammessi D238 | Risposta dopo ACK | Evidenza locale primaria |
| --- | --- | --- | --- | --- |
| E4 | `e4` | `01`, `07` | A0/E4 validator tipizzato | capture `01`; live D236 `07` + binding `match` |
| A2 #1 | `a2` | `01`, `07` | A0/A2 IRQ tipizzato | capture `01`; live D236 `07` |
| `0x82` | `82` | `01`, `07` | A0/82, body hash-pinned | capture `01`; `07` ereditato dalla semantica ACK di sessione |
| A6 | `a6` | `01`, `07` | A0/A6, body hash-pinned | capture `01`; `07` ereditato dalla semantica ACK di sessione |
| A2 #2 | `a2` | `01`, `07` | A0/A2 IRQ tipizzato | capture `01`; stesso control del live `07` |
| `0x70` | `70` | `01`, `07` | nessuna | capture `01`; `07` ereditato dalla semantica ACK di sessione |
| `0x80` ×4 | `80` | `01`, `07` | nessuna | capture `01`; `07` ereditato dalla semantica ACK di sessione |
| `0x90` | `90` | `01`, `07` | A0/90 body esatto `0100` | capture `01`; `07` ereditato dalla semantica ACK di sessione |
| D1 | `d1` | nessuno | B0/TLS diretto | capture primaria D175 e live D241: ClientHello TLS 1.2 verificato; D241 ownership exactly-once |

`0x07` non è stato promosso come risposta applicativa specifica di E4 o A2. La
capture mostra `0x01` invariato attraverso control diversi; i run reali D236
mostrano `0x07` invariato attraverso E4 e A2 nello stesso path e nello stesso
firmware. D238 lo modella quindi come secondo valore di successo ACK di
trasporto/sessione, con allowlist esplicita per ogni fase. Ogni altro status,
echo, lunghezza, control, ordine o body resta terminale e fail-closed. Questa è
un'inferenza cross-control corroborata, non una definizione nominale dei bit:
il significato interno di `0x01`/`0x07` resta ignoto.

Nella capture locale ACK e risposta tipizzata sono frame distinti in completion
USB separate. Il trasporto D238 accetta anche due frame logici esatti nella
stessa completion, perché il boundary USB non cambia il framing A0; non accetta
una forma combinata o payload più permissivi. Il report distingue completion
separate, coalesciute e frame frammentati. Gli artefatti storici nominati D43,
D178 e D226 non sono presenti nell'albero D238 corrente e non vengono simulati
o citati come fonti primarie; la prima capture resta definitivamente perduta.

## Configurazione prima di TLS

Le quattro scritture `0x80` e il download `0x90` studiati sono ricondotti a
registri/SRAM/configurazione volatile nell'APP disponibile. `0x90` è un path di
download/write e non deve essere descritto come read.

A2 subtype 2 dispatcha a `0x080272e1` (allineato `0x080272e0`). La DLL target
1.1.125.14 costruisce il body `{01,14}` da
`ResetMCUAndFingerprint(false,true)`: bit 0 reset sensore, bit 1 reset MCU. I
due frame recuperati sono quindi reset del solo sensore.

La famiglia `0x70` usa la tabella callback SRAM con target `0x0802b8f5`
(allineato `0x0802b8f4`). La DLL costruisce `{14,00}` dal ramo
`ChicagoHUSetMode(7,0,0)`, log `setmode: idle`, e lo invoca all'inizio di
`ChicagoHUsetDac`, prima delle write `0220/0236/0238/023a`. Questi risultati
convergono con la ricostruzione riferita per la DLL 1.1.125.13 e con il wire.

I corpi target-specific restano assenti. La lifetime è classificata
operativamente volatile e senza evidenza di mutazione persistente per l'exact
OEM replay; non è una prova assoluta device-side di non-mutazione NVM.

## Convergenza e gate D231

`D231_DECISION=D231_PRE_D1_CLEARED_FOR_EXACT_OEM_REPLAY`

`PRE_D1_PATH_CLEARED_FOR_EXACT_OEM_REPLAY=true` vale esclusivamente per la
sequenza byte-identica, i DAC/config del dispositivo originale e il materiale
PSK autentico già validato. Non è un gate universale e non autorizza hardware.

La roadmap storica da D231, preservata per provenance, è:

```text
D231 -> decisione statica chiusa
D232 -> implementazione/review OFFLINE chiusa dell'exact OEM replay
     -> live hard-disabled, allowlist byte-pinned, test sintetici pass
D233 -> backend USB/TLS reale + review soltanto OFFLINE, hard-disabled
D233 closure -> reference D190 + binding runtime + orchestratore candidate offline
D234 -> accettazione rischio concessa, ma nessun live: blocker entrypoint
D235 -> entrypoint production-candidate composto e testato soltanto OFFLINE
     -> doppio source seal D235/D233, nessun runtime enablement
D236 -> autorizzato, unseal revisionato, ma bloccato prima del preflight root
     -> zero enumerazione/open/comandi; source resealed
D237 -> evidenza D236 normalizzata e boundary di sicurezza riconfermato
D238 -> policy pre-D1 consolidata e kit operatore source-sealed
     -> tentativo operatore fallito sull'import Python, prima di unseal/USB
D239 -> launcher corretto + dry-run operatore production-shaped fino al pre-USB
     -> gate offline PASS; successiva run autorizzata: pre-D1 completo e B0/TLS
D240 -> SUPERSEDED / DO_NOT_EXECUTE / NOT_EXECUTED
D241 -> run live single-shot consumata: ClientHello verificato e server flight
     -> trasmesso, poi timeout senza ClientKeyExchange; zero retry/D4/app-data
D242 -> run live single-shot: timeout al primo E4 dopo generic fixed-64 A0
     -> binding/TLS/pacing non raggiunti; cleanup/restore/reseal riusciti
D243 -> split A0/B0 chiuso offline, poi run live single-shot consumata
     -> A0 corto D241 ma stesso timeout E4; binding/TLS non raggiunti; zero retry/D4
D244 -> evidenze D242/D243 verificate, timeout localizzato su bulk IN dopo OUT
     -> successiva run fresh-host valida: E4 OUT completato, bulk IN timeout
     -> fresh host boot falsificato come condizione sufficiente; power loss sensore non provata
D245 -> record storico canonico D179 A8→E4 + corroborazione locale D230
     -> D43 ACK01 e D175 ACK07 seguiti dalla stessa response 12509: vecchia policy ACK07 terminale falsificata
     -> A8 read-only una volta; ACK01/07 autorizzano una response bounded; poi E4 solo su FW12509 esatto
     -> closure offline PASS, poi live PASS: ACK07, FW12509, E4 match e TLS completo; stop prima di D4
     -> bundle 9813878a...569f precedente alla correzione ACK07 SUPERSEDED / DO_NOT_USE_FOR_LIVE_AUTHORIZATION
D246 -> evidenza D245 validata; audit primario TLS Finished→D4→ACK→AF
     -> D4 classificato volatile sul receiver APP12509 esatto; host e device persistence escluse per quel path
     -> patch offline D4 exactly-once, ACK d4/01 only, STOP_AFTER_D4; closure PASS
     -> launcher live-capable hard-gated e testato offline; successiva run live single-shot PASS
     -> TLS completo, D4 attempt/send 1/1, ACK d4/01, STOP_AFTER_D4; zero retry/app-data/persistent-write
     -> cleanup/restore/reseal riusciti; AF diventa il prossimo confine non valutato
D250 -> candidate AF exactly-once chiuso offline, poi run live singola consumata
     -> TLS e D4 riusciti; AF zero-tail attempt/send 1/1; A0/AE strutturalmente valida body 16
     -> abort fail-closed sul gate byte0==1; response_count incrementato troppo tardi; byte0 perso
     -> cleanup/restore/reseal riusciti; zero retry/app-data/persistent-write
D251 -> audit byte0: gfusb usa byte1 bit0/1/3 e non confronta byte0; Rocky corrobora
     -> byte0 riclassificato opaco; validator/telemetria corretti, wire D250 invariato
     -> closure offline PASS; successiva run live single-shot PASS e marker consumato
     -> AE unica valida: byte0=0 opaco, flags=0x02, POV false/TLS true/locked false; STOP_AFTER_AF
D252 -> audit offline fresh-FDT: tabella appresa da 0x36/IRQ0100, ma seed/freschezza current-path aperti
     -> target IRQ2 seguito da wire 0x22, non 0x20; nessun cancel/restore post-FDT provato
     -> D252_LIVE_BOUNDARY=BLOCKED; nessun kit live e zero hardware
D253 -> dataflow seed delimitato; core corretto a IRQ2->0x22; restore ancora ignoto
D254 -> audit pubblico hash-gated: WBDI=5110/12117, Issue63=5125/FW ignoto
     -> Issue63 corrobora 21/21 IRQ2->0x22 e residuo tail 0x36 agli stessi offset
     -> bootstrap ridotto ma non chiuso; restore non ridotto; nessun live
D255 -> kit offline per una sola capture Windows APP12509 correlata
     -> USBPcap attivo prima del cold attach VM; wire+WBDI+cache+marker UTC
     -> sanitizer hash-gated, redazione OTP/PSK/biometria; zero hardware in D255
     -> prima review FAIL: API PowerShell 5.1 e timestamp WBDI MMDD non chiusi
     -> corrective: helper PS5.1, self-test, clock start/end, log delta/rotation
     -> seconda review FAIL: recognition non provata e enrollment VM non completato
     -> corrective VM: capture-before-attach, singolo attach GUI, PnP+descriptor+A8
     -> setup/add-fingerprint zero-finger; IRQ2/0x22/image invalidano la run
     -> preflight reale PASS; i failure locali pre-attach sono stati corretti nello stesso step
     -> run finale acquisita: 27.684 byte/218 frame; cold attach, zero finger, cancel e re-entry
     -> recovery/postprocess offline PASS; seed/cache match; nessuna nuova capture richiesta
D256 -> timeline completa dei 206 packet target nel raw D255 hash-gated
     -> cancel interval senza traffico target; una completion bulk-IN cancellata dopo re-entry begin
     -> stesso bus/device ed endpoint; nessun abort/reset/descriptor replay/re-enumeration
     -> nuovo 0x32 accettato senza restore USB esplicito osservato
     -> secondo cancel: pending IN cancellato al frame finale; zero packet residui
     -> terminal-stop host/bus chiuso come quiescenza; stato interno/lifetime non osservati
D257 -> lifecycle FDT e provider seed esplicito implementati offline, senza backend USB
     -> corrective raw D255: bootstrap esatto 36,50,36,82,20,36,32
     -> replay precedente riclassificato sottosequenza proiettata PASS_HISTORICAL
     -> gate host dinamici NAV/delta/baseline non derivabili; candidate esatto BLOCKED
     -> first 0x36 exactly-once, ACK/IRQ/validator obbligatori, zero retry e cleanup fail-closed
     -> IRQ2->0x22 exactly-once e primo record immagine chiusi su fixture sintetica
     -> cache riusata con successo oltre 27 minuti dopo mtime; TTL generale ignota ma non safety blocker
D258 -> orchestratore target gf_update_all_base recuperato nel gfusb.dll hash-gated
     -> 0x50 NAV e 0x20 baseline acquisiti prima di stage2, classificati soltanto dopo stage2
     -> 0x82 chiuso: byte1 unsigned, abs-delta sui word FDT grezzi; predicate implementata
     -> timeout per comando 36/50/82=500, 20=2000, 32=100 ms; zero retry
     -> replay esatto avanza wire-exact fino al terzo 0x36, poi fail-closed sui classificatori NAV/image
     -> B0 D255 non decifrato: input PSK non disponibile nel confine user-readable; nessun privilegio richiesto
D259 -> branch audit dei return NAV/image 0,1,2,3 e altri/negativi sul gfusb.dll hash-gated
     -> return 1 conserva la base; ogni altro return copia la base acquisita e marca cache host dirty
     -> nessun effetto su tabella/payload/reachability 0x32, comandi USB, retry o recovery A2/0x70
     -> B0 resta obbligatoriamente consumato/autenticato/decrittato dalla sessione TLS attiva
     -> replay minimo completo PASS: due delta, zero classifier/raster/cache/retry/persistenza, final 0x32 una volta
      -> Classe A: minimal contract chiuso offline e pronto per review live separata; READY_FOR_FDT_LIVE=false
D268 -> run live one-shot eseguita una sola volta sulla baseline `c03d32e...` tramite Kit Operatore D268
      -> PASS_STOP_AFTER_FIRST_IMAGE; primo B0, trailer 0x88 no-check, CRC record valido, raster 80x64 decodificato
      -> boundary first-image CHIUSO LIVE; D267/01 riclassificato STRONG_CAUSAL_INFERENCE (trailer ignoto)
      -> closure D218-D220 preservata: Windows consuma u16 direttamente, nessun adapter u8, orientation UNRESOLVED
      -> prossimo boundary: LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT
```

L'accettazione D234 è stata consumata dal suo esito terminale senza alcun live
run. D236 ha ricevuto una nuova accettazione, ma si è chiuso al gate root prima
dell'inizio del live; per qualunque step successivo l'accettazione è nuovamente
`not_granted`,
`D233_AUTOMATIC_RESET_ON_FAILURE=forbidden` e il live resta `NOT_AUTHORIZED`.
E0/A4/F0/F4, erase, IAP, ClearApp, boot change, provisioning e varianti
cross-device restano vietati. Nel caso peggiore credibile il sensore può restare
in stato protocollo ignoto o non enumerato e richiedere recovery manuale.

La prima capture è definitivamente perduta; D231 confronta a livello packet la
sola capture recuperata. I claim 1.1.125.13 sono corroborazione indipendente
fornita, ma il relativo binario non appartiene al corpus locale.

## Implementazione e safety wall D232

`D232_DECISION=D232_READY_FOR_D233_RISK_ACCEPTANCE_REVIEW` significa soltanto
che il contratto/state model sintetico è pin-nato e testato offline.
Il modulo clean-room `src/goodix5125_d232_offline.py` è l'unico seam D232:
contiene codec A0/B0, gate del materiale locale, boundary PSK, preflight come
validazione di dati forniti, state machine e report. Non contiene backend USB,
enumerazione, driver detach, chiamate libusb o entrypoint live.

La macchina autorizza una sola transizione alla volta:

```text
START -> IDENTITY_REVALIDATED -> E4_MATCH -> A2_1_OK -> CHIPID_OK
-> OTP_OK -> A2_2_OK -> MODE_IDLE_OK -> DAC_1_OK -> DAC_2_OK
-> DAC_3_OK -> DAC_4_OK -> CONFIG_OK -> D1_SENT_CLIENT_HELLO_OK
-> TLS_HANDSHAKE_OK -> CLOSE
```

Le richieste sono esattamente `E4/A2/82/A6/A2/70/80x4/90/D1`, poi TLS.
A2 `{01,14}`, `0x70` `{14,00}` e il frame D1
`a00600a6d103000000d7` hanno golden vector. D4, E0, A4, F0, F4, IAP,
ClearApp e provisioning sono irraggiungibili. Non esistono salti, retry o reset
automatici; timeout, completamento ambiguo, ACK/DATA/IRQ inattesi, ChipID o OTP
errati, mismatch E4/config, re-enumeration inattesa, alert TLS e Bad Record MAC
terminano in `STOP` senza autorizzare la fase successiva.

I quattro valori DAC e il payload `0x90` derivano esclusivamente dalla capture
target locale provenance-valid. Il manifest pubblicabile conserva ordine,
offset, lunghezze e SHA-256; il raw `0x90` resta escluso e in un futuro D234
dovrebbe essere installato come file locale regular, root-owned, mode `0600`,
non symlink, con lunghezza 224, hash, finalizer e correlazione DAC tutti validi.
La prima capture resta definitivamente perduta: la provenance è completa per il
replay osservato, ma la coverage packet-level rimane una sola capture.

La PSK non è nel source, fixture, report o bundle. Il boundary production
accetta soltanto il record canonico `G5125POC` da 88 byte, SHA-256
`eb47bbed40e079ca780cd9cd4b2324520a67584ad3d576674914152fd6080a75`,
regular, root-owned `0600` e non symlink. Il loader verifica magic/hash, estrae
i 32 byte di transport secret dall'offset canonico senza stamparli e azzera il
record temporaneo. La stessa istanza `SecretBuffer` validata contro E4 è quella
consegnata al TLS e viene azzerata in cleanup; non esiste fallback
zero/random/sostitutivo. I test offline usano esclusivamente secret sintetici e
non aprono lo store reale.

`D232_LIVE_CAPABILITY=0` è un vincolo source: nessun flag, ambiente o config può
abilitare il live, non esiste un backend/entrypoint hardware e un oggetto backend
diverso dall'oracle sintetico esatto viene respinto. Il backend aggiunto in D233
resta a sua volta sigillato a livello source.

Il report sintetico è JSON redatto, atomico, mode `0600` e pubblicato anche sui
failure; registra fase, abort class, command count, USB open count (sempre zero
in D232), handshake, cleanup e restore. Il cleanup è exactly-once e il secret è
azzerato. La recovery futura resta: R0 stop comandi; R1 preserva report; R2
release USB/ripristina ownership e fprintd; R3 nessun altro traffico nello stesso
run; R4 reboot/power-cycle soltanto dopo review umana; R5 verifica Windows; R6
stop live se enumera male o regredisce; R7 SWD/JTAG fuori dal workflow. D232 non
automatizza R4-R7.

## Backend reale offline e safety wall D233

D233 inserisce deliberatamente uno step tra il modello D232 e qualunque prova
hardware. `src/goodix5125_d233_backend.py` contiene un binding ABI minimo a
libusb-1.0, target esatto `27c6:5125`, interfaccia 0, bulk OUT `0x01`, bulk IN
`0x81`, frame da chunk massimi di 64 byte, revalidazione bus/address/port path,
claim/release/close exactly-once e nessun detach, clear-halt, reset o retry. Il
backend riusa serializer, allowlist, timeout, response validator e core
monotono D232: non esiste una seconda sequenza safety.

Il server TLS usa OpenSSL tramite `ssl.MemoryBIO`: TLS 1.2 soltanto,
`PSK-AES128-GCM-SHA256`/`0x00a8`, identity esatta `Client_identity`, niente
certificati, ticket, resumption, downgrade, seconda PSK o API application-data.
Il bridge accetta payload B0 frammentati, alimenta il BIO, separa più record in
uscita e li reincapsula singolarmente in B0. L'handshake è one-shot e il run si
ferma appena verificati versione e cipher; alert, timeout e Bad Record MAC sono
terminali.

Il boundary secret D232 viene riusato senza fallback. D233 aggiunge
`RuntimePskE4Binder`: deriva un expected validator dal buffer PSK effettivamente
caricato, confronta in constant time i 32 byte E4 e azzera il temporaneo; un
mismatch ferma dopo E4 e prima del primo A2. D189/D190 avevano già chiuso la
teoria, l'oracle OEM e la reference locale byte-exact; la sanitizzazione
successiva della repository pubblica aveva rimosso il source, non quella prova.
Il D233 originario non riuscì a recuperarlo e dichiarò correttamente il blocker.
La closure D233 ha poi recuperato source e KAT dal transcript locale D190,
reintegrato la reference minima e ripetuto i cinque vettori sul PE canonico con
zero mismatch. Non usa un MATCH storico come gate: ogni run deriva nuovamente il
validator dalla PSK caricata e dal PE hash-gated.

## Derivazione OEM e reference D190

La catena target è `secret[32] → producer key[32] → SP800-108 HMAC-SHA-256
out48 → envelope AES-256-GCM/HMAC[102] → SHA-256 → validator[32]`. Il FixedData
SP800-108 contiene le label canoniche e `BE32(384)`; `T1` e `T2` usano counter
BE32 1 e 2. D190 ha corretto due dettagli statici tramite le istruzioni OEM:
il buffer AES è azzerato a ogni iterazione e i quattro blocchi non sono
concatenati; `inner16` è il nonce GCM e la costante target è l'AAD.

La reference sotto `poc/goodix5125/tools/binding_reference/` non esegue la DLL.
Accetta soltanto SHA-256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`,
controlla PE, range e pattern univoco, legge i due seed strettamente necessari e
li azzera insieme ai material intermedi mutabili. Nel source e nei bundle non
sono presenti seed raw, producer key o out48. La policy resta
`LOCAL_VOLATILE_DERIVATION_HASH_ONLY`; il limite onesto è che Python non può
garantire la cancellazione di ogni copia immutabile interna alla libreria.

I validator attesi V0–V4 furono prodotti dall'oracle di istruzioni OEM sotto
QEMU prima di entrare nel self-test della reference. Nella closure sono input
storici indipendenti, non output rigenerati dalla funzione sotto test. Il PE
canonico locale riproduce tutti e cinque; hash errato, pattern ambiguo, KAT
alterato, PSK mutata o E4 errato falliscono chiusi. Ne seguono
`D190_REFERENCE_PROVENANCE_VALID=yes`, `D190_KAT_NONCIRCULAR=yes` e
`RUNTIME_PSK_E4_BINDING_PROVEN=yes`.

Il raw `0x90` non è copiato nel source o nel bundle. La capture locale
provenance-valid, SHA-256 `50071c0f...19c184b`, contiene a packet index 103
l'unico body di 224 byte con SHA-256 `e1988b11...d4d82`, finalizer `519a` e
tuple DAC coerenti. La procedura D234 documentata estrae da quella sola fonte,
verifica tutti i pin e materializza atomicamente un file root-owned `0600`,
regular e non symlink; D233 non legge lo store reale.

Il preflight production-shaped usa una facade iniettata: gate euid/SUDO_UID,
marker single-use atomico, processo/thread singolo, holder esterni, stato
fprintd, blocco segnali prima del trasporto, identità target e readiness del
report. Il restore riporta fprintd esattamente allo stato precedente e ripristina
la mask segnali. In D233 sono eseguite soltanto facade mock; nessun servizio o
sistema è mutato.

L'orchestratore candidate unisce preflight, loader protetti, verifica PE,
caricamento PSK, binder D190, backend USB/TLS e core OEM monotono attraverso sole
facade iniettate in D233. Il core D232 conserva lo schema sintetico, ma quel
report è catturato soltanto in memoria: il percorso candidate pubblica
`d233-production-candidate-run-report-v1`, con mode, seal, autorizzazione,
conteggi, restore, zeroizzazione, identità target e stato binding espliciti.
Non esiste alcun valore runtime che possa dichiarare `live_single_shot`.

L'ordine di recovery è causale e testato: stop del nuovo traffico, cleanup e
zeroizzazione exactly-once, checkpoint durable pre-restore, ripristino esatto di
fprintd e signal mask, poi report finale. Il checkpoint rende il risultato
recuperabile anche se il restore fallisce; il finale registra fedelmente
l'esito del restore. Nessun failure autorizza un secondo comando o recovery
invasiva automatica.

Il live è hard-disabled due volte: l'unico entrypoint spedito risponde soltanto
con capability zero e respinge flag, ambiente, config e backend alternativo;
ogni metodo della facade libusb reale chiama un sigillo source che solleva prima
di qualsiasi API USB. D234 richiederebbe una patch esplicita a quel sigillo,
review umana e autorizzazione separata. La suite riproducibile corrente comprende
46 metodi unittest, oltre ai check statici censiti separatamente, e copre
happy/failure path D232, boundary, USB mock, TLS loopback reale, B0, restore,
report, KAT D190 e tentativi di enablement. Nessun test enumera o apre il sensore.

## Esito D234: blocker dell'unseal

L'operatore ha concesso l'accettazione del rischio D234, ma la review dell'unseal
ha stabilito che una patch minima al solo sigillo non rende raggiungibile il live
revisionato. L'entrypoint D233 resta esclusivamente offline e
`run_production_candidate_offline()` richiede ancora facade, loader, factory e
publisher iniettati; inoltre emette lo schema D233 offline e dichiara il live non
autorizzato. Collegare in modo production i path root del PSK/config, l'identità
USB, libusb reale e i report D234 richiederebbe nuova logica e nuovi parametri,
oltre il solo unseal consentito.

La decisione è `D234_BLOCKED_BY_UNSEAL_SCOPE_EXPANSION`. Il gate è avvenuto
prima del preflight operativo e prima di qualunque `libusb_init`: live run, open
USB, E4, comandi e handshake TLS sono tutti zero. Non sono stati caricati secret
o config protetti, non è stato fermato `fprintd`, non è stato necessario alcun
cleanup/restore e non vi sono stati retry. Benché nessun run live sia iniziato,
la decisione terminale consuma l'autorizzazione D234 secondo la regola finale
dello step; resta vietato avviare un altro tentativo nell'ambito di D234.

Il prossimo step è subordinato a review umana separata di un vero entrypoint
live production, dei suoi path operativi e del relativo diff ampliato, seguita
da una nuova autorizzazione esplicita. Nessun secondo tentativo è autorizzato da
D234.

## D235: entrypoint production-candidate offline

D235 chiude il blocker software di D234 senza toccare il sensore. Il nuovo
`src/goodix5125_d235_entrypoint.py` è un thin composition layer: non contiene
serializer, state machine, KDF, TLS o B0 alternativi. Risolve dipendenze,
costruisce i componenti D232/D233 esistenti, mappa i terminali e delega la
pubblicazione atomica e il restore all'orchestratore già revisionato. Per rendere
univoco il mapping, D233 espone ora soltanto due metadati osservativi aggiuntivi,
fase tentata e dominio dell'errore, senza alterare ordine o wire protocol.

I path production sono assoluti e indipendenti da `HOME`: PSK
`/var/lib/goodix-5125-poc/transport-material.bin`, manifest protetto
`/var/lib/goodix-5125-poc/target-material-manifest.json`, config
`/var/lib/goodix-5125-poc/target-config-90.bin`, PE canonico nel corpus D230,
report sotto `/var/lib/goodix-5125-poc/d236-results/` e marker
`/var/lib/goodix-5125-poc/d236-live-single-use.marker`. I tre input protetti
restano regular, root-owned, mode `0600`, non symlink e senza fallback; la
directory report production deve essere preesistente, root-owned, mode `0700`.

Il target selector futuro legge soltanto sysfs dopo il gate EUID/SUDO_UID,
richiede un unico `27c6:5125`, ricava bus/address/port-path e accetta soltanto il
nodo character esatto `/dev/bus/usb/BBB/DDD`. Non apre il device. Tale identità
alimenta sia lo scan holder sia `ProductionUsbTransport`, che la rivalida dopo
l'unico open futuro.

La composizione preflight collega EUID root, `SUDO_UID`, marker O_EXCL,
topologia processo/thread, holder, stato e restore `fprintd`, signal mask e
readiness dei report. Gli input seguono l'ordine manifest/config verificati,
PE canonico regular non-symlink e hash-gated, PSK caricata una volta,
derivazione D190/E4 e la stessa istanza `SecretBuffer` consegnata al TLS. Il
percorso di recovery resta: stop traffico, cleanup/zeroizzazione, checkpoint
durable, restore fprintd/segnali, report finale; failure di checkpoint, restore
o finale sono testati fail-closed.

La suite D235 usa soltanto facade, sysfs e USB sintetici confinati in directory
temporanee. Copre happy path, EUID/operatore/holder, metadata e symlink, PE,
E4, open/claim, ogni fase protocollo, Bad Record MAC, publication/restore,
segnali e tentativi di enablement. La suite integrata D232–D235 esegue 53 test
senza sudo, enumerazione target, lettura degli store reali o cambi a `fprintd`.

L'unico entrypoint spedito chiama `_d235_source_seal()` prima di sysfs, input,
servizi o libusb; inoltre ogni metodo libusb reale conserva il sigillo D233.
Argomenti `--live`/`--force`, argv inatteso, ambiente, config, backend alterno,
import diretto e invocazione `-m` mantengono capability e USB open a zero. Non
esiste un runtime unseal. D236 richiederà una patch source piccola e separatamente
revisionata su sigilli e dichiarazioni compile-time, nuova accettazione umana e
nuova autorizzazione; D235 non concede nessuna di queste.

## Esito D236: blocker del preflight root

D236 ha ricevuto `D236_OPERATOR_RISK_ACCEPTANCE=granted`. La patch di unseal è
rimasta minima: due source seal e le dichiarazioni compile-time D236, schema/mode
production e normalizzazione dell'exit code sulla decisione terminale. Non ha
aggiunto protocollo, builder, backend, retry, recovery o enablement runtime. I
test offline mirati dell'unseal, dell'exit code e della composizione sono passati.

Il comando root previsto era
`sudo -n python3 analysis/D236/d236_preflight.py`. `sudo` ha restituito
`a password is required` prima di avviare lo script. Di conseguenza EUID root e
`SUDO_UID` non sono stati acquisiti e il preflight protetto non è iniziato. Non
sono stati letti PSK/config store reali, non è stato enumerato il target, non è
stato interrogato o fermato `fprintd`, non è cambiata la signal mask e non è
stata chiamata alcuna API libusb.

La decisione è `D236_BLOCKED_BY_PREFLIGHT`: live run, USB init/open/claim, E4,
comandi e TLS sono tutti zero; retry, D4, application data, famiglie di scrittura
persistente e recovery invasiva sono zero. Cleanup e restore non erano necessari.
Poiché il live non è iniziato, l'autorizzazione D236 non è stata consumata, ma
l'esito terminale chiude comunque lo step e non autorizza un altro tentativo.

Dopo il blocker sono stati ripristinati entrambi i source seal e le dichiarazioni
compile-time non autorizzate; resta soltanto la correzione innocua dell'exit code.
Un futuro tentativo richiede un nuovo step, una nuova review, una nuova
autorizzazione e una sessione root già autenticata secondo governance. Non è
consentito rilanciare D236.

## Esito D237: autenticazione sudo non predisposta

D237 ha ricevuto `D237_OPERATOR_RISK_ACCEPTANCE=granted`, ma il gate operativo
iniziale obbligatorio `sudo -n true` ha restituito `a password is required`.
La decisione terminale è quindi
`D237_BLOCKED_BY_SUDO_AUTH_NOT_PRIMED`, distinta da un blocker Goodix e dal
preflight D236: nessun altro comando root è stato eseguito.

Il source unseal e la relativa review non sono stati raggiunti. Non sono stati
avviati il preflight root, la selezione sysfs, libusb, l'apertura o il claim USB,
E4, alcun comando OEM o TLS. Tutti i contatori live e di recovery sono zero;
`fprintd` e la signal mask non sono stati toccati e nessun cleanup era necessario.
La regola udev persistente resta assente. Poiché il live non è iniziato,
l'autorizzazione D237 non è stata consumata; l'esito terminale chiude comunque
lo step e non autorizza un secondo tentativo.

Un eventuale nuovo step live richiede una nuova review e autorizzazione umana e,
prima che Codex inizi, una sessione sudo già autenticata dall'operatore fuori dal
workflow. Codex non deve richiedere, ricevere o gestire credenziali.

## Evidenza live D236 successiva e consolidamento D238

Gli artefatti live aggiunti dopo i report iniziali D236/D237 modificano lo stato
canonico senza trasformare D236 in un cold-start riuscito. Nel primo run reale
E4 è stato trasmesso e il dispositivo ha restituito il validator corretto:
`runtime_psk_e4_binding_status=match`. Sul target reale e nello stesso run,
quindi, il record root autentico, la KDF/reference OEM recuperata e il validator
derivato convergono con E4. Il run si è fermato sull'ACK E4 troppo stretto, con
un solo open e un solo comando.

Dopo la correzione limitata di E4, il secondo run ha raggiunto `E4_MATCH`, ha
trasmesso A2 #1 e si è fermato sul relativo ACK: un open, due comandi e nessun
TLS. Il terzo run, deliberatamente troncato dopo il primo frame IN di A2, ha
registrato in forma redatta `wrapper=A0`, `control=b0`, body length 2,
`ack_echo=a2`, `ack_status=07`: il target reale ha quindi restituito
`B0/A2/07`. La struttura diagnostica rendeva `0x82` irraggiungibile.

Tutti e tre gli esiti hanno mantenuto zero retry, zero famiglie di scrittura
persistente, zero TLS, zero D4/application data, cleanup exactly-once,
zeroizzazione del secret, ripristino di signal mask/fprintd dove necessario e
source resealed. La conclusione corretta è soltanto:

```text
E4 cryptographic binding live proven
A2 #1 transport ACK 0x07 live proven
full pre-D1 path beyond A2 #1 not yet live-executed
```

D238 chiude offline la frammentazione. `PHASE_RESPONSE_POLICIES` è l'unica
policy ACK/risposta del core: ammette soltanto `01`/`07`, conserva restrizioni
per fase, risposte tipizzate, ordine monotono e zero retry. La suite esercita
l'intero path sia con tutti gli ACK `01` sia con tutti gli ACK `07`, oltre a
status non provati, echo errato, frame estranei, ordine invertito, B0 malformato
e ACK+risposta coalesciati. Il report production conserva per ogni fase solo
control/lunghezze/status/classificazione di ordine e completion; esclude secret,
raw config90, payload arbitrari e dati biometrici.

Il config `0x90` resta esattamente 224 byte, SHA-256
`e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82`;
il manifest resta pin-nato a
`1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15`
e `gfusb.dll` a
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`.
Il tentativo operatore D238 ha invocato direttamente
`python3 analysis/D236/d236_preflight.py` senza rendere esplicita la root del
repository nel path di import. È quindi terminato con
`ModuleNotFoundError: No module named 'src'` prima di entrare nel `main` del
preflight. L'incidente è classificato
`OPERATOR_KIT_PREFLIGHT_INVOCATION_FAILURE` e `NO_LIVE_USB_EXECUTION`: nessun
unseal, claim del marker, entrypoint production, init libusb, open USB o comando
Goodix è stato raggiunto. Il vecchio report D236 già presente non fu rigenerato
da quel tentativo e non ne costituisce evidenza.

## D239 e D241: dal primo B0 live alla transizione TLS

D239 ha sostituito il launcher operativo con
`operator_kit/d239-live-pre-d1-tls-once.sh`. Ogni entrypoint Python del launcher
riceve esplicitamente
`PYTHONPATH="$EXPECTED_REPOSITORY${PYTHONPATH:+:$PYTHONPATH}"`; il preflight
espone inoltre un probe d'import offline che costruisce gli stessi componenti
production senza toccare sistema, USB o secret reali. La patch di unseal resta
byte-identica a D238: non sono cambiati protocollo, allowlist, policy ACK,
retry, recovery, command family o percorso del materiale protetto.

Il percorso `--offline-dry-run-pre-usb` è eseguibile senza root. Usa facade,
materiale protetto e secret sintetici, verifica il PE canonico e compone il
vero entrypoint/backend fino all'esatto seam `libusb.init`. In quel punto un
fence offline termina intenzionalmente il percorso prima di inizializzare
libusb. Il report permanente attesta:

```text
OPERATOR_KIT_DRY_RUN_PRE_USB=PASS
pre_usb_fence_count=1
libusb_init_count=0
usb_open_count=0
goodix_command_count=0
real_secret_read_count=0
live_marker_create_count=0
source_unseal_count=0
fprintd_stop_count=0
live_usb_execution=NOT_PERFORMED
```

Il dry-run non crea marker persistenti; il claim single-use e il caricamento del
secret sono sostituiti soltanto in memoria. La directory marker live D238 è
protetta e non ispezionabile da utente non privilegiato; ciò non altera la
diagnosi, perché il fallimento d'import avvenne testualmente prima del relativo
check. Nessun marker live è stato creato da D239.

La Definition of Done permanente dell'operator kit è:

1. `bash -n` del launcher;
2. probe d'import con contesto esplicito;
3. dry-run reale fino al fence pre-USB;
4. validazione di schema, hash e tutti i contatori negativi del report;
5. sorgenti ancora sealed e patch live applicabile soltanto in dry-run;
6. suite completa senza regressioni.

D239 soddisfece questi punti con 74 test passati. Dopo la correzione manuale
della directory report root, l'operatore eseguì il singolo ramo live autorizzato.
Sul dispositivo reale `27c6:5125`, firmware `GF_ST411SEC_APP_12509`, la sequenza
fu `E4/A2/82/A6/A2/70/80x4/90/D1`, con `command_count=12`, binding E4 `match` e
risposta D1 `direct_b0_tls`. Il B0 aveva body length redatta 52; non vi furono
ACK D1, D4, application data, persistent write o retry. Cleanup, zeroizzazione,
restore e reseal risultarono completati.

La mappa causale chiusa da D241 è:

```text
D1 send
→ ProductionReplayBackend.exchange legge e riassembla il primo B0
→ _validate_responses verifica wrapper e ClientHello
→ il frame resta pending dopo la validazione
→ tls_handshake verifica l'identità del SecretBuffer E4-validato
→ B0TlsBridge riceve quel frame esattamente una volta
→ OpenSSL emette ServerHello e ServerHelloDone
→ due B0 distinti sono sottoposti a bulk OUT
→ una successiva bulk IN non riceve dati e scade il budget bounded
```

D241 ammette per il record layer ClientHello TLS 1.2 le legacy version
`0x0301`, `0x0302` e `0x0303` e una lista offerta che contenga `0x00a8`
anche insieme a SCSV o altre suite. Il server OpenSSL resta ristretto a
`0x00a8`; handshake version TLS 1.2, wrapper/lunghezze e struttura ClientHello
restano obbligatori. Non rende permissivo `unexpected_data` e non ammette B0
in altre fasi. Il pending frame viene rimosso prima del feed, quindi non può
essere riletto o reiniettato.

La singola run live D241 è evidenza reale, non un dry-run:

```text
D241_LIVE_SINGLE_SHOT_COMPLETED=true
D241_CLIENT_HELLO_VERIFIED=true
D241_CLIENT_HELLO_RECORD_LENGTH=47
D241_SERVER_HELLO_SENT=true
D241_SERVER_HELLO_RECORD_LENGTH=81
D241_SERVER_HELLO_DONE_SENT=true
D241_SERVER_HELLO_DONE_RECORD_LENGTH=4
D241_CLIENT_KEY_EXCHANGE_OBSERVED=false
D241_TLS_CRYPTOGRAPHIC_HANDSHAKE_COMPLETED=false
D241_ERROR_CLASS=TLS_HANDSHAKE_TIMEOUT_AFTER_SERVER_FLIGHT
D241_D4_COUNT=0
D241_APPLICATION_DATA_COUNT=0
D241_PERSISTENT_WRITE_FAMILY_COUNT=0
D241_RETRY_COUNT=0
D241_SECRET_ZEROIZED=true
D241_FPRINTD_RESTORED=true
D241_SOURCE_RESEALED=true
D241_DO_NOT_RETRY=true
```

Nel JSON ereditato, `decision=D236_ABORTED_USB_TRANSPORT` e
`backend_failure_domain=usb_transport` sono label nominali legacy. Non hanno
precedenza sulla classe causale specifica: l'esito canonico D241 è
`TLS_HANDSHAKE_TIMEOUT_AFTER_SERVER_FLIGHT`. Il server flight fu emesso da
OpenSSL, avvolto in due B0 validi, sottoposto e completato integralmente secondo
le lunghezze richieste dal codice D241; una bulk IN post-flight fu realmente
tentata e non restituì dati. Questo sposta la vecchia analisi oltre un semplice
errore locale di submit, ma non rende equivalente il contratto USB all'OEM.

La semantica delle lunghezze è ora chiusa tracciando i produttori dei campi:
`response_body_length=52` in D239 è `len(parse_b0(frame))`, cioè record TLS
completo; `record_length=47` nella trace D241 è il payload dichiarato
dall'header TLS. Quindi `52 = 5 byte di header TLS + 47 byte di payload` e la
classificazione è
`D239_52_EQUALS_TLS_HEADER_PLUS_D241_47_CONFIRMED`. Non riguarda i quattro byte
del wrapper B0.

## D242/D243/D244/D245 live e confine D246

La sola capture primaria locale disponibile è quella storicamente classificata
D175; la capture D43 è assente e resta `NOT_ASSESSABLE`. D175 mostra la stessa
struttura TLS osservata in D241: ClientHello payload 47 con suite offerte
`00a8,00ff`, ServerHello payload 81 che seleziona `00a8`, e
ServerHelloDone payload 4. ServerHello e ServerHelloDone sono in due B0
distinti, un record TLS per B0; wrapper type, declared/actual length e checksum
sono coerenti. Non è una equivalenza byte-per-byte dei valori casuali o del
session ID, che restano intenzionalmente non pubblicati.

Il differenziale primario D242 aveva identificato due divergenze dal send path
Windows osservato:

1. il send callback Windows spezza ogni B0 in segmenti logici `<=64`, ma
   sottopone sempre 64 byte al bulk OUT, con tail nonzero catturata fuori dalla
   lunghezza B0 dichiarata; D241
   sottoponeva finali corti (ServerHello `64+26`, ServerHelloDone `13`), mentre
   D175 osserva completion da `64+64` e `64`;
2. la DLL chiama `Sleep(10)` dopo ciascun record TLS. D175 osserva circa
   21,933 ms fra completion ServerHello e primo OUT ServerHelloDone, mentre
   D241 drenava e inviava i due record back-to-back senza pacing.

Il timeout di 3000 ms non spiega la divergenza temporale osservata: nella
sessione OEM il ClientKeyExchange inizia circa 13,338 ms dopo ServerHelloDone,
molto dentro quel budget. D242 aveva quindi esteso staging da 64 byte con tail
zero-initialized e completion da 64 a ogni OUT A0/B0, oltre al pacing di 10 ms
dopo ogni record TLS. La successiva run live D242 ha però terminato al primo
E4: `command_count=1`, `usb_open_count=1`, nessun frame completo IN e timeout.
Il binding E4 non è stato raggiunto; `tls_handshake_count=0`,
`server_flight_usb_bulk_out_count=0` e `server_flight_pacing_count=0`. Retry,
D4, application data e write persistenti sono rimasti zero; cleanup exactly
once, secret zeroization, restore fprintd/segnali e source reseal sono riusciti.

La copia primaria locale accessibile è
`analysis/D242/D242_operator_live_stdout.json`, SHA-256
`1d9c2c736a2b8939855a184e350ea2ecaa914921536ae2a2d616130a166eb7e7`,
classificata `PRIMARY_LOCAL_EVIDENCE_VERIFIED`.

D243 ha poi eseguito live lo split A0/B0: A0 era tornato alla submission corta
D241, ma il singolo E4 ha prodotto di nuovo `command_count=1`, nessun frame
completo e timeout. Binding E4, server flight, pacing e TLS non sono stati
raggiunti; retry, D4, application data e write persistenti sono rimasti zero;
cleanup, zeroizzazione, restore e reseal sono riusciti. La copia locale
`analysis/D243/D243_operator_live_stdout.json`, SHA-256
`a82c43f4aba5c6f9dcfe072eee7b8b6ab0edc7f621961ea6a322dfe6ac45aa23`,
è anch'essa `PRIMARY_LOCAL_EVIDENCE_VERIFIED`. Non sono state lette directory
root-only né usati privilegi per acquisire queste evidenze.

La classificazione corrente è quindi:

```text
D243_A0_FIXED64_CAUSAL_STATUS=FALSIFIED_AS_SUFFICIENT_EXPLANATION_BY_D243_LIVE
D244_A0_FIXED64_DEVICE_EQUIVALENCE_STATUS=UNRESOLVED
D244_B0_FIXED64_DEVICE_EQUIVALENCE_STATUS=NOT_YET_LIVE_REACHED
```

La tail Windows A0 resta non nota e non è né provata né falsificata come
contratto device-side. È falsificata soltanto la sua sufficienza causale per il
timeout D242. Il server flight B0 fixed-64 con pacing 10 ms non è stato
raggiunto live né da D242 né da D243.

D243 applica lo split minimo nello stesso backend: A0/E4/pre-D1 torna alla
submission D241 live-proven (ultimo chunk corto, nessuna tail aggiunta,
completion pari al chunk), mentre B0/TLS conserva fixed-64 e pacing 10 ms.
Declared length, header/checksum, serializer, policy ACK/risposta, ordine e
timeout restano invariati; wrapper inattesi falliscono chiusi. Fixture offline
verificano l'E4 logico esatto con `len(submitted_E4_chunk) != 64`, l'intera
sequenza A0 pre-D1, ServerHello `64|64`, ServerHelloDone `64`, tail zero,
short completion fail-closed e due pause da 10 ms senza pacing A0.

`PROVEN_DIVERGENCE != PROVEN_DEVICE_ROOT_CAUSE`. D244 ha rieseguito il
differenziale sulle fonti reali archiviate D241/D242/D243. I path E4 D241 e D243
non sono byte-identici come sorgente, perché D243 aggiunge validazione wrapper e
telemetria, ma sono semanticamente equivalenti sul frame E4 canonico valido.
Il generic fixed-64 A0 D242 è completamente rimosso dal path D243. Le otto
differenze D241↔D243 raggiunte prima del timeout comprendono cinque differenze
host-side behavior-relevant intenzionali (namespace, gate e preflight), nessuna
wire/timing regression sul frame valido e zero candidati causali irrisolti.

Il logical E4 D241/D242/D243/D244 è in tutti i casi
`a00c00ace40900030002bb00000000fd`, lunghezza 16, SHA-256
`b6ada1adde00249e4e55f41bbf7c00443409c3752050520bc1a1874b0b63cf1a`.
`ProductionUsbTransport.command_count` aumenta soltanto dopo completion
full-length di tutti i chunk bulk OUT. Poiché E4 era l'unico comando e i due
report live hanno `command_count=1`, entrambi provano OUT completato; il timeout
è `IN_CONFIRMED_AFTER_OUT_COMPLETION`. Un timeout OUT sintetico lascia invece
`command_count=0` e non tenta bulk IN. Non è stata necessaria nuova
strumentazione runtime.

Il kit storico D242 usava esclusivamente
`/var/lib/goodix-5125-poc/d242-operator-invocation.marker`; i marker storici
D236/D238/D239/D241 sono benigni e non vengono cancellati. Prepara
idempotentemente `/var/lib/goodix-5125-poc/d242-results` root `0700`, verifica
hash e sealed baseline, applica l'unseal soltanto per la singola invocazione,
e reseala nel cleanup. Il closure gate esegue con peer USB/TLS sintetici
preflight, lifecycle directory/marker, patch apply/reverse, handoff exactly-once,
successo, timeout post-flight, osservabilità redatta e cleanup. Il suo stato è
`D242_EXECUTABLE_CLOSURE_GATE_PASS`. Quello stato `READY_NOT_EXECUTED` era vero
prima della run; la singola invocazione live D242 è ora consumata e non è il kit
corrente.

La closure finale di observability D242 elimina il terminale generico
`PREFLIGHT_FAILED`: se il preflight reale fallisce, lo stesso launcher legge il
report JSON appena prodotto e mostra immediatamente classe specifica, lista dei
failure, marker path e contatori zero per USB/comandi/secret/marker live. Report
mancante, invalido o renderer fallito hanno classi distinte e fail-closed. Il
path è verificato senza sudo con una fixture sintetica che termina prima di
unseal, USB, secret, fprintd e marker. Questa proprietà storica resta valida;
la run D242 successiva ha consumato il kit ed è terminata al primo E4. Anche il
kit D243 è ora consumato; anche la singola autorizzazione D244 descritta sotto
è consumata. Anche la singola invocazione D245 è ora consumata. La frase
storica che indicava D246 come riferimento soltanto offline descriveva lo stato
prima della run D246: D246 è poi stato eseguito live con successo ed è chiuso a
`STOP_AFTER_D4`. D250 è stato poi eseguito una volta fino alla AE strutturale ed
è consumato. D251 ha poi corretto validator/osservabilità ed è stato eseguito
una volta sulla baseline live approvata, chiudendo AF a `STOP_AFTER_AF`; anche
il suo marker è consumato. D252 non ha prodotto un nuovo kit live.

La provenance D241 è nuovamente byte-exact e read-only:
`d241_operator_dry_run.py` ha SHA-256
`0bf0921435624ef64b57328af8c2a669be1b1da51dc8b4caeece2f5d35e2944f` e
`d241_preflight.py` ha SHA-256
`6cc7ddd62fe1dffedd71abfb05ba0a4ef5788d155ddd288782b2b222d25c5cf7`.
Sono le sole dipendenze D241 behavior-relevant della closure/preflight D242,
entrambe pin-nate e verificate prima dell'import dal launcher; l'adattamento
alla tail fixed-64 vive esclusivamente in D242. Il bundle D242 precedente
SHA-256 `a112fe2be21a48ff84072194e38cf07bfdb0817b42c44de43bc01e858a56df20`
è `SUPERSEDED_DO_NOT_USE_FOR_LIVE_AUTHORIZATION`: il differenziale tecnico e il
runtime fix restano utili, ma quella revisione fallì i gate di
provenance/closure/manuale e non è più il riferimento operativo.
Anche il bundle intermedio SHA-256
`df0f01b6fe78786eb22adf156f5d0c830d93a475e7a45f349635c5fb2843e60f`
è `SUPERSEDED_BY_FINAL_OPERATOR_OBSERVABILITY_CORRECTION_DO_NOT_USE_FOR_LIVE_AUTHORIZATION`;
il solo riferimento D242 finale è identificato dal sidecar `.zip.sha256`
esterno allo ZIP.

Gli hash sealed D242 verificati prima della modifica D243 erano
`c072db52...e90fcef` per `goodix5125_d233_backend.py` e
`6cd9fd37...908993` per `goodix5125_d235_entrypoint.py`: entrambi `MATCH`.
Gli offset `+1` e `-9` osservati applicando la patch D242 erano coordinate di
hunk non aggiornate rispetto alle linee correnti; il context match e il
round-trip byte-exact, insieme agli hash, escludono un baseline diverso. La
patch D243 è generata contro il baseline sealed D243 verificato e si applica e
si inverte senza offset.

Il launcher D243 usa il marker
`/var/lib/goodix-5125-poc/d243-operator-invocation.marker` e la directory
`/var/lib/goodix-5125-poc/d243-results`. Riusa il modello durevole già
revisionato: runtime abort, cleanup e zeroizzazione, checkpoint atomico
pre-restore, restore e report finale sono distinti. Una fixture timeout al
primo E4 verifica checkpoint con `report_publish_count=1` e segnali ancora
`pending`, quindi report finale con restore registrato e
`report_publish_count=2`. La closure offline era
`D243_EXECUTABLE_CLOSURE_GATE_PASS`; la successiva run live è quella terminata
al timeout E4 descritta sopra.

Il cleanup D241 non eseguì device reset, USB reset, A2 reset, re-enumeration
forzata, power-cycle, protocol close o Goodix state reset: eseguì soltanto stop
del nuovo traffico, release/close/exit USB, zeroizzazione, restore fprintd e
signal mask, publication e source reseal. Quindi
`D244_POST_D241_DEVICE_STATE_RESET_OBSERVED=false`. La cronologia journal
accessibile senza privilegi colloca D241 nel boot host
`704a277d1ed647ec877c90a83b2043d4` e D242/D243 nel boot successivo
`bc1ec5816f8044528be0e1feeafcc4c7`: l'ipotesi carryover è
`WEAKENED_BY_INTERVENING_BOOT`, non falsificata, perché un reboot host non prova
il power-cycle elettrico del sensore.

Il launcher D244 usa il marker
`/var/lib/goodix-5125-poc/d244-operator-invocation.marker` e la directory
`/var/lib/goodix-5125-poc/d244-results`. Conserva il wire D243 e richiede
all'operatore di confermare nell'argomento di autorizzazione un normale shutdown
completo seguito da accensione e avvio Fedora. Confronta read-only boot-id,
uptime e, se accessibile, `journalctl --list-boots` con la baseline D243. La run
è un fresh-state control valido solo con conferma operatore e boot-id diverso;
metadati insufficienti o stesso boot producono
`D244_FRESH_STATE_CONTROL_VALID=false` senza fingere una prova elettrica. La
closure sintetica verifica i casi boot-id presente/assente, uptime-only e
metadati insufficienti, insieme a E4, A0, B0, pacing, durability e safety.
La successiva singola run live è stata eseguita con fresh host boot documentato
e controllo fresh-state valido. E4 OUT ha completato, E4 IN è andato in
timeout, il binding non è stato raggiunto, TLS non è stato raggiunto, retry è
rimasto zero e cleanup, restore e reseal sono terminati. La classificazione
corretta è:

```text
D244_FRESH_STATE_HOST_CONTROL_RESULT=E4_TIMEOUT_PERSISTS
D244_FRESH_HOST_BOOT_SUFFICIENCY=FALSIFIED_AS_SUFFICIENT_RECOVERY_CONDITION
D244_SENSOR_ELECTRICAL_POWER_CYCLE_STATUS=NOT_PROVEN
```

Lo shutdown e la rimozione dell'alimentatore esterno non provano che il sensore
abbia perso alimentazione dal laptop con batteria interna. Quindi il carryover
della sola sessione host non basta a spiegare il fallimento, mentre lo stato
elettrico/protocollare del device resta irrisolto; non si dichiara falsificato
in assoluto il carryover di stato device post-D241.

Lo stato iniziale di `fprintd` non è una spiegazione sufficiente:

```text
D241: active   -> E4 superato
D242: active   -> E4 timeout
D243: active   -> E4 timeout
D244: inactive -> E4 timeout
D245_FPRINTD_INITIAL_STATE_CAUSAL_STATUS=NOT_SUFFICIENT_EXPLANATION
```

Il comportamento production resta invariato: se `fprintd` è inizialmente
active viene fermato e ripristinato; se è inactive non viene avviato.

Il corpus storico canonico conserva una run live D179 sul firmware 12509 con
questo boundary:

```text
A8 OUT      a00600a6a803000000ff
A8 ACK      a00600a6b00300a8014e        status 01
A8 response GF_ST411SEC_APP_12509
A8_COMPLETE
E4 OUT      a00c00ace40900030002bb00000000fd
E4 ACK      a00600a6b00300e40112        status 01
E4 response status 0, selector bb020003, validator 32 byte corretto
```

La policy di response A8 è determinata anche dai record storici D43 e D175:

```text
D43:  A8 -> B0/A8/01 -> A8/17 -> GF_ST411SEC_APP_12509\0
D175: A8 -> B0/A8/07 -> A8/17 -> GF_ST411SEC_APP_12509\0
```

D175 falsifica la policy erroneamente reintrodotta nella prima closure D245,
secondo cui ACK07 sarebbe stato terminale senza response. `0x01` e `0x07` sono
classi ACK empiricamente distinte; entrambe autorizzano esattamente una bounded
A8 response read. La semantica nominale interna di entrambe resta ignota. In
particolare, `0x07` è classificato
`UNKNOWN_STATUS_CLASS_EMPIRICALLY_COMPATIBLE_WITH_RESPONSE`, non failure,
busy, not-ready, terminal o response-not-authorized.

Gli artifact runtime primari D179 sono stati bonificati e non sono più nel
repository corrente: il record è
`CANONICAL_HISTORICAL_LIVE_RECORD_PRIMARY_RUNTIME_ARTIFACTS_PURGED`, non
`PRIMARY_LOCAL_EVIDENCE_VERIFIED`. D230 lo corrobora indipendentemente: la
capture corrente contiene due A8 request byte-exact, ACK `B0/A8/01` e response
tipizzata `GF_ST411SEC_APP_12509\0`; il census DLL identifica `GetEvkVersion` e
l'audit read-boundary classifica A8 come query-only di metadato fisso senza
side effect, distinta da flash/IAP, provisioning, OTP/config write e biometria.

La semantica ammessa resta limitata:

```text
D245_A8_SEMANTIC_CLASS=TARGET_LIVE_PROVEN_READ_ONLY_PRECONDITION_DISCRIMINATOR
D245_A8_INITIALIZER_STATUS=NOT_PROVEN
D245_A8_CAUSAL_ROLE=PRECONDITION_OBSERVED_BEFORE_SUCCESSFUL_E4_NOT_DEVICE_INITIALIZATION_PROVEN
```

A8 non è quindi chiamata initializer, reset o wake. D245 richiede wrapper e
checksum validi; ACK echo A8 status `01` oppure `07` autorizza esattamente una
response read. Per entrambi gli status, `A8_COMPLETE` richiede A0 control A8 e
body esatto `GF_ST411SEC_APP_12509\0`, senza frame trailing/unowned. Timeout,
response malformed, control errato, mismatch 12508/12510 o frame extra fermano
la run con E4 count zero e zero retry. Uno status diverso da `01|07` ferma la
run senza una seconda IN e sempre con E4 count zero.

Solo dopo A8 completo, E4 canonico e binding `match`, lo stesso backend continua
`A2→82→A6→A2→70→80x4→90→D1→TLS`. A0 conserva gli OUT corti D241; il server
flight B0 conserva submission fisiche fixed-64 con tail deterministica a zero,
pacing 10 ms per record e timeout 3000 ms. Nel kit D245 D4, application data,
reset e retry erano irraggiungibili. Il launcher usa il marker
`/var/lib/goodix-5125-poc/d245-operator-invocation.marker`, i risultati
`/var/lib/goodix-5125-poc/d245-results`, risolve la root dal proprio path/git e
verifica gli hash sealed dopo il rename. Gli hash correnti backend/entrypoint
coincidono con D243/D244; la closure applica e inverte la patch senza offset e
prova il dry-run production-shaped senza USB reale.

La run live D245 successiva è evidenza primaria locale verificata in
`analysis/D245/D245_operator_live_stdout.json`, SHA-256
`2992457855197b90dad3f7048bef85a6703079b95452dc07fa8e201a5c294e09`.
Il risultato è `pass`: ACK A8 `07`, response firmware 12509 esatta, binding E4
`match`, tutti i comandi pre-D1, D1 e handshake TLS completati. Il terminale è
`TLS_HANDSHAKE_OK`, con `command_count=13`, un solo open USB, un solo handshake,
zero D4, zero application data, zero retry e zero famiglie di scrittura
persistente. Cleanup, restore di fprintd/segnali e source seal risultano
completati; non è registrata una failure. Questo sostituisce lo stato storico
`READY_NOT_EXECUTED` di D245 senza attribuire ad A8 una semantica initializer.

La correzione governance v2.1 non auto-approva una baseline live. L'eventuale
commit SHA del live-critical set D245 deve essere designato dopo review
dall'Utente/AI PM; lo stato corrente è
`LIVE_BASELINE_APPROVAL_PENDING_USER_REVIEW`, che non blocca la closure offline.
I pin correnti di backend, entrypoint, core, patch unseal e preflight proteggono
ancora il percorso live/source-sealing; i pin di audit, contratto, runtime
matrix, closure runner, report storico e test sono governance/closure. D245 non
estende il pinning e non lo ridisegna opportunisticamente.

I launcher D239–D244 sono stati confrontati con i rispettivi bundle storici e
ripristinati byte-per-byte alla versione canonica, incluse le loro assunzioni
di location storiche. Solo `d245-live-tls-once.sh` resta robusto al rename della
root. I test correnti trattano l'eventuale stop per vecchia location come
comportamento storico atteso, senza mutare i launcher:

```text
D245_HISTORICAL_LAUNCHER_INTEGRITY=RESTORED
D245_HISTORICAL_LAUNCHER_MUTATION_COUNT=0
```

Nel kit D245 D4, application data, FDT, capture, enroll, reset/power-cycle e
recovery invasiva automatica erano irraggiungibili o vietati. D246 ha reso
raggiungibile soltanto D4 nella run separatamente approvata, tramite due patch
temporanee applicate in ordine D245→D246; tutte le azioni successive sono
rimaste irraggiungibili. D246 è stato eseguito live una sola volta e si è
fermato dopo l'ACK D4. D240 è obsoleto e non è stato eseguito.

Storicamente, fino a D246, il riferimento Rocky era soltanto corroborazione
esterna e nessuna implementazione GPL era stata copiata nel repository allora
BSD-2-Clause. Questa frase descrive le revisioni storiche, non la policy futura:
dopo D247 il riuso GPL è consentito in `core/`/`tools/` con provenance; resta
vietato usarlo come prova primaria target-specific o copiarlo nel dominio LGPL.

### D246: dal TLS Finished al solo D4

Il riesame metodologico che ha governato la run live completata era:

1. la run non ripeteva un esperimento precedente: D245 aveva già chiuso TLS e
   D246 aggiungeva esattamente un D4 e stop;
2. testava l'ipotesi che il D4 staticamente/capture-correlato come
   `VOLATILE_SESSION_INITIALIZATION` sia accettato live dal target con ACK
   esatto `d4/01`, senza richiedere alcuna azione successiva;
3. in caso di failure non erano autorizzati retry o patch cosmetiche; la run ha
   invece chiuso D4 al primo tentativo, quindi tale ramo non è stato percorso.

La catena causale stretta nella capture D230 è:

```text
frame 134  completion host TLS Finished
frame 136  H→D A0/D4, logical 10, physical OUT 64, zero tail
           a00600a6d403000000d3
frame 138  D→H B0 ACK, body d4 01
           a00600a6b00300d40122
frame 140  successivo host A0/AF — fuori scope e irraggiungibile in D246
```

Il submit D4 segue di circa 53,154 ms la completion host Finished; l'ACK segue
D4 di circa 1,043 ms. Il callsite primario DLL a `0x18001f16b` è nello stesso
percorso handshake/init, dopo stato handshake `0x10` e `Sleep(20)`. Chiama il
builder D4 `0x18001c46c`, che serializza major `0xd`, subtype `2`, due byte body
zero e usa il generic A0 con budget caller 200 ms. D4 è quindi plaintext A0
post-handshake, non un record TLS application data. La capture mostra un solo
ACK `d4/01` e nessuna response D4 tipizzata; D246 non autorizza una seconda IN
né interpreta altri status.

Sul firmware APP12509 il dispatcher a `0x08035e3c` instrada la famiglia D al
receiver presente `0x080396b0`. Il branch subtype 2 a `0x0803987c` azzera solo
SRAM `0x20000790`; la coda comune legge un bit volatile tramite `0x0802e144` e
setta o pulisce un bit in SRAM a `0x20006d3c+5`. `0x0802e144` effettua soltanto
un read/test di RAM. Nel percorso esatto non compaiono chiamate o target
flash/IAP, OTP, configurazione persistente, provisioning, enrollment o factory
data. La classificazione ristretta è dunque:

```text
D246_D4_SEMANTIC_CLASS=VOLATILE_SESSION_INITIALIZATION
D246_HOST_SIDE_NO_PERSISTENT_WRITE_OBSERVED=true
D246_DEVICE_SIDE_PERSISTENCE_EXCLUDED_WITH_SUFFICIENT_EVIDENCE=true
D246_SCOPE=EXACT_APP12509_D4_RECEIVER_PATH_ONLY
```

Questo non prova l'assenza assoluta di persistenza per comandi successivi,
receiver resident mancanti o varianti firmware. Prova quanto basta per il solo
D4 esatto: precondizioni TLS completo, identità stabile e buffer RX vuoto;
una pausa host da 20 ms; un OUT fisico fixed-64 zero-tail; un ACK bounded entro
200 ms; accettazione solo del body `d4 01`; quindi `STOP_AFTER_D4`. Timeout,
completion ambigua, ACK diverso o frame trailing terminano senza retry,
rilasciano le risorse e resealano. AF e ogni azione ulteriore sono non
raggiungibili.

La successiva run live D246 è evidenza primaria locale in
`analysis/D246/D246_operator_live_stdout.json`, SHA-256
`055ace08832e2297d1b3687523fd41a410ed80b215207d63c352ea1cee2493e0`.
Il risultato autoritativo è determinato dai contatori e dai campi D246
specifici della run:

```text
D246 live execution                 COMPLETED
execution_mode                      live_single_shot
usb_open_count                      1
TLS cryptographic handshake         COMPLETED (count 1)
D4 attempt/send count               1/1
D4 ACK                              status 0x01
D4 completed                        true
D4 request logical/physical length  10/64
D4 response body length             0
D4 completion                       single_frame_usb_completion
retry/application data count        0/0
persistent write family count       0
terminal boundary                   STOP_AFTER_D4
cleanup                             completed (count 1)
secret/source/fprintd               zeroized/sealed/restored
```

Il raw evidence resta byte-identico. I campi
`LIVE_BASELINE_APPROVAL=PENDING_USER_REVIEW`,
`decision=D236_LIVE_TLS_HANDSHAKE_SUCCESS` e
`reached_phase=TLS_HANDSHAKE_OK` sono metadata legacy del renderer: sono
incoerenti con la closure finale D246 ma non invalidano la run. `result=pass`,
`execution_mode=live_single_shot`, i contatori D4 e l'osservazione protocollo
D4 sono i campi autoritativi. La run produce nuova evidenza tecnica live che il
target accetta l'exchange previsto; non estende la prova semantica oltre
`EXACT_APP12509_D4_RECEIVER_PATH_ONLY`.

Il contratto exactly-once distingue ora `d4_attempt_count`, latched a uno
immediatamente prima della chiamata che può consegnare il frame al transport,
da `d4_send_count`, che indica soltanto il ritorno full-length confermato. La
guardia d'ingresso vieta D4 quando attempt è già diverso da zero. Una
completion ambigua conserva quindi `attempt=1`, `send=0`, failure
`ambiguous_usb_completion`, zero retry; una re-entry intenzionale termina prima
del transport con secondo write zero, senza inferire se il device abbia
ricevuto il frame.

Il delta vive in `analysis/D246/D246_d4_continuation.patch` ed è applicato
soltanto dopo la patch D245. Nella closure offline le patch vivono in una copia
temporanea; nella run approvata il launcher ha creato prima backup byte-exact,
applicato D245→D246 alle due sorgenti canoniche per una sola invocazione
dell'entrypoint e garantito restore/reseal tramite trap anche su uscita anomala.
Le sorgenti D233/D235 a riposo restano source-sealed. La matrice sintetica prova
regressione D245 fino a TLS, happy path D4 exactly-once, timeout D4 senza retry,
ACK inatteso e assenza di qualunque OUT dopo D4. L'estensione di safety prova
anche disconnect e re-enumeration terminali senza reopen/reclaim, secondo D4
irraggiungibile, completion ambigua con re-entry vietata e nessun reset/recovery
automatico. I fixture preflight provano che il marker D245 è benigno, il marker
D246 blocca e path/renderer sono soltanto D246. Un repository Git temporaneo
prova che la modifica di `binding_reference/runtime.py` rende la baseline
`STALE`. Closure, hash pre/post, 135 regressioni e contatori reali provano zero
open USB reale, zero handshake TLS reale, zero D4 reale e zero famiglie di
scrittura persistente.

`operator_kit/d246-live-d4-once.sh` accetta `--offline-dry-run` oppure il solo
argomento live esatto `--i-authorize-one-d246-d4-live-attempt`. Il ramo live
fallisce chiuso se non coesistono EUID root, `SUDO_UID` numerico non-root,
marker D246 assente, preflight PASS, source seal attivo e una baseline approvata.
La governance v2.1 usa come baseline primaria il commit SHA completo designato
esternamente in `D246_APPROVED_LIVE_BASELINE_SHA` dopo review AI PM e confronta
direttamente con i blob Git l'intero set live-critical transitivo: launcher,
patch D245/D246, preflight/renderer/helper D246, D232/D233/D235, il PE canonico
hash-gated e i quattro moduli package/runtime/crypto/parser del binding PSK↔E4.
SHA assente/non valido o
contenuto stale bloccano la run. Manuale, report, status e test non sono oggetto
di pinning generalizzato. Marker, directory risultati e report preflight sono
esclusivamente D246.

Prima della correzione, un tentativo operatore si è fermato nel preflight D245
ereditato sul marker storico consumato. Questo prova soltanto un difetto
host-side: `D246 live attempt=NOT_STARTED`, USB/comandi/secret read/mutazioni
fprintd/D4 attempt tutti zero e stato device invariato. Il marker D245 resta
storico, benigno e intatto. La precedente baseline candidata
`ff4cc3b748dafbce681e6fa38a44936eca794d12` è
`SUPERSEDED_NOT_APPROVED_FOR_LIVE`.

Lo stato finale è
`D246_D4_LIVE_EXECUTION_COMPLETED_STOP_AFTER_D4`, con
`ADVANCEMENT=REAL_EXECUTION_COMPLETED` ed `EXECUTABLE_CLOSURE=PASS`. La run ha
prodotto anche nuova evidenza tecnica live sul D4, mentre la categoria primaria
di avanzamento resta l'esecuzione reale completata. L'autorizzazione single-shot
è consumata: D246 non autorizza un secondo D4, retry o il comando AF.

## D249: core GPL offline AF → FDT → first image

D249 usa la baseline Rocky immutabile
`227eba219fa9e3fbac5bd59aca79f624f67cd11b`. Le sole parti adattate nel dominio
GPL provengono da `src/goodix_cmd.c`, `src/goodix_frame.c` e
`src/goodix_capture.c`, con SPDX GPL-2.0-or-later e attribution registrati nel
ledger. Rocky resta fonte implementativa e corroborativa, non prova
APP12509. Lifecycle USB, retry/reconnect, PSK/MCU write, persistenza baseline,
firmware/IAP/ClearApp e le famiglie E0/A4/F0/F4 non sono importati né
raggiungibili.

La prima revisione D249 conteneva un decoder immagine non equivalente alla
closure locale. La correzione lo ha rimosso: `core/post_d4.py` delega ora
esattamente a `src/goodix5125_cleanroom.py`. Restano quindi canonici record da
7684 byte, 7680 packed, gruppi 6-byte/4-sample, 5120 sample, trailer CRC nel
reale ordine `crc>>8, crc, crc>>24, crc>>16` e transpose wire-index → raster
80×64. I test costruiscono il record con il codec locale, confrontano tutti i
pixel dei due output, verificano un KAT non banale e corruzione CRC; non usano
un encoder duplicato D249.

La capture locale osserva AF e comandi FDT plaintext nella sessione post-TLS;
la DLL conferma serializer AF, timestamp, risposta AE da 16 byte e bit di stato.
Il modello offline D249 storico sceglieva separatamente due percorsi: AF senza
POV → invio asincrono FDT down 32 → IRQ 2 → invio asincrono SetMode Image 20 → immagine;
AF con POV valido → invio asincrono D2 → immagine cached. D252 ha poi stabilito
che questo tratto, mutuato da Rocky, non è wire-exact per l'unica occorrenza
target con IRQ 2: il successivo OUT è `0x22 [01 00]`, mentre `0x20` compare
separatamente nei path di immagine base/no-finger. D253 ha quindi corretto
organicamente il core corrente: `build_finger_image()` serializza `0x22`, la
allowlist e la policy ACK includono echo `22`, e la state machine usa quel
comando dopo IRQ2 con latch di tentativo pre-submit. `build_set_image()` resta
il builder `0x20` separato. D249 resta la provenance storica della closure
sintetica; la correzione current-path D253 non prova che il percorso sia
live-safe.
Gli ACK osservati
localmente dopo 32, 20 e 22 vengono validati se presenti, ma non sono una
precondizione causale obbligatoria; per D2 la presenza target resta non nota. Entrambi validano framing, checksum, record, CRC,
unpack/transpose e terminano esplicitamente in `FIRST_IMAGE_RECEIVED`. Questa è
closure eseguibile delle fixture sintetiche, non prova che il sequencing sia il
minimo causale o live-safe sul 12509.

La matrice ACK D249 classifica AF come `FORBIDDEN`: le occorrenze locali hanno
risposta AE diretta senza ACK. Per 32, 20, 36 e 34 la capture osserva un ACK
successivo, ma non prova che sia necessario prima dell'evento/payload push;
questi comandi sono quindi `OPTIONAL_IF_PRESENT`. D2 non è osservato nella
capture target; Rocky lo invia asincrono e consuma eventuali ACK nel receive
loop, perciò il parser D249 usa ancora `OPTIONAL_IF_PRESENT` come policy di
accettazione senza trasformarla in evidenza target. Zero o un ACK esatto sono
accettati; ACK errato o duplicato fallisce chiuso.

La policy generica D249 resta strict: `parse_payload()` calcola sempre il
checksum e un `0x88` non aritmeticamente valido fallisce. D267/03 aveva
aggiunto soltanto `payload_trailer_class=0X88`. D267/04 stabilisce però nel
materiale OEM locale che lo stesso parser riceve anche il plaintext post-TLS,
salta la verifica additiva sul trailer `0x88`, classifica poi `major == 2` e
passa `data+5`/`declared_length-6` al consumer del record immagine. Il solo
`parse_image_payload()` replica ora tale semantica dopo i gate di framing,
major image, lunghezza 7684 e POV; `payload_checksum_policy` distingue
`ADDITIVE_VERIFIED`, `NO_CHECK_0X88_ACCEPTED` e `NOT_REACHED`. Il CRC record
resta strict. Rocky è solo corroborazione. Il trailer di D267/01 resta
`UNKNOWN`, quindi la nuova validità semantica generale/image-specific non
dimostra che quel marker abbia causato la failure live.

La closure avversariale copre ACK inattesi/duplicati, eventi fuori ordine,
immagine anticipata, control e framing errati, EOF parziale, lunghezze immagine,
CRC e transizioni duplicate/regressive. Non esistono backend USB/TLS concreti,
secret, persistenza, retry o loop non bounded. D251 ha raggiunto live AF/AE e
si è fermato prima di FDT o dito. D252 ha provato la derivazione dinamica della
tabella FDT ma non la sua freschezza current-path né un restore post-arming;
D253 ha delimitato il setter host del seed senza trovarne la sorgente ultima e
ha confermato l'assenza di restore deterministico. D255/D256 hanno poi provato
la re-entry/re-arm e il terminal-stop host/bus senza restore USB esplicito;
D257 integra tali fatti nel lifecycle offline e riclassifica disarm/lifetime
interni come unknown epistemici non bloccanti. Il live resta non autorizzato
per la distinta freschezza/provenance current-attempt del seed.

## D250: canonicalizzazione Rocky, closure exactly-one AF e operator path

Lo snapshot operativo canonico è `Rockytkg/`, con provenance in
`Rockytkg/PROVENANCE.md`; struttura e licenze sono quelle descritte nella
sezione fonti. D250 non importa nuovo codice Rocky: riusa il serializer e il
validator GPL già registrati da D249 in `core/post_d4.py`.

L'audit primario riproducibile è
`analysis/D250/D250_af_capture_audit.json`. Nella sola sequenza locale
post-D4 esatta, il frame 136 è D4 logico 10 / OUT 64 zero-tail, il frame 138 è
l'ACK `d4/01`, il frame 140 è AF logico 13 / submission 64 e il frame 142 è AE
logico e fisico 24. La numerazione è umana 1-based; il JSON conserva gli indici
zero-based 135/137/139/141. Non esiste un frame IN non vuoto tra AF e AE. Tutte
le cinque occorrenze AF della capture hanno risposta AE diretta e submission
64; la tail AF fuori dalla lunghezza A0 dichiarata è sempre la stessa sequenza
opaca di 51 byte, con sei byte nonzero agli offset tail 27–32. Non è trattata
come payload protocollo né replayata. Il candidate invia 13 byte logici in un
buffer fisico 64 zero-initialized. D250 ha provato live l'accettazione
device-side di questa zero-tail fino a una AE strutturalmente valida; resta
`NOT_PROVEN` soltanto l'equivalenza byte-per-byte/universale con la tail OEM.
Presenza dell'ACK AF, lunghezza tail, conteggio e offset dei byte
nonzero e identità delle cinque tail sono ora derivati programmaticamente dalla
capture anziché descritti da costanti; il JSON resta redatto e l'audit fallisce
se questo profilo canonico cambia.

La DLL locale classifica `GetMcuState` come read tipizzata: control wire AF
(`AE` logico con `more=1`), body `55,ts16le,00,00`, ACK timeout zero, data
timeout 500 ms ed evento/risposta AE. Il call path OEM mostra anche `Sleep(20)`
prima della query; la capture osserva 58,365 ms da ACK D4 ad AF OUT. Il
candidate usa 20 ms host-side, timeout complessivo AF 500 ms e massimo una sola
lettura di frame. La AE strutturalmente valida deve essere A0, control `0xAE`,
checksum valido e body esattamente 16 byte. Le cinque capture OEM osservavano
byte 0 uguale a `1`, ma l'audit D251 non trova una semantica positiva né un
confronto OEM: chiamarlo “versione” e imporre `== 1` era una promozione di
un'osservazione a invariante. Byte 0 è quindi opaco. Byte 1: bit0 POV-valid,
bit1 TLS-connected e bit3 locked sono gli usi semantici verificati; ogni altro
bit è preservato come ignoto e non governa azioni ulteriori. La telemetria
D251 espone `af_state_byte0`, `af_state_flags`, `af_unknown_flag_bits`,
`af_pov_valid`, `af_tls_connected` e `af_locked`.

`ExactlyOneAfMachine` e la patch continuation mettono il latch attempt prima
della submission. Completion corta/ambigua conserva `attempt=1`, non marca
`send=1` e impedisce re-entry. Timeout, ACK AF, AE corta/lunga, control o
checksum errato, risposta duplicata coalesced e frame trailing falliscono
chiusi; un frame separato successivo resta unowned e non viene consumato perché
il budget autorizza una sola IN. Dopo AE valida il terminale è sempre
`STOP_AFTER_AF`; non esiste transizione verso FDT `32`, SetMode `20`, cached
`D2`, finger o image. Cleanup/release/secret zeroization/restore/reseal restano
quelli della catena D246 e sono verificati nel tree temporaneo.
Il modello core intercetta `Exception`, non `KeyboardInterrupt`, `SystemExit`
o le altre eccezioni di controllo processo.

La classificazione safety è corpus-bounded: AF è una query di stato fissa,
osservata nel workflow OEM e distinta dalle famiglie di write/provisioning/
firmware; non serializza address, blob o selector persistenti. Il receiver
resident APP12509 resta non disponibile, quindi non si afferma una proprietà
universale di ogni AF possibile. Rocky e Issue #1 corroborano serializer e
semantica, ma non sono la prova target-specific.

La run D250, eseguita una volta sulla baseline approvata
`44b22f21178c0083d4628ca9bbdb4ee895df40bd`, ha completato TLS e D4, inviato
AF una volta e ricevuto una A0/AE strutturalmente valida. È terminata
fail-closed nel controllo `byte0 == 1`; questo safety behavior era corretto
rispetto al contratto allora approvato, mentre il modello semantico era
sovravincolato e l'osservabilità insufficiente perché byte 0 e response count
non venivano persistiti prima del controllo. Il valore live non è recuperabile
dagli artefatti leggibili; i due report `/var/lib/.../d250-results/` non sono
leggibili senza privilegi e non è stato usato `sudo`.

```text
D250_AF_LIVE_BOUNDARY=CONSUMED
D250_CANDIDATE=EXECUTED_ONCE_TLS->D4_ONCE->ACK_D4_01->AF_ONCE->STRUCTURAL_AE->VALIDATOR_ABORT
D250_MAX_AF_IN_FRAME_COUNT=1
D250_AF_ACK_POLICY=FORBIDDEN
D250_RETRY_COUNT=0
D250_PERSISTENT_WRITE_FAMILY_COUNT=0
D250_USB_OPEN_COUNT=1
D250_AF_ZERO_TAIL_DEVICE_ACCEPTANCE=LIVE_PROVEN
D250_AF_ZERO_TAIL_STRUCTURAL_AE_RESPONSE=LIVE_PROVEN
D250_AF_ZERO_TAIL_OEM_BYTEWISE_EQUIVALENCE=NOT_PROVEN
D250_AF_LIVE_STATE_BYTE0_VALUE=LOST_BY_OBSERVABILITY_GAP
D250_AF_RESPONSE_COUNTER_DIAGNOSIS=INCREMENTED_TOO_LATE_AFTER_SEMANTIC_CHECK
D250_LIVE_EXECUTION=PERFORMED_ONCE_MARKER_CONSUMED
```

Il marker D250 non deve essere cancellato o riutilizzato. D251 ha usato
namespace e marker propri; anche il marker D251 è ora storico e consumato.

## D251: post-mortem semantica AF e candidate one-shot corretto

L'audit primario di `gfusb.dll` copre `GetMcuState` e i tre call site diretti
nel disassembly locale. La funzione acquisisce 16 byte; il codice OEM usa
byte 1 bit0 nel percorso POV, byte 1 bit1 per conferma TLS e byte 1 bit3 per lo
stato locked. Un call site usa solo l'esito della query. Nessun call site
confronta byte 0 con `1` né lo usa per una decisione. Le cinque capture OEM
restano una semplice osservazione `byte0=1`. Rocky legge/logga byte 0 ma governa
POV/TLS/locked con byte 1; è solo corroborazione.

Il parser canonico restituisce ora ogni A0/AE strutturalmente valida con body
da 16 byte e conserva byte 0 come `McuState.byte0`. Il continuation D251
incrementa `af_response_count` subito dopo questa validazione strutturale,
prima di classificare campi inusuali, e persiste byte0/flags/bit semantici. Il
report distingue `no_response`, `malformed_response`, `unexpected_ack`,
`valid_ae_with_unusual_state_fields` e `valid_ae_accepted`. Un byte0 diverso da
1 è osservabile ma non causa failure; ogni esito resta terminale. Serializer,
tail zero, pacing 20 ms, timeout 500 ms, endpoint e massimo una IN restano
invariati rispetto a D250.

Riesame metodologico pre-live D251:

1. cambia il solo validator/observability, eliminando l'invariante non provata;
2. testa l'ipotesi nuova che la AE D250 fosse protocollo valido con byte0 opaco;
3. se il D251 autorizzato fosse fallito ancora allo stesso punto, non si sarebbe
   ripetuto il probe: la telemetria completa avrebbe riportato all'audit del
   receiver/protocollo prima di qualsiasi nuovo live.

La run autorizzata sulla baseline
`f07352ce085651568a9aedbf04b097df91d7c0bb` ha validato esattamente l'ipotesi:
una sola AE strutturale con `byte0=0` è stata accettata e classificata senza
promuoverla a versione. `flags=0x02` significa TLS connected vero, POV-valid e
locked falsi, con bit ignoti zero. La run ha chiuso AF e si è arrestata prima
di qualsiasi FDT, D2, dito o immagine.

```text
D251_LIVE_RESULT=PASS
D251_AF_BOUNDARY=LIVE_PROVEN
D251_AF_ZERO_TAIL_DEVICE_ACCEPTANCE=LIVE_PROVEN
D251_AF_STRUCTURAL_AE=LIVE_PROVEN
D251_AF_STATE_BYTE0=0
D251_AF_STATE_BYTE0_SEMANTIC_CLASS=OPAQUE
D251_AF_STATE_FLAGS=0x02
D251_AF_POV_VALID=false
D251_AF_TLS_CONNECTED=true
D251_AF_LOCKED=false
D251_AF_UNKNOWN_FLAG_BITS=0
D251_RETRY_COUNT=0
D251_PERSISTENT_WRITE_FAMILY_COUNT=0
D251_APPLICATION_DATA_COUNT=0
D251_CLEANUP_RESEAL_RESTORE=PASS
D251_MARKER=CONSUMED
```

## D252: audit fresh-FDT, tabella dinamica e restore mancante

L'audit riproducibile `analysis/D252/d252_fdt_capture_audit.py` verifica la
capture target hash-gated. Le tre richieste `0x36` hanno data
`09 01 || table12`, frame logico 22 e submission fisica 64; la tail esterna al
frame conserva sei byte OEM opachi nonzero agli offset 40–45. Ognuna riceve
ACK echo `36`/status `01` e un evento IRQ `0x0100`, touch flag zero. La routine
DLL `0x180029210` valida i sei raw word e calcola ciascun word di tabella come
`((v >> 1) << 8) | 0x80`: nella capture le prime due tabelle apprese diventano
esattamente l'input del `0x36` successivo, e la terza diventa
`80ac80bd80a380b180a680b2`.

Le tre richieste `0x32` hanno data
`08 01 || 80ac80bd80a380b180a680b2 || ts16le`, frame logico 24, submission 64
con tail zero e ACK echo `32`/status `01`. Il timestamp DLL è
`wSecond*1000+wMilliseconds` troncato a 16 bit. La tabella è riusata per circa
117,45 secondi nella stessa sessione; la validità cross-session, termica o per
il cold-start D251 non è provata. Il primo seed `0x36` non è un literal in DLL,
APP o config90 e la sua provenienza/freschezza resta aperta, sebbene il DLL
abbia un possibile percorso cache host `goodix.dat` legato alla OTP.

Dopo l'unico IRQ 2 target, il successivo OUT è wire `0x22 [01 00]`, non il
`0x20` modellato in D249/Rocky. `0x34` arma invece finger-up. La routine OEM
`gfOnCancel` cancella la richiesta WDF host senza inviare direttamente un
comando A0; A2 reset-sensor e `0x70` idle non sono osservati come cleanup dopo
FDT. La capture termina dopo il terzo `0x32` senza un restore esplicito. Il
receiver APP family-3 risiede inoltre nel tratto mancante: non si osservano
write persistenti, ma non è possibile promuovere l'inferenza di modalità
volatile a prova assoluta di nonmutazione NVM.

```text
FDT_DOWN_TABLE_SOURCE=DYNAMIC_IRQ_0x100_TRANSFORM_AFTER_0x36; FIRST_0x36_SEED_PROVENANCE_UNRESOLVED
FDT_DOWN_TABLE_LIFETIME=OBSERVED_REUSED_WITHIN_ONE_CAPTURE_SESSION; CROSS_SESSION_AND_ENVIRONMENTAL_VALIDITY_NOT_PROVEN
FDT_DOWN_TABLE_TARGET_VALIDITY=TARGET_CAPTURE_SESSION_ONLY; NOT_VALIDATED_FOR_CURRENT_D251_COLD_START
FDT_DOWN_TABLE_LIVE_READY=false
FDT32_SEMANTIC_CLASS=FINGER_DOWN_DETECTION_ARMING_SENSOR_MODE
FDT32_PERSISTENCE_CLASS=NO_PERSISTENT_WRITE_PATH_OBSERVED; DEVICE_NVM_NONMUTATION_NOT_ABSOLUTELY_PROVEN
FDT36_REQUIRED_BEFORE_FDT32=YES_FOR_CURRENT_PATH_TO_OBTAIN_FRESH_TARGET_BASELINE; SAFE_LIVE_0x36_PRECONDITIONS_NOT_CLOSED
FDT36_SEMANTIC_CLASS=MANUAL_NO_FINGER_FDT_BASELINE_SAMPLING_WITH_IRQ_0x100
FDT36_PERSISTENCE_CLASS=DYNAMIC_SENSOR_BASELINE_AND_HOST_LEARNED_TABLE; NO_DEVICE_PERSISTENT_WRITE_PATH_OBSERVED; DEVICE_NVM_NONMUTATION_NOT_ABSOLUTELY_PROVEN
FDT_CANCEL_COMMAND=NOT_FOUND_OR_PROVEN
FDT_CANCEL_PRIMARY_EVIDENCE=NONE; gfOnCancel_IS_HOST_ONLY; 0x34_ARMS_FINGER_UP
FDT_RESTORE_STATE=NOT_PROVEN
FDT_RESTORE_LIVE_PROVEN_PREDECESSOR=NONE
FDT_ARM_AND_STOP_SAFE=false
NEXT_MINIMUM_LIVE_BOUNDARY=NONE
D252_LIVE_BOUNDARY=BLOCKED
D252_LIVE_EXECUTION=NOT_PERFORMED
```

Il prossimo avanzamento utile richiede nuova evidenza primaria sul seed del
primo `0x36`, sul restore device-side post-FDT e sulla distinzione `0x22/0x20`;
non una ripetizione live del percorso già noto.

## D253: dataflow seed, lifecycle post-FDT e correzione `0x22`

L'audit riproducibile `analysis/D253/d253_offline_audit.py` censisce tutte le
occorrenze prima di applicare gli invarianti attesi. Conferma esattamente tre
`0x36`, tutti logici 22 / fisici 64, con un'unica tail profile e nessuna
zero-tail target. I soli byte nonzero fuori frame sono sempre
`cb f2 e2 be fb 7f` agli offset fisici 40–45. Lo stesso residuo compare nei
tre comandi immagine `0x20`/`0x22`, mentre il buffer locale SetMode è azzerato
esplicitamente: la classificazione più forte è staging/transport residue fuori
dalla lunghezza A0, non payload. Rocky offre solo corroborazione zero-init;
l'equivalenza zero-tail `0x36` sul target non è provata e il contratto fisico
non è live-ready.

Il dataflow della globale FDT-down `0x180580818` separa due fasi. Il callback
registrato in `context+0x13d68` punta a `0x180028480` e copia 12 byte forniti
dal chiamante; è l'unico initializer pre-manual delimitato. Dopo ogni IRQ100,
`0x180029210` valida i raw word e sostituisce la globale con la trasformazione
già provata. Il chiamante del callback, la costruzione dei suoi 12 byte e il
criterio esterno che produce esattamente tre sample non sono presenti in
`gfusb.dll`. Non sono provati un default type-12, una derivazione da sei
scalari, una validazione pre-copy o la necessità fisica di un seed nonzero.

Nel corpus non è presente un file OEM `goodix.dat`. Il path DLL osservato
legge una quantità pari alla OTP, confronta quel prefisso con la OTP live e
sceglie i calibration bytes; non raggiunge direttamente la globale FDT.
Il layout Rocky con OTP/FDT/image/CRC resta fonte implementativa
corroborativa, non prova target del formato o della freschezza. Host persistence
Linux non è quindi autorizzata né classificabile come riuso sicuro.

L'audit differenziale target trova `0x20` ai pacchetti zero-based 167 e 238,
in contesti baseline/no-finger, e `0x22` al 227 immediatamente dopo IRQ2.
Tutti hanno data `01 00`, lunghezza logica 10/fisica 64, ACK con echo uguale al
control e un frame immagine B0/TLS da 7726 byte successivo. Il builder DLL
prova la decomposizione: `0x20 = cmd0 2, cmd1 0, more 0`; `0x22 = cmd0 2,
cmd1 1, more 0`. Il core corrente usa perciò `0x22` post-IRQ2; la semantica
non viene estesa oltre “variante immagine post-finger-down”.

Il lifecycle positivo catturato è
`0x32→IRQ2→0x22→image→0x34→IRQ0x0200→0x20→image→0x32`, ma non è un cancel.
Un `0x32` successivo è accettato senza restore osservato, mentre l'ultimo
`0x32` termina con la capture. Timeout, errori, close USB/TLS, deinit e service
stop non sono esposti. `gfOnCancel` resta host-only, `0x34` arma finger-up e
A2/`0x70` non compaiono come restore. La durata dell'arm, la sopravvivenza ai
close e il safe stop senza dito restano ignoti/non provati.

```text
INITIAL_FDT36_SEED_SOURCE=HOST_SUPPLIED_VIA_GFUSB_CALLBACK; ULTIMATE_SOURCE_UNRESOLVED
FRESH_BASELINE_BOOTSTRAP_CLOSED=false
GOODIX_DAT_AVAILABLE_FOR_AUDIT=false
FDT36_TARGET_OCCURRENCE_COUNT=3
FDT36_ZERO_TAIL_OBSERVED_ON_TARGET=false
FDT36_ZERO_TAIL_TARGET_EQUIVALENCE=NOT_PROVEN
FDT36_PHYSICAL_CONTRACT_LIVE_READY=false
POST_FDT_RESTORE_MODEL=NO_EXPLICIT_RESTORE; SUCCESS_CYCLE_EVENT_CONSUMPTION; STOP_FAILURE_MODEL_UNKNOWN
DEVICE_SIDE_CANCEL_COMMAND=NOT_FOUND_OR_PROVEN
FDT_ARM_SURVIVES_USB_CLOSE=UNKNOWN
SAFE_STOP_AFTER_FDT_ARM=false
CMD20_22_RELATION=CMD1_SELECTOR_0_VERSUS_1; MORE_0_FOR_BOTH
POST_IRQ2_IMAGE_COMMAND=0x22_DATA_0100
D249_FIRST_IMAGE_MODEL_STATUS=HISTORICAL_0x20_MODEL_CORRECTED_IN_CURRENT_CORE; OFFLINE_ONLY
NEXT_MINIMUM_LIVE_BOUNDARY=NONE
D253_OUTCOME=BLOCKED
D253_LIVE_BOUNDARY=BLOCKED
D253_LIVE_EXECUTION=NOT_PERFORMED
REQUIRES_EXTERNAL_EVIDENCE=true
```

Per riaprire il confine servono insieme: una traccia OEM sanitizzata da
cold-start che mostri input/chiamante del callback seed, cache e criterio del
loop; e una traccia OEM di cancel/timeout/service-stop/close subito dopo FDT
arm con verifica deterministica dello stato successivo. Un receiver/lifecycle
APP12509 provenance-valid può sostituire le parti che prova. Ripetere il live
esistente non produce questa evidenza.

## D254: audit esterno FDT, cache OEM e lifecycle

L'audit riproducibile `analysis/D254/d254_external_audit.py` pinna la fonte A
al commit `d39e34f240270bb13c3977a7fa99973c346fa81f`, verifica gli hash prima
del parsing e genera soltanto metadati sanitizzati. Il WBDI associato al
repository non appartiene a un 5125/12509: dichiara `27c6:5110`, chipid
`0x2504`, sensor type 12 e firmware `GF_ST411SEC_APP_12117`. È quindi evidenza
OEM cross-family.

Nel suo init riuscito, il file da 13520 byte viene letto, verificato CRC,
legato alla OTP e usato per NAV/image; segue la sequenza osservata
`FDT0 -> NAV -> FDT1 -> read-reg/delta -> 0x20 base image -> FDT2 -> save ->
FDT-down`. I tre seed sono `afaf...b7b7`, il learned table del passo 0 e quello
del passo 1; il learned table finale alimenta FDT-down. Il layout
`OTP64+FDT12+NAV3200+IMAGE10240+CRC4` spiega esattamente 13520 byte e rende
forte l'inferenza che il primo seed provenga dal campo FDT12 del cache, ma il
log non mostra la copia. Non è osservato un retry loop o un criterio di
convergenza: l'orchestratore completa esplicitamente gli stage 0/1/2. Il
singolo init non prova che il file sia sempre rigenerato né che il seed vari
fra sessioni. Nello stesso log, un controllo runtime `base_is_valid=0`
aggiorna image/NAV e salva di nuovo, mentre un successivo `base_is_valid=1`
termina senza altro save: il modello osservato è validate-and-refresh, non
rigenerazione incondizionata ad ogni controllo.

Il codice claimed-12509 della stessa fonte usa invece la costante
`b3b3c3c3a8a8b5b5a8a8b7b7`, fa due manual step separati da NAV, quindi
read-reg/DAC e `0x20`. Non implementa `0x32`, `0x34`, il current-target `0x22`
o un cancel device-side. Il commento “empirically verified” è una assertion
terza, non una capture. La costante non coincide col target; ciò è compatibile
con dipendenza device/config/session, ma non ne distingue la causa. README e
codice dipendono inoltre dalla plaintext PSK specifica del device, quindi le
claim di funzionamento non chiudono un percorso factory-PSK-preserving.

La capture Issue #63, hash
`5b2e9649b8acdbf93bbb19275feb32203dacc50d727ef2222d58162fbd1b63d0`,
include un descrittore `27c6:5125` ma nessun A8: firmware `UNKNOWN`. Comincia a
sessione già armata e contiene 22 `0x36`, 21 IRQ2, 22 IRQ100 e 13 IRQ200.
Tutti i 21 IRQ2 sono seguiti da `0x22 [01 00]`. I `0x36` sono A0 logici da 22
byte in OUT fisici da 64, con nonzero fuori frame solo agli offset 40–45:
`cb f2 ca 66 f8 7f`, diverso dal target `cb f2 e2 be fb 7f`. Questo corrobora
la natura di staging residue, non l'equivalenza zero-tail. La capture mostra
solo cicli positivi; termina su IRQ200 dopo `0x34` e non prova cancel, timeout,
close o restore.

Rocky rimane l'asse APP12508: il suo campionatore accetta il primo IRQ100
valido entro al massimo tre tentativi, usa seed zero/cache, `0x20` post-IRQ2 e
un flag di cancel host-side. Non equivale ai tre stage OEM WBDI né al target.
La matrice D254 completa classifica ogni cella come target capture, OEM cross-
family, third-party code/capture o unknown.

```text
EXTERNAL_A_WBDI_EVIDENCE_CLASS=CROSS_FAMILY_OEM_LIFECYCLE_EVIDENCE_5110_APP12117
EXTERNAL_12509_FDT_SEED=b3b3c3c3a8a8b5b5a8a8b7b7
EXTERNAL_12509_SEED_MATCH_LOCAL_TARGET=false
ISSUE63_FIRMWARE=UNKNOWN
ISSUE63_FDT36_COUNT=22
ISSUE63_POST_IRQ2_IMAGE_COMMAND=0x22_DATA_0100_FOR_ALL_21_OBSERVED_IRQ2_EVENTS
EXTERNAL_OEM_FDT_PASS_MODEL=FIXED_THREE_SUCCESSFUL_NAMED_STAGES_IN_OBSERVED_INIT
EXTERNAL_OEM_INITIAL_SEED_SOURCE=BASEFILE_FDT12_STRONGLY_INFERRED; DIRECT_COPY_NOT_LOGGED
BOOTSTRAP_BLOCKER_REDUCED=true
BOOTSTRAP_CLOSED=false
RESTORE_BLOCKER_REDUCED=false
RESTORE_CLOSED=false
D254_OUTCOME=BLOCKED
NEXT_MINIMUM_LIVE_BOUNDARY=NONE
D254_LIVE_BOUNDARY=BLOCKED
D254_LIVE_EXECUTION=NOT_PERFORMED
```

La singola acquisizione con massimo valore è una capture Windows APP12509
sanitizzata che inizi dal cold-start e mostri validazione cache e sorgente del
primo seed, poi prosegua fino a `0x32`, cancel operatore senza dito e re-entry
deterministica. Non è una sequenza Linux live proposta.

## D255: acquisizione Windows APP12509 e recovery offline

La ricostruzione storica distingue fatti e lacune. Il file
`rilevamento.pcapng`, hash `50071c0f...19c184b`, usa linktype USBPcap; manuale
ed evidence index lo classificano come cold attach e citano una seconda
capture indipendente ora perduta. `GoodixExport.zip` ne ha preservato il file
insieme a `gfusb.dll` e componenti OEM. Non sono invece preservati comando di
capture, versione Wireshark/USBPcap, prodotto VM, comando di passthrough o path
del log. Non è quindi provato il locus esatto del vecchio collector.

Il metodo poi eseguito avvia TShark sull'interfaccia USBPcap esplicita nel
guest Windows mentre il target è ancora assente; solo dopo i marker
`CAPTURE_PROCESS_STARTED` e `CAPTURE_STARTED` l'operatore usa il normale attach
GUI già revisionato. Entrambi significano processo TShark attivo e target
ancora assente, non file già creato/non vuoto o frame acquisiti. È
preferito al restart di Windows Biometric Service, che non è dimostrato come
trigger dell'intero init, e al disable/enable PnP, meno conservativo. Nessun
wrapper host è stato inventato in assenza di un hypervisor canonico. Il cold
attach è un normale lifecycle OEM con rischio Windows basso ma non nullo; le
capture storiche e l'assenza di azioni maintenance sostengono il confine
factory-preserving, senza costituire prova assoluta di nonmutazione NVM interna.

La prima review AI-PM ha respinto il kit iniziale come non eseguibile/correlabile:
`SHA256.HashData`, `Convert.ToHexString` e `Path.GetRelativePath` non possono
essere assunte su Windows PowerShell 5.1/.NET Framework, e `_oem_timestamp()`
accettava solo ISO-8601 nonostante il corpus D254 esponga timestamp Goodix
`[MMDD-HH:MM:SS:mmm]`. Quella baseline non è autorizzabile per hardware.

La revisione correttiva di
`operator_kit/d255-windows-evidence-capture.ps1` usa ora
`SHA256.Create()`/`ComputeHash()`/`BitConverter` e un helper relativo basato su
`Path.GetFullPath`, separatore normalizzato e confronto
`OrdinalIgnoreCase`; `C:\run2` non può essere accettato come figlio di
`C:\run`. Il nuovo `-SelfTestOnly`, distinto da `-PreflightOnly`, non richiede
target, autorizzazione o TShark e controlla runtime, SHA-256 KAT, path relativo,
sibling rejection, clock/JSON e collisioni con hardware action count zero.

La seconda review AI-PM ha individuato un difetto ulteriore nello stesso
boundary: il launcher assumeva recognition, mentre
`CURRENT_WINDOWS_VM_FINGERPRINT_ENROLLMENT=NOT_COMPLETED` e la disponibilità di
quel prompt non è provata. La storia nativa/operativa precedente non viene
promossa a stato della VM corrente. D175 viene usato soltanto come evidenza di
cold attach passivo e init OEM automatico senza Hello o dito; l'UI esatta della
capture sopravvissuta `rilevamento.pcapng` non è canonicamente preservata.

La terza review AI-PM ha respinto anche il requisito del vero wizard fingerprint
pre-attach e l'equivalenza implicita re-entry→restore. Windows Hello Fingerprint
è sensor-dependent: con Goodix assente dal guest il relativo controllo può
essere nascosto, indisponibile o non configurabile anche se funzionerebbe dopo
l'attach. Inoltre A8 o nuovo `0x32` accettato nella seconda sessione non
osservano necessariamente il disarm del prior arm. Questa è la decisione
canonica corrente, non un limite cosmetico del launcher.

Nel ramo one-shot eseguito, la VM Windows era già avviata e il Goodix restava visibile
sull'host Linux ma assente dal guest. Il preflight verifica soltanto
Sign-in-options/account-level: enrollment `NOT_COMPLETED`, nessuna creazione o
modifica PIN, e `WINDOWS_HELLO_PIN_STATE` in
`ALREADY_CONFIGURED|NOT_CONFIGURED|UNKNOWN|NOT_REQUIRED_BY_CURRENT_ACCOUNT_POLICY`.
Se policy setup=`REQUIRED` e PIN=`NOT_CONFIGURED`, il run fallisce prima
dell'autorizzazione. La disponibilità UI fingerprint resta
`UNKNOWN_BEFORE_ATTACH`. Se TShark vede una sola interfaccia USBPcap la selezione
è univoca; se ne vede più di una, il launcher richiede la capture simultanea di
tutte o fallisce `USBPCAP_INTERFACE_SELECTION=AMBIGUOUS`.

Solo dopo questi gate si scrive `authorization_consumed.json` e si tenta
TShark. Il launcher prova il processo attivo e di nuovo l'assenza del target,
senza usare la materializzazione del pcapng come gate pre-attach, poi presenta
una sola azione
`OPERATOR_ACTION_VM_USB_ATTACH`; non contiene attach/detach automatico. Un
failure di start dopo il record consuma il run. Il postprocessor richiede che
il descriptor `27c6:5125` compaia dopo `CAPTURE_STARTED`, entro i marker
`VM_USB_ATTACH_BEGIN/END`, su un solo bus/device, e che l'A8 byte-exact
`GF_ST411SEC_APP_12509` preceda `PASSIVE_BOOTSTRAP_SETTLED` e il successivo gate
UI. Descriptor pre-capture,
assenza di enumerazione, secondo device/attach o topology change invalidano la
provenance bootstrap. Lo script non invoca service restart, PnP mutation, VM,
provisioning, flash o comandi Goodix. Il cache discovery resta ristretto a root
Goodix e a size/naming pertinenti.

`analysis/D255/d255_postprocess_windows_evidence.py` opera solo su path privati
hash-gated, canonicamente sotto `captures/`. Seleziona il device tramite A8 esatto, ricostruisce A0/B0 senza
esportare payload, misura il contratto fisico `0x36`, valida l'ipotesi
`OTP64+FDT12+NAV3200+IMAGE10240+CRC4`, confronta solo FDT12 e hash di regioni,
e censisce la finestra ultimo `0x32` → cancel → re-entry. La UI sensor-dependent
è verificata soltanto post-attach/A8/bootstrap con una scelta strutturata:
`READY_WAITING_FOR_FINGER`, `UI_UNAVAILABLE`, `NEW_PIN_REQUIRED` o
`UNEXPECTED_PREREQUISITE`. Solo READY prosegue con due attese e due
cancellazioni, sempre senza dito, enrollment o modifica PIN. Nella finestra
`OEM_WAITING_NO_FINGER` → `REENTRY_CANCEL_END`, il sanitizer censisce IRQ
finger-down `0x0002`, exact `0x22 [01 00]` e image-sized B0; qualunque occorrenza
produce `INVALID_FINGER_INTERACTION` e forza `RESTORE_CLOSED=false`.
Il launcher conserva
local-only snapshot OEM before/after con path, size, hash e mtime; il parser usa
come nuova finestra soltanto un append byte-prefix verificato e distingue
`UNCHANGED`, `GREW`, `TRUNCATED` e `REPLACED_OR_ROTATED`.

Il preflight reale della VM ha dimostrato che questa raccolta non può assumere
l'esistenza del log: `C:\ProgramData\Goodix` contiene cache Goodix leggibili,
ma nessun `goodix*.log` o `wbdi*.log` nelle directory candidate. Il vecchio
`no readable OEM/WBDI log source was identified` bloccava quindi un caso reale
senza ridurre rischio device-side. `D255_WINDOWS_PREFLIGHT_V4` accetta zero
candidate log e riporta separatamente `OEM_LOG_STATUS`,
`OEM_LOG_SOURCE_COUNT`, `GOODIX_CACHE_STATUS` e
`GOODIX_CACHE_SOURCE_COUNT`. Quando presenti, log e cache continuano a essere
snapshot before/after; un path esplicito illeggibile resta fail-closed. Gli
snapshot vuoti sono array JSON validi. Il postprocessor accetta l'assenza di
log, conserva l'analisi wire/cache e marca la correlazione temporale
`UNAVAILABLE_NO_OEM_LOG`, senza promuovere restore o causalità.

La prima invocazione live successiva, pur autorizzata dall'operatore sulla
baseline `74a1ebda24166ac026ef7ed55c15f0d21e4593e3`, ha esposto una distinzione
PowerShell non coperta dal solo preflight: il parametro mandatory
`Write-OemLogSnapshot.Candidates` non accettava l'array vuoto e il binder ha
generato `ParameterArgumentValidationErrorEmptyArrayNotAllowed` prima di
entrare nella funzione. Il ramo aveva già creato directory e marker locali, ma
non aveva ancora raggiunto il confronto di autorizzazione, l'assegnazione
`$script:AuthorizationConsumed = $true`, `authorization_consumed.json` o
`Start-Process`; risultano quindi autorizzazione non consumata, capture non
avviata, zero attach, zero USB open e zero azioni hardware.

Una run seguente sulla baseline approvata
`999483362af23f67790eb6e54f4c02bb48bd6cd5` ha invece consumato
l'autorizzazione e avviato TShark, poi ha prodotto
`D255_FAIL_CLOSED: capture process is alive but output file was not created`
al controllo fisso dei due secondi. Il Goodix non è stato collegato alla VM e
non è avvenuta alcuna azione sul sensore. Il successivo pcapng zero-byte con
timestamp di diversi secondi posteriore prova la race host-side del gate. La
futura run richiede review AI-PM, approvazione di un nuovo SHA live-critical e
una nuova autorizzazione esplicita; quella consumata non è riutilizzabile.

La run successiva sulla baseline approvata
`f01b81d629ffe8af5eecb92ca93968045d5345ce` ha invece completato l'intero
percorso operatore senza dito. La capture canonica è
`captures/D255_20260822T205631772Z_85c8c41f/raw/wire.pcapng`: 27.684 byte,
218 frame leggibili, `FIRST_FRAME=1`, SHA-256
`802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c`.
Tutti i marker da `CAPTURE_PROCESS_STARTED` a `OPERATOR_PHASES_COMPLETE` sono
presenti una volta e ordinati. Il failure finale
`HOST_SIDE_TSHARK_EXITCODE_NULL_OR_UNAVAILABLE` è il bug noto di Windows
PowerShell 5.1 per processi `Start-Process -PassThru` con `-NoNewWindow` e
stream rediretti: dopo `Wait-Process`, il wrapper può non esporre l'ExitCode
anche se `HasExited=true`. Il launcher conserva ora anticipatamente l'handle e
tratta l'ExitCode come nullable. Zero numerico più pcap valido produce `PASS`;
null più processo terminato, file presente/non vuoto e almeno un frame
leggibile produce `PASS_WITH_EXIT_CODE_UNAVAILABLE`; non-zero, processo ancora
attivo o pcap invalido restano `FAIL_CLOSED`. Stdout/stderr rimangono soltanto
diagnostica e non sostituiscono la prova di leggibilità.

`analysis/D255/d255_recover_existing_run.py` ha finalizzato la run interamente
offline con `REAL_USB_OPEN_COUNT=0`, `REAL_CAPTURE_COUNT=0`,
`REAL_HARDWARE_ACTION_COUNT=0` e `RAW_PCAP_MODIFIED=false`. Il recovery
manifest SHA-256 è `deb08f42...dcedaa`. Gli snapshot after e il manifest
originale mai creati restano `NOT_RECOVERABLE`; il postprocessor distingue
`ORIGINAL_ARTIFACT`, `RECOVERED_ARTIFACT` e `NOT_RECOVERABLE`. L'esecuzione
reale del postprocessor passa: target APP12509, cold attach valido,
`VALID_ZERO_FINGER`, tre `0x36`, primo seed
`aeaebfbfa4a4b2b2a7a7b3b3` uguale all'FDT12 del cache before, re-entry e nuovo
arm accettato. Non prova causalità del seed né disarm del prior arm; senza log
OEM e snapshot after la closure restore resta inconclusiva e soggetta a review
AI-PM. `NEW_LIVE_CAPTURE_REQUIRED=false`.

Il riesame metodologico che precedette quella run era:

1. cambia la semantica della readiness, da file creato entro due secondi a
   processo TShark vivo più target ancora assente, con materializzazione
   post-attach e validazione finale forte;
2. testa l'ipotesi nuova che il failure osservato fosse soltanto ritardo
   host-side di creazione/buffering del pcapng con processo sano;
3. se il failure ricorre nello stesso punto, non si ripete il live: si conserva
   la diagnostica redatta e si studia TShark/USBPcap nativo con un riproduttore
   Windows senza hardware prima di proporre un metodo diverso.

L'audit orizzontale delle collezioni separa i casi semanticamente vuoti da
quelli non vuoti. `OemLogPath`, candidate OEM, `CacheRoot`, roots/file cache e
le corrispondenti collezioni del setup condiviso possono legittimamente essere
vuoti e ora espongono un contratto `AllowEmptyCollection`; un helper dedicato
scrive `[]` senza affidarsi a un secondo binding vuoto di `ConvertTo-Json`.
`CaptureInterface`, candidate USBPcap e match dei selettori non possono invece
essere vuoti nel percorso live: mantengono failure espliciti, univocità o
capture-all. Le collezioni UI/marker sono enumerazioni interne fisse o output
naturalmente vuoti e non espongono un parametro mandatory problematico.

Il setup log/cache/runtime/preflight/argomenti di cattura è ora una funzione
unica chiamata sia dal live sia da `-PreAuthorizationSimulationOnly`. La
simulazione vieta autorizzazione, TShark, interfacce e path reali, usa fixture
sintetiche ABSENT/PRESENT e si arresta prima del consumo/autorizzazione e di
`Start-Process`, con contratto atteso:

```text
EMPTY_OEM_LOG_CANDIDATES_BINDING=PASS
EMPTY_CACHE_ROOTS_BINDING=PASS
AUTHORIZATION_CONSUMED=false
REAL_CAPTURE_STARTED=false
REAL_USB_OPEN_COUNT=0
REAL_HARDWARE_ACTION_COUNT=0
```

Non sono stati rimossi altri gate pre-autorizzazione: assenza/topologia guest,
chiusura selezione USBPcap, prerequisiti account/PIN, leggibilità dei path
espliciti, runtime, collisione/spazio output, autorizzazione esatta e prova di
processo TShark attivo riducono rischio device-side, perdita di provenance o
failure operativi reali. Il requisito obbligatorio del log OEM e quello del
pcapng già creato entro due secondi erano gate host-side non probanti e restano
eliminati. Il deadline PnP post-attach e la durata bounded restano perché
proteggono rispettivamente enumerazione reale e contenimento della capture.

Ogni evento OEM sanitizzato espone sorgente timestamp, UTC e qualità, mai la
linea raw. ISO-8601 con offset/Z è diretto; Goodix MMDD viene convertito solo se
anno del run, offset locale, Windows timezone, anchor start/end e marker UTC
selezionano un istante unico. Stesso giorno, mezzanotte e fine anno non ambigua
sono supportati; cambio offset/DST, data malformata o fuori finestra e rotazione
non ricostruibile restano `AMBIGUOUS`. Eventi critici cancel/restore non
correlabili impongono `RESTORE_MODEL=INCONCLUSIVE_OEM_TIME_CORRELATION` e non
promuovono `CANCEL_IS_HOST_ONLY` o `USB_CLOSE_AFTER_CANCEL`.

Se la UI non è ready, il run consumato termina senza cancel/re-entry e lascia
scadere il timer bounded; processo terminato, ExitCode zero oppure non
disponibile, file non vuoto e readback di un frame validano il pcapng prima
degli snapshot after e del manifest. Un ExitCode numerico non-zero resta
terminale. Il postprocessor
accetta `PARTIAL_BOOTSTRAP_ONLY_UI_UNAVAILABLE` senza marker cancel ma conserva
descriptor/A8, cache, primo `0x36` e profilo fisico. Produce
`BOOTSTRAP_EVIDENCE_PRESERVED=true`, `RESTORE_EVIDENCE_ACQUIRED=false` e
`RESTORE_CLOSED=false`.

Nel ramo full occorre distinguere quattro fatti: la fase cancel operatore è
completata; la cancellazione della richiesta host è osservata in D256 tramite
una completion bulk-IN cancellata; il disarm device-side non è provato; la
re-entry e il nuovo `0x32` accettato sono provati. La vecchia scorciatoia
`OEM_CANCEL_REENTRY_PROVEN` non va usata come sinonimo di questi quattro
concetti. `PRIOR_ARM_LIFETIME_AFTER_CANCEL=UNOBSERVED` e la sola re-entry non
promuove `RESTORE_CLOSED`; prova invece che un restore USB esplicito non è un
prerequisito osservato per la continuazione/re-arm. L'uguaglianza wire/cache/log
resta correlazione, mai automaticamente causalità. Un A8 assente/diverso rende
l'evidenza non target-specific e terminale; marker/formati inattesi e collisioni
falliscono chiusi senza retry.

I 56 test D255 passano. Oltre alle coperture storiche includono i quattro casi
di finalizzazione TShark — ExitCode 0, ExitCode nullo con pcap valido, ExitCode
nullo con pcap assente/vuoto/illeggibile e ExitCode non-zero — e il recovery
end-to-end su fixture incompleta con hash e mtime raw invariati. La run reale è
stata recuperata e postprocessata offline con successo. `pwsh` non è installato
sull'host Linux: il nuovo handle-caching non è stato rieseguito su Windows
PowerShell 5.1 dopo la patch, ma l'osservazione nativa della run e il bug runtime
documentato chiudono la causa; la semantica nullable è coperta offline e non
richiede una nuova capture.

```text
D255_INITIAL_AI_PM_REVIEW=FAIL_EXECUTABILITY_AND_TIME_CORRELATION
D255_SECOND_AI_PM_REVIEW=FAIL_CURRENT_VM_RECOGNITION_PATH_ASSUMPTION
D255_THIRD_AI_PM_REVIEW=FAIL_PREATTACH_SENSOR_UI_GATE_AND_RESTORE_OVERCLAIM
D255_REAL_PREFLIGHT_OBSERVATION=FAIL_UNPROVEN_OEM_LOG_REQUIREMENT
D255_PRIOR_LIVE_PATH_OBSERVATION=FAIL_PARAMETER_ARGUMENT_VALIDATION_EMPTY_ARRAY_BEFORE_AUTHORIZATION
D255_LATEST_LIVE_PATH_OBSERVATION=CAPTURE_ACQUIRED_FINALIZATION_FAILED_EXITCODE_UNAVAILABLE
D255_LATEST_RUN_AUTHORIZATION_CONSUMED=true
D255_LATEST_RUN_TSHARK_STARTED=true
D255_LATEST_RUN_GOODIX_ATTACHED_TO_VM=true
D255_LATEST_RUN_OPERATOR_PHASES=COMPLETED_ZERO_FINGER
D255_CORRECTIVE_STATUS=RECOVERED_READY_FOR_AI_PM_REVIEW
D255_OUTCOME=CAPTURE_ACQUIRED_RECOVERED_AND_POSTPROCESSED_OFFLINE
D255_OEM_LOG_REQUIREMENT=OPTIONAL_REPORTED_PRESENT_OR_ABSENT
D255_GOODIX_CACHE_REQUIREMENT=OPTIONAL_REPORTED_PRESENT_OR_ABSENT
D255_WINDOWS_EXECUTION_ENVIRONMENT=VIRTUAL_MACHINE
D255_VM_USB_ATTACH_METHOD=OPERATOR_GUI_MANUAL_ATTACH
D255_CURRENT_WINDOWS_VM_FINGERPRINT_ENROLLMENT=NOT_COMPLETED
D255_SELECTED_WINDOWS_UI_PATH=WINDOWS_HELLO_SETUP_NO_FINGER
D255_SENSOR_DEPENDENT_UI_AVAILABILITY_BEFORE_ATTACH=UNKNOWN_BEFORE_ATTACH
D255_PARTIAL_BOOTSTRAP_RESULT_SUPPORTED=true
D255_REENTRY_ALONE_CAN_CLOSE_RESTORE=false
D255_FINGER_INTERACTION_ALLOWED=false
D255_LIVE_PATH_ATTEMPT=COMPLETED_OPERATOR_PHASES_FINALIZATION_FALSE_FAILURE
D255_LIVE_CAPTURE=SUCCEEDED
D255_CAPTURE_BYTES=27684
D255_CAPTURE_FRAME_COUNT=218
D255_FIRST_FRAME=1
D255_CAPTURE_SHA256=802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c
D255_NEW_RUN_REQUIRED=false
FUTURE_LIVE_OPERATOR_AUTHORIZATION_REQUIRED=true
D255_AUTHORIZATION_CONSUMED_AFTER_PRE_HARDWARE_SETUP=true
D255_TSHARK_PREATTACH_READINESS=PROCESS_STARTED_AND_ALIVE_TARGET_ABSENT
D255_PREATTACH_PCAP_FILE_REQUIRED=false
D255_FINAL_PCAP_VALIDATION=PROCESS_EXITED_AND_EXIT_ZERO_OR_UNAVAILABLE_AND_EXISTS_NONEMPTY_READABLE_FRAME
D255_RECOVERY_RESULT=PASS_RECOVERED_READY_FOR_OFFLINE_POSTPROCESSING
D255_POSTPROCESS_RESULT=PASS
D255_POST_CAPTURE_STATE_SNAPSHOT=NOT_RECOVERABLE_RETROACTIVELY
D255_PRIVATE_EVIDENCE_CANONICAL_LOCATION=captures/
D255_NEW_LIVE_CAPTURE_REQUIRED=false
D255_EMPTY_OEM_LOG_CANDIDATES_SUPPORTED=true
D255_EMPTY_ARRAY_CLASS_AUDIT=PASS
D255_SHARED_PREAUTHORIZATION_SIMULATION=HISTORICAL_NOT_REQUIRED_FOR_RECOVERY
D255_REPEAT_FORBIDDEN_WITHOUT_NEW_AUTHORIZATION=true
READY_FOR_AI_PM_REVIEW=true
READY_FOR_OPERATOR_RUN=false
BOOTSTRAP_CLOSED=false
RESTORE_CLOSED=false
```

## D256: contratto USB lifecycle osservato nella capture D255

L'audit riproducibile
`analysis/D256/d256_usb_lifecycle_contract_audit.py` riusa il parser pcapng
D255, verifica prima del parsing path, SHA-256, 27.684 byte, 218 frame e primo
frame `1`, quindi produce una timeline sanitizzata di tutti i 206 packet
USBPcap del target `bus 1 / device 2`. Hash, size e mtime del raw restano
invariati; nessun payload USB, OTP, PSK, cache raw o materiale biometrico entra
nei derivati.

La finestra critica inizia dal `0x32` frame 198, ACKato prima del marker cancel.
Tra `CANCEL_NO_FINGER_BEGIN` e `CANCEL_NO_FINGER_END` non compare alcun packet
target. Dopo `REENTRY_BEGIN` il frame 202 completa con
`USBD_STATUS_CANCELED` una bulk-IN pendente: è prova di cancellazione della
richiesta host, non un comando device-side. Fino al nuovo `0x32` frame 214 e al
suo ACK frame 216 compaiono soltanto URB function `0x0009`; non si osservano
abort/reset pipe, clear-stall, control transfer, select configuration/interface,
descriptor replay o re-enumeration. Il target resta `1:2` sugli endpoint bulk
`0x01/0x81`.

Il corrective dello stesso D256 separa la seconda cancellazione terminale.
Il nuovo arm/ACK e la bulk-IN pendente sono rispettivamente ai frame
`214/216/217`. Fra `REENTRY_CANCEL_BEGIN` e `REENTRY_CANCEL_END` non compare
alcun packet, target o totale. Dopo `REENTRY_CANCEL_END` non passa traffico
prima del frame `218`, unica completion bulk-IN `0x81` con
`USBD_STATUS_CANCELED`; il frame `218` è anche l'ultimo del raw. Non esistono
quindi packet target o totali successivi. TShark dichiara `218 packets
captured`, la durata configurata è 600 secondi e il marker host finale cade
602,543790 secondi dopo `CAPTURE_PROCESS_STARTED`: la capture è rimasta bounded
fino al duration boundary senza ricevere altro traffico. La distanza
frame-218→marker `RUN_FAILED` è 491,125998 secondi; l'exact process-exit
timestamp non è disponibile e `RUN_FAILED` non è trattato come evento USB.

```text
USBPCAP_LIFECYCLE_AUDIT=PASS_COMPLETE_TARGET_PACKET_TIMELINE
CANCEL_TO_REENTRY_DEVICE_CONTINUITY=SAME_BUS_DEVICE_AND_BULK_ENDPOINTS
HOST_SIDE_PENDING_BULK_IN_CANCELLATION_OBSERVED=true
EXPLICIT_USB_RESTORE_OBSERVED=false
ABORT_OR_RESET_OBSERVED=false
REENUMERATION_OBSERVED=false
REENTRY_WITHOUT_EXPLICIT_USB_RESTORE_PROVEN=true
NEW_FDT_ARM_ACCEPTED_ON_REENTRY=true
RESTORE_REQUIRED_FOR_REENTRY=false
PRIOR_ARM_DISARM_PROVEN=false
PRIOR_ARM_LIFETIME_AFTER_CANCEL=UNOBSERVED
TERMINAL_CANCEL_PENDING_BULK_IN_CANCELED=true
EXPLICIT_USB_TERMINAL_RESTORE_OBSERVED=false
TERMINAL_CANCEL_ABORT_OR_RESET_OBSERVED=false
TERMINAL_CANCEL_REENUMERATION_OBSERVED=false
POST_TERMINAL_CANCEL_CAPTURE_WINDOW_SECONDS=491.125998
POST_TERMINAL_CANCEL_TARGET_USB_PACKET_COUNT=0
POST_TERMINAL_CANCEL_TOTAL_PACKET_COUNT=0
OEM_TERMINAL_CANCEL_USB_QUIESCENCE_PROVEN=true
DEVICE_INTERNAL_FDT_STATE_AFTER_CANCEL=UNOBSERVED
```

`RESTORE_REQUIRED_FOR_REENTRY=false` è rigorosamente path-bounded: il nuovo arm
è stato accettato senza restore USB esplicito osservato. Non implica che il
prior arm sia stato disarmato o che ogni restore sia inutile. Separatamente,
`OEM_TERMINAL_CANCEL_USB_QUIESCENCE_PROVEN=true` chiude il contratto host/bus
del secondo cancel sul path osservato: la richiesta pendente è cancellata e il
bus resta silente fino alla chiusura della capture. Non prova disarm, expiry o
clear del mode FDT interno.

Il vecchio `SAFE_STOP_AFTER_FDT_ARM=UNRESOLVED` è superato dalla scomposizione:
contratto host/bus terminal-stop chiuso, quiescenza USB provata, stato interno
e lifetime non osservati, nessuna nuova implicazione factory-persistence
device-side derivata dal silenzio USB. Le classi URB di audit comprendono ora
anche `0x0002` abort pipe, `0x001e` sync reset-and-clear-stall, `0x0030` sync
reset pipe e `0x0031` sync clear-stall. Nessuna compare nella finestra reale,
quindi la robustezza del parser non cambia l'esito empirico. Sul corrente host
offline non sono installati header WDK, sorgenti Wireshark o TShark: il check
locale indipendente della nomenclatura resta dichiarato indisponibile e non è
stata usata la rete.

I control D255 `0x50` e `0x97` non sono nuovi: il census D230 classificava già
`0x50` come famiglia sensor/mode a semantica esatta irrisolta e mappava wire
`0x97` al builder `SetDriverState` logico `0x96`. D255 contiene un solo `0x50`,
frame 150, A0 logico 10/fisico 64, ACK `B0/50/01` e una A0/50 lunga seguente;
è nel bootstrap fra primo e secondo `0x36`. Contiene un solo `0x97`, frame 40,
A0 logico 10/fisico 64 senza ACK/response prima del successivo OUT, nella
sequenza iniziale pre-TLS. Nessuno compare nella finestra cancel/re-entry o
fornisce evidenza di restore. La lista `unknown_controls` D255 rifletteva
quindi una allowlist locale incompleta, non una nuova semantica protocollo.

La verifica statica severamente bounded conferma nel solo slice già noto che
`gfOnCancel` non chiama direttamente i builder A0. Le stringhe D0 già censite
non provano che D0Exit/D0Entry siano avvenuti nella run; non emerge un nuovo
dataflow USB e
`STATIC_LIFECYCLE_CORROBORATION=EXHAUSTED_NO_NEW_DATAFLOW`.

Il claim bootstrap massimo resta separato: il cache `goodix.dat` da 13.520
byte ha layout/CRC validi, è OTP-bound al target e il suo FDT12 uguaglia il
primo seed wire nella cold attach D255. La correlazione host/cache/wire è
provata, ma non il dataflow causale della callback né freschezza/lifetime
generali.

```text
BOOTSTRAP_CACHE_LAYOUT_TARGET_VALID=true
BOOTSTRAP_CACHE_OTP_BOUND=true
BOOTSTRAP_CACHE_FDT12_EQUALS_FIRST_WIRE_SEED=true
BOOTSTRAP_SEED_SOURCE_CORRELATED=true
BOOTSTRAP_SEED_DATAFLOW_CAUSALITY_PROVEN=false
BOOTSTRAP_SEED_FRESHNESS_SCOPE=FIRST_0x36_IN_THIS_D255_COLD_ATTACH_ONLY; GENERAL_LIFETIME_UNPROVEN
CURRENT_CORPUS_EXHAUSTED_FOR_REENTRY_RESTORE_QUESTION=true
CURRENT_CORPUS_EXHAUSTED_FOR_INTERNAL_ARM_LIFETIME_QUESTION=true
```

Il risultato strategico è il Caso A: non manca più una componente osservabile
del terminal stop host/bus nel corpus corrente; restano non osservabili lo stato
volatile FDT e la lifetime del prior arm. Una review futura può separare i
requisiti factory-preserving/compatibilità Windows, internal disarm e
live-readiness FDT. D256 è interamente offline, non autorizza FDT live, non
richiede una capture equivalente e non crea un operator kit. Il bundle D256
precedente è `SUPERSEDED_BY_D256_TERMINAL_CANCEL_CORRECTIVE`; il blob storico
resta preservato dalla history Git.

## D257: corrective exact fresh-bootstrap

D257 resta esclusivamente offline e conserva il provider cache esplicito
GPL-2.0-or-later: path fornito dal chiamante, lettura stabile e read-only,
layout OTP64 + FDT12 + NAV3200 + IMAGE10240 + CRC4 = 13.520 byte, CRC-32/MPEG-2
little-endian e binding constant-time all'identità OTP64. Assenza, layout, CRC,
binding o FDT12 non validi falliscono chiusi; non esistono fallback, derivazione
da PSK o scrittura della cache.

Il corrective ricalcola dal raw D255 hash
`802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c`
l'intero segmento logico dalla coppia fresh AF/AE fino all'ACK del primo
successivo `0x32`, senza preselezionare soltanto i frame FDT:

```text
0x36/ACK/IRQ100
0x50/ACK/NAV dinamico
0x36/ACK/IRQ100
0x82/ACK/risposta a due byte
0x20/ACK/baseline B0 cifrata
0x36/ACK/IRQ100
0x32/ACK
```

Il replay pre-corrective dei tre `0x36` e del contratto cancel/re-entry D256
resta `PROJECTED_FDT_SUBSEQUENCE_REPLAY=PASS_HISTORICAL`, ma non costituisce
`EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY`. Il `0x50 [01 00]` produce una risposta
NAV A0/`0x50` dinamica da 2.417 byte; l'interstage `0x82
[00 82 00 02 00]` legge due byte dal registro `0x0082`; `0x20 [01 00]`
produce la baseline/image B0 cifrata da 7.726 byte prima del terzo `0x36`.
D254 corrobora cross-family un lifecycle NAV/read-reg/baseline, ma non prova i
predicati APP12509. La necessità causale non è esclusa: tutti e tre gli stage
sono obbligatori nel candidate esatto e i gate host su NAV, delta e baseline
decifrata sono input dinamici, non blob D255 hardcoded. Poiché i predicati
target non sono derivabili dal raw, il replay esatto fallisce chiuso al primo
gate assente.

`core/fdt_lifecycle.py` distingue ora il modello storico proiettato dal
candidate esatto con ordine `36,50,36,82,20,36,32`. Sul primo `0x36` il latch
precede la submission, il massimo è un tentativo, il timeout contrattuale è
100 ms e avanzano solo ACK `36/01`, IRQ `0x0100` con touch zero e transform/
validator della tabella. Ogni errore ferma nuovo traffico, cancella una receive
pendente se presente e completa il cleanup host terminale. Non esistono retry,
A2, `0x70` o famiglie persistenti. Un test negativo prova che ACK errato lascia
un solo request/attempt e impedisce una seconda submission; un test sintetico
positivo prova l'ordine completo soltanto come proprietà implementativa.

La provenance temporale D255 è anch'essa ricalcolata programmaticamente:

```text
CACHE_MTIME_UTC=2026-08-22T20:29:28.5244390Z
VM_ATTACH_BEGIN_UTC=2026-08-22T20:56:34.7220147Z
FIRST_0x36_UTC=2026-08-22T20:56:44.146639Z
CACHE_MTIME_TO_ATTACH_BEGIN_SECONDS=1626.1975757
CACHE_MTIME_TO_FIRST_0x36_SECONDS=1635.6222000
SAME_ATTACH_SEED_GENERATION_REQUIRED=false
PERSISTED_PRE_ATTACH_CACHE_REUSE_PROVEN=true
GENERAL_CACHE_TTL_PROVEN=false
```

I delta dal mtime non sono chiamati “seed age”, perché mtime e generation time
non sono provati equivalenti. D255 prova però il riuso riuscito di un cache
persistente OTP-bound e CRC-valid che precedeva l'attach di oltre 27 minuti e
il cui FDT12 coincide con il primo seed wire. La correlazione post-hoc dello
stesso tentativo sarebbe un gate pre-run circolare e non è richiesta per la
factory-preservation: nessuna famiglia persistente è raggiungibile e un input
invalido fallisce al primo ACK/evento/gate. La TTL generale resta ignota come
rischio di successo funzionale, non come blocker factory-preservation.

```text
PROJECTED_FDT_SUBSEQUENCE_REPLAY=PASS_HISTORICAL
EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY=BLOCKED_DYNAMIC_HOST_GATES_NOT_DERIVABLE_FROM_D255_RAW
FDT_OFFLINE_CANDIDATE_CLOSED=false
HOST_BUS_LIFECYCLE_READY=true
INTERNAL_PRIOR_ARM_STATE=NON_BLOCKING_EPISTEMIC_UNKNOWN
SEED_PROVIDER_IMPLEMENTED=true
SEED_FRESHNESS_GENERALIZATION=UNPROVEN
SEED_FRESHNESS_IS_SOLE_LIVE_BLOCKER=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false
```

D256 resta canonico per cancel/re-entry e quiescenza terminale host/bus;
disarm/lifetime/stato interno restano ignoti epistemici non bloccanti. La
chiusura separata IRQ2→`0x22`→prima immagine sintetica resta valida, ma non
colma i gate bootstrap. Il bundle D257 precedente è preservato come provenance
e classificato `SUPERSEDED_BY_D257_EXACT_BOOTSTRAP_CORRECTIVE`. D257 non
apre USB, non usa hardware o dati biometrici, non crea launcher/operator kit,
non approva una baseline e non autorizza una run live.

## D258: proprietario e semantica dei gate host FDT

D258 è esclusivamente offline. L'audit statico mirato sul `gfusb.dll` target
SHA-256 `904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`
ha recuperato l'orchestratore `gf_update_all_base` a
`0x180068adc..0x18006987d` e il caller che, su successo, invoca il final FDT
down a `0x180068abe`. Questo corregge l'inferenza D257 che collocava tutti i
gate dinamici prima del terzo sample.

Il percorso target statico è:

```text
stage0 0x36 -> acquisizione/store NAV 0x50 -> stage1 0x36
-> ChipRegRead 0x0082 -> confronto base0/base1
-> acquisizione baseline 0x20 -> stage2 0x36 -> confronto base1/base2
-> classificatore NAV mode1 -> classificatore immagine mode0 -> final 0x32
```

L'helper NAV `0x180067874` copia la risposta dinamica nel buffer di lavoro e
ritorna successo senza valutarne semanticamente il contenuto; stage1 segue
dunque la sola acquisizione strutturalmente valida. Il NAV viene consumato
dopo stage2 dal wrapper `0x180023fdc`, che imposta mode 1 e chiama il
classificatore comune `0x180022654`. La baseline acquisita da `0x180067914`
viene analogamente consumata dopo stage2 da `0x180023fa8`, mode 0, verso lo
stesso classificatore. Gli enum `0..3` selezionano riuso o aggiornamento delle
basi; non autorizzano il terzo sample, già completato.

La read `ChipRegRead(register=0x0082, quantity=2)` è invece chiusa: il byte 0
della risposta non viene usato su questo path, il byte 1 è zero-extended come
soglia unsigned e ogni elemento delle due basi FDT grezze è confrontato come
word unsigned:

```text
forall i: abs(uint16(base0[i]) - uint16(base1[i])) <= uint8(response[1])
```

Una violazione sceglie il fallback alla base file quando disponibile o il loop
di rebuild; il pass prosegue verso la baseline. Lo stesso confronto è ripetuto
fra base1 e base2. Nel raw D255 la massima differenza base0/base1 è `1` e la
soglia osservata è `29`, quindi il pass deriva dalla formula e non dal blob
hardcoded `80 1d`.

Il core GPL conserva ora NAV e B0 baseline come stato runtime, applica il gate
`0x82` nativo nel punto corretto, completa stage2 e sposta i classificatori
NAV/image nel boundary post-stage2. La decryption e i classificatori mancanti
restano obbligatori prima del final `0x32`: in loro assenza il candidate fallisce
chiuso. Il replay D255 esatto è wire-exact attraverso
`36,50,36,82,20,36`, poi si arresta prima di `0x32` sul primo classificatore
post-stage2 non riproducibile. Il replay proiettato D256/D257 resta distinto e
`PASS_HISTORICAL`.

Il classifier comune è presente nel corpus, ma la sua configurazione/stato
runtime target e un modello ABI esatto validabile non sono materializzati.
Per la baseline manca inoltre il plaintext application del B0 D255: la PSK
factory approvata vive fuori dal confine user-readable del repository, quindi
`D255_B0_DECRYPTION_STATUS=INPUT_UNAVAILABLE_WITHOUT_PRIVILEGE`. D258 non ha
letto path root-only, chiesto privilegi o copiato secret. Il corpus statico
locale è esaurito per queste domande: un ulteriore census dello stesso DLL
senza runtime state o plaintext non testerebbe una nuova ipotesi.

La policy temporale non riusa più accidentalmente un unico valore:

```text
COMMAND_TIMEOUT_POLICY=PER_COMMAND_EVIDENCE_BOUNDED
TIMEOUT_0x36_MS=500
TIMEOUT_0x50_MS=500
TIMEOUT_0x82_MS=500
TIMEOUT_0x20_MS=2000
TIMEOUT_0x32_MS=100
```

I valori derivano dai callsite OEM e sono compatibili con le latenze D255
osservate (`11.025`, `17.934`, `2.198`, `81.293`, `0.957` ms rispettivamente).
Timeout significa stop fail-closed e non retry.

```text
TARGET_BOOTSTRAP_SEQUENCE_HASH_GATED=true
GATE_0x50_STATUS=PARTIAL_STORE_ROLE_CLOSED_POST_SAMPLE_CLASSIFIER_UNRESOLVED
GATE_0x82_STATUS=CLOSED_NATIVE_PREDICATE_IMPLEMENTED
GATE_0x20_STATUS=PARTIAL_ACQUISITION_ROLE_CLOSED_POST_SAMPLE_CLASSIFIER_UNRESOLVED
CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x50_GATE=true
CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x82_GATE=true
CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x20_GATE=true
PROJECTED_FDT_SUBSEQUENCE_REPLAY=PASS_HISTORICAL
EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY=BLOCKED
DYNAMIC_HOST_GATES_CLOSED=false
FDT_OFFLINE_CANDIDATE_CLOSED=false
HOST_BUS_LIFECYCLE_READY=true
SEED_FRESHNESS_FACTORY_PRESERVATION_BLOCKER=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false
```

D258 non modifica il backend USB reale, non crea launcher o operator kit, non
accede all'hardware e non autorizza una run live.

## D259: contratto minimo device-visible e consumo TLS B0

D259 è esclusivamente offline e supera il blocker D258 per separazione causale,
non ricostruendo artificialmente l'intero algoritmo OEM. L'audit riproducibile
è gated sul `gfusb.dll` SHA-256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`
e sul raw D255 SHA-256
`802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c`.
Nel caller `0x180068940`, `gf_update_all_base` è chiamato a `0x18006898a` e
il final `ChicagoHUSetMode(3,1,1)` segue a `0x180068abe` per ogni return nonzero
dell'orchestratore.

La conclusione Class A preliminare era sostenuta da anchor corretti ma da una
matrice semantica codificata nel Python. Il corrective la sostituisce con
`D259_post_classifier_disasm_excerpt.txt` e
`D259_post_classifier_cfg.json`: un parser bounded estrae programmaticamente
le sole istruzioni pertinenti, deriva target condizionali/incondizionati,
case/default, merge, call, copy e dirty flag e genera da quel CFG la matrice
finale. Un campo non derivabile farebbe fallire l'audit invece di essere
promosso. La Classe A seguente è pertanto `PASS_MECHANICALLY_DERIVED`, non più
una riaffermazione dell'assertion harness preliminare.

I wrapper classifier NAV `0x180023fdc` e image `0x180023fa8` alimentano il
classificatore comune `0x180022654`. I rispettivi return sono salvati a
`[rsp+0x54]` e `[rsp+0x58]`; gli switch `0x1800693d8..0x1800694fa` e
`0x180069592..0x1800696b4` trattano esplicitamente `0`, `1`, `2`, `3` e fanno
convergere anche ogni altro valore. Soltanto il valore esatto `1` conserva la
base esistente. Tutti gli altri valori, inclusi negativi/altri, copiano la base
acquisita nelle globali host `0x18059fa88`/`0x18059fa78` e marcano il flag
dirty. Nessuno di questi rami modifica il risultato successo inizializzato in
`[rsp+0x44]`, né la globale tabella FDT `0x180580818`, letta separatamente dal
builder del final `0x32`.

La conseguenza delimitata è:

```text
CLASSIFIER_FIRST_ARM_ROLE=NON_BLOCKING
CLASSIFIER_FULL_DRIVER_ROLE=FUTURE_HOST_ALGORITHM_OR_CACHE_FIDELITY
CLASSIFIER_FDT_TABLE_EFFECT=NONE
CLASSIFIER_FINAL_0x32_PAYLOAD_EFFECT=NONE
CLASSIFIER_ADDITIONAL_DEVICE_COMMANDS=NONE
CLASSIFIER_RETRY_OR_REBUILD_EFFECT=NONE
CLASSIFIER_ERROR_RECOVERY_COMMANDS=NONE
```

Questa non è l'affermazione che il sensore accetti ciecamente `0x32`, né che il
classifier sia inutile per sempre. È la conclusione più stretta che, nel
contratto del primo arm, l'esecuzione e il return del classifier non cambiano
alcun comando, payload, tabella, requisito temporale o stato device-visible e
sono perciò causalmente non osservabili dal MCU. Qualità, discriminazione dito,
temperatura, refresh delle basi e fedeltà cache/OEM restano possibili ruoli
futuri del classifier.

Il flag dirty porta, prima del ritorno di `gf_update_all_base`, alla chiamata
condizionale `0x180067f44` (`gf_savebaseTofile`, stringa `goodix.dat`) a
`0x1800697e1`. Il return del salvataggio non governa il final `0x32`, che il
caller invia dopo. Non è osservato alcun cache write dopo quel final nello
stesso path. La cache è persistenza host e fedeltà OEM, non factory state del
sensore; il first-live Linux la tiene disabilitata e non introduce una nuova
persistenza host:

```text
OEM_CACHE_WRITE_BEFORE_FINAL_0x32=CONDITIONAL
OEM_CACHE_WRITE_AFTER_FINAL_0x32=false
OEM_CACHE_WRITE_REQUIRED_FOR_FINAL_0x32=false
OEM_CACHE_WRITE_REQUIRED_FOR_DEVICE_PROGRESS=false
LINUX_FIRST_LIVE_CACHE_WRITE_POLICY=DISABLED
HOST_CACHE_WRITE_COUNT=0
```

Il B0 baseline `0x20` segue una regola diversa: può essere ignorato
semanticamente solo dopo il consumo da parte dello stack TLS che possiede la
sessione. Rimuovere il ciphertext dal transport senza TLS consumption è
fail-closed perché desincronizzerebbe sequence/state. Il corrective sposta il
consumo nel punto corretto: risposta B0 a `0x20` → autenticazione/decryption
tramite la sessione attiva → discard e zeroizzazione best-effort del solo
buffer mutabile → terzo `0x36`. Il finalizer post-stage2 non riceve più il B0 e
non può ritardarne il consumo.

Il core GPL espone un adapter che usa l'esatta `SSLObject` e la stessa input
MemoryBIO già handshaked, senza creare un secondo contesto/server, handshake,
transport o provisioning PSK. La fixture sintetica non biometrica prova una
sessione server, un client, un handshake, il consumo B0 e un secondo record
applicativo sulla medesima sessione, quindi anche la continuità di sequence
numbers/cipher state. La prova resta esclusivamente offline/architectural.

D245 resta evidenza live target-specific che Linux completa il TLS nel ruolo
server con lo stesso secret validato da E4. L'audit del runtime sealed mostra
però che `ProductionReplayBackend.tls_handshake()` conserva l'engine soltanto
in una variabile locale e lo chiude incondizionatamente nel `finally`; non
esiste un oggetto post-handshake esposto al consumer B0. Poiché D259 non può
modificare `src/` o i launcher live, il plumbing reale non è chiuso. Il
plaintext B0 storico D255 resta indisponibile e non è stato richiesto o
decrittato:

```text
BASELINE_B0_TLS_CONSUMPTION_REQUIRED=true
BASELINE_B0_IMAGE_CLASSIFICATION_REQUIRED=false
BASELINE_B0_RASTER_DECODE_REQUIRED=false
HISTORICAL_D255_B0_PLAINTEXT_AVAILABLE=false
FUTURE_LINUX_RUNTIME_TLS_SESSION_PROVEN=true
LIVE_TLS_ROLE=SERVER
LIVE_TLS_TO_B0_ADAPTER_STATUS=UNIMPLEMENTED
SAME_TLS_SESSION_B0_CONSUMPTION=PASS_OFFLINE_ARCHITECTURAL
POST_B0_TLS_SESSION_CONTINUITY=PASS_OFFLINE_ARCHITECTURAL
FUTURE_LINUX_RUNTIME_B0_CONSUMPTION_CAPABILITY=false
```

La zeroizzazione non è promossa oltre quanto Python/OpenSSL consentono:

```text
PLAINTEXT_MUTABLE_BUFFER_BEST_EFFORT_ZEROIZED=true
OPENSSL_INTERNAL_COPY_ZEROIZATION=NOT_PROVEN
PYTHON_IMMUTABLE_TEMP_COPY_ZEROIZATION=NOT_PROVEN
```

Il replay D259 usa per riferimento seed/cache, request e risposte non-B0 D255;
sostituisce soltanto la risposta B0 con un record TLS sintetico della stessa
lunghezza esterna `7726`, perché non pretende il plaintext storico. Il percorso
completo è wire-exact nelle request target:

```text
validated OTP-bound seed
-> 0x36 -> IRQ100 -> 0x50 structurally valid
-> 0x36 -> IRQ100 -> 0x82 native delta PASS
-> 0x20 -> B0 TLS authenticate/decrypt/best-effort mutable-buffer zeroize/discard
-> 0x36 -> IRQ100 -> second native delta PASS
-> no classifier, raster decode or cache write
-> final 0x32 exactly once
```

I timeout restano `36/50/82=500`, `20=2000`, `32=100` ms. Retry, A2/`0x70`,
famiglie device persistenti e cache write sono zero. Un failure resta
`no retry → no recovery speciale → cleanup terminale host-side`; D256 rimane
l'autorità sul terminal stop osservato.

La knowledge boundary distingue ora permanentemente tre domande. Il corpus
locale è esaurito per la fedeltà host OEM esatta, perché mancano ABI/stato
runtime completo del classifier; non è esaurito/bloccante per il contratto
minimo device-visible del classifier, ora confermato meccanicamente. Resta però
un gap software concreto fra il TLS live-proven D245 e il consumer B0: la prova
same-session sintetica non sostituisce il plumbing runtime. Analogamente, cache
fidelity non equivale a factory-preservation, e readiness review non equivale
ad autorizzazione.

```text
OUTCOME=BLOCKED_LIVE_TLS_RUNTIME_ADAPTER_GAP
POST_CLASSIFIER_BRANCH_PROOF=PASS_MECHANICALLY_DERIVED
BRANCH_MATRIX_DERIVATION_MODE=PARSED_DISASSEMBLY_CFG
POST_STAGE2_CLASSIFIER_DEVICE_PROGRESS_REQUIRED=false
POST_STAGE2_CLASSIFIER_FACTORY_PRESERVATION_REQUIRED=false
POST_STAGE2_CLASSIFIER_FIRST_ARM_REQUIRED=false
POST_STAGE2_CLASSIFIER_OEM_HOST_FIDELITY_REQUIRED=true
POST_STAGE2_CLASSIFIER_HOST_PERSISTENCE_REQUIRED=false
CORPUS_EXHAUSTED_FOR_EXACT_OEM_HOST_FIDELITY=true
CORPUS_EXHAUSTED_FOR_MINIMAL_DEVICE_LIVE_CONTRACT=false
MINIMAL_DEVICE_LIVE_CONTRACT_CLOSED=false
FACTORY_PRESERVING_MINIMAL_CANDIDATE_CLOSED=false
FDT_OFFLINE_CANDIDATE_CLOSED=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false
```

Il precedente bundle D259 è preservato per provenance ma marcato
`SUPERSEDED_BY_D259_MECHANICAL_PROOF_CORRECTIVE`. Il corrective lascia `src/`
e i launcher D245/D246/D251 byte-identici, non aggiunge backend USB, launcher o
operator kit, non auto-approva una baseline e non autorizza hardware.

## D260: runtime GPL persistente e architecture readiness offline

D260 implementa in `core/` la convergenza architetturale che D259 aveva
lasciato aperta. `core/persistent_runtime.py` possiede per l'intera esecuzione
una sessione transport logica, un `ValidatedSecretBoundary`, un server TLS 1.2
PSK, un bridge B0, il demux misto A0/B0, un `EventSource` separato e la state
machine FDT D259. `core/tls_b0.py` espone ora il lifecycle esplicito:

```text
CREATED -> HANDSHAKING -> ESTABLISHED -> APPLICATION_ACTIVE -> CLOSED
```

Il rehearsal usa esclusivamente un client OpenSSL e un secret sintetici. Il
medesimo boundary object effettua un solo handoff; il server crea un solo
`SSLObject`, registra un solo handshake e non esegue secondo provisioning,
fallback, PSK random o PSK null. La sessione rimane stabilita mentre D4 passa
come A0 plaintext canonico `a00600a6d403000000d3`, una sola volta, con policy
fixed-64 zero-tail, pacing post-TLS 20 ms e timeout 200 ms. D4 non incrementa
il contatore TLS application data. AF/AE e gli A0 FDT restano plaintext; solo
la risposta B0 a `0x20` viene autenticata/decrittata dal medesimo engine e il
buffer mutabile del plaintext sintetico viene scartato e zeroizzato
best-effort. Copie interne OpenSSL e temporanei Python immutabili restano
`NOT_PROVEN` rispetto alla zeroizzazione.

Il bridge handshake prova offline il passaggio `D1 → B0 ClientHello → server
flight B0 → client Finished B0 → ESTABLISHED`. I record B0 host→device
conservano staging fisico fixed-64 e pacing 10 ms D242/D245. D4 conserva il
contratto fisico D246 e AF quello D251. Per `0x36/0x50/0x82/0x20/0x32`, D260
modella framing e timeout logici esatti ma non inventa la tail fisica futura
del backend Linux:

```text
PHYSICAL_SUBMISSION_CONTRACT_STATUS=
  ABSTRACT_OFFLINE_FOR_FDT_A0_WITH_EXACT_D4_AND_B0_TLS_POLICIES
```

Questa incompletezza è compatibile con architecture readiness ma impedisce
operational readiness. ACK sincrono ed evento asincrono non sono collassati:
`RuntimeTransport.receive()` consegna l'ACK e solo dopo
`EventSource.wait_event()` consegna ciascuno dei tre IRQ `0x0100`, touch zero e
raw-base da 12 byte, exactly once.

Il percorso production-shaped continuo passa come singolo runtime object:

```text
D1/B0 TLS handshake
-> retained TLS engine
-> D4 A0 plaintext exactly once
-> AF/AE A0
-> 0x36 ACK -> separate IRQ100 stage0
-> 0x50 NAV
-> 0x36 ACK -> separate IRQ100 stage1
-> 0x82 first native delta PASS
-> 0x20 -> B0 consumed by same TLS engine
-> 0x36 ACK -> separate IRQ100 stage2
-> second native delta PASS
-> classifier/raster/cache zero
-> final 0x32 exactly once
-> one TLS close and one transport cleanup
```

La traccia FDT è esattamente `36,50,36,82,20,36,32`; B0 viene consumato prima
dello stage2. La matrice copre malformed B0 handshake, bad MAC handshake,
timeout TLS, ACK D4 errato, AE malformed, seed invalido, timeout primo `0x36`,
IRQ100 mancante/errato, NAV malformed, primo delta reject, B0 auth failure, B0
ritardato oltre il boundary stage2, secondo delta reject e ACK finale `0x32`
errato. Ogni scenario termina con retry/cache/device-write/A2/`0x70` a zero,
una chiusura TLS e un cleanup transport.

Il runtime D245/D246/D251 e i launcher storici restano byte-identici e
continuano a essere l'autorità dell'evidenza live pregressa. Il nuovo runtime
non è collegato a USB reale, non usa il secret E4 reale, non implementa
privilege/fprintd/marker/baseline/operator kit e non è live-proven. Lo stato
canonico D260 è:

```text
PERSISTENT_TLS_RUNTIME_IMPLEMENTED=true
LEGACY_TLS_ONE_SHOT_LIMITATION_ARCHITECTURALLY_BYPASSED_IN_CORE=true
END_TO_END_OFFLINE_RUNTIME_REHEARSAL=PASS
FAILURE_CONTAINMENT_MATRIX=PASS
MINIMAL_DEVICE_LIVE_CONTRACT_CLOSED=true
FACTORY_PRESERVING_MINIMAL_CANDIDATE_CLOSED=true
FDT_OFFLINE_CANDIDATE_CLOSED=true
READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW=true
READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW=false
READY_FOR_FDT_LIVE_REVIEW=false
READY_FOR_FDT_LIVE=false
NEW_RUNTIME_LIVE_PROVEN=false
```

La successiva review operativa, se autorizzata come step distinto, dovrà
ancora chiudere backend USB del nuovo runtime, physical policy A0 FDT,
privilege model, loading/binding del secret reale, stop/restore fprintd,
single-use marker, baseline live approvata e operator kit. D260 non autorizza
hardware e non prepara quel percorso.

## D261: operational live-readiness candidate offline

D261 implementa il percorso operativo che D260 lasciava intenzionalmente
astratto, ma lo valida soltanto con backend, OS, secret e target sintetici. Il
censimento riproducibile della capture canonica D255 separa per ciascun
controllo lunghezza logica, lunghezza fisica, tail e provenienza. Le submission
OEM FDT sono tutte da 64 byte. Nei comandi `0x36`, `0x50`, `0x82` e `0x20` i
soli byte extra nonzero occupano sempre gli offset fisici `40..45`; la capture
D254 mostra gli stessi offset con valori diversi. Il finale `0x32` D255 ha
invece tail zero e ACK valido. La decisione bounded è:

```text
FDT_A0_PHYSICAL_LENGTH=64
FDT_A0_TAIL_POLICY=ZERO_FILL_OUTSIDE_DECLARED_LOGICAL_FRAME
FDT_A0_RESIDUE_REPLAY=false
0x32_ZERO_TAIL_EVIDENCE=PRIMARY_TARGET_OEM_ACCEPTED
0x36/0x50/0x82/0x20_ZERO_TAIL_EVIDENCE=DETERMINISTIC_CANDIDATE_NOT_LIVE_PROVEN
PRIMARY_FUTURE_LIVE_RISK=FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND
```

`core/cold_start.py` reimplementa nel dominio GPL i fatti comportamentali già
provati da D245/D246 senza importare o modificare il runtime sealed: firmware
A8 esatto, E4 tipizzato e validato, due A2 soltanto nelle posizioni canoniche,
chip `0x82`, OTP A6, `0x70`, quattro DAC `0x80` correlati alla config e config
`0x90` hash-gated. L'OTP ottenuto nella stessa sessione è l'unica identità
accettata da `provide_hash_gated_fdt12()`; mismatch, layout, CRC o hash fermano
prima del primo `0x36`, senza fallback, randomizzazione o write cache.

`core/protected_runtime.py` definisce path root-owned `0600` deterministici.
Il dry-run effettua soltanto `lstat`, distingue `ABSENT` da
`INACCESSIBLE_UNPRIVILEGED`/errore errno e non legge il secret. Il supported
path crea una capability CLI-intent soltanto dopo il parsing dell'esatto flag;
questa abilita preflight e validazione del contenuto protetto ma non USB. Dopo
i gate holder, il manifest e config90 sono letti e validati, quindi la fonte
cache è verificata per hash, layout e CRC; soltanto dopo il PASS di tutto il
materiale non-secret viene costruita e materializzata la boundary secret
reale. Il secret è così l'ultimo contenuto protetto materializzato prima del
marker. Solo dopo tali controlli viene acquisito e fsyncato il marker, che
restituisce una prova opaca usata immediatamente per emettere la distinta
capability Live-I/O accettata dal backend libusb. Lo stesso buffer valida E4
mediante la reference D190 canonica e, solo dopo il match, passa al server TLS;
il cleanup lo azzera best-effort. Funzione Python interna senza capability,
ambiente da solo e backend da solo falliscono prima di marker, secret e libusb.
È un fence contro uso accidentale/path non supportati, non un confine di
sicurezza contro codice arbitrario nel medesimo interprete Python.

La bounded import closure del supported path è derivata in un processo nuovo
dal delta dei moduli repository-local effettivamente caricati e comprende 16
source Python. Oltre a entrypoint e moduli transitivi include i due package
initializer realmente eseguiti, `core/__init__.py` e
`poc/goodix5125/tools/binding_reference/__init__.py`; entrambi appartengono ora
alla tuple hardcoded e il verifier ne rileva il drift rispetto a una baseline
sintetica. Le directory namespace prive di `__init__.py` non sono incluse. Un
harness separato, senza mock che intercettino gli import, usa audit/profile
solo per osservare il subprocess e prova zero accessi USB/protected filesystem,
zero istanziazione o materializzazione secret reale, zero mutazioni fprintd e
zero marker a import-time. Definire e importare il concrete loader è consentito;
il rehearsal offline lo sostituisce esplicitamente tramite Protocol con una
fixture sintetica e non implementa fallback dopo un tentativo reale.

`core/usb_runtime.py` è un adapter libusb lazy e production-shaped per un solo
target `27c6:5125`, interfaccia `0`, OUT `0x01`, IN `0x81`. Richiede cardinalità
esatta e rivalida bus/address/port path prima e dopo ogni OUT. Non espone
detach, reset, clear-halt, reopen, retry o recovery. Un solo
`SharedFrameRouter` possiede fisicamente EP81 e conserva in code separate ACK,
risposte, eventi FDT noti e B0 anche quando sono frammentati o coalesciuti. Ogni
phase read usa una sola deadline monotonic assoluta: le completion valide ma
non corrispondenti ricevono solo il tempo residuo e non rinnovano il timeout.
Tredici harness eseguono split/coalescing, buffering incrociato, NAV/B0 grandi,
interleaving, ordine, starvation, deadline e tentativo di secondo reader. Il
transport applica inoltre pacing pre/post della policy fisica e rifiuta frame
buffered inattesi dopo l'ACK terminale `0x32`.

L'audit post-live D265/02 resta la prova storica che la baseline eseguita
separava come eventi soltanto gli IRQ `0x0100` riconosciuti da `_is_irq100()` e
lasciava IRQ `0x0002` nella vista command. D266/01 corregge offline quel difetto
nel codice corrente: `_is_fdt_event()` accetta solo A0 che superano il parser
canonico `parse_fdt_event()` e corrispondono alle coppie target osservate
`0x32/IRQ2`, `0x34/IRQ200` o `0x36/IRQ100`; distingue quindi tali eventi da
ACK, response, B0/TLS e altre combinazioni FDT. La nuova coverage attraversa il router
concreto con IRQ100 e IRQ2, le quattro sequenze di interleaving richieste, la
deadline assoluta, il lock del reader e il seam first-image fino a un solo
tentativo sintetico `0x22`. Questo è evidence software/offline e non rivela se
IRQ2 sia stato fisicamente emesso durante D265/02.

La review AI-PM di D266/01 ha accettato il fix al commit
`7a2ceff54f2fc27332a9f2a531ce4af5d90cf9a2`. L'audit D266/02 conferma che il
call graph operatore continua a costruire `LibusbRuntimeTransport`, usa il suo
unico `SharedFrameRouter` e passa al coordinator proprio
`transport.event_source`; non emerge un event source alternativo nel percorso
production. Il dry-run del launcher D265 dalla cwd esterna realistica `/tmp`
fallisce tuttavia la byte identity: `analysis/D265/D265_01_live_critical_manifest.json`
attende per `core/usb_runtime.py` l'hash D265
`a19c0ffb93a7e1dc7d4b08a0fed9ed738a9d51bb72e4327d16a41b4cb15dc278`,
mentre il blob accettato D266/01 è
`c4e62b0786d7710eb0625b033258636597b9aa8f40259ce5a1f669b0e160385b`.
Il gate si comporta quindi correttamente fail-closed, ma l'operator kit non è
execution-ready sulla nuova base. D266/02 non modifica il manifest storico né
il codice live-critical: la nuova autorità candidate e il relativo wiring
richiedono uno step corrective separato. D266/03 materializza tale separazione
nel namespace D267 e lascia D265 byte-immutato. La nuova tuple
`D267_FIRST_IMAGE_LIVE_CRITICAL_PATHS` contiene tutti e soli i 20 file
raggiungibili dal launcher D267: i due entrypoint e 18 dipendenze runtime/guard,
con `core/d267_first_image_operator.py` al posto dell'orchestrator storico
D265. Il path production costruisce `CtypesLibusbBackend` →
`LibusbRuntimeTransport`, usa l'unico `SharedFrameRouter` e il suo
`_RouterEventSource`, quindi invoca `PersistentRuntimeCoordinator` soltanto con
`STOP_AFTER_FIRST_IMAGE`; non esiste un event-source bypass nel candidate.

`core/live_capability.py` conserva le authority D261 e D265 e aggiunge classi e
nonce D267 separati. Un intent D265 non può creare marker/live-I/O D267 e un
intent D267 non può creare capability D265; il marker D267 viene scritto
`O_EXCL`/`0600`, completato e fsyncato prima del minting, e la sua capability è
consumabile una volta. Il namespace durable è
`/var/lib/goodix-5125-poc/d267-first-image-single-use.marker`; il report è
`/var/lib/goodix-5125-poc/d261-results/d267-first-image-final.json`. Il path
live richiede `D267_APPROVED_LIVE_BASELINE_SHA`, ma D266/03 non assegna alcun
valore approvato e non crea il marker reale.

Il launcher `operator_kit/d261-live-fdt-arm-once.sh` accetta soltanto
`--dry-run` oppure l'esatta autorizzazione live. Il default è hard-disabled.
Il ramo live, non eseguito in D261, richiede root derivato da un operatore non
root, full SHA approvato e confronto Git blob-per-blob dell'insieme hardcoded.
La tuple immutabile nel verifier è l'autorità; il JSON fileset è un report
derivato e il verifier include se stesso nel set. Protected root e report
directory reali, non symlink, root-owned e `0700`, più destinazione report
sicura, sono verificati o creati secondo policy prima di fprintd, marker,
secret e USB. Seguono metadata/target, stop fprintd, signal mask e holder
check; manifest, config90 e cache non-secret vengono quindi validati prima del
secret reale. Soltanto dopo la sua materializzazione il marker `O_EXCL` `0600`
viene consumato e abilita la capability Live-I/O. La pubblicazione usa
temporary `0600`, fsync file, replace nella stessa directory e fsync directory;
collisioni/symlink falliscono chiuso e un failure del report finale non può
essere rappresentato come run PASS.

Il rehearsal offline completo attraversa capability CLI-intent, gate
pre-side-effect, validazione protetta, marker, capability Live-I/O e, in una
sola sessione fake,
`cold-start → D1/TLS → D4 → AF/AE → 36,50,36,82,20/B0,36,32` e termina solo
dopo l'ACK arm. Copre split/coalescing, payload grandi, identità USB mutata,
claim failure, mismatch OTP/cache, mismatch E4 e frame extra terminale. La
matrice operativa comprende inoltre baseline errata o modificata, marker stale,
holder esterno, metadati protetti invalidi, failure fprintd/report/cleanup/
restore e mismatch della policy fisica. Tutti i 24 scenari invocano realmente
il gate o il runtime, inclusi due repository Git temporanei reali;
`ASSERTION_ONLY_FAILURE_ROWS=0`. Tutti i failure sono fail-closed con retry,
famiglie persistenti e cache write a zero. I failure config90, manifest e cache
hash/layout/CRC hanno inoltre secret materialization, marker e USB a zero; il
failure di metadata secret ha materializzazione, marker e USB a zero. La suite
repository completa passa `238/238`; nessun raw, OTP, secret o dato biometrico entra nel
bundle.

Riesame metodologico pre-live:

1. rispetto all'ultimo percorso live, cambia il metodo: il nuovo runtime GPL
   conserva cold-start, TLS e FDT nella stessa sessione reale, usa un solo
   reader fisico e sostituisce la tail astratta con una policy per comando
   derivata dal raw;
2. la nuova ipotesi tecnica è che APP12509 accetti la tail zero fixed-64 anche
   per `0x36`, `0x50`, `0x82` e `0x20`, come già osservato direttamente per
   `0x32` e per altri boundary A0;
3. se una futura singola run fallisce nello stesso punto, non si ripete: si
   analizza il comando/tail preciso e si acquisisce nuova evidenza o si cambia
   metodo tecnico, senza creare una replica basata soltanto su pacing,
   packaging o preflight.

Lo stato canonico D261 è:

```text
D261_OUTCOME=READY
D261_OPERATIONAL_EVIDENCE_HARDENING=PASS
D261_END_TO_END_OFFLINE_OPERATIONAL_REHEARSAL=PASS
D261_FAILURE_CONTAINMENT_MATRIX=PASS_EXECUTION_DERIVED
D261_FAILURE_SCENARIO_COUNT=24
D261_FAILURE_SCENARIO_EXECUTED_COUNT=24
D261_ASSERTION_ONLY_FAILURE_ROWS=0
D261_LIVE_CAPABILITY_DEFAULT=0
D261_LIVE_PATH_REACHABLE_WITHOUT_EXPLICIT_FLAG=false
D261_DIRECT_PYTHON_LIVE_CALL_WITHOUT_CAPABILITY_FAILS_CLOSED=true
D261_SHARED_READER_PHASE_DEADLINE_ENFORCED=true
D261_LIVE_IMPORT_CLOSURE_STATUS=PASS
D261_LIVE_IMPORT_CLOSURE_PATH_COUNT=16
D261_LIVE_IMPORT_CLOSURE_MISSING_PATH_COUNT=0
D261_PACKAGE_INITIALIZERS_EXECUTED_AND_BASELINE_GATED=true
D261_NO_IMPORT_TIME_SIDE_EFFECTS=true
D261_IMPORT_SAFETY_TEST=PASS
D261_NON_SECRET_CONTENT_VALIDATED_BEFORE_SECRET_MATERIALIZATION=true
D261_SECRET_MATERIALIZATION_LAST_PRE_MARKER_PROTECTED_READ=true
D261_OFFLINE_REAL_SECRET_LOADER_INSTANTIATION_COUNT=0
D261_OFFLINE_REAL_SECRET_MATERIALIZATION_COUNT=0
D261_OFFLINE_SECRET_FALLBACK_FROM_REAL_TO_SYNTHETIC=false
D261_APPROVED_LIVE_BASELINE_SHA=e9073a171697bd68dd2debabb851f23d007bf718
D261_OPERATIONAL_LIVE_CRITICAL_FILESET=APPROVED_USER_AI_PM_FULL_SHA
D261_EXACT_APPROVED_LIVE_BASELINE_PRESENT=true
D261_READY_FOR_BASELINE_APPROVAL_REVIEW=false
D261_OPERATIONAL_REVIEW_PENDING_APPROVED_BASELINE=false
D261_READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW=true
D261_READY_FOR_FDT_LIVE_REVIEW=true
D261_READY_FOR_FDT_LIVE=false
D261_LIVE_EXECUTION=NOT_PERFORMED
```

## Operazioni read note e limiti

| Operazione | Dominio | Limite |
| --- | --- | --- |
| E4 | selector service di produzione MCU | nessun serializer address+length a 32 bit |
| `0x82` | registri chip/sensore | address LE16 e quantità LE16; non MCU flash |
| A6 | OTP/factory tipizzato | risposta fixed/selective |
| A8 | versione firmware | metadato fisso |
| AE / wire AF | stato MCU | struttura fissa |
| ProductionOperateKey | enum key/state | selector tipizzato, non puntatore |
| F0/F4 | update/check | status; erase/program/reset possibili, nessun raw readback |

Nessuna di queste operazioni può codificare e leggere
`0x080272e0..0x0802b8f4` attraverso un path provato.

## Audit definitivo del readback resident (D230)

`D230_DECISION=D230_NO_SAFE_MEMORY_READ_PATH_EXISTS_IN_CORPUS`

D230 ha censito tutti i 52 request frame della capture disponibile, 20 control
wire A0 distinti, 65 call-site verso i tre builder di trasporto in `gfusb.dll`,
sette classi di superficie USB e tutte le 16 famiglie del dispatcher APP. Non è
stato trovato alcun dataflow:

```text
address MCU host-controlled a 32 bit + length
→ request USB
→ dereference flash device-side
→ byte raw proporzionali nella risposta
```

Le primitive interne di load/copy non sono esposte con source pointer
host-controlled. I path A4/F0/F4 sono maintenance mutante e non forniscono
readback grezzo.

La conclusione è rigorosamente corpus-bounded: non afferma che il dispositivo
non possa mai contenere un comando non documentato. I corpi resident sono
assenti e la prima capture è perduta. Tuttavia nessun builder o request nel
corpus trasporta un indirizzo arbitrario verso quei corpi.

`SAFE_RESIDENT_READBACK_ROUTE_STATUS=EXHAUSTED_IN_LOCAL_CORPUS`

Non creare o raccomandare D231/D232 per altre ricerche statiche della stessa
interfaccia senza nuova evidenza primaria target-specific.

## Current critical boundary

La semantica host-side A2/0x70, il backend USB/TLS, il binding runtime PSK↔E4,
l'orchestratore e l'entrypoint production non sono più blocker offline. D245 ha
provato live su 12509 l'intera catena A8→E4→pre-D1→D1→TLS e ha completato
l'handshake senza retry. D246 ha poi chiuso live il primo confine
post-handshake: il target ha accettato una sola inizializzazione volatile D4
per il receiver APP12509 esatto con ACK `0x01`, e la run si è fermata a
`STOP_AFTER_D4`. A8, E4, TLS e D4 non sono più blocker aperti.

Sul percorso nativo C/LGPL, distinto dal runtime GPL storico sopra descritto,
D278/01 ha chiuso host-only l'intera catena
`A8→E4→A2→82→A6→A2→70→80x4→90→D1→TLS ESTABLISHED→STOP`, inclusi ownership
single-IN/single-OUT, B0 fixed64 zero-tail e pacing 10 ms generation-owned. È
nuova evidenza eseguibile host-only, non target-specific: sul sensore reale il
percorso nativo resta provato soltanto fino ad A8/ACK/typed APP12509 da D277/02.
D278/02 aggiunge il loader protetto nativo, il binder D190 PSK→E4, il gate
PE bounded, la composizione live-capable e il watchdog per fase, tutti provati
host-only con fixture sintetiche; il binding GUsb/libfprint completo compila e
il solo `--self-test` passa con zero accessi reali. In aggiunta, l'operatore ha
eseguito il 29 agosto 2026 il preflight autentico read-only dei materiali
protetti (`--material-preflight-only`) con `PASS`, `e4_binding_match=true` e
zero accesso USB. D278/03 ha poi confermato sulla baseline revisionata la
executable closure locale Fedora e ha preparato la procedura single-shot
fail-closed. La prima run autorizzata e consumata ha provato
A8 nativo, inviato E4 ed è terminata sul primo frame IN E4 prima di un ACK
accettato, senza raggiungere TLS. Il riesame post-live ha provato la divergenza
della policy ACK C rispetto a D238 e l'ha corretta offline con test normal e
sanitizer PASS; lo status E4 `0x07` della run corrente resta probabile ma non
direttamente telemetrizzato. La review AI-PM del correttivo ha concluso
`AI_PM_D278_03_ACK_CORRECTIVE_REVIEW=PASS` con
`NATIVE_C_ACK_POLICY_DIVERGENCE=PROVEN_AND_CORRECTED`. Dopo tale review, sul
commit corretto `4e5d74770bce6e0a9de929b19279038827abff8c` è stata qualificata
host-only (le suite via runtime `FREEDESKTOP_SDK_25_08`, il build preservato nel `/tmp` del Fedora operatore) la post-corrective executable closure: D278/02 62/62 normal e
ASAN/UBSAN, D278/01 secure-session 11/11 normal e ASAN/UBSAN, build live-capable
e self-test PASS, zero `sudo`, zero store protetto, zero USB reale, zero live. Il
vecchio launcher pre-corrective (`SHA256=a48488b0817256d896a77bf2ac037ff5bef10524dd9c018f31d1c2bb5d3a251a`)
è stato ritirato e non è autorizzato per uso futuro; il nuovo candidate
(`SHA256=bf7a1b0dae42d1c17b613c3f03338d10c3448be622e8bc46383f1923f56f192d`) è
diverso e preservato in `/tmp`. La post-corrective executable closure e i relativi
log sono stati revisionati AI-PM con PASS; il launcher candidate è stato inoltre
verificato host-native sul Fedora operatore con ldd e self-test PASS, RC=0 e
zero USB.

Dopo quella review l'Utente ha deciso separatamente e ha eseguito **una sola
seconda** single-shot con quel launcher sulla baseline
`4e5d74770bce6e0a9de929b19279038827abff8c`. La run non ha ritestato E4: ha
inviato il solo A8 (`command_count=1`) e si è chiusa
`SECURE_SESSION_TERMINAL` già in fase A8 (`phase_trace=A8,TERMINAL`,
`LIVE_RC=1`), perché il primissimo frame IN della nuova sessione era
`outer=0xA0`, `control=0xE4`, `body_length=41` — la shape canonica della typed
response E4 — invece dell'ACK A8 atteso, con
`protocol_failure_kind=TYPED_SHAPE_MISMATCH`. Cleanup, drain e safety sono
`PASS`: una open/claim/release/close, un IN e un OUT, zero retry, reopen, reset e
scritture persistenti, secret azzerato, D4/TLS/finger/image irraggiungibili.

Il current critical boundary del percorso nativo si sposta quindi al **protocol
re-entry cross-session**, non più al solo gate E4. Il gap architetturale
host/device provenance è provato staticamente
(`CROSS_SESSION_REENTRY_ARCHITECTURAL_GAP=PROVEN`), il fenomeno è ora osservato
sul target (`TARGET_UNEXPECTED_PRIOR_PHASE_SHAPE_AT_REENTRY=OBSERVED`), ma
l'identità causale con la typed response E4 rimasta dalla prima run resta non
provata (`CROSS_SESSION_RX_RESIDUAL_TARGET_HYPOTHESIS=STRONGLY_LIVE_CORROBORATED`,
`CROSS_SESSION_RX_RESIDUAL_CAUSAL_IDENTITY=UNPROVEN`), perché il wire A0 non
porta provenance e il validator E4 dipende dal solo materiale persistente. Il
correttivo ACK non è stato esercitato in questa run
(`ACK_POLICY_CORRECTIVE_LIVE_RETESTED=false`) e non è refutato
(`ACK_POLICY_CORRECTIVE_REFUTED=false`). D278/05 chiude offline la successiva
design review: dopo A8 la provenance wire è indisponibile; prima di ogni OUT un
frame esclude la causalità di un comando host corrente senza provare identità
con la sessione precedente. Un futuro diagnostico zero-OUT, one-receive e
bounded è `JUSTIFIED_FOR_SEPARATE_REVIEW`, non implementato né autorizzato; un
timeout non proverebbe quiescenza o readiness APP12509. La recovery OEM pre-D1
resta `UNRESOLVED`, mentre il production-shaped C ora mantiene `POISONED`
sticky fino a `img_close` e rifiuta activation prima di generation/backend/USB.
Il confine immediato è quindi la review AI-PM di D278/05 e una decisione
separata sul solo design diagnostico. Nessun retry equivalente è autorizzato:
`CURRENT_LIVE_AUTHORIZED=false`, `READY_FOR_LIVE=false`,
`RETRY_AUTHORIZED=false`, `DO_NOT_RUN_AGAIN=true`,
`TARGET_PROTECTED_MATERIAL_PREFLIGHT_EXECUTED=true`,
`D278_03_LIVE_RESULT=FAIL_E4_PROTOCOL_GATE`,
`D278_03_SECOND_SINGLE_SHOT_RESULT=FAIL_SECURE_SESSION_TERMINAL_AT_A8`,
`D278_03_ACK_POLICY_CORRECTIVE_HOST_ONLY=PASS`,
`D278_03_ACK_POLICY_CORRECTIVE_AI_PM_REVIEW=PASS`,
`NATIVE_SECURE_SESSION_TARGET_PROVEN=false`,
`TARGET_E4_NATIVE_LIVE_PROVEN=false` e `TARGET_TLS_NATIVE_LIVE_PROVEN=false`.

Il boundary A0/AF è stato raggiunto una volta in D250. Il target ha accettato
la submission AF zero-tail e restituito direttamente una A0/AE con checksum
valido e body da 16 byte. La run è terminata nel validator host-side, non per
assenza o malformazione della risposta. Byte 0 non ha semantica positiva
provata; byte 1 bit0 POV valido, bit1 TLS connesso e bit3 locked sono gli usi
OEM verificati, e gli altri bit restano ignoti. Il valore byte0 della run D250
è perduto per gap di osservabilità.

D251 ha chiuso live AF sulla baseline approvata: la singola AE valida con
`byte0=0` ha confermato che il byte è opaco, e `flags=0x02` ha selezionato
fresh-FDT, non D2. Anche il marker D251 è consumato; l'esito non autorizza
retry, secondo D4, secondo AF, FDT o una nuova invocazione.

Il current critical boundary resta offline, ma D255/D256 lo hanno ristretto.
La capture APP12509 prova nella stessa cold attach il cache OTP-bound da 13.520
byte, l'uguaglianza FDT12→primo seed wire, tre `0x36`, cancel senza dito,
re-entry e nuovo `0x32` accettato. D256 prova inoltre che nell'intervallo cancel
non passa traffico target e che, dopo una completion bulk-IN cancellata
host-side, il medesimo device `1:2` continua sugli stessi endpoint senza
abort/reset, descriptor replay, reconfiguration, re-enumeration o restore USB
esplicito. Un restore USB esplicito non è quindi un prerequisito osservato per
la re-entry/re-arm OEM.

Il secondo cancel della stessa capture chiude inoltre il terminal stop
osservabile sul bus. Il nuovo arm frame `214`, ACK `216` e pending IN `217` sono
seguiti da zero packet durante il cancel, poi dalla sola completion cancellata
frame `218`, ultimo frame; per i successivi 491,125998 secondi fino al marker
host finale non viene registrato alcun altro packet. Nessun restore, abort,
reset, reconfiguration o re-enumeration è osservato: il contratto terminal-stop
host/bus è chiuso come quiescenza USB path-bounded.

D257 mantiene chiusi il lifecycle host e il provider cache fail-closed e
riclassifica il vecchio replay come sottosequenza proiettata. D258 chiude la
semantica `0x82` e corregge `0x50`/`0x20` come acquisizioni prima di stage2 con
classificazione soltanto dopo stage2. Il corrective D259 prova meccanicamente
che i return dei due classifier hanno effetto solo su basi/cache host OEM e
nessun riflesso sul contratto device-visible del primo arm; il loro modello
esatto e il plaintext B0 storico D255 non sono blocker del classifier. Il B0
resta obbligatoriamente TLS-consumed subito dopo `0x20`. Questa proprietà e la
continuità del record successivo sono provate offline sulla stessa `SSLObject`,
ma il runtime sealed D245 chiude l'engine a fine handshake e non lo espone.
D260 lascia quel runtime storico invariato e implementa invece nel nuovo core
GPL un coordinator persistente: lo stesso server TLS attraversa D4/AF/FDT A0 e
consuma il B0 baseline prima di stage2. Il rehearsal end-to-end e la matrice
failure passano offline, quindi il gap one-shot è architetturalmente superato,
non live-proven. Il disarm del prior arm, la sua lifetime e lo stato interno
FDT dopo cancel rimangono ignoti
epistemici non bloccanti rispetto al contratto host/bus D256. La TTL generale
del cache resta un'incertezza di successo funzionale, non il solo blocker né
un requisito di factory-preservation.

Il current critical boundary non è più l'implementazione operativa: D261
collega ora adapter USB reale, physical policy FDT zero-tail, privilege model,
binding del secret E4, stop/restore fprintd, marker, verifier della baseline
Git, operator kit e autorizzazione esplicita. Il corrective chiude offline le
prove operative che la prima versione aveva overclaimed: supported entrypoint
unico, capability distinte, gate pre-side-effect, marker post-validazione,
matrice failure execution-derived, deadline reader assoluta e report durable.
La review successiva è chiusa dallo stesso D261: la tuple baseline copre ora
l'intera bounded import closure inclusi i due initializer, l'import è provato
side-effect-free in subprocess pulito e il materiale non-secret viene validato
prima della materializzazione secret. Il full commit SHA
`e9073a171697bd68dd2debabb851f23d007bf718` è ora approvato da Utente e AI-PM
come baseline live-critical immutabile: la governance di readiness è promossa
a review operativa/live. Il boundary immediato era una **AI-PM final risk review**
del bounded fresh-FDT arm sulla baseline approvata; solo dopo tale review, su
nuova autorizzazione hardware esplicita dell'Utente, potrà proseguire un nuovo
step live. L'accettazione target della zero-tail per `0x36/0x50/0x82/0x20`
era il rischio live primario dichiarato, non un fatto già provato; `0x32`
restava provato sul target.

Questa AI-PM final risk review è stata completata e la singola run live
autorizzata è stata eseguita con successo (`PASS_STOP_AFTER_FDT_ARM_ACK`). Sul
target primario `27c6:5125` / firmware `GF_ST411SEC_APP_12509`, lungo il
bounded FDT arm path `0x36,0x50,0x36,0x82,0x20,0x36,0x32`, l'accettazione
zero-tail è ora **live-proven con ACK**, con la seguente tassonomia esplicita
per comando:

```text
0x32 = PRIMARY_TARGET_PROVEN_AND_ACK_ACCEPTED

0x36 / 0x50 / 0x82 / 0x20 = PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
```

Lo scope resta `27c6:5125` / `GF_ST411SEC_APP_12509` sul bounded FDT arm path.
Il rischio primario D262
`FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND` è pertanto ritirato
per questo target/firmware/path. Non si generalizza ad altri device, firmware,
comandi di controllo, flusso post-finger, `0x22`, enrollment/matching o
operazioni di scrittura persistente; `0x22` e il post-finger image non sono
stati raggiunti. Il marker single-use è consumato (`SECOND_LIVE_ATTEMPT_ALLOWED=false`)
e la stessa run non deve essere ripetuta: il prossimo confine live richiede una
nuova AI-PM review e autorizzazione hardware esplicita dell'Utente. Perciò
`READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW=true`,
`READY_FOR_BASELINE_APPROVAL_REVIEW=false`,
`OPERATIONAL_REVIEW_PENDING_APPROVED_BASELINE=false`,
`READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW=false`,
`READY_FOR_FDT_LIVE_REVIEW=false` e `READY_FOR_FDT_LIVE=false`: D262 ha aperto
hardware una sola volta in single-shot e si è chiuso, non autorizzando alcun
passo successivo; tutti i gate READY_FOR_* a qualificazione non avvenuta restano
false. D261 non aveva aperto hardware e non auto-approva una run.

Il successivo confine first-image è stato aperto prima in D265/02, che si era
chiuso fail-closed nella wait IRQ2 per il difetto deterministico del router, e
poi una sola volta in D267/01 sulla nuova baseline approvata
`219c038600deb87da1cd93340b9bd07c14e1f5fe`. D267/01 chiude definitivamente i
dubbi live sul tratto `finger-down IRQ2 -> router D266 -> un 0x22 fixed64 -> ACK
target -> primo B0`: tutti questi passaggi sono provati. D267/01 si era però
fermata fail-closed nel decoder `first_image_decode_failed`; il trailer della
run non fu conservato e resta `UNKNOWN`, quindi la causa fu allora soltanto
un'ipotesi `MEDIUM`.

D268 ha poi eseguito, una sola volta e sempre tramite il Kit Operatore D268 sulla
baseline approvata `c03d32e8647444495e6615e41c2839cbddd62143`, il confine
first-image fino al decode. L'esito è `PASS_STOP_AFTER_FIRST_IMAGE`: il primo
payload immagine usa trailer `0x88`, non coincide con il checksum additivo
(`FIRST_IMAGE_PAYLOAD_CHECKSUM_MATCH=False`), la policy image-specific
`NO_CHECK_0X88_ACCEPTED` lo accetta, il CRC-32/MPEG-2 del record risulta valido
(`FIRST_IMAGE_RECORD_CRC_MATCH=True`) e il raster `80x64` è decodificato con
successo (`FIRST_IMAGE_DECODE_STAGE=successful_raster_decode`). Il boundary
first-image è pertanto ora **chiuso live** sul target APP12509: la semantica
`0x88` non è più soltanto corroborata staticamente ma **target-proven**, il
mismatch additivo è osservato e il CRC record è osservato valido.

La classificazione epistemica di D267/01 è ora: ricezione del primo B0 e
`first_image_decode_failed` sono **osservati**; il trailer effettivo di quella
run è **UNKNOWN**. In D268 il trailer `0x88` e il mismatch del checksum additivo
sono **osservati target-specific live**; il mismatch del vecchio parser strict
additivo con `0x88` è **verificato** (D267/04 sul call-flow OEM locale). La causa
di D267/01 è pertanto una **inferenza causale forte**
(`D267_01_CAUSE=STRONG_CAUSAL_INFERENCE`), non un'osservazione retroattiva del
trailer `0x88`: D267/01 non viene riscritto come se avesse registrato `0x88`
allora.

La run D268 mantiene retry, recovery, reopen, write persistenti e comandi
post-image vietati tutti a zero; cleanup host (`HOST_CLEANUP=OBSERVED`) e zeroizzazione secret (`SECRET_ZEROIZATION=OBSERVED`) sono osservati, e il restore fprintd è `FPRINTD_RESTORE_CALLBACK_COMPLETED_WITHOUT_EXCEPTION=VERIFIED_BY_CONTROL_FLOW` mentre `EXTERNAL_FPRINTD_FINAL_STATE=NOT_INDEPENDENTLY_OBSERVED`. Il marker D268 è consumato e la run non deve essere
ripetuta. Ne segue:

```text
IRQ2_HOST_DELIVERY_LIVE_PROVEN=true
0x22_FIXED64_ACK_LIVE_PROVEN=true
FIRST_B0_LIVE_RECEIVED=true
FIRST_IMAGE_DECODE_LIVE_PROVEN=true
FIRST_IMAGE_LIVE_PROVEN=true
FIRST_IMAGE_RECEIVED=true
IMAGE_0X88_NO_CHECK_TARGET_PROVEN=true
IMAGE_ADDITIVE_CHECKSUM_MISMATCH_LIVE_OBSERVED=true
IMAGE_RECORD_CRC_LIVE_PROVEN=true
FIRST_IMAGE_RASTER_SHAPE=80x64
D268_MARKER_CLAIMED=true
D268_RETRY_AUTHORIZED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

### D272/01: validazione target SIGFM pre-live, solo offline

D272/01 parte dal commit D271 completo
`fdc52d04995d65d1e2a895a373e1fe7e24e6fa9f` sul branch `development`, con
working tree iniziale pulita e ancestor check PASS. Non ha aperto USB, letto
secret, contattato fprintd, acquisito biometria o inviato comandi reali.

#### Lifecycle dopo la prima immagine

L'evidenza primaria già hash-gated in
`analysis/D263/D263_01_post_arm_order.json` mostra, con indici zero-based:

| Ordine | Evento | Classe D272 | Limite |
| --- | --- | --- | --- |
| 1 | first B0, packet 231 | `OBSERVED`, decode `VERIFIED` live da D268 | terminale nel runtime corrente |
| 2 | `0x34 {0a01 || 808780948081807a807f8086}`, packet 233 | `OBSERVED` | origine/freshness/validità futura tabella up `UNKNOWN` |
| 3 | ACK `B0/34/01`, packet 235 | `OBSERVED` | il modello offline lo rende obbligatorio, `status` esatto `0x01` e fail-closed |
| 4 | IRQ `0x0200`, packet 237 | `OBSERVED`; finger-up fortemente supportato; Rocky `THIRD_PARTY_CORROBORATION` | timeout target `UNKNOWN` |
| 5 | `0x20 {0100}`, packet 238; ACK packet 241 | `OBSERVED` | nessuna semantica di qualità inventata |
| 6 | B0 post-up, packet 243 | `OBSERVED` | contenuto no-finger/qualità non promosso |
| 7 | `0x50 {0100}`, ACK e risposta, packet 244/247/249 | `OBSERVED` | passaggio omesso nella sequenza abbreviata ma obbligatorio nella capture |
| 8 | `0x32` re-arm, packet 251; ACK packet 253 | `OBSERVED` | usa tabella down della sessione |
| 9 | prossimo IRQ2 → `0x22` → seconda fingerprint image | `INFERRED` per composizione con packet 220–231 | non osservato dopo il re-arm packet 251 |

Il nuovo `BoundedMultiFrameRunner` rappresenta esattamente questo ordine su un
channel iniettato con un solo `read_next`. Accetta solo un opt-in esplicito da
2 a 8 ruoli, consuma l'immagine post-up senza conservarla, include `0x50`, non
ha retry/reopen/recovery e non emette comandi dopo l'ultimo sample. È un modello
sintetico: non modifica `PersistentRuntimeCoordinator`, il default D268 resta
first-image terminale e nessuna policy fisica autorizza `0x34`.

#### Policy ACK esatta del ciclo multi-frame (corrective post-review AI-PM)

La prima implementazione D272/01 di `_command_ack()` accettava
`ack.status in (0x01, 0x07)`. Questa policy era **più permissiva
dell'evidenza target-specifica** e contraddiceva il contratto già dichiarato in
`analysis/D272/D272_01_multiframe_contract.json`
(`mandatory exact ACK; no optional/permissive fallback`). Dopo review AI-PM è
stata corretta in un confronto esatto con `EXPECTED_ACK_STATUS = 0x01`.

La fonte è `analysis/D263/D263_01_post_arm_order.json`, classificata
**target-specific primary evidence** (capture hash-gated, firmware
`GF_ST411SEC_APP_12509`): tutti gli ACK del ciclo pertinente hanno `status=0x01`.

| Control | ACK target osservato | Packet zero-based | Policy corretta |
| --- | --- | --- | --- |
| `0x34` | `0x01` | 235 | esatto `0x01` |
| `0x20` | `0x01` | 241 | esatto `0x01` |
| `0x50` | `0x01` | 247 | esatto `0x01` |
| `0x32` | `0x01` | 253 (e 223 pre-first-image) | esatto `0x01` |
| `0x22` | `0x01` | 229 | esatto `0x01` |

Il seam D272 richiede quindi che `ACK_ECHO` sia uguale al control atteso e che
`ACK_STATUS` sia esattamente `0x01`; qualsiasi altro valore, incluso `0x07`, è
fail-closed e non emette alcun comando successivo. Non esistono tabelle di
status multiple, fallback, retry o recovery in questo percorso.

La distinzione rispetto al resto del codice è **intenzionale e non un difetto**:
`core/cold_start.py` (`ALLOWED_ACK_STATUSES`) e `core/post_d4.parse_ack()`
restano `0x01|0x07` perché `0x07` è realmente target-osservato live nelle fasi
di bring-up pre-TLS (D241: `E4`, `A2`, `0x82`, `0xA6`, `0x70`, `0x80`, `0x90`).
Quel set permissivo è corretto per quelle fasi e non deve propagarsi al ciclo
post-arm, dove non è mai stato osservato. I due parser globali non sono stati
modificati da questo corrective.

```text
D272_ACK_STATUS_CONTRACT=CLOSED_OFFLINE_EXACT_0X01
ACK_0X07_ACCEPTED=false
```

Il corrective è locale e deterministico: non cambia l'ordine
`0x34 → IRQ0200 → 0x20 → image → 0x50 → response → 0x32`, il mapping D269, il
seam metrico SIGFM, il privacy contract, i timeout candidate, la semantica delle
tabelle up/down, la dipendenza OpenCV o lo stato live-disabled del kit operatore.
**Non modifica i blocker primari D272**, che restano aperti.

#### Seam SIGFM e privacy

Il wrapper LGPL C++ usa `goodix_u16_to_fpimage()` e il vero ABI locale
`sigfm_extract`/`sigfm_keypoints_count`/`sigfm_match_score`/`sigfm_free_info`.
L'API è opaca ed effimera: non espone `sigfm_serialize_binary`, file, rete,
USB o TLS. Meno di 25 keypoint è `KEYPOINT_GATE_FAILED`; score zero è successo,
score negativo è `MATCH_ERROR`; eccezioni di extract, keypoint, match e destroy
non attraversano il confine C. Il buffer u8 sullo stack viene azzerato; non è
possibile garantire l'azzeramento di copie o allocazioni interne OpenCV.

Il double sintetico verifica dimensioni, mapping D269, determinismo, gate,
score/error, eccezioni e lifetime con warning severi e ASan/UBSan. Questo non
misura feature reali. Né host né Flatpak SDK installato forniscono OpenCV4-dev;
come imposto dal task non è stato installato nulla. La build/link del SIGFM
reale resta quindi non eseguita e impedisce executable closure PASS.

Il piano futuro, non eseguito, limita una singola run a sei ruoli anonimi
`A1,A2,A3,B1,B2,B3`: coppie interne ad A/B sono same-finger, coppie A:B sono
different-finger. Può produrre soltanto stato extract, keypoint count/gate,
relazione, stato/score match e failure class. Non assume threshold 20 o 40 e
serve solo a `FEASIBILITY_AND_THRESHOLD_CANDIDATE_VALIDATION`, non a una
calibrazione production.

#### Riesame metodologico prima di qualsiasi futuro live

1. Il metodo dovrà cambiare chiudendo con evidenza target origine/freshness
   della tabella `0x34`, l'intera seconda iterazione e il gate `0x50`, oltre a
   compilare il SIGFM reale in un ambiente OpenCV4-dev già disponibile.
2. Solo allora l'ipotesi tecnica sarà che una tabella up valida per la sessione
   permetta il ciclo release/re-arm completo e che raster target distinti
   producano keypoint e score SIGFM preliminarmente separabili.
3. Un fallimento allo stesso confine non autorizzerà una ripetizione: si
   tornerà ad audit offline della capture/call-flow o del build environment,
   senza nuova micro-run.

Stato canonico:

```text
OUTCOME=BLOCKED_POST_FIRST_IMAGE_UP_TABLE_SECOND_CYCLE_AND_OPENCV4_DEV
ADVANCEMENT=NEW_OFFLINE_MULTIFRAME_MODEL_AND_SIGFM_EXCEPTION_PRIVACY_SEAM
EXECUTABLE_CLOSURE=FAIL
ACK_POLICY_CORRECTIVE=PASS
D272_ACK_STATUS_CONTRACT=CLOSED_OFFLINE_EXACT_0X01
ACK_0X07_ACCEPTED=false
CORRECTIVE_EXECUTABLE_CLOSURE=PASS
FEATURE_EXTRACTOR_POLICY=CLOSED_OFFLINE_SIGFM_VALIDATION_CANDIDATE
SIGFM_STATUS=OFFLINE_METRIC_SEAM_SYNTHETIC_PASS_REAL_BUILD_BLOCKED_OPENCV4_DEV
SIGFM_EXCEPTION_CONTAINMENT=CLOSED_OFFLINE_AT_C_ABI
SIGFM_METRIC_PRIVACY_CONTRACT=CLOSED_OFFLINE_NO_SERIALIZATION
MULTIFRAME_CAPTURE_LIFECYCLE_STATUS=OFFLINE_MODEL_PASS_LIVE_INTEGRATION_BLOCKED
D272_ACK_STATUS_CONTRACT=CLOSED_OFFLINE_EXACT_0X01
POST_FIRST_IMAGE_0X34_STATUS=OBSERVED_PAYLOAD_UP_TABLE_PROVENANCE_AND_FRESHNESS_UNKNOWN
FINGER_UP_IRQ_0200_STATUS=OBSERVED_AFTER_0X34_ACK_TARGET_TIMEOUT_UNKNOWN
POST_FINGER_UP_0X20_STATUS=OBSERVED_WITH_ACK_AND_B0_SEMANTICS_NOT_QUALITY_PROVEN
REARM_0X32_STATUS=OBSERVED_WITH_ACK_SECOND_CYCLE_COMPLETION_NOT_OBSERVED
BIOMETRIC_QUALITY_STATUS=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
FULL_FPIMAGE_PIPELINE_CONTRACT=PARTIALLY_CLOSED
NEXT_PRIMARY_BOUNDARY=POST_FIRST_IMAGE_MULTIFRAME_CONTRACT_CLOSURE_AND_REAL_SIGFM_BUILD
NEXT_BOUNDARY_PREREQUISITE=TARGET_CLOSE_0X34_UP_TABLE_AND_SECOND_CYCLE_PLUS_EXISTING_OPENCV4_DEV_ENVIRONMENT
BASELINE_APPROVED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
LIVE_EXECUTION=NOT_PERFORMED
```

### D273/01: dataflow multi-frame e build SIGFM reale, solo offline

D273/01 parte dal corrective D272 completo
`062c05a1fbe198c858eaeba4b86db1d24eb79f39` sul branch `development`, con
working tree iniziale pulita e ancestor check PASS. Non ha aperto USB, inviato
comandi Goodix, materializzato secret, contattato fprintd o acquisito biometria.

Il census programmatico delle capture target-specific locali conferma una sola
sequenza positiva in `rilevamento.pcapng` hash
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`.
La seconda fonte, la capture D255 hash
`802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c`,
è zero-finger e non contiene IRQ2 o record positivo. Nella fonte positiva il
packet 249 è A0, control `0x50`, physical/outer length 2417 e inner length
2410. È quindi la response command-specific NAV, non un B0/TLS. Il DLL OEM
conferma la semantica: `chicagoHUget_navdata` a `0x180067874` usa mode 5 e
copia il NAV buffer volatile di sessione al caller.

L'audit statico del `gfusb.dll` hash
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`
chiude il dataflow FDT:

- `0x180028480` può inizializzare entrambe le globali up/down o una sola;
- il ramo IRQ `0x0002` del dispatcher chiama `0x180029314`, che valida la base
  raw, deriva sei word e aggiorna la globale up `0x180580838`;
- il builder FDT-up `0x1800250d0–0x1800251b5` copia direttamente tale globale
  nel body `0a 01 || table12` del `0x34`;
- nel ramo normale IRQ `0x0200`, `0x180029210` aggiorna la globale down
  `0x180580818`, poi consumata dal builder `0x32` con timestamp;
- il valore up osservato a packet 233 è quindi session data, non una costante
  APP12509.

La freshness è classificata `STRONG_CAUSAL_INFERENCE`: IRQ2 packet 225 precede
il builder `0x34` packet 233 nello stesso ciclo e il dataflow statico collega
esattamente quell'evento alla globale consumata. Il modello offline rende ora
eseguibile tale contratto: `DerivedFdtTable` lega 12 byte a source IRQ e
generation; IRQ0200 deve fornire la down table corrente per il `0x32`, mentre
il successivo IRQ2 fornisce la up table della generation seguente. Una tabella
stale, con source errata o lunghezza errata fallisce chiuso. I timestamp sono
forniti per transizione e la NAV response richiede control/lunghezze target
`0x50/2417/2410`.

La capture positiva termina però all'ACK packet 253 del re-arm. Il DLL espone
dispatcher IRQ2, builder immagine e consumer ripetibili, ma il call graph non
chiude univocamente l'ownership dell'intero edge nello stesso lifecycle. Rocky
corrobora apprendimento up/down e ciclo FDT, ma diverge nella coda post-`0x34`
e resta fonte terza, non prova target. La seconda iterazione e i timeout target
restano quindi aperti; una eventuale nuova fonte minima dovrebbe osservare un
solo segmento Windows OEM bounded `0x32 ACK → IRQ2 → 0x22 ACK → fingerprint
B0`, senza conservare nel bundle raw, plaintext o biometria. D273 non crea un
Operator Kit e non autorizza tale acquisizione.

Sul boundary SIGFM, host e SDK Flatpak 25.08 installato non espongono
`opencv4.pc`; l'host non ha inoltre un frontend C++ rilevato. Nello SDK isolato
dalla rete, GCC/G++ hanno compilato con warning severi adapter D269, wrapper e
harness synthetic-only reale. La compilazione del vero `sigfm.cpp` fallisce su
`opencv2/core/mat.hpp` mancante; link e runtime sono `NOT_AVAILABLE`. Nessuna
installazione o vendorizzazione è stata eseguita. L'harness non serializza e
non introduce claim di qualità, sufficienza keypoint target, separazione,
polarity, orientation o threshold.

Stato canonico D273:

```text
OUTCOME=PARTIAL_CLOSURE_UP_TABLE_AND_POST_0X50_CLOSED_SECOND_TARGET_CYCLE_AND_REAL_SIGFM_BUILD_BLOCKED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED_AND_OFFLINE_MODEL_CORRECTED
EXECUTABLE_CLOSURE=FAIL_REAL_SIGFM_NOT_AVAILABLE
MULTIFRAME_CONTRACT=PARTIALLY_CLOSED_TARGET_SECOND_CYCLE_NOT_OBSERVED_AND_TARGET_TIMEOUTS_UNCLOSED
MULTIFRAME_MODEL_EXECUTABLE_CLOSURE=PASS_OFFLINE
UP_TABLE12_SOURCE=OEM_SESSION_GLOBAL_GF_FDT_UP_BASE_VA_0X180580838
UP_TABLE12_DERIVATION=IRQ_0X0002_RAW_BASE_VALIDATION_THEN_PER_WORD_HALF_PLUS_CONTEXT_OFFSET_ENCODING_AND_MODE_DEPENDENT_COMMIT_BY_0X180029314
UP_TABLE12_LIFETIME=VOLATILE_OEM_PROCESS_SESSION_GLOBAL_INITIALIZABLE_BY_CALLBACK_0X180028480_AND_UPDATED_BY_FDT_IRQ_HANDLING
UP_TABLE12_FRESHNESS_REQUIREMENT=0X34_MUST_CONSUME_THE_MOST_RECENT_VALID_IRQ_0X0002_DERIVED_TABLE_FROM_THE_SAME_FINGER_DOWN_CYCLE
POST_FIRST_IMAGE_0X34_STATUS=OBSERVED_BUILDER_AND_SESSION_TABLE_DATAFLOW_VERIFIED_STATICALLY
FINGER_UP_IRQ_0200_STATUS=OBSERVED_AFTER_0X34_ACK_TARGET_TIMEOUT_UNKNOWN
POST_FINGER_UP_0X20_STATUS=OBSERVED_WITH_ACK_AND_POST_UP_B0_IMAGE_ROLE_STATICALLY_SUPPORTED_NO_QUALITY_CLAIM
POST_FINGER_UP_0X50_STATUS=OBSERVED_WITH_EXACT_ACK_AND_OEM_NAV_GETTER_VERIFIED
POST_0X50_RESPONSE_STATUS=OBSERVED_A0_0X50_NAV_RESPONSE_LENGTHS_2417_2410
REARM_0X32_STATUS=OBSERVED_WITH_ACK_AND_CURRENT_IRQ0200_DERIVED_DOWN_TABLE_CONTRACT
SECOND_CYCLE_STATUS=TARGET_CAPTURE_NOT_OBSERVED_STATIC_COMPONENTS_PARTIALLY_VERIFIED
D272_ACK_STATUS_CONTRACT=CLOSED_OFFLINE_EXACT_0X01
ACK_0X07_ACCEPTED=false
OPENCV4_DEV_ENVIRONMENT=NOT_AVAILABLE
REAL_SIGFM_BUILD=BLOCKED_OPENCV4_DEV_NOT_AVAILABLE
REAL_SIGFM_EXECUTABLE_CLOSURE=FAIL_NOT_AVAILABLE
SIGFM_STATUS=OFFLINE_METRIC_SEAM_SYNTHETIC_PASS_REAL_BUILD_BLOCKED_OPENCV4_DEV
SIGFM_EXCEPTION_CONTAINMENT=CLOSED_OFFLINE_AT_C_ABI
SIGFM_METRIC_PRIVACY_CONTRACT=CLOSED_OFFLINE_NO_SERIALIZATION
BIOMETRIC_QUALITY_STATUS=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED
FULL_FPIMAGE_PIPELINE_CONTRACT=PARTIALLY_CLOSED
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
D273_TARGET_EVIDENCE_GAP=EXACT_MINIMUM_NEW_OBSERVATION_REQUIRED
HISTORICAL_NEXT_PRIMARY_BOUNDARY_AFTER_D273=AI_PM_REVIEW_D273_PARTIAL_CLOSURE
HISTORICAL_NEXT_BOUNDARY_PREREQUISITE_AFTER_D273=NONE_FOR_REVIEW_EXPLICIT_AUTHORITY_REQUIRED_FOR_ANY_NEW_CAPTURE_OR_ENVIRONMENT_CHANGE
 BASELINE_APPROVED=false
 LIVE_AUTHORIZED=false
 READY_FOR_LIVE=false
 LIVE_EXECUTION=NOT_PERFORMED
 ```

### D273/01 corrective: verità probatoria, provenance Rocky e exact NAV control

Corrective locali deterministici (D273/01, su baseline
`5ef14c5051726fe6bc6624de86d3885f3306776e`; corrective 2 su
`7c991143e3670f6262f23e6159edde9e240c4287`) che ripristinano solo metadati
probatori, provenance Rocky e il classificatore NAV, senza cambiare il boundary
tecnico D273.

Primo difetto (corrective 1): `analysis/D273/d273_01_offline_capture_audit.py`
deduceva un `logical_control` universale con `wire & 0xfe`, e
`analysis/D273/D273_01_multiframe_evidence_matrix.json` riportava una provenance
Rocky errata. Corrective 1: il `wire_control` esatto è sempre preservato; un
`logical_control` semantico è emesso solo per gli ACK (echo realmente osservato)
e marcato `NOT_DERIVED` negli altri frame A0; un control dispari non
appartenente alla regola (es. D1 wire `0xd1`) non è più pubblicato falsamente
come `0xd0`; `rocky_snapshot_commit` è riallineato a
`227eba219fa9e3fbac5bd59aca79f624f67cd11b` (canonico in
`Rockytkg/PROVENANCE.md`). Coerente con il contratto di trasporto §Trasporto
USB («Non è corretto dedurre sempre il logico con `wire & 0xfe`»).

Review indipendente (corrective 2): il classificatore della response NAV usava
ancora `wire_control & 0xFE == 0x50`, semanticamente troppo permissivo (es. un
ipotetico `0x51` sarebbe stato etichettato `A0_0X50_NAV_RESPONSE`). Corrective
2: il classificatore NAV usa ora l'exact match `wire_control == 0x50` (senza
masking, parità, even/odd normalization). Aggiunti test sintetici diretti sul
classificatore: `0x50` → `A0_0X50_NAV_RESPONSE`; `0x51` → NON NAV, resta
`A0_COMMAND_OR_RESPONSE`. Aggiunta source-guard bounded sul solo script D273 che
fallisce chiuso se ricompare `wire_control & 0xfe`/`0xFE`. La claim
`GENERIC_WIRE_TO_LOGICAL_MASK_REMOVED=true` è ora letteralmente vera per l'audit
D273.

`analysis/D273/D273_01_capture_census.json` rigenerato in modo deterministico:
packet 249 resta `A0_0X50_NAV_RESPONSE` con control `0x50`, length 2417/2410;
gli ACK conservano echo/status osservati; nessun payload B0/plaintext/raster
serializzato. Nessuna classificazione tecnica Rocky cambia: resta
`THIRD_PARTY_CORROBORATION`. Nessuna conclusione D273 (dataflow up-table, NAV
packet 249, blocker seconda iterazione, blocker OpenCV4-dev) cambia per effetto
dei corrective.

```text
D273_EVIDENCE_METADATA_CORRECTIVE=PASS
GENERIC_WIRE_TO_LOGICAL_MASK_REMOVED=true
D273_NAV_CLASSIFICATION_WIRE_CONTROL=EXACT_0X50
D273_0X51_NAV_ALIAS_ACCEPTED=false
ROCKY_PROVENANCE_REALIGNED_TO=227eba219fa9e3fbac5bd59aca79f624f67cd11b
D273_TECHNICAL_CONCLUSIONS_UNCHANGED=true
```

### D274/01: Kit Windows/OEM multi-frame, solo pre-live offline

D274/01 non esegue una capture e non modifica il runtime Linux. Crea il kit
dedicato `operator_kit/d274-windows-multiframe-evidence.ps1`, il postprocessor
offline e lo schema evidence sotto `analysis/D274/`. La superficie PowerShell
espone soltanto self-test, preflight, simulazione pre-autorizzazione e il flag
nominale della futura autorizzazione; quest'ultimo termina sempre
`HARD_DISABLED_D274_01` perché `D274_REAL_CAPTURE_CAPABILITY=0` è costante nel
sorgente e non esiste alcun bypass via flag, ambiente o configurazione. Nel
sorgente D274/01 non esistono `Start-Process` né argomenti di capture TShark.

Il preflight futuro verifica Windows PowerShell 5.1, disponibilità/versione
TShark, discovery USBPcap, target assente dal guest prima della capture,
destinazione privata `captures/` verificata privata (path canonico sotto la
repository root, nessun reparse-point/junction/symlink, `Get-Acl` valutabile e
nessun ACE Allow a principal generici — Everyone, BUILTIN\Users, Authenticated
Users, Guests — per read/write/modify/full-control; i principal
amministrativi host e l'utente corrente restano ammessi per policy), assenza di
marker concorrente, clock UTC, deadline 180 s e presenza del postprocessor.
L'unicità del target dopo attach è un gate definito ma non eseguito nel
preflight pre-attach. La UI fingerprint resta `UNKNOWN_BEFORE_ATTACH`, secondo
la lezione D255. D274/01 resta pre-live e non muta ACL.

#### Audit del workflow storico

Gli artefatti D230/D263 identificano la capture positiva recuperata e il suo
hash, ma non conservano marker, UI, comando TShark o workflow OEM. La
classificazione è quindi:

```text
D263_CAPTURE_WORKFLOW_CLASS=UNKNOWN
```

D255 prova separatamente che `WINDOWS_HELLO_SETUP_NO_FINGER` è disponibile
dopo attach sul guest usato allora, ma la sua capture è zero-finger e non è la
fonte positiva D263. Per una futura run il setup Windows Hello è soltanto il
candidato locale meglio supportato:

```text
WINDOWS_OEM_WORKFLOW_SELECTED=WINDOWS_HELLO_SETUP_CANDIDATE_NO_COMMIT
WINDOWS_ENROLLMENT_COMMIT_AUTHORIZED=false
WINDOWS_ACCOUNT_MUTATION_AUTHORIZED=false
WINDOWS_PIN_MUTATION_AUTHORIZED=false
```

Il candidato deve essere abbandonato al primo boundary di commit enrollment,
nuovo PIN, mutazione account/credenziali o terzo dito. Non si cancellano
enrollment esistenti e non si modificano policy, registry, service o PnP.

#### Evidence boundary, privacy e timing

Il postprocessor richiede SHA-256 esplicito prima del parsing, linktype
USBPcap 249, un solo descriptor `27c6:5125` e A8
`GF_ST411SEC_APP_12509` nella stessa capture. Ricostruisce A0/B0 senza
serializzare payload e applica l'esatta sequenza:

```text
first IRQ2 → 0x22 → ACK 0x01 → first B0
→ 0x34 → ACK → IRQ0200 → 0x20 → ACK → post-up B0
→ exact 0x50 → ACK → exact A0 0x50 NAV 2417/2410
→ 0x32 → ACK → second IRQ2 → 0x22 → ACK 0x01 → second B0 → STOP
```

Il NAV richiede wire control esatto `0x50`; `0x51` non è alias. Tutti gli ACK
del ciclo richiedono echo esatto e status `0x01`. I B0 esportano soltanto
indice frame, direzione, outer wrapper, lunghezza fisica/dichiarata, classe TLS
esterna, timestamp relativo e associazione implicita al campo di ciclo. Nessun
payload hash o derivato biometrico viene prodotto.

Per essere promosso a `FINGERPRINT_B0` (e quindi a `first_image_b0`,
`post_up_b0` e `second_b0` della sequenza) un B0 deve essere strutturalmente
coerente con il boundary target: direzione device-to-host, outer `0xB0` non
troncato, lunghezza totale outer esatta 7726 byte, lunghezza B0 dichiarata 7722,
record TLS `17 03 03` con la lunghezza del record in network byte order
(big-endian), distinta dalla lunghezza outer B0 Goodix in little-endian, e
`TLS_record_declared_length + 5 == declared_B0_length`.
Non viene decriptato né ispezionato il payload applicativo. Un B0 generico
(`B0_OTHER`) — alert TLS, lunghezza diversa, length incoerente o direzione
host→device — non chiude il secondo ciclo e fallisce chiuso con
`FIRST/POST_UP/SECOND_B0_NOT_FINGERPRINT_SHAPE`.

La capture target storica hash-gated attraversa il primo ciclo fino all'ACK
del re-arm e poi termina; il nuovo tool la classifica
`failure_class=MISSING_SECOND_IRQ2`, coerentemente con D273. Non è nuova
evidenza e non cambia `SECOND_CYCLE_STATUS`.

Timing osservato nella stessa fonte: ACK `0x32` iniziale → IRQ2 7.108 s e
finestra re-arm iniziale → ACK finale 8.383 s. D255 misura 62.884 s da
`VM_USB_ATTACH_BEGIN` a `HELLO_SETUP_UI_READY`. La deadline D274 è una sola,
180 s, scelta con margine sopra entrambe le osservazioni:

```text
D274_HOST_CAPTURE_DEADLINE_POLICY=EVIDENCE_BOUNDED_NOT_DEVICE_TIMEOUT_CLAIM
D274_HOST_CAPTURE_DEADLINE_SECONDS=180
D274_DEVICE_SEMANTIC_TIMEOUT=UNKNOWN
```

#### Chiusura sintetica e stato

La suite genera pcapng/eventi interamente sintetici e copre happy path, assenza
del secondo IRQ2/`0x22`, comandi `0x20`/`0x50` errati, `0x51`, ACK echo/status,
B0 anticipato, terzo ciclo, duplicati, re-enumeration, secondo target, metadata
troncati, A0/B0 malformati, deadline, marker fuori ordine e terminal condition
UI. Il run da Git root e da `/tmp` passa. `pwsh` non è installato sull'host
Fedora: la verifica nativa Windows resta correttamente `NOT_AVAILABLE`, mentre
il source/static contract è verificato offline.

#### Corrective D274/01 — quattro overclaim chiusi (review AI-PM)

La review AI-PM ha chiuso quattro overclaim del kit pre-live:

1. **B0 generico ≠ fingerprint B0.** Il `_event` accettava ogni B0 come
   `kind=B0` e lo promuoveva a `SECOND_CYCLE_FINGERPRINT`. Ora esiste un
   classificatore esplicito `classify_b0` che distingue `FINGERPRINT_B0` (solo
   device-to-host, outer `0xB0` non troncato, totale outer 7726 byte, B0
   dichiarato 7722, record TLS `17 03 03` con la lunghezza del record in
   network byte order / big-endian, e `TLS_record_declared_length + 5 ==
   declared_B0_length`) da `B0_OTHER`. La sequenza richiede `FINGERPRINT_B0` per
   `first_image_b0`, `post_up_b0` e `second_b0`; un B0 generico (alert TLS,
   lunghezza diversa, length incoerente o direzione host→device) fallisce chiuso
   con `FIRST/POST_UP/SECOND_B0_NOT_FINGERPRINT_SHAPE` e non chiude il secondo
   ciclo. Non viene decriptato né esportato alcun payload.
2. **Writable ≠ private.** Il preflight verificava solo creazione/scrittura della
   destination. Ora `Test-D274PrivateOutputRoot` impone il contract di privacy:
   path canonico `<repo>\captures`, nessun reparse-point/junction/symlink,
   `Get-Acl` valutabile e nessun ACE Allow a principal generici (Everyone,
   BUILTIN\Users, Authenticated Users, Guests) per read/write/modify/full-control;
   i principal amministrativi host e l'utente corrente restano ammessi. La claim
   `output_root_private_writable=true` è emessa solo dopo il check reale; in
   caso contrario il preflight fallisce chiuso. D274/01 non muta ACL.
3. **`CREDENTIAL_MUTATION_UI` terminale e marker sconosciuti falliscono.** Il set
   terminale ora include `ENROLLMENT_COMMIT_UI`, `ACCOUNT_MUTATION_UI`,
   `PIN_MUTATION_UI`, `CREDENTIAL_MUTATION_UI`, `THIRD_FINGER_PROMPT` e
   `THIRD_FINGERPRINT_B0`. Ogni marker deve appartenere a `MARKER_ORDER` o a
   `UI_TERMINAL_MARKERS`; un marker sconosciuto (es. `SOMETHING_UNKNOWN`) fallisce
   chiuso con `UNKNOWN_MARKER`; i marker terminali restano failure terminali
   (`UI_TERMINAL_CONDITION`); quelli ordinari restano monotonici strict senza
   duplicati. La distinzione fra marker umano e osservazione wire è preservata.
4. **JSON parse ≠ istanza evidence validata.** Lo schema ora tipizza i frame
   metadata con `additionalProperties: false` (solo `frame`, `direction`,
   `outer_wrapper`, `physical_length`, `declared_outer_length`,
   `relative_timestamp_ms` e, opzionali, `declared_b0_length`,
   `tls_record_type_class`, `cycle_association`), vietando implicitamente
   `raw`/`body`/`payload`/`plaintext`/`image`/`raster`/`pixel`/`hash`/
   `descriptor`/`template`/`secret`/`psk`. La validazione non si ferma al parse:
   `D274_01_prelive_corrective_test_results.json` esegue realmente la validazione
   dello schema su evidenza happy-path sintetica, evidenza storica sanitizzata,
   e fixture negative (campo `raw` aggiunto, tipo errato, campo richiesto
   assente). `jsonschema` non è disponibile sull'host, quindi il corrective
   implementa e dichiara onestamente un validator locale strict equivalente
   (`STRICT_LOCAL_SCHEMA_VALIDATOR=PASS`), senza fingere una validazione
   library-backed.

#### Corrective D274/01 — finalizzazione in-place (review AI-PM successiva)

La review successiva ha individuato tre difetti reali ancora presenti nel
corrective corrente e li ha corretti in-place, senza aprire D274/02 e senza
creare un "corrective 2". Non è stata eseguita alcuna capture, alcun accesso
USB, alcuna decriptazione o alcuna mutazione ACL.

- **A — TLS record length interpretata little-endian.** Il classificatore
  leggeva `frame.raw[7:9]` come little-endian, e le fixture codificavano la
  lunghezza del record TLS in little-endian (`17 03 03 25 1e`). Il record layer
  TLS è network byte order (big-endian), quindi l'header realistico è
  `17 03 03 1e 25` (7717 = `0x1e25`). Corretto: il classificatore usa
  `int.from_bytes(frame.raw[7:9], "big")` e le fixture codificano la lunghezza
  TLS in big-endian; la lunghezza outer B0 Goodix (`raw[1:3]`) resta
  little-endian. È stato aggiunto un test che costruisce esplicitamente
  l'header `17 03 03 1e 25` (FINGERPRINT_B0) e la variante little-endian
  `17 03 03 25 1e` (B0_OTHER), impedendo alla fixture sintetica di ridefinire la
  semantica TLS.
- **B — il check ACL non chiudeva davvero la privacy.** `Test-D274PrivateOutputRoot`
  elencava `Write/Modify/FullControl` ma ometteva `Read`, quindi un ACE
  `Everyone: Read` non veniva respinto; inoltre controllava `AceType` anziché
  `AccessControlType` (il discriminante allow/deny su `FileSystemAccessRule`), e
  confrontava principal in forma nominale (non robusto su Windows localizzato).
  Corretto: il mask dei diritti include ora `Read` (intercettando anche
  `ReadAndExecute`/`ReadData` via band), il discriminante è
  `AccessControlType -eq Allow`, e l'`IdentityReference` è normalizzata a
  `SecurityIdentifier` tramite `Translate(...)`; la traduzione SID fallita è
  fail-closed. I quattro SID canonici (S-1-1-0, S-1-5-32-545, S-1-5-11,
  S-1-5-32-546) sono rifiutati se concedono un diritto coperto dal mask. Non
  viene usato `Set-Acl` né `icacls`; D274 resta pre-live. Il contratto è una
  closure source/policy offline, non una verifica nativa Windows (vedi
  `WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=NOT_AVAILABLE`).
- **C — il fallback strict-local trattava float come integer.** Il validator
  locale accettava `1.5` per uno schema che richiede `"type": "integer"`.
  Corretto: `integer` richiede `isinstance(node, int)` (bool escluso) e `number`
  richiede `int` o `float`. Aggiunti test forzati sul validator locale
  (indipendenti da `jsonschema`) con fixture negative `frame=1.5`,
  `physical_length=7726.5`, `declared_outer_length="7726"`, proprietà `raw`
  extra, campo richiesto mancante, e positive `frame=int`,
  `relative_timestamp_ms=float`.
- **Contract runtime evidence (rafforzamento).** Il producer ora esegue, prima
  della serializzazione, una validazione strutturale fail-closed
  (`validate_evidence_document_strict`): set esatto di proprietà top-level,
  campi richiesti, privacy booleans false, allowlist strict dei frame metadata,
  `frame` integer, campi di lunghezza integer, `direction` enum, shape
  outer-wrapper, `timestamp` number, e forbid-list esatta dei campi
  privacy-sensitive (`raw`/`body`/`payload`/`plaintext`/`image`/`raster`/`pixel`/
  `hash`/`descriptor`/`template`/`secret`/`psk`). Nessuna dipendenza runtime da
  `jsonschema`.

```text
D274_PRELIVE_WINDOWS_MULTIFRAME_EVIDENCE_KIT=READY_FOR_AI_PM_REVIEW
D274_REAL_CAPTURE_CAPABILITY=0
D274_HARD_DISABLED=true
D274_SECOND_CYCLE_TARGET_OBSERVATION=NOT_EXECUTED
D274_POSTPROCESSOR_STATUS=PASS_OFFLINE_HASH_GATED_SANITIZED
D274_EVIDENCE_SCHEMA_STATUS=PASS
D274_SYNTHETIC_SECOND_CYCLE_FIXTURE=PASS
D274_PRIVACY_CONTRACT=PASS_METADATA_ONLY_NO_B0_CONTENT
D274_FINGERPRINT_B0_CONTRACT=CLOSED_OFFLINE_STRUCTURAL_7726_TLS_APPLICATION_DATA
D274_GENERIC_B0_AS_FINGERPRINT_ACCEPTED=false
D274_TLS_ALERT_B0_AS_FINGERPRINT_ACCEPTED=false
D274_WRONG_LENGTH_B0_AS_FINGERPRINT_ACCEPTED=false
D274_TLS_RECORD_LENGTH_ENDIAN=BIG_ENDIAN_NETWORK_ORDER
D274_GOODIX_B0_LENGTH_ENDIAN=LITTLE_ENDIAN
D274_REALISTIC_TLS_HEADER_1703031E25_ACCEPTED=true
D274_SYNTHETIC_LITTLE_ENDIAN_TLS_LENGTH_ACCEPTED=false
D274_OUTPUT_ROOT_PRIVACY_CONTRACT=CLOSED_OFFLINE_PREFLIGHT_POLICY
D274_OUTPUT_ROOT_PRIVACY_POLICY_SOURCE_CONTRACT=PASS
D274_OUTPUT_ROOT_REPARSE_POINT_ACCEPTED=false
D274_BROAD_ACL_ACCEPTED=false
D274_BROAD_ACL_READ_ACCEPTED=false
D274_ACL_ALLOW_DISCRIMINATOR=AccessControlType
D274_ACL_IDENTITY_NORMALIZATION=SecurityIdentifier
WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=NOT_AVAILABLE
D274_CREDENTIAL_MUTATION_UI_TERMINAL=true
D274_UNKNOWN_MARKER_ACCEPTED=false
D274_FRAME_METADATA_SCHEMA=STRICT_ADDITIONAL_PROPERTIES_FALSE
D274_LOCAL_SCHEMA_INTEGER_SEMANTICS=STRICT_INTEGER_ONLY
D274_SCHEMA_JSON_PARSE=PASS
D274_SCHEMA_INSTANCE_VALIDATION=PASS
D274_RUNTIME_EVIDENCE_CONTRACT_VALIDATION=PASS_LOCAL_STRICT
D274_PRIVACY_FRAME_METADATA_SHAPE=PASS
WINDOWS_NATIVE_EXECUTION_TEST=NOT_AVAILABLE
REAL_USB_OPEN_COUNT=0
REAL_COMMAND_SEND_COUNT=0
REAL_CAPTURE_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
REAL_WINDOWS_ACCOUNT_MUTATION_COUNT=0
REAL_WINDOWS_ENROLLMENT_COMMIT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
BASELINE_APPROVED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
SECOND_CYCLE_STATUS=TARGET_CAPTURE_NOT_OBSERVED_STATIC_COMPONENTS_PARTIALLY_VERIFIED
HISTORICAL_NEXT_PRIMARY_BOUNDARY_AFTER_D274_01=AI_PM_REVIEW_D274_01_CORRECTIVE
HISTORICAL_NEXT_BOUNDARY_PREREQUISITE_AFTER_D274_01=CORRECTIVE_REVIEW_THEN_WINDOWS_NATIVE_OFFLINE_QUALIFICATION
```

### D274/02: Pacchetto operatore per qualificazione nativa Windows (preparazione OFFLINE)

D274/02 prepara esclusivamente offline un **pacchetto operator-run** per
qualificare nativamente su Windows le sole modalità innocue del Kit D274/01:
`-SelfTestOnly`, `-PreflightOnly`, `-PreAuthorizationSimulationOnly`. L'AI
esecutrice non dispone della VM Windows target e non esegue né simula la
qualificazione nativa. La **prima operator-run Windows nativa** del pacchetto ha
chiuso `result=FAIL` allo `pre_gate` per un falso positivo del source scan (la
regex `-f\s` ha scambiato l'operatore di formattazione PowerShell per il
capture-filter di TShark); è seguito un corrective in-place dello stesso D274/02
che rende il source contract context-aware e corregge la verità dell'ACL dopo
pre-gate fallito. La review AI-PM aveva inoltre trovato e corretto cinque
difetti (A–E) più un hardening (F) e una lacuna di privacy. La **seconda
operator-run Windows nativa** (result ZIP verificato AI-PM,
`ZIP_SHA256=e146c39a…`, `SIDECAR_MATCH=PASS`, `ZIP_CRC=PASS`) ha invece raggiunto
lo stage `selftest` ed è **fallita nativamente** su Windows PowerShell Desktop
5.1 per un difetto del **Kit D274/01** (selettore modalità scalare `.Count`
sotto `StrictMode 2.0`), emerso proprio durante D274/02. Lo step corregge il
Kit canonico D274/01 e rigenera coerentemente il pacchetto; chiude ora `D274_02_OPERATOR_PACKAGE=CLOSED` (dopo la terza operator-run nativa,
vedi sotto). La terza operator-run Windows nativa del pacchetto è stata realmente
eseguita nella VM e revisionata da AI-PM: `result=PASS` con
`D274_02_WINDOWS_NATIVE_QUALIFICATION=PASS`,
`WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=PASS` e
`D274_NATIVE_HARD_DISABLE_ADVERSARIAL_TEST=PASS`. D274/02 è pertanto
`D274_02_STATUS=CLOSED` e `CORRECTIVE_REQUIRED=false`. Le due run precedenti
(FAIL pre-gate per falso positivo source scan; FAIL selftest per scalare `.Count`
sotto StrictMode) restano provenance storica delle run 1 e 2, superate dal
corrective del Kit D274/01 validato nativamente alla terza run.

Il Kit D274/01 (`operator_kit/d274-windows-multiframe-evidence.ps1`) è stato
**corretto in questo step** (non è più baseline non modificata): il selettore
modalità ora forza il risultato a sempre array via outer `@(...)`, risolvendo il
`PropertyNotFoundStrict` su `.Count` su Windows PowerShell 5.1. La copia nel
pacchetto è rigenerata **byte-identica** al Kit canonico corretto (SHA-256
verificato `2f2e2f1b…6c` per il kit e `2867ff23…f37` per il postprocessor).
Non è emerso alcun altro nuovo difetto D274/01 oltre al selettore; il pacchetto
non è bloccato da `BLOCKED_BY_NEW_D274_01_DEFECT`.

La review AI-PM del pacchetto preparato ha trovato e corretto in-place (senza
aprire D274/03) cinque difetti e un hardening: (A) l'autority della radice
`captures/` era incoerente tra wrapper (`package\..`) e kit (`package/captures`),
ora unificata in `package/captures`; (B) `Write-D274JsonResult` era tipizzato
`[hashtable]` pur ricevendo un `PSCustomObject` da `ConvertFrom-Json` in Windows
PowerShell 5.1, ora `[object]` e senza dipendenza da `-AsHashtable`; (C) un FAIL
pre-gate non produceva tutti e sei i core JSON, ora ogni esito scrive i sei file
(le modalità non eseguite come `SKIPPED` con `skipped_because`); (D) il runtime
summary dichiarava ancora "pending operator run", ora dichiara
`WINDOWS_NATIVE_OFFLINE_QUALIFICATION_EXECUTED_BY_OPERATOR` e
`NO_LIVE_CAPTURE_PERFORMED`; (E) `operator_package_sha256` etichettava come hash
dell'intero pacchetto lo SHA-256 del solo kit, ora esiste
`D274_02_operator_package_integrity.json` (verificato read-only a runtime) e
l'environment esporta `operator_package_integrity`,
`operator_package_manifest_sha256`, `approved_d274_01_kit_sha256`. Hardening (F):
il collector ora richiede uguaglianza canonica esatta del path `results/`
(rimosso il controllo prefix). La privacy del FAIL è centralizzata in
`Sanitize-String` e rafforzata da una seconda barriera FAIL_CLOSED nel collector.

Revisione AI-PM ulteriore (sempre in-place, senza D274/03) ha corretto la
probatorietà del FAIL: (A) la presenza del sensore è ora osservata da
`Get-D274GoodixPresence` (booleano) separatamente dal gate; se il target
`VID_27C6&PID_5125` è presente il gate fallisce chiuso
(`FAIL_CLOSED_GOODIX_PRESENT_BEFORE_OFFLINE_QUALIFICATION`) e
`goodix_present_before_run=true`; se `Get-PnpDevice` non è disponibile la presenza
è `null` (mai un falso negativo); (B) il primo failure preserva
`failure_detail_sanitized` (messaggio eccezione passato per `Sanitize-String`,
senza stack trace) nel summary, distinguendo PowerShell/integrity/kit-contract/
Goodix/marker; (C) i FAIL dei subprocess preservano `exit_code` e un
`error_sanitized` bounded (<=2048 char) derivato da stderr/stdout, così un
preflight fallito per TShark/USBPcap/output-root è diagnosticabile; (D) l'evidence
importata dal Kit (`D274_WINDOWS_PREFLIGHT_V1`) è sanitizzata prima del result
bundle: `output_root` diventa `<PACKAGE_ROOT>\captures` e `tshark_path` passa per
`Sanitize-String`, preservando i fatti semantici. Ne consegue che un package
copiato sotto un user profile Windows (`C:\Users\<utente>\...`) resta
collezionabile dal collector purché il relativo ACL privacy gate passi: il
collector non rifiuta il path per il solo nome, ed è sempre la seconda barriera
(SID/MAC/IP/`C:\Users\`/HKEY_/credential) a rifiutare eventuali dati sensibili
residui.

Il pacchetto `analysis/D274/D274_02_windows_native_operator_package/` contiene
copia byte-identica del kit e del postprocessor, una `captures/` vuota (radice
privata di destinazione), `results/` (prodotto dall'operatore), il launcher
`run-d274-02-native-qualification.ps1`, il collector
`collect-d274-02-results.ps1` e il manifest di integrità statico
`D274_02_operator_package_integrity.json` (entrambi gli script GPL-2.0-or-later,
Windows PowerShell 5.1). Il launcher verifica read-only il manifest prima di
eseguire.

Il launcher nativo, in ordine e senza retry:

1. verifica read-only il manifest di integrità `D274_02_operator_package_integrity.json`
   (SHA-256 dei file statici e baseline D274/01), poi verifica Windows PowerShell
   5.1 (edizione Desktop);
2. verifica assenza del sensore `VID_27C6&PID_5125` dal guest
   (`Get-PnpDevice -PresentOnly` → fail-closed
   `FAIL_CLOSED_GOODIX_PRESENT_BEFORE_OFFLINE_QUALIFICATION`);
3. verifica assenza di un marker D274 attivo;
4. esegue `-SelfTestOnly`, `-PreflightOnly`, `-PreAuthorizationSimulationOnly`,
   fermandosi al primo FAIL (le modalità non eseguite emettono placeholder
   `SKIPPED` per mantenere completo il deliverable);
5. esegue il test read-only nativo sul comportamento ACL della `captures/`
   (metadati sanitizzati: `canonical_capture_root_match`, `reparse_point`,
   `acl_readable`, `broad_*_read_or_stronger`, `write_probe_pass`); il preflight
   nativo deve attestare `output_root_privacy == PASS_PRIVATE_CONTRACT`, altrimenti
   `WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=FAIL` e qualification chiusa — nessuna mutazione
   ACL; la radice `captures/` usata è l'unica authority `package/captures`,
   allineata con quella del kit copiato (corretto il difetto A);
6. esegue il test avversario hard-disable, ma solo se il safety pre-gate è
   passato (altrimenti è registrato `SKIPPED`): il flag nominale
   `-IUnderstandAndAuthorizeOneD274WindowsMultiframeCapture` è lanciato in un
   subprocess separato e deve fallire (`exit != 0`, messaggio
   `HARD_DISABLED_D274_01`, nessuna capture, nessuna azione hardware) →
   `D274_NATIVE_HARD_DISABLE_ADVERSARIAL_TEST=PASS|FAIL`;
7. raccoglie evidenza d'ambiente non sensibile e produce i JSON in `results/`.

TShark/USBPcap sono usati solo in discovery (`--version`, `-D`);
`REAL_CAPTURE_START_COUNT=0`. Il collector accetta solo `results/`, verifica
l'allowlist, rifiuta file inattesi, esegue uno privacy scan testuale e produce
`D274_02_windows_native_qualification_results.zip` + `.sha256` contenente
soltanto i sei artefatti risultato (più eventuali stderr sanitizzati solo in
caso di FAIL e solo se privi di dati sensibili). Non include pcap, ACL raw,
registry, event log, screenshot, dati di impronta, B0, TLS, segreti, PSK, cache,
DLL o firmware.

Il blocco seguente è separato in snapshot temporali: i flag FAIL appartengono
alla **seconda run** e non descrivono lo stato finale; i flag PASS successivi
appartengono alla **terza run** e sono l'authority finale D274/02. Le prime due
righe preservano inoltre l'esito distinto della prima run. Questa etichettatura
è cleanup storico D274/03 e non riapre D274/02.

```text
D274_02_FIRST_WINDOWS_OPERATOR_RUN=FAIL_PRE_GATE_FALSE_POSITIVE_SOURCE_SCAN
D274_02_FIRST_WINDOWS_OPERATOR_RUN_ROOT_CAUSE=GENERIC_REGEX_-f_MATCHED_POWERSHELL_FORMAT_OPERATOR
D274_02_SECOND_WINDOWS_OPERATOR_RUN=FAIL_SELFTEST_NATIVE_POWERSHELL51_SCALAR_COUNT
D274_02_SECOND_WINDOWS_OPERATOR_RUN_ROOT_CAUSE=MODE_SELECTOR_PIPELINE_SCALAR_COUNT_UNDER_STRICTMODE
```

Snapshot storico della seconda run FAIL (non è lo stato finale):

```text
WINDOWS_POWERSHELL51_RUNTIME=PASS
OPERATOR_PACKAGE_INTEGRITY_RUNTIME=PASS
KIT_SOURCE_CONTRACT_RUNTIME=PASS
GOODIX_ABSENCE_GATE_RUNTIME=PASS
NO_ACTIVE_MARKER_GATE_RUNTIME=PASS
SELFTEST_RUNTIME=FAIL
PRELIGHT_RUNTIME=SKIPPED
PREAUTHORIZATION_SIMULATION_RUNTIME=SKIPPED
HARD_DISABLE_ADVERSARIAL_RUNTIME=FAIL_BEFORE_EXPECTED_BRANCH_DUE_SELECTOR
FIRST_FAILURE_STOP_RUNTIME=PASS
FAIL_CORE_JSON_PRODUCTION_RUNTIME=PASS
NO_LIVE_CAPTURE_PERFORMED=true
REAL_CAPTURE_START_COUNT=0
REAL_USB_OPEN_COUNT=0
HARDWARE_ACTION_COUNT=0
HARD_DISABLE_PRESERVED=true
D274_02_ACL_RESULT_AFTER_SKIPPED_PREFLIGHT=NOT_EXECUTED_DUE_PRIOR_FAILURE
```

Snapshot finale della terza run PASS (authority corrente D274/02):

```text
D274_01_NATIVE_POWERSHELL51_MODE_SELECTOR_CORRECTIVE=CLOSED
D274_01_MODE_SELECTOR_FORCED_ARRAY=true
D274_01_STRICTMODE_PRESERVED=true
D274_01_NATIVE_POWERSHELL51_MODE_SELECTOR=PASS_NATIVE
D274_02_CORRECTED_KIT_CANONICAL_PACKAGE_BYTE_IDENTITY=PASS
D274_02_OPERATOR_PACKAGE=CLOSED
D274_02_TSHARK_SOURCE_CONTRACT=CONTEXT_AWARE_EXACT_ALLOWLIST
D274_02_TSHARK_ALLOWLIST_TRAILING_ARGUMENT_ESCAPE=false
D274_02_POWERSHELL_FORMAT_OPERATOR_FALSE_POSITIVE=false
D274_02_FINAL_INTEGRITY_MANIFEST_SELF_CONSISTENT=PASS
D274_02_INTEGRITY_MANIFEST_GENERATED_AFTER_STATIC_FILES_FROZEN=true
D274_02_FINAL_RUNNER_HASH_MATCHES_MANIFEST=PASS
D274_02_FINAL_COLLECTOR_HASH_MATCHES_MANIFEST=PASS
D274_02_FINAL_README_HASH_MATCHES_MANIFEST=PASS
D274_02_FINAL_KIT_HASH_MATCHES_MANIFEST=PASS
D274_02_FINAL_POSTPROCESSOR_HASH_MATCHES_MANIFEST=PASS
D274_02_BUNDLE_MANIFEST_STATIC_RUNTIME_PATHS_ACCURATE=PASS
D274_02_FAIL_RESULT_COLLECTOR_CONTRACT=PASS
D274_02_ENVIRONMENT_TSHARK_DISCOVERY=NON_AUTHORITATIVE_DIAGNOSTIC
D274_01_PREFLIGHT_TSHARK_DISCOVERY=AUTHORITATIVE_GATE
D274_02_SUMMARY_ALL_STAGE_KEYS=PASS_STATIC_ALL_NINE_KEYS_PRESENT
D274_02_POST_SELFTEST_FAILURE_SKIP_CONTRACT=PRESERVED
D274_02_VM_ABSOLUTE_LOG_TIMESTAMPS_CROSS_SESSION_DURATION_AUTHORITY=false
D274_02_WINDOWS_NATIVE_EXECUTION=COMPLETED
D274_02_WINDOWS_NATIVE_QUALIFICATION=PASS
WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=PASS
D274_NATIVE_HARD_DISABLE_ADVERSARIAL_TEST=PASS
D274_02_CAPTURE_ROOT_AUTHORITY=PACKAGE_ROOT_CAPTURES
D274_02_WRAPPER_KIT_CAPTURE_ROOT_ALIGNMENT=PASS
D274_02_OPERATOR_PACKAGE_INTEGRITY=PASS_STATIC_AND_RUNTIME_VERIFIABLE
D274_02_OPERATOR_PACKAGE_HASH_OVERCLAIM_REMOVED=true
D274_02_COLLECTOR_RESULTS_PATH_AUTHORITY=EXACT_PACKAGE_RESULTS
D274_02_FAIL_RESULT_COLLECTABILITY=PASS
D274_02_FIRST_FAILURE_AUTHORITY=PASS
D274_02_AUTOMATIC_RETRY_COUNT=0
D274_REAL_CAPTURE_CAPABILITY=0
D274_HARD_DISABLED=true
D274_SECOND_CYCLE_TARGET_OBSERVATION=NOT_EXECUTED
BASELINE_APPROVED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
LIVE_EXECUTION=NOT_PERFORMED
D274_02_TECHNICAL_REGRESSION=false
D274_02_REOPEN_REQUIRED=false
D274_02_MANUAL_HISTORICAL_STATE_CLEANUP=COMPLETED
NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_D274_03_PRELIVE_OPERATOR_KIT
NEXT_BOUNDARY_PREREQUISITE=SEPARATE_AI_PM_REVIEW_BASELINE_APPROVAL_AND_EXPLICIT_ONE_SHOT_AUTHORIZATION
```

#### D274/02 — prima operator-run Windows (FAIL pre-gate, falso positivo source-scan)

La prima vera esecuzione operatore Windows del pacchetto D274/02 ha chiuso
`result=FAIL` allo `pre_gate`. Non è un failure dell'ambiente Windows: la review
AI-PM ha identificato un falso positivo nel source scan del package.

Evidence nativa osservata:

```text
runtime_result_state=WINDOWS_NATIVE_OFFLINE_QUALIFICATION_EXECUTED_BY_OPERATOR
result=FAIL
failed_stage=pre_gate
failure_detail_sanitized=D274_02_FAIL_CLOSED: kit source scan found forbidden capture argument token: -f\s
assert_windows_powershell_51=PASS
package_integrity=PASS
pre_gate=FAIL
selftest=SKIPPED
preflight=SKIPPED
preauthorization_simulation=SKIPPED
hard_disable_adversarial=SKIPPED
```

Environment: Windows 11 Home build 26200; Windows PowerShell Desktop
5.1.26100.8655; `operator_package_integrity=PASS`; `goodix_present_before_run=null`
(corretto: il source-contract gate è fallito prima dell'osservazione PnP).

Root cause: la regex generica `-f\s` applicata all'intero sorgente del Kit
D274/01 ha scambiato l'operatore di formattazione PowerShell
`(".d274-write-probe-{0}" -f [Guid]::NewGuid().ToString("N"))` per il
capture-filter di TShark.

La run ha chiuso solo i confini raggiunti:

```text
WINDOWS_POWERSHELL51_RUNTIME=PASS
OPERATOR_PACKAGE_INTEGRITY_RUNTIME=PASS
FIRST_FAILURE_STOP_RUNTIME=PASS
FAIL_CORE_JSON_PRODUCTION_RUNTIME=PASS
NO_LIVE_CAPTURE_PERFORMED=true
REAL_CAPTURE_START_COUNT=0
REAL_USB_OPEN_COUNT=0
HARD_DISABLE_PRESERVED=true
```

Non è promossa a `WINDOWS_NATIVE_QUALIFICATION=PASS`, né a
`WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=FAIL_REAL_ENVIRONMENT`, né a
`TSHARK=ABSENT`/`USBPCAP=ABSENT`: la run è fallita troppo presto per tali
conclusioni.

Corrective in-place (stesso D274/02, nessun D274/03): il source contract è ora
context-aware (`& $tshark` allowlist solo discovery; `-f` PowerShell non più
falso positivo); l'ACL dopo pre-gate fallito è `NOT_EXECUTED_DUE_PRIOR_FAILURE`;
il runner stampa in italiano l'invito al collector; il collector accetta il FAIL.
Lo `environment.json` esporta `tshark_discovery_role=NON_AUTHORITATIVE_DIAGNOSTIC`
(il vero gate è il `-PreflightOnly` del Kit D274/01,
`D274_01_PREFLIGHT_TSHARK_DISCOVERY=AUTHORITATIVE_GATE`).

#### D274/02 — corrective finale post-review AI-PM (manifest integrità + allowlist esatta)

La review AI-PM del bundle `64ddee56…` ha rilevato due blocchi, corretti in
questa iterazione finale (sempre D274/02, nessun D274/03):

- **FINAL_PACKAGE_INTEGRITY_MANIFEST_STALE=true** — root cause:
  `MANIFEST_GENERATED_BEFORE_FINAL_RUNNER_AND_README_CHANGES`. Il bundle
  precedente era stato costruito prima della rigenerazione del manifest, quindi
  conteneva gli hash obsoleti di runner e README; alla seconda run Windows il
  gate `package_integrity` sarebbe fallito (`pre_gate -> package_integrity ->
  FAIL`) prima di raggiungere il fix del source-contract. Risolto rispettando
  l'ordine: freeze dei file statici, calcolo degli SHA-256 reali dai file finali,
  rigenerazione del manifest, verifica indipendente manifest-vs-files (tutte
  PASS), e solo per ultimo la creazione dello ZIP. Stato:
  `D274_02_FINAL_INTEGRITY_MANIFEST_SELF_CONSISTENT=PASS`,
  `D274_02_INTEGRITY_MANIFEST_GENERATED_AFTER_STATIC_FILES_FROZEN=true`,
  `D274_02_FINAL_RUNNER_HASH_MATCHES_MANIFEST=PASS`,
  `D274_02_FINAL_COLLECTOR_HASH_MATCHES_MANIFEST=PASS`,
  `D274_02_FINAL_README_HASH_MATCHES_MANIFEST=PASS`,
  `D274_02_FINAL_KIT_HASH_MATCHES_MANIFEST=PASS`,
  `D274_02_FINAL_POSTPROCESSOR_HASH_MATCHES_MANIFEST=PASS`.

- **HARDENING B — allowlist TShark esatta**: `Test-D274KitSourceContract`
  isola le righe `& $tshark`, rimuove redirection/pipeline (`2>&1`, `2>`, `>`,
  `|`) e richiede argomenti effettivi **esattamente** `--version` o `-D`. Le due
  righe baseline restano accettate; forme aumentate (`--version -i`, `-D -w`,
  ecc.) sono rifiutate. Stato:
  `D274_02_TSHARK_SOURCE_CONTRACT=CONTEXT_AWARE_EXACT_ALLOWLIST`,
  `D274_02_TSHARK_ALLOWLIST_TRAILING_ARGUMENT_ESCAPE=false`.

D274/01 **non** resta byte-identico: il selettore modalità del Kit canonico è
stato corretto in questo step (kit `2f2e2f1b…6c`, postprocessor `2867ff23…f37`);
il corrective cambia l'esito della seconda operator run (che era fallita proprio
sul selettore) e sarà verificato nativamente alla terza operator run.

#### D274/02 — seconda operator-run Windows (FAIL selftest, difetto nativo D274/01)

La seconda vera esecuzione operatore Windows del pacchetto D274/02 (result ZIP
verificato AI-PM, `ZIP_SHA256=e146c39a…`, `SIDECAR_MATCH=PASS`, `ZIP_CRC=PASS`)
ha raggiunto lo stage `selftest` ed è **fallita nativamente** su Windows
PowerShell Desktop 5.1. Non è un failure dell'ambiente Windows: il root cause è
un difetto del **Kit D274/01**

Evidence nativa osservata:

```text
runtime_result_state=WINDOWS_NATIVE_OFFLINE_QUALIFICATION_EXECUTED_BY_OPERATOR
result=FAIL
failed_stage=selftest
assert_windows_powershell_51=PASS
package_integrity=PASS
kit_source_contract=PASS
goodix_absence_gate=PASS
no_active_marker_gate=PASS
preflight=SKIPPED
preauthorization_simulation=SKIPPED
hard_disable_adversarial=FAIL_BEFORE_EXPECTED_BRANCH_DUE_SELECTOR
windows_native_acl_behavior_test=NOT_EXECUTED_DUE_PRIOR_FAILURE
real_capture_start_count=0
real_usb_open_count=0
hardware_action_count=0
real_usb_open_count=0
```

Self-test failure reale:

```text
PropertyNotFoundException / PropertyNotFoundStrict
Impossibile trovare la proprietà 'Count' in questo oggetto.
```

Il failure proviene dal selettore modalità del Kit D274/01:

```powershell
$selected = @($SelfTestOnly, $PreflightOnly, $PreAuthorizationSimulationOnly,
              $IUnderstandAndAuthorizeOneD274WindowsMultiframeCapture) |
    Where-Object { $_ }
if ($selected.Count -ne 1) { Fail-D274 "select exactly one mode" }
```

Con `Set-StrictMode -Version 2.0`, la pipeline produce uno **scalare** quando è
selezionata un'unica modalità, e l'accesso `.Count` su quello scalare non è
affidabile su Windows PowerShell Desktop 5.1 (osservato `FAIL` reale). Il
sub-processo hard-disable è morto sullo stesso `.Count` prima di raggiungere il
ramo `HARD_DISABLED_D274_01`; pertanto
`HARD_DISABLE_NATIVE_BRANCH_TEST=NOT_YET_PASSED` (l'invariant source
hard-disable è preservato, non bypassato). Stato di interpretazione corretta:

```text
HARD_DISABLE_SOURCE_INVARIANT=PRESERVED
HARD_DISABLE_NATIVE_BRANCH_TEST=NOT_YET_PASSED
```

Non è interpretato: hard-disable bypassed, capture attempted, hardware action
occurred.

Root cause: `MODE_SELECTOR_PIPELINE_SCALAR_COUNT_UNDER_STRICTMODE`.

La run ha chiuso solo i confini raggiunti:

```text
WINDOWS_POWERSHELL51_RUNTIME=PASS
OPERATOR_PACKAGE_INTEGRITY_RUNTIME=PASS
KIT_SOURCE_CONTRACT_RUNTIME=PASS
GOODIX_ABSENCE_GATE_RUNTIME=PASS
NO_ACTIVE_MARKER_GATE_RUNTIME=PASS
SELFTEST_RUNTIME=FAIL
PRELIGHT_RUNTIME=SKIPPED
PREAUTHORIZATION_SIMULATION_RUNTIME=SKIPPED
HARD_DISABLE_ADVERSARIAL_RUNTIME=FAIL_BEFORE_EXPECTED_BRANCH_DUE_SELECTOR
REAL_CAPTURE_START_COUNT=0
REAL_USB_OPEN_COUNT=0
HARDWARE_ACTION_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
```

Corrective (qui, stesso D274/02 + Kit D274/01, nessun D274/03): il selettore
modalità del Kit canonico `operator_kit/d274-windows-multiframe-evidence.ps1`
forza ora il risultato a **sempre array** tramite outer `@(...)`:

```powershell
$selected = @(
    @(
        $SelfTestOnly,
        $PreflightOnly,
        $PreAuthorizationSimulationOnly,
        $IUnderstandAndAuthorizeOneD274WindowsMultiframeCapture
    ) | Where-Object { $_ }
)
if ($selected.Count -ne 1) { Fail-D274 "select exactly one mode" }
```

`0/1/2/4` switch selezionati → `Count=0/1/2/4` affidabili; lo `StrictMode`
**non è stato rimosso**. La copia nel pacchetto D274/02 è rigenerata
**byte-identica** al Kit corretto. Dopo la correzione, il nominale
`-IUnderstandAndAuthorizeOneD274WindowsMultiframeCapture` supera la selezione e
raggiunge `Fail-D274 "HARD_DISABLED_D274_01; D274_REAL_CAPTURE_CAPABILITY=0"`
prima di ogni capture/USB/hardware/finger-prompt. Stato:

```text
D274_01_NATIVE_SELECTOR_CORRECTIVE=APPLIED_PENDING_OPERATOR_RETEST
D274_01_MODE_SELECTOR_FORCED_ARRAY=true
D274_01_STRICTMODE_PRESERVED=true
D274_01_NATIVE_POWERSHELL51_MODE_SELECTOR=NOT_YET_PASS_NATIVE_PENDING_THIRD_RUN
D274_NATIVE_HARD_DISABLE_ADVERSARIAL_TEST=PENDING_WINDOWS_RETEST
D274_02_CORRECTED_KIT_CANONICAL_PACKAGE_BYTE_IDENTITY=PASS
```

Non è promossa a `WINDOWS_NATIVE_QUALIFICATION=PASS`, né a
`WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=FAIL`, né a `TSHARK=ABSENT`/`USBPCAP=ABSENT`:
la run è fallita prima del preflight nativo realmente eseguito. I timestamp
assoluti della VM **non** sono authority sulla durata tra sessioni (la VM può
essere sospesa/riattivata); `D274_02_VM_ABSOLUTE_LOG_TIMESTAMPS_CROSS_SESSION_DURATION_AUTHORITY=false`.

#### D274/02 — terza operator-run Windows (PASS: qualificazione nativa completa)

La terza vera esecuzione operatore Windows del pacchetto D274/02 è stata
realmente eseguita nella VM Windows e revisionata da AI-PM. Non è un tooling
run: è l'authority definitiva della qualificazione nativa. Il result bundle è
verificato:

```text
D274_02_WINDOWS_NATIVE_RESULT_ZIP_SHA256=4bbca10957dd30b672a76d84368303083a392eb18480a6d0c506045be313eaf0
SIDECAR_MATCH=PASS
ZIP_CRC=PASS
EXPECTED_RESULT_FILES=6/6
UNEXPECTED_RESULT_FILES=0
PRIVACY_SCAN=PASS
```

Le due run precedenti erano failure di tooling (run 1: falso positivo source
scan `-f`; run 2: scalare `.Count` sotto `StrictMode 2.0`) entrambi superati dal
corrective del Kit D274/01; la terza run li ha chiusi entrambi nativamente.

Environment nativo osservato (authority della terza run):

```text
WINDOWS_OS_CAPTION=Microsoft Windows 11 Home
WINDOWS_OS_BUILD=26200
WINDOWS_POWERSHELL_EDITION=Desktop
WINDOWS_POWERSHELL_VERSION=5.1.26100.8655
TSHARK_AUTHORITATIVE_PREFLIGHT_PATH=<PROGRAMFILES>\Wireshark\tshark.exe
TSHARK_AUTHORITATIVE_PREFLIGHT_VERSION=TShark (Wireshark) 4.6.7
USBPCAP_AUTHORITATIVE_PREFLIGHT_INTERFACE_COUNT=1
GOODIX_PRESENT_BEFORE_RUN=false
D274_02_ENVIRONMENT_TSHARK_DISCOVERY=NON_AUTHORITATIVE_DIAGNOSTIC
D274_01_PREFLIGHT_TSHARK_DISCOVERY=AUTHORITATIVE_GATE
```

Gli orari assoluti dei log VM **non** sono authority sulla durata tra sessioni
(la VM può essere sospesa/riattivata):
`D274_VM_ABSOLUTE_LOG_TIMESTAMPS_CROSS_SESSION_DURATION_AUTHORITY=false`.

Tutti gli stage nativi = PASS (authority AI-PM):

```text
assert_windows_powershell_51=PASS
package_integrity=PASS
kit_source_contract=PASS
goodix_absence_gate=PASS
no_active_marker_gate=PASS
selftest=PASS
preflight=PASS
preauthorization_simulation=PASS
hard_disable_adversarial=PASS
```

Quindi: `D274_02_SELFTEST_NATIVE=PASS`, `D274_02_PREFLIGHT_NATIVE=PASS`,
`D274_02_PREAUTHORIZATION_SIMULATION_NATIVE=PASS`,
`D274_NATIVE_HARD_DISABLE_ADVERSARIAL_TEST=PASS`.

Il corrective D274/01 (selettore modalità forzato a array sotto
`Set-StrictMode -Version 2.0`) ha superato nativamente `-SelfTestOnly`. Lo stage
pre-authorization simulation ha osservato:

```text
synthetic_marker_lifecycle=PASS
authorization_consumed=false
real_capture_started=false
real_usb_open_count=0
real_finger_interaction_count=0
enrollment_commit_authorized=false
account_mutation_authorized=false
pin_mutation_authorized=false
```

Native ACL privacy = PASS (osservato realmente):

```text
canonical_capture_root_match=true
reparse_point=false
acl_readable=true
broad_everyone_read_or_stronger=false
broad_builtin_users_read_or_stronger=false
broad_authenticated_users_read_or_stronger=false
broad_guests_read_or_stronger=false
write_probe_pass=true
WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=PASS
D274_02_OUTPUT_ROOT_PRIVACY_NATIVE=PASS
```

Nessuna ACL è stata modificata: né `Set-Acl` né `icacls`. Quindi
`D274_02_OUTPUT_ROOT_PRIVACY_NATIVE=PASS`.

Native hard-disable adversarial test = PASS (fail-closed): il ramo nominale di
autorizzazione deve fallire con `HARD_DISABLED_D274_01` e
`D274_REAL_CAPTURE_CAPABILITY=0`; l'exit code 1 è il risultato corretto del test
avversario.

```text
subprocess_exit_code=1
expected_hard_disable_message_observed=true
no_capture_started=true
no_hardware_action=true
D274_REAL_CAPTURE_CAPABILITY=0
D274_HARD_DISABLED=true
authorization_consumed=false
D274_NATIVE_HARD_DISABLE_ADVERSARIAL_TEST=PASS
D274_HARD_DISABLE_NATIVE_BRANCH=PASS_FAIL_CLOSED
```

Safety closure D274/02 (nessun hardware/live eseguito):

```text
REAL_CAPTURE_START_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_COMMAND_SEND_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
REAL_WINDOWS_ACCOUNT_MUTATION_COUNT=0
REAL_WINDOWS_ENROLLMENT_COMMIT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
D274_REAL_CAPTURE_CAPABILITY=0
D274_HARD_DISABLED=true
```

Non promosso (restano false): `APPROVED_FOR_CAPTURE`, `LIVE_AUTHORIZED`,
`READY_FOR_LIVE`. D274/02 NON ha osservato il secondo ciclo biometrico:
`D274_SECOND_CYCLE_TARGET_OBSERVATION=NOT_EXECUTED`,
`SECOND_CYCLE_STATUS=TARGET_CAPTURE_NOT_OBSERVED_STATIC_COMPONENTS_PARTIALLY_VERIFIED`.

Stato finale D274/02:

```text
D274_02_WINDOWS_NATIVE_EXECUTION=COMPLETED
D274_02_WINDOWS_NATIVE_QUALIFICATION=PASS
D274_02_SELFTEST_NATIVE=PASS
D274_02_PREFLIGHT_NATIVE=PASS
WINDOWS_NATIVE_ACL_BEHAVIOR_TEST=PASS
D274_02_PREAUTHORIZATION_SIMULATION_NATIVE=PASS
D274_NATIVE_HARD_DISABLE_ADVERSARIAL_TEST=PASS
D274_01_NATIVE_POWERSHELL51_MODE_SELECTOR=PASS_NATIVE
D274_01_NATIVE_POWERSHELL51_MODE_SELECTOR_CORRECTIVE=CLOSED
D274_01_STRICTMODE_PRESERVED=true
D274_02_FINAL_REVIEW=PASS
D274_02_STATUS=CLOSED
CORRECTIVE_REQUIRED=false
```

Il Kit canonico D274/01 `operator_kit/d274-windows-multiframe-evidence.ps1` e la
sua copia byte-identica nel pacchetto D274/02 restano immutati in questo closure
step: nessuna modifica comportamentale al Kit. La terza run chiude D274/02 come
qualificazione nativa Windows offline completa (selftest, preflight, simulazione
pre-autorizzazione, ACL privacy, hard-disable adversarial), senza alcuna capture
o azione hardware. Quel boundary storico di pianificazione è stato consumato
dalla preparazione offline D274/03; il boundary corrente è ora
`NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_D274_03_PRELIVE_OPERATOR_KIT`, con
prerequisito `SEPARATE_AI_PM_REVIEW_BASELINE_APPROVAL_AND_EXPLICIT_ONE_SHOT_AUTHORIZATION`.
D274/02 non abilita capture reale, non rimuove hard-disable e non autorizza live.

### D274/03: Kit Windows/OEM one-shot per il secondo ciclo (preparazione OFFLINE)

D274/03 non esegue hardware. Crea la nuova authority separata
`analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/`; D274/01 e
D274/02 restano storici, salvo il cleanup narrativo sopra. Il package parla in
italiano all'operatore e contiene launcher, runner live futuro, collector,
observer pcapng growing metadata-only, sanitizer finale strict, schema,
template authority con gate false, README, package di qualificazione nativa,
marker e radici D274/03 distinte. La review AI-PM della prima baseline ha
bloccato l'approvazione sui cinque difetti causali/UI/finalizzazione/nativi
descritti nella sintesi alta; il corrective resta nello stesso D274/03.

#### Riesame metodologico pre-live

1. **Cosa cambia realmente rispetto alla prima baseline D274/03?** Il gate
   Goodix diventa causalmente interno alla stessa invocazione live e lo stop
   passa dalla conferma UI all'osservazione passiva del secondo B0, seguita da
   verifica del raw finalizzato; nessun hardware viene eseguito ora.
2. **Quale nuova ipotesi tecnica verrà testata?** Dopo ACK del re-arm `0x32`,
   un nuovo finger-down nel workflow OEM produce IRQ `0x0002`, wire `0x22`, ACK
   echo `0x22` con status esatto `0x01` e un secondo B0 fingerprint.
3. **Se la futura run non chiude il boundary?** Nessun retry automatico e
   nessuna seconda run equivalente per default. Si revisiona offline il raw e
   si classifica il failure in workflow/UI, emissione secondo IRQ2, dispatch
   secondo `0x22`, ACK o secondo B0. Una nuova run richiede modifica
   metodologica sostanziale, nuova review e nuova autorizzazione.

#### Authority, workflow e safety

Il workflow resta `WINDOWS_HELLO_SETUP_CANDIDATE_NO_COMMIT`: non attribuisce
retroattivamente D263 a una UI nota. Il runner futuro invoca un solo processo
TShark con USBPcap e deadline host-side 180 s; non contiene Python/libusb
sensor-reaching. Prima della capture richiede authority separata con tre flag
true, full SHA di 40 caratteri, HEAD esatto e branch `main`,
live-critical set pulito e uguale alla baseline, root privata non-reparse e
marker atomico `CreateNew`. Prima del marker verifica inoltre, tramite
`Get-PnpDevice -PresentOnly`, che il target esatto `VID_27C6&PID_5125` sia
assente dal guest nella stessa invocazione; discovery non disponibile o target
presente falliscono chiuso. Il gate precede causalmente marker, `Start-Process`,
attach e prompt dito e non esegue mutazioni PnP né aperture USB. Il template
corrente ha i flag false e nessun SHA, quindi fallisce prima di
`Start-Process`.

`EXISTING_PIN_AUTHENTICATION` è ammessa solo quando Windows richiede il PIN già
configurato per verificare l'identità: il valore resta esclusivamente nella UI
Windows e il Kit non lo legge, chiede, registra o serializza. `NEW_PIN_REQUIRED`,
`PIN_CREATION_UI`, `PIN_MUTATION_UI`, `ACCOUNT_MUTATION_UI`,
`CREDENTIAL_MUTATION_UI`, `UNEXPECTED_PREREQUISITE` ed
`ENROLLMENT_COMMIT_UI` sono terminali senza conferma UI. Il Kit non offre un
terzo prompt e vieta retry/recovery.

L'operatore certifica soltanto che la UI richiede il secondo dito; non certifica
il B0. L'observer legge passivamente il file del solo TShark, tollera il normale
trailing block pcapng incompleto e segnala il secondo B0 strutturale senza
esportarne il contenuto. Quel segnale causa lo stop bounded. Il runner attende
la terminazione, richiede raw presente/non vuoto, calcola SHA-256 solo dopo la
finalizzazione e invoca il sanitizer strict hash-gated. Il raw finale deve
contenere lo stesso frame terminale; altrimenti il failure distinto è
`CAPTURE_FINALIZATION_LOST_TERMINAL_EVIDENCE`. Il sanitizer rifiuta inoltre
terzo IRQ2/`0x22`/B0, duplicato secondo `0x22`, ACK diverso, B0
mancante/malformato, target ambiguo, re-enumeration, firmware non APP12509,
deadline, schema o privacy failure.

Il prefisso first-cycle resta nel matcher soltanto per provare che il `0x32` è
il re-arm e non il primo arm. L'output pubblicabile contiene soltanto metadata:
frame, direzione, wrapper, control/IRQ/ACK, lunghezze, classe TLS esterna,
ordine, delta intra-run, stop reason e conteggi. Non serve il decode immagine
per distinguere il B0 fingerprint strutturale già chiuso da D274/01/D274/02.

#### Closure offline

Il test D274/03 esegue 46 casi sintetici/avversari: success boundary; secondo
IRQ mancante/errato; secondo `0x22` mancante/duplicato; ACK echo/status errati;
B0 malformato/classe errata; terzo ciclo; target ambiguo/re-enumerato; firmware
errato; deadline; privacy/schema; authority non autorizzata; baseline stale;
marker riusato; ordine causale same-run; policy PIN; trigger growing esatto;
trailing block incompleto; deadline observer; stop/finalizzazione bounded;
perdita terminal evidence; raw vuoto/mancante/troncato; source contract passivo;
ACL/privacy; lingua italiana; package nativo; manifest strict; regressione sulla
capture storica D263; BOM UTF-8, decodifica `utf-8-sig`, assenza di mojibake e
hash del contenuto logico di ciascun `.ps1`; cattura immediata dell'exit code
nativo, assenza del pattern `$LASTEXITCODE`-dopo-pipeline in tutti i `.ps1`,
fail-closed sulla variabile catturata e validazione non-vuoto del repository;
literal TShark non interpolato sotto StrictMode; privacy contract attribuito
all'import `inspect_growing_capture` dell'observer e al campo
`biometric_plaintext_exported=False` del postprocessor; assenza di nuove
letture PIN/credenziali, invocazioni USB/capture attive e promozioni authority.
Tutti passano su Linux.

#### Qualification nativa: PASS finale operator-supplied, nessun hardware toccato

Entrambe le run native sono state eseguite su Windows 11 Home build 26200,
Windows PowerShell Desktop 5.1.26100.8655, con Goodix `27c6:5125` assente dal
guest. Nessuna ha toccato hardware, aperto USB o creato capture/marker.

La prima è fallita al parsing di `run-d274-03-native-qualification.ps1` prima
del runtime, per script UTF-8 senza BOM con superficie italiana/non-ASCII. Il
corrective BOM è ora confermato dal campo, non solo offline: il parsing 5.1 passa
e lo stage `powershell_51` ha dato PASS.

La seconda è la prima run realmente entrata in runtime ed è fallita allo stage
`repository_and_goodix_absence` con `D274_03_NATIVE_FAIL_CLOSED: repository Git
non individuabile`. Il repository era in realtà individuabile. La diagnostica
manuale, eseguita nello stesso clone e nella stessa directory Kit, isola la
causa in modo non ambiguo:

```text
& git -C $PackageRoot rev-parse --show-toplevel   # toplevel corretto
EXIT_DIRECT=0
$repository = (& git -C $PackageRoot rev-parse --show-toplevel 2>&1 |
    Select-Object -First 1)                       # stesso toplevel corretto
EXIT_PIPE=-1
```

In Windows PowerShell 5.1 `Select-Object -First 1` interrompe la pipeline
upstream; il comando nativo non consegna il proprio exit code e `$LASTEXITCODE`
osservato diventa `-1` anche quando Git riesce. Il gate leggeva quindi un exit
code inventato dalla pipeline, non quello di Git, e falliva chiuso su un
repository valido. Nessun controllo Goodix, ACL, TShark/USBPcap, selector 5.1,
gate same-run o simulazione pre-authority è stato raggiunto in quella run.

Il corrective adotta un unico idioma PowerShell 5.1-safe: il comando nativo è
invocato senza pipeline, l'exit code è catturato nello statement immediatamente
successivo in una variabile dedicata, il fail-closed valuta quella variabile e
solo dopo l'output viene selezionato, normalizzato e validato come non vuoto.
L'audit del Kit ha trovato cinque siti realmente vulnerabili, tutti su Git, e li
ha corretti: repository nel runner di qualificazione, repository nel launcher,
repository nel collector, `rev-parse HEAD` e `branch --show-current` nel runner
live. Restano audit-safe e non modificati i siti che leggono `$LASTEXITCODE`
senza pipeline interposta (`git diff --quiet`, `git status --porcelain` e il
sanitizer Python, tutti in forma `@(& …)` o invocazione diretta) e le
invocazioni TShark che usano solo l'output senza mai leggere `$LASTEXITCODE`.
Observer e postprocessor Python continuano a essere avviati con `Start-Process
-PassThru` e valutati su `ExitCode`, che non è soggetto al problema. La semantica
dei gate non cambia: HEAD deve ancora coincidere con la baseline approvata e la
branch deve ancora essere `main`.

La run finale post-corrective, eseguita dall'operatore nello stesso ambiente
Windows con Goodix assente, ha dato PASS completo. I relativi stage
`powershell_51`, `repository_and_goodix_absence`, `selftest`,
`powershell_51_selector`, `preflight`, `preauthorization_simulation`,
`same_run_goodix_absence_gate`, `causal_source_order`,
`authority_false_adversarial`, `source_privacy_language_and_runtime_contract`
e `no_real_capture_or_marker` sono tutti PASS. Il contratto runtime registra
`same_run_goodix_absence_gate=PASS_NATIVE`, selector 5.1 PASS nativo,
TShark/USBPcap `PASS_NATIVE_NO_CAPTURE`, ACL privacy PASS nativo e lingua
operatore italiana.

I due micro-fix finali consolidati sono host-only. Nel controllo dell'ordine
causale il literal `Start-Process -FilePath $TsharkPath` usa apici singoli:
con `Set-StrictMode` Windows PowerShell 5.1 non tenta più di espandere nel
processo di qualification una variabile che appartiene al runner ispezionato.
Nel privacy contract l'observer deve importare/usare `inspect_growing_capture`,
mentre il postprocessor — owner dello stato pubblicato — deve dichiarare
`"biometric_plaintext_exported": False`; l'observer non duplica artificialmente
la costante.

Il collector operator-supplied riporta result e privacy scan PASS e SHA-256
`5a498239c9988445deedd0732009a2766a5ac564756c7c581461708faa9eca87` per
`D274_03_windows_native_qualification_results.zip`. Il package non è presente
sull'host AI Linux e i suoi byte non sono stati ricalcolati dall'agente. Il
runtime PowerShell Desktop 5.1 resta non disponibile localmente, ma non viene
simulato: il PASS nativo qui registrato ha provenance operatore.

Il processo operativo risultante è: qualification host-only con Goodix assente
per iterazioni correttive rapide; dopo PASS, freeze e review formale del
candidato; eventuale live one-shot soltanto dopo approvazione separata della
baseline. Il PASS di qualification non promuove da solo alcuna authority.

La review AI-PM del freeze correttivo ha poi chiuso PASS e ha autorizzato la
sola approvazione formale della baseline. Il record canonico separato
`analysis/D274/D274_03_baseline_approval.json` fissa il full SHA
`ed87646fe54e01baaffe0b12fd4ec73ba3e20fd5`, la qualification Windows
`PASS_OPERATOR_SUPPLIED`, il package hash operatore
`5a498239c9988445deedd0732009a2766a5ac564756c7c581461708faa9eca87` e il
freeze bundle hash verificato AI-PM
`d7e5db36a0efec05ab33c82c221beb42c91aea4772a059764930ead5d8ed1d6b`.
Il record non è un input del runner live. Il template
`D274_03_live_authority.json` resta byte-invariato e fail-closed con
`baseline_approved=false`, `approved_for_capture=false`,
`live_authorized=false`, SHA `null` e one-shot ID `null`, preservando anche il
percorso `-NativeQualificationOnly`. Nessun marker o contatore reale è stato
creato o incrementato. Il prossimo boundary è una decisione separata ed
esplicita di capture/live one-shot; la baseline approval non la anticipa.

```text
D274_02_TECHNICAL_REGRESSION=false
D274_02_REOPEN_REQUIRED=false
D274_02_MANUAL_HISTORICAL_STATE_CLEANUP=COMPLETED
D274_03_CORRECTIVE_IMPLEMENTED_OFFLINE=true
D274_03_OPERATOR_LANGUAGE=ITALIAN
D274_03_OFFLINE_EXECUTABLE_CLOSURE=PASS_LINUX_OFFLINE_ONLY
D274_03_LIVE_BRANCH_GATE=main
D274_03_POWERSHELL51_ENCODING_CORRECTIVE=IMPLEMENTED_OFFLINE
D274_03_POWERSHELL51_BOM_CORRECTIVE=PASS
D274_03_PS1_ENCODING=UTF8_WITH_BOM
D274_03_FIRST_NATIVE_QUALIFICATION_RESULT=FAIL_PARSE_BEFORE_RUNTIME
D274_03_FIRST_NATIVE_QUALIFICATION_GOODIX_PRESENT=false
D274_03_FIRST_NATIVE_QUALIFICATION_POWERSHELL=5.1.26100.8655
D274_03_FIRST_NATIVE_QUALIFICATION_HARDWARE_TOUCHED=false
D274_03_POST_BOM_NATIVE_QUALIFICATION_RESULT=FAIL_REPOSITORY_STAGE
D274_03_POST_BOM_NATIVE_QUALIFICATION_POWERSHELL_51=PASS
D274_03_POST_BOM_NATIVE_QUALIFICATION_OS=WINDOWS_11_HOME_BUILD_26200
D274_03_POST_BOM_NATIVE_QUALIFICATION_GOODIX_PRESENT=false
D274_03_POST_BOM_NATIVE_QUALIFICATION_HARDWARE_TOUCHED=false
D274_03_POST_BOM_GIT_EXIT_DIRECT=0
D274_03_POST_BOM_GIT_EXIT_PIPE=-1
D274_03_POST_BOM_STAGES_AFTER_REPOSITORY=NOT_REACHED
D274_03_LASTEXITCODE_CORRECTIVE=PASS_OFFLINE
D274_03_LASTEXITCODE_VULNERABLE_SITES_CORRECTED=5
D274_03_WINDOWS_NATIVE_QUALIFICATION=PASS_OPERATOR_SUPPLIED
WINDOWS_NATIVE_PACKAGE_SHA256=5a498239c9988445deedd0732009a2766a5ac564756c7c581461708faa9eca87
WINDOWS_NATIVE_PACKAGE_BYTES_REHASHED_BY_AGENT=false
WINDOWS_NATIVE_ALL_STAGES=PASS_OPERATOR_SUPPLIED
WINDOWS_POWERSHELL_5_1_NATIVE_RUNTIME=NOT_AVAILABLE_ON_LINUX_HOST
BASELINE_APPROVAL_BLOCKED_PENDING_NATIVE_QUALIFICATION=false
D274_03_REAL_CAPTURE_CAPABILITY=1_CURRENT_AUTHORITY_TEMPLATE
SOURCE_CONTAINS_FUTURE_LIVE_PATH=true
# Stato di autorizzazione/esecuzione live di baseline (template non eseguito via questo kit):
# i contatori REAL_* restano a zero per i tentativi UI non validi; la capture osservata è separata.
LIVE_PATH_EXECUTED=false
LIVE_PATH_AUTHORIZED=false
D274_03_FREEZE_REVIEW=PASS
FREEZE_BUNDLE_SHA256=d7e5db36a0efec05ab33c82c221beb42c91aea4772a059764930ead5d8ed1d6b
D274_03_BASELINE_APPROVAL_REVIEW_PENDING=false
D274_03_BASELINE_APPROVED=true
D274_03_APPROVED_BASELINE_FULL_SHA=ed87646fe54e01baaffe0b12fd4ec73ba3e20fd5
APPROVED_FOR_CAPTURE=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
LIVE_EXECUTION=NOT_PERFORMED
# Contatori dell'attivita' diretta di invio/osservazione USB del Kit operatore
# (observer passivo: nessun sender Python/libusb; i due tentativi UI non validi non
# hanno aperto USB ne' catturato). La run Windows OEM osservata ha svolto l'attivita'
# USB/finger/command sul target, ma il Kit non la misura separatamente e tali conteggi
# non sono enumerati qui come totali della run.
REAL_USB_OPEN_COUNT=0
REAL_FINGER_INTERACTION_COUNT=0
REAL_GOODIX_COMMAND_COUNT=0
D274_SECOND_CYCLE_TARGET_OBSERVATION=OBSERVED_COMPLETE
REAL_CAPTURE_COUNT=1
# Stato canonico della capture osservata (run live autorizzata separata):
D274_03_OBSERVED_TERMINAL_FRAME=249
D274_03_OBSERVER_STOP_TRIGGER=WIRE_DRIVEN
D274_03_AUTOMATIC_RETRY_COUNT=0
D274_03_CANONICAL_RAW_SHA256=5f11d06763d34531c72283a189a47d9bcd7c666a5fa3c043ec1371eddf107998
D274_03_THIRD_CYCLE_OBSERVED=false
D274_03_OFFLINE_FINALIZER_CORRECTIVE=IMPLEMENTED_OFFLINE_ON_PRESERVED_RAW
D274_03_NO_NEW_LIVE_RUN=true
D274_03_DEVICE_TIMEOUT_CLAIM=UNKNOWN
# I conteggi low-level USB/finger/command della run Windows OEM osservata non sono
# enumerati qui (observer passivo): vedere i contatori di attivita' diretta del Kit
# nello stato di template/autorizzazione. L'unica scrittura persistente e' nulla.
PERSISTENT_DEVICE_WRITE_COUNT=0
NEXT_PRIMARY_BOUNDARY=D274_03_OFFLINE_FINALIZER_CORRECTIVE_REVIEW
NEXT_BOUNDARY_PREREQUISITE=FORMAL_FREEZE_REVIEW_POST_OBSERVATION
```

Il current critical boundary si sposta ora a valle del primo raster decodificato.
La closure canonica D218–D220 (contract immagine Windows) va preservata e non
reinventata: il preprocessing Windows/AlgoChicago consuma direttamente il raster
`u16`/12-bit (`INTENSITY_CONTRACT=DIRECT_U16_CONSUMED_PROVEN`, WIN-001 in
`docs/EVIDENCE.md`); non è giustificato alcun adapter `u16→u8` ricostruito dal
contratto Windows; l'orientamento resta `UNRESOLVED`. Il nuovo fatto D268
(`target live image → valid image record → decoded raster 80x64 u16`) e la
conoscenza D220 (Windows consuma u16 direttamente, nessun adapter u8) portano al
prossimo boundary principale, che è una **decisione di engineering Linux-specifica**
e non una nuova campagna statica Windows:

```text
NEXT_PRIMARY_BOUNDARY=LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT  # post-D268; SUPERSEDED by D269/01 (see update below)
```

Il task successivo dovrà affrontare, senza assumere la soluzione: i requisiti di
rappresentazione immagine libfprint, il mapping `u16`/12-bit → Linux/libfprint,
la policy di scaling/clipping/normalizzazione, orientation/transpose/flag, la
proprietà di quality/preprocessing e se la conversione appartenga al core GPL o
alla glue LGPL libfprint. Resta aperto anche il lifecycle di capture per frame
ripetuti e il confine verso la pipeline biometrica (quality/enrollment/matching).
Tale boundary è definito in D268/02 e da sottoporre a review AI-PM prima di ogni
nuovo live.

Separatamente, la riproducibilità generale resta limitata dal materiale di
trasporto machine-bound. Il motore TLS Linux è ora verificato anche sul target
D245, ma questa evidenza non rende portabile il materiale né autorizza un nuovo
live.

D269/01 ha successivamente chiuso offline la decisione di engineering Linux-specifica
post-D268 (il vecchio `NEXT_PRIMARY_BOUNDARY=LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT`
è ora superato) auditando l'API locale libfprint 1.94.5 e implementando l'adapter bounded
`libfprint-driver/goodix_u16_to_fpimage` (LGPL-2.1-or-later, byte-identico e non modificato
in questo corrective). Lo stato corrente del current critical boundary per il dominio
Linux/libfprint è:

```text
PIXEL_REPRESENTATION_CONTRACT=CLOSED_OFFLINE
INTENSITY_QUANTIZATION_CONTRACT=CLOSED_OFFLINE
FULL_FPIMAGE_PIPELINE_CONTRACT=NOT_YET_CLOSED
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
NEXT_PRIMARY_BOUNDARY=LIBFPRINT_IMAGE_PIPELINE_INTEGRATION_OFFLINE
NEXT_BOUNDARY_PREREQUISITE=RESOLVE_OR_EXPLICITLY_BOUND_PPMM_SEMANTICS
```

Il full `FpImage` pipeline contract resta `NOT_YET_CLOSED` perché `FpImage::ppmm`
(pixels-per-mm, campo `gdouble` osservato in `fpi-image.h`) è consumato da NBIS
(`get_minutiae` → `combined_minutia_quality`, `radius_pix = RADIUS_MM × ppmm`) ma non
da SIGFM; il valore fisico target-specific APP12509 è `UNKNOWN` (l'unica assegnazione
trovata, `fimg->ppmm = 500.0/25.4` in `Rockytkg/src/goodixgf.c`, è terza parte e la sua
stessa commento la dichiara "solo per display"). Orientation e polarity restano `UNRESOLVED`.

D270/01 ha successivamente superato il boundary di sola integrazione oggetto:
il helper LGPL `goodix_fpimage_pipeline` costruisce realmente il GObject locale
e trasferisce i pixel sintetici tramite l'unico adapter D269. Lo stato corrente
del current critical boundary diventa:

```text
FPIMAGE_OBJECT_CONSTRUCTION=CLOSED_OFFLINE
FPIMAGE_BUFFER_OWNERSHIP=CLOSED_OFFLINE
FPIMAGE_DIMENSION_CONTRACT=CLOSED_OFFLINE
UNKNOWN_PPMM_SEMANTICS=EXPLICITLY_BOUNDED
NBIS_WITH_UNKNOWN_PPMM=BLOCKED
SIGFM_PPMM_CONSUMPTION=NO_VERIFIED
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
FULL_FPIMAGE_PIPELINE_CONTRACT=PARTIALLY_CLOSED
NEXT_PRIMARY_BOUNDARY=LIBFPRINT_FEATURE_EXTRACTION_POLICY_OFFLINE
```

Il prossimo step non deve ripetere la costruzione né promuovere SIGFM per sola
comodità: deve fondare la policy di feature extraction su evidenza o limiti
espliciti per orientation, polarity, risoluzione e qualità biometrica.

D271/01 ha successivamente auditato extractor, matcher ed enrollment nel fork
locale. La policy risultante è chiusa senza promuovere una qualità non
dimostrata:

```text
FEATURE_EXTRACTOR_POLICY=CLOSED_OFFLINE
SIGFM_STATUS=CANDIDATE_FOR_VALIDATION
NBIS_STATUS=BLOCKED_UNKNOWN_PHYSICAL_PPMM_AND_TARGET_LOCAL_MINUTIA_DENSITY_UNPROVEN
SIGFM_80X64_SUPPORT_STATUS=ARCHITECTURALLY_SUPPORTED_WITH_MIN_25_KEYPOINT_GATE_TARGET_QUALITY_UNPROVEN
NBIS_80X64_SUPPORT_STATUS=STRUCTURALLY_ACCEPTED_MIN_8PX_BLOCK_BUT_TARGET_USABILITY_BLOCKED
BIOMETRIC_QUALITY_STATUS=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED
FULL_FPIMAGE_PIPELINE_CONTRACT=PARTIALLY_CLOSED
NEXT_PRIMARY_BOUNDARY=SIGFM_TARGET_LOCAL_BIOMETRIC_VALIDATION
NEXT_BOUNDARY_PREREQUISITE=AUTHORIZED_PRIVACY_PRESERVING_TARGET_REAL_KEYPOINT_AND_MATCH_METRICS_WITH_D269_FIXED_MAPPING
```

Il prossimo step non deve ripetere la scelta architetturale né assumere il
threshold Rockytkg: deve produrre metriche target-reali autorizzate e
privacy-preserving su keypoint, extraction gate e separazione dei punteggi,
preservando il mapping D269 finché l'evidenza non giustifica una revisione.

D272/01 ha ora superato la sola progettazione di quelle metriche con un seam
sintetico verificato, ma **non** ha raggiunto la validazione target: il
lifecycle live resta bloccato sulla tabella up `0x34` e sulla seconda
iterazione non osservata, mentre la build SIGFM reale è bloccata
dall'assenza di OpenCV4-dev. Il current next boundary è quindi quello indicato
nella sintesi alta, non una run target immediata.

### D274/03 parallel offline forward analysis (solo OFFLINE, non live)

Questa sessione fu svolta mentre D274/03 era **in attesa della qualification
nativa Windows con Goodix assente**; tale attesa è ora superata dal PASS
operator-supplied, mentre restano invariati candidato live-critical e authority
false. La sessione svolse una analisi differenziale OFFLINE end-to-end rispetto
allo snapshot Rockytkg
(`227eba219fa9e3fbac5bd59aca79f624f67cd11b`) per individuare i componenti
software Linux realmente mancanti, anticipabili oggi senza il target. Artefatti in
`analysis/D274/D274_03_offline_forward_*.{md,json}`.

Due ruoli distinti di D274/03 (chiariti dopo review AI-PM):

- `D274_03_WINDOWS_NATIVE_QUALIFICATION_WITH_GOODIX_ABSENT` — qualifica solo la
  parte host-only eseguibile: Windows PowerShell 5.1 runtime, Git/repository gate,
  TShark/USBPcap/preflight, ACL/privacy, selector/same-run gates, simulazione
  pre-authority, hard-disable / host-side executable closure. Il sensore è assente
  → **non può osservare né chiudere l'evidenza del secondo ciclo**, né qualificare
  il TLS Linux (che ha evidenza storica propria).
- `FUTURE_D274_03_EXPLICITLY_AUTHORIZED_LIVE_ONE_SHOT_WITH_GOODIX_ATTACHED` —
  solo dopo qualification PASS + AI-PM freeze review + baseline approval +
  autorizzazione esplicita, osserverà `0x32` re-arm ACK → second `IRQ0002` →
  second `0x22` → ACK `0x01` → second fingerprint `B0` → STOP. Boundary stretto =
  *second-cycle existence/order after re-arm*; non è una campagna biometrica o di
  timing e un live riuscito non prova il timeout semantico del device.

Esito della mappa: il progetto ha già chiuso offline (o modella fail-closed) tutto
il percorso da cold-start a prima immagine, inclusi decode canonico, mapping
`u16→FpImage` (D269/D270), policy feature-extraction (D271) e lifecycle
multi-frame (D273). I gap che richiedono il target restano: secondo/successivo
ciclo di capture dopo re-arm (`TARGET_EVIDENCE_REQUIRED`; boundary del futuro live
one-shot; re-arm osservato con ACK ma seconda iterazione completa non osservata),
orientation/polarity/ppmm (`TARGET_EVIDENCE_REQUIRED`, separato dal one-shot),
qualità biometrica/threshold di match (richiede distribuzioni di score target), e
glue device libfprint non ancora implementata localmente.

Responsabilità framework (verificata): l'enrollment aggregation multi-stage è di
proprietà di libfprint — `Rockytkg/libfprint/libfprint/fpi-image-device.c:302-306`
esegue `fpi_print_add_print(enroll_print, print)` → `priv->enroll_stage += 1` →
`fpi_device_enroll_progress(...)`. Il driver deve invece: catturare un'immagine →
costruire `FpImage` → riportare lo stato del dito →
`fpi_image_device_image_captured()`. Di conseguenza:

```text
LIBFPRINT_ENROLLMENT_AGGREGATION=FRAMEWORK_OWNED_VERIFIED
PROJECT_EXTRA_FPIMAGE_AGGREGATOR_REQUIRED=false
LOCAL_LIBFPRINT_DEVICE_GLUE=IMPLEMENTED_HOST_ONLY_EXECUTABLY_CLOSED
LOCAL_LIBFPRINT_DEVICE_GLUE_SLICE_1=IMPLEMENTED_CORRECTIVE_EXECUTABLY_CLOSED_HOST_ONLY
D276_02_OUTCOME=READY

LINUX_TLS_1_2_PSK_TARGET_STATUS=LIVE_PROVEN_D245
PERSISTENT_TLS_RUNTIME_STATUS=IMPLEMENTED_D260
LINUX_TLS_REBUILD_REQUIRED=false

A2_0X70_COLD_START_CANONICAL_REACHABILITY=ALLOWED_BOUNDED_EXISTING_PATH
A2_0X70_FDT_RECOVERY_REENTRY_REACHABILITY=FORBIDDEN_FAIL_CLOSED
PERSISTENT_COMMAND_FAMILIES_REACHABLE=false
```

Nessun seam è stato implementato in questo corrective: il collector
`goodix_capture_aggregation` aggiunto nello step precedente è stato rimosso dopo
review AI-PM perché non chiaramente mancante (vedi
`analysis/D274/D274_03_offline_forward_seam_decision.md`). `Rockytkg/src/goodixgf.c`
è `LGPL-2.1-or-later` e può essere valutato per riuso/adattamento diretto nel
dominio LGPL dopo audit per-file di SPDX/licenza/copyright/origini/provenance; le
porzioni firmware-update/ClearApp/PSK e ogni espressione GPL-only restano escluse
(`GPL_TO_LGPL_EXPRESSION_CROSSING_ALLOWED=false`).

La policy no-write del progetto (`core/fdt_lifecycle.py`,
`core/persistent_runtime.py`, `core/cold_start.py`) rende le famiglie
persistenti `0xE0/0xA4/0xF0/0xF4` irraggiungibili per costruzione (nessun
provisioning/firmware/IAP/ClearApp/persistent write). I comandi `0xA2/0x70`
**non** sono globalmente irraggiungibili: sono raggiungibili solo nei loro
bounded canonical cold-start positions già autorizzati/provati via
`core/cold_start.py` (`A2_0X70_COLD_START_CANONICAL_REACHABILITY=ALLOWED_BOUNDED_EXISTING_PATH`),
e restano vietati come retry/recovery/FDT re-entry/session repair dentro
`FdtLifecycle._record()` (`A2_0X70_FDT_RECOVERY_REENTRY_REACHABILITY=FORBIDDEN_FAIL_CLOSED`).
I corrispondenti path Rockytkg (`goodix_fwupdate.c`, `goodix_psk.c`,
`goodix_otp.c`) restano classificati `ROCKY_UNSAFE_FOR_PROJECT` e non importati.

Inoltre il TLS 1.2 PSK è già **live-proven** in D245 (A8→E4→pre-D1→D1→TLS
completo, stop prima di D4, zero retry, zero persistent-write) e il runtime TLS
persistente è **implementato** in D260 (one TLS server engine, one retained
session, one handshake, mixed A0/B0 routing), riusato dai successivi step live;
`LINUX_TLS_REBUILD_REQUIRED=false` (ruolo server-side rispetto al ClientHello
del device, nessun nuovo TLS client da costruire).

D274/03 è qualificato nativamente con PASS operator-supplied e la baseline è
formalmente approvata sul full SHA
`ed87646fe54e01baaffe0b12fd4ec73ba3e20fd5`, ma NON è approvato per capture e
NON è live-ready. La decisione successiva resta separata ed esplicita
(`D274_03_WINDOWS_NATIVE_QUALIFICATION=PASS_OPERATOR_SUPPLIED`,
`D274_03_BASELINE_APPROVED=true`, `APPROVED_FOR_CAPTURE=false`,
`LIVE_AUTHORIZED=false`, `READY_FOR_LIVE=false`).

### D274/03 parallel offline forward — Sessione 3: SIGFM / OpenCV4 real-build closure

Sessione 3 del track parallel offline forward D274/03 (esecutore Hy3 Free,
host-only, nessun target). Chiude il blocker D273
`REAL_SIGFM_BUILD=BLOCKED_OPENCV4_DEV_NOT_AVAILABLE` / `EXECUTABLE_CLOSURE=FAIL_NOT_AVAILABLE`
ottenendo un **real SIGFM executable closure** con OpenCV4-dev reale, senza
inventare qualità biometrica, threshold, orientamento, polarity o ppmm.

Precondizione Git rispettata: `HEAD == origin/main`
(`b88edaa44e124ea7b6cd5b0464fca630f5d2da51`), working tree pulito, nessuna
divergenza. Branch di sessione `session/agent_*`, nessun merge/rebase/force-push.

Ambiente (riproducibile, bounded): Ubuntu 22.04 jammy; GCC/G++ 11.4.0;
pkg-config 0.29.2. OpenCV4-dev **non** presente di default → installato nel
sandbox esecutore via `apt-get install -y build-essential pkg-config libopencv-dev`
(`libopencv-dev 4.5.4+dfsg-9ubuntu4`). Nessuna credenziale utente, nessun
aggiramento di sicurezza, nessun vendorizzazione nel repository, nessun binario
committato, nessun target/USB/fprintd. Il mirror `Rockytkg/` **non** è stato
modificato per far compilare il codice.

Codice usato (tutti LGPL-2.1-or-later, audit per-file OK):
`libfprint-driver/goodix_u16_to_fpimage.c/.h`,
`libfprint-driver/goodix_sigfm_metrics.cpp/.h` (progetto),
`Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp/.h`, `binary.hpp`, `img-info.hpp`
(riferimento terzo-party libfprint, header di licenza LGPL-2.1-or-later esplicito verificato; NESSUN tag SPDX letterale rivendicato),
`libfprint-driver/tests/test_goodix_sigfm_metrics_real.cpp` (progetto).

Policy warning differenziata (giustificata, non nasconde warning nostri):
codice progetto compilato con
`-std=c11 -O2 -g -Wall -Wextra -Werror -Wconversion` (C) e
`-std=c++17 -O2 -g -Wall -Wextra -Werror -Wconversion -Wshadow -Wold-style-cast`
(C++); il riferimento SIGFM terzo-party compilato con `-Wall -Wextra` (no
`-Werror`/`-Wconversion`/`-Wold-style-cast`); gli header terzo-party inclusi via
`-isystem` così i warning progetto restano visibili. Nessun warning nel nostro
codice; nessun warning terzo-party mascherato nel nostro oggetto.

Risultato (vedi `analysis/D274/D274_03_sigfm_real_build_*.{md,json}` e bundle):

```text
OUTCOME=READY_FOR_AI_PM_REVIEW
ADVANCEMENT=SIGFM_REAL_OPENCV4_HOST_ONLY_BUILD_AND_POSITIVE_RUNTIME_CLOSURE
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
REAL_SIGFM_BUILD=PASS_HOST_ONLY_WITH_REAL_OPENCV4
REAL_SIGFM_LINK=PASS
REAL_SIGFM_POSITIVE_EXTRACT=PASS
REAL_SIGFM_MATCH_PATH=PASS
REAL_SIGFM_SYNTHETIC_RUNTIME=PASS
REAL_SIGFM_EXECUTABLE_CLOSURE=PASS_HOST_ONLY
REAL_SIGFM_SANITIZER_STATUS=PASS
LEAK_DETECTION=DISABLED
MEMORY_SAFETY_SCOPE=ASAN_UBSAN_RUNTIME_NO_DETECTED_ADDRESS_OR_UB_ERRORS_LEAKS_NOT_ASSESSED
OPENCV4_DEV_ENVIRONMENT=AVAILABLE_HOST_ONLY_LIBOPENCV_DEV_4_5_4_VIA_APT
SIGFM_REFERENCE_LICENSE=LGPL-2.1-or-later_EXPLICIT_LICENSE_HEADER_VERIFIED
SIGFM_REFERENCE_LITERAL_SPDX_TAG_CLAIM=false

BUILDABILITY=PASS
LINKABILITY=PASS
SYNTHETIC_REAL_SIGFM_RUNTIME=PASS
POSITIVE_EXTRACT_AND_MATCH_PATH=PASS
MEMORY_SAFETY=SCOPE_ASAN_UBSAN_RUNTIME_CLEAN_LEAKS_NOT_ASSESSED
TARGET_BIOMETRIC_QUALITY=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED
PRODUCTION_INTEGRATION=NOT_INTEGRATED_NO_DEVICE_GLUE

BIOMETRIC_QUALITY_STATUS=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED
PRODUCTION_MATCH_THRESHOLD=UNSET
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
SECOND_TARGET_CYCLE=UNOBSERVED  # HISTORICAL_SCOPE; SUPERSEDED_BY_D278_14_LIVE_12

LINUX_TLS_REBUILD_REQUIRED=false
LIBFPRINT_ENROLLMENT_AGGREGATION=FRAMEWORK_OWNED_VERIFIED
PROJECT_EXTRA_FPIMAGE_AGGREGATOR_REQUIRED=false
LOCAL_LIBFPRINT_DEVICE_GLUE=IMPLEMENTED_HOST_ONLY_EXECUTABLY_CLOSED
LOCAL_LIBFPRINT_DEVICE_GLUE_SLICE_1=IMPLEMENTED_CORRECTIVE_EXECUTABLY_CLOSED_HOST_ONLY
D276_02_OUTCOME=READY

REAL_USB_OPEN_COUNT=0
REAL_COMMAND_SEND_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
REAL_BIOMETRIC_CAPTURE_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
D274_03_OPERATOR_KIT_MODIFIED=false
LIVE_CRITICAL_SET_MODIFIED=false
```

Regressione host-only rieseguita: `goodix_u16_to_fpimage` unit test PASS;
`goodix_sigfm_metrics` synthetic/double PASS + forbidden-symbol audit PASS
(nessun simbolo libusb_/SSL_/gnutls_/socket/fopen/open/write/read in `metrics.o`);
`goodix_fpimage_pipeline` **NON_RUN_ENVIRONMENT_LIMITATION**: il suo harness
storico Flatpak (`run_goodix_fpimage_pipeline_test.sh`) richiede l'SDK Flatpak e
l'header di framework libfprint `fpi-image.h`, non disponibili in questo
esecutore. È una limitazione d'ambiente/toolchain, **indipendente** dallo stato
del device glue (D276/02 ha implementato la shell host-only con executable closure
`PASS_HOST_ONLY` su GitHub Actions; il pipeline helper è un componente D270
autonomo, non il futuro device glue).

Harness riproducibile host-only aggiunto:
`libfprint-driver/tests/run_goodix_sigfm_metrics_real_host.sh` (machine-actionable,
fail-closed: se `opencv4.pc` manca → stampa
`REAL_SIGFM_EXECUTABLE_CLOSURE=BLOCKED_ENVIRONMENT` e
`REAL_SIGFM_DEPENDENCY=BLOCKED_OPENCV4_DEV_UNAVAILABLE` poi **exit 77** (SKIP
convenzionale, non finto PASS); dipendenza presente + tutti i PASS → exit 0;
failure build/link/runtime → exit 1; stampa SKIP/NOT_AVAILABLE vs FAIL vs PASS,
nessun USB/fprintd/secret/network a runtime, nessun pacchetto auto-installato,
nessuna scrittura fuori `/tmp`, nessun vendorizzazione OpenCV, nessun cambio
threshold). Il test real positivo richiede `GOODIX_SIGFM_OK` su due estrazioni
identiche, `keypoints >= 25`, e che `goodix_sigfm_match_ephemeral` esegua
effettivamente `sigfm_match_score()` (fixture sintetica strutturata deterministica,
checkerboard 8x8 + grating, nessun target/biometrica/tuning); un test negativo
separato copre il `GOODIX_SIGFM_KEYPOINT_GATE_FAILED`. L'harness Flatpak esistente
(`run_goodix_sigfm_metrics_test.sh`) resta valido per il percorso synthetic/double.

Confine rispettato: un PASS sintetico host-only di build/link/run **non** chiude
qualità biometrica, sufficienza keypoint target, separazione same/different
finger, threshold di produzione, orientation, polarity o ppmm/DPI. Restano aperti
tutti i gap `TARGET_EVIDENCE_REQUIRED`. Prossimo vero gap dopo questa sessione:
glue device libfprint locale + observazione del secondo ciclo di capture dopo
re-arm (futuro D274/03 live one-shot esplicitamente autorizzato), non più il
blocco della build SIGFM OpenCV4.

### D275/02: candidate Linux live one-shot fino al secondo B0 (OFFLINE)

D275/02 non è una nuova evidenza hardware. Distingue tre authority già chiuse
altrove e una sola superficie operatore nuova:

- **D268**: first-image Linux live storico; baseline frozen
  `c03d32e8647444495e6615e41c2839cbddd62143`. Manifest e kit D268 non vengono
  riscritti per adattarli al current HEAD.
- **D275/01**: production path Linux chiuso offline fino a
  `STOP_AFTER_SECOND_IMAGE` nel vero `PersistentRuntimeCoordinator`.
- **D275/02**: thin operator path
  `operator_kit/d275-second-b0-once.sh` → `tools/d275_live_second_b0_once.py` →
  `core.d275_second_b0_operator` → `PersistentRuntimeCoordinator`, con stop
  immediato al secondo B0.

Il corrective Git-native (policy v2.5) sostituisce i gate host difettosi della
prima chiusura D275/02: niente ZIP/Base64, niente manifesto SHA-256 cerimoniale,
nessuna auto-approvazione di SHA. Il gate live verifica SHA completo lowercase,
`HEAD ==` SHA approvato, worktree pulito, path set esatto e byte-identity Git
del live-critical set. Il report D275 è distinto da D268 e viene pubblicato
solo dopo l'adattamento `PASS_STOP_AFTER_SECOND_IMAGE`. Il marker usa lo schema
`D275_SECOND_B0_SINGLE_USE_MARKER_V1` con `approved_baseline_sha` e
`terminal_boundary=STOP_AFTER_SECOND_IMAGE`; fsync precede la capability.
Le capability D268 e D275 non si mintano a vicenda. Il riuso D268 è limitato
alla host transaction guarded, con adapter intent/live-io/verifier in
try/finally e zero leakage globale. Il default storico D268 resta
`STOP_AFTER_FIRST_IMAGE`.

Il full suite D268 sul current HEAD che fallisce sul manifest frozen è
`EXPECTED_HISTORICAL_MANIFEST_GUARD`. Alla baseline storica `c03d32e...` la
suite D268 è riproducibile. Nessuna USB reale, nessun comando sensore, nessuna
nuova evidenza live.

```text
LINUX_SECOND_B0_LIVE_OBSERVED=false  # HISTORICAL_SCOPE; SUPERSEDED_BY_D278_14_LIVE_12
LIVE_AUTHORIZED=false
TARGET_DEVICE_TIMEOUT=UNKNOWN
NEXT_PRIMARY_BOUNDARY=AI_PM_PRE_LIVE_REVIEW_D275_02
```

Stato al termine di D275/02; promosso a `LINUX_SECOND_B0_LIVE_OBSERVED=true`
da D275/04.

## Hard Wall

```text
APP mapped start          0x0802c000
A2 target                 0x080272e1
0x70 target               0x0802b8f5
minimum missing interval  0x080272e0..0x0802b8f4
PRE_D1_PATH_CLEARED_FOR_EXACT_OEM_REPLAY  true
DEVICE_RESIDENT_NO_NVM_SIDE_EFFECT_PROVEN false
D246_EXACT_APP12509_D4_NO_NVM_SIDE_EFFECT_PROVEN true
D250_AF_LIVE_BOUNDARY CONSUMED
D250_AF_ZERO_TAIL_DEVICE_ACCEPTANCE LIVE_PROVEN
D250_AF_ZERO_TAIL_STRUCTURAL_AE_RESPONSE LIVE_PROVEN
D250_AF_ZERO_TAIL_OEM_BYTEWISE_EQUIVALENCE NOT_PROVEN
D250_AF_LIVE_STATE_BYTE0_VALUE LOST_BY_OBSERVABILITY_GAP
D250_LIVE_EXECUTION PERFORMED_ONCE
D251_LIVE_RESULT PASS
D251_AF_BOUNDARY LIVE_PROVEN
D251_AF_STATE_BYTE0 0_OPAQUE
D251_AF_STATE_FLAGS 0x02
D251_AF_POV_VALID false
D251_MARKER CONSUMED
FDT_DOWN_TABLE_LIVE_READY false
D253_POST_IRQ2_IMAGE_COMMAND 0x22_DATA_0100
D255_LIVE_CAPTURE SUCCEEDED
D255_CAPTURE_BYTES 27684
D255_CAPTURE_FRAME_COUNT 218
D255_CAPTURE_SHA256 802370d618dc94effc2ca7401076b71a2425857d59daa27b99cd5a00cc63337c
D255_RECOVERY_RESULT PASS
D255_POSTPROCESS_RESULT PASS
D255_NEW_LIVE_CAPTURE_REQUIRED false
D255_NEW_RUN_REQUIRED false
FUTURE_LIVE_OPERATOR_AUTHORIZATION_REQUIRED true
D256_USBPCAP_LIFECYCLE_AUDIT PASS_COMPLETE_TARGET_PACKET_TIMELINE
D256_CANCEL_TO_REENTRY_DEVICE_CONTINUITY SAME_BUS_DEVICE_AND_BULK_ENDPOINTS
D256_HOST_SIDE_PENDING_BULK_IN_CANCELLATION_OBSERVED true
D256_EXPLICIT_USB_RESTORE_OBSERVED false
D256_ABORT_OR_RESET_OBSERVED false
D256_REENUMERATION_OBSERVED false
D256_REENTRY_WITHOUT_EXPLICIT_USB_RESTORE_PROVEN true
D256_NEW_FDT_ARM_ACCEPTED_ON_REENTRY true
D256_RESTORE_REQUIRED_FOR_REENTRY false
D256_PRIOR_ARM_DISARM_PROVEN false
D256_PRIOR_ARM_LIFETIME_AFTER_CANCEL UNOBSERVED
D256_DEVICE_INTERNAL_FDT_STATE_AFTER_CANCEL UNOBSERVED
D256_TERMINAL_CANCEL_PENDING_BULK_IN_CANCELED true
D256_EXPLICIT_USB_TERMINAL_RESTORE_OBSERVED false
D256_TERMINAL_CANCEL_ABORT_OR_RESET_OBSERVED false
D256_TERMINAL_CANCEL_REENUMERATION_OBSERVED false
D256_POST_TERMINAL_CANCEL_CAPTURE_WINDOW_SECONDS 491.125998
D256_POST_TERMINAL_CANCEL_TARGET_USB_PACKET_COUNT 0
D256_POST_TERMINAL_CANCEL_TOTAL_PACKET_COUNT 0
D256_OEM_TERMINAL_CANCEL_USB_QUIESCENCE_PROVEN true
D256_HOST_BUS_TERMINAL_STOP_CONTRACT CLOSED_OBSERVED_PATH_BOUNDED_USB_QUIESCENCE
D256_FACTORY_PERSISTENCE_IMPLICATION NO_NEW_DEVICE_SIDE_CLAIM_FROM_USB_SILENCE
D256_CURRENT_CORPUS_EXHAUSTED_FOR_REENTRY_RESTORE_QUESTION true
D256_CURRENT_CORPUS_EXHAUSTED_FOR_INTERNAL_ARM_LIFETIME_QUESTION true
D256_LIVE_EXECUTION NOT_PERFORMED
D257_SEED_PROVIDER_IMPLEMENTED true
D257_SEED_CACHE_LAYOUT_VALIDATION PASS
D257_SEED_OTP_BINDING_VALIDATION PASS
D257_SEED_CRC_VALIDATION PASS
D257_PROJECTED_FDT_SUBSEQUENCE_REPLAY PASS_HISTORICAL
D257_EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY BLOCKED_DYNAMIC_HOST_GATES_NOT_DERIVABLE_FROM_D255_RAW
D257_EXACT_BOOTSTRAP_OUT_TRACE 36,50,36,82,20,36,32
D257_INTERSTAGE_0x50_OBSERVED true
D257_INTERSTAGE_0x82_OBSERVED true
D257_INTERSTAGE_0x20_OBSERVED true
D257_FIRST_0x36_MAX_ATTEMPTS_PER_AUTHORIZATION 1
D257_FIRST_0x36_COMMAND_TIMEOUT_MS 100
D257_FIRST_0x36_AUTOMATIC_RETRY_COUNT 0
D257_IRQ2_0x22_PATH PASS_EXACTLY_ONCE
D257_FIRST_IMAGE_OFFLINE_CLOSURE PASS_SYNTHETIC_NON_BIOMETRIC_CODEC_FIXTURE
D257_INTERNAL_PRIOR_ARM_STATE NON_BLOCKING_EPISTEMIC_UNKNOWN
D257_NO_SPECIAL_FDT_RECOVERY_COMMAND_POLICY DEFAULT
D257_SEED_FRESHNESS_GENERALIZATION UNPROVEN
D257_CURRENT_CORPUS_EXHAUSTED_FOR_SEED_FRESHNESS_GENERALIZATION true
D257_SAME_ATTACH_SEED_GENERATION_REQUIRED false
D257_PERSISTED_PRE_ATTACH_CACHE_REUSE_PROVEN true
D257_CACHE_MTIME_TO_ATTACH_BEGIN_SECONDS 1626.1975757
D257_CACHE_MTIME_TO_FIRST_0x36_SECONDS 1635.6222000
D257_GENERAL_CACHE_TTL_PROVEN false
D257_SEED_FRESHNESS_FACTORY_PRESERVATION_BLOCKER false
D257_SEED_FRESHNESS_FUNCTIONAL_SUCCESS_RISK true
D257_FDT_OFFLINE_CANDIDATE_CLOSED false
D257_HOST_BUS_LIFECYCLE_READY true
D257_SEED_FRESHNESS_IS_SOLE_LIVE_BLOCKER false
D257_READY_FOR_FDT_LIVE_REVIEW false
D257_READY_FOR_FDT_LIVE false
D257_LIVE_EXECUTION NOT_PERFORMED
D258_TARGET_BOOTSTRAP_SEQUENCE_HASH_GATED true
D258_GATE_0x50_STATUS PARTIAL_STORE_ROLE_CLOSED_POST_SAMPLE_CLASSIFIER_UNRESOLVED
D258_GATE_0x82_STATUS CLOSED_NATIVE_PREDICATE_IMPLEMENTED
D258_GATE_0x20_STATUS PARTIAL_ACQUISITION_ROLE_CLOSED_POST_SAMPLE_CLASSIFIER_UNRESOLVED
D258_D255_B0_DECRYPTION_STATUS INPUT_UNAVAILABLE_WITHOUT_PRIVILEGE
D258_COMMAND_TIMEOUT_POLICY PER_COMMAND_EVIDENCE_BOUNDED
D258_TIMEOUT_0x36_MS 500
D258_TIMEOUT_0x50_MS 500
D258_TIMEOUT_0x82_MS 500
D258_TIMEOUT_0x20_MS 2000
D258_TIMEOUT_0x32_MS 100
D258_CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x50_GATE true
D258_CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x82_GATE true
D258_CURRENT_LOCAL_CORPUS_EXHAUSTED_FOR_0x20_GATE true
D258_PROJECTED_FDT_SUBSEQUENCE_REPLAY PASS_HISTORICAL
D258_EXACT_TARGET_FRESH_BOOTSTRAP_REPLAY BLOCKED
D258_DYNAMIC_HOST_GATES_CLOSED false
D258_FDT_OFFLINE_CANDIDATE_CLOSED false
D258_HOST_BUS_LIFECYCLE_READY true
D258_SEED_FRESHNESS_FACTORY_PRESERVATION_BLOCKER false
D258_READY_FOR_FDT_LIVE_REVIEW false
D258_READY_FOR_FDT_LIVE false
D258_LIVE_EXECUTION NOT_PERFORMED
D259_OUTCOME BLOCKED_LIVE_TLS_RUNTIME_ADAPTER_GAP
D259_POST_CLASSIFIER_BRANCH_PROOF PASS_MECHANICALLY_DERIVED
D259_BRANCH_MATRIX_DERIVATION_MODE PARSED_DISASSEMBLY_CFG
D259_NAV_RETURN_CFG_PROVEN true
D259_IMAGE_RETURN_CFG_PROVEN true
D259_CLASS_A_CLASSIFIER_HOST_ONLY_FOR_FIRST_ARM true
D259_POST_STAGE2_CLASSIFIER_DEVICE_PROGRESS_REQUIRED false
D259_POST_STAGE2_CLASSIFIER_FACTORY_PRESERVATION_REQUIRED false
D259_POST_STAGE2_CLASSIFIER_FIRST_ARM_REQUIRED false
D259_POST_STAGE2_CLASSIFIER_OEM_HOST_FIDELITY_REQUIRED true
D259_POST_STAGE2_CLASSIFIER_HOST_PERSISTENCE_REQUIRED false
D259_NAV_CLASSIFIER_FINAL_0x32_EFFECT NONE
D259_IMAGE_CLASSIFIER_FINAL_0x32_EFFECT NONE
D259_CLASSIFIER_FDT_TABLE_EFFECT NONE
D259_CLASSIFIER_FINAL_0x32_PAYLOAD_EFFECT NONE
D259_CLASSIFIER_ADDITIONAL_DEVICE_COMMANDS NONE
D259_CLASSIFIER_RETRY_OR_REBUILD_EFFECT NONE
D259_CLASSIFIER_ERROR_RECOVERY_COMMANDS NONE
D259_BASELINE_B0_TLS_CONSUMPTION_REQUIRED true
D259_BASELINE_B0_IMAGE_CLASSIFICATION_REQUIRED false
D259_BASELINE_B0_RASTER_DECODE_REQUIRED false
D259_HISTORICAL_D255_B0_PLAINTEXT_AVAILABLE false
D259_FUTURE_LINUX_RUNTIME_TLS_SESSION_PROVEN true
D259_LIVE_TLS_ROLE SERVER
D259_LIVE_TLS_TO_B0_ADAPTER_STATUS UNIMPLEMENTED
D259_B0_CONSUMED_BEFORE_STAGE2 true
D259_TLS_SERVER_SESSION_OBJECT_COUNT 1
D259_TLS_CLIENT_SESSION_OBJECT_COUNT 1
D259_TLS_SERVER_HANDSHAKE_COUNT 1
D259_TLS_APPLICATION_RECORD_CONSUMPTION_COUNT 1
D259_SECOND_SERVER_SESSION_CREATED false
D259_SECOND_PSK_PROVISIONING false
D259_SAME_TLS_SESSION_B0_CONSUMPTION PASS_OFFLINE_ARCHITECTURAL
D259_POST_B0_TLS_SESSION_CONTINUITY PASS_OFFLINE_ARCHITECTURAL
D259_FUTURE_LINUX_RUNTIME_B0_CONSUMPTION_CAPABILITY false
D259_PLAINTEXT_MUTABLE_BUFFER_BEST_EFFORT_ZEROIZED true
D259_OPENSSL_INTERNAL_COPY_ZEROIZATION NOT_PROVEN
D259_PYTHON_IMMUTABLE_TEMP_COPY_ZEROIZATION NOT_PROVEN
D259_SRC_SEALED_UNCHANGED true
D259_LIVE_LAUNCHERS_UNCHANGED true
D259_OEM_CACHE_WRITE_BEFORE_FINAL_0x32 CONDITIONAL
D259_OEM_CACHE_WRITE_AFTER_FINAL_0x32 false
D259_OEM_CACHE_WRITE_REQUIRED_FOR_FINAL_0x32 false
D259_LINUX_FIRST_LIVE_CACHE_WRITE_POLICY DISABLED
D259_CORPUS_EXHAUSTED_FOR_EXACT_OEM_HOST_FIDELITY true
D259_CORPUS_EXHAUSTED_FOR_MINIMAL_DEVICE_LIVE_CONTRACT false
D259_MINIMAL_DEVICE_LIVE_CONTRACT_CLOSED false
D259_FACTORY_PRESERVING_MINIMAL_CANDIDATE_CLOSED false
D259_FDT_OFFLINE_CANDIDATE_CLOSED false
D259_READY_FOR_FDT_LIVE_REVIEW false
D259_READY_FOR_FDT_LIVE false
D259_NO_SPECIAL_FDT_RECOVERY_COMMAND_POLICY DEFAULT
D259_A2_REENTRY_INJECTION 0
D259_0x70_REENTRY_INJECTION 0
D259_HOST_CACHE_WRITE_COUNT 0
D259_REAL_USB_OPEN_COUNT 0
D259_REAL_CAPTURE_COUNT 0
D259_REAL_HARDWARE_ACTION_COUNT 0
D259_REAL_COMMAND_SEND_COUNT 0
D259_PERSISTENT_WRITE_FAMILY_COUNT 0
D259_LIVE_EXECUTION NOT_PERFORMED
D260_PERSISTENT_TLS_RUNTIME_IMPLEMENTED true
D260_TLS_SERVER_SESSION_OBJECT_COUNT 1
D260_TLS_SERVER_HANDSHAKE_COUNT 1
D260_SECOND_SERVER_SESSION_CREATED false
D260_SECOND_PSK_PROVISIONING false
D260_D4_POST_TLS_A0_PLAINTEXT_EXACTLY_ONCE true
D260_D4_TLS_APPLICATION_RECORD_COUNT 0
D260_POST_D4_TLS_ENGINE_RETAINED true
D260_EVENT_SOURCE_CONTRACT_REQUIRED true
D260_IRQ100_EVENT_SEPARATE_FROM_ACK_REQUIRED true
D260_EXACT_FDT_COMMAND_TRACE 36,50,36,82,20,36,32
D260_BASELINE_B0_CONSUMED_BEFORE_STAGE2 true
D260_SAME_TLS_SESSION_B0_CONSUMPTION PASS_OFFLINE_ARCHITECTURAL
D260_SECOND_NATIVE_DELTA_REQUIRED true
D260_CLASSIFIER_CALL_COUNT 0
D260_RASTER_DECODE_COUNT 0
D260_HOST_CACHE_WRITE_COUNT 0
D260_RETRY_COUNT 0
D260_PERSISTENT_WRITE_FAMILY_COUNT 0
D260_PHYSICAL_SUBMISSION_CONTRACT_STATUS ABSTRACT_OFFLINE_FOR_FDT_A0_WITH_EXACT_D4_AND_B0_TLS_POLICIES
D260_END_TO_END_OFFLINE_RUNTIME_REHEARSAL PASS
D260_FAILURE_CONTAINMENT_MATRIX PASS
D260_MINIMAL_DEVICE_LIVE_CONTRACT_CLOSED true
D260_FACTORY_PRESERVING_MINIMAL_CANDIDATE_CLOSED true
D260_FDT_OFFLINE_CANDIDATE_CLOSED true
D260_READY_FOR_FDT_LIVE_ARCHITECTURE_REVIEW true
D260_READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW false
D260_READY_FOR_FDT_LIVE_REVIEW false
D260_READY_FOR_FDT_LIVE false
D260_NEW_RUNTIME_LIVE_PROVEN false
D260_REAL_USB_OPEN_COUNT 0
D260_REAL_TLS_TARGET_HANDSHAKE_COUNT 0
D260_REAL_HARDWARE_ACTION_COUNT 0
D261_OUTCOME READY
D261_OPERATIONAL_EVIDENCE_HARDENING PASS
D261_FDT_A0_PHYSICAL_LENGTH 64
D261_FDT_A0_TAIL_POLICY ZERO_FILL_OUTSIDE_DECLARED_LOGICAL_FRAME
D261_FDT_A0_RESIDUE_REPLAY false
D261_FDT_ZERO_TAIL_0x32 PRIMARY_TARGET_OEM_ACCEPTED
D261_FDT_ZERO_TAIL_0x36_0x50_0x82_0x20 UNPROVEN_LIVE_HYPOTHESIS
D261_COLD_START_GPL_RUNTIME_IMPLEMENTED true
D261_REAL_USB_ADAPTER_IMPLEMENTED true
D261_ONE_PHYSICAL_EP81_READER true
D261_REAL_SECRET_BOUNDARY_IMPLEMENTED true
D261_SEED_LIVE_OTP_BINDING_REQUIRED true
D261_LIVE_CAPABILITY_DEFAULT 0
D261_LIVE_PATH_REACHABLE_WITHOUT_EXPLICIT_FLAG false
D261_SUPPORTED_LIVE_ENTRYPOINT_COUNT 1
D261_DIRECT_PYTHON_LIVE_CALL_WITHOUT_CAPABILITY_FAILS_CLOSED true
D261_CLI_INTENT_CAPABILITY_REQUIRED true
D261_LIVE_IO_CAPABILITY_REQUIRES_MARKER true
D261_MARKER_AFTER_PROTECTED_CONTENT_VALIDATION true
D261_MARKER_IMMEDIATELY_PRECEDES_LIVE_IO_CAPABILITY true
D261_REPORT_DIRECTORY_SAFETY_CHECKED_PRE_SIDE_EFFECT true
D261_PROTECTED_ROOT_SAFETY_CHECKED_PRE_SIDE_EFFECT true
D261_END_TO_END_OFFLINE_OPERATIONAL_REHEARSAL PASS
D261_FAILURE_CONTAINMENT_MATRIX PASS_EXECUTION_DERIVED
D261_FAILURE_SCENARIO_COUNT 24
D261_FAILURE_SCENARIO_EXECUTED_COUNT 24
D261_ASSERTION_ONLY_FAILURE_ROWS 0
D261_SHARED_READER_PHASE_DEADLINE_ENFORCED true
D261_TIMEOUT_RENEWAL_PER_UNMATCHED_FRAME false
D261_SINGLE_READER_DEMUX_EXECUTABLE_EVIDENCE PASS
D261_LIVE_IMPORT_CLOSURE_STATUS PASS
D261_LIVE_IMPORT_CLOSURE_PATH_COUNT 16
D261_LIVE_IMPORT_CLOSURE_MISSING_PATH_COUNT 0
D261_PACKAGE_INITIALIZERS_EXECUTED_AND_BASELINE_GATED true
D261_CORE_INIT_DRIFT_DETECTED true
D261_BINDING_REFERENCE_INIT_DRIFT_DETECTED true
D261_NO_IMPORT_TIME_SIDE_EFFECTS true
D261_IMPORT_SAFETY_TEST PASS
D261_IMPORT_TIME_USB_ATTEMPT_COUNT 0
D261_IMPORT_TIME_PROTECTED_FS_ACCESS_COUNT 0
D261_IMPORT_TIME_SECRET_INSTANTIATION_COUNT 0
D261_IMPORT_TIME_SECRET_MATERIALIZATION_COUNT 0
D261_IMPORT_TIME_FPRINTD_MUTATION_COUNT 0
D261_IMPORT_TIME_MARKER_CREATE_COUNT 0
D261_NON_SECRET_CONTENT_VALIDATED_BEFORE_SECRET_MATERIALIZATION true
D261_SECRET_MATERIALIZATION_LAST_PRE_MARKER_PROTECTED_READ true
D261_OFFLINE_REAL_SECRET_LOADER_INSTANTIATION_COUNT 0
D261_OFFLINE_REAL_SECRET_MATERIALIZATION_COUNT 0
D261_OFFLINE_SECRET_FALLBACK_FROM_REAL_TO_SYNTHETIC false
D261_FULL_TEST_SUITE 238_PASS
D261_LIVE_CRITICAL_PATH_SOURCE HARDCODED_REVIEWED_TUPLE_IN_VERIFIER
D261_LIVE_CRITICAL_FILESET_JSON_ROLE DERIVED_REPORT_NOT_AUTHORITY
D261_APPROVED_LIVE_BASELINE_SHA e9073a171697bd68dd2debabb851f23d007bf718
D261_OPERATIONAL_LIVE_CRITICAL_FILESET APPROVED_USER_AI_PM_FULL_SHA
D261_EXACT_APPROVED_LIVE_BASELINE_PRESENT true
D261_READY_FOR_BASELINE_APPROVAL_REVIEW false
D261_OPERATIONAL_REVIEW_PENDING_APPROVED_BASELINE false
D261_READY_FOR_FDT_LIVE_OPERATIONAL_REVIEW true
D261_READY_FOR_FDT_LIVE_REVIEW true
D261_READY_FOR_FDT_LIVE false
D261_REAL_USB_OPEN_COUNT 0
D261_REAL_SECRET_READ_COUNT 0
D261_REAL_COMMAND_SEND_COUNT 0
D261_FPRINTD_MUTATION_COUNT 0
D261_REAL_SINGLE_USE_MARKER_CREATE_COUNT 0
D261_REAL_HARDWARE_ACTION_COUNT 0
D261_LIVE_EXECUTION NOT_PERFORMED
D262_PRELIVE_OUTCOME READY
D262_PRELIVE_ADVANCEMENT LIVE_EXECUTION_READINESS_REVIEW
D262_PRELIVE_EXECUTION_TARGET STOP_AFTER_FDT_ARM_ACK
D262_PRELIVE_LIVE_CRITICAL_MODIFICATION_COUNT 0
D262_PRELIVE_LIVE_CRITICAL_WORKTREE_MATCH PASS
D262_PRELIVE_D261_OPERATOR_KIT_REUSED true
D262_PRELIVE_DRY_RUN PASS
D262_PRELIVE_DRY_RUN_REAL_USB_OPEN_COUNT 0
D262_PRELIVE_DRY_RUN_REAL_SECRET_READ_COUNT 0
D262_PRELIVE_DRY_RUN_REAL_COMMAND_SEND_COUNT 0
D262_PRELIVE_DRY_RUN_REAL_MARKER_CREATE_COUNT 0
D262_PRELIVE_DRY_RUN_FPRINTD_MUTATION_COUNT 0
D262_PRELIVE_FULL_TEST_SUITE 238_PASS
D262_PRELIVE_READY_FOR_D262_OPERATOR_EXECUTION_REVIEW true
D262_PRELIVE_READY_FOR_D262_OPERATOR_EXECUTION false
D262_PRELIVE_READY_FOR_FDT_LIVE_REVIEW true
D262_PRELIVE_READY_FOR_FDT_LIVE false
D262_PRELIVE_LIVE_EXECUTION NOT_PERFORMED
D262_LIVE_EXECUTION_PERFORMED_ONCE true
D262_LIVE_OUTCOME PASS
D262_LIVE_RESULT PASS_STOP_AFTER_FDT_ARM_ACK
D262_LIVE_PHASE_REACHED STOP_AFTER_FDT_ARM_ACK
D262_LIVE_TARGET_IDENTITY 27c6:5125
D262_LIVE_TARGET_FIRMWARE GF_ST411SEC_APP_12509
D262_APPROVED_BASELINE_SHA e9073a171697bd68dd2debabb851f23d007bf718
D262_LIVE_CRITICAL_FILESET_DIGEST 39d162077156b2af5fdb4b43d4382923006aa44f75e1e44c0fff741709761418
D262_EXACT_FDT_COMMAND_TRACE 0x36,0x50,0x36,0x82,0x20,0x36,0x32
D262_FDT_ARM_BOUNDARY_LIVE_PROVEN true
D262_FDT_ZERO_TAIL_0x32 PRIMARY_TARGET_PROVEN_AND_ACK_ACCEPTED
D262_FDT_ZERO_TAIL_0x36 PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
D262_FDT_ZERO_TAIL_0x50 PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
D262_FDT_ZERO_TAIL_0x82 PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
D262_FDT_ZERO_TAIL_0x20 PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED
D262_PRIMARY_ZERO_TAIL_RISK_RETIRED true
D262_ZERO_TAIL_PROOF_SCOPE PRIMARY_TARGET_27C6_5125_APP_12509_BOUNDED_FDT_ARM_PATH
D262_FINGER_INTERACTION_COUNT 0
D262_RASTER_DECODE_COUNT 0
D262_RETRY_COUNT 0
D262_PERSISTENT_DEVICE_WRITE_COUNT 0
D262_CACHE_WRITE_COUNT 0
D262_HOST_CACHE_WRITE_COUNT 0
D262_A2_SPECIAL_RECOVERY_COUNT 0
D262_0X70_SPECIAL_RECOVERY_COUNT 0
D262_USB_TRANSPORT_SESSION_COUNT 1
D262_TLS_SERVER_SESSION_OBJECT_COUNT 1
D262_TLS_SERVER_HANDSHAKE_COUNT 1
D262_TRANSPORT_REOPEN_AFTER_TLS false
D262_TRANSPORT_CLEANUP_COUNT 1
D262_TLS_CLOSE_COUNT 1
D262_SECOND_SERVER_SESSION_CREATED false
D262_SECOND_PSK_PROVISIONING false
D262_SECRET_BOUNDARY_HANDOFF_COUNT 1
D262_SECRET_BOUNDARY_ZEROIZED true
D262_SECRET_ZEROIZED true
D262_SECRET_LOG_COUNT 0
D262_BASELINE_B0_TLS_CONSUMED true
D262_BASELINE_B0_CONSUMED_BEFORE_STAGE2 true
D262_SECOND_NATIVE_DELTA_PASSED true
D262_FPRINTD_RESTORE_STATUS restored_to_initial_state
D262_SIGNAL_RESTORE_STATUS restored
D262_RUNTIME_STATE CLOSED
D262_SINGLE_USE_MARKER_STATUS claimed_single_use
D262_SECOND_LIVE_ATTEMPT_ALLOWED false
D262_NEXT_LIVE_BOUNDARY_REQUIRES_NEW_AI_PM_REVIEW_AND_EXPLICIT_USER_AUTHORIZATION true
D262_OUTCOME PASS
D262_ADVANCEMENT LIVE_FDT_ARM_BOUNDARY_PROVEN
D262_EXECUTABLE_CLOSURE PASS
D262_READY_FOR_D262_OPERATOR_EXECUTION_REVIEW false
D262_READY_FOR_D262_OPERATOR_EXECUTION false
D262_READY_FOR_FDT_LIVE_REVIEW false
D262_READY_FOR_FDT_LIVE false
D262_CANONICAL_MANUAL_UPDATED true
```

Il corpus sa dove si trovano i receiver ma non contiene i loro corpi. La safety
ristretta D231 deriva dalla convergenza di control flow, dataflow, due versioni
host e wire OEM; non dall'ordine della capture o dalla sola raggiungibilità.

## Evidenza primaria richiesta per riaprire

La via readback si riapre esclusivamente con almeno una delle seguenti fonti:

1. firmware resident/combined 12509 provenance-valid;
2. capture target recuperata/nuova che usa un opcode assente dal census D230;
3. artefatto OEM target-specific che documenta una readback interface;
4. evidenza primaria indipendente equivalente.

La capture definitivamente perduta, se recuperata e contenente un nuovo opcode,
rientrerebbe nel punto 2. “Cercare ancora” nello stesso corpus non è una
condizione di riapertura.

## Implicazione strategica

`NO_NOT_WITH_CURRENT_LOCAL_CORPUS_AND_CONSTRAINTS`

Non esiste oggi una strada tecnicamente concreta e factory-preserving per
estrarre autonomamente dal sensore il resident code mancante. Questo resta vero
anche se D231 consente di implementare e revisionare offline in D232 l'exact OEM
replay senza tale estrazione.

## Stato implementazione Linux

Stato corrente post-D278/03: la shell `FpImageDevice` non registrata
è ora implementata in C/LGPL con backend in-memory e validata host-only
(`LOCAL_LIBFPRINT_DEVICE_GLUE_SLICE_1=IMPLEMENTED_CORRECTIVE_EXECUTABLY_CLOSED_HOST_ONLY`).
L'architettura production resta chiusa
(`LOCAL_LIBFPRINT_DEVICE_GLUE_ARCHITECTURE=CLOSED_D276_01`) ed è una
reimplementazione nativa C/LGPL indipendente con provenance controllata e
in-process, con un solo `GoodixDeviceContext` per open epoch. Il context è owner
di TLS/secret, ma lifetime TLS fra più activation e quiescenza device-side dopo
cancel arbitrario restano irrisolti. Il release tail corrente completa
`0x20`/B0-discard/`0x50`/NAV prima del finger-off; solo il re-arm `0x32`
dipende da `AWAIT_FINGER_ON`, tail completo e down-table fresca. Il rescue D276/02
e la successiva CI su GitHub Actions (run 33165906857, commit `87d4aacec23b5415cca5de73e0dfeb83ffe65bab`)
hanno chiuso la executable closure host-only con 2 run deterministiche (14/14
normal PASS, 14/14 ASAN/UBSAN PASS, `CI_DIAGNOSTIC_PATCH=NONE`). La precedente
indisponibilità di Flatpak/GLib-dev nell'ambiente di rescue è superata. D276/03
ha inoltre chiuso `PASS_HOST_ONLY` il router A0/B0 single-receive: commit CI
`49e7e9d108d14fc7a9910d97022cd4baa829c5e4`, run push 33184060807 e PR
33184064239 PASS, merge `main` `474aa2b931977a2c748098c4e510764ad7ee7f42`.
Il boundary D276/04 è chiuso `PASS_HOST_ONLY`.

D277/01 ha aggiunto un harness nativo test-only e ha tentato una sola run A8
reale, terminata prima del claim e di ogni submit per `USB_OPEN_FAILED` nel
contesto operatore corrente. Il nodo USB era `root:root` `0664` senza ACL e
l'utente non aveva write permission; questa causa resta strong inference nel
record storico D277/01. Il correttivo host-only ha aggiunto un permission
preflight read-only che blocca prima di `g_usb_device_open()` quando il nodo non
è scrivibile.

D277/02 ha eseguito, con autorizzazione single-shot consumata, una run live sullo
stesso target `27c6:5125` (bus 1, address 4, port 7). Dopo una ACL named-user
temporanea applicata e rimossa manualmente dall'operatore sul solo nodo
`/dev/bus/usb/001/004`, l'harness ha aperto/reclamato il dispositivo, ha
sottomesso l'exact A8 `a00600a6a803000000ff`, ha ricevuto ACK logico A8 e
risposta tipata con firmware `GF_ST411SEC_APP_12509`, e ha rilasciato/chiuso il
dispositivo. Il percorso nativo A8/A0 è quindi target-proven entro i limiti del
bounded path A8→ACK→risposta tipata; TLS, E4, finger path, image path e qualunque
scrittura persistente non sono stati esercitati. L'autorizzazione live corrente
è falsa e ogni nuova run richiede un nuovo preflight permessi e nuova
autorizzazione esplicita.

D278/01 integra nello stesso `GoodixDeviceContext` una state machine
secure-session LGPL isolata e un codec A0 indipendente. Il context resta la sola
generation authority e il router l'unico receive owner; il backend ammette un
solo OUT fisico, mentre l'egress TLS conserva un B0 per record, chunk fisici da
64 byte, tail zero e pacing 10 ms cancellabile. La suite sintetica usa il vero
OpenSSL e chiude TLS 1.2 PSK senza application data, D4 o azioni
post-handshake. La disponibilità del codice e dei test non promuove equivalenza
hardware: `NATIVE_SECURE_SESSION_TARGET_PROVEN=false`; nel contesto D278/01 il
raw CONFIG_90 target non era disponibile all'esecutore e il live non era autorizzato.

D278/02 introduce `GoodixTargetMaterial` come unico owner dello scratch
protetto, della PSK, di CONFIG90 e del validator E4 fino alla costruzione della
sessione. La produzione accetta soltanto i path fissi dello store root-owned,
la DLL canonica hash-pinned e i contratti target D232/D245; il test policy seam
non modifica i costanti produttivi. `GoodixD278Harness` orchestra la stessa
state machine per transport sintetico o `FpiUsbTransfer`, deriva telemetria
redatta dallo stato reale e impedisce teardown prima del drain. Il launcher
`d278_native_secure_session_once` è live-capable ma, nello step, soltanto il
ramo sintetico `--self-test` è stato eseguito. In seguito l'operatore ha
eseguito il preflight autentico read-only dei materiali protetti (`--material-preflight-only`,
29 agosto 2026): il protected store reale è stato letto una sola volta in modo
read-only con i privilegi host necessari, mentre GUsb enumeration/open/claim e
ogni transfer reale sono rimasti irraggiungibili (zero accesso USB,
`e4_binding_match=true`, `project_secret_zeroized=true`).

D278/03 ha dapprima chiuso la review pre-live senza modificare il runtime. La
singola run poi autorizzata ha completato A8, inviato E4 ed è terminata al gate
del primo frame E4, con cleanup sicuro e autorizzazione consumata. Il
correttivo post-live modifica soltanto il sequencer/harness nativo e i test:
una tabella ACK per fase riconcilia il C a D238 con i soli successi
`0x01|0x07`, preserva D1 diretto B0/TLS e aggiunge telemetria strutturale
redatta della prima failure. Tutte le suite pertinenti passano host-only; non
è stata eseguita una seconda run, né usato `sudo`, store protetto o USB reale.
Una futura live resta non autorizzata e, in caso di nuova failure E4, è vietata
una terza full run equivalente senza diagnostica separata.

Artefatti: `analysis/D276/D276_01_libfprint_device_architecture.{md,json}`,
`analysis/D276/D276_02_fpimage_device_shell_host_only.{md,json}` e
`analysis/D276/D276_03_usb_router_host_only.{md,json}`,
`analysis/D276/D276_04_native_tls_fpi_usb_host_only.{md,json}` e
`analysis/D277/D277_01_native_a8_real_usb.{md,json}` e
`analysis/D277/D277_02_native_a8_real_usb.{md,json}` e
`analysis/D278/D278_01_native_secure_session_host_only.{md,json}` e
`analysis/D278/D278_02_native_target_material_secure_session_prep.{md,json}` e
`analysis/D278/D278_03_native_secure_session_prelive_closure.md`,
`analysis/D278/D278_03_native_secure_session_live_result_20260829.json` e
`analysis/D278/D278_03_e4_ack_policy_corrective.md`.

Il repository implementa il codec immagine clean-room, il seam D232, la
reference D190 recuperata, il backend/orchestratore D233, l'entrypoint
production-candidate D235, il consolidamento D238, l'evidenza D239 e la
transizione command→TLS D241, le evidenze E4 D242/D243/D244 e il kit D245 per
la precondizione read-only A8→E4 con continuazione TLS. D245 è ora anche una
run live TLS riuscita; D246 ha aggiunto ed eseguito live il solo D4 volatile con
stop immediato, completando il percorso implementato fino a quel boundary. Le
sorgenti sono state ripristinate e sealed dopo la run. L'implementazione storica include ABI libusb esatta e TLS OpenSSL, ma non
costituisce ancora un driver libfprint pronto. D249 aggiunge
`core/post_d4.py`, GPL-2.0-or-later e privo di backend USB: framing/parsing
fail-closed, AF, demux A0 + byte-stream applicativo B0 già decifrato, builder/eventi
FDT, due state path bounded fino a `FIRST_IMAGE_RECEIVED` e delega diretta al
codec immagine locale canonico. L'allowlist
rende E0/A4/F0/F4 e le famiglie provisioning/firmware irraggiungibili per
costruzione. Il record immagine noto è di 7684 byte:
7680 byte packed-12 più CRC-32/MPEG-2, convertito in raster u16 `80x64` con
transpose.

D250 aggiunge il terminale AF-only, la patch continuation sopra la catena
D245→D246 e la matrice avversaria. Il primo bundle aveva un launcher invocabile
soltanto in dry-run; la correzione same-step aggiunge il ramo live hard-gated,
il namespace/marker D250, il preflight specifico e il verifier Git del
live-critical set. Il set include launcher, patch chain, preflight/helper, core
AF, sorgenti backend/entrypoint, PE canonico e dipendenze transitive che possono
influire sul path sensor-reaching; manuale, report, bundle e test offline non
sono pin-nati. Una fixture Git prova `APPROVED` pulito e `STALE` mutando ciascun
file del set senza consultare lo staging index. Il codice sorgente USB storico
resta sealed nel repository; patch apply/reverse e hash dimostrano ripristino
byte-identico. Il dry-run reale passa dalla root e da cwd esterno. Questa è
executable closure offline del percorso operatore live-capable, non esecuzione
hardware né approvazione del commit live.

D251 mantiene invariato quel wire path e aggiunge una patch continuation
successiva che rimuove esclusivamente il gate `byte0 == 1`, rinomina il campo
opaco e corregge response count/classificazione/telemetria. Il launcher usa il
nuovo marker `d251-operator-invocation.marker` e la directory `d251-results`,
tratta il marker D250 come storico benigno ma consumato, applica
D245→D246→D250→D251 e ripristina le sorgenti sealed byte-exact. La matrice
offline copre byte0 `1`, `0` e `2`, failure strutturali, timeout, ACK inatteso,
completion ambigua, duplicati e fence post-AF. Quel launcher è stato poi
eseguito una volta sulla baseline approvata e ha chiuso AF con `byte0=0`,
`flags=0x02`, stop terminale e restore completo; il marker è consumato.

D252 non aggiunge runtime USB né operator kit. Aggiunge soltanto un audit
offline GPL hash-gated della capture, la decisione strutturata e il report
step-local. Il modello D249 `IRQ2→0x20` resta storico e viene esplicitamente
marcato non wire-exact rispetto al target `IRQ2→0x22`; non è stato promosso un
nuovo percorso perché tabella fresh e restore non sono entrambi chiusi.

D253 corregge soltanto il core GPL offline corrente e i test: la state machine
usa `IRQ2→0x22`, conserva `0x20` come builder baseline distinto e applica un
fence single-shot prima del secondo comando. L'audit/report/decisione sono
step-local; non esistono backend USB aggiunti, persistenza host, live kit o
autorizzazione hardware. Bootstrap seed, contratto fisico `0x36` e restore
restano bloccanti.

D254 aggiunge soltanto parser e derivati sanitizzati hash-gated. Clone, WBDI,
ZIP e PCAP esterni restano fuori dal repository; non sono stati importati
codice runtime, secret, OTP, immagini o payload biometrici. La corroborazione
esterna non modifica guardrail, non crea un backend/launcher e non autorizza
hardware. D254 lasciava seed APP12509 iniziale e restore no-finger bloccanti;
D255/D256 hanno poi provato la correlazione target cache→seed e la re-entry
senza restore USB esplicito, restringendo ma non chiudendo causalità/freschezza,
disarm e lifetime interna. Il corrective D256 chiude invece il distinto
terminal-stop host/bus come quiescenza USB path-bounded.

D255 ha aggiunto il kit PowerShell GPL e il postprocessor GPL offline, poi ha
acquisito la capture APP12509 definitiva e ne ha recuperato offline la
finalizzazione. Il raw canonico da 27.684 byte/218 frame prova cold attach,
bootstrap, zero finger, cancel e re-entry; non è richiesta una nuova run D255.
Le revisioni e i failure pre-attach precedenti restano provenance storica nella
sezione D255, non stato corrente dell'implementazione.

D256 aggiunge soltanto l'audit GPL offline e derivati sanitizzati: timeline
CSV/MD completa dei packet target, decisione lifecycle, test minimi e report.
Non modifica il runtime live-critical, il core FDT, fprintd o un operator kit.
Il nuovo modello corrente ammette re-entry e re-arm senza restore USB esplicito
osservato e chiude separatamente il terminal-stop host/bus come cancellazione
della bulk-IN pendente più quiescenza USB fino alla fine della capture. Il
bundle D256 corrective sostituisce il precedente artefatto D256 ed esclude raw
USB, cache, DLL, firmware, OTP, PSK e biometria.

D257 aggiunge `core/fdt_lifecycle.py`, `core/fdt_seed.py`, l'integrazione
observer opzionale in `core/post_d4.py`, test e replay offline. Il corrective
aggiunge l'audit esatto del raw e il candidate ordinato
`36,50,36,82,20,36,32`, con gate dinamici espliciti e failure containment
single-shot sul primo `0x36`. Il provider accetta solo cache esplicita valida,
OTP-bound e read-only; cancel/re-entry/terminal-stop restano host-only e
recovery speciali/famiglie persistenti restano vietate per costruzione. Il
vecchio replay è una sottosequenza proiettata storica; l'esatto resta bloccato
sui predicati NAV/delta/baseline non derivabili. La chiusura separata
IRQ2→`0x22`→prima immagine usa una fixture sintetica non biometrica. Non sono
stati aggiunti backend USB, launcher, baseline approvata o operator kit, e il
live resta non autorizzato.

D258 estende soltanto il core e gli audit offline: preserva NAV/B0 come input
runtime, implementa il predicate target `0x82`, sposta correttamente i
classificatori dopo stage2 e introduce timeout per comando. L'audit statico e
il replay sono hash-gated e non esportano raw, OTP, cache, DLL, secret o raster.
Storicamente D258 lasciava il final `0x32` irraggiungibile finché entrambi i
classificatori post-stage2 non fossero riproducibili; D259 supera precisamente
questa conclusione per branch audit causale, senza retro-modificare gli
artefatti D258.

D259 aggiunge il consumer B0 TLS post-handshake riutilizzabile in `core/`, il
finalizer del contratto minimo, matrici branch/wire/recovery/cache hash-gated,
replay D255-by-reference e test OpenSSL con secret/plaintext sintetici non
biometrici. La compatibilità D258 del finalizer host-semantico storico resta
testata, mentre il nuovo path minimo conserva B0 TLS consumption e due delta
native ma ha contatori classifier, raster e cache a zero. Nessun dato storico
B0 è decrittato o esportato. Non sono stati aggiunti backend USB, launcher,
operator kit, baseline live approvata o autorizzazione hardware.

D260 aggiunge `core/runtime_transport.py` e `core/persistent_runtime.py` ed
estende il TLS e lifecycle FDT esistenti senza toccare `src/`. Il nuovo core
separa framing logico, policy fisica ed eventi asincroni; conserva un solo
server TLS oltre l'handshake, lascia D4/AF/FDT come A0 plaintext e inoltra il
solo B0 baseline allo stesso engine. Il rehearsal sintetico production-shaped
copre l'intera sessione e 15 failure terminali. D4 e B0 hanno policy fisiche
evidence-backed; gli A0 FDT restano `ABSTRACT_LOGICAL_ONLY`. Questa è
executable closure del runtime offline e architecture readiness, non un
backend USB, un path operatore o una readiness live.

D261 aggiunge `core/cold_start.py`, `core/protected_runtime.py` e
`core/usb_runtime.py`, rende operativa la policy FDT fixed-64 zero-tail nel
coordinator e aggiunge entrypoint e launcher D261. Il live-critical set è
hardcoded e verificato sia contro la working tree sia contro ogni blob di un
full commit SHA esternamente approvato; il riferimento architetturale D260 è
letto dal commit storico, non da report rigenerabili nella working tree. Il
corrective mantiene la tuple hardcoded come autorità e riclassifica il JSON
fileset come report derivato; il verifier include se stesso. Separa capability
CLI-intent e Live-I/O, sposta materiale protetto prima del marker, anticipa i
gate delle directory, rende assoluta la deadline del shared reader e rende
execution-derived matrici failure/demux e safety del report durable. Il
corrective finale completa inoltre la tuple con i due package initializer,
prova import purity in un subprocess nuovo e impone manifest/config/cache
non-secret prima del secret. Il dry-run reale è cwd-independent, non legge il
secret e non apre USB; il rehearsal usa soltanto fixture sintetiche iniettate e
non istanzia il real loader. La baseline live-critical
`e9073a171697bd68dd2debabb851f23d007bf718` è ora approvata da Utente e AI-PM
(EXACT_APPROVED_LIVE_BASELINE_PRESENT=true), promuovendo la readiness a review
operativa/live senza autorizzare hardware (READY_FOR_FDT_LIVE=false). Il
precedente bundle D261 resta preservato ma è
`SUPERSEDED_BY_D261_OPERATIONAL_EVIDENCE_HARDENING_CORRECTIVE`.

### D218–D220: closure del contratto immagine Windows e boundary Linux/libfprint

La closure canonica D218–D220 (recuperata da `docs/EVIDENCE.md`, WIN-001, e da
`README.md`) definisce il contract di intensità dell'immagine e non va reinventata
da D268/02. I fatti supportati sono:

- il record immagine è `7684` byte (7680 packed-12 + CRC-32/MPEG-2) e produce un
  raster `u16`/`80x64` trasposto — `CONFIRMED` (codec clean-room + decoder OEM);
- il preprocessing Windows/`AlgoChicago.dll` (selezionato da `EngineAdapter.dll`
  con sensor index 12) consuma **direttamente** il raster `u16`/12-bit
  (`INTENSITY_CONTRACT=DIRECT_U16_CONSUMED_PROVEN`, WIN-001);
- non è giustificato alcun adapter `u16 → u8` ricostruito dal contratto Windows
  (`D220_WINDOWS_PREPROCESSOR_CONSUMES_U16_NO_U8_ADAPTER_JUSTIFIED`);
- l'orientamento fisico del raster resta `UNRESOLVED`;
- la successiva decisione è **Linux-specifica**
  (`NEXT_BLOCKER=LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT`):
  Linux deve definire il proprio contract `FpImage`/`libfprint` dopo che
  l'acquisizione live è sicura (residual uncertainty di WIN-001).

D268/02 preserva questa closure: il nuovo fatto D268 (`target live image →
valid image record → decoded raster 80x64 u16`) eredita lo stesso contract
`u16`. D269/01 chiude poi la decisione Linux-specifica senza reinterpretare il
contratto Windows: il core GPL mantiene il raster canonico, mentre il glue LGPL
valida 5120 sample nel range `0..4095` e produce il packed u8 libfprint tramite
mapping fixed full-range `round(v*255/4095)`. L'orientamento fisico/naturale e la
polarità restano `UNRESOLVED`; zero flag significa conservare l'ordine canonico
del decoder, non dichiararlo fisicamente orientato.

Lo stato di implementazione Linux per il dominio libfprint, aggiornato da
D271/01, è pertanto:

```text
PIXEL_REPRESENTATION_CONTRACT=CLOSED_OFFLINE
INTENSITY_QUANTIZATION_CONTRACT=CLOSED_OFFLINE
FPIMAGE_OBJECT_CONSTRUCTION=CLOSED_OFFLINE
FPIMAGE_BUFFER_OWNERSHIP=CLOSED_OFFLINE
FPIMAGE_DIMENSION_CONTRACT=CLOSED_OFFLINE
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
UNKNOWN_PPMM_SEMANTICS=EXPLICITLY_BOUNDED
NBIS_PPMM_REQUIREMENT=REQUIRED_VERIFIED
NBIS_WITH_UNKNOWN_PPMM=BLOCKED
SIGFM_PPMM_REQUIREMENT=NOT_CONSUMED_VERIFIED
FEATURE_EXTRACTOR_POLICY=CLOSED_OFFLINE
SIGFM_STATUS=CANDIDATE_FOR_VALIDATION
NBIS_STATUS=BLOCKED_UNKNOWN_PHYSICAL_PPMM_AND_TARGET_LOCAL_MINUTIA_DENSITY_UNPROVEN
SIGFM_80X64_SUPPORT_STATUS=ARCHITECTURALLY_SUPPORTED_WITH_MIN_25_KEYPOINT_GATE_TARGET_QUALITY_UNPROVEN
NBIS_80X64_SUPPORT_STATUS=STRUCTURALLY_ACCEPTED_MIN_8PX_BLOCK_BUT_TARGET_USABILITY_BLOCKED
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
BIOMETRIC_QUALITY_STATUS=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED
FULL_FPIMAGE_PIPELINE_CONTRACT=PARTIALLY_CLOSED
NEXT_PRIMARY_BOUNDARY=SIGFM_TARGET_LOCAL_BIOMETRIC_VALIDATION
NEXT_BOUNDARY_PREREQUISITE=AUTHORIZED_PRIVACY_PRESERVING_TARGET_REAL_KEYPOINT_AND_MATCH_METRICS_WITH_D269_FIXED_MAPPING
```

Il contratto pixel, la quantizzazione, la costruzione del GObject, le dimensioni
e l'ownership sono `CLOSED_OFFLINE`. Il full `FpImage` pipeline contract è
soltanto `PARTIALLY_CLOSED`: lo stato separato D270 rende l'ignoto `ppmm`
truth-preserving senza trasformare lo zero storage in una misura; NBIS resta
bloccato. D271 sceglie SIGFM soltanto come candidato di validazione, sulla base
del call-flow, del supporto strutturale 80×64 e della corroborazione terza parte;
non risolve qualità, orientation o polarity e non seleziona un path production.


## D262: fresh-FDT arm execution-readiness review offline

D262 esegue una **final execution-readiness review offline** del bounded fresh-FDT arm
usando il candidate D261 già approvato, senza modificare alcun file live-critical e
senza hardware. La baseline live-critical immutabile rimane
`e9073a171697bd68dd2debabb851f23d007bf718` (sha completo approvato da Utente e AI-PM).

Il live path futuro validato è:

```text
A8
→ E4
→ exact cold-start pre-D1
→ D1
→ TLS 1.2 PSK handshake
→ D4 plaintext A0
→ AF / AE
→ fresh FDT:
   0x36 stage0 → ACK → IRQ 0x0100 → 0x50 → ACK + response
   → 0x36 stage1 → ACK → IRQ 0x0100 → 0x82 → ACK + response
   → 0x20 → ACK → B0 baseline on SAME retained TLS session
   → authenticate/decrypt/consume B0
   → 0x36 stage2 → ACK → IRQ 0x0100 → 0x32 → ACK
→ STOP_AFTER_FDT_ARM_ACK
```

Il candidate riutilizza il kit operatore D261
(`operator_kit/d261-live-fdt-arm-once.sh` + `tools/d261_live_fdt_arm_once.py`) con il
ramo `--dry-run` e con cwd realistico (repo root). `D262_LIVE_CRITICAL_MODIFICATION_COUNT=0`:
nessun file del live-critical set D261 è stato toccato. Il verifier D261 conferma che
TUTTI i 17 blob del set sono byte-identici ai blob del commit di baseline. Nessun nuovo
runtime/launcher D262 è stato creato.

Verifiche eseguite in D262 (tutte offline, zero hardware):

```text
D261_APPROVED_LIVE_BASELINE_SHA = e9073a171697bd68dd2debabb851f23d007bf718
D261_APPROVED_BASELINE_RESOLVES = true
D261_LIVE_CRITICAL_WORKTREE_MATCH = PASS
D261_LIVE_CRITICAL_MISMATCH_COUNT = 0
D262_LIVE_CRITICAL_MODIFICATION_COUNT = 0
D262_D261_OPERATOR_KIT_REUSED = true
D262_DRY_RUN = PASS
D262_DRY_RUN_REAL_USB_OPEN_COUNT = 0
D262_DRY_RUN_REAL_SECRET_READ_COUNT = 0
D262_DRY_RUN_REAL_COMMAND_SEND_COUNT = 0
D262_DRY_RUN_REAL_MARKER_CREATE_COUNT = 0
D262_DRY_RUN_FPRINTD_MUTATION_COUNT = 0
D262_EXECUTION_TARGET = STOP_AFTER_FDT_ARM_ACK
D262_EXACT_FDT_COMMAND_TRACE = 0x36,0x50,0x36,0x82,0x20,0x36,0x32
D262_RETRY_COUNT = 0
D262_AUTOMATIC_RETRY_COUNT = 0
D262_AUTOMATIC_RECOVERY_COMMAND_COUNT = 0
D262_PERSISTENT_WRITE_FAMILY_COUNT = 0
COMMAND_0X22_REACHABLE = false
POST_FINGER_IMAGE_REACHABLE = false
ENROLLMENT_REACHABLE = false
MATCHING_REACHABLE = false
FINGER_INTERACTION_REQUIRED = false
FINGER_INTERACTION_ALLOWED = false
IRQ_FINGER_DOWN_REQUIRED = false
A2_0X70_RECOVERY_AFTER_FDT_FAILURE = forbidden
PHYSICAL_USB_OUT_LENGTH = 64
FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND = 0x36/0x50/0x82/0x20
PRIMARY_FUTURE_LIVE_RISK = FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND
```

Questo blocco descrive lo stato offline pre-live della readiness review. Dopo
l'esecuzione live una tantum, il rischio `FDT_A0_ZERO_TAIL_DEVICE_ACCEPTANCE_UNPROVEN_PER_COMMAND`
è **ritirato** per `27c6:5125` / `GF_ST411SEC_APP_12509` sul bounded FDT arm path:
`0x36/0x50/0x82/0x20` sono ora `PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED`;
`0x32` resta `PRIMARY_TARGET_PROVEN_AND_ACK_ACCEPTED`
(v. sezione "D262: esecuzione live una tantum e closure" e Hard Wall).

Il rehearsal end-to-end offline (238 test suite PASS) conferma che il runtime
giunge solo a `STOP_AFTER_FDT_ARM_ACK` dopo il terzo `0x36`/IRQ `0x0100` e l'ACK finale
`0x32`, con una sola sessione TLS, un solo server, un solo handshake, zero retry,
zero famiglie persistenti, zero A2/`0x70` di recovery, secret zeroizzato e fprintd
ripristinato. Il dry-run è cwd-independent, non legge il secret e non apre USB;
l'import safety dimostra zero side-effect a import-time in un subprocess non
privilegiato (16 moduli Python, closure 16/16). Il live-critical set è verificato
blob-per-blob contro la baseline approvata.

La decisione corrente restava invariata: `READY_FOR_D262_OPERATOR_EXECUTION_REVIEW=true`,
`READY_FOR_D262_OPERATOR_EXECUTION=false`, `READY_FOR_FDT_LIVE=false`. D262 non aveva
ancora aperto hardware, non aveva letto secret reale, non aveva aperto USB reale, non
aveva creato marker reale e non aveva tolto fprintd. La prossima azione era esclusivamente
la review AI-PM del bundle D262 e la decisione/autorizzazione live esplicita dell'Utente,
con esecuzione terminale da eseguire manualmente dall'operatore su base single-shot.

### D262: esecuzione live una tantum e closure del confine fresh-FDT arm

La review AI-PM è stata completata e la run è stata eseguita una sola volta (single-shot)
e si è chiusa con `PASS_STOP_AFTER_FDT_ARM_ACK`. La prova primaria del rapporto operatore
(recuperato read-only da `/var/lib/goodix-5125-poc/d261-results/d261-final.json`) è
riprodotta fedelmente negli artefatti `analysis/D262/D262_live_fdt_arm_result.json`,
`D262_post_live_closure_report.md` e `D262_post_live_decision.json`.

Risultato live (target `27c6:5125`, firmware `GF_ST411SEC_APP_12509`, baseline immutabile
`e9073a171697bd68dd2debabb851f23d007bf718`, live-critical fileset digest
`39d162077156b2af5fdb4b43d4382923006aa44f75e1e44c0fff741709761418`):

```text
D262_LIVE_ATTEMPT = PASS
D262_LIVE_RESULT = PASS_STOP_AFTER_FDT_ARM_ACK
PHASE_REACHED = STOP_AFTER_FDT_ARM_ACK
EXACT_FDT_COMMAND_TRACE = 0x36,0x50,0x36,0x82,0x20,0x36,0x32
FDT_ARM_BOUNDARY_LIVE_PROVEN = true

FINGER_INTERACTION_COUNT = 0
RASTER_DECODE_COUNT = 0
RETRY_COUNT = 0
PERSISTENT_DEVICE_WRITE_COUNT = 0
CACHE_WRITE_COUNT = 0
HOST_CACHE_WRITE_COUNT = 0
A2_SPECIAL_RECOVERY_COUNT = 0
0X70_SPECIAL_RECOVERY_COUNT = 0

USB_TRANSPORT_SESSION_COUNT = 1
TLS_SERVER_SESSION_OBJECT_COUNT = 1
TLS_SERVER_HANDSHAKE_COUNT = 1
TRANSPORT_REOPEN_AFTER_TLS = false
TRANSPORT_CLEANUP_COUNT = 1
TLS_CLOSE_COUNT = 1

SECOND_SERVER_SESSION_CREATED = false
SECOND_PSK_PROVISIONING = false
SECRET_BOUNDARY_HANDOFF_COUNT = 1
SECRET_BOUNDARY_ZEROIZED = true
SECRET_ZEROIZED = true
SECRET_LOG_COUNT = 0

BASELINE_B0_TLS_CONSUMED = true
BASELINE_B0_CONSUMED_BEFORE_STAGE2 = true
SECOND_NATIVE_DELTA_PASSED = true

FPRINTD_RESTORE_STATUS = restored_to_initial_state
SIGNAL_RESTORE_STATUS = restored
RUNTIME_STATE = CLOSED

SINGLE_USE_MARKER_STATUS = claimed_single_use
SECOND_LIVE_ATTEMPT_ALLOWED = false
```

La traccia FDT esatta è stata accettata dal target primario con ACK. Il rischio zero-tail
per `0x36/0x50/0x82/0x20` passa da `UNPROVEN_LIVE_HYPOTHESIS` a
`PRIMARY_TARGET_LIVE_PROVEN_AND_ACK_ACCEPTED`; `0x32` resta `PRIMARY_TARGET_PROVEN_AND_ACK_ACCEPTED`.
Lo scope della prova è limitato a `27c6:5125` / `GF_ST411SEC_APP_12509` sul bounded FDT arm
path. Non si generalizza ad altri device, firmware, comandi di controllo, flusso post-finger,
`0x22`, enrollment/matching o scritture persistenti. Nessuna interazione dito, nessun retry,
nessuna scrittura persistente/cache, nessun recovery A2/`0x70`, un'unica sessione USB e un
solo handshake/server TLS, B0 consumato sulla stessa sessione TLS prima di stage2, secret
zeroizzato e non loggato, fprintd e segnale ripristinati, runtime chiuso.

`D262_PRIMARY_ZERO_TAIL_RISK_RETIRED=true`; `D262_ZERO_TAIL_PROOF_SCOPE=
PRIMARY_TARGET_27C6_5125_APP_12509_BOUNDED_FDT_ARM_PATH`. Il marker single-use è consumato e
la stessa run non deve essere ripetuta: il prossimo confine live richiede nuova AI-PM review
e autorizzazione hardware esplicita dell'Utente. I vincoli factory-preserving e di
compatibilità Windows restano integrali. Lo stato massimo è `OUTCOME=PASS`,
`ADVANCEMENT=LIVE_FDT_ARM_BOUNDARY_PROVEN`, `EXECUTABLE_CLOSURE=PASS`; i flag `READY_FOR_*`
restano false perché D262 è già eseguito e chiuso, non perché D262 sia fallito.

## D263: post-arm order e policy fisica `0x22` (sottostep 01)

D263/01 ricostruisce e chiude, con evidenza primaria target-specific, il tratto
`final 0x32 → IRQ 0x0002 → 0x22 [01 00] → first image` e ne classifica la
policy fisica USB di `0x22`. Esecuzione OFFLINE, strictly no-USB/no-sudo/no-secret.

La capture primaria è `analysis/D230/work/GoodixExport/rilevamento.pcapng`
(`GF_ST411SEC_APP_12509`, SHA-256
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`), hash-gated.
La capture D255 (`VALID_ZERO_FINGER`) **non** contiene il sottoalbero
post-arm (`FINGER_DOWN_IRQ_COUNT=0`, `POST_IRQ2_0x22_COUNT=0`); pertanto il
tratto è derivato da `rilevamento.pcapng`, non da D255. Issue #63 (21/21 IRQ2→
`0x22`) resta solo corroborazione esterna, non autorità primaria APP12509.

Ordine osservato (indici pacchetto zero-based):

```text
0x32 arm  OUT@220 / ACK@223 echo 0x32 status 0x01
IRQ finger-down  IN@225  value 0x0002  wrapper 3f00d500ee00c800ba00c500d200
0x22  OUT@227  body 01 00  logical A0=10  physical OUT=64
0x22  ACK@229  echo 0x22 status 0x01
first image  IN@231  outer 0xB0  TLS(17 03 03)  size 7726
subtree: 0x34@233 → IRQ 0x0200@237 → 0x20[01 00]@238 → 2a immagine B0/TLS@243
         → 0x50@244 → … → final 0x32@251 / ACK@253
```

Derivazioni meccaniche `0x22`: body `01 00`; lunghezza logica A0 = **10**;
lunghezza fisica OUT = **64**; 54 byte fuori frame; unici 6 non-zero a offset
fisici **40–45** = `cb f2 e2 be fb 7f` (staging residue, identica a `0x36`/`0x20`,
non payload). ACK echo `0x22`/status `0x01`, subito dopo l'OUT e prima della
prima immagine. Prima immagine: outer `0xB0`, **TLS** (`17 03 03`), 7726 byte;
nessun frame A0 "immagine" la precede. Occorrenze `0x22` nel primary corpus:
**1** OUT (`rilevamento.pcapng`@227), 0 IN; D255 = 0; Issue#63 = 21 (esterno).

`MINIMUM_CAUSAL_REQUIREMENT`: la capture prova l'**ordine**
`0x32(arm,ACK) → IRQ0x0002 → 0x22[01 00](ACK) → first image`; **non** prova
che `0x22` sia l'unico comando necessario né che l'IRQ finger-down lo richieda
causalmente (osservato ≠ causale).

**Taxonomy `0x22` = `PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY`.** Il post-arm order,
ACK/echo/status e la policy fisica fixed-64 sono direttamente osservati nella
capture primaria APP12509. Il live proof D262 copre **solo** il bounded FDT arm
(`0x36,0x50,0x36,0x82,0x20,0x36,0x32`, `STOP_AFTER_FDT_ARM_ACK`) e **non**
raggiunge il sottoalbero finger-down/`0x22`/immagine; dunque `0x22` NON è
live-proven/accepted.

**Modello `0x22` (coerente con `D263_01` v2).**
- *Observed on primary target:* logical A0 length 10; physical OEM OUT length 64;
  out-of-frame residue/staging observed (offset 40–45 = `cb f2 e2 be fb 7f`).
- *Linux deterministic operational candidate:* `FIXED64_ZERO_TAIL`.
- *Candidate status:* `EVIDENCE_SUPPORTED_DETERMINISTIC_CANDIDATE`.
- *Device acceptance of Linux zero-tail on `0x22`:* `NOT_LIVE_PROVEN`.

La capture primaria prova la **submission** OEM fixed64 e supporta la scelta
candidate zero-tail; **non** conferma live l'acceptance device del zero-fill
Linux su `0x22` (`phase2_model_confirmed` di `D263_01` = `false`).

Artefatti `analysis/D263/`: `d263_01_0x22_evidence_audit.py`,
`D263_01_post_arm_order.json`, `D263_01_0x22_physical_policy.json`,
`D263_01_report.md`, `D263_workflow_state.json`. Nessun ZIP in 01.

### D263/02: retained TLS e pipeline first-image (sottostep 02)

Audit OFFLINE dell'architettura esistente per
`encrypted first-image B0 -> retained TLS -> Goodix payload -> image record -> CRC -> packed12 -> 80x64`,
senza modifiche runtime. Esito `PASS_AUDIT_NOT_BLOCKED`.

Retained TLS: `PersistentRuntimeCoordinator` crea **una** sola
`Tls12PskServerSession` (`server_session_object_count=1`,
`psk_context_provisioning_count=1`, `handshake_count=1`); l'adapter
`MemoryBioApplicationSessionAdapter` può consumare più application
record sulla stessa sessione retainita (baseline B0 = record #1). La stessa
sessione può quindi teoricamente trasportare anche il primo B0 immagine
(IRQ2 → 0x22 → first-image). Tuttavia `run()` si ferma a `machine.arm(ts16)` e
il `finally` chiude TLS prima di qualsiasi post-arm: la fase post-arm non è
cablata. Chi decripta B0: `B0ApplicationConsumer.consume`
(`core/tls_b0.py:287`); chi parse l'immagine:
`parse_image_payload`→`decode_image_record`→`src/goodix5125_cleanroom.decode_record`
(servono i byte decriptati). `FdtLifecycle` ha già gli stati/metodi
`FDT_ARMED_WAIT`, `FIRST_IMAGE_RECEIVED`, `post_irq2_image_command`,
`first_image_received`, ma il coordinator/macchina di produzione non li
invoca: la transizione terminale `FDT_ARMED_WAIT → FIRST_IMAGE_RECEIVED` è assente.
Nessun redesign TLS/transport richiesto (target: ONE USB/TLS session, ONE
handshake, ONE secret boundary, ZERO second PSK/reopen è già soddisfatto).

Pipeline immagine: codec canonico **unico** in `src/goodix5125_cleanroom.py`
(packed12, `RECORD_BYTES=7684`, `SAMPLE_COUNT=5120`, raster 80×64, CRC-32/MPEG-2
fail-closed). `decode_image_record` è solo wrapper. Nessun decoder duplicato.
Test esistenti: `test_cleanroom.py`, `test_d249_post_d4.py`,
`test_d257_fdt_candidate.py` (tutti fixture sintetiche). `FIRST_IMAGE_RECEIVED`
è raggiunto solo da `FirstImageMachine` (offline/test), non dal coordinator.

Artefatti `analysis/D263/`: `D263_02_retained_tls_map.json`,
`D263_02_first_image_pipeline.json`, `D263_02_runtime_gap_report.md`. Nessun ZIP.

### D263/03: terminal stop dopo la first image e gate Phase 1 (sottostep 03)

OFFLINE, no live, no patch runtime. Confronto con il ciclo positivo primario
(`rilevamento.pcapng`, in `D263_workflow_state.observed_order`): lo stack
Windows dopo la prima immagine invia `0x34` (arm finger-up, manuale 170-171) →
`IRQ 0x0200` → `0x20` (seconda immagine) → `0x32` re-arm. Questo è
multi-enrollment e **non** prova che `0x34`/`0x20`/re-arm siano richiesti per
uno stop host dopo la prima immagine.

Candidato terminale D263/03:
`0x32 → IRQ 0x0002 → 0x22 → first image → HOST/TLS/USB CLEANUP → STOP`,
senza `0x34`, `0x20`, re-arm, A2, `0x70`, reset, retry, comandi persistenti.

Host cleanup (VERIFICATO fattibile/implementato): cancel pending receive
(D255/D256 quiescenza bus: pending IN cancellato a frame 218, zero packet
residui), TLS close (`core/persistent_runtime.py` finally), USB release/close,
restore `fprintd` exactly-once (manuale 912-928, 1377-1387), nessun comando
Goodix extra (D255/D256: intervallo cancel senza packet target).

Device internal state (UNKNOWN per taxonomy): FDT/finger post-image non noto
(D252 BLOCKED); `0x34` osservato solo come arm finger-up, necessità non provata;
tolleranza disconnect device-side non osservata; recovery cold start INFERITO OK
(D256: nuovo `0x32` accettato senza restore USB); restore device-side non
osservato, A2/`0x70` NON sono restore FDT.

Classificazione: `FIRST_IMAGE_TERMINAL_STOP=EVIDENCE_SUPPORTED_BUT_DEVICE_INTERNAL_STATE_UNKNOWN`.
`D263_PHASE1_READY_FOR_PHASE2_OFFLINE_RUNTIME_INTEGRATION=true`: autorizza solo
design/implementazione **OFFLINE** del candidato bounded (cablare path post-arm
first-image su TLS retainita + cleanup host esattamente-once + STOP), NON live
review né live execution. Baseline D262 `e9073a17...` rispettata, non regredita.

Artefatti `analysis/D263/`: `D263_03_terminal_boundary_evidence.json`,
`D263_03_terminal_boundary_decision.json`, `D263_03_phase1_decision.json`,
`D263_03_report.md`. Nessun ZIP.

### D263/04: Phase 2 design contract e patch plan (sottostep 04, design-only)

Gate Phase 2 `READY` (`D263_PHASE1_READY…=true`). Nessuna patch runtime in
04. Contratto minimo: `D262 path → arm 0x32 ACK → bounded wait IRQ 0x0002 →
exactly one 0x22 [01 00] → retained TLS receives first B0 → parser/codec
canonico valida+decodifica → FIRST_IMAGE_RECEIVED → bounded host-only terminal
cleanup → STOP`. Invarianti: one USB/TLS session+handshake, zero second
secret/USB reopen/retry/A2/`0x70`/`0x34`/`0x20`-post/re-arm/persistent-write,
first-image bytes non persistiti (plaintext azzerato, raster solo in memoria),
fail-closed su mismatch.

Primitive riusate (nessun duplicato): `build_finger_image` (post_d4.py:257),
`parse_fdt_event` (irq==2, post_d4.py:273),
`application_session.consume_application_record` (tls_b0.py:252),
`parse_image_payload`/`decode_image_record` (post_d4.py:336/347 → codec
canonico), `lifecycle.post_irq2_image_command`/`first_image_received`/
`cancel_pending_receive`/`terminal_stop` (fdt_lifecycle.py:222/230/234/251).
Il gap era solo in `PersistentRuntimeCoordinator.run()` che si ferma a
`machine.arm(ts16)` (persistent_runtime.py:232).

Patch plan (step 05/06, ciascuno <15 min):
- **Step 05**: `core/runtime_transport.py` (aggiungere `0x22` agli allowlist
  `fdt_a0_policy`/`operational_fdt_a0_policy`); `core/fdt_lifecycle.py`
  (aggiungere `0x22` a `COMMAND_TIMEOUT_MS`; `cancel_pending_receive` accetta
  anche `FIRST_IMAGE_RECEIVED`). Rischio basso.
- **Step 06**: `core/persistent_runtime.py` (orchestrazione post-arm: wait
  IRQ2 → un `0x22` → receive B0 TLS → decode → `first_image_received` →
  `cancel_pending_receive`+`terminal_stop`; rilassare il check
  `EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE` a prefisso + audit comandi proibiti;
  arricchire `RuntimeResult`); nuovo `tests/test_d263_phase2_first_image_terminal.py`.
  Rischio medio, mitigato da riuso primitive auditate, single-use, fail-closed,
  cleanup exactly-once.

Hash pre-change dei file live-critical in
`D263_04_live_critical_prechange_hashes.json` (baseline per step 05/06).

Artefatti `analysis/D263/`: `D263_04_phase2_contract.json`,
`D263_04_patch_plan.md`, `D263_04_live_critical_prechange_hashes.json`. Nessun ZIP.

### D263/05: Phase 2 support primitives lifecycle + transport (sottostep 05)

Gate READY + contract step 04 valido. Implementati SOLO i support primitives;
il coordinator NON è stato esteso (rimandato a step 06).

`core/fdt_lifecycle.py` (`2aac7422…93a33a`): `COMMAND_TIMEOUT_MS` +`0x22:2000`;
`post_irq2_image_command` con guard one-shot (secondo tentativo →
`fail_closed`+`InvalidTransition`, niente re-arm retry); `cancel_pending_receive`
ora accetta anche `FIRST_IMAGE_RECEIVED` (cleanup host terminale post-first-image
per la decisione step 03). `core/runtime_transport.py` (`2930aa57…3e38d`):
`0x22` aggiunto a `fdt_a0_policy` (ABSTRACT_LOGICAL_ONLY, **non** live-proven,
nessun tail inventato) e a `operational_fdt_a0_policy`
(FIXED64_ZERO_TAIL_D261_CANDIDATE, deterministico zero-fill). `0x34`/`0xA2`/`0x70`
restano rifiutati da entrambe. Nuovo `tests/test_d263_phase2_support_primitives.py`
(12 test sintetici, tutti OK): valid transition (trace termina `0x32,0x22`, nessun
`0x34`/`0x20`), one-shot `0x22`, second attempt rejected, wrong-order rejected,
terminal transition, prohibited unreachable, physical frame construction,
deterministic tail. Coordinator invariato (`8e448caa…0df12c`).

Artefatti `analysis/D263/`: `D263_05_change_summary.json`,
`D263_05_test_results.json`, `D263_05_report.md`. Nessun ZIP.

### D263/06: Phase 2 PersistentRuntime first-image integration (sottostep 06)

Gate READY + step05 PASS. Esteso il production-shaped
`PersistentRuntimeCoordinator` (`persistent_runtime.py`
`c266ef8a…3963af`) con il minimo percorso offline candidato:
`D262 arm complete -> bounded IRQ2 wait -> exactly-one 0x22 -> retained TLS
first-image B0 -> canonical parser/codec -> FIRST_IMAGE_RECEIVED -> bounded
host/TLS/USB cleanup -> stop`. Nuovo metodo `_run_first_image_terminal()`
riusa `build_finger_image`, `parse_image_payload`/`decode_image_record` (codec
canonico) e la retained TLS B0 application session; nessun parser/codec
duplicato. `run()` chiama il metodo dopo `arm(ts16)` e rilassa il check del
trace esatto a prefisso `EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE` + extra esattamente
`(0x22)` + audit comandi proibiti; `RuntimeResult`/`audit()` arricchiti. Il
`finally` esistente (TLS close + secret zeroize + USB release) resta
exactly-once su ogni failure. `tests/test_d263_phase2_first_image_terminal.py`
(8 test sintetici TLS, tutti OK) copre happy-path completo, wrong IRQ, timeout,
wrong ACK, malformed B0, CRC/image failure (plaintext azzerato), prevenzione
second 0x22 (one-shot), nessun pixel persistito, one-session/one-handshake/no-
reopen. Invarianti: one USB/TLS session+handshake, zero second secret/USB
reopen/retry, same retained session, esattamente un `0x22`, no
`0x34`/`0x20`-post/re-arm/`A2`/`0x70`/persistent-write, first-image bytes non
persistiti, fail-closed su mismatch, cleanup su failure. Nota: l'env Cloud non
ha OpenSSL PSK; i test usano TLS sintetico, il path `Tls12PskServerSession` di
produzione è validato da `test_d259` in env con OpenSSL-PSK.

Artefatti `analysis/D263/`: `D263_06_runtime_integration_summary.json`,
`D263_06_test_results.json`, `D263_06_report.md`. Nessun ZIP.

### D263/07: executable closure, regression audit, micro-corrective (sottostep 07)

Sottostep conclusivo di review offline end-to-end del change-set D263 (Phase 2
attiva: gate Phase1 READY + step05/06 completati). Closure eseguibile
verificata: coordinator importato da cwd repo-root, path resolution ok,
invocazione offline via double iniettati (nessun USB/live), failure reporting
fail-closed (`run()` -> `FAILED_CLOSED` + `lifecycle.fail_closed()` + re-raise;
`audit()` espone `failure_reason`), single-use (`runtime_single_use`),
cleanup garantito nel `finally` (TLS zeroize + secret boundary + transport).

Regression audit (checklist prompt): sequence state machine esatta (trace
prefisso `EXACT_FRESH_BOOTSTRAP_COMMAND_TRACE` + solo `(0x22)`); one-shot
(`post_irq2_image_command` incrementa `image_command_attempt_count` e fail-closed
al secondo tentativo; coordinator single-use); no forbidden reachability
(`run()` rifiuta `{0x34,0xA2,0x70,0x20}` post-arm e impone `extra==(0x22,)`;
lifecycle `_record` rifiuta non-allowlist/persistent/recovery); physical `0x22`
policy coerente con evidence e con il contratto `D263_04`: il runtime seleziona
`fdt_a0_policy(0x22,…)` = `ABSTRACT_LOGICAL_ONLY` quando `operational_physical_policy`
è false, e `operational_fdt_a0_policy(0x22,…)` = `FIXED64_ZERO_TAIL` (candidato
deterministico Linux, `EVIDENCE_SUPPORTED_DETERMINISTIC_CANDIDATE`, **NON**
live-accepted) quando è true; nessun nuovo submission mode inventato; nessuna
claim di acceptance device; retained TLS single-session (`handshake_count==1`,
`second_server_session_created=False`, stesso secret-boundary); no second
handshake/provision/reopen (`session_count==1`, `psk_context_provisioning_count==1`);
first-image non persistita (plaintext azzerato dopo decode, azzerato anche su
fallimento decode; solo shape `(…,64)` in report, mai pixel; `host_cache_write_count=0`);
cleanup in success/failure; lifecycle terminale
(`FIRST_IMAGE_RECEIVED`->`HOST_WAIT_CANCELED`->`TERMINAL_STOPPED`); exception
fail-closed; no log di payload sensibile; nessun path operator/live preparato.

Micro-corrective (unico step con correzione permessa): difetto locale —
`_run_first_image_terminal` hardcodava `first_image_raster_shape=(80,64)`
invece di derivarlo dal decode canonico. Corretto:
`raster = parse_image_payload(bytes(plaintext)); outcome["first_image_raster_shape"] = (len(raster)//64, 64)`
(`core/persistent_runtime.py` `c266ef8a…` -> `1a731cda…`); decode canonico
inalterato, nessun pixel persistito, scope/invarianti invariati. Retest: 8+12 D263
test PASS.

Test: D263-targeted 20/20 PASS; full discovery 248 (5 fail + 33 err + 3 skip)
tutti ambientali (no OpenSSL PSK / `patch` / libusb / synthetic-TLS client nel
Cloud), pre-esistenti a D263: i guasti ambientali osservati nel Cloud avvengono
prima di raggiungere il path D263 modificato — il rehearsal D260 importa in via
transitiva `core/persistent_runtime.py`, ma il failure Cloud avviene prima del
path D263; nessuna regressione è attribuibile al change-set D263. Nessuna
regressione D263. Integrity: vs `D263_04`, cambiano esattamente i tre
file patch-ati (persistent_runtime, runtime_transport, fdt_lifecycle); tutti gli
altri live-critical (backend/guardrail/launcher) byte-identici.

Artefatti `analysis/D263/`: `D263_07_executable_closure.json`,
`D263_07_regression_results.json`, `D263_07_live_critical_diff_manifest.json`,
`D263_07_report.md`. Nessun ZIP.

### D263/08: consolidamento finale, closure canonica, UNICO bundle (sottostep 08, ultimo)

Consolidamento OFFLINE di D263 (Phase 1 + Phase 2). Nessuna feature nuova.
Verifica di coerenza tra sottostep 01–07: nessuna contraddizione (taxonomy
`0x22`=`PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY` costante; gate Phase1 READY
coerente; step05/06/07 implementano esattamente il contratto `D263_04`; hash
live-critical coerenti con `D263_07`).

Esito finale: **`OFFLINE_IMPLEMENTATION_READY_FOR_AI_PM_REVIEW`** (non live-ready).
D263 ha provato offline: (a) ordine post-arm target-specific
`0x32(arm,ACK)→IRQ0x0002→0x22[01 00](ACK)→first image(TLS B0)→host/TLS/USB
cleanup→STOP`; (b) policy `0x22`: logical offline = `ABSTRACT_LOGICAL_ONLY`;
operational Linux candidate = `FIXED64_ZERO_TAIL`
(`EVIDENCE_SUPPORTED_DETERMINISTIC_CANDIDATE`, `NOT_LIVE_PROVEN`); nessun padding
inventato per la policy logica, mentre il candidato operativo è deterministico e
non live-accepted; (c) pipeline first-image canonica unica (TLS retained → codec
`decode_image_record` 7684-byte → 80×64, CRC fail-closed); (d) retained TLS
single-session/single-handshake; (e) terminal-stop su coordinator di produzione
cablatо ed esercitato end-to-end con double offline; (f) micro-correttiva shape
raster derivata dal decode.

Stato canonico D263 (coerente con i marker globali del manuale):

```text
CURRENT BOUNDARY            = D263 implements an opt-in OFFLINE first-image terminal candidate; default coordinator run() boundary remains STOP_AFTER_FDT_ARM_ACK (D260/D262); D263 non live
READY_FOR_FDT              = architecture-review true; operational/live false
SECOND_LIVE_ATTEMPT_ALLOWED= false (single-use coordinator; D262 marker consumato)
FRESH_FDT_BOOTSTRAP_LIVE_PROVEN = true
FINAL_FDT_ARM_LIVE_PROVEN       = true
POST_ARM_0x22_LIVE_PROVEN        = false
FIRST_IMAGE_LIVE_PROVEN          = false
FDT_DOWN_TABLE_LIVE_READY (storico D252, solo stato storico) = false
0x22                       = PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY; non live-proven
0x22_LOGICAL_OFFLINE_POLICY= ABSTRACT_LOGICAL_ONLY
0x22_OPERATIONAL_LINUX_CANDIDATE = FIXED64_ZERO_TAIL (EVIDENCE_SUPPORTED_DETERMINISTIC_CANDIDATE, NOT_LIVE_PROVEN)
FIRST_IMAGE                = pipeline canonica OFFLINE chiusa; non persistita
D262_OUTCOME               = PASS_STOP_AFTER_FDT_ARM_ACK (baseline e9073a17… non regredita)
D263                       = OFFLINE_IMPLEMENTATION_READY_FOR_AI_PM_REVIEW
D263_PHASE1_READY_FOR_PHASE2_OFFLINE_RUNTIME_INTEGRATION = true
D263_PHASE2_EXECUTED       = true
D263_PHASE2_RESULT         = OFFLINE_PASS (no live)
D263_EXECUTABLE_CLOSURE    = PASS_OFFLINE
D263_LIVE_CRITICAL_MODIFICATION_COUNT = 3 (persistent_runtime, runtime_transport, fdt_lifecycle)
D263_CORRECTIVE_MODIFICATION_COUNT  = 1 (solo core/persistent_runtime.py: defect A + B)
D263_HARDWARE_ACTION_COUNT = 0
D263_READY_FOR_LIVE_REVIEW = false
D263_READY_FOR_LIVE        = false
D263_LIVE_EXECUTION        = NOT_PERFORMED
```

File live-critical cambiati (vs `D263_04`): `core/persistent_runtime.py`,
`core/runtime_transport.py`, `core/fdt_lifecycle.py`. Tutti gli altri
backend/guardrail/launcher live-critical sono byte-identici. Nessun live
test/autorizzazione; nessun comando USB/PSK/OTP/flash. Bundle unico:
`D263_post_arm_first_image_offline_bundle.zip` (+ `.sha256`), step-local,
non cumulativo, con manifest path+SHA-256, senza raw capture/secret/biometric.

Review necessaria prima di qualunque futuro live: baseline live approvata
esplicitamente dall'AI PM; autorizzazione live separata; verifica del
live-critical set contro questo bundle; riapertura dei blocchi D252/D253/D255
(device-side restore/cancel, arm lifetime, current-path seed) con evidenza OEM
mirata. `0x22` resta `OBSERVED_ONLY` finché un live dedicato non lo accetta.

### D263/09: correttivo post-review AI-PM (defect A/B + normalizzazione)

Correttivo OFFLINE dello stesso milestone D263, senza rifare D263 da zero né
ampliare il boundary, né preparare/eseguire live. Branch
`session/agent_16ceb075-09cc-4bef-9575-02c7f6528892`, HEAD
`320dbf3c…`, stato clean. Esecuzione strictly OFFLINE; live hardware vietato.

**Defect A — regressione semantica D260/D262 in `run()` (CHIUSO).** `run()`
invocava incondizionatamente `_run_first_image_terminal()` dopo l'arm,
promuovendo implicitamente ogni consumer (incl. il rehearsal D260) al boundary
D263. Correzione: enum esplicito `TerminalBoundary`;
`STOP_AFTER_FDT_ARM_ACK` è il **default** (preserva D260/D262: termina dopo
il final `0x32` ACK, nessun IRQ2/`0x22`/first-image); `STOP_AFTER_FIRST_IMAGE`
è **opt-in**. Il check della command trace dipende dal boundary scelto
(arm-only: trace storica esatta; first-image: prefisso esatto + unico suffix
`(0x22,)`). I test pubblici `run()` arm-only lo provano end-to-end in modo
environment-independent (senza OpenSSL-PSK).

**Defect B — `operational_physical_policy` ignorata sul nuovo `0x22` (CHIUSO).**
`_run_first_image_terminal()` usava sempre `fdt_a0_policy(0x22,…)`. Correzione:
`0x22` seleziona `operational_fdt_a0_policy` (`FIXED64_ZERO_TAIL`) quando
`operational_physical_policy=true`, altrimenti `fdt_a0_policy`
(`ABSTRACT_LOGICAL_ONLY`). Nessun nuovo submission mode inventato; nessuna
claim di acceptance live. `Zero22PolicySelectionTests` verifica il mode
realmente passato a `transport.submit()`.

**Normalizzazione taxonomy/policy `0x22` (coerente con `D263_01` v2).**

```text
0x22                       = PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY
0x22_LOGICAL_OFFLINE_POLICY= ABSTRACT_LOGICAL_ONLY
0x22_OPERATIONAL_LINUX_CANDIDATE        = FIXED64_ZERO_TAIL
0x22_OPERATIONAL_ZERO_TAIL_CANDIDATE    = EVIDENCE_SUPPORTED_DETERMINISTIC_CANDIDATE
0x22_LIVE_ACCEPTANCE       = NOT_LIVE_PROVEN
0x22_ACK_POLICY            = EXACTLY_ONE_REQUIRED_AND_VALIDATED
FIRST_IMAGE_TERMINAL_STOP  = EVIDENCE_SUPPORTED_BUT_DEVICE_INTERNAL_STATE_UNKNOWN
HOST_CLEANUP_MECHANISM_SUPPORTED             = true
POST_FIRST_IMAGE_HOST_CLEANUP_IMPLEMENTED_OFFLINE = true
POST_FIRST_IMAGE_DEVICE_INTERNAL_STATE       = UNKNOWN
POST_FIRST_IMAGE_DEVICE_STOP_LIVE_PROVEN     = false
```

La capture primaria conferma la **submission** OEM fixed64 e supporta la scelta
candidate zero-tail; **non** conferma live il padding zero Linux su `0x22`. Il
`phase2_model_confirmed` di D263/01 è stato riportato a `false` per non essere
interpretato come acceptance device.

**Closure pubblica `run()` (Sezione 5).** Aggiunti test OFFLINE, sintetici,
environment-independent che esercitano il metodo pubblico `run()` (non il
privato): (A) backward-compat arm-only (stop dopo arm, nessun `0x22`, trace
esatta, cleanup exactly-once, nessun retry/persistenza); (B) first-image opt-in
end-to-end success (un solo session/handshake/secret-handoff, prefisso storico
+ unico `0x22`, ACK valido, first B0 su TLS retained, codec canonico, immagine
valida, non persistita, `TERMINAL_STOPPED`, cleanup exactly-once) e failure
path (fail-closed, cleanup once, nessun secondo `0x22`/recovery/persistenza).

**Audit regression.** 27 test D263 PASS (12 support-primitives + 8
first-image + 7 public-run nuovi). I test D260 pertinenti falliscono solo per
limite ambientale Cloud (`SSLContext` senza `set_psk_client_callback`):
il fallimento avviene alla costruzione di `SyntheticTlsClient` in
`d260_offline_rehearsal`, **prima** che qualunque modulo D263 esegua — non è
una regressione D263. Nessuna regressione attribuibile ai tre moduli D263.

**Bundle.** Rigenerato `D263_post_arm_first_image_offline_bundle.zip` (+`.sha256`)
dopo il correttivo; step-local, non cumulativo. File live-critical cambiati dal
solo correttivo: `core/persistent_runtime.py` (`1a731cda…`→`36963ce7…`);
`core/runtime_transport.py` e `core/fdt_lifecycle.py` invariati
(`2930aa57…`, `2aac7422…`). Nessun launcher/operator-kit modificato.

**Esito correttivo: `D263_CORRECTIVE = PASS`.** Stato finale:
`OFFLINE_IMPLEMENTATION_READY_FOR_AI_PM_REVIEW`; `D263_HARDWARE_ACTION_COUNT=0`;
`D263_READY_FOR_LIVE_REVIEW=false`; `D263_READY_FOR_LIVE=false`;
`D263_LIVE_EXECUTION=NOT_PERFORMED`. Nessuna autorizzazione live concessa né
consumata.

## Regole operative

- niente erase, IAP, ClearApp, F0/F4, cambio boot-mode o provisioning sostitutivo;
- niente payload privati, secret o materiale biometrico nei log/bundle;
- nessun comando live senza autorizzazione esplicita e step separato;
- qualunque test hardware/live esclusivamente tramite Kit Operatore dedicato,
  senza Python o comandi USB manuali, con interazione e messaggi in italiano;
- fonti di modelli Goodix correlati sono atlanti strutturali, non prova target;
- ogni promozione di safety richiede sorgente, control flow, dataflow, lifetime
  ed effetto persistente chiusi sul target.

## Riferimenti

L'indice pubblico delle claim è `docs/EVIDENCE.md`; le fonti OEM/private e i
riferimenti community sono elencati in `docs/REFERENCES.md`. Gli artefatti
D230–D262 sono sotto `analysis/`; nessuna fonte proprietaria raw, WBDI esterna
o capture Issue #63 raw è redistribuita.

## D264/01: audit terminal-state first-image e finestra di arm

D264/01 è un audit target-oriented OFFLINE; non ha eseguito D261/D262, USB,
dito, secret reale o comandi. La baseline contenuto iniziale coincide con
`4db9058a3235b82c8777f306a89bab10eb863337`; il branch osservato era `work`
anziché l'atteso `codex-cloud` ed è stato lasciato invariato. Questo SHA non è
una baseline live approvata.

La capture primaria APP12509 hash-gated osserva, dopo la prima immagine,
`0x34 → IRQ 0x0200 → 0x20 → seconda immagine → 0x50 → successivo 0x32`.
Questa è **HOST WORKFLOW CONTINUATION**, non evidenza di un **DEVICE-SIDE
REQUIREMENT FOR SAFE STOP**. Capture e analisi locale `gfusb.dll` verificano
`0x34` come arm finger-up/continuation primitive; non esiste evidenza primaria
che sia cancel, disarm, restore o requisito pre-disconnect. `gfOnCancel` cancella
la richiesta host senza inviare direttamente A0; A2 e `0x70` non sono osservati
come restore post-image. Rockytkg corrobora il ruolo finger-up, senza diventare
prova APP12509. La Issue #1 esterna non era accessibile (HTTP 401) e nessun suo
contenuto è stato ricostruito a memoria.

Recoverability: D256 prova una cancellazione host con quiescenza USB terminale
(491,125998 s, zero packet) e una re-entry sullo stesso device/endpoints in cui
un nuovo `0x32` è accettato senza reset, re-enumerazione o restore USB esplicito.
D262 prova poi live l'exact bounded fresh-FDT path, incluso il cold-start OEM
che contiene A2 come reset sensore volatile. Ne segue l'inferenza delimitata che
un eventuale stato FDT post-image è recuperabile al cold-start successivo. Lo
stato interno resta però `POST_FIRST_IMAGE_DEVICE_INTERNAL_STATE=UNKNOWN` e non
viene dichiarato SAFE. Non sono osservati write NVM post-image, il candidato non
contiene famiglie di scrittura persistente e non emerge un path plausibile di
stato persistente/non recuperabile; l'assenza assoluta di mutazione NVM resta
non direttamente osservabile.

La finestra primaria è: `0x32` OUT@220, ACK@223, IRQ2@225, `0x22`@227,
ACK@229, primo B0@231. Dai timestamp pcap: ACK32→IRQ2 **7108,212 ms**,
IRQ2→`0x22` 2,404 ms, IRQ2→ACK22 2,952 ms e IRQ2→B0 50,217 ms. Esiste una sola
osservazione positiva: non prova TTL o lifetime device, comportamento con dito
immediato/tardivo o no-finger. Il modello bounded futuro è una singola deadline
host monotonic assoluta dopo ACK32, non rinnovata da frame inattesi, attesa
exactly-once di IRQ2 e cleanup host-only fail-closed alla scadenza. La deadline
raccomandata è **15000 ms**: copre l'unico delta target con margine, ma non è una
claim sulla lifetime interna. Il valore D263 5000 ms avrebbe scartato la traccia
primaria a 7,108 s; D264 applica quindi il corrective minimo a 15000 ms e un test
di regressione, senza altra modifica runtime.

Riesame blocker:

| Blocker storico | Classificazione D264/01 | Motivo corrente |
| --- | --- | --- |
| provenienza/freschezza first-`0x36` | `SUPERSEDED_BY_D262_LIVE_EVIDENCE` | D262 ha accettato live una volta l'intero bounded path che consuma quel seed; la sorgente ultima resta conoscenza, non blocker operativo dello stesso path |
| cancel/disarm/restore | `RESIDUAL_KNOWLEDGE_GAP_ONLY` | nessun restore device provato, ma D256 prova cancel host, quiescenza e re-entry senza restore esplicito |
| arm lifetime | `RESIDUAL_KNOWLEDGE_GAP_ONLY` | lifetime interna ignota; deadline host bounded separata dalla TTL device |
| IRQ2→`0x22` | `BOUNDARY_SPECIFIC_UNPROVEN_HYPOTHESIS` | ordine primario osservato, causalità e acceptance live non provate |
| zero-tail fisica `0x22` | `STILL_RELEVANT_LIVE_BLOCKER` | candidate deterministico supportato; D262 non ha inviato `0x22` |
| first image | `STILL_RELEVANT_LIVE_BLOCKER` | capture OEM e codec offline non equivalgono a esecuzione Linux live |
| stato device post-image | `RESIDUAL_KNOWLEDGE_GAP_ONLY` | unknown conservato; persistenza/danno irrecoverabile non supportati dall'evidenza |

L'audit del codice conferma default
`TerminalBoundary.STOP_AFTER_FDT_ARM_ACK` e opt-in esplicito
`STOP_AFTER_FIRST_IMAGE`; one IRQ2 wait, one `0x22`, one ACK, primo B0 sulla TLS
retained, zero secondo secret/reopen/retry/`0x34`/post-image `0x20`/re-arm/A2/
`0x70`/write persistenti/persistenza biometrica e cleanup exactly-once. Il gate è:

```text
FIRST_IMAGE_TERMINAL_RISK=ACCEPTABLY_BOUNDED
D264_01_READY_FOR_OFFLINE_OPERATIONALIZATION_REVIEW=true
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
BASELINE_APPROVED=false
POST_FIRST_IMAGE_DEVICE_INTERNAL_STATE=UNKNOWN
POST_FIRST_IMAGE_DEVICE_STOP_LIVE_PROVEN=false
0x22_TARGET_LIVE_ACCEPTANCE=NOT_LIVE_PROVEN
FIRST_IMAGE_LIVE_PROVEN=false
```

Gli artefatti machine-readable e il report di review sono in `analysis/D264/`.

### D264/02: candidate operatore first-image, executable closure OFFLINE

D264/02 rende il boundary D263 operativamente invocabile senza abilitare il
live. Il launcher `operator_kit/d264-first-image-offline.sh` non ha modalità
hardware: senza argomenti seleziona `STOP_AFTER_FDT_ARM_ACK`, mentre
`--stop-after-first-image` è l'unico opt-in per `STOP_AFTER_FIRST_IMAGE`.
Valori ignoti o selezioni multiple falliscono prima dell'entrypoint.
L'entrypoint riusa il coordinatore pubblico e le fixture sintetiche D263; non
duplica protocollo, transport o lifecycle.

La rehearsal first-image attraversa realmente il coordinatore persistente con
policy fisica candidate `FIXED64_ZERO_TAIL`, un solo deadline IRQ2 host-side
assoluto/non rinnovabile da 15000 ms, esattamente un `0x22`, una validazione
ACK, un primo B0 sulla TLS trattenuta, decode canonico in memoria e cleanup
host. Il JSON conserva soltanto dimensioni e telemetria non biometrica. I test
coprono default e opt-in, selezione fail-closed, timeout/evento inatteso, ACK
errato, B0 malformato, CRC/decode failure, one-shot e cleanup parziale. Il
cleanup runtime è indipendente per TLS, secret e transport: un'eccezione non
impedisce le fasi successive e chiude il runtime come `FAILED_CLOSED`.

Il path non invia `0x34`, `0x20` post-image, un secondo `0x22`, re-arm, A2,
`0x70`, recovery, retry o write persistenti. La rehearsal attesta
`REAL_USB_OPEN_COUNT=0`, `REAL_TLS_HANDSHAKE_COUNT=0` e
`REAL_SENSOR_COMMAND_COUNT=0`. `POST_FIRST_IMAGE_HOST_CLEANUP_IMPLEMENTED` è
provato offline; `POST_FIRST_IMAGE_DEVICE_INTERNAL_STATE=UNKNOWN`; `0x22`
fixed64 e first image restano `NOT_LIVE_PROVEN`.
`FIRST_IMAGE_TERMINAL_RISK=ACCEPTABLY_BOUNDED`, non sicurezza assoluta.

Questa reachability è esclusivamente sintetica. Il real launcher D261 continua
a chiamare il coordinatore senza selezionare `STOP_AFTER_FIRST_IMAGE`, quindi
resta `STOP_AFTER_FDT_ARM_ACK`: USB reale è raggiungibile soltanto sotto i suoi
guard storici, ma il boundary first-image non lo è. Il manifest distingue ora
esplicitamente i file raggiunti dal launcher D264 offline da quelli inclusi
soltanto per una futura review live. Il riferimento remoto canonico della tree
eseguibile già reviewata è
`REMOTE_REVIEW_HEAD=a4b2eec79071b3b2682962be63c583bad0fae03b`; gli SHA locali
Codex `c0463b0…` e `7dfa7f8…` sono sola provenance dell'esecutore, non autorità
di baseline remota. Il corrective non modifica file eseguibili/live-critical.
Stato corrente:

```text
D264_02_EXECUTABLE_CLOSURE=PASS_OFFLINE
D264_02_READY_FOR_AI_PM_REVIEW=true
D264_02_READY_FOR_BASELINE_APPROVAL=false
FIRST_IMAGE_LIVE_OPERATOR_WIRING=NOT_IMPLEMENTED
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
BASELINE_APPROVED=false
```

### D264/03: wiring pre-live protetto first-image, OFFLINE ONLY

Il nuovo surface `operator_kit/d264-first-image-prelive.sh` →
`tools/d264_first_image_prelive.py` è cwd-independent e offre soltanto
`--dry-run`. Non espone una modalità live: qualsiasi altra combinazione viene
respinta dal launcher come `HARD_DISABLED_D264_03`, prima di controllo root
mutante, stop/start fprintd, lettura secret, marker, backend USB o comando.
Il dry-run valida schema e hash del live-critical set v3, sintassi launcher,
modello baseline full-SHA e soli metadata del marker futuro; ignora
intenzionalmente qualunque valore dell'environment di approvazione.

La prima versione reviewata dall'AI-PM al remote HEAD
`830c95c407ecbe0f9b185a8adbc968ae5c9cef0d` era uno skeleton parzialmente
production-shaped: non chiamava il baseline verifier dal candidate, celava i
guard in un unico callback, emetteva convenzionalmente la capability live-I/O
e poteva chiudere due volte il secret. Il corrective rende invece esplicita in
`core/future_first_image_operator.py` la sequenza: baseline full-SHA/path-set/
blob identity → contesto operatore → directory/report sicuri → metadata
protetti → hash gfusb → target/cardinalità → stop fprintd → signal block →
holder check → materiale/cache non-secret → singola materializzazione secret →
marker → capability live-I/O → backend/coordinator → run/restore/report. La
seconda review AI-PM al remote HEAD
`495cc2c6cd2467241cf67ec4e0e8e748726e9f8c` ha tuttavia individuato un
indebolimento strutturale: i validator pubblici iniettabili di secret,
materiale e backend avrebbero accettato anche una callback arbitraria sempre
vera; inoltre path-set atteso e osservato erano entrambi caller-controlled e il
manifest ometteva il modulo D261 direttamente importato. Il corrective 2
rimuove queste superfici prima di confermare la closure.

La control flow richiede l'intento
esatto `--i-authorize-one-future-d265-first-image-live-attempt`, consumabile una
sola volta, e usa il marker distinto
`/var/lib/goodix-5125-poc/d265-first-image-single-use.marker`, schema
`D265_FUTURE_FIRST_IMAGE_SINGLE_USE_MARKER_V1`. D264/03 non crea quel marker:
claim, capability live-I/O e backend sono esercitati soltanto con fixture e
doubles. Non è più un legame convenzionale: la catena tipata/nonce è
`FutureIntentCapability → FutureMarkerClaimCapability → FutureLiveIoCapability`,
con consumo one-shot e rigetto di tipo/nonce/namespace D261 errati.
`core/live_capability.py` è ora l'unica authority fissa per capability D261 e
future note: le API pubbliche non accettano più funzioni validator. La factory
marker future è una seam privata chiamata dal durable claim; non esiste un path
production supportato intent-consumato → marker-capability senza claim.
La terza review AI-PM al remote HEAD
`415c7357e6cdc7457ccd2f70d55805b6471818dd` ha precisato che anche gli helper
D261 intent/marker/live-I/O non potevano restare API pubbliche: avrebbero
permesso di saltare il durable marker pur conservando tipi e nonce validi. Il
micro-corrective 3 li rende privati e mantiene come unica superficie supportata
D261 quella storica in `core.protected_runtime`: exact main flag → intent →
writer marker `O_EXCL`/write-all/fsync → marker capability → live-I/O. Lo
stesso vincolo vale per il marker future, la cui capability nasce soltanto
dalla seam privata chiamata dopo fsync.
`FutureProductionDependencies` collega concretamente i guard D261-reviewed,
`RealSecretBoundary`, `CtypesLibusbBackend`, `ColdStartMachine`, seed FDT e
`PersistentRuntimeCoordinator`, ma non è raggiungibile dal CLI D264/03. La
factory concreta non riceve più transaction o publisher arbitrari: costruisce
`FprintdTransaction` e `SignalTransaction` e vincola il report futuro distinto
a `/var/lib/goodix-5125-poc/d261-results/d265-first-image-final.json`, la cui
assenza/sicurezza viene verificata prima degli effetti. Anche l'assenza del
marker D265-future viene verificata senza lettura o mutazione prima del secret;
il claim successivo conserva `O_EXCL`, `O_NOFOLLOW`, mode 0600 e fsync.
Il writer future gestisce ora anche short-write con un ciclo write-all e
fallisce senza capability quando `write()` non progredisce.

La transaction outer traccia separatamente report-destination preflight,
fprintd avviato e segnali bloccati. Un failure baseline, contesto operatore o
report preflight non pubblica e non consuma il report protetto; restore viene
tentato solo per transaction effettivamente iniziate. Dopo report preflight un
failure successivo può invece pubblicare il report fail-closed. La policy
operatore è condivisa con D261: `EUID=0`, `SUDO_UID` presente e numerico, e
`int(SUDO_UID) != 0`; quindi `SUDO_UID=0` è respinto.

L'outer possiede il secret fino alla costruzione riuscita del coordinator: un
failure marker/capability/costruzione causa un solo close outer. Dopo la
costruzione l'ownership passa al coordinator, il cui `run()` possiede cleanup
TLS/secret/transport; l'outer non richiama il secret close e conserva soltanto
restore segnali/fprintd/report. Successo, failure runtime e failure prima del
transfer provano `SECRET_DOUBLE_CLOSE_COUNT=0`.

La tuple interna `FUTURE_FIRST_IMAGE_LIVE_CRITICAL_PATHS` è l'autorità della
baseline futura e non è fornita dal caller. Il manifest
`analysis/D264/D264_03_live_critical_manifest.json` deriva esattamente 18 file
future-live dal call graph concreto, inclusi `core/live_capability.py` e
`tools/d261_live_fdt_arm_once.py`: helper protetti,
backend USB, cold-start/FDT, coordinator, transport/framing, retained TLS/B0,
codec immagine/CRC e dipendenze di validazione secret. Launcher/tool D264/03
formano invece un set offline-gate separato di due file e non sono marcati
future-live; shell D261, test e manuale sono esclusi con classificazione
esplicita. I due record offline hanno ora ruolo coerente di hard-disable
launcher/dry-run inspector e classificazione
`OFFLINE_GATE_ONLY_NOT_FUTURE_LIVE`. Nessuno SHA è approvato:
il modello rifiuta SHA corto, branch, `HEAD`, commit errato e blob worktree non
identico. Review AI-PM e successiva approvazione byte-level restano gate
separati.

La closure offline attraversa dall'orchestrator il vero
`PersistentRuntimeCoordinator.run()` con fixture D263: prefisso FDT storico,
un solo `0x22` `FIXED64_ZERO_TAIL`, TLS trattenuta, primo B0, raster 80×64,
zero persistenza/retry/comandi vietati e cleanup host. La failure matrix v4
associa ogni PASS a test/artifact e distingue prova D264/03 diretta, regressione
D264/02/D263 ereditata e deadline su runtime byte-identico. La suite D263,
D264/02 e D260 pertinente resta verde; la suite D261 non è eseguibile in questo
ambiente perché la dipendenza preesistente `cryptography` manca, senza essere
installata. Nessun test hardware è stato eseguito. Stato canonico:

```text
D264_03_EXECUTABLE_CLOSURE=PASS_OFFLINE
D261_SUPPORTED_CAPABILITY_CHAIN_PRESERVED=true
D261_PUBLIC_INTENT_MINT_BYPASS_ABSENT=true
D261_PUBLIC_MARKER_MINT_BYPASS_ABSENT=true
FUTURE_PUBLIC_MARKER_MINT_BYPASS_ABSENT=true
DURABLE_MARKER_REQUIRED_BEFORE_CAPABILITY=true
BASELINE_FAILURE_REPORT_WRITE_COUNT=0
REPORT_PUBLICATION_REQUIRES_PREFLIGHT=true
FUTURE_OPERATOR_CONTEXT_MATCHES_D261=true
FUTURE_MARKER_SHORT_WRITE_SAFE=true
PUBLIC_AUTHORIZATION_VALIDATOR_BYPASS_ABSENT=true
PUBLIC_LIVE_IO_VALIDATOR_BYPASS_ABSENT=true
CANONICAL_FUTURE_LIVE_CRITICAL_PATHS_INTERNAL=true
CALLER_CONTROLLED_EXPECTED_PATH_SET_REMOVED=true
FUTURE_LIVE_CRITICAL_MANIFEST_EXACT_MATCH=true
D261_OPERATOR_DEPENDENCY_INCLUDED=true
FUTURE_REPORT_DESTINATION_BOUND=true
FUTURE_MARKER_PREFLIGHT_BEFORE_SECRET=true
PROTECTED_GUARD_ORDER_PROVEN=true
BASELINE_BYTE_IDENTITY_GATE_PROVEN=true
MARKER_TO_LIVE_IO_CAPABILITY_CHAIN_PROVEN=true
SECRET_CLEANUP_OWNERSHIP=TRANSFER_TO_COORDINATOR_AFTER_CONSTRUCTION
SECRET_DOUBLE_CLOSE_COUNT=0
REAL_COORDINATOR_FIRST_IMAGE_INTEGRATION_PROVEN=true
LIVE_CRITICAL_REACHABILITY_PROVEN=true
FAILURE_MATRIX_ALL_REQUIRED_CASES_PROVEN=true
FIRST_IMAGE_PRELIVE_OPERATOR_WIRING=IMPLEMENTED_OFFLINE
CURRENT_D261_REAL_BOUNDARY=STOP_AFTER_FDT_ARM_ACK
FUTURE_FIRST_IMAGE_REAL_BOUNDARY=STOP_AFTER_FIRST_IMAGE
DEDICATED_FUTURE_MARKER_NAMESPACE=D265_FUTURE_FIRST_IMAGE_SINGLE_USE_MARKER_V1
D261_MARKER_REUSED=false
D264_03_REAL_USB_OPEN_COUNT=0
D264_03_REAL_SECRET_READ_COUNT=0
D264_03_REAL_SENSOR_COMMAND_COUNT=0
D264_03_REAL_SINGLE_USE_MARKER_CREATE_COUNT=0
D264_03_FPRINTD_MUTATION_COUNT=0
D264_03_LIVE_TLS_HANDSHAKE_COUNT=0
POST_FIRST_IMAGE_HOST_CLEANUP_IMPLEMENTED_OFFLINE=true
POST_FIRST_IMAGE_DEVICE_INTERNAL_STATE=UNKNOWN
POST_FIRST_IMAGE_DEVICE_STOP_LIVE_PROVEN=false
0x22_TARGET_EVIDENCE=PRIMARY_TARGET_CAPTURE_OBSERVED_ONLY
0x22_OPERATIONAL_CANDIDATE=EVIDENCE_SUPPORTED_DETERMINISTIC_CANDIDATE
0x22_TARGET_LIVE_ACCEPTANCE=NOT_LIVE_PROVEN
D264_03_READY_FOR_AI_PM_REVIEW=true
D264_03_READY_FOR_BASELINE_APPROVAL=false
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
BASELINE_APPROVED=false
```

Il prossimo gate è la review AI-PM del remote branch e del set byte-level. Solo
uno step successivo e separatamente autorizzato potrà approvare una baseline e
valutare se abilitare il collegamento reale; fino ad allora il rischio residuo
rimane l'accettazione target non provata di `0x22` fixed64 e del primo B0,
insieme allo stato interno device post-image ignoto.

### D265/01: kit operatore one-shot first-image, OFFLINE ONLY

Il corrective AI-PM mantiene lo stesso milestone e chiude offline quattro
classi di difetto. Il launcher cwd-independent accetta solo `--dry-run` e
`--i-authorize-one-d265-first-image-live-attempt`; ogni messaggio human-facing,
inclusi gli errori, è italiano. La forma futura canonica è:

```text
sudo env D265_APPROVED_LIVE_BASELINE_SHA=<FULL_APPROVED_SHA> \
  ./operator_kit/d265-first-image-once.sh \
  --i-authorize-one-d265-first-image-live-attempt
```

`sudo` conserva la gestione interattiva della password e genera `SUDO_UID`;
`env` passa al processo root soltanto la baseline esplicita. Il kit non legge
password, non usa `sudo -S` e non inventa alcuno SHA approvato. Il dry-run mostra
questo template e continua a non consumare l'environment né raggiungere secret,
marker, servizi o USB.

Il prompt dito non precede più il runtime. Un decorator D265 dell'event source
lascia invariati gli eventi preliminari e, una sola volta quando riceve la
richiesta esatta `FIRST_IMAGE_IRQ2_TIMEOUT_MS=15000`, stampa le istruzioni
italiane e `D265_OPERATOR_ACTION = APPOGGIA_UN_DITO_ORA`, quindi delega al vero
`wait_event(15000)`. Ciò avviene dopo il final `0x32`/ACK. Il `finally` chiude la
finestra con `D265_OPERATOR_ACTION_WINDOW = CHIUSA`; sessione, transport,
coordinator, timeout e command path restano identici.

La telemetria è truth-preserving. Un tracker incrementa materializzazione
secret, claim marker, capability live-I/O e costruzione coordinator soltanto
dopo il successo della fase. Il riferimento al coordinator permette di leggere
`audit()` anche dopo failure senza nuovo I/O. `USB_OPEN_COUNT` viene dal backend
concreto; sessioni/TLS/retry/persistenza/zeroization/cleanup derivano dalle
chiavi audit reali. Tre contatori monotoni host-only nel runtime registrano IRQ2
valido, ACK `0x22` valido e primo B0 riconosciuto nei punti già esistenti, senza
nuovi branch, comandi, timeout, retry o cleanup. Valori non osservabili sono
`UNKNOWN`/`NOT_REACHED`, mai zero/uno/true inventati. `LIVE_RESULT` conserva
l'esatto risultato runtime.

L'autorità live-critical D265/01 resta di 20 file e include il runtime telemetry-only;
`baseline_approved=false`. Il manifest D264/03 è invece uno snapshot storico
congelato, byte-identico alla baseline D264/03: non riceve hash D265 e non entra
nel bundle step-local D265/01. Test synthetic provano ordine arm→prompt→IRQ2,
progressi parziali timeout/ACK/B0/successo, audit su failure, command trace
immutata e zero retry/persistenza/comandi post-image vietati. Nessun live è
stato eseguito. D261 resta `STOP_AFTER_FDT_ARM_ACK`; D265 resta futuro
`STOP_AFTER_FIRST_IMAGE`; `0x22_FIXED64_LIVE_PROVEN=false`,
`FIRST_IMAGE_LIVE_PROVEN=false`, stato interno post-image `UNKNOWN` e stop
post-image non live-proven. La precedente autorizzazione non è consumata né
trasferita. Servono ancora PASS AI-PM, merge, approvazione esplicita del nuovo
full SHA e nuova autorizzazione separata. Stato: `READY_FOR_LIVE=false`,
`LIVE_AUTHORIZED=false`, `BASELINE_APPROVED=false` e
`D265_01_READY_FOR_BASELINE_APPROVAL=false`.

### D265/02: live fail-closed e difetto deterministico del router IRQ2

Il live one-shot D265/02 è stato eseguito una sola volta sulla baseline full-SHA
approvata `2e57aa95cbe7d5eb468c12882cfa3a1a4d457e6d`. Dopo il prompt
`D265_OPERATOR_ACTION = APPOGGIA_UN_DITO_ORA`, l'operatore riferisce di aver
appoggiato il dito; nessun output immediato è stato osservato e dopo alcuni
secondi la run ha chiuso fail-closed. Questa è un'osservazione soggettiva e non
viene trasformata in una misura temporale.

La telemetria terminale sanitizzata registra:

```text
OUTCOME=FAIL_CLOSED
LIVE_ATTEMPT_INVOCATION_COUNT=1
USB_OPEN_COUNT=1
TRANSPORT_SESSION_COUNT=1
TLS_OBJECT_COUNT=1
TLS_HANDSHAKE_COUNT=1
SECRET_MATERIALIZATION_COUNT=1
FINAL_FDT_ARM_COUNT=1
IRQ2_FINGER_DOWN_COUNT=0
COMMAND_22_ATTEMPT_COUNT=0
COMMAND_22_ACK_VALIDATION_COUNT=0
FIRST_B0_COUNT=0
RETRY_COUNT=0
RECOVERY_COUNT=0
REOPEN_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
FORBIDDEN_POST_IMAGE_COMMAND_COUNT=0
FAILURE_CLASS=TimeoutError:libusb_bulk_timeout:0x81
HOST_CLEANUP_STATUS=COMPLETED
SECRET_ZEROIZED=true
```

Il report protetto già prodotto dalla run, letto dall'operatore senza nuovo
traffico USB, conferma `result=FAIL_CLOSED`, la stessa failure class,
`retry_count=0`, `report_destination_preflight_passed=true` e
`secret_ownership_transferred_to_coordinator=true`. Poiché non espone lo stato
fprintd, `FPRINTD_RESTORE_STATUS` resta non direttamente provato da tale JSON e
va consultato nel rapporto operatore; non viene promosso a PASS.

L'audit dei blob eseguiti dimostra che `core/usb_runtime.py` ha SHA-256
`a19c0ffb93a7e1dc7d4b08a0fed9ed738a9d51bb72e4327d16a41b4cb15dc278` e
che `_is_irq100()` restituisce true soltanto per A0 `0x36` il cui data prefix è
`00 01`. `_pop(event=True)` consegna esclusivamente quei frame. Il coordinator
in `core/persistent_runtime.py`, SHA-256
`42efbc29d2cebc06d3a83fd37cb410d9412dd6d20f0ffc7e3348338a70d79641`,
chiama invece `wait_event(15000)` e procede a `0x22` soltanto dopo aver parsato
`event.irq == 2`. Il decorator D265, nel tool con SHA-256
`f5501cf1d90bb5b2b873c7a22f8d41b4db23c6b96bffd2ce1243b71665dab1e4`,
stampa correttamente il prompt e delega senza alterare la classificazione.

Una riproduzione sintetica offline sul `SharedFrameRouter` concreto conferma:
`_is_irq100(IRQ2)=false`; `receive_event()` continua fino a
`TimeoutError:libusb_bulk_timeout:0x81`; il frame IRQ2 resta accodato e viene
poi consegnato da `receive_command()`. Questa prova è code-level e non dimostra
che il device abbia realmente emesso IRQ2 durante il live. La classificazione
corretta è pertanto:

```text
D265_02_ROUTER_IRQ2_DELIVERY_DEFECT=PROVEN_FROM_EXECUTED_BASELINE
DEVICE_IRQ2_PHYSICAL_EMISSION_DURING_D265_02=UNDETERMINED
D265_02_FIRST_IMAGE_PATH_WAS_SOFTWARE_BLOCKED_BEFORE_0x22=true
0x22_FIXED64_LIVE_PROVEN=false
FIRST_IMAGE_LIVE_PROVEN=false
POST_D265_02_DEVICE_INTERNAL_STATE=UNKNOWN
```

Il gap di test è una mancata integrazione fra first-image e router concreto:
gli event source sintetici D263/D264 e il decorator D265 bypassano il demux;
gli harness D261 del router coprono IRQ `0x0100`, non un logical A0/FDT IRQ2
attraverso `receive_event()`. La prompt timing logic resta corretta; la real
router event classification è incompleta per IRQ2.

D265/02 non modifica codice live-critical e non applica il fix. L'unica
autorizzazione è consumata, `D265_02_RETRY_AUTHORIZED=false`,
`READY_FOR_LIVE=false`, `LIVE_AUTHORIZED=false` e
`BASELINE_APPROVED_FOR_NEW_ATTEMPT=false`. Un eventuale passo futuro deve prima
correggere offline la classe di routing, aggiungere test concreti end-to-end e
attraversare review, merge, nuova approvazione full-SHA e autorizzazione live
separata. Gli artefatti sanitizzati sono in `analysis/D265/`; nessun raw USB,
secret, plaintext TLS, marker, cache protetta o dato biometrico è incluso.

### D266/01: correzione offline del router eventi FDT

D266/01 parte dal branch `codex` a
`c68398db24c7a1689e3056b771df83b479a1c7ef` e non esegue hardware. Il fix
rinomina il predicato in `_is_fdt_event()` e delega la validazione semantica al
parser FDT già canonico. Il contratto risultante è evidence-bounded: outer A0,
payload strutturalmente valido, control nella famiglia `0x3x` e IRQ nella
allowlist target osservata delle coppie `0x32/IRQ2`, `0x34/IRQ200` e
`0x36/IRQ100`; non equivale a «ogni A0 è evento». ACK/response e frame non
riconosciuti restano command-side.

Otto test D266 sul router concreto verificano IRQ100 e IRQ2 exactly-once,
non-stealing di ACK/response, quattro interleaving, code finali vuote, deadline
monotonic assoluta e `concurrent_physical_in_reader_forbidden`. Il seam
first-image usa una fixture bulk-IN sintetica e passa da
`SharedFrameRouter` a `_RouterEventSource` e al runtime: con IRQ2 produce un
solo submit logico `0x22 [01 00]` e completa una immagine sintetica `80x64`;
senza IRQ2 termina in timeout con zero submit. La suite mirata router/runtime/
first-image passa 37/37. La suite generale `unittest` esegue 282 test e
mantiene un failure e tre errori non attribuibili al router: i due esiti D261
storici (capability exception class e dry-run drift) e due import di test
pytest-only con `pytest` non installato. Nessuna dipendenza è stata aggiunta.

```text
OUTCOME=D266_01_READY_FOR_AI_PM_REVIEW
ADVANCEMENT=CONCRETE_ROUTER_EVENT_CLASSIFICATION_FIXED_OFFLINE
EXECUTABLE_CLOSURE=PASS
DEVICE_IRQ2_PHYSICAL_EMISSION_DURING_D265_02=UNDETERMINED
D265_02_RETRY_AUTHORIZED=false
0x22_FIXED64_LIVE_PROVEN=false
FIRST_IMAGE_LIVE_PROVEN=false
READY_FOR_LIVE=false
LIVE_AUTHORIZED=false
BASELINE_APPROVED_FOR_NEW_ATTEMPT=false
```

La review AI-PM successiva è conclusa con:

```text
D266_01_AI_PM_REVIEW=PASS
D266_01_ROUTER_FIX_ACCEPTED=true
D266_01_CORRECTIVE_REQUIRED=false
```

### D266/02: execution-readiness post-review fail-closed

D266/02 parte e resta sul branch `codex` al commit
`7a2ceff54f2fc27332a9f2a531ce4af5d90cf9a2`, con `origin/main` invariato a
`c68398db24c7a1689e3056b771df83b479a1c7ef`. L'integrità del bundle D266/01 è
PASS: vero ZIP, sidecar coerente, archive test e hash membri validi, path-set
esatto e contenuto sanitizzato. I test del router passano 8/8 e la suite mirata
passa 37/37. La regressione generale riproduce senza differenze D266/01: 282
test, 278 PASS, un FAIL e tre ERROR preesistenti/ambientali; `pytest` non è
installato e i due moduli pytest-only D264/D265 risultano invariati dal delta
D266.

Il dry-run ufficiale `operator_kit/d265-first-image-once.sh --dry-run`, eseguito
da `/tmp`, restituisce invece `FAIL_CLOSED` con
`byte_identity:core/usb_runtime.py`. Il manifest D265/01 è correttamente uno
snapshot storico del candidate pre-fix e conserva SHA-256 `a19c0ffb…`; il
router accettato D266/01 ha SHA-256 `c4e62b07…`. Tutti i contatori reali del
dry-run restano zero, ma il gate impedisce la executable closure sulla nuova
base. D266/02 non retro-modifica il manifest storico e non cambia alcun file
live-critical.

```text
OUTCOME=D266_02_CORRECTIVE_REQUIRED
ADVANCEMENT=POST_ROUTER_FIX_OPERATOR_GATE_DEFECT_LOCALIZED_OFFLINE
EXECUTABLE_CLOSURE=FAIL
D266_01_AI_PM_REVIEW=PASS
D266_01_ROUTER_FIX_ACCEPTED=true
D266_02_LIVE_CRITICAL_CODE_CHANGE_COUNT=0
D265_OPERATOR_DRY_RUN=FAIL_CLOSED_BYTE_IDENTITY_CORE_USB_RUNTIME
DEVICE_IRQ2_PHYSICAL_EMISSION_DURING_D265_02=UNDETERMINED
0x22_FIXED64_LIVE_PROVEN=false
FIRST_IMAGE_LIVE_PROVEN=false
READY_FOR_NEW_BASELINE_APPROVAL_REVIEW=false
BASELINE_APPROVED_FOR_NEW_ATTEMPT=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

### D266/03: nuova authority post-router e namespace D267, OFFLINE ONLY

D266/03 parte dal branch `codex` al commit
`65b8ec198603c347b89107fe5b7b28cf84fbd318`, con parent
`7a2ceff54f2fc27332a9f2a531ce4af5d90cf9a2`, `origin/codex` coincidente,
`origin/main` invariato a `c68398db24c7a1689e3056b771df83b479a1c7ef` e
worktree iniziale pulito. Il bundle D266/02 è verificato al digest
`207dea0f24ee163fb9f7a7f3be1ec1aecfbc6f1b6bc442dbcdd353b077c1dfd1`.
D266/02 è accettato come audit fail-closed e il corrective non modifica
`analysis/D265/D265_01_live_critical_manifest.json`,
`operator_kit/d265-first-image-once.sh` o
`tools/d265_live_first_image_once.py`.

Il nuovo surface D267 espone soltanto `--dry-run` e
`--i-authorize-one-d267-first-image-live-attempt`. Il live, non eseguito,
richiederebbe `D267_APPROVED_LIVE_BASELINE_SHA`; marker e report canonici sono
rispettivamente
`/var/lib/goodix-5125-poc/d267-first-image-single-use.marker` e
`/var/lib/goodix-5125-poc/d261-results/d267-first-image-final.json`. Le
capability D267 usano tipi e nonce propri, incompatibili con D261/D265, e il
live-I/O non può nascere prima del durable claim fsyncato. La nuova authority
di 20 file è esatta e include il router accettato D266 al digest
`c4e62b0786d7710eb0625b033258636597b9aa8f40259ce5a1f669b0e160385b`;
il manifest dichiara correttamente `baseline_approved=false`.

Il dry-run eseguito dalla cwd esterna `/tmp` passa con tutti i contatori reali
a zero. I nuovi test D266/03 passano 21/21; router 8/8 e suite mirata 37/37
passano. La discovery completa esegue 303 test: 299 PASS, un FAIL D261 per il
drift storico del dry-run e tre ERROR (classe eccezione D261 più due moduli
pytest-only con pytest assente), esattamente le classi già documentate; zero
nuovi failure sono attribuibili a D266/03. Nessun pytest è installato. Nessun
USB reale, secret reale, TLS live, marker reale, fprintd o comando device è
stato raggiunto.

```text
OUTCOME=D266_03_READY_FOR_AI_PM_BASELINE_REVIEW
ADVANCEMENT=POST_ROUTER_NEW_ONE_SHOT_AUTHORITY_CLOSED_OFFLINE
EXECUTABLE_CLOSURE=PASS
D266_01_ROUTER_FIX_ACCEPTED=true
D266_02_AI_PM_REVIEW=PASS_AS_FAIL_CLOSED_AUDIT
D266_02_CORRECTIVE_REQUIRED=true
D266_02_FAILURE_IS_EXPECTED_STALE_D265_AUTHORITY=true
D265_HISTORICAL_AUTHORITY_IMMUTABLE=true
D265_02_RETRY_AUTHORIZED=false
D267_OPERATOR_CANDIDATE_READY_OFFLINE=true
READY_FOR_NEW_BASELINE_APPROVAL_REVIEW=true
BASELINE_APPROVED_FOR_NEW_ATTEMPT=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
DEVICE_IRQ2_PHYSICAL_EMISSION_DURING_D265_02=UNDETERMINED
0x22_FIXED64_LIVE_PROVEN=false
FIRST_IMAGE_LIVE_PROVEN=false
```

### D267/01–03: first B0 live, localizzazione bounded e corrective osservabilità

D267/01 è stato eseguito manualmente una sola volta sulla baseline approvata
`219c038600deb87da1cd93340b9bd07c14e1f5fe`. L'output sanitizzato fornito
dall'operatore registra una sessione USB/transport, un oggetto e handshake TLS,
un solo secret materializzato e un arm finale. Dopo il prompt dito, IRQ2 è
stato consegnato al runtime; un solo `0x22` fixed64 è stato inviato, il relativo
ACK è stato validato e il primo B0 è stato ricevuto. Il boundary precedente è
quindi avanzato realmente fino al decoder:

```text
D267_BASELINE_APPROVED=true
D267_APPROVED_BASELINE_SHA=219c038600deb87da1cd93340b9bd07c14e1f5fe
D267_01_LIVE_AUTHORIZATION_CONSUMED=true
D267_01_LIVE_ATTEMPT_COUNT=1
D267_01_SECOND_LIVE_ATTEMPT_AUTHORIZED=false
D267_01_LIVE_RESULT=FAIL_CLOSED
D267_01_FAILURE_CLASS=RuntimeFailure:first_image_decode_failed
IRQ2_HOST_DELIVERY_LIVE_PROVEN=true
0x22_FIXED64_LIVE_SENT=true
0x22_FIXED64_ACK_LIVE_PROVEN=true
FIRST_B0_LIVE_RECEIVED=true
FIRST_IMAGE_DECODE_LIVE_PROVEN=false
FIRST_IMAGE_LIVE_PROVEN=false
RETRY_COUNT=0
RECOVERY_COUNT=0
REOPEN_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
FORBIDDEN_POST_IMAGE_COMMAND_COUNT=0
HOST_CLEANUP_STATUS=COMPLETED
SECRET_ZEROIZED=true
FPRINTD_RESTORE_STATUS=UNVERIFIED_FROM_AVAILABLE_SANITIZED_EVIDENCE
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

Il report protetto
`/var/lib/goodix-5125-poc/d261-results/d267-first-image-final.json` non è
leggibile dall'utente corrente (`PROTECTED_D267_REPORT_READ_STATUS=
UNAVAILABLE_WITH_CURRENT_PERMISSIONS`); D267/02 non usa privilegi, non cambia
permessi e non copia il raw.

La call-chain production termina in
`PersistentRuntimeCoordinator._run_first_image_terminal()`. Dopo outer B0 e
consumo TLS, il plaintext viene passato a `parse_image_payload()`. Una failure
nel consumo/auth TLS avrebbe la classe distinta
`first_image_b0_consumption_failed`; l'esito osservato prova per call-flow che
il TLS consumer ha invece restituito plaintext non vuoto. Il successivo
`except Exception` azzera il buffer e sostituisce qualunque dettaglio con
`first_image_decode_failed`.

Il formato accettato offline è esatto: plaintext 7693 byte, `v19=7690`, data
7689 byte, cmd0=2, prefix immagine 5 byte non-POV, record 7684 byte composto da
7680 packed12 più trailer CRC-32/MPEG-2, output 5120 sample `80x64`. I test
router passano 8/8 e decoder/first-image/cleanroom 30/30; il dry-run operatore
da `/tmp` passa con tutti i side effect reali a zero. Un probe sintetico
conferma che la fixture 7693 passa, mentre trailer forzato `0x88`, record raw,
B0 intero e payload troncato falliscono nei gate attesi. `pytest` non è
installato e non è stato aggiunto.

Questo `7693 → 7690 → 7689 → 5+7684 → 7680+4 → 80x64` è verificato dal
contratto sintetico e dal codec corrente. Gli artefatti storici D209/D210 non
sono più presenti nel repository e non sono quindi re-queryable come evidenza
primaria: qualunque richiamo storico a `7693 byte / major image 2` sopravvive
solo alla forza probatoria del manuale canonico e degli artefatti D267 ancora
presenti, non come nuova verifica dei raw D209/D210.

La causa interna della run consumata non è ricostruibile perché non furono
registrati exception class, stage, lunghezze, control, categoria trailer,
checksum o CRC sanitizzati. Le ipotesi restano ordinate: mismatch strict
checksum/no-check `0x88` (`MEDIUM`), framing/header/lunghezza (`MEDIUM-LOW`),
CRC record (`MEDIUM-LOW`), control/POV (`LOW`) e concatenazione di più payload
TLS (`LOW`). DLL locale e Rocky ammettono `0x88`; il parser Python no. Questa
divergenza giustifica test e osservabilità offline, non prova che il trailer
live fosse `0x88`.

```text
OUTCOME=D267_02_DECODE_FAILURE_BOUNDED_BUT_NOT_LOCALIZED
ADVANCEMENT=LIVE_IRQ2_0x22_B0_BOUNDARY_PROVEN_DECODE_FAILURE_BOUNDED_OFFLINE
EXECUTABLE_CLOSURE=PASS_FOR_POST_LIVE_ANALYSIS
RESIDUAL_BLOCKER_OR_RISK=MISSING_SANITIZED_INNER_DECODER_STAGE_AND_LENGTH_CHECKSUM_CRC_METADATA_FROM_CONSUMED_RUN
READY_FOR_DECODE_CORRECTIVE_REVIEW=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

Il solo passo successivo proposto è un corrective **offline** separato:
conservare diagnostica tipizzata e sanitizzata per stage e aggiungere fixture
image-specific per `0x88`, lunghezze/header, POV e CRC. D267/02 non modifica
`core/`, `tools/`, `operator_kit/`, `src/` o `poc/` e non autorizza un live.

D267/03 esegue quel corrective senza cambiare i predicati; D267/04 estende poi
il medesimo record `first_image_decode_diagnostic`, che nello stato corrente
contiene esclusivamente:

```text
decode_stage
plaintext_length
declared_payload_length
control_or_major_class
is_pov_notification
payload_trailer_class
payload_checksum_match
payload_checksum_policy
image_record_length
image_record_crc_match
exception_class
raster_shape_if_success
```

I campi non raggiunti restano `null`. Il runtime continua a emettere la classe
esterna canonica `RuntimeFailure:first_image_decode_failed`, azzera il plaintext
anche sul failure e conserva il solo record sanitizzato nell'audit. Il report
protetto di una futura esecuzione e il summary operatore potranno pertanto
distinguere il predicato senza conservare B0, plaintext, bytes immagine, raster,
pixel, materiale biometrico o hash sensibili.

La matrice sintetica 9/9 prova classi distinte per valid, truncated,
declared-length, major/control, POV, checksum ordinario, `0x88`, record length e
record CRC. Il caso `0x88` termina ancora in
`ChecksumMismatch:payload_checksum`; DLL locale
`function_18005f098_non_b0_dispatch` e
`Rockytkg/src/goodix_capture.c` corroborano una diversa policy no-check, ma non
provano quale trailer abbia prodotto APP12509 in D267/01. La graduatoria delle
ipotesi resta quindi invariata: `0x88` `MEDIUM`, framing/header/lunghezza e CRC
`MEDIUM-LOW`, control/POV e concatenazione TLS `LOW`. Il nuovo codice rende
queste ipotesi discriminabili soltanto da nuova evidenza; non ricostruisce la
run consumata.

Le invarianti offline confermano stessa allowlist, ACK policy, command trace,
un solo `0x22`, retained TLS/first-B0 ownership, zero retry/recovery/reopen e
zero reachability di write persistenti o comandi post-image vietati. Il dry-run
reale da `/tmp` usa il manifest D267/03 non approvato e ha tutti i contatori
sensor-reaching a zero. Il manifest D266/03 resta immutato come snapshot
storico.

```text
OUTCOME=D267_03_DECODE_DIAGNOSTIC_CORRECTIVE_READY_OFFLINE
ADVANCEMENT=NEW_OFFLINE_DIAGNOSTIC_CAPABILITY
EXECUTABLE_CLOSURE=PASS
OBSERVABILITY_CHANGE=YES
DECODER_SEMANTIC_CHANGE=NO
WIRE_CHANGE=NO
0X88_DIAGNOSTICALLY_RECOGNIZED=true
0X88_BYPASS_ENABLED=false
RESIDUAL_BLOCKER_OR_RISK=EXACT_D267_01_INNER_FAILURE_PREDICATE_STILL_UNOBSERVED_WITHOUT_NEW_EVIDENCE
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

D267/04 chiude il successivo audit semantico **solo offline**. Nel materiale
OEM locale il call-flow osservato è:

```text
USB parser 0x18005ef1a (major B0)
  -> TLS input 0x18003f0a8
  -> application-data callback 0x1800211c8
  -> plaintext buffer/length 0x180058128
  -> parser 0x18005f098 at call 0x1800213fd
  -> declared length bytes [1:3], payload copy from byte 3
  -> trailer compare 0x18005f4f9
     0x88: success flag at 0x18005f51f
     other: additive verifier 0x180059390
  -> major dispatch from control high nibble
  -> major 2 branch 0x18005f76e
  -> consumer callback with data+5 and declared_length-6
```

È quindi `OSSERVATO` che il buffer controllato è plaintext applicativo
post-TLS e che la lunghezza dichiarata proviene dai byte 1–2; è `VERIFICATO`
staticamente che `0x88` evita la chiamata al verificatore additivo e porta allo
stesso success path; è `VERIFICATO` che il medesimo buffer viene classificato
per major e che `major == 2` passa al consumer il sottointervallo image
`data+5`, lungo `declared_length-6` (7684 per il contratto 7693 corrente).
L'identità simbolica del callback OEM rimane `NON_NOTO`, ma data-flow,
dimensione e dispatch rendono l'applicabilità al payload immagine diretta e
non dipendente da Rocky. Lo snapshot Rockytkg, commit preservato
`227eba219fa9e3fbac5bd59aca79f624f67cd11b`, corrobora indipendentemente in
`src/goodix_capture.c:223-268` cmd0 2, prefix 5, `v19-6`, marker no-check
`0x88` e record 7684; il suo rilassamento CRC non è stato importato.

Il corrective minimo conserva `parse_payload()` strict e applica il no-check
soltanto in `parse_image_payload()`, dopo struttura/lunghezza dichiarata,
major image, record length 7684 e rifiuto POV. Trailer ordinari richiedono
ancora l'additive match; il CRC-32/MPEG-2 viene sempre eseguito. La matrice
D267/04 copre i dieci casi richiesti e prova anche identità completa del raster
80×64 fra fixture 7693 ordinaria e variante `0x88`. Le regressioni decoder,
D263, D266 e runtime passano; il dry-run reale da `/tmp` passa con baseline
non approvata e zero side effect. D209/D210 restano assenti e non re-queryable.

La causa D267/01 non viene promossa: `TARGET_D267_01_TRAILER=UNKNOWN` e il
sotto-predicato che fallì resta non osservato. La graduatoria non deve più
trattare il significato image-specific di `0x88` come incerto; resta invece
aperta l'ipotesi che D267/01 avesse effettivamente quel marker, insieme agli
altri predicati non registrati. Qualunque futuro live resta un gate separato e
potrà essere eseguito soltanto tramite Kit Operatore dedicato con interazione
in italiano, nuova baseline e autorizzazione esplicita.

```text
OUTCOME=D267_04_IMAGE_NO_CHECK_SEMANTIC_CORRECTIVE_READY_OFFLINE
ADVANCEMENT=NEW_LOCAL_OEM_SEMANTIC_EVIDENCE_AND_BOUNDED_DECODER_CORRECTIVE
EXECUTABLE_CLOSURE=PASS
SEMANTIC_CORRECTIVE_GATE=PASS
OEM_0X88_SEMANTICS=VERIFIED_NO_CHECK_ADDITIVE
OEM_IMAGE_PATH_APPLICABILITY=VERIFIED_REACHABLE_MAJOR_2_DATA_PLUS_5_LENGTH_MINUS_6
ROCKYTKG_CORROBORATION=YES_NOT_PRIMARY
TARGET_D267_01_TRAILER=UNKNOWN
DECODER_SEMANTIC_CHANGE=YES
DECODER_SEMANTIC_CHANGE_SCOPE=IMAGE_ADDITIVE_CHECKSUM_0X88_ONLY
IMAGE_RECORD_CRC_POLICY_CHANGE=NO
WIRE_CHANGE=NO
USB_PATH_CHANGE=NO
TLS_PATH_CHANGE=NO
FDT_IRQ_ROUTING_CHANGE=NO
COMMAND_22_CHANGE=NO
ACK_POLICY_CHANGE=NO
B0_OWNERSHIP_CHANGE=NO
RETRY_RECOVERY_CHANGE=NO
PERSISTENT_WRITE_REACHABILITY_CHANGE=NO
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

### D268/01: Kit Operatore first-image con decoder D267/04

D268/01 è interamente **OFFLINE ONLY**. Parte da `development` al commit
`999976978b5fb2da21cbf16ef79d942a90c4581b`, con worktree iniziale pulito.
Non ha eseguito USB, secret reale, TLS live, comandi device, marker o mutazioni
fprintd e non ha autorizzato una nuova run.

La repository hygiene è stata corretta ripristinando soltanto
`analysis/D267/D267_03_live_critical_manifest.json` ai byte del commit
`42af60107cf21eb610de867a6de05b774ec1e37f`. In D267/04 quel file storico era
stato aggiornato retroattivamente con l'hash corrente di `core/post_d4.py`;
ora l'identità dello snapshot D267/03 è nuovamente verificabile e il current
live-critical set vive soltanto in
`analysis/D268/D268_01_live_critical_manifest.json`.

Il nuovo path
`operator_kit/d268-first-image-once.sh` →
`tools/d268_live_first_image_once.py` →
`core/d268_first_image_operator.py` conserva la call graph produttiva
`cold start → TLS → D4 → AF → fresh FDT → IRQ2 → un 0x22 → ACK → primo B0 →
TLS retained → parse_image_payload() → stop/cleanup`. Flag, baseline
environment, capability/nonce, marker single-use e report sono D268 e
incompatibili con D267. Il verifier richiede full SHA lowercase a 40 caratteri,
HEAD uguale, worktree pulito, path-set esatto e identità byte commit/worktree;
nessuna SHA è auto-approvata.

Il summary operatore espone separatamente status/stage/classe eccezione,
classe trailer, policy ed esito checksum, CRC record e shape raster. Le classi
`ADDITIVE_VERIFIED`, `NO_CHECK_0X88_ACCEPTED`, mismatch checksum,
control/major, POV, lunghezza record, CRC immagine e decode riuscito restano
distinguibili senza persistere payload sensibili. La semantica decoder resta
quella accettata in D267/04: `0x88` evita soltanto il controllo additivo nel
parser image-specific dopo i gate strutturali; il parser generico e il CRC del
record restano strict/fail-closed.

Il launcher `--dry-run`, eseguito sia dalla Git root sia da `/tmp`, passa con
`REAL_USB_ACCESS_COUNT`, `REAL_SECRET_READ_COUNT`,
`REAL_DEVICE_COMMAND_COUNT`, `MARKER_MUTATION_COUNT`,
`FPRINTD_MUTATION_COUNT`, `PERSISTENT_DEVICE_WRITE_COUNT` e
`LIVE_TLS_HANDSHAKE_COUNT` tutti a zero. Il flag live senza SHA approvata si
ferma prima di costruire dipendenze produttive e riporta in italiano il gate
mancante. Le regressioni mirate D263/D266/D267 e D268 passano 94/94; non è
stata prodotta nuova evidenza device-side.

#### Riesame metodologico pre-live

1. **Cosa cambia realmente rispetto a D267/01?** Il decoder applica la
   semantica OEM locale verificata del marker image-specific `0x88`; il
   runtime conserva diagnostica tipizzata/sanitizzata del predicato interno;
   il futuro tentativo usa nuova authority e Kit D268.
2. **Quale nuova ipotesi viene testata?** Una futura run dovrà distinguere se
   D267/01 fallì per la policy additiva `0x88` oppure per framing/lunghezza,
   control/POV, CRC o un'altra failure tipizzata, senza assumere che il trailer
   storico fosse `0x88`.
3. **Se fallisce di nuovo allo stesso boundary?** La classe diagnostica
   guiderà il corrective successivo. Se il record fosse assente od opaco, si
   correggerà offline il reporting e non si ripeterà immediatamente il live.

```text
OUTCOME=READY — D268_01_FIRST_IMAGE_OPERATOR_KIT_READY_OFFLINE
ADVANCEMENT=NEW_LIVE_CRITICAL_OPERATOR_PATH_WITH_CORRECTED_DECODER_AND_TYPED_DIAGNOSTICS
EXECUTABLE_CLOSURE=PASS
RESIDUAL_BLOCKER_OR_RISK=NEW_D268_BASELINE_NOT_YET_APPROVED_AND_LIVE_NOT_AUTHORIZED
CANONICAL_DOCUMENTATION=UPDATED
D267_03_MANIFEST_HISTORY_RESTORED=true
BASELINE_APPROVED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
FIRST_IMAGE_LIVE_PROVEN=false
```

### D268/02: post-live first-image evidence closure e prossimo boundary

D268/02 è **OFFLINE ONLY**. Non esegue hardware, non usa `sudo`, non apre USB
reale, non materializza secret reali, non esegue una seconda run D268 e non
modifica la semantica live-critical. La run D268 one-shot appartiene alla baseline
approvata `c03d32e8647444495e6615e41c2839cbddd62143` ed è conclusa; il marker è
consumato e nessuna nuova autorizzazione live è implicita.

La closure probatoria della run live D268 è **buona e non viene rifatta né
reinterpretata** (`LIVE_EVIDENCE_CLOSURE=PASS`).

#### Evidenza live classificata

Registrata come **osservata target-specific live** (non più sola corroborazione
statica/OEM/third-party):

```text
FIRST_IMAGE_B0_LIVE_PROVEN=true
IMAGE_0X88_NO_CHECK_TARGET_PROVEN=true
IMAGE_ADDITIVE_CHECKSUM_MISMATCH_LIVE_OBSERVED=true
IMAGE_RECORD_CRC_LIVE_PROVEN=true
FIRST_IMAGE_DECODE_LIVE_PROVEN=true
FIRST_IMAGE_RASTER_SHAPE=80x64
FIRST_IMAGE_RECEIVED=true
```

Il punto essenziale: `trailer=0x88`, `payload additive checksum match=false`,
`policy=NO_CHECK_0X88_ACCEPTED`, `record CRC=true`, `decode=successful_raster_decode`,
`shape=80x64`. Questa è ora evidenza primaria sul target APP12509.

#### Causalità storica D267/01 (inferenza causale forte, non osservazione retroattiva)

Classificazione epistemica esatta:

```text
D267_01_FIRST_B0_RECEIVED=OBSERVED
D267_01_FIRST_IMAGE_DECODE_FAILED=OBSERVED
D267_01_ACTUAL_TRAILER=UNKNOWN
D268_FIRST_IMAGE_TRAILER_0X88=OBSERVED_TARGET_LIVE
D268_ADDITIVE_CHECKSUM_MATCH_FALSE=OBSERVED_TARGET_LIVE
OLD_STRICT_ADDITIVE_PARSER_MISMATCH_WITH_0X88=VERIFIED
D267_01_CAUSE=STRONG_CAUSAL_INFERENCE
```

- In D267/01 sono **osservati** la ricezione del primo B0 e il fallimento
  `first_image_decode_failed`; il trailer effettivo di quella run non fu conservato
  e resta `UNKNOWN`.
- In D268 sono **osservati target-specific live** il trailer `0x88` e il mismatch
  del checksum additivo; è inoltre **verificato** (da D267/04 sul call-flow OEM) che
  il vecchio parser strict additivo è incompatibile con `0x88`.
- La causa di D267/01 è pertanto una **inferenza causale forte**, non un'
  osservazione retroattiva del trailer `0x88`: D267/01 non viene riscritto come se
  avesse registrato `0x88` allora.

#### Safety closure

```text
USB_OPEN_COUNT=1
TRANSPORT_SESSION_COUNT=1
TLS_OBJECT_COUNT=1
TLS_HANDSHAKE_COUNT=1
SECRET_MATERIALIZATION_COUNT=1
FINAL_FDT_ARM_COUNT=1
IRQ2_FINGER_DOWN_COUNT=1
COMMAND_22_ATTEMPT_COUNT=1
COMMAND_22_ACK_VALIDATION_COUNT=1
FIRST_B0_COUNT=1
RETRY_COUNT=0
RECOVERY_COUNT=0
REOPEN_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
FORBIDDEN_POST_IMAGE_COMMAND_COUNT=0
HOST_CLEANUP_STATUS=COMPLETATO
SECRET_ZEROIZED=true
FPRINTD_RESTORE_CALLBACK_COMPLETED_WITHOUT_EXCEPTION=VERIFIED_BY_CONTROL_FLOW
```

Il report protetto canonico
`/var/lib/goodix-5125-poc/d261-results/d268-first-image-final.json` non è
leggibile dall'utente corrente (permessi negati) e D268/02 non usa `sudo`, non
cambia permessi e non blocca lo step: il summary live e il control-flow verificabile
del codice sono sufficienti. La run ha restituito `PASS_STOP_AFTER_FIRST_IMAGE`,
quindi `restore_fprintd()` nel `finally` non ha sollevato eccezione. La classe
dell'evidenza è:

```text
FPRINTD_RESTORE_EVIDENCE_CLASS=VERIFIED_BY_CONTROL_FLOW_NOT_EXTERNAL_STATE_OBSERVATION
EXTERNAL_FPRINTD_FINAL_STATE=NOT_INDEPENDENTLY_OBSERVED
```

#### Closure canonica D218–D220 preservata

D268/02 **preserva integralmente** la closure D218–D220 (recuperata da
`docs/EVIDENCE.md` WIN-001 e da `README.md`):

```text
D220_WINDOWS_PREPROCESSOR_CONSUMES_U16_NO_U8_ADAPTER_JUSTIFIED=true
INTENSITY_CONTRACT=DIRECT_U16_CONSUMED_PROVEN
ORIENTATION_CONTRACT=UNRESOLVED
NEXT_BLOCKER=LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT
D220_CLOSURE_PRESERVED=true
```

Significato: Windows/`AlgoChicago.dll` consuma direttamente il raster `u16`/12-bit;
non è giustificato alcun adapter `u16 → u8` ricostruito dal contratto Windows;
l'orientamento resta non risolto; la decisione successiva è Linux-specifica, non
una nuova campagna statica Windows.

#### Prossimo boundary tecnico

Il prossimo boundary principale è la **decisione di engineering Linux-specifica**
su come rappresentare/adattare il raster Goodix `80x64 u16`/12-bit verso il
contratto Linux/libfprint, mantenendo distinte semantica del sensore, contratto
Windows già ricostruito e orientamento `UNRESOLVED`:

```text
NEXT_PRIMARY_BOUNDARY=LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT
```

Parte dal nuovo fatto D268 (`target live image → valid image record → decoded
raster 80x64 u16`) e dalla conoscenza D220 (Windows consuma u16 direttamente, nessun
adapter u8). I sottoproblemi che il prossimo step dovrà affrontare, senza assumere
la soluzione:

```text
libfprint image representation requirements
u16/12-bit -> Linux/libfprint mapping
scaling / clipping / normalization policy
orientation / transpose / flags
quality/preprocessing ownership
whether conversion belongs in GPL core or LGPL libfprint glue
```

Non si implementa codice in D268/02: il task successivo è definito per review
AI-PM.

```text
OUTCOME=READY — D268_02_FIRST_IMAGE_LIVE_EVIDENCE_CLOSED
ADVANCEMENT=LIVE_FIRST_IMAGE_BOUNDARY_CLOSED_AND_LINUX_LIBFPRINT_BOUNDARY_DEFINED
EXECUTABLE_CLOSURE=NOT_APPLICABLE
RESIDUAL_BLOCKER_OR_RISK=LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT; ORIENTATION_UNRESOLVED
CANONICAL_DOCUMENTATION=UPDATED
LIVE_EVIDENCE_CLOSURE=PASS
D267_01_CAUSAL_CLASSIFICATION=STRONG_CAUSAL_INFERENCE
FPRINTD_RESTORE_EVIDENCE_CLASS=VERIFIED_BY_CONTROL_FLOW_NOT_EXTERNAL_STATE_OBSERVATION
D220_CLOSURE_PRESERVED=true
NEXT_PRIMARY_BOUNDARY=LINUX_U16_TO_LIBFPRINT_ENGINEERING_DECISION_NON_WINDOWS_CONTRACT
FIRST_IMAGE_RECEIVED=true
IMAGE_0X88_NO_CHECK_TARGET_PROVEN=true
IMAGE_RECORD_CRC_LIVE_PROVEN=true
FIRST_IMAGE_DECODE_LIVE_PROVEN=true
FIRST_IMAGE_RASTER_SHAPE=80x64
D267_01_CAUSE=STRONG_CAUSAL_INFERENCE
D268_RETRY_AUTHORIZED=false
LIVE_AUTHORIZED=false
```

### D269/01: contratto Linux u16/12-bit → libfprint e adapter bounded offline

D269/01 è **OFFLINE ONLY**: nessun accesso USB, TLS, secret, fprintd o hardware;
nessun file live-critical è modificato. L'audit usa la copia libfprint
materializzata nello snapshot Rockytkg, identificata dalla provenance al gitlink
upstream `7ebe0c809b4d1df3400e84299a4ec4acdea84590` e dichiarata versione `1.94.5`.

Il contratto osservato/verificato è:

```text
LIBFPRINT_IMAGE_PIXEL_CONTRACT=PACKED_GRAYSCALE_U8_ONE_BYTE_PER_PIXEL
LIBFPRINT_IMAGE_BIT_DEPTH=8
LIBFPRINT_IMAGE_DIMENSION_CONTRACT=WIDTH_HEIGHT_CONSTRUCT_ONLY_DATA_LENGTH_WIDTH_X_HEIGHT_STRIDE_IMPLICIT_WIDTH
LIBFPRINT_IMAGE_ORIENTATION_MECHANISM=V_FLIPPED_H_FLIPPED_COLORS_INVERTED_FLAGS_NO_ROTATE_OR_TRANSPOSE_FLAG
LIBFPRINT_IMAGE_OWNERSHIP_CONTRACT=FPIMAGE_GOBJECT_OWNS_ALLOCATED_DATA
LIBFPRINT_PREPROCESSING_EXPECTATION=DRIVER_SUPPLIES_U8;STANDARD_PATH_ONLY_APPLIES_FLAGS_THEN_NBIS_8BIT;SIGFM_CONSUMES_U8_COPY_DIRECTLY
```

`fp_image_new(width,height)` alloca `width*height` byte; `FpImage::data` è
`guint8 *`; `fp_image_get_data()` restituisce esattamente `width*height`; NBIS è
invocato con depth `8`. I flag standard possono applicare flip verticale,
orizzontale e inversione colori prima di NBIS, ma non esiste un flag rotate o
transpose né un helper standard che converta/normalizzi un raster u16. Nel fork
SIGFM, l'estrazione copia e consuma direttamente i byte senza applicare i flag:
questo rende ancora più importante non usare flag come sostituto di una futura
decisione esplicita di orientation/polarity.

Il confronto locale mostra due precedenti distinti: il driver AES3K espande in
modo fixed il proprio dominio 4-bit a 8-bit (`nibble*17`), mentre ELAN applica
un min/max frame-local specifico del driver. Rockytkg `src/goodixgf.c` (LGPL)
chiama `gx_imgproc_to8bit`, ma la trasformazione concreta è in
`src/goodix_imgproc.c` (GPL) ed è sensor/matcher-specifica: baseline, flat-field,
percentili e enhancement. È corroborazione che il boundary esiste, non prova
target-specific né espressione trasferibile nel glue LGPL.

D269/01 adotta quindi il minimo contratto Linux stabile e non adattivo:

```text
INTENSITY_MAPPING_DECISION=FIXED_LINEAR_FULL_RANGE_ROUND_NEAREST_12BIT_TO_8BIT
INTENSITY_MAPPING_FORMULA=round(sample*255/4095)
INTENSITY_MAPPING_EVIDENCE_CLASS=VERIFIED_ENGINEERING_DECISION_FROM_LOCAL_API_AND_FIXED_RANGE_PRECEDENT
INTENSITY_MAPPING_STABILITY=FRAME_CONTENT_INDEPENDENT_CROSS_FRAME_STABLE_MONOTONIC_NONDECREASING
WINDOWS_CONTRACT_REUSED=false
```

Questa quantizzazione usa l'intero dominio dichiarato dal decoder, conserva
ordine e endpoint ed evita che il significato di uno stesso sample cambi da un
frame all'altro. Non è una quality policy e non dimostra contrasto sufficiente
per NBIS/SIGFM; min/max, percentili, baseline subtraction, flat-field ed
enhancement restano fuori dal contratto bounded finché non esiste evidenza
biometrica/architetturale specifica.

L'adapter indipendente `libfprint-driver/goodix_u16_to_fpimage.c` è
`LGPL-2.1-or-later`. Accetta soltanto 5120 `uint16_t`, valida l'intero frame nel
range `0..4095` prima di scrivere, produce 5120 byte packed e metadata
`80x64`, stride `80`, flags `0`, orientation canonica preservata e natural
orientation non risolta. Non modifica il decoder GPL e non contiene I/O.

```text
WIRE_TO_CANONICAL_RASTER_TRANSPOSE=IMPLEMENTED_IN_CANONICAL_GPL_DECODER
CANONICAL_RASTER_TO_FINGERPRINT_NATURAL_ORIENTATION=UNRESOLVED
ORIENTATION_CONTRACT=UNRESOLVED
U16_TO_LIBFPRINT_OWNER=LGPL_LIBFPRINT_DRIVER_GLUE
LICENSING_BOUNDARY_STATUS=PASS_INDEPENDENT_LGPL_ADAPTER_NO_GPL_EXPRESSION_TRANSFERRED
GPL_TO_LGPL_DATA_CONTRACT=OWNED_80X64_U16_12BIT_CANONICAL_RASTER_PLUS_METADATA
ADAPTER_IMPLEMENTATION_GATE=PASS
```

I test C sintetici coprono raster valido, count e output size errati, null,
sample oltre range, rappresentazione castata di un negativo, minimo, massimo,
KAT non banale, monotonicità su tutti i 4096 valori, determinismo,
indipendenza dal contenuto globale del frame, input invariato, dimensioni e
orientation metadata. Build GCC strict, unit test da root e da cwd esterno e
audit dell'oggetto senza simboli I/O indefiniti passano. ASan/UBSan è saltato
per runtime linker non installati; non è necessario alla closure.

```text
OUTCOME=READY — D269_01_PIXEL_REPRESENTATION_CONTRACT_CLOSED_PPMM_LOCALIZED
ADVANCEMENT=LINUX_LIBFPRINT_IMAGE_CONTRACT_DEFINED_BOUNDED_ADAPTER_VERIFIED_AND_PPMM_PREREQUISITE_LOCALIZED
EXECUTABLE_CLOSURE=PASS
PIXEL_REPRESENTATION_CONTRACT=CLOSED_OFFLINE
INTENSITY_QUANTIZATION_CONTRACT=CLOSED_OFFLINE
FULL_FPIMAGE_PIPELINE_CONTRACT=NOT_YET_CLOSED
RESIDUAL_BLOCKER_OR_RISK=TARGET_APP12509_PHYSICAL_PPMM_UNRESOLVED;ORIENTATION_AND_POLARITY_UNRESOLVED;BIOMETRIC_QUALITY_OF_FIXED_MAPPING_NOT_YET_PROVEN
CANONICAL_DOCUMENTATION=UPDATED
NEXT_PRIMARY_BOUNDARY=LIBFPRINT_IMAGE_PIPELINE_INTEGRATION_OFFLINE
NEXT_BOUNDARY_PREREQUISITE=RESOLVE_OR_EXPLICITLY_BOUND_PPMM_SEMANTICS
D268_RETRY_AUTHORIZED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

#### D269/01 corrective — audit semantico `FpImage::ppmm`

Il corrective (post-review AI-PM) audità `FpImage::ppmm` senza modificare il
converter. Gerarchia probatoria:

```text
LIBFPRINT_IMAGE_PPMM_FIELD=OBSERVED            (fpi-image.h:63; fp-image.h getter)
FPIMAGE_PPMM_INITIAL_VALUE=0.0                 (GObject instance zero-init; fp_image_init vuoto)
FPIMAGE_PPMM_INITIALIZATION_PATH=NONE_IN_LIBFPRINT_CORE  (driver scrive fimg->ppmm direttamente)
LIBFPRINT_NBIS_CONSUMES_PPMM=VERIFIED
NBIS_PPMM_CALLSITE=fp-image.c:370 → get_minutiae → combined_minutia_quality → radius_pix=RADIUS_MM*ppmm
NBIS_PPMM_SEMANTIC_ROLE=resolution-scaled minutia reliability neighborhood radius
SIGFM_PPMM_CONSUMPTION=NO                      (sigfm_extract(image,w,h) only)
ROCKYTKG_GOODIX_PPMM_500DPI=THIRD_PARTY_CORROBORATION (Rockytkg/src/goodixgf.c:281; commento: "solo per display")
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
TARGET_PPMM_EVIDENCE_CLASS=UNKNOWN
ADAPTER_BYTES_UNCHANGED=true
RUNTIME_CODE_CHANGE_REQUIRED=false
```

NBIS richiede `ppmm` semanticamente (raggio in pixel derivato da `RADIUS_MM ×
ppmm`); SIGFM non lo passa. Il glue futuro che alloca il vero `FpImage` dovrà
quindi fissare `ppmm` con evidenza target-specific o dichiararlo esplicitamente
non risolto, prima che il full pipeline contract possa chiudersi. Non esiste
alcuna evidenza locale target-specific (OEM, capture, misura diretta, datashed
APP12509) che fissi ppmm/DPI: il valore 500 DPI in Rockytkg è terza parte e non
viene promosso a fatto target-specific.

Il D268 operator-kit `test_full_lowercase_sha_is_mandatory_and_dirty_tree_fails_closed`
fallisce in questo ambiente (guard worktree-dirty non solleva); è pre-esistente,
estraneo al corrective ppmm e all'adapter (byte-identico) e non viene corretto
qui per disciplina anti-deragliamento.

### D270/01: integrazione offline del vero FpImage e ppmm bounded

D270/01 è **OFFLINE ONLY** e synthetic-only. Non apre USB, non usa capture
biometriche reali, non contatta fprintd e non materializza secret. La fonte API
è la copia libfprint 1.94.5 materializzata in `Rockytkg/libfprint/`, commit
gitlink di provenance `7ebe0c809b4d1df3400e84299a4ec4acdea84590`.

L'audit verifica nel codice locale che `fp_image_new(width,height)` usa
`g_object_new()` con width/height construct-only e che `constructed()` alloca
`width*height` byte tramite `g_malloc0`. `FpImage` possiede `data`; il getter
restituisce una vista `transfer none`; `finalize()` libera data, binarized e
minutiae. Non esiste stride esplicito. `flags`, `ppmm`, binarized, minutiae,
SIGFM info e il campo interno `ref_count` partono da zero/null per
zero-initialization; `fp_image_init()` è vuoto e non assegna 500 DPI.

Il nuovo owner opaco LGPL `libfprint-driver/goodix_fpimage_pipeline.c` alloca
`FpImage(80,64)`, passa direttamente il buffer object-owned all'adapter D269 e
verifica metadata `80×64`, stride implicito 80, 5120 byte e flags zero. Non
introduce flip, rotate, transpose, inversione, normalizzazione frame-local o
I/O. L'owner mantiene l'unico riferimento iniziale fino alla free; un weak
pointer GObject prova la finalizzazione nel test.

Il campo numerico `image->ppmm` resta tecnicamente `0.0` perché il core locale
lo zero-inizializza, ma questo valore non è semanticamente esposto come misura.
Lo stato autorevole del wrapper è
`GOODIX_FPIMAGE_PHYSICAL_PPMM_UNKNOWN`. Il gate consumer-specific blocca NBIS
con `GOODIX_FPIMAGE_PIPELINE_PHYSICAL_PPMM_REQUIRED`; per SIGFM restituisce
soltanto che il requisito ppmm non si applica. Non autorizza feature extraction,
matching o enrollment e non sceglie l'algoritmo.

Matrice downstream canonica:

| Livello | Usa ppmm | Eseguibile con ppmm unknown | Validità semantica D270 | Gate |
| --- | --- | --- | --- | --- |
| costruzione FpImage | no | sì, testata | valida per rappresentazione/ownership | PASS |
| preprocessing bounded D269 | no | sì, testato | valida solo la quantizzazione fixed | PASS |
| SIGFM extraction | no, verificato | tecnicamente sì | non validata/né selezionata | STOP prima dell'uso feature |
| NBIS minutiae/quality | sì, verificato | codice tecnicamente invocabile con zero, ma non autorizzato | invalida senza ppmm fisico | BLOCKED |
| feature extraction | dipende dall'algoritmo | non chiusa | non dimostrata | BLOCKED oltre i soli gate extractor |
| matching | non direttamente dopo feature valide | non autorizzato | non dimostrata | BLOCKED |
| enrollment | dipende da extraction e matching validi | non autorizzato | non dimostrata | BLOCKED |

Il runner compila il vero `fp-image.c` locale insieme al nuovo helper e a stub
link-only che abortirebbero se D270 attraversasse accidentalmente NBIS/SIGFM.
Build GCC strict, KAT, determinismo, frame-independence, failure behavior,
weak-finalization, audit simboli vietati, ASan/UBSan e invocazione da Git root e
da `/tmp` passano. La fault injection di OOM interna a `fp_image_new()` è
`NOT_AVAILABLE`: GLib usa allocazione abort-on-OOM; il wrapper usa `g_try_new0`,
gestisce NULL e non introduce un allocator globale solo per il test.

```text
OUTCOME=READY — D270_01_FPIMAGE_OBJECT_PIPELINE_PARTIALLY_CLOSED
ADVANCEMENT=REAL_LOCAL_FPIMAGE_CONSTRUCTION_AND_LIFETIME_VERIFIED_WITH_UNKNOWN_PPMM_FAIL_CLOSED
EXECUTABLE_CLOSURE=PASS
PIXEL_REPRESENTATION_CONTRACT=CLOSED_OFFLINE
INTENSITY_QUANTIZATION_CONTRACT=CLOSED_OFFLINE
FPIMAGE_OBJECT_CONSTRUCTION=CLOSED_OFFLINE
FPIMAGE_BUFFER_OWNERSHIP=CLOSED_OFFLINE
FPIMAGE_DIMENSION_CONTRACT=CLOSED_OFFLINE
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
UNKNOWN_PPMM_SEMANTICS=EXPLICITLY_BOUNDED
NBIS_WITH_UNKNOWN_PPMM=BLOCKED
SIGFM_PPMM_CONSUMPTION=NO_VERIFIED
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
FULL_FPIMAGE_PIPELINE_CONTRACT=PARTIALLY_CLOSED
RESIDUAL_BLOCKER_OR_RISK=PPMM_ORIENTATION_POLARITY_AND_BIOMETRIC_QUALITY_UNRESOLVED;EXTRACTOR_NOT_SELECTED
CANONICAL_DOCUMENTATION=UPDATED
NEXT_PRIMARY_BOUNDARY=LIBFPRINT_FEATURE_EXTRACTION_POLICY_OFFLINE
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

### D271/01: policy feature extraction libfprint offline

D271/01 è **OFFLINE ONLY** e documentale: non apre USB, non usa capture o
raster biometrici reali, non contatta fprintd, non materializza secret e non
modifica codice eseguibile. La fonte software primaria è la copia libfprint
1.94.5 materializzata in `Rockytkg/libfprint/`, gitlink di provenance
`7ebe0c809b4d1df3400e84299a4ec4acdea84590`.

#### Call-flow locale

`fpi_image_device_image_captured()` sceglie l'extractor dalla proprietà di
classe `algorithm`. Il default è NBIS; un driver può scegliere SIGFM. Entrambi
lavorano asincronicamente su una copia di `width*height` byte. NBIS applica
prima i flag H/V/inversione, invoca `get_minutiae(..., depth=8, ppmm)` e porta
nel `FpImage` dati normalizzati, binarized e minutiae. SIGFM ignora invece tutti
i flag, copia direttamente il raster u8 in una `cv::Mat CV_8UC1` e usa
`cv::SIFT::detectAndCompute`; meno di 25 keypoint produce failure retryable nel
`FpImageDevice`.

Su successo `fpi_print_add_from_image()` converte NBIS in una struttura XYT
owned dal `FpPrint`; per SIGFM inserisce nel template il `SigfmImgInfo`
(keypoint + descrittori). Il trasferimento SIGFM è implicito: l'array del print
ha `sigfm_free_info` come destructor, mentre `FpImage::finalize()` non libera
`sigfm_info`; il call-flow principale mantiene una reference all'immagine e
usa una sola aggiunta, ma il riuso dello stesso info in più print non è un
contratto sicuro dimostrato. La serializzazione `FP3` salva ogni XYT NBIS o il
blob SIGFM keypoint+descriptor e la deserializzazione ricostruisce gli oggetti.

Enrollment accumula una feature structure per stage nel template. Il base
`FpImageDevice` usa 5 stage; Rockytkg configura, come sola corroborazione terza
parte, un percorso SIGFM Goodix dinamico 3--8 stage. Verify/identify estraggono
un singolo nuovo print e lo confrontano con ogni stage/template: Bozorth3 per
NBIS, `sigfm_match_score()` per SIGFM.

#### SIGFM

SIGFM non consuma `ppmm`, non ridimensiona e non normalizza internamente oltre
alla copia in `CV_8UC1`. L'extractor SIFT non contiene un limite dimensionale
esplicito, quindi `80x64` è strutturalmente accettato, ma il gate libfprint di
25 keypoint rende l'effettiva supportability dipendente dal contenuto. La
pipeline Rockytkg usa esattamente 80×64 ed è riportata funzionante per
enrollment/verify: è `THIRD_PARTY_CORROBORATION`, non prova la qualità del
mapping D269 sul target locale.

Il matcher applica ratio test descrittore 0,75, richiede almeno 5 match, accetta
lunghezze tra coppie entro circa il 5% e conta coppie con trasformazione angolare
coerente entro circa il 5%; un driver stabilisce poi lo score threshold. Il
default generico locale è 40, Rockytkg usa 20: nessuno dei due è una soglia
target-local validata per il nostro mapping. Il codice suggerisce tolleranza a
rotazione rigida e scala molto limitata, ma i test locali SIGFM coprono
serializzazione su immagini 256×256, non trasformazioni, 80×64 o polarity.
Pertanto non è provata invarianza generale a rotazione/scala; inversione di
polarità e flag non sono gestiti dal path SIGFM. Il matcher contiene le proprie
eccezioni e restituisce errore, mentre `sigfm_extract()` non contiene eccezioni
OpenCV; inoltre `fp_print_equal()` non implementa SIGFM. Sono limiti del fork
da preservare nella futura validazione, non blocker della sola candidatura.

#### NBIS

NBIS usa LFSv2 con blocksize 8 e rifiuta soltanto immagini più piccole di un
blocco: `80x64` supera quindi il limite strutturale e produce una mappa teorica
10×8. Questo non prova minutiae utili. `combined_minutia_quality()` converte il
raggio fisico in pixel con `round(RADIUS_MM*ppmm)`; lo zero storage non è valido.
Il template conserva fino a 200 minutiae XYT e Bozorth restituisce score zero
quando probe o gallery hanno meno di 10 minutiae. Anche ottenendo il `ppmm`
fisico resterebbe dunque da provare che la piccola geometria e il mapping D269
producano almeno 10 minutiae stabili e score separabili.

#### Evidenza target e licensing

Il riesame di D218--D220, D268--D270, `gfusb.dll`, `AlgoChicago.dll` e del
corpus testuale non trova una misura fisica APP12509 né un contratto di natural
orientation o polarity. Le stringhe di rotazione osservate in
`AlgoChicagoT.dll` non appartengono al consumer target selezionato
`AlgoChicago.dll` e non vengono promosse. Restano quindi:

```text
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
```

Il fork libfprint e SIGFM dichiarano `LGPL-2.1-or-later`; NBIS incorporato è
materiale NIST public domain. SIGFM aggiunge una dipendenza build/runtime
OpenCV4. Rockytkg `goodixgf.c` è LGPL, ma la sua trasformazione concreta
`goodix_imgproc.c` è GPL-2.0-or-later e non entra nel driver LGPL. D271 non
importa né adatta alcuna espressione esterna.

#### Decisione e prossimo confine

La policy si chiude come classificazione architetturale: SIGFM è l'unico
candidato da validare, non un extractor production-selected; NBIS è bloccato
dal `ppmm` ignoto e da una seconda incertezza sulla densità di minutiae. La
qualità biometrica richiede evidenza target-reale futura: almeno distribuzione
dei keypoint per frame rispetto al gate 25, stabilità/serializzazione dei
template, punteggi same-finger e different-finger sufficienti a calibrare una
soglia, e confronto controllato della polarity/orientation solo se una
trasformazione è indipendentemente giustificata. Nessun numero sintetico può
soddisfare tali metriche.

```text
OUTCOME=READY — D271_01_FEATURE_EXTRACTION_POLICY_CLOSED_OFFLINE
ADVANCEMENT=ARCHITECTURAL_NON_HARDWARE_LIBFPRINT_EXTRACTOR_POLICY_CLOSED_WITH_PRECISE_VALIDATION_BOUNDARY
EXECUTABLE_CLOSURE=NOT_APPLICABLE
FEATURE_EXTRACTOR_POLICY=CLOSED_OFFLINE
SIGFM_STATUS=CANDIDATE_FOR_VALIDATION
NBIS_STATUS=BLOCKED_UNKNOWN_PHYSICAL_PPMM_AND_TARGET_LOCAL_MINUTIA_DENSITY_UNPROVEN
SIGFM_PPMM_REQUIREMENT=NOT_CONSUMED_VERIFIED
NBIS_PPMM_REQUIREMENT=REQUIRED_VERIFIED
SIGFM_80X64_SUPPORT_STATUS=ARCHITECTURALLY_SUPPORTED_WITH_MIN_25_KEYPOINT_GATE_TARGET_QUALITY_UNPROVEN
NBIS_80X64_SUPPORT_STATUS=STRUCTURALLY_ACCEPTED_MIN_8PX_BLOCK_BUT_TARGET_USABILITY_BLOCKED
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
BIOMETRIC_QUALITY_STATUS=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED
FULL_FPIMAGE_PIPELINE_CONTRACT=PARTIALLY_CLOSED
RESIDUAL_BLOCKER_OR_RISK=SIGFM_TARGET_LOCAL_KEYPOINT_MATCH_THRESHOLD_POLARITY_AND_ORIENTATION_VALIDATION_MISSING;NBIS_PPMM_AND_MINUTIA_DENSITY_MISSING
CANONICAL_DOCUMENTATION=UPDATED
NEXT_PRIMARY_BOUNDARY=SIGFM_TARGET_LOCAL_BIOMETRIC_VALIDATION
NEXT_BOUNDARY_PREREQUISITE=AUTHORIZED_PRIVACY_PRESERVING_TARGET_REAL_KEYPOINT_AND_MATCH_METRICS_WITH_D269_FIXED_MAPPING
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

### D278/14 — closure live finale native C a due acquisizioni

Data closure: **1 settembre 2026**.

Questa sezione è la fonte canonica corrente per il boundary D278/14 e
**supersede**, senza cancellarne il valore storico, tutti i precedenti marker
D278/12–D278/14 che classificavano il secondo raster, il secondo ciclo o
l'integrazione live native C come `HOST_ONLY`, `UNOBSERVED` o
`TARGET_PROVEN=false`.

#### Baseline finale e risultato

```text
D278_14_FINAL_LIVE_ATTEMPT=12
D278_14_FINAL_LIVE_RESULT=PASS
D278_14_FINAL_BASELINE=5b7b8415d57a474ae9915a4e46954a7afaafe327
D278_14_FINAL_PREPARED_BUILD_DIR=/tmp/goodix-d278-14-approved.LXYYuS
D278_14_FINAL_BINARY_SHA256=7f9ecad1097c279d54c6ba7f61be9e00c7ef1e5edd6b9362f72320dcf8e34379
D278_14_TOTAL_LIVE_ATTEMPTS=12
D278_14_TOTAL_CONSUMED_AUTHORIZATIONS=12
D278_14_RERUN_AUTHORIZED=false
```

La run ha raggiunto `STOP` normalmente in **5287 ms**. Non è stata una
closure per timeout o cleanup successivo al failure:

```text
RESULT=pass
FAILURE_CLASS=NONE
STOP_REACHED=true
SECURE_PHASE_AT_STOP=STOP
POST_TLS_PHASE_AT_STOP=STOP
POST_TLS_TERMINAL=false
IN_OUTSTANDING_AT_STOP=0
ROUTER_OUTSTANDING_AT_STOP=0
BACKEND_DRAINED=true
CLEANUP_COMPLETE=true
```

#### Sequenza target live chiusa

La seguente catena è ora osservata/provata sul target reale nello stesso
percorso native C:

```text
PRE_SESSION_RX_SYNC
→ REENTRY_RECOVERY_A2
→ A8 / GF_ST411SEC_APP_12509
→ E4
→ OEM_COLD_START_A2_1
→ CHIP_82
→ OTP_A6
→ OEM_COLD_START_A2_2
→ MODE_70
→ DAC_220
→ DAC_236
→ DAC_238
→ DAC_23A
→ CONFIG_90
→ D1
→ TLS 1.2 PSK
→ D4
→ AF
→ 0x36 / IRQ0100
→ 0x50 / NAV
→ 0x36 / IRQ0100
→ 0x82
→ 0x20 / baseline B0
→ 0x36 / IRQ0100
→ fresh FDT
→ first 0x32 arm
→ first IRQ0002
→ first 0x22
→ first B0
→ first decode
→ first FpImage pipeline
→ 0x34
→ IRQ0200
→ post-up 0x20
→ post-up B0
→ 0x50 / NAV
→ release tail complete
→ fresh down table
→ exactly one rearm 0x32
→ second IRQ0002
→ second 0x22
→ second B0
→ second decode
→ second FpImage pipeline
→ STOP
```

Contatori canonici:

```text
D4_COUNT=1
AF_COUNT=1

FDT36_COUNT=3
FDT_IRQ100_COUNT=3
FRESH_FDT_COUNT=1

FIRST_IRQ0002_COUNT=1
FIRST_0X22_COUNT=1
FIRST_B0_COUNT=1
FIRST_DECODE_COUNT=1
FIRST_IMAGE_PIPELINE_COUNT=1

RELEASE_0X34_COUNT=1
IRQ0200_COUNT=1
POST_UP_0X20_COUNT=1
POST_UP_B0_COUNT=1
NAV_0X50_COUNT=1
NAV_RESPONSE_COUNT=1
RELEASE_TAIL_COMPLETE_COUNT=1
FRESH_DOWN_TABLE_COUNT=1
REARM_COUNT=1

SECOND_IRQ0002_COUNT=1
SECOND_0X22_COUNT=1
SECOND_B0_COUNT=1
SECOND_DECODE_COUNT=1
SECOND_IMAGE_PIPELINE_COUNT=1

THIRD_CYCLE_COMMAND_COUNT=0
```

#### Ownership USB/TLS e invarianti di sicurezza

La run finale prova il boundary con:

```text
USB_OPEN_ATTEMPT_COUNT=1
USB_OPEN_COUNT=1
USB_CLAIM_COUNT=1
USB_RELEASE_COUNT=1
USB_CLOSE_COUNT=1

PHYSICAL_SUBMIT_COUNT=88
PHYSICAL_IN_SUBMIT_COUNT=54
PHYSICAL_OUT_SUBMIT_COUNT=34
PHYSICAL_IN_COMPLETION_COUNT=54
PHYSICAL_OUT_COMPLETION_COUNT=34
MAX_OUTSTANDING_IN=1
MAX_OUTSTANDING_OUT=1

TLS_HANDSHAKE_COUNT=1
TLS_ESTABLISHED=true
SECRET_HANDOFF_COUNT=1
PROJECT_SECRET_ZEROIZED=true

RETRY_COUNT=0
REOPEN_COUNT=0
DEVICE_RESET_COUNT=0
CLEAR_HALT_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
```

Promozioni probatorie correnti:

```text
REENTRY_PREFIXED_NATIVE_SECURE_SESSION_TARGET_PROVEN=true
NATIVE_TLS12_PSK_HANDSHAKE_WITH_REENTRY_RECOVERY_TARGET_PROVEN=true
POST_TLS_TWO_ACQUISITION_NATIVE_C_INTEGRATION_LIVE_PROVEN=true

LINUX_FIRST_IMAGE_PIPELINE_LIVE_PROVEN=true
LINUX_SECOND_IMAGE_PIPELINE_LIVE_PROVEN=true
SECOND_IMAGE_RASTER_TARGET_PROVEN=true
TWO_ACQUISITION_REARM_LIVE_PROVEN=true

SAME_GOODIX_DEVICE_CONTEXT_LIVE_PROVEN=true
SAME_OPEN_EPOCH_USB_OWNER_LIVE_PROVEN=true
SINGLE_USB_BACKEND_OWNER_LIVE_PROVEN=true
SINGLE_USB_ROUTER_LIVE_PROVEN=true
SINGLE_PHYSICAL_IN_OWNER_LIVE_PROVEN=true

SINGLE_TLS_OBJECT_LIVE_PROVEN=true
SAME_TLS_SESSION_THROUGH_SECOND_IMAGE_LIVE_PROVEN=true
SINGLE_SECRET_HANDOFF_LIVE_PROVEN=true

NO_RETRY_LIVE_PROVEN=true
NO_REOPEN_LIVE_PROVEN=true
NO_DEVICE_RESET_LIVE_PROVEN=true
NO_CLEAR_HALT_LIVE_PROVEN=true
NO_PERSISTENT_DEVICE_WRITE_LIVE_PROVEN=true
```

Questa prova è target-specific per `27c6:5125` /
`GF_ST411SEC_APP_12509`. Non generalizza automaticamente ad altri firmware o
modelli Goodix e non modifica i vincoli factory-preserving.

#### Ledger delle dodici autorizzazioni consumate

| # | Baseline | Confine raggiunto / esito | Conoscenza prodotta |
|---:|---|---|---|
| 1 | `2172e750...` | `SIGABRT` prima del protocollo | `FpDevice` virtuale incompatibile con `fpi-usb-device` reale |
| 2 | `fceae05d...` | A2 ACK, poi deadline | callback USB reale non riarmava il secondo IN |
| 3 | `87c1bf89...` | typed-shaped pre-ACK | evidenza compatibile con residui RX inter-sessione |
| 4 | `7ce15fa7...` | ACK + secondo ACK-shaped | backend drained non implica RX device vuoto |
| 5 | `b64c01a3...` | TLS + D4, stop su D4 | delta live rispetto alla policy storica di pacing |
| 6 | `ddc01a3b...` | D4 ACK + AF, timeout AF | pre-D4 20 ms ripristina avanzamento; AF resta bloccato |
| 7 | `e2f11d40...` | timeout AF | pre-AF pacing non è la causa del blocco |
| 8 | `5aa04e71...` | PRE_BIND, USB non aperto | CWD caller leaked nei path live-critical; autorizzazione consumata ma sensore non toccato |
| 9 | `5aa04e71...` | AF superato, primo IRQ0100, stop NAV | checksum AF `wire 0xAF / checksum coordinate 0xAE` validato live; NAV OEM richiede `0x88` |
| 10 | `fbfcd583...` | NAV superato, terzo `0x36` | plaintext B0 >4096 veniva erroneamente spezzato in più callback lifecycle |
| 11 | `9c8fb80c...` | prima immagine + release + rearm, stop prima del secondo IRQ2 | intero primo ciclo e rearm live-proven; evento finale non osservabile con telemetry precedente |
| 12 | `5b7b8415...` | **PASS fino al secondo raster e STOP** | closure native C completa a due acquisizioni |

La live #11 non deve essere retro-classificata come «errore operatore»:
l'evento esatto che causò il terminale non era registrato. Fra #11 e #12 è
stata aggiunta soltanto telemetry sanitizzata del reject post-TLS, **senza
cambio di protocollo**. La #12, eseguita con la stessa semantica wire, ha
completato il secondo IRQ2/B0/decode/pipeline. La classificazione corretta di
#11 resta quindi `TRANSIENT_OR_PHYSICAL_SENSOR_EVENT_NOT_STRUCTURAL_PROTOCOL_DEFECT`,
con causa precisa `UNKNOWN`.

#### Difetti di porting definitivamente chiusi durante D278/14

La campagna non deve essere ripercorsa in futuro per riscoprire i seguenti
fatti:

```text
FPDEVICE_USB_SUBTYPE_REQUIRED=true
REAL_USB_IN_COMPLETION_MUST_REARM_CONTEXT_RX=true
PRE_SESSION_RX_QUIET_BOUNDARY_REQUIRED_FOR_REENTRY=true
CALLER_CWD_MUST_NOT_DEFINE_LIVE_CRITICAL_RESOURCE_PATHS=true

A0_ODD_WIRE_CONTROL_CHECKSUM_COORDINATE=control&0xfe
AF_WIRE_CONTROL=0xaf
AF_CHECKSUM_COORDINATE=0xae

OEM_NAV_0X50_RESPONSE_TRAILER=0x88
OEM_NAV_0X50_ADDITIVE_CHECKSUM_REQUIRED=false

TLS_B0_PLAINTEXT_DELIVERY_CONTRACT=ONE_LOGICAL_DELIVERY_PER_CONSUMED_B0_RECORD
TLS_INTERNAL_SSL_READ_CHUNK_SIZE_IS_NOT_LIFECYCLE_BOUNDARY=true

FDT_IRQ0100_BASELINE_COMPONENT=(word>>1)&0xff
FDT_DELTA_OUTSIDE_THRESHOLD=FAIL_CLOSED
```

Il fix AF è causalmente target-validato dal passaggio live da timeout `AF` a
risposta AF/FDT. Il fix NAV è target-validato dal passaggio fino ai successivi
stadi FDT. Il contratto TLS/B0 è target-validato dal passaggio del terzo
`0x36`, dall'intero primo ciclo e infine dalla closure #12.

#### Supersession dei vecchi marker

Sono da leggere esclusivamente come stato storico al loro milestone originario:

```text
D278_12 SECOND_IMAGE_RASTER_TARGET_PROVEN=false
D274/D275 SECOND_TARGET_CYCLE=UNOBSERVED
eventuali marker pre-D278 LINUX_SECOND_B0_LIVE_OBSERVED=false
D278_13 LIVE_CAPABLE_INTEGRATED_PATH_HOST_ONLY_PROVEN=true
```

Lo stato corrente è invece:

```text
SECOND_IMAGE_RASTER_TARGET_PROVEN=true
SECOND_TARGET_CYCLE_NATIVE_C_LIVE_OBSERVED=true
LINUX_SECOND_B0_NATIVE_C_LIVE_OBSERVED=true
LIVE_CAPABLE_INTEGRATED_PATH_TARGET_PROVEN=true
D278_14_EXECUTABLE_CLOSURE=PASS_LIVE
```

#### Decisione

D278/14 è **CHIUSO**. Una nuova esecuzione equivalente non aggiungerebbe
conoscenza necessaria e non è richiesta per confermare questo boundary.

```text
D278_14_OUTCOME=PASS
D278_14_ADVANCEMENT=NATIVE_C_TWO_ACQUISITION_TARGET_LIVE_CLOSURE
D278_14_EXECUTABLE_CLOSURE=PASS_LIVE
D278_14_RERUN_REQUIRED=false
D278_14_RERUN_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
NEXT_PRIMARY_BOUNDARY=OFFLINE_NATIVE_C_DRIVER_INTEGRATION_AND_PRODUCTIONIZATION
EQUIVALENT_TWO_ACQUISITION_LIVE_RERUN_REQUIRED=false
```

Il prossimo lavoro deve quindi partire da questa closure e non ricostruire
A2/A8, TLS, D4/AF, bootstrap FDT, first-image, release-tail, rearm o second-image
come se fossero ancora ipotesi del percorso native C.

### D279/01 — audit di registrazione USB production Fedora 44/libfprint 1.94.100

D279/01 ha verificato integralmente provenance e spec Fedora, le convenzioni
Meson/registry 1.94.100 e il call-flow `FpImageDevice` target prima di applicare
una patch. Il registry standard costruisce `fpi-drivers.c` dai nomi in
`supported_drivers`; una futura registrazione Goodix dovrebbe quindi usare
quel meccanismo e un `FpIdEntry` esatto `27c6:5125`, separato da `goodixmoc`.
Nessun registrar custom è necessario o ammesso.

Il blocker precede però la registrazione. Nella reference target:

```text
FpImageDeviceClass.algorithm=ABSENT
FPI_DEVICE_ALGO_SIGFM=ABSENT
FPI_PRINT_SIGFM=ABSENT
SIGFM_EXTRACTION_AND_MATCHING=ABSENT
fpi_image_device_image_captured=UNCONDITIONALLY_NBIS
```

Nel grafo Goodix già provato la classe imposta invece SIGFM e la pipeline lascia
correttamente `FpImage::ppmm` senza un valore fisico inventato. All'epoca di
D279/01 il contratto canonico D269–D271 trattava il consumo NBIS di `ppmm`
nella quality come veto fail-closed; quindi rimuovere soltanto l'assegnazione
SIGFM non era una correzione meccanica ammessa da quello step. Integrare SIGFM
in 1.94.100 non è una piccola modifica di construction/build: coinvolgerebbe il
core image/print, extraction, matching, serializzazione/deserializzazione,
C++/OpenCV e Meson. Il prompt D279/01 imponeva di non allargare lo scope e di
classificare questo caso come `BLOCKED`.

Nessun sorgente production, registry o build file è stato modificato in
D279/01; nessuna regressione runtime è stata eseguita dopo l'identificazione
del blocker perché non esisteva una patch conforme da validare. Le prove
hardware, discovery operativa, open/claim/submit e fprintd sono rimaste
esplicitamente non eseguite. Il report step-local è
`analysis/D279/D279_01_offline_production_usb_driver_registration_Fedora44_libfprint_1.94.100.md`.
I documenti D279/01, inizialmente non committati per review umana, risultano
poi versionati in `924774e9bd7ea10eabdfd540bf8a4be9b8413c99`.

```text
OUTCOME=BLOCKED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=NOT_REACHED_BLOCKED_BEFORE_IMPLEMENTATION
RESIDUAL_BLOCKER_OR_RISK=FEDORA_44_LIBFPRINT_1_94_100_HAS_ONLY_NBIS_IMAGE_EXTRACTION_WHILE_THE_CANONICAL_GOODIX_CLASS_SELECTS_SIGFM_AND_TARGET_PPMM_IS_UNKNOWN
CANONICAL_DOCUMENTATION=COMMITTED_AS_924774e9bd7ea10eabdfd540bf8a4be9b8413c99
REVIEW_SET=BASELINE_f609c865f760768edb6a9e404b863ccd0569e1c8_HEAD_924774e9bd7ea10eabdfd540bf8a4be9b8413c99_analysis/D279/D279_01_offline_production_usb_driver_registration_Fedora44_libfprint_1.94.100.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md
```

D279/02 ha poi riesaminato il contratto NBIS 1.94.100 e chiuso la decisione
extractor: `EXTRACTOR_DECISION=NBIS`, senza inventare `ppmm` e senza portare
SIGFM. La registrazione USB production resta il prossimo boundary, non uno
step già eseguito.

### D279/02 — decisione extractor NBIS vs SIGFM per Fedora 44 / libfprint 1.94.100

D279/02 è un step di analisi/decisione, non di integrazione production. Sul
sorgente target `reference/libfprint-fedora44-1.94.100/source` il call-flow
immagine è NBIS-only. `ppmm` influenza solo la quality radius e quella
reliability non entra in Bozorth3. `80x64` supera il blocksize 8. SIGFM non è
necessità target-proven e non è isolabile nel solo driver. La decisione è
quindi NBIS come path nativo a delta minore, classe
`ARCHITECTURAL_TECHNICAL`, validazione biometrica ancora `false`. Report:
`analysis/D279/D279_02_offline_extractor_compatibility_decision_NBIS_vs_SIGFM.md`.

```text
D279_02_OUTCOME=READY
EXTRACTOR_DECISION=NBIS
DECISION_CLASS=ARCHITECTURAL_TECHNICAL
NBIS_PIPELINE_COMPATIBLE=true
NBIS_BIOMETRICALLY_VALIDATED=false
SIGFM_PIPELINE_COMPATIBLE=false
SIGFM_BIOMETRICALLY_VALIDATED=false
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
BIOMETRIC_MATCHER_BENCHMARK_READY=false
NEXT_PRIMARY_BOUNDARY=OFFLINE_FEDORA44_LIBFPRINT_1_94_100_PRODUCTION_USB_DRIVER_REGISTRATION_WITH_NBIS
```
