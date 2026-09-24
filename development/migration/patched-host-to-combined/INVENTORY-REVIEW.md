# Review del PC patchato — inventario consegnato il 20 settembre 2026

**PM_DECISION=HUMAN_REQUIRED — MIGRATION_AND_CANDIDATE_LIVE**

La review iniziale e16bc6404e8b60ae683d79347e495f5029aee681 ha identificato il
gate sul formato. L’Utente ha successivamente autorizzato esclusivamente la
preparazione offline della conversione reversibile del manifest: il gate di
preparazione è superato, quello di esecuzione reale rimane. Le evidenze
inventariali sottostanti restano invariate; la closure finale è aggiornata.

Ripartenza della fase inventario su `development`, HEAD `4e571eb72cc9c213cfbebab4a745afeefee6373c`,
worktree pulito e ref remoto privato allineato. La baseline del task originale
resta `dfc33c3e44d6172dc7244b4f958ad71be3774be5`. Nessun altro worktree, reset,
stash, cambio branch o autenticazione dell'AI. Le query host restano uid 1000;
i metadata root-only provengono dal JSON consegnato dall'Utente.

## Correttivo successivo alla run f97de44: RPM e riarmo

Evidenza operatore: preflight reale PASS, apply mascherato PASS, password PASS,
release, install STOP `plasmalogin_vendor_pam_package_drift`, rollback automatico
PASS. Nessun workflow sensore. Nuovo preflight STOP sulla recovery preservata.
I precedenti risultati solo-offline sono quindi aggiornati senza inferire un
PASS candidate/live. HEAD iniziale `f97de44e0192f249ccb80fd9b32e1488195f0101`, pulito.

Query read-only uid 1000 e riproduzione con librpm dimostrano l'mtime:

- PAM Plasma package: 1010 byte, SHA `c6fc4a0b…`, 0100644 root/root, data
  `1788825600`, caps `(none)`, verifyflags `4294967295`, fileflags 0;
- file storico dopo rollback: 1100 byte, SHA `559910be…`, mode/owner corretti,
  label `system_u:object_r:lib_t:s0`, `mtime_ns=1789933663280138531`, flags `S.5....T.`;
- trasformazione precedente riprodotta in /tmp: **solo RPMVERIFY_MTIME=32**;
  stessa post-image con mtime package: **RPMVERIFY_NONE=0**. Header RPM copiato
  in memoria e soli path/uid/gid adattati al test utente. Nessuna scrittura RPM DB;
- KDE package `plasma-workspace`: post-image 520 byte, SHA `8b3181ce…`, stessa
  data, config/noreplace 17; proprietà/metadata entrambe qualificate nel piano.

Non sono log acquisiti durante il breve intervallo post-apply reale. Sono query
attuali e una riproduzione del difetto con l'effettivo verificatore RPM. La
prima verifica in sandbox riportava anche U/G per la mappatura degli utenti:
scartata come evidenza host, poi ripetuta fuori sandbox sempre uid 1000.

Il gate post-image confronta tutti gli attributi rilevanti e ripete il controllo
RPM del manager prima di release; il manager production resta immutato. Le nuove
snapshot registrano mtime ns e lo ripristinano su rollback. Quello precedente
alla run f97de44 non fu registrato e non viene inventato.

Il rearm autentica codice e backup correnti oppure esatti di f97de44, verifica
baseline restaurata, archivia per digest completo del vecchio state e conserva
un riferimento nel nuovo state. Exchange atomico mantiene `/run/gx` utilizzabile.
Due chiamate sono idempotenti; collisioni estranee STOP; pending prima exchange
STOP senza cleanup, pending dopo exchange completabile dal medesimo comando.
La recovery annulla anche il rearm preparato prima di un nuovo apply.

Test: 26 migration, 18 launcher, 13 corrective; 31 managed con login completo,
PAM 18/15/3 normale e sanitizer, deploy 13 e parser 3 casi in entrambi i modi.
I casi mirati coprono entrambi i failure reali, mtime e metadata diversi,
partial install, import della snapshot realmente versionata, rearm/secondo apply,
foreign/modified short, backup/archivio estranei e drift della baseline.
Nessuna lettura host dei quattro binari o template; per essi soltanto metadata
nei futuri comandi umani e fixture sintetici nei test.

