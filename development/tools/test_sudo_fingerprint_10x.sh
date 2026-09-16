#!/usr/bin/env bash
# Test ripetibilità autenticazione fingerprint via sudo/fprintd - 10 sessioni
# Non modifica configurazioni PAM/fprintd e non invoca direttamente API di verifica.
# Osserva in sola lettura i segnali D-Bus VerifyStatus emessi da fprintd mentre
# l'utente esegue la normale autenticazione sudo su /usr/bin/true.

set -u
set -o pipefail

SESSIONS=10
STAMP="$(date +%Y%m%d_%H%M%S)"
OUTDIR="${PWD}/fingerprint_sudo_test_${STAMP}"
SUMMARY_LOG="${OUTDIR}/summary.log"
SESSIONS_CSV="${OUTDIR}/sessions.csv"
EVENTS_CSV="${OUTDIR}/events.csv"
MONITOR_PID=""

fail() {
    printf '\nERRORE: %s\n' "$*" >&2
    exit 1
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || fail "comando richiesto non trovato: $1"
}

pct() {
    awk -v n="$1" -v d="$2" 'BEGIN { if (d == 0) printf "0.0"; else printf "%.1f", (100*n/d) }'
}

cleanup_monitor() {
    if [[ -n "${MONITOR_PID:-}" ]] && kill -0 "$MONITOR_PID" 2>/dev/null; then
        kill "$MONITOR_PID" 2>/dev/null || true
        wait "$MONITOR_PID" 2>/dev/null || true
    fi
    MONITOR_PID=""
}

cleanup_all() {
    cleanup_monitor
    # Lascia sudo senza credenziale temporale valida. Non richiede autenticazione.
    sudo -k 2>/dev/null || true
}

trap cleanup_all EXIT
trap 'exit 130' INT TERM

for cmd in gdbus sudo awk sed grep date mkdir sleep kill head tee; do
    need_cmd "$cmd"
done
[[ -x /usr/bin/true ]] || fail "/usr/bin/true non disponibile"

mkdir -p "$OUTDIR" || fail "impossibile creare $OUTDIR"

# Individua il device fprintd predefinito. La chiamata e' di sola lettura.
DEVICE_REPLY="$(
    gdbus call --system \
        --dest net.reactivated.Fprint \
        --object-path /net/reactivated/Fprint/Manager \
        --method net.reactivated.Fprint.Manager.GetDefaultDevice 2>&1
)" || fail "fprintd non ha restituito un device predefinito: $DEVICE_REPLY"

DEVICE_PATH="$(printf '%s\n' "$DEVICE_REPLY" | grep -oE '/net/reactivated/Fprint/Device/[A-Za-z0-9_/-]+' | head -n1)"
[[ -n "$DEVICE_PATH" ]] || fail "impossibile estrarre il path del device da: $DEVICE_REPLY"

# Verifica soltanto che il monitor D-Bus possa essere avviato; nessuna autenticazione.
PREFLIGHT_LOG="${OUTDIR}/dbus_preflight.log"
gdbus monitor --system \
    --dest net.reactivated.Fprint \
    --object-path "$DEVICE_PATH" >"$PREFLIGHT_LOG" 2>&1 &
MONITOR_PID=$!
sleep 0.25
if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
    wait "$MONITOR_PID" 2>/dev/null || true
    MONITOR_PID=""
    fail "monitor D-Bus fprintd non disponibile; vedere $PREFLIGHT_LOG"
fi
cleanup_monitor

printf '%s\n' \
    'session,start_iso,duration_s,sudo_rc,result,decisive_attempts,success_on_attempt,no_match,acquisition_retry,technical_error,raw_log' \
    > "$SESSIONS_CSV"
printf '%s\n' 'session,event_no,status,done' > "$EVENTS_CSV"

success_sessions=0
failed_sessions=0
inconclusive_sessions=0
success_first=0
success_second=0
success_third=0
success_after_third=0
total_decisive=0
total_match=0
total_no_match=0
total_retry=0
total_technical=0

printf '\n=== TEST SUDO + IMPRONTA: 10 SESSIONI ===\n'
printf 'Device fprintd: %s\n' "$DEVICE_PATH"
printf 'Output: %s\n\n' "$OUTDIR"
printf '%s\n' \
    'Ogni sessione esegue: sudo -k /usr/bin/true' \
    '- /usr/bin/true non compie alcuna operazione privilegiata.' \
    '- sudo -k forza una nuova autenticazione, evitando il riuso della cache sudo.' \
    '- Il tool NON cambia PAM, fprintd, max-tries o configurazioni del sensore.' \
    '- Se dopo i tentativi biometrici compare la password, puoi inserirla per far' \
    '  terminare sudo: NON verra conteggiata come successo biometrico.' \
    '- I retry di qualita/posizionamento sono registrati separatamente e non vengono' \
    '  conteggiati come uno dei tentativi decisivi match/no-match.'
