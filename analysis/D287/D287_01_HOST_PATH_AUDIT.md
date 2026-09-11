<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D287/01 — audit orizzontale del percorso host

## Provenance e causa del secondo abort

La seconda invocazione operatore usa la baseline
`dc09bad49913fd51529ad5d4cbe399bf2f04f04c`. La capture sanitizzata è in
`captures/D287_01/D28701_ATTEMPT_20260911T210420Z_dc09bad49913/sanitized/`:

```text
c40543f6e62435224909ab7dc5ca1e709a043e63614728542395d64b129787e3  root-series.log
ef4ed5d7d8970e37b53366181205885c40927bf2a7691e4afd63e651af3697ca  summary.env
```

La capture prova pre-audit D285 completo e
`D286_01_D287_SERIES_PRE_ROOT_AUDIT_SENSOR_ACTION_COUNT=0`, seguito dal rifiuto
`JOURNAL_CURSOR_AMBIGUOUS`. Non contiene marker di greeter ready, namespace
attempt, VERIFY o telemetry device-side.

La riproduzione read-only sullo stesso boot, systemd 259, determina la causa:

```text
journalctl -b -u fprintd.service -n 0 --show-cursor --no-pager
return_code=0
stdout=-- No entries --
stderr_bytes=0
cursor_count=0
```

Il filtro `fprintd.service` non ha entry pregresse nel boot e quindi non offre
un cursor. Non è un errore di lettura né un formato multiplo. Il boundary
corretto usa la coda globale del boot senza produrre una entry artificiale:

```text
journalctl -b -n 0 --show-cursor --no-pager
return_code=0
cursor_count=1
cursor_format=VALID
```

La raccolta resta invece unit-specific e successiva al boundary:

```text
journalctl -b -u fprintd.service --after-cursor CURSOR --no-pager
return_code=0
```

Sul target il comando restituisce correttamente `-- No entries --` quando non
sono ancora presenti eventi successivi. Non esiste fallback `--since`.

## Matrice del percorso reale

Legenda:

- `BEHAVIORALLY_TESTED_OFFLINE`: è esercitato il control flow reale con soli
  boundary esterni sostituiti da fixture deterministiche;
- `READ_ONLY_TARGET_VERIFIED`: assunzione verificata direttamente sul target
  senza modifiche o device open;
- `STATIC_ONLY_WITH_JUSTIFICATION`: nessuno stadio host resta in questa sola
  classe;
- `REQUIRES_HUMAN_GATE`: la parte indicata richiede intrinsecamente privilegi,
  greeter/PAM reale o sensore.

| Stadio | Classificazione | Evidenza / limite |
|---|---|---|
| repo gate | BEHAVIORALLY_TESTED_OFFLINE | Temp repo con remote: clean PASS, tracked/untracked dirty rifiutati anche con path contenenti spazi, status read failure rifiutato, nessuna esecuzione dei pathspec. |
| host contract | BEHAVIORALLY_TESTED_OFFLINE; READ_ONLY_TARGET_VERIFIED | Drift rifiutato prima di pkexec; NEVRA e hash reali 6.7.5 verificati. |
| polkit password path | BEHAVIORALLY_TESTED_OFFLINE; READ_ONLY_TARGET_VERIFIED | Ordine prima dell'handoff e PAM `polkit-1`/`system-auth` verificati; il secondo run ha superato pkexec. |
| session environment validation | BEHAVIORALLY_TESTED_OFFLINE; READ_ONLY_TARGET_VERIFIED | Wayland, runtime UID 1000, socket Wayland e bus presenti. |
| capture creation | BEHAVIORALLY_TESTED_OFFLINE | Directory, log e summary attraversati dal vero `d287_operator_run`. |
| pkexec handoff contract | BEHAVIORALLY_TESTED_OFFLINE; READ_ONLY_TARGET_VERIFIED | Argomenti validati nel harness; il run 2 prova l'handoff reale fino a root-series. |
| root-series revalidation | BEHAVIORALLY_TESTED_OFFLINE | Stesso `d287_root_series`, con gate richiamati dopo l'handoff. |
| target cardinality gate | BEHAVIORALLY_TESTED_OFFLINE; READ_ONLY_TARGET_VERIFIED | Fixture 1 target; enumerazione sysfs reale trova esattamente un `27c6:5125`, senza device open. |
| D285 root audit contract | BEHAVIORALLY_TESTED_OFFLINE; READ_ONLY_TARGET_VERIFIED | Pre/post ordine simulato; il pre-audit autentico del run 2 è PASS e conta zero azioni sensore. |
| operator confirmation parsing | BEHAVIORALLY_TESTED_OFFLINE | `INDICE DESTRO`, poi `TENTATIVO 2` soltanto dopo NO_MATCH. |
| journal cursor creation | BEHAVIORALLY_TESTED_OFFLINE; READ_ONLY_TARGET_VERIFIED | Valid/missing/multiple/invalid/read-error distinti; cursor globale systemd 259 provato. |
| inner log creation | BEHAVIORALLY_TESTED_OFFLINE | `mktemp`, redirection, lettura esito e cancellazione esercitati dal root-series reale. |
| unshare invocation construction | BEHAVIORALLY_TESTED_OFFLINE | Il mock valida tutti gli argomenti dell'invocazione reale. |
| namespace assumptions | BEHAVIORALLY_TESTED_OFFLINE; REQUIRES_HUMAN_GATE | Validazione e propagation failure path restano nel codice reale; il namespace mount effettivo richiede root. |
| tmpfs staging assumptions | BEHAVIORALLY_TESTED_OFFLINE; REQUIRES_HUMAN_GATE | Ordine/trap/path testati; mount tmpfs effettivo richiede root. |
| PAM overlay path/hash assumptions | READ_ONLY_TARGET_VERIFIED; REQUIRES_HUMAN_GATE | PAM sorgente/destinazione e hash verificati; bind/remount effettivi richiedono root. |
| greeter command construction | BEHAVIORALLY_TESTED_OFFLINE; READ_ONLY_TARGET_VERIFIED | Argomenti/env e binario hash-pinned; processo reale resta al gate. |
| greeter readiness detection | BEHAVIORALLY_TESTED_OFFLINE; REQUIRES_HUMAN_GATE | Ready e not-ready senza hang testati sul vero supervisore; readiness reale richiede greeter. |
| journal collection | BEHAVIORALLY_TESTED_OFFLINE; READ_ONLY_TARGET_VERIFIED | Filtro `fprintd.service` e `--after-cursor` verificati con mock e journalctl reale. |
| MATCH / NO_MATCH detection | BEHAVIORALLY_TESTED_OFFLINE; REQUIRES_HUMAN_GATE | Fixture causali complete; esito PAM reale resta live. |
| greeter supervision/termination | BEHAVIORALLY_TESTED_OFFLINE; REQUIRES_HUMAN_GATE | Not-ready, exit inattesa, timeout, TERM/KILL e process group coperti; greeter reale resta live. |
| exit-code handling | BEHAVIORALLY_TESTED_OFFLINE | Match, inner failure, root failure, result missing/multiple e pipeline verificati. |
| telemetry collection | BEHAVIORALLY_TESTED_OFFLINE; REQUIRES_HUMAN_GATE | Fixture complete/assenti/avverse; telemetry autentica richiede VERIFY. |
| classification | BEHAVIORALLY_TESTED_OFFLINE | MATCH, NO_MATCH, PAM_ERROR e SAFETY_VIOLATION esercitati. |
| cleanup | BEHAVIORALLY_TESTED_OFFLINE; REQUIRES_HUMAN_GATE | Process-group cleanup e failure propagation provati; unmount reale richiede namespace root. |
| post-attempt host validation | BEHAVIORALLY_TESTED_OFFLINE; READ_ONLY_TARGET_VERIFIED | Ordine anche dopo inner failure; contract target corrente PASS. |
| D285 post-audit contract | BEHAVIORALLY_TESTED_OFFLINE; REQUIRES_HUMAN_GATE | Ordine/failure propagation coperti; audit root autentico post-VERIFY resta live. |
| next-attempt gating | BEHAVIORALLY_TESTED_OFFLINE | NO_MATCH richiede frase successiva; MATCH arresta a uno; nessun retry implicito. |
| final result | BEHAVIORALLY_TESTED_OFFLINE | PASS, failure e risultato multiplo sono distinti e propagati. |
| capture summary/hash | BEHAVIORALLY_TESTED_OFFLINE | RC root e `tee`, result, chmod e hash attraversati; `tee` failure non è mascherato. |