Review PM Git-native separata dall'implementazione: esamina direttamente codice,
diff e output; nessuna seconda istanza agente. README e manuale sono aggiornati,
nessun Dxxx nuovo, governance/production invariati. Dopo review positiva la
consegna viene costruita due volte dal commit pulito e i 36 file confrontati;
SHA finali vengono riportati nell'handoff senza un commit successivo che li
renda stale. Il prossimo passo resta umano e da KDE, senza cleanup sulla TTY.

Decisione PM del correttivo: `ACCEPT_AND_CONTINUE` alla consegna finale. Log e
test sono stati riesaminati direttamente; il syscall exchange/reversal è
verificato come uid 1000 anche con sole directory temporanee sul filesystem
Btrfs del workspace (stesso tipo osservato per /var/lib), oltre alle root
sintetiche tmpfs. Il preflight aggiornato resta il probe host read-only prima
di rearm/apply; la verifica della post-image reale resta un gate tecnico prima
di release. Nessuna nuova evidenza privilegiata è necessaria per la preparazione.

## Correttivo successivo a 7d9ccfa: causa dello STOP e UX

Il primo preflight umano è terminato read-only `fprintd_dropins_drift`:
nessun apply/install/conversione host. Il controllo diretto come uid 1000
mostra il percorso aggiuntivo **vendor**
`/usr/lib/systemd/system/service.d/10-timeout-abort.conf`, prima dei tre 90/95/96.
RPM owner `systemd-259.9-1.fc44.x86_64`; file root:root 0644, 596 byte,
SHA effettivo = RPM = `ae6b234f92bc22f1201a7572b59b454c9809f33c80d13f361b9674e1801acc37`.
Contenuto: sola opzione `TimeoutStopFailureMode=abort` più commenti Fedora.
La lista del preflight era incompleta. Il piano ora preserva e qualifica quel
solo file: nessuna wildcard, nessun file aggiuntivo ammesso implicitamente.
La nuova qualifica delle proprietà host pubbliche è PASS senza root.

Il task operativo impone >=95% copia-incolla da KDE: `operator.sh preflight`
e `operator.sh run` sostituiscono la trascrizione dei comandi sulla TTY.
Il launcher controlla la baseline PAM password-only prima del singolo pkexec,
non autentica di nuovo dopo l'installazione, verifica la password come guido
mentre fprintd è mascherato e termina prima dei workflow biometrici manuali.
La root console già osservata attiva resta solo emergenza. `/run/gx` avvia
recovery salvata, indipendente dal checkout, compresa la rimozione candidate.
Il manager production non cambia; la sua copia per recovery rimuove soltanto
il Git-root lookup inutilizzato ed è vincolata alla sola modalità uninstall.

Test mirati: migration/policy 26, launcher 18, inclusi vero manager su root
sintetica, recovery salvata, interrupt, privilege failures simulati, receipt e
cwd. Nessuna chiamata root/sudo/pkexec/USB reale nei test. Il difetto iniziale
è stato riprodotto contro l'elenco completo; aggiunte/omissioni/riordino,
duplicati e contenuto vendor diverso restano rifiutati. PM review Git-native
separata dall'implementazione, non review di una seconda istanza agente.
Regressioni rieseguite PASS: inventory 8, deploy Polkit 13, parser nelle tre
varianti normale/ASan/UBSan, build sanitizer e login completo con 31 test managed,
PAM Polkit 18, sudo 15, incrociati 3 sia normale sia sanitizer. La review ha
controllato direttamente diff, log, percorso da cwd esterno, sorgenti salvati,
ordine password/mask/install/status e assenza di modifiche production/governance.
Decisione PM: ACCEPT_AND_CONTINUE alla preparazione della consegna dal nuovo
HEAD pulito, con gate reale invariato. I risultati candidate/receipt del commit
finale sono verificati dopo il commit e riportati nell'handoff, senza generare
un successivo commit che ne invalidi la corrispondenza SOURCE_COMMIT.
Sono stati riletti AGENTS/START e le sezioni correnti del manuale; non è presente
un documento separato denominato Linee Guida nel clone o nei percorsi documentali
esaminati. Le linee guida correnti incorporate in AGENTS/manuale sono applicate;
nessuna policy viene modificata.

