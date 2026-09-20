# Review del PC patchato — inventario consegnato il 20 settembre 2026

**PM_DECISION=HUMAN_REQUIRED — MATERIAL_MANIFEST_COMPATIBILITY_DECISION**

Ripartenza su `development`, HEAD `4e571eb72cc9c213cfbebab4a745afeefee6373c`,
worktree pulito e ref remoto privato allineato. La baseline del task originale
resta `dfc33c3e44d6172dc7244b4f958ad71be3774be5`. Nessun altro worktree, reset,
stash, cambio branch o autenticazione dell'AI. Le query host restano uid 1000;
i metadata root-only provengono dal JSON consegnato dall'Utente.

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

## Baseline target proposta, ancora non installabile

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
| hook e modulo SELinux B5 | UNKNOWN_STOP → RECREATE_BY_CANDIDATE | ownership/digest policy da verificare; stessi nomi, collisione reale |
| template, staging, archivi, quattro binari materiali | PRESERVE | zero letture/conversioni/rimozioni biometriche o modifiche dei binari |
| manifest materiali installato | UNKNOWN_STOP | nessuna conversione autorizzata; incompatibilità del formato storico |
| selezione fprintd e greeter managed | RECREATE_BY_CANDIDATE | solo dopo baseline supportata e recovery pronto |

Questa è una classificazione, non `MIGRATION_PLAN=DETERMINISTIC`. Il manager
rifiuta i vecchi drop-in, il vendor PAM modificato, PAM custom e selettori sudo;
non si modificano tali controlli per accettare il PC attuale.

## Strategia e blocker di formato

A) Rimozione manuale selettiva: i file sono individuati, ma resta da rendere
atomica/verificabile la recovery fra PAM, selettore, policy e runtime.
B) Uninstall storici: scartati. D285 enumera USB, avvia fprintd, cancella un
template e riabilita with-fingerprint; D293 ripristina una snapshot precedente
al 96; D297 ha state stale; early non ripristina D290 nel vendor PAM.
C) Nuova transazione specifica: preferita per la parte overlay, con pin,
backup propri e recovery ripetibile; non ancora preparata per l'esecuzione.

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

Proposta da autorizzare: preparare offline una conversione reversibile del
**solo manifest host**, originale root-only conservato, tutti i binari e i
template invariati, nessuna azione sul sensore, esecuzione futura solo umana.
L'alternativa è una candidate privata con loader storico, divergente dalla
candidate canonica richiesta. Né conversione né ripristino dei quattro loader
sono implicitamente autorizzati. La prima viola l'attuale vincolo sui materiali;
la seconda cambia la strategia canonica. Dettagli e decisione nel README.

Non si richiede un nuovo inventario generico né un terzo tentativo di accesso
root. Il prossimo gate è la decisione di scope, previsto da AGENTS §§6.2/6.4,
prima di preparare azioni dipendenti. Nessuna live viene consegnata come READY.

## Closure corrente

```text
OUTCOME=HUMAN_REQUIRED
GATE=MATERIAL_MANIFEST_COMPATIBILITY_DECISION
HEAD=git_HEAD_del_review_set_su_development
WORKTREE=clean_after_review_commit
HOST_INVENTORY=COMPLETE_FOR_BOUNDED_COLLECTOR_SCOPE
PRIVILEGED_READ_REQUIRED=NO_REPEAT_INVENTORY_FUTURE_MATERIAL_CHECK_NEEDS_DECISION
OVERLAY_ORDER=CONFIGURED_PRECEDENCE_AND_PROJECTED_STATES_REVIEWED
D285_STATUS=ACTIVE_SELECTOR_PIN_VERIFIED_USER_SUDO_PASS_PRESERVED
D293_STATUS=SUPERSEDED_BUT_PRESENT
LOGIN_EARLY_STATUS=SELECTED_WITH_THREE_ATTEMPT_DELTA
AUTHSELECT_CURRENT=local_with-silent-lastlog_with-mdns4
TARGET_BASELINE=PASSWORD_ONLY_WITH_PRESERVED_GOODIX_DATA_MATERIAL_BOUNDARY_UNRESOLVED
TEMPLATE_PRESERVATION=UNTOUCHED_METADATA_REVIEWED_MIGRATION_PROOF_PENDING
PROTECTED_MATERIAL_PRESERVATION=UNTOUCHED_METADATA_ONLY_MIGRATION_PROOF_PENDING
MIGRATION_STRATEGY=C_SCOPED_TRANSACTION_PREFERRED_MATERIAL_DECISION_PENDING
MIGRATION_TOOL=INVENTORY_AND_OFFLINE_BOUNDARY_CHECK_ONLY_NO_APPLY
ROLLBACK=NOT_PREPARED_HISTORICAL_UNINSTALL_NOT_APPROVED
CANDIDATE_SOURCE_COMMIT=NOT_REBUILT_CURRENT_CANONICAL_SOURCE_4e571eb72cc9c213cfbebab4a745afeefee6373c
CANDIDATE_PREFLIGHT_POST_MIGRATION=NOT_RUN_BASELINE_UNRESOLVED
CANDIDATE_REPRODUCTION=NOT_RUN_AT_THIS_GATE
OFFLINE_TESTS=INVENTORY_8_SOURCE_CHECKS_MATERIALS_27_NORMAL_27_ASAN_UBSAN_BOUNDARY_2_PER_MODE_MANAGED_METADATA_1_PASS
EXECUTABLE_CLOSURE=OFFLINE_FORMAT_BOUNDARY_VERIFIED_HOST_APPLY_NOT_PREPARED
HOST_CHANGED=false
POLKIT_PATCH_INSTALLED=false
REAL_SENSOR_ACCESS=false
NEXT_OPERATOR_ACTION=DECIDE_OFFLINE_PREPARATION_OF_MANIFEST_ONLY_REVERSIBLE_MIGRATION
```

Build candidate normale/sanitizer, sudo/Polkit/private-bus suite completa,
transaction/migration failure injection e install/uninstall post-migrazione
non sono stati ripetuti né dichiarati PASS in questo step: il gate precede
la determinazione della baseline e la creazione dell'apply. Il runtime non è
modificato. Le prove precedenti restano documentate nel manuale nel loro scope.
Nessun nuovo D-number, pubblicazione, secret, biometric data o payload host.
