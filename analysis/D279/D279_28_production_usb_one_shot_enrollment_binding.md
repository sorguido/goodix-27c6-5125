# D279/28 — binding enrollment USB production one-shot

## Esito

`READY_OFFLINE`. La action enrollment della sottoclasse USB production è
collegata al grafo target-local a 21 stage attraverso secure session, TLS e
backend USB già esistenti. Nessuna esecuzione live o operazione privilegiata è
stata effettuata.

## Delta runtime

- `production_activation_start_secure_graph()` configura il grafo enrollment
  solo quando l’action corrente è `FPI_DEVICE_ACTION_ENROLL`;
- il grafo riceve A0 dal router unico e B0 plaintext soltanto dal callback TLS
  post-handshake; il B0 ausiliario resta opaco;
- il primo tentativo production consuma l’open epoch anche in caso di failure;
  ogni seconda action è respinta prima di generation e submit, imponendo
  close/reopen;
- la allowlist first-live respinge qualunque action production diversa da
  enrollment prima di generation e submit;
- gli audit runtime espongono secure/TLS/post-TLS/enrollment/binding e il
  conteggio degli ausiliari;
- le API di open/submit/receive/operator-epoch usate dai transcript sintetici
  sono compilate solo con `GOODIX_ENABLE_TEST_SEAMS`. La libreria target non ne
  contiene i simboli.

Non sono stati aggiunti retry, reopen automatici, reset, clear-halt, comandi di
recovery, fprintd, verify/PAM o packaging/install-tree.

## Prove offline

Il test production-shaped usa un `FpDevice` USB tipizzato ma sostituisce sia i
materiali sia il trasporto con seam sintetiche. Percorre:

1. open e claim sintetici;
2. completamento della deadline pre-session RX senza byte;
3. protocollo secure pre-D1;
4. handshake TLS 1.2 PSK reale;
5. bootstrap D4/AF/FDT;
6. 21 stage completi attraverso il binding USB;
7. 21 progress e un completion libfprint;
8. rifiuto di una seconda action senza nuovi submit;
9. close, release e distruzione dell’owner.

La suite secure-session, corretta anche nella propria source closure per
linkare i moduli enrollment già richiesti da `goodix_fpimage_device.c`, passa
25/25 normale e 25/25 ASan/UBSan. La suite FpImageDevice passa 28/28 normale e
sanitizer. La build/registry Fedora 44/libfprint 1.94.100 passa; l’audit `nm`
conferma l’assenza delle seam host-only dall’artefatto production. Il test
D279/27 sullo stesso target continua a percorrere l’action con NBIS nativo per
21 stage, normale e ASan/UBSan.

```text
PRODUCTION_USB_TYPED_SYNTHETIC_ACTION=PASS
PRODUCTION_ONE_SHOT_ENROLLMENT_FULL_TLS=PASS
PRODUCTION_OPEN_EPOCH_ACTION_MAX=1
PRODUCTION_ACTION_ALLOWLIST=ENROLL_ONLY
SECOND_ACTION_SUBMIT_COUNT=0
SECURE_HANDSHAKE_COUNT=1
ENROLLMENT_PROGRESS_COUNT=21
LIBFPRINT_COMPLETION_COUNT=1
HOST_ONLY_TRANSCRIPT_SEAMS_IN_PRODUCTION_LIBRARY=false
REAL_USB_ENUMERATION_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_USB_CLAIM_COUNT=0
REAL_USB_SUBMIT=0
LIVE_EXECUTION_PERFORMED=false
```

## Interpretazione dei guardrail

Le deadline sono soltanto limiti di attesa/sicurezza host-side. Una completion
di timeout senza byte non dimostra timeout semantico, readiness o quiescenza
device-side; dopo un’interruzione non è consentito inferire che il sensore sia
inattivo.

Il serializer enrollment accetta esclusivamente i control
`0x20/0x22/0x32/0x34/0x36/0x50`. Il conteggio zero per le famiglie persistenti
note è un guardrail sull’allowlist del sender. Non prova che nessuno dei comandi
ammessi, né il percorso complessivo, possa avere un effetto persistente interno
non ancora compreso.

## Confini residui

- qualità/polarità/orientamento e sufficienza biometrica delle immagini reali;
- comportamento reale del sensore lungo il grafo completo;
- eventuali effetti sensor-side non visibili dalla sola classificazione delle
  famiglie note;
- stato device-side dopo interruzione;
- robustezza multi-action/cancel/reactivation nello stesso open epoch;
- packaging, fprintd, verify/PAM e install-tree.

I primi tre confini non sono ulteriormente risolvibili con transcript
sintetici. Il prossimo step metodologico è una review live-critical separata,
seguita dal kit operatore one-shot e da un Human Gate su SHA completo. Nessuna
run live è autorizzata da questo report.

```text
OUTCOME=READY_OFFLINE
ADVANCEMENT=MATERIAL_ARCHITECTURAL_AND_EXECUTABLE_PRODUCTION_BINDING
EXECUTABLE_CLOSURE=PASS_OFFLINE_SYNTHETIC_FULL_PRODUCTION_GRAPH
RESIDUAL_BLOCKER_OR_RISK=FIRST_HARDWARE_ENROLLMENT_EVIDENCE_REQUIRES_EXPLICIT_ONE_SHOT_HUMAN_GATE
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md
REVIEW_SET=GIT_NATIVE_D279_28_DIFF
CURRENT_LIVE_AUTHORIZED=false
```