## Evidenza ricevuta e limiti

File designato dall'Utente: `/home/guido/goodix-inventory.json`, 65096 byte,
SHA-256 `58fef9bbcafec8485e3dd428d7cc19347b493ee7d036f99bb61513e5d24924a9`.
È output del collector, non istruzioni né una garanzia di installabilità.
L'Utente attesta inventario privilegiato completato e stderr vuoto; non
aggiunge dettagli sull'identità/dialogo effettivamente usati. Il precedente
`su -` fallito non viene reinterpretato. Il comando pkexec consegnato resta
provenance del percorso proposto, non una nuova operazione da ripetere.

JSON schema 1, `outcome=REVIEW_REQUIRED`, 262 righe: 232 righe di dati
(metadata, digest o campi proiettati), 27 `ABSENT`, 3 `UNKNOWN_STOP`.
Non sono 262 oggetti distinti: un file può avere righe separate.
I tre limiti di profondità riguardano esclusivamente:

- `/var/lib/goodix-5125-poc/d236-results/archive`;
- `/var/lib/goodix-5125-poc/d275-history/attempt-1`;
- `/var/lib/goodix-5125-poc/d275-history/attempt-2-pre-corrective`.

Questi alberi restano `PRESERVE`, opachi, senza ricorsione aggiuntiva. I limiti
non vengono cancellati dal report né interpretati come assenza. Non serve
ampliare l'inventario degli archivi per disattivare le selezioni software.
Il JSON non contiene contenuti/digest di template o del bundle protetto.
Non è stato copiato in Git, in un export o nella candidate.

## Ordine degli overlay

| Oggetto | Stato ricostruito | Evidenza e limite |
|---|---|---|
| Fedora 44 KDE x86_64 | BASE | fprintd 1.94.5-5.fc44, libfprint 1.94.100-1.fc44, sudo 1.9.17-8.p2.fc44 |
| D285 | ACTIVE per selettore/PAM sudo; runtime SUPERSEDED_BUT_PRESENT | unico frammento sudoers osservato, byte ricostruibili dal generatore e hash corrispondente allo state |
| D290 manuale | ACTIVE sotto override login | PAM vendor modificato; esatta rimozione della riga storica ricostruisce il digest RPM in memoria |
| D293 | SUPERSEDED_BUT_PRESENT | state ACTIVE, manifest/wrapper/drop-in 95 coerenti; ExecStart effettivo selezionato dal 96 |
| D293/B5 | ACTIVE configurato | hook corrispondente allo state; modulo SELinux presente a priorità 400, contenuto effettivo non attestato |
| D297 KScreenLocker | ACTIVE configurato | state, backup vendor/managed e PAM corrente concordano |
| D297 runtime c372298 / ef302008 | SUPERSEDED_BUT_PRESENT | runtime e wrapper presenti, drop-in 99 assente; state D297/02 ACTIVE stale; previous-dropin corrispondente al pin |
| login-same-action | Non rilevato nei path osservati | nessuna affermazione di assenza su tutto il filesystem |
| login-early | ACTIVE configurato | drop-in fprintd 96 e greeter utente 96 selezionano lo stesso runtime |
| login-three | ACTIVE nel runtime early | PROVENANCE 98ec4e6cbbd06b9eff9e00dc9bb07629c62567a8, PAM 3/8, snapshot con otto backup correlati |
| managed / patch locale Polkit | ABSENT nei path canonici | nessun current/state/wrapper managed; nessun override/leaf PAM o modulo locale Polkit |

Precedenza provata: **Fedora → D285 (90) → D293 (95) → login-early (96),
aggiornato da login-three**. B5, PAM vendor D290 e KScreenLocker sono rami
aggiuntivi. Gli state `ACTIVE` non prevalgono sulla configurazione effettiva.
L'ultima query host ha fprintd `inactive/dead`, ExecStart
`/usr/local/sbin/goodix-login-early-fprintd`; il greeter configurato è quello
sotto `/usr/local/lib64/goodix-27c6-5125/login-early/`.

## PAM, sudo e dati preservati

Authselect valido: `local with-silent-lastlog with-mdns4`. system-auth usa
pam_unix, senza pam_fprintd; fingerprint-auth disabilita l'autenticazione
fingerprint. Nessun `.rpmnew`/`.rpmsave` nei path PAM esaminati. sudo/sudo-i e
Polkit vendor coincidono coi digest RPM; non sono stati autenticati dall'AI.

