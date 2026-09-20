# Polkit/Discover — audit host e decisione PM

Data: 20 settembre 2026. Task: `AI_PM_POLKIT_FINGERPRINT_DISCOVER.md`.
Baseline: `development`, `59167be30742ae270a91502cf094d55aa5fe978d`, pulita.
Questo è il risultato della diagnosi, non una patch pronta da installare.
Lo stato narrativo canonico è nel manuale tecnico, sezione Polkit/Discover.

## Esito

```text
OUTCOME=HUMAN_REQUIRED
ROOT_CAUSE=POLKIT_SYSTEM_AUTH_WITHOUT_PAM_FPRINTD
EVIDENCE=VENDOR_POLKIT_INCLUDE_AND_CURRENT_AUTHSELECT_CONTENT
REAL_TARGET_COMPATIBILITY=BLOCKED_HUMAN_REQUIRED
HOST_PATCH=NOT_PREPARED_PASSWORD_AND_RETRY_REQUIREMENTS_UNSATISFIED
CANDIDATE_CHANGE=SUPPORT_BOUNDARY_DOCUMENTATION_ONLY
PASSWORD_FALLBACK_BEHAVIOR=UNCHANGED_NO_HOST_WRITE
PASSWORD_FALLBACK_REGRESSION=EXPLICITLY_BLOCKED_BEFORE_IMPLEMENTATION
OFFLINE_TESTS=26_EXISTING_MANAGED_LIFECYCLE_TESTS_PASS
LIVE_TEST=HUMAN_REQUIRED
ROLLBACK=NOT_APPLICABLE_NO_HOST_CHANGE
RESIDUAL_RISK=PASSWORD_SERIALIZATION_AND_OUTER_CONVERSATION_RETRIES
EXECUTABLE_CLOSURE=NOT_APPLICABLE_DOCUMENTATION_ONLY
```

Il gate è quello esplicito della sezione B del prompt: se il percorso PAM
disponibile non concilia fingerprint e password immediata, fermare la review
prima di implementare un compromesso. Le sezioni C–E sono condizionate a una
soluzione accettabile; produrre adesso apply/rollback sarebbe distribuire una
candidate già incompatibile con i criteri di accettazione. Il gate non è una
richiesta di eseguire privilegi o biometria per confermare un difetto di codice.

## Evidenza corrente, ottenuta senza autenticazione

Pacchetti installati:

| Pacchetto | NEVRA |
| --- | --- |
| polkit | `polkit-127-2.fc44.2.x86_64` |
| polkit-kde | `polkit-kde-6.7.5-1.fc44.x86_64` |
| fprintd | `fprintd-1.94.5-5.fc44.x86_64` |
| fprintd-pam | `fprintd-pam-1.94.5-5.fc44.x86_64` |
| plasma-workspace | `plasma-workspace-6.7.5-1.fc44.x86_64` |
| authselect | `authselect-1.7.1-1.fc44.x86_64` |

`/usr/lib/pam.d/polkit-1`, posseduto da polkit, è `root:root:0644`, 155 byte,
SHA-256 `a4454c54582a86fd4560321b22ffb7639485968438a07d5412fadc102d62cf49`,
uguale al digest nel database RPM. Contenuto osservato:

```text
#%PAM-1.0

auth       include      system-auth
account    include      system-auth
password   include      system-auth
session    include      system-auth
```

`/etc/pam.d/polkit-1` è assente; non risultano omonimi `.rpmnew/.rpmsave`
nelle directory PAM ispezionate. Authselect riporta profilo `local` e feature
`with-silent-lastlog`, `with-mdns4`. Le symlink system-auth/fingerprint-auth
puntano ai rispettivi file in `/etc/authselect`. La sezione auth di system-auth
contiene, in ordine: pam_env required, pam_faildelay required con 2000000 µs,
pam_unix sufficient nullok, pam_deny required. Fingerprint-auth contiene solo
`auth required pam_debug.so auth=authinfo_unavail`.

L'agente `plasma-polkit-agent.service` e `polkit.service` sono attivi;
`polkit-agent-helper.socket` è inattivo al momento del controllo. L'helper
package-owned conserva mode RPM 04755; il sorgente della sessione Polkit 127
prevede il fallback al processo helper quando il socket non è disponibile.
Il binario locale contiene chiamate in sequenza a pam_start, pam_authenticate,
pam_acct_mgmt. L'unit helper contiene isolamento dei device, ma il PAM parla
con fprintd via D-Bus: quell'isolamento non dimostra un blocco USB di fprintd.

`rpm -V polkit polkit-kde fprintd-pam plasma-workspace`, ripetuto fuori dal
sandbox come normale utente, segnala soltanto
`S.5....T. c /etc/pam.d/kde-fingerprint`. Il file coincide con la configurazione
del correttivo storico: modulo Fedora, tre tentativi, timeout 45. I falsi
scostamenti owner/group del primo controllo sono dovuti alla rimappatura UID/GID
del sandbox e non sono classificati come drift host. Nel journal incluso nello
status dell'agente compaiono errori di registrazione al portale; non provano
la causa del fingerprint assente, poiché il PAM non lo invoca già in origine.

