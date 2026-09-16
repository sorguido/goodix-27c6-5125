<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/32 — primitive TLS 1.2 PSK per ricostruzione offline

## Esito

È disponibile una primitive offline bounded per il profilo
`TLS_PSK_WITH_AES_128_GCM_SHA256`: premaster pure-PSK RFC 4279, PRF SHA-256,
master/key-block TLS 1.2, chiavi/IV client e server, autenticazione record GCM e
verifica Finished. Il modulo non apre file, non conosce path production e non
espone una CLI che accetti secret; nessun materiale target è stato letto.

```text
OUTCOME=READY_OFFLINE_TLS12_PSK_DECRYPT_PRIMITIVE
ADVANCEMENT=MATERIAL_EXECUTABLE_CRYPTOGRAPHIC_BOUNDARY
EXECUTABLE_CLOSURE=PASS_SYNTHETIC_INDEPENDENT_OPENSSL
TARGET_PSK_ACCESSED=false
ATTEMPT02_RECORD_DECRYPTED_COUNT=0
LIVE_OR_USB_ACTION_COUNT=0
```

## Contratto e failure behavior

Il key schedule accetta soltanto PSK di 32 byte, random TLS di 32 byte e le
quattro label necessarie. Supporta esplicitamente due profili distinti:

- master secret TLS 1.2 classico da `client_random || server_random`, richiesto
  dal transcript OEM ATTEMPT02 che non offre Extended Master Secret;
- Extended Master Secret da session hash SHA-256, usato dal KAT OpenSSL moderno.

Non esiste fallback fra i due profili: il futuro composer dovrà selezionare
quello osservato nel ClientHello/ServerHello e fallire su mismatch.

AES-128-GCM richiede chiave/IV esatti, sequence number bounded, content type
allowlisted, versione `0x0303`, nonce esplicito e tag. PSK errata, sequence
errata o record modificato terminano in `TLS_GCM_AUTHENTICATION_FAILED`.
Finished client/server è confrontato constant-time con il transcript hash.

I buffer owned dal modulo (`premaster`, master, key-block, chiavi e IV) sono
mutabili e azzerati su successo/failure/close idempotente. La libreria
`cryptography`/OpenSSL può creare copie interne non osservabili dal chiamante:
la loro assenza o zeroizzazione non viene dichiarata provata. Non esiste
persistenza su disco.

## Verifica indipendente

Il test costruisce una handshake reale tramite due `ssl.MemoryBIO` OpenSSL,
callback PSK sintetiche e TLS 1.2 ristretto a `PSK-AES128-GCM-SHA256`. Il
transcript moderno negozia EMS e può inviare NewSessionTicket fra le Finished;
il test deriva le chiavi indipendentemente, autentica entrambe le Finished e
recupera l'application-data client. Questo ha rilevato e corretto durante lo
step la differenza EMS rispetto al target OEM non-EMS.

Quattro test passano:

1. PRF SHA-256 classica contro un vector prodotto da `openssl kdf TLS1-PRF`;
2. handshake/Finished/application-data OpenSSL indipendente con EMS;
3. PSK e sequence errate respinte dal tag GCM;
4. owner mutabile azzerato e close idempotente.

## Limite e prossimo step

D279/32 non è ancora un evaluator ATTEMPT02. Manca la composizione fail-closed
fra il parser hash-gated D279/31, il profilo non-EMS osservato, l'autenticazione
di entrambe le Finished, i 43 plaintext in memoria, il decoder APP12509 e il
runner NBIS delle varianti. Questi restano lavoro offline consentito.

```text
RESIDUAL_BLOCKER_OR_RISK=ATTEMPT02_PROFILE_COMPOSITION_IMAGE_DECODER_NBIS_AGGREGATOR_AND_PROTECTED_LOADER_NOT_YET_CLOSED
NEXT_PRIMARY_BOUNDARY=OFFLINE_ATTEMPT02_DECRYPTION_IMAGE_DECODE_AND_NBIS_VARIANT_EVALUATOR_SYNTHETIC_CLOSURE
CURRENT_LIVE_AUTHORIZED=false
```

Riproduzione:

```text
python3 -m unittest -v analysis.D279.test_d279_32_tls12_psk_decrypt
```