| File | SHA-256 corrente | Significato |
|---|---|---|
| `/etc/pam.d/sudo` | `fb766aab394fc417c72f07365ea29f9ba65bb101991293a14a6e81aed6202f77` | conforme al digest RPM; include system-auth |
| `/etc/pam.d/sudo-i` | `268616ef041372c9cdc170df1b4deea85cbf67928b17451759bfd24ac689b803` | conforme al digest RPM; include sudo |
| `/etc/pam.d/goodix-d285-01-sudo` | `dd853208220902d1737357a02e47a6c1ac47e5ddf56bf02247efda52e17f2048` | max-tries=3 timeout=45, fallback pam_unix; diverso dal limite originale D285 a uno; pin state verificato |
| `/etc/authselect/system-auth` | `2e53f704372b6c7fb69cdc4dfd6c27456d642c83feff8b1588fa1f9cb1126cd0` | password baseline già attiva |
| `/etc/authselect/fingerprint-auth` | `9e0ea3820ffe5b6ff6f4cea4896b40e244077830538ea824911759095f8b4a8a` | fingerprint globale disabilitato |
| `/usr/lib/pam.d/plasmalogin` | `559910be8631f69398332b2979bd5c18f1155a7af0960215d175694082cae2ac` | modifica storica D290; RPM atteso `c6fc4a0bc2d89f88fa15ca7e9a6c5aaeccfbe66897755b5416ce9c5e35b4e40b` |
| `/etc/pam.d/plasmalogin` | `91a632300cde2e9bd351625a49558cb0531a035338221039d3a01e671ad9cbcc` | override early con max-tries=3 timeout=8 debug |
| `/etc/pam.d/kde-fingerprint` | `858713e5b3b7ecf58a91f6fe5b736f344aa6c5b9c207318e6ac552a1a3ffb3d1` | delta D297; RPM atteso `8b3181ce5979f498e2cd07acaf3f57c63b1e2f9593e44bfa9027b6dd8bb62437` |
| `/usr/lib/pam.d/polkit-1` | `a4454c54582a86fd4560321b22ffb7639485968438a07d5412fadc102d62cf49` | vendor; override `/etc` assente |
| hook B5 `50-goodix-fprint-account-delete` | `42024daf2f33372014d5a1f45059aeb49a8be4b78198899e9cb9b331a813af10` | 0755 root:root, pin hook/state verificato; policy attiva non attestata |


`/etc/sudoers` (`c63df9a912d5f33614f0daab3996b400d36cac6e651a8b110f02dad15f885572`)
e `/etc/sudo.conf` (`9af0d568d19a8c778d17202647b5eb75e36b074f42b2df65aa1ea23e567e3be3`)
corrispondono ai digest RPM letti senza privilegi. L'unico frammento
`/etc/sudoers.d/90-goodix-d285-01` coincide con i byte generati da
`Defaults:guido pam_service=goodix-d285-01-sudo` seguiti da newline, digest
`9c98b1ffa91b889a7d17bd654aaa77715dc751a0271e5fa1b168135f891480e1`.
Il collector resta lessicale: una futura transazione userà anche il vero
preflight della candidate, senza inferire una policy effettiva dal solo JSON.

Il template osservato è `/var/lib/fprint/guido/goodix_27c6_5125/0/7`, regular,
root:root 0644, 521555 byte; directory antenate 0700. Il tree bounded in questo
ramo è completo. Presenza e numero sono osservati, validità/compatibilità del
template non sono una nuova prova biometrica. Il PASS sudo resta quello umano.

`/var/lib/goodix-5125-poc` è 0700 root:root; i cinque regular 0600 root:root sono
transport (88 byte), CONFIG90 (224), manifest (2305), DLL (5771496), cache FDT
(13520). Anche staging e archivi restano preservati. Nessun byte/digest di
questi file è stato letto. Nome, dimensione e permessi non provano readiness.

## Correlazioni di ownership e recovery

Le 57 verifiche puntuali sul JSON e sui soli file software leggibili passano:

