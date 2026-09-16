# D231 — audit semantico del comando 0x70

## Esito

`CMD70_HOST_SEMANTICS=CONVERGED_SETMODE_IDLE`

Nel `gfusb.dll` target 1.1.125.14 il body `{14,00}` è emesso dal ramo
`ChicagoHUSetMode(7,0,0)`, con log `setmode: idle`. La chiamata è la prima
operazione di `ChicagoHUsetDac`, prima delle quattro write di registro. Il frame
wire della capture coincide esattamente.

La corroborazione 1.1.125.13 proviene dalla issue indicata nel prompt,
<https://github.com/Rockytkg/goodix-linux-27c6-5125/issues/1>; binario e pagina
non sono archiviati nel corpus D231, perciò il peso primario resta alla DLL
1.1.125.14 e alla capture locali.

## Costruzione del comando

`ChicagoHUSetMode` inizia a `0x180024c90` e salva `mode`, `type`, `base_type`
dai registri `cl`, `dl`, `r8b`. Il dispatch di `mode==7` porta a
`0x180025641`; quel ramo:

- referenzia la stringa `setmode: idle`;
- scrive body[0] `0x14` a `0x180025686`;
- scrive body[1] `0x00` a `0x1800256b4` e lunghezza 2 a `0x1800256bc`;
- passa `r8b=7`, `r9d=0` al builder A0 `0x18005c148` a
  `0x1800256f5..0x180025705`, ottenendo control wire `0x70`.

Il builder configura 200 ms a `0x1800256d6`; la capture mostra un ACK B0 in
1.813 ms e nessuna response typed 0x70 prima del comando successivo. Questo è
coerente con una transizione di modo con ACK, non con un readback.

## Call chain DAC

La tabella operazioni sensore assegna `ChicagoHUsetDac` a `+0x13d38` a
`0x180026c31` e `ChicagoHUSetMode` a `+0x13d30` a `0x180026c57`.
`ChicagoHUsetDac` (`0x180027ed0`) carica quattro word dai campi contesto
`+0x5200,+0x5202,+0x5204,+0x5206`; può applicare la correzione runtime
`+0x13d98`, con log relativi a DAC/OTP.

A `0x180028100..0x18002811e` invoca il puntatore SetMode con `(7,0,0)`. Nel
ramo normale (`0x180576db3==0`) seguono, nell'ordine:

1. `ChipRegWrite(0x0220, value0, 2, 100)` a `0x180028227`;
2. `ChipRegWrite(0x0236, value1, 2, 100)` a `0x180028292`;
3. `ChipRegWrite(0x0238, value2, 2, 100)` a `0x1800282fd`;
4. `ChipRegWrite(0x023a, value3, 2, 100)` a `0x180028368`.

Il ramo alternativo usa un package 0x98 e non è quello osservato. Il download
config 0x90 è una fase separata dell'orchestrazione (`gf_download_config` a
`0x180067328`), non una chiamata diretta interna a `ChicagoHUsetDac`.

## Evidenza wire e lifetime

Nella capture recuperata packet 82 è wire 0x70, inner length 3, body `14 00`,
checksum `23`; packet 85 è ACK. Seguono esattamente le write 0x80 ai registri
`0220,0236,0238,023a` e poi il 0x90.

La classificazione operativa è
`VOLATILE_IDLE_MODE_TRANSITION_WITH_NO_PERSISTENT_MUTATION_EVIDENCE`. Il nome,
il dispatch, il caller DAC, la versione 1.1.125.13 riferita e il wire convergono.
Resta `CMD70_RESIDENT_BODY_AVAILABLE=false`: non si afferma una prova assoluta
device-side dell'assenza di side effect persistenti.

La prima capture è definitivamente perduta; la coverage wire è quindi 1/1
delle capture disponibili e non 2/2 storiche.
