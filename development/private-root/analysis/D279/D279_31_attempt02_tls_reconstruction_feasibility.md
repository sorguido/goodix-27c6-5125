<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/31 — fattibilità di ricostruzione TLS ATTEMPT02

## Esito

L'audit hash-gated del pcap OEM ATTEMPT02 chiude la fattibilità tecnica della
decrittazione passiva: la capture contiene tutti gli input pubblici del key
schedule e tutti i record cifrati in ordine. L'unico input crittografico
mancante è la PSK target protetta. D279/31 non la legge, non accetta un path PSK
e non decifra alcun record.

```text
OUTCOME=READY_OFFLINE_TLS_RECONSTRUCTION_FEASIBILITY_CLOSED
ADVANCEMENT=NEW_TECHNICAL_EVIDENCE_PRODUCED
EXECUTABLE_CLOSURE=PASS_HASH_GATED_METADATA_ONLY
PASSIVE_RECONSTRUCTION=FEASIBLE_WITH_AUTHORIZED_TARGET_PSK
LIVE_OR_USB_ACTION_REQUIRED=false
PSK_ACCESSED=false
RECORDS_DECRYPTED=0
```

## Evidenza

La sorgente resta il pcapng al digest
`3575ca810b969f1f248684d105c679e408ef88a0c83370387e9e90d541d10eab`.
Il parser riusa il demux USBPcap già revisionato in D274 e verifica 924
pacchetti, 442 frame target e 51 wrapper B0, ciascuno contenente esattamente un
record TLS 1.2.

La sequenza iniziale è completa e direzionalmente coerente:

```text
device→host ClientHello
host→device ServerHello (suite 0x00a8)
host→device ServerHelloDone
device→host ClientKeyExchange (identity attesa)
device→host CCS + encrypted Finished
host→device CCS + encrypted Finished
```

La suite selezionata è
`TLS_PSK_WITH_AES_128_GCM_SHA256`. Client random, server random, nonce espliciti,
type/version/length e ordine dei record sono presenti nella capture, ma i loro
byte non vengono esportati nel report. L'audit delle extension vector registra
esplicitamente `extended_master_secret_offered=false` e
`extended_master_secret_selected=false`: il key schedule target è quello TLS
1.2 classico, non EMS.

Dopo la CCS client esistono esattamente 43 record application-data
device→host, tutti lunghi 7717 byte cifrati e identici come insieme ai 43 B0
fingerprint-shape già classificati da D279/10: una baseline, 21 primari e 21
ausiliari. La numerazione record client è quindi non ambigua: Finished cifrato
sequence 0, application-data sequence 1–43. Non si osservano gap o record
application-data host→device.

## Confine privacy e sicurezza

L'audit non esporta ciphertext, random, nonce, plaintext, raster, template,
hash biometrici o secret. Legge solo la capture già versionata e produce
metadata aggregati. Nessun USB, fprintd, sudo o materiale protetto è raggiunto.

La fattibilità non autorizza l'accesso alla PSK. La PSK autentica è protected
material e la sua lettura, anche per un evaluator offline in-memory, richiede
un Human Gate esplicito. Tale futura operazione non richiede una nuova action
hardware e deve evitare qualunque persistenza di plaintext, raster, template o
secret.

## Prossimo delta offline consentito

Prima del gate si può ancora costruire e chiudere sinteticamente un evaluator
bounded che:

1. implementi il key schedule TLS 1.2 pure-PSK e AES-128-GCM con KAT indipendenti;
2. autentichi Finished e tutti i record prima di usare il plaintext;
3. decodifichi i 43 raster soltanto in memoria;
4. confronti mapping fisso, normalizzazione robusta e polarità/orientamenti
   esplicitamente enumerati tramite conteggi NBIS aggregati;
5. non serializzi input sensibili, pixel, minutiae, template o hash biometrici;
6. azzeri PSK, chiavi, plaintext e raster su successo e failure.

La sua esecuzione autentica dovrà fermarsi prima della lettura PSK fino a nuova
autorizzazione.

```text
RESIDUAL_BLOCKER_OR_RISK=PROTECTED_TARGET_PSK_REQUIRED_FOR_AUTHENTIC_OFFLINE_DECRYPTION
NEXT_PRIMARY_BOUNDARY=OFFLINE_IN_MEMORY_TLS_PSK_DECRYPTION_AND_NBIS_VARIANT_EVALUATOR_SYNTHETIC_CLOSURE
HUMAN_GATE_AFTER_NEXT_OFFLINE_CLOSURE=AUTHORIZED_PROTECTED_PSK_READ_FOR_ONE_OFFLINE_EVALUATION
CURRENT_LIVE_AUTHORIZED=false
```

Riproduzione:

```text
python3 -m unittest -v analysis.D279.test_d279_31_attempt02_tls_reconstruction_feasibility
python3 analysis/D279/d279_31_attempt02_tls_reconstruction_feasibility.py
```
