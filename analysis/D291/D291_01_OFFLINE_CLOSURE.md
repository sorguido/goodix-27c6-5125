<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D291/01 — correttivo continuità biometrica dopo explicit reopen

## Evidenza live e boundary

La live sulla candidate `8ed02cc3467899c8b1e6f914cc5870e04b6ff4e0`
prova che il lifecycle D291 raggiunge il sensore alla seconda e terza
`VerifyStart`, con una acquisizione esplicita per epoch, TLS=1, drain completo
e zero retry, reset, clear-halt o famiglie persistenti. La precedente failure
`open epoch already consumed` non ricorre.

Le tre VERIFY hanno però dato score zero contro tutti gli otto sample. Il primo
contatto era deliberatamente errato, quindi una regressione della prima epoch
non è provata. Secondo e terzo contatto erano l'indice destro registrato, con
133 e 119 keypoint; D289 aveva già prodotto 9/14/376 e MATCH. Il boundary
correttivo è dunque la comparabilità biometrica dopo reopen, non il transport.

```text
D291_EXPLICIT_SECOND_VERIFY_REACHES_REAL_SENSOR=PROVEN
D291_EXPLICIT_THIRD_VERIFY_REACHES_REAL_SENSOR=PROVEN
D291_ONE_REAL_ACQUISITION_PER_VERIFY_START=PROVEN
D291_NO_HIDDEN_RETRY=PROVEN
D291_REOPEN_LIFECYCLE_TRANSPORT=PROVEN
D291_FIRST_EPOCH_REGRESSION=NOT_PROVEN
```

## Diagnosi del delta D291

Nel delta `02c0cd0952d04ba89655a69926a1bfd713d24b95..8ed02cc`, il nuovo
`goodix_device_context_release_epoch_objects()` puliva e invalidava
`sigfm_baseline`. Il teardown avviene tra due action esplicite, mentre il
`FpImageDevice` resta nello stesso logical open. `context_post_tls_image()`
copiava poi la B0 della nuova sessione in una variabile locale e costruiva il
raster R2 con quella baseline: la nuova probe entrava quindi in uno spazio di
normalizzazione diverso all'interno della stessa serie.

Ownership e lifetime verificati nel codice:

- secure session, TLS, FDT seed/table, material view, claim e generation sono
  per-epoch e vengono correttamente rilasciati/ricreati;
- la B0 di ciascuna nuova sessione è ancora acquisita, decodificata e
  validata, ma non deve sostituire la baseline R2 del logical open;
- il template FP3 è posseduto da libfprint/fprintd, non dal context transport:
  la stessa `FpPrint` viene passata alle action successive e il matcher legge
  gli otto descrittori senza mutarli;
- orientamento, decoder packed-12, raster `80x64 U8` e parametri R2/SIGFM non
  cambiano tra epoch.

Il reopen D291 replica una nuova open a livello transport, non una nuova
`img_open` libfprint. La baseline di normalizzazione era quindi l'unico stato
biometrico con lifetime accorciato dal nuovo teardown.

## Correzione

La prima B0 utile viene fissata in `GoodixDeviceContext` per tutto il logical
open. Le riaperture esplicite consumano normalmente la propria B0 di protocollo
ma usano la baseline R2 fissata; solo `goodix_device_context_free()` la pulisce.
L'audit distingue `sigfm_baseline_pinned=1` nella prima epoch e
`sigfm_baseline_reused=1` nelle successive.

Il fix è consumer-agnostic e soltanto in-memory. Non aggiunge retry, action,
comandi wire o modifiche persistenti. Restano max tre `VerifyStart` di
pam_fprintd, stop al primo MATCH e nessuna quarta acquisizione.

## Gap e rafforzamento dei test

Il vecchio test D291 controllava outcome sintetici tramite
`goodix_test_sigfm_match_set_score()`; inoltre il relativo shell harness non
definiva `GOODIX_LIBFPRINT_SIGFM`, quindi non compilava il percorso production
R2. Poteva provare il lifecycle ma non rilevare perdita di continuità
biometrica.

Il nuovo test `/goodix/d291/biometric-continuity-across-reopen`:

1. genera soltanto raster strutturati non biometrici;
2. attraversa decoder packed-12 e preprocessing R2 production;
3. costruisce otto sample logici e ne controlla l'identità;
4. ottiene NO_MATCH con il pattern errato;
5. cambia deliberatamente la B0 di sessione nella reopen;
6. ottiene MATCH con il pattern iscritto sul reale percorso libfprint di
   confronto;
7. ripete anche NO_MATCH→NO_MATCH→MATCH senza quarta action;
8. verifica dimensioni/formato `80x64 U8`, estrazione non vuota, otto sample e
   template invariato.

La regressione Rocky/OpenCV/SIFT reale, separata dal test double, ottiene score
zero su tutti gli otto confronti errati e score 1504/MATCH sul primo campione
iscritto; la serializzazione FP3 è byte-identica prima e dopo i confronti.

## Kit e stato host

Il launcher esistente `operator_kit/d291-01-multi-verify/run-d291-01.sh`
calcola un path assoluto prima di `pkexec`, eliminando la failure osservata con
`$0` relativo. Accetta MATCH al secondo contatto oppure, solo dopo un secondo
NO_MATCH, al terzo; verifica pin/reuse della baseline e conserva tutti i gate
factory-preserving e il rollback.

Non esiste evidenza disponibile che il rollback della live fallita sia
completato:

```text
HOST_RUNTIME_AFTER_FAILED_D291=UNKNOWN_TO_AI
```

Per questo la prossima run esegue prima del deployment un audit read-only di
state, runtime, manifest e PAM correnti e si ferma su drift.

## Verifica offline

```text
FULL_DRIVER_NORMAL=29/29 PASS
FULL_DRIVER_ASAN_UBSAN=29/29 PASS
REAL_ROCKY_OPENCV_SIGFM_R2=PASS
D291_WRONG_THEN_ENROLLED=NO_MATCH_THEN_MATCH
D291_TEMPLATE_SAMPLES=8
D291_TEMPLATE_IDENTITY_ACROSS_MATCH=PASS
D285_D286_OFFLINE_CONTRACT=64/64 PASS
D291_OPERATOR_KIT_CONTRACT=13/13 PASS
PRODUCTION_BUILD_WITHOUT_TEST_SEAMS=PASS
PRODUCTION_ABI_PREFLIGHT=PASS
REAL_USB_ACCESS=0
REAL_SENSOR_ACCESS=0
FACTORY_PRESERVING=true
```

## Decisione PM

Il correttivo offline è completo; la validazione finale è sensor-reaching e
privilegiata e resta un singolo Human Gate operatore. Tentativo 1 dito errato,
tentativo 2 indice destro registrato e stop al MATCH; il terzo è consentito
solo se il secondo è NO_MATCH.

```text
ROOT_CAUSE_IDENTIFIED=true
CORRECTIVE_IMPLEMENTED=true
BIOMETRIC_CONTINUITY_TEST_ADDED=true
FULL_OFFLINE_REGRESSION=PASS
PM_DECISION=HUMAN_REQUIRED
LIVE_VALIDATION_REQUIRED=true
```
