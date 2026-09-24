# Structural public-tree audit

Decisione Utente: `PUBLIC_TREE = EVERYTHING_EXCEPT_TOP_LEVEL_DEVELOPMENT`.
Questo è un audit interno di ristrutturazione, non una allowlist o un meccanismo
di export. Ogni nuovo file esterno a `development/` deve rispettare il medesimo
boundary senza eccezioni.

## Inventario iniziale

La baseline `39dd81ee43ae200e74bcbb1f70a57815113eff84` conteneva 3.337 file
versionati, dei quali **852** esterni a `development/`. La classificazione dei
852 percorsi è stata eseguita per nome, ruolo, provenienza e dipendenze; non sono
stati aperti materiali protetti, capture, immagini biometriche o template.

- retained public source/documentation: 329 file.
- relocated internal/history: 522 file.
- removed obsolete publication allowlist: 1 file.

Il tree pubblico finale contiene **338 file versionati**, calcolati dallo stato
staged come tutti i file eccetto quelli sotto `development/`. La copia temporanea
esatta di questa superficie è stata verificata senza `.git` e senza directory
interna. I nuovi sorgenti installer/build/materiali e relativi test sono compresi.
Le rinomine in `goodix_action_binding.[ch]`, `run_goodix_post_tls_test.sh` e
`tests/support/post_tls/` rimuovono nomi milestone senza cambiare il protocollo.

## Spostamenti

Le directory interne mantengono i file e la provenance. Gli snippet di comandi
nei report storici restano evidenza del loro checkout originario e non sono la
procedura corrente; i collegamenti Markdown sono stati aggiornati dove la
relocation li cambiava. Manuale e roadmap sono aggiornati organicamente insieme
allo stato corrente. Il file di selezione pubblica precedente è stato eliminato.

| Origine | Destinazione | File versionati |
| --- | --- | ---: |
| `AGENTS.md` | `development/AGENTS.md` | 1 |
| `Goodix 27c6 5125 manuale tecnico.md` | `development/Goodix 27c6 5125 manuale tecnico.md` | 1 |
| `GoodixArtifacts` | `development/GoodixArtifacts` | 2 |
| `ROADMAP_DISTRO_DECOUPLED_RELEASE.md` | `development/ROADMAP_DISTRO_DECOUPLED_RELEASE.md` | 1 |
| `START_PROMPT.md` | `development/START_PROMPT.md` | 1 |
| `deployment/managed-install` | `development/deployment/managed-install` | 17 |
| `deployment/minimal-runtime` | `development/deployment-history/public-release-transition/deployment/minimal-runtime` | 19 |
| `deployment/plasma-login-opt-in/R4_PLASMA_LOGIN_VM.md` | `development/deployment/plasma-login-opt-in/R4_PLASMA_LOGIN_VM.md` | 1 |
| `deployment/plasma-login-opt-in/build-vm.sh` | `development/deployment-history/public-release-transition/deployment/plasma-login-opt-in/build-vm.sh` | 1 |
| `deployment/plasma-login-opt-in/manage.py` | `development/deployment-history/public-release-transition/deployment/plasma-login-opt-in/manage.py` | 1 |
| `deployment/plasma-login-opt-in/test_manage.py` | `development/deployment-history/public-release-transition/deployment/plasma-login-opt-in/test_manage.py` | 1 |
| `deployment/recovery/R5_VM.md` | `development/deployment/recovery/R5_VM.md` | 1 |
| `deployment/recovery/install.sh` | `development/deployment-history/public-release-transition/deployment/recovery/install.sh` | 1 |
| `deployment/recovery/manage.py` | `development/deployment-history/public-release-transition/deployment/recovery/manage.py` | 1 |
| `deployment/recovery/test_manage.py` | `development/deployment-history/public-release-transition/deployment/recovery/test_manage.py` | 1 |
| `deployment/recovery/uninstall.sh` | `development/deployment-history/public-release-transition/deployment/recovery/uninstall.sh` | 1 |
| `docs/DEVICE_MATERIAL_PIN_AUDIT.md` | `development/docs/DEVICE_MATERIAL_PIN_AUDIT.md` | 1 |
| `docs/MINIMAL_RUNTIME.md` | `development/docs/MINIMAL_RUNTIME.md` | 1 |
| `docs/R4_PLASMA_LOGIN_INTEGRATION.md` | `development/docs/R4_PLASMA_LOGIN_INTEGRATION.md` | 1 |
| `docs/R5_INSTALL.md` | `development/docs/R5_INSTALL.md` | 1 |
| `docs/STOCK_FPRINTD_ATTEMPTS.md` | `development/docs/STOCK_FPRINTD_ATTEMPTS.md` | 1 |
| `production/build-inner.sh` | `development/build-history/public-release-transition/production/build-inner.sh` | 1 |
| `production/build-support` | `development/build-history/public-release-transition/production/build-support` | 5 |
| `production/build.sh` | `development/build-history/public-release-transition/production/build.sh` | 1 |
| `production/check-source.sh` | `development/build-history/public-release-transition/production/check-source.sh` | 1 |
| `production/login` | `development/production/login` | 17 |
| `production/minimal-runtime` | `development/build-history/public-release-transition/production/minimal-runtime` | 4 |
| `production/plasma-vt` | `development/production/plasma-vt` | 13 |
| `production/polkit` | `development/production/polkit` | 9 |
| `production/sudo` | `development/production/sudo` | 8 |
| `reference/fprintd-fedora44-1.94.5` | `development/retired-public-tree/reference/fprintd-fedora44-1.94.5` | 144 |
| `reference/plasma-login-manager-fedora44-6.7.5` | `development/reference/plasma-login-manager-fedora44-6.7.5` | 263 |

