# D246 — post-TLS D4 boundary

## Decisione

`D246_D4_FACTORY_PRESERVING_CONTINUATION_READY_NOT_EXECUTED`

Il gate è superato. Il D4 esatto è ricostruito su callsite host, serializer,
capture primaria e receiver APP12509; per quel solo path gli effetti sono
volatili in SRAM e la persistenza host/device è esclusa con evidenza sufficiente.
La continuazione è implementata come patch offline e verificata, ma non è stata
eseguita live. Le sorgenti canoniche restano sigillate e la baseline live è
`PENDING_USER_REVIEW`.

## Riesame metodologico pre-live

1. **Cosa cambia realmente:** D246 non ripete il tentativo E4/TLS. Assume il
   successo D245 validato e isola una sola nuova azione: D4, poi stop.
2. **Nuova ipotesi:** il primo comando OEM dopo il TLS Finished è una
   inizializzazione volatile di sessione, ricostruibile esattamente e senza
   effetti persistenti.
3. **Se il gate fallisse:** nessun unseal/launcher live; si identifica la fonte
   primaria mancante sul tratto host→wire→receiver e si arresta, senza ripetere
   il live nello stesso punto.

## Validazione dell'evidenza D245

Fonte primaria locale:
`analysis/D245/D245_operator_live_stdout.json`, SHA-256
`2992457855197b90dad3f7048bef85a6703079b95452dc07fa8e201a5c294e09`.

I campi sono coerenti e non attivano il blocker del prompt:

| Campo | Valore verificato |
| --- | --- |
| `result` | `pass` |
| `d245_result` | `TLS_CRYPTOGRAPHIC_HANDSHAKE_COMPLETED_STOP_BEFORE_D4` |
| A8 | ACK `07`, response osservata, FW12509 `match` |
| E4 | runtime PSK/E4 binding `match` |
| sequenza | pre-D1 e D1 completati, terminale `TLS_HANDSHAKE_OK` |
| TLS | un solo handshake, completato |
| esclusioni | D4 0, application data 0, retry 0, persistent-write family 0 |
| chiusura | cleanup 1, fprintd/segnali restored, source seal `sealed` |
| failure | `none` |

Il preflight D245 locale ha SHA-256
`715f253652c9bb0df491878ded84964b5d5dcaff03b7a0da5f8e291259ef8c96`
ed è coerente con la run. I due file D245 preesistenti non sono stati modificati.

## Sequenza causale stretta

Fonte packet-level: capture D230 `rilevamento.pcapng`, SHA-256
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`.
Fonte host: `gfusb.dll`, SHA-256
`904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2`.

| Ordine | Evidenza |
| --- | --- |
| 1 | frame 134: completion dell'OUT host TLS Finished |
| 2 | frame 136: primo comando post-handshake, A0/D4 |
| 3 | frame 138: ACK B0 con echo D4 e status `01` |
| 4 | frame 140: successivo A0/AF, fuori scope e non raggiungibile |

Wire contract D4:

```text
direction              H→D
protocol               A0 plaintext post-TLS (non TLS application_data)
major/subtype           0xd / 2, wire control d4
logical frame           a00600a6d403000000d3 (10 byte; body 0000)
physical submission     un solo OUT da 64 byte, tail 54 byte tutti zero
host pacing             Sleep(20) prima del D4
bounded timeout         200 ms
ACK                     a00600a6b00300d40122 (echo d4, status 01)
typed response          nessuna osservata; nessuna seconda read autorizzata
terminal                STOP_AFTER_D4
```

Il submit D4 segue la completion host Finished di circa 53,154 ms; l'ACK segue
D4 di circa 1,043 ms. Il tempo catturato include overhead host e non sostituisce
il pacing esplicito di 20 ms nel callsite.

## Traccia semantica e side effect

- Il caller DLL primario `0x18001f16b`, nel percorso handshake/init dopo stato
  `0x10`, esegue `Sleep(20)` e chiama il builder `0x18001c46c`.
- Il builder seleziona major `0xd`, subtype `2`, body zero di due byte e inoltra
  al generic A0; il caller usa un budget di 200 ms.
- Il dispatcher APP12509 `0x08035e3c` instrada D-family al receiver presente
  `0x080396b0`.
- Il branch subtype 2 a `0x0803987c` scrive zero in SRAM `0x20000790`.
- La coda comune legge un bit volatile con `0x0802e144` e setta/pulisce un bit
  in SRAM a `0x20006d3c+5`.
- Nel branch esatto non risultano target o chiamate flash/IAP, OTP, factory
  data, configurazione persistente, provisioning o enrollment.

Classificazione:

```text
D246_D4_SEMANTIC_CLASS=VOLATILE_SESSION_INITIALIZATION
D246_HOST_SIDE_NO_PERSISTENT_WRITE_OBSERVED=true
D246_DEVICE_SIDE_PERSISTENCE_EXCLUDED_WITH_SUFFICIENT_EVIDENCE=true
D246_SCOPE=EXACT_APP12509_D4_RECEIVER_PATH_ONLY
```

La conclusione non è una prova globale sui receiver resident mancanti, su AF o
su firmware diversi. Esclude la persistenza con sufficienza per il solo path D4
esatto che D246 implementa.

## Implementazione offline

`D246_d4_continuation.patch` si applica dopo la patch D245 soltanto in un albero
temporaneo. Estende il percorso A8→E4→pre-D1→D1→TLS con:

- precondizioni TLS completo una volta, fase esatta, buffer RX vuoto e identità
  stabile;
- pacing D4 una volta, frame byte-pinned, unico OUT fixed-64 zero-tail;
- una sola read ACK bounded, ammesso esclusivamente body `d4 01`;
- zero response D4, zero retry e terminale `STOP_AFTER_D4`;
- cleanup/restore/reseal invariati per successi, timeout e dati inattesi.

`operator_kit/d246-live-d4-once.sh` è deliberatamente offline-only. Accetta
soltanto `--offline-dry-run`; ogni altra invocazione termina con exit 64 e
`BLOCKED_LIVE_BASELINE_APPROVAL_PENDING_USER_REVIEW`. Non contiene un percorso
capace di aprire USB reale.

## Verifica

La closure applica D245+D246 in una directory temporanea, compila le due
sorgenti patchate, esegue la matrice sintetica e verifica che sorgenti canoniche,
hash e source seal siano invariati.

| Test | Esito |
| --- | --- |
| T1 regressione D245 fino a TLS | PASS, stall TLS e D4 count 0 |
| T2 happy D4 una volta | PASS, fixed-64 zero-tail, ACK `d4/01`, stop |
| T3 timeout D4 | PASS, bounded, zero retry, cleanup/reseal |
| T4 ACK inatteso | PASS, fail-closed |
| T5 nulla dopo D4 | PASS, AF non raggiungibile |
| T6 launcher da cwd reale e `/tmp` | PASS |
| invocazione non-dry-run | BLOCKED, exit 64 |

Telemetria reale della verifica: USB open 0, TLS handshake 0, D4 send 0,
persistent-write family 0. L'unico D4 completato è sintetico e vive nel tree
temporaneo.

## Residui

- D4 non è stato eseguito live in D246.
- La baseline SHA completa del live-critical set deve essere approvata
  esplicitamente dopo review; non è stata inventata o auto-approvata.
- AF, prima azione successiva nella capture, non è semanticamente classificato
  e resta irraggiungibile.
- L'esclusione device-side non si estende oltre il receiver D4 APP12509 esatto.
- Nessun raw proprietario, secret, PSK, payload TLS privato o dato biometrico è
  incluso negli output D246.