printf '\n'

for ((session=1; session<=SESSIONS; session++)); do
    printf '%s' "Sessione ${session}/${SESSIONS} - premi INVIO quando sei pronto: "
    IFS= read -r _

    RAW_LOG="${OUTDIR}/session_$(printf '%02d' "$session")_dbus.log"

    gdbus monitor --system \
        --dest net.reactivated.Fprint \
        --object-path "$DEVICE_PATH" >"$RAW_LOG" 2>&1 &
    MONITOR_PID=$!
    sleep 0.20

    if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
        wait "$MONITOR_PID" 2>/dev/null || true
        MONITOR_PID=""
        printf '  ERRORE: monitor D-Bus terminato prima di sudo. Sessione inconcludente.\n'
        start_iso="$(date --iso-8601=seconds)"
        printf '%s\n' "$session,$start_iso,0,NA,INCONCLUSIVE_MONITOR,0,0,0,0,1,$RAW_LOG" >> "$SESSIONS_CSV"
        ((inconclusive_sessions+=1))
        ((total_technical+=1))
        continue
    fi

    start_iso="$(date --iso-8601=seconds)"
    start_s="$(date +%s)"

    # Il payload privilegiato e' intenzionalmente un no-op.
    sudo -k /usr/bin/true
    sudo_rc=$?

    end_s="$(date +%s)"
    duration=$((end_s - start_s))

    # Piccolo margine per far arrivare l'ultimo segnale D-Bus prima di chiudere il monitor.
    sleep 0.20
    cleanup_monitor

    decisive=0
    match_count=0
    no_match=0
    retry_count=0
    technical_count=0
    success_attempt=0
    event_no=0

    while IFS= read -r line; do
        status="$(printf '%s\n' "$line" | sed -n "s/.*'\(verify-[a-z-]*\)'.*/\1/p")"
        [[ -n "$status" ]] || continue

        done_flag="$(printf '%s\n' "$line" | sed -n 's/.*,[[:space:]]*\(true\|false\)).*/\1/p')"
        [[ -n "$done_flag" ]] || done_flag="unknown"

        ((event_no+=1))
        printf '%s\n' "$session,$event_no,$status,$done_flag" >> "$EVENTS_CSV"

        case "$status" in
            verify-match)
                ((decisive+=1))
                ((match_count+=1))
                if (( success_attempt == 0 )); then
                    success_attempt=$decisive
                fi
                ;;
            verify-no-match)
                ((decisive+=1))
                ((no_match+=1))
                ;;
            verify-retry-scan|verify-swipe-too-short|verify-finger-not-centered|verify-remove-and-retry|verify-too-fast)
                ((retry_count+=1))
                ;;
            verify-disconnected|verify-unknown-error)
                ((technical_count+=1))
                ;;
            *)
                # Conserva comunque l'evento nel CSV; uno status futuro/sconosciuto
                # non viene trasformato arbitrariamente in successo o no-match.
                ((technical_count+=1))
                ;;
        esac
    done < <(grep 'VerifyStatus' "$RAW_LOG" 2>/dev/null || true)

    ((total_decisive+=decisive))
    ((total_match+=match_count))
    ((total_no_match+=no_match))
    ((total_retry+=retry_count))
    ((total_technical+=technical_count))

    if (( match_count > 0 )); then
        result="BIOMETRIC_SUCCESS"
        ((success_sessions+=1))
        case "$success_attempt" in
            1) ((success_first+=1)) ;;
            2) ((success_second+=1)) ;;
            3) ((success_third+=1)) ;;
            *) ((success_after_third+=1)) ;;
        esac
        printf '  OK: match al tentativo decisivo n. %d' "$success_attempt"
        if (( retry_count > 0 )); then
            printf ' | retry acquisizione: %d' "$retry_count"
        fi
        printf '\n'
    elif (( no_match > 0 )); then
        result="BIOMETRIC_FAILURE"
        ((failed_sessions+=1))
        printf '  FAIL biometrico: %d no-match, nessun match' "$no_match"
        if (( retry_count > 0 )); then
            printf ' | retry acquisizione: %d' "$retry_count"
        fi
        printf '\n'
    else
        result="INCONCLUSIVE_NO_DECISION"
        ((inconclusive_sessions+=1))
        printf '  INCONCLUDENTE: nessun match/no-match rilevato'
        if (( retry_count > 0 )); then
            printf ' | retry acquisizione: %d' "$retry_count"
        fi
        if (( technical_count > 0 )); then
            printf ' | errori tecnici: %d' "$technical_count"
        fi
        printf '\n'
    fi

    if (( decisive > 3 )); then
        printf '  ATTENZIONE: osservati %d tentativi decisivi (>3 attesi). Verificare raw log.\n' "$decisive"
    fi
    if (( sudo_rc == 0 && match_count == 0 )); then
        printf '  Nota: sudo e terminato con successo senza match biometrico osservato (es. fallback password).\n'
    fi

    printf '%s\n' \
        "$session,$start_iso,$duration,$sudo_rc,$result,$decisive,$success_attempt,$no_match,$retry_count,$technical_count,$RAW_LOG" \
        >> "$SESSIONS_CSV"