I README dei due componenti deployment sono stati preservati prima della
riscrittura in `documentation-history/before-public-installer/`.
La cache non versionata GoodixArtifacts è stata spostata con la sua directory;
`development/.gitignore` conserva l'esclusione degli RPM e degli archivi locali.
Il `.gitignore` della vecchia reference fprintd, inizialmente intercettato dalla
sua stessa regola, è preservato nella destinazione interna e incluso esplicitamente
nello staging. Nessun vecchio file utile è stato eliminato dalla relocation.

## Superficie pubblica rimanente

- Documentazione inglese del prodotto, README di componente, licenze e
  provenance: nessun percorso privato, diario milestone o link verso l'area interna.
- `libfprint-driver/`: implementazione corrente, test e stub sintetici; nessun
  materiale del lettore o capture reale distribuito.
- `Rockytkg/`: soltanto i quattro file SIGFM usati dal build, con notice originali.
- `reference/libfprint-fedora44-1.94.100/`: base sorgente/provenance Fedora
  necessaria alla libreria e relativa documentazione upstream.
- `production/`: builder corrente, test sintetici, ledger di origine/licenze e
  digest sorgenti; nessuna build privata conservata è un input pubblico.
- `deployment/`: installer/material validator, selector Plasma minimo e recovery
  standalone correnti, con test sintetici. Nessun vecchio installer richiede VM,
  branch privato o commit storico nel percorso pubblico.
- `.gitignore`: esclusioni effimere e protezione dei nomi dei cinque materiali,
  senza deroghe per tenere file interni versionati nell'albero pubblico.

## Audit dati della reference

La reference pubblica contiene 224 file versionati: 97 `.c`, 69 `.h`, 8
`meson.build`, 4 Markdown e ulteriori testi di build/configurazione/licenza.
Non contiene directory `tests/`, capture, template o fixture biometriche.
L'unico asset con estensione immagine è
`source/demo/org.freedesktop.libfprint.Demo.png` (25.039 byte), classificato come
icona dell'applicazione dal corrispondente `demo/meson.build`; non è stato letto
o visualizzato. È un asset upstream pubblico, non una capture del sensore.
I GTK example sono disabilitati nel percorso build; la modalità minimal evita
la configurazione dei test e degli esempi upstream non inclusi.

Gli otto file nascosti della reference sono configurazione CI/Git upstream:
`.ci/check-abi`, `.git-blame-ignore-revs`, `.gitignore`, `.gitlab-ci.yml` e quattro
file sotto `.gitlab-ci/`. I commit nel blame-ignore appartengono alla provenance
upstream e non sono prerequisiti dell'installer/build pubblico. Nessun dato
privato individuato. Gli altri snapshot Fedora/fprintd/Plasma, architetture
respinte, vecchi build e guide operative sono stati spostati sotto `development/`.