Sono configurati i drop-in fprintd `90` D285, `95` D293 e `96` login-early;
l'ultimo seleziona `/usr/local/sbin/goodix-login-early-fprintd`. Il PAM login
locale usa `/usr/local/lib64/goodix-27c6-5125/login-early/pam_fprintd.so`
con `max-tries=3 timeout=8 debug`. È una fotografia dei file, non una nuova
validazione live. State e directory runtime managed sono assenti: installare
una candidate managed sul PC non è un correttivo Polkit appropriato.

## Classificazione delle cause richieste

| Ipotesi | Valutazione |
| --- | --- |
| 1. Polkit salta lo stack fingerprint | Confermata: include system-auth; non include kde-fingerprint né il servizio sudo storico. |
| 2. System-auth non abilita fingerprint | Confermata dal contenuto e da authselect current. Causa sufficiente del comportamento descritto. |
| 3. Sudo usa un percorso specifico | Esiste `/etc/pam.d/goodix-d285-01-sudo`, con pam_fprintd Fedora, max-tries=3, timeout=45 e password fallback. Il selettore sudoers è illeggibile al normale utente: selezione effettiva corrente non verificata. `/etc/pam.d/sudo` ordinario è password-only tramite system-auth. I PASS storici restano validi nel loro contesto. |
| 4. Override Polkit/drift package | Esclusa per i file osservati: override assente, vendor e package Polkit verificati. |
| 5. Integrazione managed mancante | Confermata: candidate/manifest/state/transazioni gestiscono login e KScreenLocker, nessun polkit-1. Il PC non usa quel deployment. |
| 6. Helper 127 blocca un PAM già corretto | Non è la causa iniziale: manca il ramo fingerprint. La serializzazione dell'helper rende invece rischiosa la modifica proposta. |
| 7. Agente KDE | Nessuna prova di blocker iniziale; è attivo. Il codice upstream della versione installata inoltra la password alla stessa sessione e può riavviarla dopo fallimento. |
| 8. Ownership/daemon/Goodix nel contesto Polkit | Non testata e non necessaria per spiegare il sintomo iniziale. Diventa un confine di accettazione solo dopo una soluzione UX e retry corretta. |

## Valutazione dei moduli e del lifecycle

`/usr/lib64/security/pam_fprintd.so` è posseduto da fprintd-pam, verificato RPM,
SHA-256 `96e47e1514a7c6c4fc722fa086bc25bb1c4d44774421c3d2970c7fc2b4385ebd`.
Usa l'API ordinaria Claim/VerifyStart del daemon selezionato dal servizio D-Bus
globale. Il percorso KScreenLocker locale lo usa già: per una futura regola
Polkit con API ordinaria non è necessario ClaimLogin.

La patch canonica `production/login/fprintd.patch` sceglie ClaimLogin solo
quando PAM_SERVICE è plasmalogin; per polkit-1 il modulo paired usa ancora
Claim. `fprintd-attempts.patch` limita il contesto prepared-login, non tutte le
sessioni Polkit. Nessuno dei due moduli interrompe l'attesa fingerprint quando
arriva una password. Il path `/usr/lib64/goodix-27c6-5125/current/pam_fprintd.so`
non esiste sul PC. Sceglierlo ora romperebbe la patch locale.

Il gestore mantiene runtime immutabili e un link current per lo switch
coordinato; salva stato/digest PAM e ripristina login/KScreenLocker nel rollback,
incluse failure parziali. Le regole esistenti sono stabili fra update compatibili.
Un futuro Polkit richiederebbe stato corrente e precedente dedicati, override
derivato dal vendor verificato, collision/drift check, ripristino dell'assenza
originale, metadata e SELinux corretti. Nessun cambiamento di ABI, file-context
o policy è stato implementato o qualificato. Se la soluzione richiedesse un
PAM modificato, pairing e rollback di quel binario andrebbero rivalutati:
la scelta attuale del modulo Fedora non prova compatibilità con tale delta.

## Perché non consegnare una semplice regola PAM

Il reference Fedora fprintd 1.94.5, verificato dalla provenance locale, esegue
do_verify aspettando il bus e SIGINT. Non osserva lo stdin dell'helper o un
evento di password inviata. Il timeout è per tentativo; su timeout la funzione
termina, su NO MATCH può avviare il tentativo successivo. Claim/cleanup possono
aggiungere tempo: `timeout=8` non è una garanzia di fallback entro otto secondi.

