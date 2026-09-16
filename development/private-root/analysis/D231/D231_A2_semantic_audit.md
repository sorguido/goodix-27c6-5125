# D231 — audit semantico A2

## Esito

`A2_HOST_SEMANTICS=CONVERGED_SENSOR_ONLY_RESET`

Nel `gfusb.dll` target 1.1.125.14 il frame A2 osservato, body `01 14`, è
costruito da `gfresetMCUAndfingerprint(false, true, ...)`: bit 0 significa
reset del sensore, bit 1 reset software dell'MCU. Entrambi i frame A2 della
capture recuperata sono quindi richieste di reset del solo sensore. Il secondo
byte costante è `0x14` (20 decimale).

Questa è una ricostruzione host-side forte e converge byte-per-byte con la
ricostruzione indipendente riferita per `gfusb.dll` 1.1.125.13. Il body del
receiver resident 12509 non è nel corpus: non si pretende una dimostrazione
istruzione-per-istruzione device-side né un'assoluta impossibilità di effetti
NVM non documentati.

La corroborazione 1.1.125.13 è quella riportata nel prompt dalla issue
<https://github.com/Rockytkg/goodix-linux-27c6-5125/issues/1>. D231 non aveva
nel corpus né il relativo binario né un export locale della pagina; la tratta
quindi come claim esterna fornita, non come fonte primaria locale.

## Control flow locale 1.1.125.14

Funzione `gfresetMCUAndfingerprint` a `0x180069880`, ABI Win64:

- il primo booleano (`cl`, poi `[rsp+0x80]`) seleziona il reset MCU; se non è
  disponibile l'hard-reset DSM, `0x18006994e..0x180069956` fa OR con `0x02`;
- il secondo booleano (`dl`, poi `[rsp+0x88]`) seleziona il reset sensore;
  `0x18006995a..0x1800699aa` fa OR con `0x01`;
- le stringhe referenziate sono `soft reset MCU`, `reset sensor` e
  `irqstatus:0x%x`, coerenti con i due rami;
- `0x1800699c4..0x1800699da` scrive `{flag, 0x14}` e lunghezza 2;
- `0x180069a66..0x180069a7a` passa coordinate builder `r8b=0x0a`,
  `r9b=0x01` a `0x18005c148`, producendo il control wire A2; lo stesso invio
  è duplicato a `0x180069bb1..0x180069bc5` per l'altro ramo di ritorno;
- `0x180069ae4..0x180069b32` assembla tre byte di irqstatus dalla response
  area `0x18058bed8` solo se il puntatore output è fornito.

Un call-site inequivoco è `0x1800644a1..0x1800644ad`: `ecx=0`, `dl=1`,
`r8w=0x01f4`; l'eventuale secondo tentativo a `0x1800644b6..0x1800644c2`
usa gli stessi argomenti. Questo chiude la relazione tra nome, rami, flag,
serializer e caller, senza dipendere dal nome esportato soltanto.

## Evidenza wire

Capture `rilevamento.pcapng`, SHA-256
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`:

| packet | wire control | inner len | body | checksum | response |
| ---: | --- | ---: | --- | --- | --- |
| 58 | A2 | 3 | `01 14` | `f0` | ACK packet 61; typed A2 packet 63 |
| 77 | A2 | 3 | `01 14` | `f0` | ACK packet 79; typed A2 packet 81 |

La prima risposta typed arriva in 27.062 ms, la seconda in 44.703 ms dal
request; i rispettivi ACK arrivano in 0.556 ms e 17.780 ms. Sono misure di una
sola capture disponibile, non limiti universali.

## Lifetime e safety

La semantica host è una transizione runtime di reset sensore e l'uso OEM è nel
cold-start ordinario. La classificazione operativa per un replay *esatto* è
`VOLATILE_RESET_TRANSITION_WITH_NO_PERSISTENT_MUTATION_EVIDENCE`. Non viene
promossa a prova assoluta del receiver: `A2_RESIDENT_BODY_AVAILABLE=false` e
`A2_DEVICE_NVM_NONMUTATION_ABSOLUTELY_PROVEN=false`.

Un test D233 non deve fare retry cieco dopo timeout: il reset può essere stato
accettato anche senza ACK osservabile. In quel caso si interrompe, si classifica
lo stato come ambiguo e si verifica enumerazione/ripristino senza inviare altri
comandi.

## Limite di coverage

La prima capture è definitivamente perduta. D231 ha 2/2 A2 nella sola capture
recuperata, ma non può effettuare un confronto packet-level con la capture
perduta. Questo limite non viene sostituito da riepiloghi storici.