## Verifiche documentali

La guida pubblica usa una sola procedura clone/install con URL pubblico,
`$HOME/goodix-27c6-5125` e `$HOME/goodix-5125-materials`; la destinazione runtime
è gestita dall'installer. La recovery è disponibile nel PATH ed è indipendente
dal clone. Il sensore resta presente. Nessuna promessa di fallback immediato
in TTY: attesa stock indicativa circa 30 secondi e STOP/supporto se la password
non compare o fallisce. Il nuovo percorso completo resta in attesa della prova
fisica Utente; nessuna pubblicazione o installazione fisica è stata eseguita qui.


## Esito finale offline — 24 settembre 2026

La copia dei **338 file pubblici staged**, priva di `.git` e `development/`, ha
superato **112 test**: 12 builder, 40 materiali, 14 installer, 46 removal.
La qualifica comprende i due eseguibili C mirati per i materiali, compilati con
`-Werror` usando header SDK e librerie host, e i due bundle sintetici distinti
attraverso il loader nativo. Nessun materiale reale, USB, privilegio o PAM host
è stato usato. Questi risultati non sono una compilazione nativa completa del
payload libfprint, che resta non eseguita per dipendenze Fedora mancanti.

Review documentale separata: **14 Markdown progetto, 54 link locali**, più
**4 Markdown reference e 5 link locali**; totale **18 documenti e 59 link**.
Tutti i target e gli anchor risolvono; tre blocchi shell superano `bash -n`, con
un solo blocco canonico di installazione. Nessun link pubblico raggiunge
`development/`; nessun percorso privato o vocabolario operativo interno compare
nella narrativa pubblica. Le due ultime correzioni limitano il rifiuto del
lifecycle alla mancata quiescenza/inibizione e il claim di pulizia dei buffer al
loader/sessione C runtime. Non modificano codice o risultati delle suite.

Il `LICENSE` root descrive solo componenti presenti e relative licenze, conserva
esplicitamente il precedente grant BSD senza riferimenti milestone e non cambia
le licenze per-file. Il ledger del preprocessing Rocky ora indica il commit
originario completo `227eba219fa9e3fbac5bd59aca79f624f67cd11b`, coerente con
snapshot, sorgenti e manuale; è una correzione di provenance, non un relicensing.
I percorsi canonici di bootstrap/manuale/roadmap sotto `development/` esistono e
sono coerenti. Le metriche finali del manuale e della roadmap sono consolidate
separatamente dal reviewer principale.

## Risposte alla review indipendente richiesta dal §19

Le risposte seguenti qualificano **il tree e il percorso offline verificato**.
Non attribuiscono una disponibilità attuale all'URL pubblico né una prova fisica
non eseguita. Il repository pubblico corrente deve prima ricevere dall'Utente
la copia del nuovo tree; l'AI non esegue questa pubblicazione.

