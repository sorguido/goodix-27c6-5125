# D231 — decisione di safety e gate PRE-D1

## Decisione

`D231_DECISION=D231_PRE_D1_CLEARED_FOR_EXACT_OEM_REPLAY`

`PRE_D1_PATH_CLEARED_FOR_EXACT_OEM_REPLAY=true` **solo** per la sequenza
byte-identica OEM del dispositivo originale. È l'ingresso a D232, che è
implementazione/review esclusivamente offline con live hard-disabled. Non
autorizza esecuzione live, non crea un operator kit e non abilita varianti,
retry, provisioning o uso cross-device.

## Perché il gate ristretto si chiude

1. A2 è chiuso host-side come `ResetMCUAndFingerprint(0,1)` con flag sensore
   `0x01`, costante `0x14`, due match wire identici e response typed.
2. 0x70 è chiuso host-side come `ChicagoHUSetMode(7,0,0)`, `setmode: idle`,
   body `{0x14,0x00}`, chiamato prima delle quattro DAC write.
3. Le ricostruzioni riferite per 1.1.125.13 convergono con la DLL target
   1.1.125.14 e con la capture, indipendentemente per nome, flag, argomenti,
   body e ordine DAC.
4. Il materiale PSK autentico è canonicamente portato e validato E4 per
   l'originale laptop/sensore; la DLL locale conferma la copia diretta
   plaintext→runtime PSK→TLS senza secondo KDF.
5. Il replay è il cold-start OEM osservato e non raggiunge alcun path noto di
   erase, IAP, boot change, provisioning o persistent write.
6. D231 definisce timeout, abort, stato ambiguo e recovery fail-closed per
   l'implementazione/review offline D232 e l'eventuale D233 successivo.

## Limiti che restano veri

- i body resident A2 e 0x70 non sono disponibili;
- l'assenza assoluta di effetti NVM interni non è dimostrabile istruzione per
  istruzione; la safety è una classificazione operativa convergente per exact
  OEM replay, non una proprietà universale degli opcode;
- la prima capture è definitivamente perduta: la coverage proof ha una sola
  capture packet-level disponibile;
- la claim esterna 1.1.125.13 è registrata come corroborazione fornita dal
  prompt; il relativo binario non è nel corpus locale;
- `LIVE_TLS_HANDSHAKE_VERIFIED=false` e D231 non ha eseguito hardware;
- `PSK_PORTABILITY_STATUS=PSK_PORTABILITY_PROVEN`, con
  `PORTABILITY_SCOPE=ORIGINAL_DEVICE_AND_LEGITIMATELY_EXPORTED_MACHINE_BOUND_MATERIAL_ONLY`;
  la portabilità non è generalizzabile.

## Handoff D232/D233

```text
D231
  -> decisione statica chiusa

D232
  -> implementazione/review OFFLINE
  -> exact OEM replay
  -> live hard-disabled
  -> allowlist byte-pinned
  -> abort/timeout matrix D231
  -> no automatic invasive recovery

D233
  -> eventuale LIVE single-shot
  -> richiede review positiva di D232
  -> richiede accettazione umana esplicita del blast radius
  -> richiede autorizzazione separata
```

`D233_RISK_MODEL_READY_FOR_HUMAN_ACCEPTANCE=yes`, ma
`D233_OPERATOR_RISK_ACCEPTANCE=not_granted` e
`D233_AUTOMATIC_RESET_ON_FAILURE=forbidden`. D233 è `NOT_AUTHORIZED`.

Qualsiasi differenza di versione, hash, body, ordine, DAC/config, identity,
validator, suite, response o stato di enumerazione riapre il gate come
`PRE_D1_PATH_CLEARED_FOR_EXACT_OEM_REPLAY=false` fino a nuova review.

## Confine D230

D231 non riapre né contraddice D230:
`SAFE_RESIDENT_READBACK_ROUTE_STATUS=EXHAUSTED_IN_LOCAL_CORPUS`. La convergenza
host-side permette di classificare l'exact OEM replay senza estrarre il
resident; non dimostra l'esistenza di un readback arbitrario.
