# D268/01 — Readiness Kit Operatore first-image

## Esito

```text
OUTCOME=READY — D268_01_FIRST_IMAGE_OPERATOR_KIT_READY_OFFLINE
ADVANCEMENT=NEW_LIVE_CRITICAL_OPERATOR_PATH_WITH_CORRECTED_DECODER_AND_TYPED_DIAGNOSTICS
EXECUTABLE_CLOSURE=PASS
RESIDUAL_BLOCKER_OR_RISK=NEW_D268_BASELINE_NOT_YET_APPROVED_AND_LIVE_NOT_AUTHORIZED
CANONICAL_DOCUMENTATION=UPDATED
D267_03_MANIFEST_HISTORY_RESTORED=true
BASELINE_APPROVED=false
LIVE_AUTHORIZED=false
READY_FOR_LIVE=false
```

D268/01 è stato eseguito esclusivamente offline. Nessun USB, secret reale,
TLS live, comando device, marker reale, fprintd o write persistente è stato
raggiunto.

## Repository hygiene e authority

`analysis/D267/D267_03_live_critical_manifest.json` è byte-identico al blob
del commit `42af60107cf21eb610de867a6de05b774ec1e37f`. Il file torna a essere
lo snapshot storico D267/03; non sono stati modificati altri artefatti
D267/03. Il current set è esclusivamente
`analysis/D268/D268_01_live_critical_manifest.json`, composto dai 20 file
derivati dalla call graph produttiva e comprendente `core/post_d4.py` con la
semantica D267/04. Il manifest dichiara `baseline_approved=false`,
`live_authorized=false` e `ready_for_live=false`.

## Nuovo Kit D268

Il percorso esclusivo è:

```text
operator_kit/d268-first-image-once.sh
  -> tools/d268_live_first_image_once.py
  -> core/d268_first_image_operator.py
```

Flag live, environment della baseline, capability e nonce, marker e report
sono D268 e incompatibili con D267. Il live futuro richiede il flag D268
esatto e un commit SHA lowercase completo esplicitamente approvato; il verifier
richiede inoltre `HEAD == SHA`, worktree pulito, path-set esatto e identità
byte commit/worktree. Nessuna SHA è stata auto-approvata.

Il path terminale resta:

```text
cold start -> TLS -> D4 -> AF -> fresh FDT -> IRQ2 -> un solo 0x22
-> ACK validato -> primo B0 -> TLS retained -> parse_image_payload()
-> prima immagine oppure failure diagnostica -> stop/cleanup
```

Le regressioni provano un solo tentativo `0x22`, zero retry, recovery, reopen,
write persistenti e comandi post-image vietati. La semantica decoder non è
stata modificata in D268: `0x88` usa soltanto la policy image-specific
`NO_CHECK_0X88_ACCEPTED`; i trailer ordinari richiedono
`ADDITIVE_VERIFIED` e il CRC record resta sempre fail-closed.

## Diagnostica e interazione operatore

Messaggi, istruzioni dito e cause human-facing sono in italiano. Il riepilogo
espone separatamente:

```text
FIRST_IMAGE_DECODE_STATUS
FIRST_IMAGE_DECODE_STAGE
FIRST_IMAGE_DECODE_EXCEPTION
FIRST_IMAGE_PAYLOAD_TRAILER_CLASS
FIRST_IMAGE_PAYLOAD_CHECKSUM_POLICY
FIRST_IMAGE_PAYLOAD_CHECKSUM_MATCH
FIRST_IMAGE_RECORD_CRC_MATCH
FIRST_IMAGE_RASTER_SHAPE
```

Il report non contiene B0 raw, plaintext TLS, image bytes, raster/pixel,
materiale biometrico, PSK/secret o hash di plaintext sensibile. L'operatore
non deve eseguire Python direttamente, inviare comandi USB manuali o bypassare
il launcher.

## Executable closure e test

- launcher `bash -n`: PASS;
- import/PYTHONPATH e import-time purity: PASS;
- `--dry-run` dalla Git root: PASS, sette contatori reali a zero;
- `--dry-run` da `/tmp`: PASS, sette contatori reali a zero;
- flag live privo di full SHA: fail-closed prima di dipendenze produttive, con
  causa in italiano e sette contatori reali a zero;
- regressioni mirate D263/D266/D267/D268: 94/94 PASS;
- discovery completa: 338 test, 334 PASS, 1 FAIL e 3 ERROR nelle quattro
  classi storiche D261/assenza pytest; zero failure nuove D268.

## Riesame metodologico pre-live

1. **Cosa cambia realmente rispetto a D267/01?** Decoder image-specific
   `0x88` corretto secondo evidenza OEM locale, diagnostica tipizzata del
   predicato interno e nuova authority/Kit D268.
2. **Quale nuova ipotesi viene testata?** Una futura run discriminerà se la
   failure D267/01 dipendeva dalla policy additiva `0x88` oppure da
   framing/lunghezza, control/POV, CRC o altra classe tipizzata. Il trailer
   D267/01 resta `UNKNOWN`.
3. **Se fallisce di nuovo nello stesso boundary?** La classe diagnostica
   guiderà il corrective successivo. Se il record fosse assente od opaco, si
   correggerà offline il reporting senza ripetere immediatamente il live.

Il riesame non approva una baseline e non autorizza hardware.