| Domanda del prompt | Risposta e limite |
| --- | --- |
| `CAN_A_NEW_USER_CLONE_THE_PUBLIC_REPO_AND_INSTALL_WITH_ONE_DOCUMENTED_BLOCK?` | Sì per la procedura e gli input pubblici verificati offline, **dopo che l'Utente avrà pubblicato questa versione**. L'URL corrente non fornisce ancora il nuovo installer; installazione fisica completa non ancora qualificata. |
| `DOES_THE_INSTALLER_WORK_FROM_A_DIFFERENT_CLONE_PATH?` | Sì nello scope sintetico: entrypoint reale risolve il proprio root e usa path alternativi/cwd estranea, senza cercare altri clone. |
| `ARE_THE_FIVE_FILES_STAGED_IN_ONE_CLEAR_STANDARD_LOCATION?` | Sì: `$HOME/goodix-5125-materials/`, nomi esatti documentati, esterna al clone. |
| `DOES_INSTALLER_COPY_AND_SECURE_THEM_AUTOMATICALLY?` | Sì, verificato offline: validazione preventiva, importazione atomica, root `0700`/`0600`, mapping/label gestiti dalla transazione; SELinux reale resta parte della prova fisica. |
| `IS_GUIDOS_PRIVATE_READER_PIN_REMOVED?` | Sì: il manifest dell'Utente governa i binding del proprio bundle; due reader bundle sintetici differenti accettati. Rimane soltanto l'identità OEM DLL globale qualificata. |
| `DOES_ANY_PUBLIC_PATH_REQUIRE_PRIVATE_GIT_HISTORY?` | No: copia priva di `.git`, provenance da contenuti e pacchetti, suite offline superate. Le citazioni upstream non sono dipendenze dalla history privata. |
| `DOES_ANY_PUBLIC_PATH_REQUIRE_DEVELOPMENT/?` | No: directory assente nella copia testata; nessun input build/install/test o link pubblico la richiede. |
| `DOES_ANY_RELEASE_PATH_REQUIRE_READER_DETACH?` | No: lifecycle con lettore presente, quiescenza/inibizione software, nessun accesso USB diretto da installer/remover. |
| `CAN_UNINSTALL_AND_FORCE_REMOVE_WORK_AFTER_THE_CLONE_IS_GONE?` | Sì nello scope eseguibile sintetico: comandi installati standalone continuano a funzionare senza clone; non importano helper dal repository. |
| `IS_EVERY_NONPUBLIC_TRACKED_FILE_UNDER_DEVELOPMENT/?` | Sì nell'audit del tree finale: tutti gli 852 percorsi iniziali classificati e materiale non pubblico fisicamente ricollocato; nuove aggiunte pubbliche incluse nella verifica finale. |
| `WOULD_COPYING_EVERYTHING_EXCEPT_DEVELOPMENT/PRODUCE_A_COHERENT_PUBLIC_REPOSITORY?` | Sì per il tree sorgente versionato verificato: 338 file, dipendenze Fedora dichiarate, documentazione coerente e test offline autonomi. Non copiare la history `.git` privata; pubblicazione e qualifica fisica restano dell'Utente. |

**Esito review documentale/strutturale: ACCEPT per la closure offline.** Rimangono
le condizioni esplicite di pubblicazione Utente e prova fisica del medesimo
blocco pubblico; nessuna delle due è stata simulata come già avvenuta.


## Post-review correction — device-material acquisition guide

Independent review after the R6/R7 restructuring found that the public
`docs/DEVICE_MATERIALS.md` had been reduced to the runtime contract and had
lost the detailed acquisition reference that was present at
`4f244fa2946da94406f03991332f8a70e9a8b401`. That removal was not required by
the publication boundary.

The acquisition reference has been restored from that commit as the technical
base and reconciled with the current public release tree:

- standard final staging is `$HOME/goodix-5125-materials/`;
- the public `./install.sh` performs validation/import into
  `/var/lib/goodix-5125-poc/`;
- the retired managed importer and roadmap references are not restored;
- the current binding implementation path is
  `libfprint-driver/goodix_action_binding.c`;
- Step 10 builds the canonical `goodix-5125-device-materials-v1` manifest
  directly; the historical `d232-target-material-v1` format is not an
  end-user input;
- the guide remains informational acquisition documentation: the public release
  does not ship automated DPAPI/USBPcap/manifest-generation tools.

README, installation and validation wording were aligned so a first-time user is
sent to the detailed material guide instead of being told only to arrive with a
pre-existing bundle. No runtime, installer, protocol or safety code changed in
this documentation correction.


## Live installation audit correction — terminal preservation

The first execution of the documented public installation block on a fresh
Fedora 44 KDE VM exposed a documentation/UX defect: the block began with
`set -euo pipefail` directly in the user's interactive shell. A non-zero
command therefore terminated the whole Konsole session before the User could
inspect the failing output. At that point the repository had not yet been
cloned, so no root cause beyond "failure before clone completed" was inferred.

The public block was corrected to use explicit per-step error handling inside a
temporary shell function. It no longer changes the interactive shell's errexit
state and contains no `exit` command. It reports a stable
`GOODIX_INSTALL_BLOCK=STOP STEP=... EXIT_CODE=...` marker and leaves the
terminal open on every handled failure. This is a documentation/installer-UX
correction only; no runtime, material, USB or authentication code changed.
