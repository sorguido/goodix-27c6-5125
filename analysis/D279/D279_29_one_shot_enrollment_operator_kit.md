# D279/29 — operator kit enrollment production one-shot

## Esito

`READY_FOR_HUMAN_GATE`. Il percorso offline necessario alla prima action
enrollment reale è chiuso; nessuna enumerazione USB, lettura di materiale
protetto, operazione privilegiata o run live è stata eseguita.

La review PM separata del commit D279/28 ha accettato il live-critical set:
registry Fedora 44/libfprint 1.94.100, open/claim production, secure session,
TLS, bootstrap post-TLS, grafo enrollment a 21 stage, sender allowlisted,
pipeline NBIS e close/release. Ha inoltre verificato esplicitamente che:

- le seam di open/submit/receive/operator epoch usate dai transcript sintetici
  non sono presenti nella libreria production;
- i deadline sono safety bound host-side e non dimostrano timeout o quiescenza
  device-side;
- zero famiglie persistenti note nell'allowlist è un vincolo del sender, non
  prova l'assenza di persistenza sensor-side ignota.

## Kit

Il kit è in `operator_kit/d279-29-one-shot-enrollment/` e contiene istruzioni
italiane, launcher e build helper. `tools/d279_one_shot_enroll.c` è un client
GPL minimale delle sole API pubbliche libfprint.

La run prevista:

1. verifica SHA completo, branch `development`, uguaglianza con
   `origin/development` e pulizia del live-critical set;
2. compila da `git archive` dello SHA la libreria target esatta con driver
   unico `goodix_27c6_5125` e NBIS nativo;
3. verifica con `nm` che la libreria non contenga le seam host-only;
4. lega hash di client, libreria e `libgusb` host al build preparato;
5. richiede un grant deterministico legato a SHA e operazione, mode privato e
   owner dell'operatore/root;
6. rifiuta un processo `fprintd` concorrente e consuma atomicamente il grant
   prima di materiale protetto, enumerazione e USB;
7. copia e riverifica gli artefatti in una directory runtime root-owned;
8. seleziona esattamente un device del driver target, apre una volta, chiama
   `fp_device_enroll_sync()` una volta e chiude una volta;
9. non salva raster o template biometrico.

Non esistono loop d'azione. Qualunque errore/retry di progress cancella
immediatamente la stessa action. Non vengono invocate capture, verify,
identify, delete/list/clear-storage o seconde action. Un successivo tentativo
richiederebbe un nuovo Human Gate; il grant deterministico dello SHA corrente
non può essere consumato due volte.

Il limite interno di 600 secondi e quello esterno di 660 secondi sono soltanto
bound host-side. Timeout, segnale, kill o close fallita lasciano lo stato del
sensore ignoto e impongono stop senza retry.

## Verifiche offline

`--offline-preflight` compila il medesimo client con baseline
`UNAPPROVED_FOR_LIVE`; il self-test prova il rifiuto prima di `fp_context_new()`.
Il build usa l'albero target Fedora 44/libfprint 1.94.100, NBIS nativo e il
driver production. L'audit `nm` conferma l'assenza delle seam sintetiche.
Una staging Meson `runtime` soltanto dentro `/tmp` rimuove l'RPATH di build,
senza installazione di sistema. Il link runtime risolve la libreria target e le
dipendenze host; il kit copia e hasha anche `libgusb.so.2` per evitare che la
run root dipenda dal path di build scrivibile dall'utente.

```text
D279_29_OPERATOR_EXECUTABLE_CLOSURE=PASS_OFFLINE
D279_29_COMPILED_BASELINE=UNAPPROVED_FOR_LIVE
D279_29_EXACT_TARGET_LIBFPRINT=1.94.100
D279_29_EXTRACTOR=NBIS_NATIVE
HOST_ONLY_TRANSCRIPT_SEAMS_IN_PRODUCTION_LIBRARY=false
PRODUCTION_LIBRARY_BUILD_RPATH_PRESENT=false
ACTION_ATTEMPT_MAX=1
OPERATOR_RETRY_COUNT=0
SECOND_ACTION_COUNT=0
REOPEN_COUNT=0
BIOMETRIC_TEMPLATE_SAVED=false
KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=0
SENSOR_SIDE_PERSISTENCE_ABSENCE_PROVEN=false
HOST_DEADLINE_IS_DEVICE_QUIESCENCE_PROOF=false
REAL_USB_ENUMERATION_ATTEMPTED=false
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
```

Sono inoltre verificati sintassi Bash/POSIX shell, `git diff --check`, rifiuto
del prepare su live-critical set non corrispondente allo SHA e rifiuto del ramo
run senza root. Le suite D279/28 già rieseguite prima della review restano
28/28 FpImageDevice e 25/25 secure-session, normali e ASan/UBSan; registration,
NBIS action e allowlist sender restano verdi.

## Confine e Human Gate

Packaging/install-tree e fprintd non sono prerequisiti della run: il kit usa un
build effimero revisionabile dello SHA approvato. Multi-action,
cancel/reactivation nello stesso open epoch, verify/PAM e robustezza production
generale restano post-live.

Il solo prossimo passo è il Human Gate. L'Utente deve approvare esplicitamente
il full SHA del commit che contiene D279/29 per una singola operazione
`D279_29_ONE_SHOT_ENROLLMENT`. L'approvazione non è implicita in questo report,
nel build offline o in autorizzazioni live precedenti.

```text
OUTCOME=READY_FOR_HUMAN_GATE
ADVANCEMENT=NEW_LIVE_BOUNDARY_OPERATOR_KIT_WITH_OFFLINE_EXECUTABLE_CLOSURE
EXECUTABLE_CLOSURE=PASS_OFFLINE_UNAPPROVED_BUILD
RESIDUAL_BLOCKER_OR_RISK=EXPLICIT_ONE_SHOT_HUMAN_APPROVAL_AND_FIRST_HARDWARE_EVIDENCE
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md
REVIEW_SET=GIT_NATIVE_D279_29_DIFF
CURRENT_LIVE_AUTHORIZED=false
```
