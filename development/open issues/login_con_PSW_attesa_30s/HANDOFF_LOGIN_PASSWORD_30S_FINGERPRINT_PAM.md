# Handoff tecnico — latenza ~30 s al login con password per utenti con fingerprint

## Scopo

Questo documento riassume in modo autosufficiente l'indagine svolta sulla **latenza di circa 30 secondi al login grafico KDE/Plasma quando un utente che ha impronte registrate sceglie di autenticarsi con password invece che con fingerprint**.

È pensato come handoff per una futura riapertura dell'attività, con l'obiettivo di poter riprendere l'analisi senza dipendere dal contesto della chat originale.

---

# 1. Problem statement

Sul target reale Fedora 44 KDE del progetto Goodix `27c6:5125`, dopo l'abilitazione del login via fingerprint è stato osservato che:

- il login iniziale via **fingerprint** funziona normalmente;
- il login iniziale via **password** continua a funzionare;
- tuttavia, **se l'utente ha almeno un'impronta registrata e sceglie la password**, l'accesso al desktop risulta sensibilmente più lento;
- il ritardo percepito è dell'ordine di **~30 secondi**.

Il comportamento non è stato osservato sugli account che **non hanno impronte registrate**: per questi, il login password rimane immediato.

Domanda originaria:

> l'extra timing è causato dal driver Goodix, da `fprintd`, da PAM, da Plasma Login Manager, da KWallet oppure dalla fase di startup del desktop?

---

# 2. Stato funzionale già noto

Al momento dell'indagine:

```text
FINGERPRINT LOGIN = funzionante
PASSWORD LOGIN = funzionante
LOGIN SCREEN = Plasma Login Manager
SESSION TYPE = Wayland / KDE Plasma
```

L'utente riusciva normalmente a:

```text
boot/reboot
→ schermata login iniziale
→ selezione utente / INVIO
→ fingerprint
→ accesso al desktop
```

La latenza anomala compariva invece usando la password.

---

# 3. Prime ipotesi considerate

Sono state considerate principalmente queste piste.

## 3.1 PAM / `pam_fprintd`

Ipotesi:

```text
pam_fprintd viene tentato prima della password
→ aspetta il timeout fingerprint
→ solo dopo passa a pam_unix
```

Questa era l'ipotesi principale.

## 3.2 KWallet / `ksecretd`

Nel primo `loginctl session-status` erano comparsi:

```text
pam_kwallet5: final socket path: /run/user/1000/kwallet5.socket
Wallet failed to get opened by PAM, error code is -9
```

Poiché il messaggio KWallet compariva alcuni secondi dopo l'apertura della sessione, è stato inizialmente considerato un possibile contributore alla lentezza.

## 3.3 Startup Plasma / KWin

È stata considerata anche la possibilità che l'autenticazione fosse rapida ma che i secondi venissero persi dopo PAM, nella fase:

```text
session opened
→ startplasma-wayland
→ kwin_wayland
→ desktop pronto
```

---

# 4. Raccolta log eseguita

Per isolare il punto esatto della latenza sono stati usati log con timestamp monotonic.

Comandi usati:

```bash
loginctl session-status --no-pager

sudo journalctl -b -u fprintd \
  --since "2026-09-13 23:29:30" \
  --until "2026-09-13 23:31:00" \
  -o short-monotonic \
  --no-pager

sudo journalctl -b \
  --since "2026-09-13 23:29:30" \
  --until "2026-09-13 23:31:00" \
  -o short-monotonic \
  --no-pager \
  | grep -Ei 'plasmalogin|pam_fprintd|pam_unix|pam_kwallet|ksecretd|fprintd|authentication|session opened|session closed|logind|startplasma|kwin_wayland'
```

Il login analizzato era stato effettuato **con password**.

---

# 5. Evidenza temporale decisiva

Il journal ha mostrato:

```text
[36.036620] pam_fprintd(plasmalogin:auth): Waiting for 30 seconds
[36.036733] pam_fprintd(plasmalogin:auth): Waiting for 30 seconds

[41.622326] pam_fprintd(...): Waiting for 24 seconds
[46.054179] pam_fprintd(...): Waiting for 20 seconds

...

[66.438223] plasmalogin: "Verification timed out"

[66.503434] PAM:authentication grantors=pam_unix acct="guido" ... res=success

[66.518883] systemd-logind: New session '2' of user 'guido'
```

La finestra critica è quindi:

```text
36.036 s → 66.438 s ≈ 30.40 s
```

Subito dopo il timeout fingerprint:

