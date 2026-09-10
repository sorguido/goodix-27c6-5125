# D281/01 — fprintd storage e control plane offline

## Decisione

```text
OUTCOME=PASS_HOST_ONLY
ADVANCEMENT=INSTALLED_FPRINTD_PRIVATE_DBUS_FP3_RELOAD_VERIFY_CORRUPTION_DELETE
EXECUTABLE_CLOSURE=PASS_OFFLINE_REAL_DAEMON_AND_CLI
RESIDUAL_BLOCKER_OR_RISK=TARGET_SIGFM_SYSTEM_SERVICE_AND_END_USER_AUTH_REMAIN_GATED
CANONICAL_DOCUMENTATION=UPDATED
REVIEW_SET=GIT_NATIVE
```

D281/01 attraversa il vero daemon e i veri client Fedora 44 con storage
effettivo, ma mantiene hardware, biometria reale, privilegi e stato di sistema
fuori scope. Il risultato chiude il boundary generico fprintd/storage; non è
una prova target-specific del driver Goodix/SIGFM sotto il servizio di sistema.

## Incidente metodologico e corrective

La prima esplorazione usava una build libfprint con il solo driver
`virtual_image`. La review immediatamente successiva ha rilevato che
`fp_context_init()` crea comunque un `GUsbContext` e
`fp_context_enumerate()` chiama `g_usb_context_enumerate()`, anche quando
nessun driver USB è registrato. Quella esplorazione può quindi avere enumerato
il bus host e non è usata come evidenza D281 conforme. Non conteneva il driver
Goodix: open, claim e transfer al sensore erano irraggiungibili, ma il vincolo
più forte di zero enumerazione non era soddisfatto.

Il corrective è una patch overlay applicata soltanto a una copia temporanea
della sorgente. La macro `D281_01_DISABLE_USB_CONTEXT` esclude a compile time
sia `g_usb_context_new()` sia `g_usb_context_enumerate()`. Il runner rifiuta la
build se uno dei due simboli resta importato, se compare il driver Goodix o se
fprintd non carica l'esatto `.so` temporaneo osservato in `/proc/<pid>/maps`.
La sorgente production canonica non è modificata dalla seam.

## Ambiente pinning

```text
fprintd=fprintd-1.94.5-5.fc44.x86_64
libfprint_host=libfprint-1.94.100-1.fc44.x86_64
libgusb=libgusb-0.4.9-5.fc44.x86_64
custom_libfprint_sha256=65c8b6a254b73e2c70e01e79b85321cf01db62d8a2cad3cf7c80614d9d22052b
usb_disable_patch_sha256=b83373189664ee7bc7aabf10bd5bf5ddb26e2d707dea3e79fb19dd92fd9ec58d
virtual_image_png_sha256=b957788d60d4d7f5527d455fa558707d127bed502118d4db3f8a44ac62b7ccda
build_network_shared=false
```

La build avviene nell'SDK Freedesktop 25.08 già installato, con namespace di
rete disabilitato, `drivers=virtual_image` e una copia hash-identica della
libreria runtime libgusb installata. La libreria conserva SONAME
`libfprint-2.so.2`; `/usr/libexec/fprintd` viene eseguito senza installazione.

Il bus è creato da `dbus-run-session`; `DBUS_SYSTEM_BUS_ADDRESS` punta allo
stesso socket privato sotto `/tmp`. Il mock PolicyKit rifiuta bus non temporanei
e autorizza soltanto `verify`, `enroll` e `setusername`. `STATE_DIRECTORY` e
socket virtuale vivono nella directory probe `0700`. Non sono usati system
bus, `/var/lib/fprint`, systemd, sudo/root o dati biometrici reali.

## Esecuzione deterministica conforme

La run canonica host-only è
`/tmp/goodix-d281-01.el9ImB`; il risultato importato è
`analysis/D281/D281_01_OFFLINE_RESULT.env`. Il suo blocco originario
`summary.env` ha SHA-256
`102190971db3156682672e11a83fd68baa0c15d774e4b046fd71cc3627b97723`.

1. Il vero `fprintd-enroll` completa sei stage sintetici e il daemon scrive un
   singolo FP3 da 5435 byte.
2. Il daemon termina; un nuovo processo con la stessa `STATE_DIRECTORY`
   elenca `right-index-finger` e `fprintd-verify` ottiene
   `verify-match (done)` con la stessa immagine sintetica.
3. Dopo un nuovo stop, il primo byte dell'header FP3 viene sostituito. Un terzo
   daemon stampa `Error deserializing data: Data could not be parsed`; il
   client riceve `NoEnrolledPrints` e termina con codice 1. Nessun match è
   prodotto.
4. Ripristinati i byte originali, un quarto daemon esegue
   `fprintd-delete`; al termine lo storage contiene zero file.

```text
D281_01_STORED_FP3_SHA256=5631491476b04b0b2903bf004280f0e9b342b0c72e794b0ce8eb0d86609e5fc6
D281_01_STORED_FP3_SIZE=5435
D281_01_STORED_FP3_MODE=0644
D281_01_STATE_ANCESTOR_MODE=0700
D281_01_RELOAD_LIST_PASS=true
D281_01_RELOAD_VERIFY_MATCH_PASS=true
D281_01_CORRUPT_VERIFY_REJECTED=true
D281_01_DELETE_PASS=true
D281_01_REMAINING_STATE_FILE_COUNT=0
D281_01_REAL_USB_ENUMERATION_ATTEMPTED=false
D281_01_REAL_SENSOR_ACCESSED=false
```

Il mode upstream del file è `0644`, protetto in questa run dagli antenati
`0700`; il servizio Fedora dichiara analogamente `StateDirectory=fprint` e
`StateDirectoryMode=0700`. Ownership root, label SELinux e policy del system
bus sono verificati staticamente rispetto ai file installati, non eseguiti.

## Portata delle prove

`VERIFIED_HOST_ONLY`:

- ABI reale fra fprintd 1.94.5 e libfprint 1.94.100 con SONAME production;
- chiamate D-Bus reali di enroll/list/verify/delete tramite i client installati;
- scrittura FP3, sopravvivenza al restart, deserialize e match NBIS virtuale;
- rifiuto fail-closed di un FP3 con header corrotto;
- delete e assenza di file residui;
- separazione da system bus e state directory production.

`NON PROVATO`:

- caricamento del driver `goodix_27c6_5125` da fprintd;
- storage/reload di un FP3 SIGFM autentico tramite fprintd;
- accesso live Goodix o comportamento del servizio systemd con il sensore;
- enrollment/verify end-user reali, discriminazione same/different-finger,
  FAR/FRR;
- integrazione PAM di login e sudo;
- ownership/SELinux runtime production e persistenza dopo reboot;
- assenza di persistenza sensor-side.

## Prossimo boundary

Il successivo vero confine è `D282/01`: staging production e prova end-to-end
del driver target sotto il servizio fprintd, includendo storage SIGFM reale,
restart del daemon, verify dello stesso dito, no-match controllato con dito
diverso, delete/cleanup e una integrazione PAM limitata e reversibile. Questo
richiede privilegi, installazione/attivazione capace di raggiungere il sensore,
biometria reale e nuove azioni live; è quindi una nuova Human Gate. Non è stata
preparata alcuna build o autorizzazione live in D281/01.

```text
NEXT_PRIMARY_BOUNDARY=D282_01_HUMAN_GATED_TARGET_FPRINTD_STORAGE_VERIFY_AND_LIMITED_PAM
CURRENT_LIVE_AUTHORIZED=false
CURRENT_PRIVILEGED_INSTALL_AUTHORIZED=false
```
