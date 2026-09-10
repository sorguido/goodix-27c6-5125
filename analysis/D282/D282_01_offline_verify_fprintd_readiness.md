<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/01 — attempt 01 e correttivo staging fprintd target

## Decisione

```text
OUTCOME=CORRECTIVE_IMPLEMENTED_OFFLINE_BLOCKED_ON_PRIVILEGED_SYSTEMD_SELINUX_TEST
ADVANCEMENT=ATTEMPT_01_NORMALIZED_DIRECT_SYSTEMD_EXEC_DESIGNED_AND_EXIT_TRAP_SCOPE_FIXED
EXECUTABLE_CLOSURE=PARTIAL_OFFLINE_SYSTEMD_PARSER_AND_REAL_BASH_TRAP_PASS_RUNTIME_START_NOT_RUN
RESIDUAL_BLOCKER_OR_RISK=REAL_SYSTEMD_FPRINTD_START_WITH_SELINUX_ENFORCING_REQUIRES_SEPARATE_PRIVILEGED_HOST_ONLY_AUTHORIZATION
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
D282_01_HUMAN_GATE_READINESS=NOT_READY
```

Il correttivo è implementato e verificato per quanto consentito offline, ma il
blocker systemd/SELinux non può essere dichiarato chiuso senza avviare il vero
servizio di sistema con il vero drop-in. Questa operazione richiede privilegi
e un'autorizzazione separata; non è stata eseguita. Il kit non è quindi pronto
per una nuova Human Gate biometrica, non approva una baseline e non crea grant.

## Attempt 01: esito autentico normalizzato

