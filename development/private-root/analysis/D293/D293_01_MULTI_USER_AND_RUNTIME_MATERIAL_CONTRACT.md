<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D293/01 — contratto multi-user e materiali runtime protetti

## Esito

```text
D293_01_OUTCOME=PASS_OFFLINE_CONTRACT
D293_01_BASELINE=77268753ba6d787defb5c96ca9f96c7ecc513227
PHASE_B_B1=COMPLETED
CURRENT_PHASE=B
PRODUCTION_READY=false
REAL_USB_ACCESS=0
PROTECTED_FILE_CONTENT_READ=false
LIVE_EXECUTION_PERFORMED=false
NEXT_BOUNDARY=PHASE_B_B2_MULTI_USER_STORAGE_MODEL_AND_MULTI_FINGER_ANY_OFFLINE
```

B1 e chiuso nel suo perimetro di analisi: il contratto standard e derivato
dai sorgenti esatti Fedora, il confine template/materiali e esplicito e i gap
sono trasformati in requisiti verificabili. Non chiude Phase B e non prova il
workflow KDE multi-user sul target.

## Autorita ed evidenze consultate

- `reference/fprintd-fedora44-1.94.5/PROVENANCE.md`: il tree e upstream
  fprintd v1.94.5 esatto per `fprintd-1.94.5-5.fc44.x86_64`; lo spec Fedora
  non applica patch.
- `reference/libfprint-fedora44-1.94.100/PROVENANCE.md`: baseline Fedora
  `libfprint-1.94.100-1.fc44.x86_64`, con delta locale documentato.
- `Rockytkg/PROVENANCE.md` e `docs/LICENSING_AND_PROVENANCE.md`: provenienza
  del subset SIGFM/R2 e dei loader locali; nessun boundary di licenza cambia.
- `src/device.c`, `src/file_storage.c`, XML D-Bus, policy e unit systemd del
  tree fprintd; `fp-print.c`, `fp-device.c` e `fpi-device.c` libfprint; classe
  e loader Goodix locali.