- D285: PAM, selettore, wrapper, daemon vendor, manifest e drop-in coincidono
  coi pin di state. Il PASS funzionale corrente non viene invalidato.
- D293: wrapper, indice runtime e drop-in coincidono coi pin; lo stato
  precedente D285 concorda coi pin della stessa baseline. La snapshot systemd
  storica non è una descrizione del sistema dopo early/login-three.
- D297/02: wrapper e indice coerenti, previous-dropin coerente; il suo drop-in
  attivo è assente. Vietato usare lo state stale per ripristinarlo implicitamente.
- B5: hook corrente coincide col pin; stato dichiara modulo
  `goodix_fprint_account_delete`, priorità 400. Directory modulo osservata;
  digest CIL attivo da verificare prima di qualsiasi rimozione. La policy
  package è ora 44.9-1.fc44, mentre lo state registra 44.8-1.fc44.
- KScreenLocker: entrambi i backup corrispondono ai pin, managed corrisponde al
  file corrente. Invertendo la singola trasformazione in memoria si ottiene
  esattamente il digest vendor RPM; nessuna scrittura host.
- Early: tutti i 16 pin software proiettati coincidono con i digest del JSON
  o dei file leggibili, e i due symlink sono quelli attesi. Il backup
  login-three contiene gli otto file attesi, tutti con digest `before`
  corrispondente; sette `after` verificabili coincidono coi file correnti.
  Il digest completo dello state early corrente non era raccolto: non si
  dichiara verificato l'ottavo `after` né un rollback storico eseguibile.

Il delta D290 è invertibile in memoria: rimuovere l'unica riga
`auth        sufficient    /usr/lib64/security/pam_fprintd.so max-tries=3 timeout=45 debug`
produce il vendor Plasma `c6fc4a0b…`. Anche questo è un risultato sui byte
software, non un ripristino eseguito sul PC.

## Baseline target deterministica, preparata offline

| Oggetto | Classificazione per la futura migrazione | Condizione |
|---|---|---|
| PAM e sudoers D285 | REMOVE | solo allo switch; pin correnti esatti e backup verificato |
| fprintd drop-in 90 D285 / 95 D293 / 96 early | REMOVE | transaction scoped, nessun vecchio uninstall |
| greeter drop-in 96 early | REMOVE / RECREATE_BY_CANDIDATE | disattivare selezione storica, poi nuovo 99 managed |
| override `/etc/pam.d/plasmalogin` | REMOVE / RECREATE_BY_CANDIDATE | preservare copia corrente per recovery |
| vendor `/usr/lib/pam.d/plasmalogin` D290 | RESTORE_VENDOR | byte ricostruiti identici al digest RPM |
| `/etc/pam.d/kde-fingerprint` D297 | RESTORE_VENDOR / RECREATE_BY_CANDIDATE | copia vendor qualificata, poi trasformazione managed |
| `/usr/local` runtime e wrapper storici | PRESERVE, inattivi dopo switch | nessun drop-in/consumer deve selezionarli; nessuna cancellazione necessaria |
| D297/02 state e previous-dropin | PRESERVE, STATE_ONLY | non riattivare dal solo flag ACTIVE |
| altri state/rollback/authselect backup storici | PRESERVE | recovery e provenance; non consumarli con vecchi uninstall |
| authselect e system-auth/fingerprint-auth | PRESERVE | password-only già configurato; non riabilitare with-fingerprint |
| sudo/sudo-i e Polkit vendor | PRESERVE / RECREATE_BY_CANDIDATE | integrazioni locali prodotte dal manager |
| hook e modulo SELinux B5 | REMOVE / RECREATE_BY_CANDIDATE | policy di recovery ricostruita; futuro preflight richiede hash CIL effettivo, priorità 400 e modulo abilitato/unico |
| template, staging, archivi, quattro binari materiali | PRESERVE | zero letture/conversioni/rimozioni biometriche o modifiche dei binari |
| manifest materiali installato | MIGRATE | preparazione autorizzata; hash storico esatto obbligatorio, originale conservato integralmente, nessun altro materiale convertito |
| selezione fprintd e greeter managed | RECREATE_BY_CANDIDATE | solo dopo baseline supportata e recovery pronto |

