# D278/13 — integrated path live-capable, host-only pre-live closure

## Esito

```text
OUTCOME=PASS_HOST_ONLY_PRELIVE_CLOSURE
ADVANCEMENT=NEW_EXECUTABLE_INTEGRATED_BINDING_AND_HOST_ONLY_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
CANONICAL_DOCUMENTATION=UPDATED
```

D278/13 chiude il gap tra il grafo nativo C D278/12 e la forma di invocazione
fisica futura. Non esegue una run live e non approva la readiness live.

```text
factory_firmware_and_persistent_state_must_remain_untouched
```

```text
D278_13_BASELINE=78230ff1ebd4f1db5d5fd06fbfe6d41fa3a07eca
START_BRANCH=main
START_HEAD=78230ff1ebd4f1db5d5fd06fbfe6d41fa3a07eca
START_WORKTREE=CLEAN
FINAL_HEAD=78230ff1ebd4f1db5d5fd06fbfe6d41fa3a07eca
FINAL_STATE=STEP_LOCAL_WORKTREE_DIFF_NO_COMMIT
```

## Architettura scelta

La fixture D278/12 completa usava backend/router/session compatibili ma
composti manualmente. Il tool live D278/11 possedeva invece un
`GoodixD278Harness` separato e si fermava al TLS. D278/13 non estende quel
percorso: usa la shell `GoodixFpImageDevice` non registrata e il suo solo
`GoodixDeviceContext`.

```text
GUsbDevice già selezionato
  -> goodix_fpimage_device_new_for_usb()
  -> GoodixDeviceContext operator epoch
     -> un GoodixFpiUsbBackend
     -> un GoodixUsbRouter / un owner fisico IN
     -> un GoodixSecureSession
     -> un GoodixTlsServer / handshake 1 / handoff 1
     -> handoff backend solo dopo TLS egress/OUT drain
     -> un GoodixPostTlsLifecycle
     -> decoder C -> pipeline FpImage, due volte
     -> STOP -> fence/cancel -> drain -> release/close
```

L'adapter GPL non contiene un sequencer, costruttore TLS/backend/router,
derivazione FDT di lifecycle, decoder o pipeline. Carica il materiale mediante
gli stessi `goodix_target_material_*` e `goodix_d190_pe_*` già accettati in
D278/02. Il seed iniziale FDT è future-only e read-only dal blob raw privato
D255 canonico, con SHA esatto, layout/CRC e binding OTP hash-only. Non esiste
fallback, ricerca path, cache write o trasporto di secret nuovo.

La shell non ha id table `27c6:5125`, non è registrata o installata. Solo il
tool GPL seleziona esattamente un target e applica la meccanica
open/claim/release/close. Ogni semantica wire resta nel grafo LGPL già
revisionato.

## Sicurezza del launcher

Entry point operator:

```text
./operator_kit/d278-13-integrated-path-once.sh --host-only-prelive
```

Il futuro ramo `--live-integrated-once` compila il medesimo adapter. Un build
ordinario incorpora `UNAPPROVED_FOR_LIVE`: anche invocando esplicitamente il
ramo live, il binario termina con codice `3` e marker
`LIVE_NOT_AUTHORIZED_OR_BASELINE_UNAPPROVED` prima di:

1. leggere manifest/transport/config90 protetti;
2. leggere il cache raw FDT;
3. creare o enumerare `GUsbContext`;
4. aprire/claimare o sottomettere transfer.

Una futura run richiede sia un SHA completo approvato al build sia match esatto
runtime dello SHA, token single-shot e operation name. D278/13 non ha fornito
né consumato tali valori.

Il monitor tool-side osserva soltanto STOP/terminal/deadline e gestisce pacing
GLib e cleanup; non decide fasi o comandi. Il success boundary è la seconda
pipeline, poi nessun terzo ciclo. Tutti i contatori di retry/reopen/reset/
clear-halt/write restano hard-zero. Il cleanup applica generation fence,
cancel e drain. Questo non promuove la quiescenza fisica dopo cancel arbitrario.

## Prova host-only integrata

Il test `/goodix/d278/integrated-context-live-binding-host-only` usa il vero
context owner e synthetic async seams. Attraversa:

```text
REENTRY_RECOVERY_A2 -> ... -> D1
-> handshake TLS 1.2 PSK OpenSSL reale in Memory BIO
-> STOP secure a TLS e OUT completamente drenati
-> automatic backend handoff sullo stesso context
-> D4/AF/fresh-FDT/bootstrap B0
-> first IRQ2/0x22/B0/decode/FpImage
-> 0x34/IRQ0200/fresh down-table/0x20/post-up B0 discard/0x50/NAV
-> release complete + AWAIT_FINGER_ON -> exactly-one 0x32
-> second IRQ2/0x22/B0/decode/FpImage -> STOP
```

Asserzioni integrate: stesso puntatore backend/router/TLS, secure command 14,
handshake 1, handoff 1, prima e seconda pipeline 1, rearm 1, terzo ciclo 0,
real submit 0 e max outstanding 1/1. Il passaggio post-TLS è osservabile solo
dopo `GOODIX_SECURE_PHASE_STOP`; il test distingue correttamente il primo D4
A0 dal flight B0 già drenato.

I nuovi casi `/integrated-context-cancel-secure` e
`/integrated-context-cancel-post-tls` provano cancel terminale e drain nello
stesso context con retry/reopen/reset/clear-halt/write tutti zero. Le suite
D278/12 già esistenti coprono ordine release tail, fresh same-cycle gate,
reiezione stale/cross-generation, rearm exactly once, post-up B0 non-image,
frammentazione fisica e callback N-1.