La prima Human Gate D282/01 sulla baseline
`54b6eb3002d1afacbb5331e0dbd33761f8865bca` è chiusa come failure host-side:
il grant one-shot è stato consumato, ma `fprintd` non ha superato l'exec del
wrapper e nessuna azione biometrica o sensor-reaching è iniziata. Il journal
fornito dall'operatore riporta `launch-fprintd: /usr/libexec/fprintd: Permesso
negato` e `status=126`. Il trap `EXIT` ha poi dereferenziato
`service_touched`, variabile locale già fuori scope.

L'evidenza è normalizzata in
`D282_01_ATTEMPT_01_NORMALIZED.env` e
`D282_01_attempt_01_host_staging_failure.md`. Il result raw sotto `/var/tmp` è
root-only e non è stato letto o copiato, coerentemente con il divieto corrente
di sudo/root; i marker non direttamente leggibili sono quindi esplicitamente
`USER_ATTESTED`. La verifica host read-only ha confermato l'assenza corrente
del drop-in e lo stato systemd recuperato. Nessuna proprietà biometrica viene
elevata:

```text
D282_01_ATTEMPT_01_SENSOR_PROTOCOL_RESULT=NOT_REACHED
D282_01_ATTEMPT_01_BIOMETRIC_RESULT=NOT_REACHED
D282_01_ATTEMPT_01_HOST_STAGING_RESULT=FAIL
D282_01_ATTEMPT_01_GRANT_CONSUMED=true
D282_01_ATTEMPT_01_RETRY_AUTHORIZED=false
```

## Sorgente fprintd esatto e root cause VERIFY

La macchina installa `fprintd-1.94.5-5.fc44.x86_64`. È stato scaricato senza
installazione l'esatto SRPM Fedora 44 e importato come reference immutata in
`reference/fprintd-fedora44-1.94.5/`:

```text
SRPM_SHA256=886d192ad57e52d3f953e86d78ba72b389bc09d433d6ff999421542ea381f292
SOURCE_TAR_SHA256=a026ef34c31b25975275cc29a5e4eba2b54524769672095a5228098a08acd82c
SPEC_SHA256=b87b2786e5b4b0e69735ac0c3a8bab6ad1f5393660f738d5d052d62bb3ebadbd
FEDORA_PATCH_DIRECTIVE_COUNT=0
```

Lo spec usa `%autosetup -S git` senza `Patch`, `%patch` o `%autopatch`. Nel
percorso `VerifyStart`, `finger=any` carica la gallery. Zero print fallisce
prima dell'action; un solo print seleziona il suo dito; più print possono usare
IDENTIFY. Dopo la selezione del singolo dito, fprintd carica il template e
chiama `fp_device_verify()`. Il gap era quindi duplice: la classe
`FpImageDevice` Fedora non registrava VERIFY e il Goodix production lo
respingeva; una semplice allowlist avrebbe inoltre scelto il vecchio profilo a
due acquisizioni.

La correzione registra VERIFY sulla capture action, comprende VERIFY in
cancellation/completion/state assertions, estrae un probe SIGFM, lo confronta
con lo specifico template di `fpi_device_get_verify_data()`, invia match/no-
match/retry con `fpi_device_verify_report()` e completa con
`fpi_device_verify_complete()`. Il controllo newer-core del scanned print
tratta SIGFM come l'altro tipo matcher-backed NBIS. Nel driver VERIFY condivide
esattamente `GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION` con IDENTIFY;
nessun wire command, lifecycle o protocollo nuovo è stato aggiunto.

## Retry e failure path

Nel sorgente esatto, `verify_cb()` richiama automaticamente
`fp_device_verify()` quando riceve `FP_DEVICE_RETRY`, senza effettuare open o
close. Il controllo scelto conserva il risultato retryable verso fprintd ma
marca la prima activation production come consumata. Ogni secondo dispatch
nella medesima open epoch incrementa attempt/rejected e fallisce prima di
generation, secure session, TLS o submit USB.

Il test production-shaped induce un errore di extraction dopo una sola
acquisizione, osserva una callback retry, simula il richiamo fprintd ed esige:

```text
production_action_attempt_count=2
production_rejected_action_count=1
tls_handshake_count=1
SECOND_SENSOR_REACHING_ACTION_COUNT=0
```

Match e no-match completano entrambi con una callback, un'acquisizione,
`single_acquisition_terminal_count=1` e zero re-arm. La cancellazione è
provata dopo handshake con receive pendente: l'azione termina `CANCELLED`, il
backend è drenato e retry/reopen/reset/clear-halt restano zero. Un secondo
VerifyStart inatteso usa lo stesso fence. Un nuovo open epoch è possibile solo
dopo close esplicito; non è prodotto dal callback retry.

L'enrollment ha un contratto diverso e più stretto: otto acquisizioni
sensor-side massime, senza contatto sostitutivo. La policy interna
`enroll_processing_fail_closed` è abilitata soltanto dalla sottoclasse USB
Goodix production. Se extraction o processing del template falliscono dopo
una acquisizione consumata, il core restituisce
`FP_DEVICE_ERROR_DATA_INVALID`, deattiva e completa terminalmente senza
inoltrare `FP_DEVICE_RETRY`. La regressione induce il failure allo stage 3:
tre stage sensor-side risultano consumati, soltanto due rearm precedenti,
nessun nuovo `AWAIT_FINGER_ON`, nessun quarto contatto, nessun submit
successivo, callback retry zero e backend drenato. Il launcher aggiunge una
seconda fence e rifiuta il successo se `fprintd-enroll` mostra marker
`enroll-retry-*`.

## Staging e storage reversibili

Il kit `operator_kit/d282-01-fprintd-target/` costruisce da `git archive` del
full SHA, con RPM OpenCV locali hash-pinned e network namespace disabilitato.
Controlla la NEVRA fprintd, i 47 simboli ABI richiesti, SONAME, RPATH, driver
registry e assenza di test seam/reset/clear-halt/persistent symbol. La libreria
di sistema non viene modificata. Il wrapper che ha fallito nell'attempt 01 è
stato eliminato: il drop-in sotto `/run/systemd/system` mantiene
`ExecStart=/usr/libexec/fprintd`, imposta `LD_LIBRARY_PATH` e
`FP_DRIVERS_ALLOWLIST`, e usa `StateDirectory=fprint/.goodix-d282-01-*` per
ottenere il `STATE_DIRECTORY` isolato tramite systemd. In questo modo il primo
exec resta quello normale etichettato `fprintd_exec_t`; non esiste più il
doppio exec dal wrapper sotto `/run`. `/proc/<pid>/exe` deve essere esattamente
`/usr/libexec/fprintd` e `/proc/<pid>/maps` deve contenere la candidate esatta.

Prima di ogni mutazione il kit registra unit, stato active/inactive, hash della
libreria di sistema e inventario read-only di `/var/lib/fprint` con metadata,
SHA-256 e label SELinux. Lo storage futuro è un root D282 univoco e isolato
sotto `/var/lib/fprint`, così fprintd attraversa il layout production senza
confondere o sovrascrivere template personali. Il trap è installato prima
della prima scrittura di staging; rimuove solo nomi D282 esatti, ripristina il
servizio e confronta byte/metadata preesistenti. Ogni mismatch di rollback è
FAIL con recovery esplicita e nessuna action ulteriore.

Il trap non è più una funzione annidata che dipende dai `local` di
`run_authorized_live()`: `cleanup_live()` è top-level e tutto lo stato di
rollback ha nomi globali `live_*`, inizializzati fail-closed prima di armare il
trap. Una regressione avvia un vero sottoprocesso Bash, entra in una funzione,
arma `EXIT`, provoca `return 41` sotto `set -e` e verifica rimozione di runtime,
drop-in e storage sintetico, summary di failure e assenza di `unbound variable`.

Il correttivo pre-Human-Gate mantiene D282/01 e separa validazione da consumo
del grant. Il launcher valida prima formato, baseline, operation, ID, owner,
mode e utente; completa poi tooling, collisioni, stato fprintd, libreria/hash,
precondizioni SELinux, creazione del result sink, snapshot della unit e
inventario storage. Il trap è attivo prima degli ultimi due controlli. Solo
dopo questi controlli conta passivamente le entry esatte `27c6:5125` in
`/sys/bus/usb/devices`: zero o più di una rifiutano con il conteggio osservato,
grant intatto, zero enumerazione attiva e zero live. Dopo il PASS completo
prepara il namespace one-shot e acquisisce con `mkdir` atomica il claim;
imposta immediatamente `GRANT_CONSUMED=true` e passa allo staging. Il
controllo ripetuto dopo lo start di fprintd resta come fence anti-TOCTOU. Non
resta alcun probe `command -v`/`getenforce` dopo il consumo.

La futura sequenza usa un grant composto per evitare che un errore host-side
dopo enrollment obblighi a ripetere otto contatti. Le phase A/B/C sono gated
in ordine. Sono autorizzabili al massimo tre azioni biometriche in tre open
epoch: enrollment, same-finger verify e different-finger verify. Il client
`fprintd-delete` aggiunge un quarto `Claim/Release` osservabile, ma il Goodix
non espone `FP_DEVICE_FEATURE_STORAGE`: il sorgente fprintd elimina soltanto
lo storage host e non chiama una delete sensor-side. Il report distingue
quindi open epoch e action consumate. Tutti i contatori finali sono calcolati
dai log, non stampati come esito predefinito.

L'export contiene soltanto `operator.log` e `summary.env` byte-identici. Gli
inventari restano in `private/`; l'FP3 autentico rimane esclusivamente nello
storage D282 isolato durante A/B, viene eliminato in C o dal rollback e non è
copiato in `private/`. `TEMPLATE_INCLUDED_IN_EXPORT=false`.

## Matrice obbligatoria e risultati

| # | Contratto | Evidenza offline | Esito |
|---:|---|---|---|
| 1 | one-print fprintd → VERIFY | sorgente esatto 1.94.5 | PASS |
| 2 | VERIFY Goodix single acquisition | profilo production + test | PASS |
| 3 | SIGFM same-template match | core Fedora con SIGFM reale | PASS |
| 4 | SIGFM different-template no-match | core Fedora/SIGFM reale, due raster sintetici distinti | PASS_OFFLINE_SYNTHETIC |
| 5 | IDENTIFY non regredisce | action Fedora + production-shaped | PASS |
| 6 | enrollment non regredisce | stage 8 Fedora + D278 production | PASS |
| 7 | extraction retry senza seconda action | failure injection | PASS |
| 8 | callback retry fprintd senza nuova USB/TLS | sorgente esatto + fence | PASS |
| 9 | FP3 malformato | D281 reale + parser strict | PASS |
| 10 | FP3 mancante | lookup fprintd fail-before-action | PASS |
| 11 | wrong user/finger | store lookup e client precheck | PASS |
| 12 | close/open/restart | D280 + flow kit | PASS |
| 13 | cancellation VERIFY | action-shaped post-TLS | PASS |
| 14 | daemon restart | D281 reale + flow kit | PASS |
| 15 | cleanup completo | modello e trap bounded | PASS |
| 16 | rollback staging | modello deterministico | PASS |
| 17 | failure intermedi | runtime/drop-in/storage injected | PASS |
| 18 | pre-existing storage | sentinel byte/metadata-preserved | PASS |
| 19 | no retry/reopen/reset/clear-halt nascosti | audit + symbol/test | PASS |
| 20 | no persistent family fuori allowlist vuota | audit + build gate | PASS |
| 21 | ordine gate → claim atomico → staging | audit strutturale launcher | PASS |
| 22 | collisione staging non consuma grant | modello + sorgente | PASS |
| 23 | stato fprintd unsafe non consuma grant | modello + sorgente | PASS |
| 24 | libfprint di sistema mancante non consuma grant | modello + sorgente | PASS |
| 25 | snapshot unit fallito non consuma grant | modello + sorgente | PASS |
| 26 | inventario storage fallito non consuma grant | modello + sorgente | PASS |
| 27 | precondizione SELinux fallita non consuma grant | modello + sorgente | PASS |
| 28 | grant malformed/baseline/operation/user errati pre-consumo | modello + sorgente | PASS |
| 29 | claim one-shot impedisce riuso | modello + `mkdir` atomica | PASS |
| 30 | failure post-consumo: rollback, zero retry; flow invariato | modello + sorgente | PASS |
| 31 | target assente contato passivamente | sysfs sintetico | PASS |
| 32 | target multiplo contato passivamente | sysfs sintetico | PASS |
| 33 | cardinalità esatta uno accettata | sysfs sintetico | PASS |
| 34 | gate cardinalità prima del claim atomico | modello + audit launcher | PASS |
| 35 | controllo cardinalità post-start preservato | audit launcher anti-TOCTOU | PASS |
| 36 | extraction enrollment intermedia terminale solo Goodix production | action-shaped stage 3 | PASS |
| 37 | marker enrollment retry rifiutato prima del restart | audit launcher | PASS |
| 38 | trap EXIT sopravvive all'uscita dallo scope funzione | vero sottoprocesso Bash, failure 41 e rollback | PASS |
| 39 | drop-in direct-exec production-shaped e sintassi systemd | helper reale + `systemd-analyze verify` | PASS_OFFLINE_PARSER |
| 40 | attempt 01 normalizzata senza claim biometrici | env/report canonici + provenance | PASS |
| 41 | assenza di prova runtime SELinux non mascherata | stato canonico fail-closed | PASS |

Esecuzioni di closure:

- `analysis.D282.test_d282_01_offline_contract`: **41/41 PASS**;
- `analysis.D281.test_d281_01_fprintd_storage_integration`: **6/6 PASS**;
- integrazione D281 con vero daemon/client, bus privato e USB compile-disabled:
  **PASS**;
- suite D278/D279/D280/D282 production-shaped: **27/27 PASS normal** e
  **27/27 PASS ASan/UBSan**;
- build Fedora 44/libfprint 1.94.100 con vero SIGFM/OpenCV, stage 8, FP3,
  identify e VERIFY same-template: **PASS**;
- standard driver registry e ABI esatto fprintd: **PASS**;
- preflight aggregato del kit: **PASS offline**.

Il test 39 prova la generazione del vero drop-in e la sua accettazione dal
parser systemd, non l'avvio del servizio. Non sono stati eseguiti
`systemctl start`, installazioni in `/run/systemd/system`, accessi USB o driver
target. Pertanto restano deliberatamente:

```text
FPRINTD_SYSTEMD_STAGING_START=NOT_RUN_REQUIRES_SEPARATE_PRIVILEGED_AUTHORIZATION
SELINUX_EXEC_DENIAL=NOT_PROVEN_CORRECTED
EXACT_LIBRARY_MAP_VERIFIED=NOT_OBSERVED_FOR_CORRECTIVE
```

Il different-finger è deliberatamente solo sintetico offline. Non viene
dichiarata una soglia FAR/FRR. Soltanto una futura Human Gate può elevare
`DIFFERENT_FINGER_NO_MATCH=OBSERVED_LIVE`.

## Self-review e stop point

Il percorso futuro è stato riesaminato da CLI → D-Bus → fprintd → API
libfprint → core FpImageDevice/SIGFM → driver Goodix. VERIFY non introduce
protocollo rispetto all'IDENTIFY D280 target-proven. Il retry VERIFY è bounded
dal fence prima del sensore; un processing failure enrollment è invece
terminale già dopo l'acquisizione consumata. A e B sono auditati prima di avanzare; ogni failure
attiva rollback, senza ripetere enrollment. Stato preesistente e libreria di
sistema sono confrontati dopo cleanup. Non compare alcuna modifica PAM.

Il prossimo passo non è una nuova run biometrica: serve prima una verifica
host-only separatamente autorizzata del vero avvio systemd con SELinux
Enforcing, USB target non raggiungibile, seguita da review indipendente. Fino a
quel momento la readiness resta `NOT_READY`. D283/PAM non è preparato.

```text
D282_01_GRANT_ORDERING_CORRECTIVE=PASS
D282_01_TARGET_CARDINALITY_PRECONSUMPTION_GATE=PASS
D282_01_ENROLLMENT_IMPLICIT_RETRY_FENCE=PASS
D282_01_ATTEMPT_01=FAIL_HOST_STAGING_CLOSED
D282_01_ATTEMPT_01_GRANT_CONSUMED=true
D282_01_ATTEMPT_01_RETRY_AUTHORIZED=false
D282_01_EXIT_TRAP_SCOPE_CORRECTIVE=PASS
EXIT_TRAP_LOCAL_SCOPE_REGRESSION=PASS
UNBOUND_VARIABLE_DURING_CLEANUP=false
D282_01_SYSTEMD_DIRECT_EXEC_DESIGN=PASS_OFFLINE_STATIC_AND_SYSTEMD_PARSER
D282_01_SYSTEMD_SELINUX_STAGING_CORRECTIVE=IMPLEMENTED_PENDING_PRIVILEGED_HOST_TEST
FPRINTD_SYSTEMD_STAGING_START=NOT_RUN_REQUIRES_SEPARATE_PRIVILEGED_AUTHORIZATION
SELINUX_EXEC_DENIAL=NOT_PROVEN_CORRECTED
D282_01_HUMAN_GATE_READINESS=NOT_READY
EXTRA_ENROLLMENT_CONTACT_REQUESTED=false
PRECONSUMPTION_REFUSALS_LEAVE_GRANT_UNUSED=true
POSTCONSUMPTION_FAILURE_RETRY_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
CURRENT_PRIVILEGED_INSTALL_AUTHORIZED=false
APPROVED_BASELINE=NONE
GRANT_CREATED=false
REAL_USB_ENUMERATION_ATTEMPTED=false
LIVE_EXECUTION_PERFORMED=false
PAM_IN_SCOPE=false
```
