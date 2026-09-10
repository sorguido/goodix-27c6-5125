<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D280/01 — riuso FP3 effimero attraverso close/open

## Stato e scopo

Questo kit prepara una sola run composta da **due action esplicite** sul
Goodix `27c6:5125`: enrollment SIGFM a otto contatti, quindi identify dello
stesso dito dopo un vero `close`/`open`. È il primo boundary live che può
provare insieme riutilizzabilità del template autentico e continuità del
driver tra due open epoch.

Il kit non autorizza la run. Servono un nuovo full SHA approvato e una nuova
Human Gate specifica per:

```text
D280_01_ENROLL_FP3_CLOSE_OPEN_IDENTIFY_EPHEMERAL
```

Non è un test fprintd/PAM/login/sudo e non installa il driver nel sistema.

## Trattamento del template biometrico

L'FP3 autentico è dato sensibile. Il client lo crea con `O_EXCL`,
`O_NOFOLLOW`, owner root e modo `0600`, nel solo percorso:

```text
/var/tmp/goodix-d280-01-results/<UTC>-<SHA12>/template.fp3
```

Il print in memoria viene distrutto prima del primo close. Nel secondo epoch
il file viene letto, deserializzato, pulito dal buffer e rimosso **prima**
dell'identify. Trap host e cleanup del client tentano la rimozione su ogni
errore o segnale. `operator.log`, `summary.env` e l'export non contengono il
file, i byte FP3 o un loro hash.

La rimozione del pathname non garantisce la cancellazione fisica dei blocchi
su SSD, filesystem copy-on-write, journal o snapshot. Il kit riduce durata e
superficie del dato, ma l'eventuale run richiede accettazione esplicita di
questo rischio residuo. Non usare `shred` come falsa garanzia.

## Invarianti

```text
factory_firmware_and_persistent_state_must_remain_untouched
ACTION_ATTEMPT_MAX=2
ENROLL_ACTION_ATTEMPT_MAX=1
IDENTIFY_ACTION_ATTEMPT_MAX=1
OPEN_ATTEMPT_MAX=2
REOPEN_COUNT=1
OPERATOR_RETRY_COUNT=0
KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=0
TEMPLATE_REMOVAL_BOUNDARY=BEFORE_IDENTIFY
```

La seconda open/action avviene solo se enrollment, scrittura FP3, close e
audit completi del primo epoch sono PASS. Qualunque errore ferma il flusso;
non esiste un retry automatico. L'assenza di famiglie persistenti note è un
guardrail software, non prova l'assenza di persistence sensor-side ignota.

## Prerequisiti

- branch `development`, HEAD e `origin/development` uguali al full SHA
  esplicitamente approvato, live-critical set pulito;
- Freedesktop SDK 25.08 e accesso ai repository Fedora per gli RPM OpenCV
  4.13 hash-pinned;
- runtime Fedora TBB/FlexiBLAS/libstdc++ nelle versioni verificate dal kit;
- esattamente un target gestito dal driver;
- materiale production già disponibile nel layout protetto;
- `fprintd` non attivo; il launcher lo verifica e non lo arresta;
- accettazione esplicita della breve persistenza host-side del dato
  biometrico e del rischio SSD descritto sopra.

L'AI non esegue `sudo`, non legge il materiale protetto e non avvia questo
percorso live.

## Preflight offline consentito

Come utente normale:

```bash
./operator_kit/d280-01-ephemeral-template-reuse/run-d280-01.sh \
  --offline-preflight
```

Il preflight esegue le suite production-shaped e target-native, costruisce da
sorgenti la libreria Fedora 44/libfprint 1.94.100 e il client con baseline
`UNAPPROVED_FOR_LIVE`, controlla dipendenze e simboli e prova il rifiuto prima
di `FpContext`. Non enumera o apre USB e non crea template.

## Procedura soltanto dopo nuova approvazione

Come utente normale:

```bash
./operator_kit/d280-01-ephemeral-template-reuse/run-d280-01.sh \
  --prepare-approved-live <SHA_COMPLETO_APPROVATO>

mkdir -m 700 /tmp/goodix-d280-01-grant
./operator_kit/d280-01-ephemeral-template-reuse/run-d280-01.sh \
  --write-grant <SHA_COMPLETO_APPROVATO> \
  /tmp/goodix-d280-01-grant/grant.env
```

Annotare `PREPARED_BUILD_DIR`. Soltanto allora, e soltanto con autorizzazione
one-shot ancora valida, l'operatore può avviare manualmente:

```bash
sudo ./operator_kit/d280-01-ephemeral-template-reuse/run-d280-01.sh \
  --run-approved-live <PREPARED_BUILD_DIR> \
  --grant /tmp/goodix-d280-01-grant/grant.env
```

Il grant viene consumato atomicamente prima dell'accesso al materiale e
dell'enumerazione USB. Non cancellare il marker in
`/var/tmp/goodix-d280-01-consumed-grants/`.

## Interazione e stop condition

Usare sempre l'indice destro e seguire soltanto `AZIONE_OPERATORE`. Durante
l'enrollment, sollevare il dito soltanto dopo
`RILASCIO_FISICO_PRONTO=n`; riposizionarlo quando richiesto. Dopo il PASS del
primo epoch il client riapre il device e chiede un solo contatto identify.

Qualunque errore, no-match, retry callback, segnale, limite host, close o audit
non conforme è terminale: non rilanciare, non creare un nuovo grant, non
avviare fprintd e tornare alla review AI-PM. Il timeout è solo host-side e non
prova quiescenza del sensore.

## Output ed export

Gli unici output conservabili sono:

```text
/var/tmp/goodix-d280-01-results/<UTC>-<SHA12>/operator.log
/var/tmp/goodix-d280-01-results/<UTC>-<SHA12>/summary.env
```

Dopo la run, `template.fp3` deve essere assente. L'export fail-closed rifiuta
la directory se il template esiste:

```bash
sudo ./operator_kit/d280-01-ephemeral-template-reuse/run-d280-01.sh \
  --export-results /var/tmp/goodix-d280-01-results/<UTC>-<SHA12>
```

Anche un PASS consuma il grant e non autorizza altre action.
