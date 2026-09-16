<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D279/09 — binding offline della activation production

## Esito

```text
D279_09_OUTCOME=READY_OFFLINE_BOUNDED_NON_ENROLL
ADVANCEMENT=MATERIAL_ARCHITECTURAL_AND_REPOSITORY_ADVANCEMENT
EXECUTABLE_CLOSURE=PASS_OFFLINE_SYNTHETIC_ACTIVATION_AND_FEDORA44_BUILD
REAL_TARGET_COMPATIBILITY=PASS_API_ABI_AND_D279_07_LAYOUT_PREREQUISITES
PRODUCTION_CAPTURE_IDENTIFY_ACTIVATION_GRAPH_WIRED=true
PRODUCTION_ENROLLMENT_ENABLED=false
FPRINTD_OPERATIONAL_PATH_PROVEN=false
REAL_USB_EXECUTION=false
```

Baseline: `81b01731f37b23618413c31e1cde31aeeed1152d` sul branch
`development`.

## Delta implementato

La sottoclasse USB non usa più l'arm in-memory durante una activation
production. Dopo l'open epoch D279/08 avvia lo stesso grafo nativo già chiuso
nei milestone D278:

```text
pre-session RX sync quiet boundary
-> GoodixSecureSession reentry-prefixed
-> TLS 1.2 PSK retained
-> GoodixPostTlsLifecycle bounded a due acquisizioni
```

Il sync RX è obbligatorio anche per la vfunc production. Soltanto il timeout
quiet drenato permette il primo protocol OUT; residue, errori non-timeout,
bound o cancellation falliscono chiuso e completano correttamente la
activation con errore. Dopo la costruzione dei due consumer, secure descriptor
e FDT12 borrowed vengono cancellati dalla glue; l'owner D279/06 resta vivo fino
a `img_close`.

Gli errori asincroni di secure session, post-TLS o receive re-arm ora vengono
instradati al corretto completion point libfprint: `activate_complete(error)`
se l'attivazione non era conclusa, `session_error(error)` se il framework era
già attivo. Il path operator D278 conserva invece la propria osservazione
diretta senza notifiche spurie al framework.

## Gate enrollment

Il source Fedora 44 conferma che `FpImageDevice` mantiene una sola activation
per l'intero enrollment e usa il default di cinque stage. L'evidenza target
locale e il lifecycle nativo arrivano deliberatamente soltanto al secondo B0;
il terzo ciclo non è provato e la policy stage è ancora `NOT_SELECTED`.

D279/09 non riduce quindi gli stage a due, non inventa un terzo ciclo e non
lascia che l'enrollment si blocchi dopo la seconda immagine. La vfunc rifiuta
`FPI_DEVICE_ACTION_ENROLL` con `FP_DEVICE_ERROR_NOT_SUPPORTED` prima di creare
una generation o effettuare qualsiasi submit. Capture/identify possono usare
il grafo bounded già esistente, ma non sono ancora target-eseguiti.

La lifetime cross-activation resta intenzionalmente conservativa: al termine
di una sessione sensor-reaching il contesto viene recintato e il successivo
uso richiede il normale close/open. Non è stato promosso un TLS restart o
resume non provato.

## Verifiche

I test D279/09 esercitano con soli materiali e USB sintetici:

- quiet sync prima di ogni protocol OUT;
- costruzione di secure session e post-TLS lifecycle dalla vfunc reale;
- cancellazione delle view borrowed dopo l'handoff, owner ancora vivo;
- failure sync propagato e open epoch poisoned;
- enrollment rifiutato con zero IN/OUT submit; lo sticky poison ha precedenza
  sul gate di policy e conserva l'errore terminale originario senza nuovi
  submit.

```text
FPIMAGE_DEVICE_NORMAL=24/24_PASS
FPIMAGE_DEVICE_ASAN_UBSAN=24/24_PASS
D278_SECURE_SESSION_REGRESSION=24/24_NORMAL_AND_ASAN_UBSAN_PASS
D278_13_UNAPPROVED_LIVE_ADAPTER_HOST_ONLY_BUILD=PASS
FEDORA44_LIBFPRINT_1_94_100_BUILD=PASS
FEDORA44_STANDARD_REGISTRY=PASS
REAL_PRODUCTION_INPUT_READ_BY_AI=false
REAL_USB_ENUMERATION_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_USB_SUBMIT=0
FPRINTD_EXECUTED=false
```

La prima regressione D278 ha inoltre scoperto che due builder storici linkavano
`goodix_fpimage_device.c` senza tutti i moduli runtime diventati dipendenze nel
D279/08. Il runner secure-session e il builder adapter D278/13 sono stati
corretti aggiungendo binder/target material dove mancanti e i nuovi runtime
inputs/runtime material. Il successivo 24/24 normale/sanitizer e la build
adapter unapproved host-only sono i risultati validi. Non è stato necessario
cambiare il grafo protocollo o abilitare una baseline live.

## Prossimo boundary

Il più piccolo fatto target-specific mancante per un enrollment è sapere se il
release-tail e rearm già validati per la transizione prima→seconda acquisizione
si ripetono correttamente dopo la seconda immagine per raggiungere una terza.
Una prova sensor-reaching richiede un operator kit separato, baseline live
revisionata e autorizzazione one-shot. Solo dopo tale evidenza si potrà
generalizzare il lifecycle e selezionare una policy stage senza usare il
default libfprint come autorità target.

```text
RESIDUAL_BLOCKER_OR_RISK=THIRD_ACQUISITION_TARGET_UNPROVEN;ENROLLMENT_STAGE_POLICY_NOT_SELECTED;CROSS_ACTIVATION_TLS_REUSE_UNPROVEN
NEXT_PRIMARY_BOUNDARY=THIRD_ACQUISITION_TARGET_EVIDENCE
NEXT_LIVE_PREREQUISITE=DEDICATED_OPERATOR_KIT_AI_PM_REVIEW_AND_EXPLICIT_ONE_SHOT_AUTHORIZATION
REVIEW_SET=BASELINE_81b0173_PLUS_FINAL_DEVELOPMENT_COMMIT_PLUS_D279_09_REPORT_PLUS_DRIVER_DIFF_PLUS_MANUAL
```
