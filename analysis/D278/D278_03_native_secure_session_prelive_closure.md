# D278/03 — local executable closure e procedura single-shot operatore

## Provenance e risultato

```text
OUTCOME=READY_FOR_AI_PM_REVIEW
ADVANCEMENT=NATIVE_SECURE_SESSION_PRELIVE_EXECUTABLE_CLOSURE_CONFIRMED_AND_SINGLE_SHOT_OPERATOR_PROCEDURE_MATERIALIZED
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
BASELINE_HEAD=843290e7790d7930bb136d91510a3db9d3a97027
AI_PM_STATIC_PRELIVE_REVIEW=PASS
EXISTING_LAUNCHER_SUFFICIENT=true
LIVE_CRITICAL_CODE_CHANGED=false
EXECUTION_ENVIRONMENT=OPERATOR_FEDORA_HOST
D278_02_RC=0
D278_01_RC=0
D278_03_BUILD=/tmp/goodix-d278-03-prelive.a65WgM
D278_03_LAUNCHER=/tmp/goodix-d278-03-prelive.a65WgM/d278_native_secure_session_once
D278_03_LAUNCHER_SHA256=a48488b0817256d896a77bf2ac037ff5bef10524dd9c018f31d1c2bb5d3a251a
SUDO_USED=0
PROTECTED_STORE_READ_COUNT=0
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0
LIVE_EXECUTION_PERFORMED=false
CURRENT_LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

La baseline iniziale era pulita: `HEAD` e `origin/main` coincidevano con
`843290e7790d7930bb136d91510a3db9d3a97027`. L'esecuzione è avvenuta sul
Fedora 44 dell'operatore, nello stesso clone e nello stesso `/tmp` disponibile
all'Utente. Il path del launcher e i log sotto `/tmp` sono evidenza operativa
effimera e non fanno parte del review set canonico.

Il primo avvio di ciascun runner nel sandbox AI si è fermato prima di build o
test perché Flatpak/bwrap non poteva creare il socket `NETLINK_ROUTE`. Come
consentito per un failure chiaramente ambientale, ciascun runner è stato
rieseguito una sola volta fuori dal sandbox, senza cambiare configurazione o
scope. Entrambi i rerun diagnostici sono passati; non vi sono stati ulteriori
rerun.

```text
D278_02_NORMAL=PASS
D278_02_ASAN_UBSAN=PASS
D278_02_LIVE_HARNESS_BUILD=PASS
D278_02_SELF_TEST=PASS
D278_02_TEST_COUNT=62
D190_FIVE_INDEPENDENT_KATS=PASS
PROTECTED_MATERIAL_NEGATIVE_MATRIX=PASS
PRODUCTION_POLICY_CANONICAL_PIN_MATRIX=PASS
D278_02_PHASE_WATCHDOG_HOST_ONLY_PROVEN=true
D278_02_DYNAMIC_REDACTED_TELEMETRY=PASS
D278_01_D1_TLS_FOCUSED_NORMAL=10/10_PASS
D278_01_D1_TLS_FOCUSED_ASAN_UBSAN=10/10_PASS
```

`ldd` ha risolto il launcher contro le librerie Fedora host, incluse
`libgusb.so.2`, GLib/GIO/GObject, OpenSSL 3 e `libusb-1.0.so.0`. Il launcher
non è stato copiato nel repository.

## Matrice sintetica della review AI-PM

Questa matrice trascrive senza estenderli i risultati della review statica
AI-PM già acquisita. L'authority è il prompt D278/03; le sorgenti revisionate
sono `tools/d278_native_secure_session_once.c`,
`tools/goodix_d278_harness.c`,
`libfprint-driver/goodix_secure_session.c`,
`libfprint-driver/goodix_tls_server.c`,
`libfprint-driver/goodix_usb_router.c`,
`libfprint-driver/goodix_fpi_usb_backend.c`,
`libfprint-driver/goodix_target_material.c` e
`libfprint-driver/goodix_a0_protocol.c`; completano l'authority i test e runner
D278/01–02 e le evidenze canoniche D232, D277/02, D278/01 e D278/02 elencati
nel prompt.

| Boundary | Esito statico AI-PM |
|---|---|
| CLI intent esplicito e mutuamente esclusivo | PASS |
| Materiali, pin e D190 prima di GUsb | PASS |
| Target exact `27c6:5125`, exactly-one match | PASS |
| One open/claim/release/close | PASS_STATIC |
| Un solo physical IN owner; max 1 IN e max 1 OUT | PASS_STATIC |
| Stale generation fenced; drain prima del free | PASS_STATIC |
| `A8→E4→A2→82→A6→A2→70→80×4→90→D1→TLS→STOP` | PASS |
| Pin canonici D232 | PASS |
| D1 senza A0 ACK; gate B0/ClientHello | PASS |
| D1 avanza solo dopo push OpenSSL riuscita e server flight sincrono | PASS |
| TLS 1.2, `PSK-AES128-GCM-SHA256`, `Client_identity` | PASS |
| B0 record-separated, physical 64 B, zero tail, pacing 10 ms | PASS |
| Watchdog per fase | PASS |
| Zero retry/reopen/reset | PASS_STATIC |
| D4, application data, finger e image fuori boundary | PASS |
| TLS established, drain egress, STOP | PASS |
| Failure: fence/cancel/drain/cleanup terminale | PASS_STATIC |
| Executable closure sulla baseline host operatore | PASS_HOST_ONLY (D278/03) |
| SHA-256 launcher costruito sull'host operatore | ACQUISITO (D278/03) |

## Riesame metodologico pre-live

1. **Cambiamento materiale rispetto all'ultima target proof.** D277/02 provava
   soltanto A8/A0/APP12509 sul target; D278/02 ha poi provato il protected-
   material boundary autentico con `e4_binding_match=true` e zero USB. La
   futura run combinerà per la prima volta questi confini nel percorso nativo
   fino a TLS.
2. **Nuova ipotesi.** Con gli stessi factory material già preflightati,
   APP12509 accetterà
   `A8→E4 MATCH→A2→82→A6→A2→70→80×4→90→D1→TLS 1.2 PSK→STOP`.
3. **Se fallisce.** Nessun secondo tentativo equivalente: classificare la
   prima fase di failure, riesaminare offline e richiedere nuova review e nuova
   autorizzazione.

## Procedura operatore futura — NON ANCORA AUTORIZZATA

### Fase A — verifica baseline e launcher

Eseguire da una directory interna al clone canonico. Questi controlli non
accedono al dispositivo né allo store protetto.

```bash
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"
BASELINE=843290e7790d7930bb136d91510a3db9d3a97027
LAUNCHER=/tmp/goodix-d278-03-prelive.a65WgM/d278_native_secure_session_once
APPROVED_LAUNCHER_SHA256=a48488b0817256d896a77bf2ac037ff5bef10524dd9c018f31d1c2bb5d3a251a
LIVE_CRITICAL=(
  tools/d278_native_secure_session_once.c
  tools/goodix_d278_harness.c
  libfprint-driver/goodix_secure_session.c
  libfprint-driver/goodix_tls_server.c
  libfprint-driver/goodix_usb_router.c
  libfprint-driver/goodix_fpi_usb_backend.c
  libfprint-driver/goodix_target_material.c
  libfprint-driver/goodix_a0_protocol.c
)