| Opzione | Conseguenza nota / limite |
| --- | --- |
| Fingerprint prima di system-auth | Abilita il ramo, ma la password resta dietro fingerprint/esito/timeout. Viola il vincolo B. |
| Ridurre timeout a 1–8 s | Riduce una finestra di attesa e quella disponibile al dito, senza offrire cambio immediato. Affidabilità e tempi totali sul target non misurati. |
| Fingerprint dopo system-auth invariato | Una password valida termina con successo prima dell'impronta; una fallita incontra pam_deny required. Il successivo sufficient non elimina quel fallimento. |
| Password-first con nuovo control flow e Invio vuoto | Richiede un'interazione diversa, audit degli errori e dei retry; non dà password immediata dopo un NO MATCH mentre fingerprint attende ancora. Non pronta. |
| Abilitare with-fingerprint globalmente | Allarga i consumer e riproduce il problema seriale. Nessuna necessità tecnica emersa. |
| Modificare conversazione/cancellazione | È la direzione da studiare se entrambi i metodi devono restare prontamente utilizzabili. Richiede nuova review di cleanup, password handling e limite globale; non basta cambiare ordine PAM. |

Polkit issue #650 descrive circa dieci secondi su Ubuntu con Polkit 127:
corrobora il rischio, non misura il target Fedora. Il codice KDE `v6.7.5`
consente tre conversazioni complessive, con due riavvii tramite tryAgain
dopo fallimenti non cancellati.
Una regola `max-tries=3` limita ogni singola conversazione: il percorso
combinato può consentire nuove serie se fallisce anche la password. Non è
dimostrato un limite globale di tre contatti, né è stata osservata una serie
di nove sul sensore. Una sola istruzione operatore non risolverebbe il guardrail.

## Decisione richiesta prima del passo successivo

1. Mantenere i requisiti: studiare un correttivo circoscritto della conversazione
   PAM/Polkit, inclusi interruzione su password e budget del dialogo, senza
   implementare nuove azioni hardware. È la direzione consigliata; non implica
   già la scelta di un agente alternativo o di pacchetti KDE modificati.
2. Accettare esplicitamente un workflow sequenziale: definire il compromesso UX
   ammesso prima della patch. Restano obbligatori tre tentativi complessivi,
   stop al MATCH, cancellazione e rollback. Un timeout breve da solo non basta.
3. Conservare Polkit password-only e lasciare questo supporto sospeso.

Dopo la decisione, una soluzione accettabile deve avere patch locale minima e
rollback, integrazione candidate simmetrica e test delle transazioni richiesti
dal prompt. Solo allora: HUMAN_REQUIRED per installazione dell'Utente e
accettazione Discover (fingerprint, password, NO MATCH poi password, cancel)
più regressioni sudo/unlock/login. Nessuna live aggiuntiva è richiesta adesso.

## Verifiche e provenance

Eseguiti read-only: query dei sei pacchetti, authselect current, lettura dei PAM,
status/cat dell'agente, stato Polkit/socket, verifica RPM, digest/metadata e
ispezione statica dell'helper. Nessun sudo/pkexec/Discover/fprintd-verify,
accesso USB, dato biometrico o materiale protetto. Sudoers non è stato forzato.

Eseguito `python3 deployment/managed-install/test_offline.py`: **26/26 PASS**,
root sintetiche temporanee e azioni host simulate. Copre il lifecycle esistente,
non una trasformazione Polkit, la sua UI o nuove regressioni live. Nessun nuovo
test/harness o build runtime: il delta è solo documentale.

Fonti lette, senza copiarne codice nel progetto:

- [pam_fprintd: limitazioni](https://man.archlinux.org/man/pam_fprintd.8.en).
- [Polkit #650](https://github.com/polkit-org/polkit/issues/650), consultata aperta.
- [Helper PAM Polkit 127](https://raw.githubusercontent.com/polkit-org/polkit/127/src/polkitagent/polkitagenthelper-pam.c), SHA-256 `477f00755e8153638d3796772f9ebfc3cd9798f5ce09741a0eccba51c2f71f55`.
- [Sessione Polkit 127](https://raw.githubusercontent.com/polkit-org/polkit/127/src/polkitagent/polkitagentsession.c).
- [Listener KDE v6.7.5](https://raw.githubusercontent.com/KDE/polkit-kde-agent-1/v6.7.5/policykitlistener.cpp), SHA-256 `2c10093d6cd8a0e5c1e0a9cf56c91ea4f26074e50ea07bd841ef62e98d495449`.
- [Dialogo KDE v6.7.5](https://raw.githubusercontent.com/KDE/polkit-kde-agent-1/v6.7.5/qml/QuickAuthDialog.qml), SHA-256 `66b84de1b6450e919507b095a0243e49d28a0781d56d8f1b70ec8bf583176874`.
- Reference locale `reference/fprintd-fedora44-1.94.5/PROVENANCE.md`, sorgente PAM
  e patch `production/login/`; documentazione e codice managed-install.

I tag upstream KDE/Polkit sono reference della stessa versione, non prova che
ogni patch di distribuzione sia assente né della cancellazione sul target.
La lettura HTTP iniziale del tag KDE tramite browser non riusciva; il download
non privilegiato del tag esatto in `/tmp` è riuscito. La discussione Fedora
indicata nel prompt non era accessibile e non è usata come prova. Nessun riuso
Rockytkg o modifica del licensing boundary.
