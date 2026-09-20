# Review del PC patchato — 20 settembre 2026

Baseline `development` @ `dfc33c3e44d6172dc7244b4f958ad71be3774be5`;
worktree iniziale pulito, unico worktree, tracking ref e `git ls-remote` del
repository privato concordanti. Nessun lavoro interrotto da recuperare.
Il prompt Utente richiede la migrazione, ma §§5/14 impongono prima il gate
di lettura privilegiata. Questa review chiude soltanto la fase non privilegiata
e la preparazione del singolo inventario. Non costituisce un piano apply.

Le query host sono state eseguite come uid 1000, senza sudo. Owner reali
root:root e systemd sono stati ricontrollati fuori dalla rimappatura del sandbox;
gli owner `nobody` visibili nel sandbox non sono metadata del target.

## Selezione e ordine degli overlay

| Oggetto | Stato osservato | Evidenza/limite |
|---|---|---|
| Fedora 44 KDE x86_64 | BASE | fprintd 1.94.5-5.fc44, libfprint 1.94.100-1.fc44, sudo 1.9.17-8.p2.fc44; unit vendor selezionabile `/usr/libexec/fprintd` |
| D285 | ACTIVE per PAM sudo; runtime SUPERSEDED_BUT_PRESENT | PASS sudo attestato dall'Utente; PAM presente. Selettore per-user ricostruito dal generatore; contenuto sudoers corrente ancora root-only |
| D290 manuale | ACTIVE sotto override login | `/usr/lib/pam.d/plasmalogin` modificato rispetto al digest RPM; il manuale documenta l'aggiunta diretta della riga fingerprint dopo la prova pragmatica |
| D293 | SUPERSEDED_BUT_PRESENT | runtime e wrapper per `e61fce313794922a2dab156a1b38a8ddc5837f19`, drop-in 95 presente; stato root-only |
| D293/B5 | ACTIVE configurato | hook userdel presente; stato root-only. La policy Enforcing è qualificata storicamente, installazione/ownership corrente ancora da chiudere |
| D297 KScreenLocker | ACTIVE configurato | PAM trasformato e state directory presenti; backup vendor e state root-only |
| D297 runtime c372298 / ef302008 | SUPERSEDED_BUT_PRESENT | entrambi runtime e wrapper presenti, drop-in 99 assente. State ef302008 e previous-dropin presenti: UNKNOWN quanto alla loro coerenza, non validazione di un rollback |
| login-same-action | Non rilevato nei path osservati | nessun runtime/wrapper/state omonimo nelle directory esaminate; non una prova di assenza su tutto il filesystem |
| login-early | ACTIVE configurato | drop-in fprintd 96 e greeter utente 96 selezionano il runtime omonimo |
| login-three | ACTIVE nel runtime early | PROVENANCE `SOURCE_COMMIT=98ec4e6cbbd06b9eff9e00dc9bb07629c62567a8`, `PURPOSE=PREPARED_LOGIN_THREE_ATTEMPTS`; PAM 3/8; backup root-only presente |
| managed / patch locale Polkit | ABSENT nei path canonici | nessun current/state/wrapper managed; nessun override/leaf PAM, stato, modulo locale, tmpfiles o drop-in helper Polkit |

Ordine della selezione runtime provato dalla configurazione e dalla query
systemd: **Fedora → D285 (90) → D293 (95) → login-early (96), aggiornato da
login-three**. D290 PAM, B5 e KScreenLocker sono rami paralleli, non semplici
override ExecStart. I due runtime D297 sono residui presenti con drop-in 99
assente. Non si inventa una cronologia di rimozione a partire dai timestamp.

`systemctl show fprintd.service` riporta `inactive/dead` ed ExecStart
`/usr/local/sbin/goodix-login-early-fprintd`; lettura soltanto, nessun avvio.
Il greeter configurato è `/usr/local/lib64/goodix-27c6-5125/login-early/greeter`.

## PAM, authselect, pacchetti e digest osservati

Authselect `local with-silent-lastlog with-mdns4`; `authselect check` valido.
Nessun `with-fingerprint`. I link system-auth e fingerprint-auth puntano agli
omonimi file sotto `/etc/authselect`; system-auth contiene pam_unix e non
pam_fprintd, fingerprint-auth contiene `pam_debug auth=authinfo_unavail`.
Nessun `.rpmnew`/`.rpmsave` nelle due directory PAM ispezionate.
Nessuna riga `sudoers:` in nsswitch corrente: non si inferisce da ciò una
policy effettiva sudo completa. `/etc/sudo.conf` è 0640 root:root, non leggibile.

