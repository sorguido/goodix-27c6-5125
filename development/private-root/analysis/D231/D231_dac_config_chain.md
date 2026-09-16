# D231 — catena DAC/config pre-D1

## Catena ricostruita

```text
ChicagoHUsetDac
  -> ChicagoHUSetMode(7,0,0)
       -> wire 70 {14,00}
  -> ChipRegWrite 0220 <- 0bd8
  -> ChipRegWrite 0236 <- 00be
  -> ChipRegWrite 0238 <- 00bd
  -> ChipRegWrite 023a <- 00bc
orchestrazione init
  -> gf_download_config
       -> wire 90, 224-byte configuration
  -> D1
```

`DAC_CHAIN_RECONSTRUCTED=true` per il ramo normale osservato. I quattro valori
sono word little-endian della capture, non valori raccomandati per altri
dispositivi. La loro provenienza host è il contesto del sensore/OTP e non una
costante universale.

## Corrispondenza statica/capture

| fase | statico 1.1.125.14 | packet | wire/body | ACK/response |
| --- | --- | ---: | --- | --- |
| idle | `0x18002811e` -> SetMode | 82 | `70: 14 00` | ACK 85 |
| DAC0 | `0x180028227` | 87 | `80: 00 20 02 d8 0b` | ACK 89 |
| DAC1 | `0x180028292` | 90 | `80: 00 36 02 be 00` | ACK 93 |
| DAC2 | `0x1800282fd` | 94 | `80: 00 38 02 bd 00` | ACK 97 |
| DAC3 | `0x180028368` | 99 | `80: 00 3a 02 bc 00` | ACK 101 |
| config | `gf_download_config` `0x180067328` | 103 | `90`, 224 byte | ACK 111; typed 113 |
| TLS trigger | D1 builder già canonico | 114 | `d1 03 00 00 00 d7` | B0/ClientHello 117 |

I gap request→ACK osservati sono 1.813 ms per 0x70; 7.333, 0.437, 0.413 e
20.073 ms per le 0x80; 2.478 ms per 0x90. Il typed 0x90 arriva in 3.245 ms.
Sono baseline diagnostiche di una singola capture, non budget hardware.

## Confine causale

La DLL prova che 0x70 è parte di `setDac` e precede le quattro write. La capture
prova che 0x90 segue la catena DAC. Non è stata trovata una chiamata diretta da
`ChicagoHUsetDac` a `gf_download_config`; il legame è a livello di
orchestrazione init. D231 non descrive quindi l'intera sequenza come una singola
funzione né dimostra che ogni elemento sia causalmente minimo.

`0x80` e `0x90` conservano la classificazione D230 per i path studiati:
configurazione runtime/volatile, con 0x90 download/write e non read. Il gate
D232 ammette soltanto implementazione/review offline del replay byte-identico,
con live hard-disabled. Un eventuale D233 potrà usare quei valori sul dispositivo
originale solo dopo review D232 positiva, verifica identità/precondizioni,
accettazione umana del rischio e autorizzazione separata; sintesi, calibrazione
alternativa e riuso cross-device restano vietati.