```text
66.503 s → pam_unix PASSWORD SUCCESS
66.519 s → sessione aperta
```

Il ritardo aggiuntivo tra password accettata e sessione logind è quindi di pochi millisecondi.

---

# 6. Conclusione principale dell'indagine

La latenza di circa 30 secondi è stata **confermata oggettivamente** e attribuita all'ordine seriale della stack PAM usata da Plasma Login Manager.

Il flusso reale osservato è:

```text
utente preme INVIO
→ pam_fprintd parte
→ attesa fingerprint
→ timeout ~30 s
→ password-auth / pam_unix
→ password SUCCESS
→ sessione grafica
```

Quindi:

```text
ROOT_CAUSE = PAM serial order
pam_fprintd viene tentato prima di password-auth
```

Non è stata trovata evidenza che il driver Goodix sia responsabile dei 30 secondi.

---

# 7. Evidenza lato Goodix / fprintd

Nella stessa finestra è comparso:

```text
GOODIX_PRODUCTION_EPOCH_AUDIT
action=FPI_DEVICE_ACTION_VERIFY
attempts=1
rejected=0
logical_actions=1
transport_epochs=1
tls=1
persistent=0
```

Questo è importante perché mostra che:

- il percorso fingerprint viene effettivamente attivato;
- non risultano retry incontrollati;
- non risultano scritture persistenti;
- il driver non sta eseguendo una catena di tentativi che spieghi i ~30 s.

La latenza deriva dal fatto che la conversazione PAM resta in attesa del completamento/timeout di `pam_fprintd`.

---

# 8. KWallet: pista investigata ma non causa primaria

Dopo la riuscita autenticazione PAM:

```text
[66.725783] Starting Wayland user session
[70.183122] Starting plasma-kwin_wayland.service
[70.198722] Started plasma-kwin_wayland.service
[70.996359] ksecretd: Wallet failed to get opened by PAM, error code is -9
```

Quindi KWallet produce un problema reale separato, ma:

```text
pam_fprintd timeout ≈ 30.4 s
startup session / Plasma ≈ 4 s
```

Il messaggio KWallet arriva **dopo** che PAM e logind hanno già aperto la sessione.

Conclusione:

```text
KWALLET = problema secondario / separato
NON = causa principale della latenza di 30 s
```

Se l'attività verrà riaperta, KWallet può essere analizzato separatamente, ma non deve essere confuso con il problema in oggetto.

---

# 9. Individuazione della stack PAM reale

Inizialmente era stato cercato:

```text
/etc/pam.d/plasmalogin
```

ma il file non esisteva.

Il file effettivamente usato è risultato:

```text
/usr/lib/pam.d/plasmalogin
```

Contenuto rilevante:

```text
auth [success=done ignore=ignore default=bad] pam_selinux_permit.so
auth sufficient /usr/lib64/security/pam_fprintd.so max-tries=3 timeout=45 debug
auth substack   password-auth
-auth optional  pam_gnome_keyring.so
-auth optional  pam_kwallet5.so
-auth optional  pam_kwallet.so
-auth optional  pam_oo7.so
auth include    postlogin
```

Le due righe decisive sono:

```text
auth sufficient /usr/lib64/security/pam_fprintd.so max-tries=3 timeout=45 debug
auth substack   password-auth
```

Quindi `pam_fprintd` precede esplicitamente `password-auth`.

Questo è coerente con il comportamento osservato nel journal.

---

# 10. Proprietà e stato del file PAM

È stato eseguito:

```bash
rpm -qf /usr/lib/pam.d/plasmalogin
```

Risultato:

```text
plasma-login-manager-6.7.5-1.fc44.x86_64
```

È stato poi eseguito:

```bash
rpm -V plasma-login-manager
```

Risultato rilevante:

```text
S.5....T. /usr/lib/pam.d/plasmalogin
```

Interpretazione:

```text
S = dimensione diversa dal file RPM
5 = checksum diverso
T = timestamp diverso
```

Quindi il file PAM vendor risulta **modificato localmente rispetto al pacchetto installato**.

Importante:

- è molto plausibile che la modifica sia collegata all'abilitazione del fingerprint login;
- durante questa indagine **non è stata formalmente ricostruita la provenance esatta della modifica**;
- non va quindi attribuita automaticamente a uno specifico Dxxx senza verifica Git/manuale.

Una futura riapertura dovrebbe ricostruire questo punto.

---

# 11. Anomalia residua: `timeout=45` ma attesa reale ~30 s

La configurazione mostra:

```text
pam_fprintd.so max-tries=3 timeout=45 debug
```