done

# Invalida l'eventuale timestamp sudo lasciato dall'ultima sessione.
sudo -k 2>/dev/null || true

completed=$((success_sessions + failed_sessions + inconclusive_sessions))
valid_bio_sessions=$((success_sessions + failed_sessions))
all_scan_events=$((total_match + total_no_match + total_retry + total_technical))

{
    printf '=== REPORT TEST SUDO + FINGERPRINT ===\n'
    printf 'Data fine: %s\n' "$(date --iso-8601=seconds)"
    printf 'Device fprintd: %s\n' "$DEVICE_PATH"
    printf 'Sessioni previste: %d\n' "$SESSIONS"
    printf 'Sessioni completate/classificate: %d\n\n' "$completed"

    printf -- '--- RISULTATO PER SESSIONE ---\n'
    printf 'Successi biometrici: %d/%d = %s%%\n' "$success_sessions" "$SESSIONS" "$(pct "$success_sessions" "$SESSIONS")"
    printf 'Fallimenti biometrici: %d/%d = %s%%\n' "$failed_sessions" "$SESSIONS" "$(pct "$failed_sessions" "$SESSIONS")"
    printf 'Sessioni inconcludenti/telem. mancante: %d/%d = %s%%\n\n' "$inconclusive_sessions" "$SESSIONS" "$(pct "$inconclusive_sessions" "$SESSIONS")"

    printf -- '--- A QUALE TENTATIVO E ARRIVATO IL MATCH ---\n'
    printf '1° tentativo: %d/%d sessioni = %s%%\n' "$success_first" "$SESSIONS" "$(pct "$success_first" "$SESSIONS")"
    printf '2° tentativo: %d/%d sessioni = %s%%\n' "$success_second" "$SESSIONS" "$(pct "$success_second" "$SESSIONS")"
    printf '3° tentativo: %d/%d sessioni = %s%%\n' "$success_third" "$SESSIONS" "$(pct "$success_third" "$SESSIONS")"
    if (( success_after_third > 0 )); then
        printf '>3° tentativo (anomalia rispetto all atteso): %d\n' "$success_after_third"
    fi
    if (( success_sessions > 0 )); then
        printf 'Tra i soli successi: 1°=%s%% | 2°=%s%% | 3°=%s%%\n' \
            "$(pct "$success_first" "$success_sessions")" \
            "$(pct "$success_second" "$success_sessions")" \
            "$(pct "$success_third" "$success_sessions")"
    fi
    printf '\n'

    printf -- '--- EVENTI BIOMETRICI ---\n'
    printf 'Tentativi decisivi (match + no-match): %d\n' "$total_decisive"
    printf 'MATCH: %d/%d = %s%%\n' "$total_match" "$total_decisive" "$(pct "$total_match" "$total_decisive")"
    printf 'NO-MATCH: %d/%d = %s%%\n' "$total_no_match" "$total_decisive" "$(pct "$total_no_match" "$total_decisive")"
    printf 'Retry di acquisizione/qualita: %d\n' "$total_retry"
    printf 'Errori tecnici/disconnessioni/status sconosciuti: %d\n' "$total_technical"
    printf 'Eventi fprintd classificati complessivi: %d\n\n' "$all_scan_events"

    printf -- '--- INTERPRETAZIONE ---\n'
    printf 'MATCH/NO-MATCH sono decisioni biometriche e determinano il numero del tentativo.\n'
    printf 'I retry di acquisizione (dito non centrato, scansione da ripetere, ecc.) sono\n'
    printf 'registrati separatamente perche fprintd li considera verifica ancora in corso.\n'
    if (( valid_bio_sessions > 0 )); then
        printf 'Success rate sulle sole sessioni biometricamente classificabili: %d/%d = %s%%\n' \
            "$success_sessions" "$valid_bio_sessions" "$(pct "$success_sessions" "$valid_bio_sessions")"
    fi

    printf '\nFile dettaglio sessioni: %s\n' "$SESSIONS_CSV"
    printf 'File eventi D-Bus: %s\n' "$EVENTS_CSV"
    printf 'Raw log per sessione: %s/session_XX_dbus.log\n' "$OUTDIR"
} | tee "$SUMMARY_LOG"

printf '\nTest terminato. Report principale: %s\n' "$SUMMARY_LOG"