| File | SHA-256 corrente | Significato |
|---|---|---|
| `/etc/pam.d/sudo` | `fb766aab394fc417c72f07365ea29f9ba65bb101991293a14a6e81aed6202f77` | conforme al digest RPM; include system-auth |
| `/etc/pam.d/sudo-i` | `268616ef041372c9cdc170df1b4deea85cbf67928b17451759bfd24ac689b803` | conforme al digest RPM; include sudo |
| `/etc/pam.d/goodix-d285-01-sudo` | `dd853208220902d1737357a02e47a6c1ac47e5ddf56bf02247efda52e17f2048` | max-tries=3 timeout=45, fallback pam_unix; diverso dal limite originale D285 a uno; pin state da verificare |
| `/etc/authselect/system-auth` | `2e53f704372b6c7fb69cdc4dfd6c27456d642c83feff8b1588fa1f9cb1126cd0` | password baseline già attiva |
| `/etc/authselect/fingerprint-auth` | `9e0ea3820ffe5b6ff6f4cea4896b40e244077830538ea824911759095f8b4a8a` | fingerprint globale disabilitato |
| `/usr/lib/pam.d/plasmalogin` | `559910be8631f69398332b2979bd5c18f1155a7af0960215d175694082cae2ac` | modifica storica D290; RPM atteso `c6fc4a0bc2d89f88fa15ca7e9a6c5aaeccfbe66897755b5416ce9c5e35b4e40b` |
| `/etc/pam.d/plasmalogin` | `91a632300cde2e9bd351625a49558cb0531a035338221039d3a01e671ad9cbcc` | override early con max-tries=3 timeout=8 debug |
| `/etc/pam.d/kde-fingerprint` | `858713e5b3b7ecf58a91f6fe5b736f344aa6c5b9c207318e6ac552a1a3ffb3d1` | delta D297; RPM atteso `8b3181ce5979f498e2cd07acaf3f57c63b1e2f9593e44bfa9027b6dd8bb62437` |
| `/usr/lib/pam.d/polkit-1` | `a4454c54582a86fd4560321b22ffb7639485968438a07d5412fadc102d62cf49` | vendor; override `/etc` assente |
| hook B5 `50-goodix-fprint-account-delete` | `42024daf2f33372014d5a1f45059aeb49a8be4b78198899e9cb9b331a813af10` | 0755 root:root, state/policy da correlare |

Pacchetti proprietari: plasma-login-manager e plasma-workspace
6.7.5-1.fc44. Il nome RPM `plasmalogin` non è il package installato.
PAM 1.7.2-2.fc44, authselect 1.7.1-1.fc44, polkit 127-2.fc44.2,
polkit-kde e kscreenlocker 6.7.5-1.fc44, shadow-utils 4.19.0-7.fc44,
selinux-policy-targeted **44.9-1.fc44** (diverso dalla policy 44.8 studiata in B5).

Runtime early: digest indice SHA256SUMS
`c82c0440692dcca4d5ef7b87f19f6ee744f6775a3b83b7ef501fa06d53f695f5`;
driver `39b70e0ba3da385b7921671543295f8166e27ffde5e990cf1cee94ee0aee081f`,
daemon `56adcc05718e12dd393d732b6e0af369b85044e3cf19e4209ca631d7cae5e353`,
PAM `d746f2cdace223a42ae988207f306bd734a78d3e9a99c9071a8b58c087039372`.
Sono digest osservati, non una nuova verifica completa dei manifest runtime.
Gli indici artifacts.sha256 D293 e D297 sono 0600 root-only; il D285 è leggibile.

## Gate e rischi dei rollback storici

Il codice D285 corrente in
`development/private-root/operator_kit/d285-01-persistent-sudo/run-d285-01.sh`
controlla un unico template ownership-pinned, enumera il target, avvia fprintd,
chiama fprintd-delete, poi riabilita `with-fingerprint` e rimuove runtime/state.
Questa non è una migrazione template-preserving. Non va eseguito né aggirato.

D293, recuperabile con `git show e61fce313794922a2dab156a1b38a8ddc5837f19:deployment/d293-native-kde-live/install.sh`,
richiede pin degli oggetti D285 e ripristina la vecchia snapshot systemd:
la presenza del 96 cambia quel boundary. B5, dal commit
`ef302008c85adfecde14433dd486187d2ad9d3f8`, possiede hook e modulo SELinux;
la candidate usa gli stessi nomi, quindi serve una transizione di ownership.
Lo stesso commit conserva `deployment/d297-02-local-live/install.sh`:
il suo uninstall presuppone lo stato/drop-in D297 attivo, oggi non dimostrato.
Il kit KScreenLocker salva vendor/managed e li hash-pinna. Login-three ripristina
otto oggetti early, incluso lo state; early rimuove l'override PAM `/etc` ma
**non corregge la modifica D290 del PAM vendor `/usr/lib`**.

