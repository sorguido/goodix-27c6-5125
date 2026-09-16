# D231 — audit derivazione e portabilità PSK

## Esito

`PSK_PORTABILITY_STATUS=PSK_PORTABILITY_PROVEN`

`PORTABILITY_SCOPE=ORIGINAL_DEVICE_AND_LEGITIMATELY_EXPORTED_MACHINE_BOUND_MATERIAL_ONLY`

La portabilità rilevante per la roadmap D232/D233 è già attestata canonicamente
per il laptop e sensore originali: il materiale legittimo è stato esportato localmente,
importato in uno store Linux root-only e ha prodotto una singola E4 read-only
`MATCH` (risultato hash-pinned). Non esiste invece una procedura generale per
derivare o sostituire la PSK su un'altra macchina/dispositivo.

D231 ha ri-derivato dalla DLL locale il tratto DPAPI→buffer runtime→TLS. Gli
artefatti privati storici D189–D206 non sono presenti nel checkout corrente;
le loro conclusioni vengono quindi usate esclusivamente tramite le claim
canoniche in `README.md` e `docs/EVIDENCE.md`, senza fingere una nuova verifica
dei blob o del secret.

## Catena di valore

```text
Goodix_Cache.bin
  -> DPAPI machine-scope CryptUnprotectData
  -> plaintext out A (32 byte)
       -> KDF_OEM(out A) -> validator E4
       -> copia diretta a 0x180576e50, len a 0x180576e70
            -> TLS setup usa pointer 0x180576e50 + stessa len
            -> TLS 1.2 pure PSK / 0x00a8 / Client_identity
```

La DLL importa `CryptProtectData` e `CryptUnprotectData`; i call wrapper sono a
`0x18000be03` e `0x18000c11c`. La stringa `Goodix_Cache.bin` è presente insieme
ai path globali `ProgramData\Goodix`.

Il consumer riuscito copia il buffer recuperato:

- `0x18003b942..0x18003b946`: length → `0x180576e70`;
- `0x18003b94c..0x18003b964`: source plaintext → `0x180576e50` con quella
  stessa length.

Il setup TLS a `0x180058f8c` rilegge la length; a
`0x180059020..0x180059038` passa `r9d=length` e `r8=&0x180576e50` a
`0x180058438`. La configurazione contiene il path `mbedtls_ssl_conf_psk` e la
suite `0x00a8`; `Client_identity` è presente nella DLL. Non è visibile un
secondo KDF OEM fra area pubblicata e PSK TLS.

## Audit dei vincoli post-recupero

Le importazioni PE mostrano DPAPI, ma nessuna importazione `NCrypt`, TPM/TBS o
un challenge hardware nel tratto pubblicazione→TLS. Le occorrenze testuali di
“Challenge” appartengono alle operazioni di produzione/PMK e non sono nel
dataflow TLS appena descritto. Pertanto il binding macchina è il confine di
protezione del contenitore Windows; una volta recuperato legittimamente `out A`,
il consumer TLS usa i byte direttamente.

Questa assenza è una conclusione statico-corpus-bounded, non una garanzia su
versioni OEM diverse. Il secret non è stato letto, stampato, copiato o incluso
negli artefatti D231.

## Confini precisi

- `validator = KDF_OEM(out A)`; il validator non è la PSK.
- `PSK_TLS = out A`; nessun default/zero/replacement PSK è valido.
- suite `TLS_PSK_WITH_AES_128_GCM_SHA256` (`0x00a8`), identity
  `Client_identity`, device client, host server.
- l'E4 MATCH dimostra il materiale originale su quel dispositivo soltanto.
- `LIVE_TLS_HANDSHAKE_VERIFIED=false`: sintesi e capture Windows non sono un
  handshake Linux reale completato.
- nessun provisioning o write di key è autorizzato.