## Audit shell e correzioni di classe

La review di `set -euo pipefail`, command substitution, array, quote, newline,
pipeline, `PIPESTATUS`, trap, background job/PGID, `wait`, `grep=1`, `mktemp`,
stdout/stderr e cleanup ha prodotto questi correttivi:

1. il risultato di `git status` è acquisito separatamente; un errore del
   comando diventa `REPOSITORY_STATUS_READ_FAILED` e non può sembrare clean;
2. cursor missing, multiple, invalid e read failure hanno marker distinti;
3. il cursor nasce dal journal globale del boot, mentre la collection resta
   filtrata per unit dopo il cursor;
4. greeter non pronto, exit prima dell'outcome e timeout journal hanno marker
   diversi;
5. cleanup fallito in uscita normale, segnale o trap resta nonzero e visibile;
6. root-series accetta una sola riga outcome e operator-run una sola riga
   result;
7. `PIPESTATUS` viene copiato atomicamente subito dopo `pkexec | tee`, così una
   failure di capture non è persa;
8. i timeout sono parametri interni con default production invariati, usati
   dalle fixture per esercitare i rami senza attese artificiali;
9. EOF/errore durante una conferma operatore produce ora
   `OPERATOR_CONFIRMATION_READ_FAILED` invece di un exit silenzioso causato da
   `set -e`.

`bash -n` passa. `shellcheck` non è installato e non è stato aggiunto.

## Assunzioni target read-only

Sono verificati: systemd 259; NEVRA `kscreenlocker-6.7.5-1.fc44.x86_64`,
`plasma-workspace-6.7.5-1.fc44.x86_64`, `pam-1.7.2-2.fc44.x86_64`,
`fprintd-pam-1.94.5-5.fc44.x86_64`; hash già pin; path `/usr/bin` di `pkexec`,
`unshare`, `mount`, `umount`, `mountpoint`, `runuser`, `setsid`, `journalctl`,
`chcon`, `sha256sum`, `findmnt`, `getent`, `pgrep`, `strings`, `mktemp`;
sessione Wayland coerente, runtime directory UID/mode corretti e socket Wayland
e DBus presenti. L'enumerazione sola sysfs conta un target; non apre USB.

## Residuo intrinsecamente live

```text
RESIDUAL_UNTESTABLE_BEFORE_HUMAN_RUN=
- comportamento reale di kscreenlocker_greet --testing nel namespace mount effettivo
- reale PAM call da kde-fingerprint verso fprintd
- reale VERIFY e contatto sensore
- reale telemetry prodotta e raccolta da quella VERIFY
```

Non restano failure host-side note di shell, path, journal, parsing, logging,
supervisione o cleanup riproducibili offline.