ma il journal osservato mostra:

```text
Waiting for 30 seconds
...
Verification timed out
```

con durata reale di circa 30.4 s.

Questa discrepanza **non è stata risolta**.

Possibili spiegazioni da studiare in futuro:

- Plasma Login Manager potrebbe imporre un timeout di conversazione più corto;
- `pam_fprintd`/fprintd potrebbe avere un limite effettivo differente;
- la build Fedora può avere comportamento proprio;
- potrebbe esistere un timeout superiore nello strato chiamante.

Questa anomalia è secondaria rispetto alla root cause, ma è un ottimo punto diagnostico per una futura riapertura.

---

# 12. Test comparativo utenti con / senza impronte

È stata posta la domanda:

> il ritardo colpisce solo utenti con fingerprint registrato o anche utenti password-only?

Test empirico eseguito dall'Utente:

```text
utente SENZA impronte registrate
→ password
→ nessuna attesa anomala
→ login immediato
```

Conferma:

```text
PASSWORD_LOGIN_NON_ENROLLED_USERS = PASS_NO_DELAY
```

Per utenti con impronte registrate:

```text
PASSWORD_LOGIN_ENROLLED_USERS = PASS_WITH_APPROX_30S_DELAY
```

Questo è un risultato fondamentale.

---

# 13. Interpretazione funzionale finale

Lo stato emerso è:

```text
FINGERPRINT_LOGIN=PASS

PASSWORD_LOGIN_NON_ENROLLED_USERS=PASS_NO_DELAY

PASSWORD_FALLBACK_ENROLLED_USERS=PASS_WITH_APPROX_30S_DELAY

ROOT_CAUSE=PAM_SERIAL_ORDER_PAM_FPRINTD_BEFORE_PASSWORD_AUTH

GOODIX_DRIVER_REGRESSION=false

SEVERITY=UX_LIMITATION

PHASE_B_BLOCKER=false
```

La decisione presa in chat è stata di **non aprire subito un corrective PAM**, perché:

- l'extra timing interessa solo gli utenti che hanno scelto di configurare il fingerprint;
- il percorso normale per tali utenti è presumibilmente il fingerprint;
- gli utenti senza fingerprint mantengono login password immediato;
- la password resta comunque disponibile come fallback;
- il comportamento è stato accettato come limite UX, non come regressione funzionale bloccante.

---

# 14. Cosa NON è stato fatto

Durante questa indagine non sono state applicate modifiche correttive alla stack PAM.

Non sono stati:

- riordinati i moduli PAM;
- modificati `password-auth` o `system-auth`;
- cambiati i timeout;
- rimossi `pam_fprintd` o fingerprint login;
- applicati override sotto `/etc/pam.d/`;
- testate configurazioni password-first;
- modificati authselect/profile;
- modificati driver o fprintd.

La sessione si è fermata alla diagnosi e alla classificazione del comportamento.

---

# 15. Rischi da evitare alla riapertura

Se l'attività verrà ripresa, evitare modifiche manuali improvvisate a:

```text
/etc/pam.d/system-auth
/etc/pam.d/password-auth
```

perché risultavano gestiti da `authselect`:

```text
# Generated by authselect
# Do not modify this file manually
```

Evitare inoltre di assumere che modificare direttamente:

```text
/usr/lib/pam.d/plasmalogin
```

sia il meccanismo definitivo corretto: è un file package-owned ed è già risultato modificato rispetto all'RPM.

Prima di qualunque modifica va ricostruita la provenance e definito un percorso reversibile.

---

# 16. Punti aperti per una futura riapertura

## 16.1 Provenance del PAM modificato

Ricostruire:

```text
chi / quale Dxxx / quale installer
ha modificato /usr/lib/pam.d/plasmalogin
```

Confrontare:

- history Git;
- manuale tecnico;
- deployment/install script;
- backup o baseline precedenti;
- contenuto originale del pacchetto.

## 16.2 Perché `timeout=45` produce ~30 s

Determinare quale componente tronca la finestra a ~30 s.

## 16.3 Possibile comportamento desiderato

Idealmente ottenere:

```text
fingerprint → login rapido
password    → login rapido
```

senza perdere:

- compatibilità PAM Fedora;
- `pam_faillock` / policy password;
- KWallet/session semantics;
- fingerprint login;
- fallback password;
- integrazione authselect;
- rollback pulito.

## 16.4 Strategie da valutare, NON ancora validate

Possibili linee di studio:

