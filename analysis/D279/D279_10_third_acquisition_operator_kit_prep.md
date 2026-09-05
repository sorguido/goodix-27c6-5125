<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/10 — replan del Kit per il primo enrollment OEM completo

## Esito offline

```text
D279_10_OUTCOME=ATTEMPT01_FAIL_CLOSED_A0_CORRECTIVE_READY_OFFLINE
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_LINUX_SYNTHETIC;WINDOWS_NATIVE_PENDING
REAL_TARGET_EXECUTION_BY_OPERATOR=true
USB_ACCESSED_BY_AI=false
AUTHENTIC_CAPTURE_ACCESSED_BY_AI=true
LIVE_AUTHORIZED=false
```

Baseline del replan: `fc2172f9973ea5a13f067dc3abfd98881c274efa`.
Il correttivo resta nello stesso D279/10 perché sostituisce il boundary e il
contratto operativo del Kit già introdotto, senza creare un nuovo fatto live.

## Corrective PowerShell 5.1 post-qualificazione `cc8754e`

La prima qualificazione nativa della versione full-enrollment è stata eseguita
dall’Utente su clone fresco, branch `development`, HEAD esatto
`cc8754e009da52e392996c045deb57fca2b30c32` e worktree pulito. Il self-test è
passato; `NativeQualificationOnly` si è fermato alla precedente riga 259 con
`FullyQualifiedErrorId: NativeCommandError`. Nessun live era autorizzato o
eseguito.

La causa è host-side e riproducibile: `unittest -q` scrive il normale riepilogo
su stderr; Windows PowerShell Desktop 5.1, con
`$ErrorActionPreference = "Stop"` e `2>&1`, può promuoverlo a errore terminante
prima che il launcher salvi `$LASTEXITCODE`.

Il corrective introduce `Invoke-D279NativeCaptured`. Solo durante il comando
nativo imposta localmente `Continue`, cattura entrambi gli stream, salva
l’exit code nativo e ripristina sempre la policy globale nel `finally`. Il
controllo non è indebolito: la qualificazione esegue un probe `stderr + exit 0`
e un probe separato con exit intenzionale `7`, poi pretende exit zero dalla
suite. L’output qualification diventa V3 e registra entrambi i probe.

## Attempt 01: analisi diretta del raw autentico

L’Utente ha eseguito e preservato nel commit
`98ec62bea75d7764e44296a1d70da7a2f06609c5` l’attempt
`D27910_20260905_ATTEMPT01`. Il launcher è fallito chiuso prima del wizard e di
qualsiasi contatto: target attached, capture started/stopped, zero retry,
restore richiesto per stato prudenzialmente incerto. L’AI ha letto il solo raw
autentico espressamente autorizzato, hash
`557ff136e5a1d383f7413ca24d731eeae32d2b377e61003846b034ecda991743`.

Il pcapng finalizzato passa il parser strutturale stretto: 186 pacchetti, 75
frame target, firmware APP12509 riconosciuto, nessun frame pending. La stessa
analisi in modalità growing e finalizzata individua quattro errori agli indici
pacchetto `25, 29, 37, 45`. Tutti sono A0 OUT completi, physical USB 64 byte,
outer logico dichiarato/osservato 12 byte, inner length 5, non troncati e
byte-identici:

```text
a0 08 00 a8 01 05 00 00 00 00 00 88
```

Il trigger effettivo dell’observer è il primo della serie, packet index `25`;
gli altri tre sono occorrenze latenti della stessa lacuna che il fail immediato
non aveva raggiunto.

La somma del checksum generico è `0x8d`, non `0xaa`; perciò D274 emetteva
`MALFORMED_A0`. Non è però un A0 incompatibile: il census sanitizzato D230
`analysis/D230/work/offline_census.json` conserva per 10 occorrenze della
reference OEM positiva lo stesso payload corto `0000000088`; i censimenti
metadata D273 mostrano inoltre la forma `A0/0x01/outer 12/inner 5` 10 volte
nella reference positiva e 8 volte nella reference zero-finger, sempre senza
inventare un logical control. Nell’attempt il driver prosegue dopo ogni
occorrenza con ulteriori comandi validi. La classificazione probatoria è quindi:

```text
COMPLETE_TRULY_MALFORMED_A0=false
VALID_OEM_CONTROL_SPECIFIC_A0_NOT_HANDLED_BY_D274=true
INCREMENTAL_PCAP_ARTIFACT=false
```

Il corrective D274 riconosce la costante solo se frame completo, direzione
host-to-device e uguaglianza byte-esatta, prima del parser checksum generico.
Non modifica il trattamento incremental/PENDING. Una regressione derivata dal
raw prova sia growing sia final; una variante con solo trailer `0x89` continua
a fallire definitivamente `MALFORMED_A0`. Sul raw autentico corretto risultano
75 eventi senza errori, quattro `OEM_FIXED_CONTROL_01`, zero cicli (atteso
prima del wizard) e observer state `OBSERVING`.

## Decisione metodologica

Il precedente metodo terminava wire-driven al terzo B0 e quindi non poteva
rispondere alla domanda sul workflow OEM completo. Il nuovo metodo:

1. cattura passivamente dall’avvio del wizard alla conferma reale Windows più
   un tail host di cinque secondi;
2. usa la conferma numerica dell’operatore sull’UI come authority di completion;
3. conta dinamicamente tutti i lifecycle esatti
   `IRQ2 → 0x22 → ACK 0x01 → fingerprint B0`, senza imporre il default
   libfprint di cinque stage;
4. registra il terzo B0 come milestone e continua;
5. non contiene sender Goodix né retry automatici.

