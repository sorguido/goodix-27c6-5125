<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D282/01 — closure offline VERIFY e readiness fprintd target

## Decisione

```text
OUTCOME=READY_OFFLINE_PENDING_INDEPENDENT_AI_PM_REVIEW
ADVANCEMENT=REAL_FPRINTD_VERIFY_PATH_IMPLEMENTED_AND_TARGET_OPERATOR_BOUNDARY_PREPARED
EXECUTABLE_CLOSURE=PASS_OFFLINE_EXACT_FPRINTD_ABI_REAL_SIGFM_AND_SANITIZERS
RESIDUAL_BLOCKER_OR_RISK=TARGET_FPRINTD_STORAGE_SAME_DIFFERENT_FINGER_AND_SYSTEM_STAGING_REQUIRE_A_NEW_HUMAN_GATE
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
D282_01_HUMAN_GATE_READINESS=READY
```

Questa decisione significa che i blocker pre-live sono chiusi offline e che il
kit può essere sottoposto a review indipendente. Non approva una baseline, non
crea un grant e non autorizza installazione privilegiata, USB o live.

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

## Staging e storage reversibili

Il kit `operator_kit/d282-01-fprintd-target/` costruisce da `git archive` del
full SHA, con RPM OpenCV locali hash-pinned e network namespace disabilitato.
Controlla la NEVRA fprintd, i 47 simboli ABI richiesti, SONAME, RPATH, driver
registry e assenza di test seam/reset/clear-halt/persistent symbol. La libreria
di sistema non viene modificata: una wrapper sotto `/run` imposta
`LD_LIBRARY_PATH` e `STATE_DIRECTORY`; un drop-in sotto `/run/systemd/system`
sostituisce temporaneamente soltanto `ExecStart`. `/proc/<pid>/maps` deve
confermare la candidate esatta.

Prima di ogni mutazione il kit registra unit, stato active/inactive, hash della
libreria di sistema e inventario read-only di `/var/lib/fprint` con metadata,
SHA-256 e label SELinux. Lo storage futuro è un root D282 univoco e isolato
sotto `/var/lib/fprint`, così fprintd attraversa il layout production senza
confondere o sovrascrivere template personali. Il trap è installato prima
della prima scrittura di staging; rimuove solo nomi D282 esatti, ripristina il
servizio e confronta byte/metadata preesistenti. Ogni mismatch di rollback è
FAIL con recovery esplicita e nessuna action ulteriore.

Il correttivo pre-Human-Gate mantiene D282/01 e separa validazione da consumo
del grant. Il launcher valida prima formato, baseline, operation, ID, owner,
mode e utente; completa poi tooling, collisioni, stato fprintd, libreria/hash,
precondizioni SELinux, creazione del result sink, snapshot della unit e
inventario storage. Il trap è attivo prima degli ultimi due controlli. Solo
dopo il PASS completo prepara il namespace one-shot e acquisisce con `mkdir`
atomica il claim; imposta immediatamente `GRANT_CONSUMED=true` e passa allo
staging. Non resta alcun probe `command -v`/`getenforce` dopo il consumo.

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
inventari e ogni FP3 autentico restano in `private/` e
`TEMPLATE_INCLUDED_IN_EXPORT=false`.

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

Esecuzioni di closure:

- `analysis.D282.test_d282_01_offline_contract`: **30/30 PASS**;
- `analysis.D281.test_d281_01_fprintd_storage_integration`: **6/6 PASS**;
- integrazione D281 con vero daemon/client, bus privato e USB compile-disabled:
  **PASS**;
- suite D278/D279/D280 production-shaped: **26/26 PASS normal** e
  **26/26 PASS ASan/UBSan**;
- build Fedora 44/libfprint 1.94.100 con vero SIGFM/OpenCV, stage 8, FP3,
  identify e VERIFY same-template: **PASS**;
- standard driver registry e ABI esatto fprintd: **PASS**;
- preflight aggregato del kit: **PASS**.

Il different-finger è deliberatamente solo sintetico offline. Non viene
dichiarata una soglia FAR/FRR. Soltanto una futura Human Gate può elevare
`DIFFERENT_FINGER_NO_MATCH=OBSERVED_LIVE`.

## Self-review e stop point

Il percorso futuro è stato riesaminato da CLI → D-Bus → fprintd → API
libfprint → core FpImageDevice/SIGFM → driver Goodix. VERIFY non introduce
protocollo rispetto all'IDENTIFY D280 target-proven. Ogni retry è bounded dal
fence prima del sensore. A e B sono auditati prima di avanzare; ogni failure
attiva rollback, senza ripetere enrollment. Stato preesistente e libreria di
sistema sono confrontati dopo cleanup. Non compare alcuna modifica PAM.

Resta necessaria una review AI-PM indipendente dell'esatto commit finale prima
di una eventuale richiesta di Human Gate. D283/PAM non è preparato.

```text
D282_01_GRANT_ORDERING_CORRECTIVE=PASS
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