- evidenza storica D279/07 (layout target controllato dall'operatore) e D281
  (vero daemon/CLI su storage isolato). Non sono state rieseguite live.

## Contratto utenti, autorizzazione e claim

| Operazione | Utente effettivo | Stato claim | PolicyKit |
| --- | --- | --- | --- |
| `Claim(username)` | il sender D-Bus e risolto con `GetConnectionUnixUser` + `getpwuid`; stringa vuota o nome proprio diventano `pw_name`; un nome differente resta quello richiesto | device libero; crea una sessione esclusiva legata a unique bus name e utente | basta una fra `verify` ed `enroll`; un nome diverso richiede inoltre `setusername` |
| `ListEnrolledFingers(username)` | stessa risoluzione; non richiede claim | anytime | `verify`; `setusername` per altro nome |
| `EnrollStart(finger)` | utente della sessione | claim dello stesso sender | `enroll` |
| `VerifyStart(finger|any)` | utente della sessione | claim dello stesso sender | `verify` |
| `DeleteEnrolledFinger` / `DeleteEnrolledFingers2` | utente della sessione | claim dello stesso sender | `enroll` |
| legacy `DeleteEnrolledFingers(username)` | parametro risolto come sopra; auto-claim | puo operare senza claim preesistente | `enroll`; `setusername` per altro nome |
| `Release`, `EnrollStop`, `VerifyStop` | sessione esistente | stesso sender | nessuna nuova richiesta PolicyKit |

`setusername` protegge la gestione di un altro nome, ma il ramo privilegiato
non chiama `getpwnam()` sul nome richiesto. Il normale percorso locale deve
quindi passare la stringa vuota; strumenti amministrativi devono validare il
nome e limitare rigidamente il target. Un solo sender puo detenere il device e
una singola action puo essere attiva.

I default Fedora autorizzano `verify` all'utente locale attivo, richiedono
`auth_self_keep` per `enroll` e `auth_admin_keep` per `setusername`; utenti
inactive/any sono negati. Questi sono default policy, non una garanzia sulla
configurazione finale della macchina.

## Storage e cardinalita dei template

Il backend file usa il primo valore non vuoto di `STATE_DIRECTORY`, oppure
`/var/lib/fprint`, e costruisce:

```text
<state-directory>/<username>/<driver>/<device-id>/<finger-hex>
```

La unit Fedora dichiara `StateDirectory=fprint`, `StateDirectoryMode=0700` e
gira come root. Il codice crea gli antenati con `0700`; `g_file_set_contents`
non fissa direttamente il mode del file. D281 ha osservato `0644` sotto
antenati `0700`. Confidenzialita e isolamento DAC dipendono quindi dal root
`0700` e dal daemon root/PolicyKit, non dal file leaf da solo.

Fatti per utente e device:

- zero dita: list e verify restituiscono `NoEnrolledPrints`;
- un dito: esiste al massimo un file per codice dito; re-enrollment elimina
  prima il template precedente e poi avvia la nuova enrollment, quindi un
  fallimento non ripristina automaticamente il vecchio template;
- piu dita: fino ai dieci codici `FpFinger` possono coesistere e list li
  riporta; delete singolo rimuove un leaf, delete completo itera tutti i
  codici e rimuove gli antenati rimasti vuoti;
- piu utenti: il primo livello `username` separa i namespace. Load controlla
  anche username serializzato, finger e compatibilita device prima di
  pubblicare il print;
- restart/reboot: gli FP3 sono persistenti nello state directory e vengono
  deserializzati al bisogno; D281 ha gia provato restart/list/verify/delete
  con il vero daemon su storage isolato.

### Limite multi-finger corrente

La classe production si identifica come `goodix_27c6_5125`, supporta
ENROLL/VERIFY ma maschera `FP_DEVICE_FEATURE_IDENTIFY` per conservare il
percorso direct-enroll target-proven. Nel fprintd esatto, `VerifyStart("any")`
con un solo print seleziona quel dito; con piu print e senza IDENTIFY finisce
nel ramo VERIFY e prende soltanto il primo elemento della gallery. L'ordine
deriva dalla scansione directory e non e un contratto di scelta stabile.

Quindi lo storage multi-finger esiste, ma l'autenticazione standard `any` non
prova oggi che qualunque dito registrato possa autenticare. Riabilitare
IDENTIFY non e una correzione meccanica: lo stesso feature induce fprintd a
fare un'azione IDENTIFY di duplicate-check prima di ENROLL, mentre il lifecycle
APP12509 corrente permette il direct-enroll bounded. B2 deve risolvere e
provare offline questo conflitto senza indebolire il fence sensor-reaching.

Senza IDENTIFY fprintd non esegue inoltre il duplicate-check globale fra
utenti: lo stesso dito fisico potrebbe essere registrato in namespace diversi.
La portata di sicurezza e UX va decisa e testata in B2; non viene assunta.

## Identita driver e compatibilita FP3

`fp_print_new()` copia nel template `fp_device_get_driver()` e
`fp_device_get_device_id()`. `fp_print_compatible()` richiede uguaglianza di
entrambi. fprintd usa gli stessi due campi nel path e ripete il controllo al
load.

La classe USB locale fissa il driver ID `goodix_27c6_5125` e non implementa
una vfunc probe. In libfprint 1.94.100 il device-id iniziale e `"0"` e resta
tale quando probe completa senza un ID. Il contratto corrente e quindi:

```text
DRIVER_ID=goodix_27c6_5125
DEVICE_ID=0
STORAGE_KEY=goodix_27c6_5125/0
PRINT_COMPATIBILITY=EXACT_DRIVER_AND_DEVICE_ID
```

Una futura introduzione di probe/seriale o un rename del driver renderebbe i
vecchi FP3 invisibili nel path corrente e incompatibili al load: richiede una
migrazione esplicita, non un fallback silenzioso.

## Utenti creati, rinominati o cancellati

**KNOWN dal codice:** il normale sender e risolto a ogni chiamata tramite UID
e NSS; lo storage del nuovo nome viene creato lazy al primo salvataggio. Non
esiste username, home o path user-specific nel source set Goodix production.
Un utente locale creato dopo l'installazione non richiede reinstallazione o
configurazione del driver.

**KNOWN dal codice:** la chiave persistente e il nome, non l'UID. fprintd non
ascolta il lifecycle degli account: rename e cancellazione OS non migrano ne
rimuovono `/var/lib/fprint/<username>`. `discover_users()` enumera directory,
non NSS. Il riuso futuro dello stesso nome puo quindi riassociare template
stale al nuovo account.

**Requisito Phase B:** rename equivale a delete controllato + re-enrollment;
la cancellazione account deve eliminare esattamente le impronte di quel nome
prima del riuso, tramite API fprintd amministrativa finche applicabile o un
hook di lifecycle distro progettato e verificato. Sono vietati delete ampi,
glob e database Goodix paralleli. La scelta/hook di packaging appartiene alle
fasi successive, ma B2 deve modellare assenza, rename, delete e name reuse.

## Materiali runtime protetti: confine separato

Il driver non riceve username. A ogni open production carica lo stesso set
fisso prima del claim USB, da `/var/lib/goodix-5125-poc`:

| Input | Natura derivata dal loader | Classificazione | Scope noto |
| --- | --- | --- | --- |
| `target-material-manifest.json` | manifest hash-pinned del set target | metadata protetto | sistema, non utente |
| `transport-material.bin` | contenitore 88 byte; include la PSK usata dalla secure session | **secret** | sistema e target-bound; unicita per singola unita non provata |
| `target-config-90.bin` | payload CONFIG90 target-pinned, validato per hash/finalizer/DAC | configurazione protetta | sistema e target-bound |
| `gfusb.dll` | PE OEM hash-pinned, solo letto come byte per estrarre due seed; mai eseguito o mappato executable | proprietario/protetto, non redistribuibile senza diritto verificato | sistema; origine OEM, non utente |
| `fdt-cache.bin` | cache target-pinned con binding OTP e seed FDT | device data protetto | sistema e target-bound |

Il set e **globalmente condiviso sul sistema** da tutte le sessioni fprintd,
ma e vincolato ai pin APP12509/target. Non e provato se PSK/config siano unici
per la singola unita, per un lotto o per il modello: `PER_PHYSICAL_DEVICE` e
quindi `UNKNOWN`, non una premessa di distribuzione.

La policy compilata e fail-closed:

```text
DIRECTORY=/var/lib/goodix-5125-poc root:root 0700
FILES=five_exact_direct_children root:root 0600 regular_no_symlink
VALIDATION=exact_size_and_sha256_plus_format_or_binding_checks
DISCOVERY=false
FALLBACK=false
WRITE_BY_DRIVER=false
SECRET_IN_REPOSITORY_PACKAGE_LOG=false
```

Il loader verifica directory e file descriptor prima/dopo, usa
`O_NOFOLLOW|O_CLOEXEC`, pubblica gli output solo dopo validazione completa e
azzera PSK, seed, validator, FDT e CONFIG owned al teardown. Manifest e
CONFIG90 sono protetti con la stessa policy anche quando la loro natura non e
equivalente a una PSK.

### Origine e provisioning lecito

**KNOWN:** D279/07 ha registrato un provisioning operatore autorizzato: i tre
input target preesistenti sono stati preservati; `gfusb.dll` proveniva dal
corpus OEM D230 e `fdt-cache.bin` dall'evidenza target D255. Il probe operatore
ha verificato root ownership, mode e label `fprintd_var_lib_t` su Fedora
SELinux Enforcing. Licensing/provenance del codice non concede di per se il
diritto di redistribuire il DLL o i materiali target.

**OBSERVED, non target-authoritative:** nel namespace AI corrente e stato
letto solo `stat` della directory: mode `0700`, uid/gid mappati a `65534`; i
figli non sono traversabili. Nessun contenuto e stato aperto. Come gia
documentato da D279/07, questo namespace non rende osservabili gli owner reali
host; il dato non invalida il probe operatore ne prova readiness corrente.

**Requisito:** package e repository distribuiscono solo codice, policy,
schema e tool di verifica, mai questi cinque byte set. Il provisioning deve
essere un atto amministrativo separato, esplicito, no-overwrite e auditabile,
da una sorgente legittimamente detenuta, con staging atomico, owner/mode/label
esatti e rollback dei soli file creati. Non deve estrarre PSK dal sensore,
reprovisionarla o generare sostituti casuali/nulli.

**UNKNOWN / gate futuro:** non e documentata una fonte redistribuibile ne una
procedura factory-preserving per ottenere un set nuovo per una macchina o un
sensore diverso; non e provata la riusabilita del set corrente oltre il target
testato. Accesso/copia/verifica dei file autentici e prova su macchina nuova
richiedono autorizzazione specifica dell'Utente e percorso operatore. Questo
non impedisce B2 offline, ma impedisce la closure Phase B e la dichiarazione
production-ready.

## B2 proposto, ancora offline

Il prossimo boundary minimo e
`PHASE_B_B2_MULTI_USER_STORAGE_MODEL_AND_MULTI_FINGER_ANY_OFFLINE`:

1. modello/test a due principal e storage temporaneo per zero/una/piu dita,
   due utenti, restart, replace, delete singolo/completo, rename/delete/name
   reuse, senza account host reali;
2. prova executable col vero fprintd/libfprint in bus e `STATE_DIRECTORY`
   isolati, usando solo backend sintetico compile-time non USB;
3. decisione e prototipo offline minimo per `VerifyStart(any)` multi-finger e
   duplicate-check cross-user, preservando direct-enroll e tutti i fence;
4. verifica che il set runtime sia un prerequisito system-wide unico e non
   venga copiato nello storage utente o negli artefatti.

Il primo Human Gate resta dopo questa chiusura offline: provisioning/lettura
del materiale autentico oppure prova KDE/fprintd con un secondo utente locale
e biometria reale. D293/01 non crea kit e non autorizza tali azioni.

## Verifiche

```text
python3 analysis/D293/validate_d293_01_contract.py=PASS
PRODUCTION_USER_HOME_HARDCODE_COUNT=0
PRODUCTION_RUNTIME_PATH_COUNT=6
FPRINTD_DBUS_METHOD_COUNT=10
PROTECTED_FILE_CONTENT_READ=false
git diff --check=PASS
```