Se una run fallisce, non viene rilanciata nella stessa invocazione. Il suo
`attempt_status.json` distingue il solo failure pre-attach/pre-wizard, per cui
un nuovo tentativo può essere ragionevole senza restore, da ogni failure dopo
attach, per cui lo stato è prudenzialmente incerto e si richiede restore.

## Attempt, snapshot e conservazione

Il marker globale è rimosso. Ogni authority specifica un
`authorized_attempt_id` distinto; la directory e `attempt.lock` sono creati
con protezione per-attempt e non vengono mai riusati, sovrascritti o rimossi.
Un failure non rende inutilizzabile il Kit, ma una nuova invocazione richiede
nuova authority/autorizzazione e nuovo ID.

La procedura preferita crea uno snapshot VM pre-run dopo aver inserito e
qualificato repository e Kit. Poiché il restore elimina anche le evidenze
create dopo lo snapshot, il runner e il manuale impongono di esportare prima,
verso storage esterno alla VM/snapshot, entrambe:

```text
captures/D279_10/<attempt_id>/raw/
captures/D279_10/<attempt_id>/sanitized/
```

## Superficie implementata

L’observer resta passivo per tutta la run e mantiene un journal JSONL
append-only. Un aumento dei cicli o il terzo B0 produce soltanto una milestone
con `stop_triggered=false`. L’arresto arriva esclusivamente da un control file
CreateNew scritto dal runner dopo conferma UI e tail. Il finalizer rilegge il
pcapng finalizzato, verifica SHA-256, operator event e durata tail, poi esporta
solo metadata di frame, conteggi e famiglie comando.

Tutti gli input interattivi passano da un solo `Read-Host` racchiuso in menu
numerici brevi. Il loop contatti non ha limite di stage assunto; resta bounded
dalla deadline host di 1200 secondi, che non è un claim su timeout device.

## Review specifica del rischio sensor-side

La mutazione host-side della VM, inclusa la prima impronta, è stata accettata
esplicitamente dall’Utente ed è registrata `true` nel template, senza che ciò
autorizzi il live; viene gestita con snapshot. La stessa soluzione non copre
il sensore.

La review delle evidenze versionate ha trovato:

- le famiglie note `0xE0`, `0xA4`, `0xF0`, `0xF4` sono già classificate come
  persistenti/manutentive;
- le stringhe statiche di `gfusb.dll` in
  `analysis/D230/work/GoodixExport/gfusb_static_refs/gfusb_strings_utf16_off.txt`
  espongono `HwAddOrUpdateTemplate`, `HwDeleteTemplate` e messaggi di scrittura
  template su flash nel dominio PBA;
- non esiste evidenza target-local che provi che il normale completamento
  Windows Hello/WBDI non raggiunga alcuna capacità sensor-side equivalente;
- l’assenza di famiglie visibili nel pcap non è prova negativa sufficiente,
  perché parte del traffico applicativo è cifrato.

Quindi l’assenza di persistenza sensor-side non può essere affermata per la run
completa. Il finalizer segnala famiglie note osservate ma, in loro assenza,
produce esplicitamente `...TEMPLATE_PERSISTENCE_NOT_EXCLUDED`. L’Utente ha ora
autorizzato il normale workflow OEM Windows Hello anche qualora persista un
template sul sensore, già usato per anni con enrollment Windows. L’authority
V2 registra questa sola accettazione a `true`, senza autorizzare una nuova run.
Restano vietati flash/IAP, ClearApp, PSK provisioning/substitution, OTP/factory
writes, cambi persistenti VID:PID/mode e comandi Goodix manuali/manutentivi.

## Verifiche offline

La suite sintetica copre completion UI, numero dinamico di cicli, terzo B0 non
terminale, mismatch operator/wire conservato come dato, tail, SHA-256,
risincronizzazione dopo contraddizione, famiglie persistenti, privacy,
observer non terminale, collisioni output, authority chiusa, soli input
numerici, ordering dei gate, attempt scope e dipendenza D274 pin.

```text
LINUX_SYNTHETIC_TESTS=18/18_PASS
AUTHORITY_TEMPLATE_CLOSED=true
GLOBAL_MARKER_PRESENT=false
ATTEMPT_SCOPED_ANTI_OVERWRITE=true
AUTOMATIC_RETRY_COUNT=0
MANUAL_GOODIX_COMMAND_PATH=false
WINDOWS_POWERSHELL_5_1_NATIVE_QUALIFICATION=PENDING_HUMAN
WINDOWS_POWERSHELL_5_1_NATIVE_STDERR_CORRECTIVE=PENDING_REAL_TARGET_RETEST
```

## Gate successivo

La nuova versione richiede prima una qualificazione nativa Windows con Goodix
assente, poi review del full SHA e una nuova authority live per-attempt. La
decisione sensor-side è acquisita ma non costituisce autorizzazione live.

```text
RESIDUAL_BLOCKER_OR_RISK=WINDOWS_NATIVE_QUALIFICATION_PENDING;NEW_LIVE_NOT_AUTHORIZED
NEXT_PRIMARY_BOUNDARY=D279_10_WINDOWS_NATIVE_QUALIFICATION_WITH_GOODIX_ABSENT
NEXT_LIVE_PREREQUISITE=FULL_SHA_BASELINE_APPROVAL_AND_EXPLICIT_PER_ATTEMPT_LIVE_DECISION
REVIEW_SET=EVIDENCE_COMMIT_98ec62b_PLUS_D279_10_A0_CORRECTIVE_KIT_TEST_REPORT_MANUAL
```