Il manager corrente rifiuta sia il PAM vendor contenente pam_fprintd sia i
drop-in storici, il PAM KScreenLocker custom e i selettori sudo custom. Non sono
stati modificati i preflight. La baseline candidata richiederà password-only
authselect, vendor Plasma conforme, ownership B5/KScreenLocker risolta e
selettore D285 rimosso solo al passaggio controllato. La scelta fra rimozione
selettiva, rollback parziali o migration tool **resta pendente**: questi fatti
non autorizzano una strategia deterministica senza gli stati mancanti.

`/var/lib/fprint`, `/var/lib/goodix-5125-poc`, `/var/lib/goodix-5125-staging` e
state KScreenLocker sono 0700 root:root. Non si deducono presenza, numero,
validità o ownership dei template dalla dimensione delle directory. Nessun
contenuto o digest biometrico/materiale è stato letto. La compatibilità tra
loader storico e materiali canonici deve ancora essere risolta, senza import,
overwrite o esportazione dei materiali. Nessuna garanzia di rollback esatto
può essere dichiarata prima di tale ricostruzione.

## Closure di questo gate

```text
OUTCOME=HUMAN_REQUIRED
GATE=PRIVILEGED_READ_ONLY_INVENTORY
HOST_INVENTORY=PRIVILEGED_READ_REQUIRED
PRIVILEGED_READ_REQUIRED=true
OVERLAY_ORDER=CONFIGURED_PRECEDENCE_PROVEN_FULL_STATE_PENDING
D285_STATUS=USER_SUDO_PASS_PRESERVED_SELECTOR_STATE_PENDING
D293_STATUS=SUPERSEDED_BUT_PRESENT
LOGIN_EARLY_STATUS=SELECTED_WITH_THREE_ATTEMPT_DELTA
AUTHSELECT_CURRENT=local_with-silent-lastlog_with-mdns4
TARGET_BASELINE=PASSWORD_ONLY_AUTHSELECT_GOODIX_DATA_PRESERVED_NOT_YET_QUALIFIED
TEMPLATE_PRESERVATION=UNTOUCHED_NO_CONTENT_READ_MIGRATION_PROOF_PENDING
PROTECTED_MATERIAL_PRESERVATION=UNTOUCHED_METADATA_ONLY_MIGRATION_PROOF_PENDING
MIGRATION_STRATEGY=PENDING_PRIVILEGED_INVENTORY
MIGRATION_TOOL=NOT_PREPARED_CASE_A
ROLLBACK=NOT_PREPARED_CASE_A_HISTORICAL_UNINSTALL_NOT_APPROVED
CANDIDATE_SOURCE_COMMIT=9e47bdc77246322d6fafee18dd278a066dd583ef
CANDIDATE_PREFLIGHT_POST_MIGRATION=NOT_RUN_BASELINE_UNRESOLVED
CANDIDATE_REPRODUCTION=PREVIOUSLY_PROVEN_NOT_REPEATED_AT_INVENTORY_GATE
OFFLINE_TESTS=8_SYNTHETIC_INVENTORY_TESTS_PASS_AND_DIFF_CHECK
EXECUTABLE_CLOSURE=INVENTORY_OFFLINE_VERIFIED_ROOT_EXECUTION_PENDING
HOST_CHANGED=false
POLKIT_PATCH_INSTALLED=false
REAL_SENSOR_ACCESS=false
NEXT_OPERATOR_ACTION=RUN_SINGLE_READ_ONLY_INVENTORY_FROM_EXISTING_ROOT_SHELL
```

Candidate build normal/sanitizer, Polkit/sudo/private-bus/managed suites,
migration failure injection e candidate install/uninstall post-migrazione
**non sono rieseguiti** in questo gate: i sorgenti production non cambiano,
apply/recovery non esistono ancora e la baseline post-migrazione non è stabilita.
Le prove precedenti restano quelle del manuale, non diventano nuove prove di
migrazione. Il prompt richiede esplicitamente lo stop in caso A.

Review Git-native: baseline indicata, commit che introduce questa directory,
script/test/README, questa review e aggiornamento del manuale. Nessun dato host
privato entra nella candidate, nessuna pubblicazione o nuovo D-number.
