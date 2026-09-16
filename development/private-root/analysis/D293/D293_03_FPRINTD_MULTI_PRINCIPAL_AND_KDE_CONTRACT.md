<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D293/03 — fprintd multi-principal host-only e contratto KDE

Baseline: `cb918c6114f518d10d386d2b639eb3c8e5dd5f20`
(`development`, worktree inizialmente pulito).

## Esito

Il vero daemon Fedora `fprintd-1.94.5-5.fc44.x86_64` e i client fprintd hanno
completato su un bus D-Bus privato il lifecycle di due nomi principal e tre
template sintetici. La build libfprint usa soltanto `virtual_image`, compila
fuori la creazione/enumerazione del contesto USB con l'overlay D281 già
verificato e usa uno `STATE_DIRECTORY` sotto `/tmp`. Il driver Goodix non è
presente nel registro della build e la libreria non importa i simboli di
creazione/enumerazione GUsbContext.

```text
D293_03_OUTCOME=PASS_HOST_ONLY
PHASE_B_B3_OFFLINE_PREREQUISITES=COMPLETED
KDE_KCM_STATIC_CONTRACT=PASS
PHASE_B_B4_OFFLINE_PREREQUISITES=COMPLETED
PHASE_B_CLOSED=false
PRODUCTION_READY=false
NEXT_BOUNDARY=HUMAN_GATE_PHASE_B_KDE_NEW_USER_LIFECYCLE_TARGET
```

## Metodo e confini

`d293_03_fprintd_integration.sh` estende il metodo D281 senza creare un
secondo framework: copia in una directory temporanea il tree Fedora
libfprint 1.94.100, applica il solo fence compile-time D281, abilita
`virtual_image`, costruisce offline nel Flatpak SDK 25.08 e lancia il vero
`/usr/libexec/fprintd` installato. Il system bus viene reindirizzato al bus
privato creato da `dbus-run-session`; il mock PolicyKit D281 autorizza
esattamente `verify`, `enroll` e `setusername`. Non viene avviato né contattato
il daemon fprintd di sistema.

Le immagini `whorl.png`, `loop-right.png`, `tented_arch.png` e `arch.png` sono
fixture pubbliche del source tree libfprint, non immagini o template del
target. Lo storage finale resta nel tempdir del probe; `/var/lib/fprint` non è
letto o scritto. Nessun contenuto di `goodix_runtime_inputs`, `material` o
`target_material` viene aperto.

Questo test usa **due username/principal D-Bus distinti** (`d293-alpha` e
`d293-beta`) richiesti dal medesimo sender e autorizzati tramite
`setusername`. Il processo client e il daemon privato esercitano quindi un
solo UID Unix del namespace host: il test prova isolamento e lifecycle per
chiave username nel vero storage fprintd, non autenticazione/PolicyKit di due
account Unix realmente distinti. Questa distinzione impedisce di usare D293/03
come sostituto della prova target con un nuovo utente locale.

## Matrice eseguita

| Caso | Evidenza osservata | Esito |
| --- | --- | --- |
| Enrollment iniziale | `d293-alpha`: right-index + left-index; `d293-beta`: right-index | PASS |
| Restart/reload | stop completo del daemon, nuovo processo, `fprintd-list` ritrova 2 + 1 dita | PASS |
| Gallery multi-finger | `fprintd-verify -f any d293-alpha` elenca due dita e la fixture del secondo dito produce `verify-match` | PASS |
| Isolamento principal | la fixture alpha contro la sola gallery beta produce `verify-no-match` | PASS |
| Replace | nuovo enrollment dello stesso right-index alpha con fixture distinta, poi `any` produce match | PASS |
| Delete singolo | delete del left-index alpha lascia un solo leaf | PASS |
| Delete completo | delete di beta lascia zero leaf e rimuove il namespace vuoto | PASS |

