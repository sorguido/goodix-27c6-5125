<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/30 — recovery del primo enrollment Linux live

## Esito PM

La run D279/29 è accettata come evidenza target-local autentica della baseline
`f4f0436acb887d9724a0ee77b51975fe3e072f44`. I due output sanitizzati forniti
dall'operatore sono preservati byte-identici in
`captures/D279_29/D27929_20260906_LIVE/sanitized/` e verificati ai digest:

```text
operator.log  85348fe527e5d2373734fa288604c7a569ec1f3e5bc61c10acf8952a83178727
summary.env   9a7c9ff13976e324f3eaa6cb2f3b0628bbf36ce5467a876eea94ddd35022a9fb
```

La singola autorizzazione è consumata. Non esiste autorizzazione per retry,
seconda action o nuova esecuzione live.

## Evidenza prodotta

Il percorso production ha identificato un solo driver target, completato open,
sessione secure, handshake TLS e la prima acquisizione primaria B0. Il raster
è arrivato al vero extractor NBIS di libfprint 1.94.100, che ha restituito
`No minutiae found` prima del primo avanzamento enrollment. Il client ha
cancellato la stessa action senza retry e ha chiuso il device.

```text
TARGET_DRIVER_MATCH_COUNT=1
OPEN_SUCCEEDED=true
ACTION_ATTEMPT_COUNT=1
AUDIT_TLS_HANDSHAKE_COUNT=1
AUDIT_ENROLL_EVENT_PRIMARY_B0_COUNT=1
COMPLETED_STAGE_COUNT=0
PROGRESS_ERROR_COUNT=1
CLOSE_SUCCEEDED=true
```

Questo chiude come live-proven il collegamento minimo del primo raster dal
percorso USB production a NBIS. Non prova che il dito sia stato posizionato in
modo errato e non consente di attribuire il failure all'operatore.

## Safety e limiti epistemici

I contatori osservati confermano zero retry, zero seconda action, zero reopen,
zero reset/clear-halt e zero famiglie persistenti note. Backend e OUT sono
drenati, il claim non è più attivo, l'owner è liberato e il secret TLS è
azzerato. Queste sono proprietà host-side osservate: non dimostrano quiescenza,
timeout o assenza di persistenza sensor-side.

Il failure localizza il nuovo confine nella rappresentazione/qualità biometrica
del primo raster. Il codice eseguito applica il mapping fisso
`round(sample*255/4095)`, non normalizza rispetto al range del frame e usa
`flags=0`. Restano realmente indistinguibili con la telemetria corrente:

- contrasto insufficiente dopo il mapping full-range;
- polarità errata;
- orientamento errato;
- insufficienza intrinseca di NBIS sulla particolare immagine 80×64;
- qualità fisica del contatto.

Il test D279/27 su fixture sintetica provava soltanto la meccanica dell'action
NBIS e produceva tre minutiae; non è evidenza biometrica APP12509 e non chiude
nessuna delle ipotesi sopra.

## Confine offline successivo

Il prossimo lavoro deve prima verificare se il pcapng OEM ATTEMPT02 già
preservato consente una ricostruzione in memoria, privacy-preserving, di raster
reali e il confronto controllato di mapping/polarità/orientamento senza nuova
azione sul sensore. Il traffico applicativo è TLS 1.2 PSK cifrato: la fattibilità
può essere studiata offline, ma l'accesso al PSK/protected material resta un
Human Gate separato e non è autorizzato da D279/30.

Non va modificato il mapping production sulla sola base di `No minutiae found`.
Se il percorso ATTEMPT02 non è eseguibile senza materiale protetto, il delta
autonomo consentito si limita alla progettazione/verifica sintetica di un
evaluator che non persista raster, template, plaintext o secret; la sua
esecuzione autentica dovrà fermarsi al relativo Human Gate.

```text
OUTCOME=READY_POST_LIVE_EVIDENCE_CLOSED
ADVANCEMENT=NEW_TARGET_REAL_PRODUCTION_USB_TO_NATIVE_NBIS_BOUNDARY_REACHED
EXECUTABLE_CLOSURE=NOT_APPLICABLE_EVIDENCE_INTEGRATION
LIVE_RESULT=FAIL_CLOSED_NO_MINUTIAE_FIRST_STAGE
LIVE_AUTHORIZATION_CONSUMED=true
D279_29_RERUN_AUTHORIZED=false
PRODUCTION_USB_TO_FIRST_PRIMARY_B0_LIVE_PROVEN=true
PRODUCTION_FIRST_RASTER_TO_NATIVE_NBIS_LIVE_PROVEN=true
TARGET_REAL_MINUTIAE_COUNT=0
OPERATOR_ERROR_PROVEN=false
HOST_CLEANUP_OBSERVED=true
KNOWN_PERSISTENT_FAMILY_OBSERVED_COUNT=0
SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN=false
DEVICE_SIDE_TIMEOUT_OR_QUIESCENCE_INFERRED=false
RESIDUAL_BLOCKER_OR_RISK=REAL_RASTER_CONTRAST_POLARITY_ORIENTATION_NBIS_SUITABILITY_AND_CONTACT_QUALITY_UNRESOLVED
NEXT_PRIMARY_BOUNDARY=OFFLINE_ATTEMPT02_PRIVACY_PRESERVING_RASTER_RECONSTRUCTION_FEASIBILITY
CURRENT_LIVE_AUTHORIZED=false
```