La classificazione è implementata nel piano fisso `host-plan.json`. Il manager
rifiuta i vecchi drop-in, il vendor PAM modificato, PAM custom e selettori sudo;
non si modificano tali controlli per accettare il PC attuale.

## Strategia e risoluzione offline del formato

A) Rimozione manuale selettiva: i file sono individuati, ma resta da rendere
atomica/verificabile la recovery fra PAM, selettore, policy e runtime.
B) Uninstall storici: scartati. D285 enumera USB, avvia fprintd, cancella un
template e riabilita with-fingerprint; D293 ripristina una snapshot precedente
al 96; D297 ha state stale; early non ripristina D290 nel vendor PAM.
C) Nuova transazione specifica: preferita per la parte overlay, con pin,
backup propri e recovery ripetibile; implementata e verificata offline.
La rimozione del selettore D285 precede quella del PAM che seleziona; il
runtime è mascherato e inattivo. Le selezioni fprintd vengono tolte 96→95→90,
poi si ricostruisce la baseline. I runtime storici restano senza selettori.

Il blocker precedente alla fase E/F è il contratto dei materiali. Il manuale,
la ricetta `development/patches/login-three/prepare.sh` e la PROVENANCE
installata concordano sul loader D293 e61fce3. Il manifest D232 di analisi,
versionato e dichiarato non segreto dalla propria provenance, ha 2305 byte e
corrisponde esattamente al pin del vecchio loader. Ha oggetti annidati e uno
schema diverso dai dieci campi stringa del v1 canonico. Non si è letto il
manifest host per stabilirlo.

`check-material-boundary.sh` compila direttamente il loader canonico e il
binder senza USB/daemon. Copia quel solo fixture di analisi in una directory
temporanea e cambia unicamente owner atteso per il test utente. Risultato:
`PROTECTED_CONTENT`, un solo file letto, zero bind, nessuna apertura di
transport/CONFIG90. Il controllo positivo usa un v1 sintetico della stessa
dimensione e arriva all'apertura fallita di un transport volutamente assente.
Passano normale e ASan/UBSan. La differenza è di schema, non di permessi/size.
Questo non è una prova eseguita sui materiali reali; la loro identità resta
inferita con forte supporto dalla provenance, non misurata.

Il test managed esistente mostra che `PROTECTED_MATERIAL_READY=true` è
compatibile con cinque file dal contenuto sintetico arbitrario: il controllo
è solo metadata. Un install/status PASS su root sintetica non giustificherebbe
quindi la migrazione senza risolvere il formato.

## Conversione autorizzata, minima e deterministica

`manifest.py` accetta esclusivamente il fixture D232 di 2305 byte con SHA-256
`1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15`.
Non legge file e non cerca materiali. I dieci campi risultanti sono:

| Campo canonico | Provenienza |
|---|---|
| schema | costante `goodix-5125-device-materials-v1` |
| vid, pid, app | target storico; rimozione del prefisso `0x` da vid/pid |
| config90_sha256 | config90.body_sha256 |
| a2_response_sha256 | a2.response_body_sha256 |
| chip82_response_sha256 | chip82.response_body_sha256 |
| otp_a6_response_sha256 | otp_a6.response_body_sha256 |
| transport_sha256 | pin già applicato dal loader e61fce3 goodix_target_material.c |
| fdt_cache_sha256 | pin già applicato dal loader e61fce3 goodix_runtime_inputs.c |

I due digest mancanti nel JSON storico non vengono ricalcolati dal deposito;
sono gli stessi vincoli di accettazione del runtime installato. Il test estrae
indipendentemente tutti e sei i pin dagli array C del commit storico completo,
poi li confronta con la conversione. Serializzazione: ASCII, chiavi ordinate,
indentazione 2, newline finale. Metadati narrativi/redundanti restano nel backup
integrale; nessun campo runtime aggiuntivo o fallback permissivo.

Il vero parser canonico accetta la conversione e arriva alla lettura del
transport deliberatamente assente, normale e ASan/UBSan. Non è una prova del
binding completo o dei materiali reali. Il file host viene letto e qualificato
soltanto dal futuro preflight umano: qualsiasi differenza interrompe tutto.

## Transazione e rollback verificati