Il test conferma il control plane e lo storage standard che consumerà il
driver, ma non percorre il lifecycle USB/TLS Goodix: D293/02 rimane l'evidenza
offline del relativo handoff IDENTIFY→ENROLL e D291 rimane l'evidenza
target-proven. Non si inferisce dal backend virtuale equivalenza biometrica o
sensor-reaching.

## Audit statico KDE Plasma 6.7.5 installato

La superficie installata è pinned read-only:

- `plasma-systemsettings-6.7.5-1.fc44.x86_64` e
  `plasma-desktop-6.7.5-1.fc44.x86_64`;
- `/usr/lib64/qt6/plugins/plasma/kcms/systemsettings/kcm_users.so`, owner
  `plasma-workspace-libs-6.7.5-1.fc44.x86_64`, SHA-256
  `764b86abb81f4be9ee38c836a558955bca192546dc77158e2ace72e8bb2cf2d9`;
- `/usr/share/applications/kcm_users.desktop`, owner
  `plasma-workspace-6.7.5-1.fc44.x86_64`, SHA-256
  `c27ab075c4e07d07631ae584695bc62376d3e3f1db258f20e622d6fda9e6c4be`,
  con `Exec=systemsettings kcm_users`.

La string table del plugin contiene le interfacce standard
`net.reactivated.Fprint.Manager` e `.Device` e i metodi `GetDefaultDevice`,
`Claim`, `Release`, `ListEnrolledFingers`, `EnrollStart`, `EnrollStop`,
`DeleteEnrolledFinger`, `DeleteEnrolledFingers` e
`DeleteEnrolledFingers2`. Contiene inoltre i percorsi UI
`deleteFingerprint`, `reenrollFinger` e `Re-enroll finger`. Ne segue, come
inferenza statica limitata all'artefatto installato, che il KCM usa discovery,
list, enroll/re-enroll e delete fprintd standard e non richiede una GUI
Goodix. Il KCM non è stato avviato: autorizzazioni reali, feedback UI,
lifecycle di un account appena creato e comportamento col sensore reale non
sono provati da questo audit.

## Verifiche

```text
bash analysis/D293/d293_03_fprintd_integration.sh=PASS
D293_03_PRINCIPAL_NAME_COUNT=2
D293_03_UNIX_UID_COUNT=1
D293_03_SETUSERNAME_AUTHORIZED=true
D293_03_VERIFY_ANY_MULTI_FINGER=PASS
D293_03_PRINCIPAL_NAMESPACE_ISOLATION=PASS
D293_03_REPLACE=PASS
D293_03_DELETE_SINGLE=PASS
D293_03_DELETE_COMPLETE=PASS
D293_03_REAL_USB_ENUMERATION_ATTEMPTED=false
D293_03_REAL_SENSOR_ACCESSED=false
D293_03_PROTECTED_FILE_CONTENT_READ=false
python3 analysis/D293/validate_d293_03.py=PASS
git diff --check=PASS
```

Il risultato compatto è in `D293_03_OFFLINE_RESULT.env`. Gli output completi
della run erano confinati al tempdir e non contenevano secret o dati
biometrici reali.

## Residuo e prossimo boundary

I prerequisiti offline di B3/B4 e il contratto statico KDE sono esauriti. I
veri scenari B3/B4 non sono stati eseguiti e la Phase B non è chiusa. Il primo
boundary che può aggiungere evidenza è ora soggetto a Human
Gate: sul target già installato, creare un nuovo normale utente locale senza
reinstallare il driver, usare il KCM Users standard per list/enroll/re-enroll/
delete, verificare `VerifyStart(any)` con più dita e isolamento rispetto a un
utente preesistente attraverso logout/login/restart. Questa prova richiede
account host reali, UI KDE, sensore e materiale runtime protetto già
provisionato; l'AI non la esegue e D293/03 non crea né autorizza un operator
kit.

Il lifecycle di cancellazione/rename dell'account resta inoltre un requisito
di integrazione host: fprintd indicizza per username e non offre un hook OS
automatico. Non è stato simulato come risolto.
