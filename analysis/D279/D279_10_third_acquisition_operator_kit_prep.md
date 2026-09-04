<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/10 — preparazione operator kit terza acquisizione

## Esito offline

```text
D279_10_OUTCOME=READY_OFFLINE_PENDING_WINDOWS_NATIVE_QUALIFICATION
ADVANCEMENT=MATERIAL_REPOSITORY_ADVANCEMENT
EXECUTABLE_CLOSURE=PASS_LINUX_SYNTHETIC;WINDOWS_NATIVE_PENDING
REAL_TARGET_EXECUTION=false
USB_ACCESSED_BY_AI=false
AUTHENTIC_CAPTURE_ACCESSED_BY_AI=false
LIVE_AUTHORIZED=false
```

Baseline di partenza: `1cc2b83` (`D279/09`). Il Kit e in
`operator_kit/d279-10-third-acquisition-observe/`.

## Decisione metodologica

D279/09 ha reso esplicito che il default libfprint di cinque stage non e
authority target e che il lifecycle locale termina al secondo B0. Il prossimo
fatto minimo non viene cercato estendendo alla cieca il sender Linux: il Kit
osserva passivamente il workflow OEM Windows e non invia comandi Goodix.

Risposte pre-live obbligatorie:

1. il metodo cambia da stop Linux al secondo B0 a osservazione OEM passiva fino
   al terzo edge;
2. viene testata l'ipotesi che il release-tail/re-arm gia provato fra prima e
   seconda acquisizione si ripeta dopo la seconda, nella stessa sessione;
3. al medesimo failure non segue un retry: si classifica la singola traccia e
   si effettua replan.

## Superficie implementata

Il sanitizer riusa soltanto il parser pcapng/USBPcap e i classificatori di
framing D274/03 gia revisionati. La sequenza D274 fino al secondo B0 e un
prefisso obbligatorio. Il delta D279/10 richiede poi quindici eventi ordinati,
dal secondo release `0x34` al terzo B0. Sono ammessi interposti FDT/housekeeping
non appartenenti al lifecycle; un evento lifecycle confliggente fallisce
chiuso. Il growing observer produce il segnale terminale metadata-only; il
finalizer verifica raw SHA-256, frame terminale identico e assenza di un quarto
ciclo completo o contraddittorio. Failure e deadline dell'observer lasciano un
segnale metadata-only la cui classe viene propagata al runner.

Il launcher PowerShell 5.1 ha tre modalita: self-test, qualificazione nativa
con target assente e futuro live hard-gated. Authority, full SHA, branch
`development`, live-critical set pulito, same-run target absence, marker
CreateNew, privacy ACL, deadline e cleanup sono verificati prima/durante la
run. La qualifica registra full HEAD/branch e richiede gia il live-critical set
pulito, rendendo il suo PASS attribuibile. Il template authority e chiuso.

## Verifiche

Quattordici test sintetici coprono successo, sequenza incompleta/malformed,
ACK errato, FDT interposto, quarto ciclo, hash, growing observer, collisione
output e concordanza observer/finalizer. Non leggono il raw D274 autentico.

```text
LINUX_SYNTHETIC_TESTS=14/14_PASS
AUTHORITY_TEMPLATE_CLOSED=true
AUTOMATIC_RETRY_COUNT=0
MANUAL_GOODIX_COMMAND_PATH=false
WINDOWS_POWERSHELL_5_1_NATIVE_QUALIFICATION=PENDING_HUMAN
```

## Rischio e gate successivo

Il numero di contatti dopo il quale Windows/OEM persiste l'enrollment host non
e target-provato. Il terzo contatto puo quindi mutare lo stato account prima
dello stop wire-driven. Questo non viene rappresentato come no-commit certo:
il futuro live richiede un'accettazione esplicita separata del rischio. Prima
di qualunque baseline/live serve inoltre la qualificazione nativa innocua con
Goodix assente.

```text
RESIDUAL_BLOCKER_OR_RISK=WINDOWS_NATIVE_QUALIFICATION_PENDING;HOST_ENROLLMENT_COMMIT_EDGE_UNKNOWN
NEXT_PRIMARY_BOUNDARY=D279_10_WINDOWS_NATIVE_QUALIFICATION_WITH_GOODIX_ABSENT
NEXT_LIVE_PREREQUISITE=AI_PM_REVIEW_THEN_FULL_SHA_BASELINE_APPROVAL_AND_EXPLICIT_ONE_SHOT_RISK_ACCEPTANCE
REVIEW_SET=BASELINE_1cc2b83_PLUS_D279_10_KIT_TEST_REPORT_MANUAL
```
