<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/58 — IRQ0100 authentic OEM flags corrective

## Trigger

La seconda run live D279/57, eseguita one-shot sul full SHA
`d94c7af192bb3f0d0cb4ed7b411d099d73902e3b`, ha superato il nuovo
contact/release boundary del primo stage ma si è arrestata fail-closed
durante il secondo ciclo con:

```text
A0 mismatch: expected IRQ0100, observed control 0x36 IRQ 0x0100 flags 0x003f
```

La run non è stata ripetuta. Il grant è consumato.

## Root cause review

Il riesame diretto dell'evidenza autentica D279/10 ATTEMPT02 ha verificato
nel PCAP OEM che `IRQ0100` usa la forma target-local:

```text
control = 0x36
irq     = 0x0100
flags   = 0x003f
```

Il binding production D279/14 richiedeva invece erroneamente:

```text
control = 0x36
irq     = 0x0100
flags   = 0x0000
```

L'audit storico D279/10 classificava control e IRQ ma non validava il campo
flags; le fixture sintetiche D279/14 avevano poi incorporato `0x0000`,
auto-convalidando l'assunzione errata.

Classificazione:

```text
ROOT_CAUSE=HISTORICAL_TARGET_LOCAL_MODELING_ERROR
LIVE_VALUE_MATCHES_AUTHENTIC_OEM=true
PARSER_RELAXED=false
EXPECTED_IRQ0100_FLAGS=0x003f
```

## Corrective

Il matcher production continua a essere strict/fail-closed. Non viene
introdotta alcuna mask o accettazione permissiva: il solo valore atteso per
l'IRQ0100 enrollment target-local viene corretto da `0x0000` a `0x003f`.

Sono aggiornate coerentemente:
- production `goodix_enrollment_post_tls_events.c`;
- fixture D279/14;
- fixture production-shaped FpImageDevice;
- documentazione D279/14.

IRQ2 e IRQ0200 restano invariati.

## Independent offline verification

Eseguiti localmente dall'operatore dopo il correttivo:

```text
D279_14_NORMAL=PASS
D279_14_ASAN_UBSAN=PASS
D279_14_INBOUND_ONLY_SOURCE_AUDIT=PASS
D279_17_SYNTHETIC_SINK_SOURCE_AUDIT=PASS
REAL_USB_ACCESS=0
REAL_USB_SUBMIT=0

Sanitizer test run: PASS
D279_20_DORMANT_CONTEXT_OWNERSHIP_AND_DRAIN=PASS
D279_24_CONTEXT_FIRST_ARM_ENROLLMENT_HANDOFF=PASS
D279_57_SIGFM_STAGE8_CONTEXT_TRANSCRIPT=PASS
D279_57_LEGACY_21_STAGE_FIXTURE_RETIRED=PASS
D279_28_PRODUCTION_ENROLLMENT_GRAPH_BOUND=PASS
D279_28_PRODUCTION_OPEN_EPOCH_ACTION_MAX=1
D279_20_REAL_USB_SUBMIT=0
```

## Addendum D279/59 — claim superseded

Il modello exact-value di questo correttivo è **superato** dall'audit completo
D279/59. Il valore OEM `0x003f` osservato resta un fatto autentico, ma non è
unico: i flags di contatto sono un bitfield a sei canali. La successiva live
one-shot sul full SHA `4de9c342b4d2d59aa37cf333638f3f88350547ea`
ha infatti osservato `IRQ2/control 0x32/flags 0x002f` dopo il primo re-arm.

La correzione corrente non ignora i flags e non usa wildcard: accetta solo un
sottoinsieme **non nullo** di `0x003f` per finger-down/contact-sample, richiede
zero esatto per bootstrap baseline e finger-up, rifiuta tutti i bit riservati
e usa il bitfield nella derivazione FDT-up. D279/58 resta quindi provenance del
secondo failure live e del sintomo corretto, non autorità sulla policy attuale.

## Boundary

Questa correzione non prova ancora:
- completion reale degli 8 stage;
- terminale stage-8 senza nono re-arm;
- reusability/template persistence/fprintd integration.

Una nuova run live richiede nuovo full SHA, nuovo prepared build, nuovo
grant one-shot e nuova Human Gate authorization.

```text
D279_58_OUTCOME=READY_OFFLINE
LIVE_OR_USB_ACTION_DURING_CORRECTIVE=0
CURRENT_LIVE_AUTHORIZED=false
NEXT_PRIMARY_BOUNDARY=NEW_ONE_SHOT_D279_57_STAGE8_LIVE_ON_CORRECTED_FULL_SHA
```