## Verifiche eseguite

Tutte le esecuzioni sono avvenute dalla Git root. Il Flatpak Freedesktop SDK
25.08 è stato avviato con `--unshare=network`. Nessun test ha un device reale o
un loader production raggiungibile.

| Comando/verifica | Risultato |
|---|---|
| `./libfprint-driver/tests/run_goodix_fpimage_device_test.sh` | 17/17 normal + 17/17 ASAN/UBSAN PASS |
| `./libfprint-driver/tests/run_goodix_d278_secure_session_test.sh` | 17/17 normal + 17/17 ASAN/UBSAN PASS |
| `./libfprint-driver/tests/run_goodix_d278_12_post_tls_test.sh` | 6/6 normal + 6/6 ASAN/UBSAN PASS, deterministic repeat PASS |
| `./libfprint-driver/tests/run_goodix_d278_02_test.sh` | 62/62 normal + 62/62 ASAN/UBSAN PASS; loader/gate regressions PASS |
| seconda e successive esecuzioni della suite D278 | 17/17 + 17/17 PASS; determinismo logico confermato |
| `./libfprint-driver/tests/build_goodix_d278_13_adapter.sh` | live-shaped GUsb adapter build/link/`ldd` PASS |
| gate self-test del binario | `EXECUTABLE_CLOSURE=PASS_HOST_ONLY` |
| ramo live su build ordinario | exit 3 prima di secret/cache/GUsb, PASS |
| `./operator_kit/d278-13-integrated-path-once.sh --host-only-prelive` | PASS, invocazione operatore realistica |
| stesso launcher via path assoluto con cwd `/tmp` | PASS, Git-root discovery e cwd independence |
| source/symbol persistent-recovery audit | PASS |
| duplicate-stack e legacy-harness-fallback audit | PASS |
| shell `sh -n` | PASS |
| `git diff --check` | PASS |

Il build adapter risolve dinamicamente GUsb, GLib/GIO/GObject, OpenSSL 3 e
libusb; non richiede installazione e vive in una directory `/tmp` effimera.
La root è risolta con `git rev-parse`, quindi non dipende dal cwd o da path
workstation. L'audit del source vieta costruttori di session/TLS/lifecycle/
backend/router nel tool; `nm` prova l'assenza del legacy `GoodixD278Harness`.

## Telemetria futura bounded

L'adapter è capace di emettere, senza raster o secret:

- open attempt/open/claim/release/close;
- submit reali, completion IN/OUT e massimi outstanding;
- trace nominale delle fasi secure, command/ACK/typed, reentry strict e A8 pin;
- handshake/handoff e zeroizzazione tramite audit esistenti;
- tutti i contatori post-TLS fino alle due pipeline, release, fresh down-table,
  rearm, STOP e cleanup;
- zero esplicito per retry/reopen/reset/clear-halt/write/terzo ciclo.

Il numero di submit IN non è congelato. Nessun payload biometrico, FDT raw,
OTP, PSK, validator o CONFIG90 viene serializzato.

## Provenance

Il dominio LGPL modifica soltanto plumbing/observer e test derivati dalle API
pubbliche e dall'architettura canonica D276/D278. Il glue nuovo resta GPL. Nel
dominio GPL, la sequenza di material prep riusa il pattern project-owned di
`tools/goodix_d278_harness.c`; la validazione cache riusa il contratto
project-owned `core/fdt_seed.py`/D255/D261. Non entra espressione GPL nel
driver LGPL. `docs/LICENSING_AND_PROVENANCE.md` è aggiornato; clean-room è una
disciplina ingegneristica, non una conclusione legale.

## Marker di completamento e limiti residui

```text
INTEGRATED_PATH_LIVE_CAPABLE_IMPLEMENTED=true
LIVE_CAPABLE_INTEGRATED_PATH_HOST_ONLY_PROVEN=true
SAME_GOODIX_DEVICE_CONTEXT=true
SINGLE_USB_BACKEND_OWNER=true
SINGLE_USB_ROUTER=true
SINGLE_PHYSICAL_IN_OWNER=true
SINGLE_TLS_OBJECT=true
TLS_HANDSHAKE_COUNT_MAX=1
SECRET_HANDOFF_COUNT_MAX=1

FIRST_IMAGE_PIPELINE_HOST_ONLY_PROVEN=true
SECOND_IMAGE_PIPELINE_HOST_ONLY_PROVEN=true
SECOND_IMAGE_RASTER_TARGET_PROVEN=false
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
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
CANONICAL_DOCUMENTATION=UPDATED
```

## Review set Git-native

```text
REVIEW_SET=BASELINE_78230ff1ebd4f1db5d5fd06fbfe6d41fa3a07eca_ON_main_PLUS_CURRENT_WORKTREE_DIFF_PLUS_analysis/D278/D278_13_integrated_path_live_capable_host_only_prelive.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md_PLUS_docs/LICENSING_AND_PROVENANCE.md_PLUS_libfprint-driver/goodix_fpimage_device.[ch]_PLUS_libfprint-driver/tests/test_goodix_d278_secure_session.c_PLUS_libfprint-driver/tests/run_goodix_d278_secure_session_test.sh_PLUS_libfprint-driver/tests/build_goodix_d278_13_adapter*.sh_PLUS_tools/d278_integrated_path_once.c_PLUS_operator_kit/d278-13-integrated-path-once.sh
```

Nessun ZIP/Base64 è stato creato. HEAD non è stato modificato; nessun commit,
merge, rebase, reset, installazione o pubblicazione è stato eseguito.