Piano derivato dall'inventario fornito e dai soli file software leggibili:
10 file software da rimuovere/ripristinare, 67 guardie software di preservazione,
proiezione lessicale dello state D285 priva di pin biometrici, 10 oggetti
metadata-only per template/quattro binari e relativi alberi. Il manifest è
l'undicesimo target, con il pin storico indipendente. Lo staging e gli archivi
sono esclusi dalle scritture/letture di contenuto, senza inventariarli di nuovo.

Il modulo B5 originale è ricostruito da
`232e9401ca3ce72a0f9f08448deb46c6251aaa2a`,
`deployment/d293-phase-b-account-lifecycle/goodix_fprint_account_delete.{te,fc}`.
`prepare-policy.sh` verifica TE/FC, compila senza installare, verifica PP da
2086 byte SHA-256
`674740ba782b501a68dbaff9bef04d725cc9e88adad6f37c6f3c468a2cc71d03`
e CIL `e993729e97ad84f2a89e6cd41bbdb2e5f557a9898f0d96962183053bea0a69f3`.
La dimensione 563 dell'HLL compresso nel deposito SELinux non è quella del PP.
Il contenuto effettivamente attivo rimane da confrontare nel preflight root.

`migration.py` non ha override root/test nel CLI: root reale è esclusivamente
operatore; i test costruiscono esplicitamente Files sotto `/tmp` come utente.
I path usano directory descriptor, O_NOFOLLOW/O_NOATIME, regular file single-link,
owner/mode e sole etichette SELinux supportate. Snapshot root-only atomica
prima dello switch; copie originali, policy e codice recovery verificati.
Mask runtime fino alla prova password; release esplicita prima del vero manager.
Nessun comando sensor-reaching, import, authselect, sudo o pkexec nel tool.

Rollback rifiuta candidate/residui, drift e file temporanei estranei; ripristina
originale manifest, file PAM/selettori e policy. Rileva cambiamenti dei quattro
binari/template tramite metadata senza leggerli. I test provano il recupero
anche usando il codice conservato nella snapshot, senza dipendere dal checkout.
La snapshot non viene cancellata su PASS o rollback. Una snapshot incompleta
`.pending` precede tutte le modifiche di configurazione e richiede STOP.

Il codice non garantisce recovery automatica da qualunque modifica concorrente,
corruzione, power-loss o failure della policy SELinux reale. La console root
transitoria indipendente dal logout resta il canale di recovery umano; se non
è ottenibile con password prima dello switch, non iniziare la migrazione.

## Validazione e review PM

Review Git-native del delta da e16bc6404e8b60ae683d79347e495f5029aee681,
con alternanza Executor/PM; fase PM separata, senza modifiche durante la review.
Non è stata usata una seconda istanza agente. Correttivi emersi dalla review:
dimensione PP vs HLL compresso, rifiuto del padre mancante prima di rollback,
conservazione di temporanei preesistenti su O_EXCL fallito, eccezione di lettura
solo per il temporaneo del manifest durante recovery, e controllo del vincolo
HEAD esatto imposto dal vero manager. Nessun controllo production indebolito.

Prove eseguite senza root/USB/autenticazione:

- 8 test inventario; 23 test conversione/migrazione/policy (includono 13
  interruzioni: mask, undici file, rimozione policy), errori durante snapshot,
  drift, link/FIFO, file temporanei parziali, CLI reale da cwd diverso,
  rollback idempotente, preservation e codice recovery salvato;
- vero parser: storico rifiutato, v1 sintetico della stessa dimensione accettato,
  conversione effettiva accettata, tutti normale e ASan/UBSan;
- build production completa normale e sanitizer; suite login completa con
  protocollo/lifecycle, daemon/private-bus, greeter e 31 managed transaction;
- PAM Polkit 18, sudo 15, incrociati 3, in normale e sanitizer; deploy Polkit 13;
- candidate completa preparata due volte da e16bc6: tutti i 36 file identici,
  indice SHA256SUMS `a91ec4eac1692bdf03f88245dd7a832c1970797c71647604e0d2406f8b8312e2`,
  SBOM SPDX 2.3 con 50 package, 34 file e 84 relazioni;
- vero manager su root sintetica post-migrazione: install/status/uninstall
  PASS, ritorno alla baseline senza D285, poi rollback storico PASS;
  failure candidate dopo policy/KScreenLocker/login/Polkit ripristina la
  baseline post-migrazione, recuperabile con lo stesso rollback.