1. capire se Plasma Login Manager supporta un'autenticazione fingerprint separata/non bloccante;
2. verificare se il login manager può interrompere `pam_fprintd` appena l'utente immette una password;
3. valutare una stack password-first compatibile con il comportamento UI desiderato;
4. valutare un override PAM supportato sotto `/etc/pam.d/`, anziché modificare direttamente il file vendor;
5. verificare se esiste una configurazione upstream/Fedora/KDE raccomandata per password + fingerprint senza attesa seriale.

Nessuna di queste strategie è stata provata nel target durante questa indagine.

---

# 17. Procedura consigliata per riaprire l'attività

Prima di modificare qualcosa:

```bash
# 1. Fotografare lo stato reale
rpm -q plasma-login-manager fprintd pam
rpm -V plasma-login-manager

# 2. Leggere la stack reale
cat /usr/lib/pam.d/plasmalogin
grep -Rns 'pam_fprintd' /etc/pam.d /usr/lib/pam.d 2>/dev/null

# 3. Ricostruire authselect senza modificare
authselect current

# 4. Cercare nel repository la provenance della modifica PAM
# Cercare "plasmalogin", "pam_fprintd", "timeout=45" negli installer e nella history.

# 5. Acquisire un nuovo baseline login con password
journalctl -b -o short-monotonic
```

---

# 18. Acceptance criteria di un eventuale corrective futuro

Un corrective potrà essere considerato riuscito solo se dimostra sul target reale:

```text
1. fingerprint login continua a funzionare;
2. password login per utenti con fingerprint non aspetta ~30 s;
3. password login per utenti senza fingerprint resta immediato;
4. fallback password resta disponibile;
5. nessuna regressione sudo / lockscreen / polkit pertinente;
6. nessuna regressione KWallet/sessione introdotta dal cambiamento;
7. nessuna modifica diretta non gestita a file authselect;
8. installazione e rollback sono reversibili;
9. la soluzione sopravvive correttamente agli aggiornamenti package secondo il meccanismo scelto.
```

---

# 19. Timeline sintetica della diagnosi

```text
Problema percepito:
password login più lento dopo abilitazione fingerprint

↓
Ipotesi PAM/fprintd vs KWallet vs startup Plasma

↓
journal monotonic

↓
pam_fprintd attende ~30.4 s

↓
"Verification timed out"

↓
pam_unix accetta subito la password

↓
sessione aperta ~15 ms dopo

↓
KWallet fallisce ~4 s dopo, quindi problema secondario

↓
stack reale trovata in /usr/lib/pam.d/plasmalogin

↓
pam_fprintd precede password-auth

↓
rpm -V mostra plasmalogin PAM modificato rispetto al pacchetto

↓
test account senza fingerprint: nessun ritardo

↓
classificazione finale:
accepted UX limitation / non blocker
```

---

# 20. Stato handoff finale

```text
PROBLEM_REPRODUCED=true

EXTRA_DELAY≈30s

AFFECTED_USERS=accounts_with_enrolled_fingerprints

UNAFFECTED_USERS=accounts_without_enrolled_fingerprints

ROOT_CAUSE_CONFIDENCE=high

ROOT_CAUSE=PAM_SERIAL_ORDER_PAM_FPRINTD_BEFORE_PASSWORD_AUTH

GOODIX_DRIVER_INVOLVEMENT=not_root_cause

KWALLET=secondary_separate_issue

PAM_VENDOR_FILE=/usr/lib/pam.d/plasmalogin

PAM_VENDOR_FILE_MODIFIED_VS_RPM=true

CONFIGURED_PAM_FPRINTD_TIMEOUT=45s

OBSERVED_EFFECTIVE_WAIT≈30.4s

WHY_45_BECOMES_30=unresolved

CORRECTIVE_IMPLEMENTED=false

CURRENT_DECISION=accepted_UX_limitation

PHASE_B_BLOCKER=false
```

---

## Nota finale per la futura riapertura

Il problema è **diagnosticato ma non risolto**.

La parte più importante da preservare è questa:

> non serve più dimostrare che il ritardo esiste né dove nasce: il journal ha già mostrato che `pam_fprintd` blocca la stack PAM prima di `password-auth` per circa 30 secondi sugli utenti con fingerprint registrato.

La prossima attività, se riaperta, dovrebbe quindi partire direttamente da:

```text
PROVENANCE DELLA MODIFICA PAM
+
STUDIO DELLA MIGLIORE ORCHESTRAZIONE PASSWORD/FINGERPRINT
+
CORRECTIVE REVERSIBILE
```

senza ripetere da zero la diagnosi già conclusa.