git status --short --branch
git rev-parse HEAD
test "$(git rev-parse "$BASELINE^{commit}")" = "$BASELINE"
git diff --quiet "$BASELINE" -- "${LIVE_CRITICAL[@]}"
git diff --cached --quiet "$BASELINE" -- "${LIVE_CRITICAL[@]}"
test -z "$(git status --porcelain -- "${LIVE_CRITICAL[@]}")"
test -x "$LAUNCHER"
test "$(sha256sum "$LAUNCHER" | awk '{print $1}')" = "$APPROVED_LAUNCHER_SHA256"
printf 'PRELIVE_BASELINE_AND_LAUNCHER_CHECK=PASS\n'
```

Un futuro commit esclusivamente documentale D278/03 non modifica da solo la
baseline live-critical: i controlli sopra confrontano esplicitamente soltanto
il set revisionato.

### STOP gate

```text
STOP — NON ESEGUIRE IL BLOCCO LIVE

Serve prima:
1. review AI-PM PASS di D278/03;
2. approvazione esplicita della baseline live-critical;
3. approvazione esplicita dello SHA-256 del launcher;
4. autorizzazione esplicita dell'Utente per UNA sola run hardware.

CURRENT_LIVE_AUTHORIZED=false
DO NOT RUN TWICE
```

### Fase B — comando live futuro

```text
NOT_AUTHORIZED_DO_NOT_EXECUTE
```

Il blocco seguente è preparato per una futura autorizzazione separata. **Non è
stato eseguito in D278/03.** Ripete fail-closed i controlli sul live-critical
set e sul launcher. Il limite di 30 secondi deriva dalla somma dei watchdog di
fase reali (11,75 s) con margine host ragionevole; `--kill-after=5s` impedisce
un'attesa indefinita dopo TERM.

```bash
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"
BASELINE=843290e7790d7930bb136d91510a3db9d3a97027
LAUNCHER=/tmp/goodix-d278-03-prelive.a65WgM/d278_native_secure_session_once
APPROVED_LAUNCHER_SHA256=a48488b0817256d896a77bf2ac037ff5bef10524dd9c018f31d1c2bb5d3a251a
LIVE_LOG=/tmp/d278_03_native_secure_session_single_shot.log
LIVE_CRITICAL=(
  tools/d278_native_secure_session_once.c
  tools/goodix_d278_harness.c
  libfprint-driver/goodix_secure_session.c
  libfprint-driver/goodix_tls_server.c
  libfprint-driver/goodix_usb_router.c
  libfprint-driver/goodix_fpi_usb_backend.c
  libfprint-driver/goodix_target_material.c
  libfprint-driver/goodix_a0_protocol.c
)