Per l'esecuzione il manager richiede SOURCE_COMMIT = HEAD corrente: la candidate
preliminare e16bc6 **non viene consegnata per installazione dopo questo commit**.
La preparazione/riproduzione finale dal commit pulito è verificata nuovamente;
SHA completo e indice finali sono nel MANIFEST, nella ricevuta di consegna e nel
report finale. Nessun sorgente production cambia in questa transazione.

Le root sintetiche usano systemctl/SELinux/identità simulate: provano percorsi,
preflight strutturali e ripristino, non l'accettazione del vero host. La build
compila il profilo production, ma il parser test interrompe prima dei materiali.
Sanitizer ASan/UBSan con leak detection disabilitata per limite SDK/ptrace.
Le prime esecuzioni PAM in sandbox hanno incontrato limiti socket/librerie:
risolti usando uid 1000 fuori sandbox e librerie SDK linkate soltanto in /tmp.
Nessuna installazione di dipendenze host o esecuzione privilegiata dell'AI.

## Riesame metodologico prima della live

1. Cosa cambia: una transazione nuova qualificata sostituisce gli uninstall
   storici; si converte il solo formato e si usa l'intera candidate canonica,
   con root console indipendente e rollback già verificato offline.
2. Ipotesi nuova: il manifest con gli stessi pin storici espressi nel contratto
   canonico permette al runtime combined di usare i materiali/template esistenti
   e ai suoi consumer locali di operare senza i selettori storici.
3. Se fallisce: interrompere al primo confine, ripristinare quando possibile,
   poi diagnostica read-only mirata al failure reale. Non ripetere una live
   equivalente né sostituire materiali/loader o rilassare il parser.

Il fallimento precedente era accesso root `su`, non una prova di matching:
non viene contato come NO MATCH, né viene inventato un PASS nuovo del sensore.

## Closure corrente

```text
OUTCOME=HUMAN_REQUIRED
GATE=MIGRATION_AND_CANDIDATE_LIVE
HOST_INVENTORY=COMPLETE_BOUNDED_SCOPE_OPAQUE_ARCHIVES_PRESERVED
PRIVILEGED_READ_REQUIRED=FINAL_HUMAN_PREFLIGHT_ONLY
OVERLAY_ORDER=PROVEN_CONFIGURED_PRECEDENCE
D285_STATUS=ACTIVE_SELECTOR_PRESERVED_UNTIL_HUMAN_SWITCH
D293_STATUS=SUPERSEDED_BUT_PRESENT
LOGIN_EARLY_STATUS=SELECTED_WITH_LOGIN_THREE_DELTA
AUTHSELECT_CURRENT=local_with-silent-lastlog_with-mdns4
TARGET_BASELINE=PASSWORD_ONLY_WITH_EXISTING_DATA_AND_CANONICAL_MANIFEST
TEMPLATE_PRESERVATION=UNTOUCHED_HOST_PROVEN_SYNTHETIC_NO_CONTENT_READ
PROTECTED_MATERIAL_PRESERVATION=FOUR_BINARIES_UNTOUCHED_MANIFEST_ONLY_REVERSIBLE_PREPARED
MIGRATION_STRATEGY=C_FIXED_TRANSACTION
MIGRATION_APPLY=PREPARED_NOT_EXECUTED
MIGRATION_ROLLBACK=PREPARED_NOT_EXECUTED
CANDIDATE_PREFLIGHT_POST_MIGRATION=PASS_SYNTHETIC
CANDIDATE_UNINSTALL_BASELINE_RESTORE=PASS_SYNTHETIC
OFFLINE_TESTS=PASS
EXECUTABLE_CLOSURE=OFFLINE_VERIFIED_HUMAN_ROOT_AND_LIVE_PENDING
HOST_CHANGED=false
POLKIT_PATCH_INSTALLED=false
REAL_SENSOR_ACCESS=false
NEXT_OPERATOR_ACTION=KDE_OPERATOR_PREFLIGHT_THEN_RUN
```

Il singolo handoff operativo è [README.md](README.md). Nessun nuovo D-number,
nessuna modifica delle policy permanenti, nessun materiale del PC nel payload
candidate o nel review set pubblico; repository pubblico non toccato.