test "$(git rev-parse "$BASELINE^{commit}")" = "$BASELINE"
git diff --quiet "$BASELINE" -- "${LIVE_CRITICAL[@]}"
git diff --cached --quiet "$BASELINE" -- "${LIVE_CRITICAL[@]}"
test -z "$(git status --porcelain -- "${LIVE_CRITICAL[@]}")"
test -x "$LAUNCHER"
test "$(sha256sum "$LAUNCHER" | awk '{print $1}')" = "$APPROVED_LAUNCHER_SHA256"

set +e
sudo timeout --signal=TERM --kill-after=5s 30s \
  "$LAUNCHER" --live-exact-secure-session 2>&1 | tee "$LIVE_LOG"
LIVE_PIPE_RC=("${PIPESTATUS[@]}")
set -e
LIVE_RC=${LIVE_PIPE_RC[0]}
printf 'LIVE_RC=%s\nLIVE_LOG=%s\n' "$LIVE_RC" "$LIVE_LOG"
```

Il comando contiene una sola invocazione, senza loop, retry, reopen, reset o
D4. Il `sudo` resta un'azione manuale dell'Utente.

### Output da riportare all'AI-PM

Dopo l'eventuale futura run, l'operatore dovrà riportare il JSON terminale
completo redatto, `LIVE_RC` e il path del log. Un successo richiede
semanticamente:

```text
result=pass
failure_class=none
tls_handshake_count=1
tls_established=true
retry_count=0
transport_reopen_count=0
device_reset_count=0
persistent_device_write_count=0
d4_reachable=false
application_data_count=0
finger_wait_count=0
image_count=0
backend_drained=true
terminal_cleanup_completed=true
usb_open_count=1
usb_claim_count=1
usb_release_count=1
usb_close_count=1
current_live_authorized=false
```

Non sono imposti conteggi di transfer, ACK o typed response non deterministici.

## Confine residuo e review set

```text
NATIVE_SECURE_SESSION_TARGET_PROVEN=false
TARGET_E4_NATIVE_LIVE_PROVEN=false
TARGET_TLS_NATIVE_LIVE_PROVEN=false
OPERATOR_PROCEDURE_PREPARED=true
OPERATOR_STOP_GATE_PRESENT=true
NO_RAW_PSK_IN_REVIEW_SET=PASS
NO_RAW_E4_VALIDATOR_IN_REVIEW_SET=PASS
NO_RAW_CONFIG90_IN_REVIEW_SET=PASS
NO_BIOMETRIC_DATA_IN_REVIEW_SET=PASS
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=BASELINE_843290e7790d7930bb136d91510a3db9d3a97027_PLUS_WORKTREE_DIFF_PLUS_analysis/D278/D278_03_native_secure_session_prelive_closure.md_PLUS_Goodix_27c6_5125_manuale_tecnico.md
RESIDUAL_BLOCKER_OR_RISK=NATIVE_SECURE_SESSION_TARGET_UNPROVEN_BEYOND_A8_A0;TARGET_E4_NATIVE_LIVE_UNPROVEN;TARGET_TLS_NATIVE_LIVE_UNPROVEN;CURRENT_LIVE_AUTHORIZED_FALSE
```
