# Polkit/Discover — evidenza e review del correttivo

20 settembre 2026. Diagnosi iniziale consolidata nel commit
`2f34f95563271c5070ec60db6415311d708041b7`. La successiva risposta Utente
`HUMAN_GATE_RESPONSE_POLKIT_REVIEWED.md` sceglie l'opzione 1 e autorizza il
correttivo circoscritto di conversazione. Il precedente gate prima del design
non è più pendente; il gate corrente è prima di installazione e live.
Lo stato narrativo canonico è nel manuale, sezione corrente Polkit/Discover.

## Diagnosi verificata

| Ipotesi | Evidenza e conclusione |
| --- | --- |
| Polkit salta fingerprint | Confermata: vendor polkit-1 include system-auth. Nessun override locale. |
| System-auth senza fingerprint | Confermata: authselect local, with-silent-lastlog e with-mdns4, senza with-fingerprint; auth env/faildelay/unix/deny. È causa sufficiente del sintomo. |
| Sudo specifico | **PASS corrente riferito dall'Utente**; selettore D285 pam_service=goodix-d285-01-sudo e servizio versionato spiegano la catena. La lettura del solo PAM sudo non sostituisce sudoers. Nessun nuovo controllo privilegiato richiesto. |
| Drift Polkit/package | Escluso nei file osservati: vendor e helper corrispondono ai digest RPM, override assente. |
| Integrazione managed mancante | Confermata alla baseline: login/KScreenLocker gestiti, Polkit e sudo specifico assenti. Il PC attuale non è managed. Ora Polkit è candidate-owned; la promessa sudo pulito è corretta come gap aperto. |
| Helper 127 | Non è la causa dell'assenza; la sua PAM seriale rende insufficiente anteporre pam_fprintd. Il bridge ora rende interrompibile l'attesa nel servizio. |
| Agente KDE | Attivo. Sorgente Fedora esatto: tre conversazioni dopo fallimenti, cambio identità può ricreare sessioni senza avanzare il contatore KDE. Serve un limite esterno alla singola conversazione. |
| Driver/ownership nel nuovo consumer | Nessuna nuova live: cleanup lato daemon verificato offline; compatibilità sul sensore e SELinux effettivo restano da osservare. |

Pacchetti: polkit 127-2.fc44.2, polkit-kde/plasma-workspace 6.7.5-1.fc44,
fprintd/fprintd-pam 1.94.5-5.fc44, authselect 1.7.1-1.fc44, PAM 1.7.2-2.fc44.
Polkit e agente KDE attivi, helper.socket inattivo all'ispezione.

| Oggetto osservato | SHA-256 |
| --- | --- |
| Vendor `/usr/lib/pam.d/polkit-1`, root:root 0644, 155 byte | `a4454c54582a86fd4560321b22ffb7639485968438a07d5412fadc102d62cf49` |
| Fedora `/usr/lib64/security/pam_fprintd.so` | `96e47e1514a7c6c4fc722fa086bc25bb1c4d44774421c3d2970c7fc2b4385ebd` |
| Helper Polkit, root:root 04755 | `026972c2853aa610480cdf5957dacdf28d7b07059977282cfee0a5d8deb0605a` |
| System-auth corrente | `2e53f704372b6c7fb69cdc4dfd6c27456d642c83feff8b1588fa1f9cb1126cd0` |
| Fedora KDE source RPM esatto | `2ba0e271420c91623e7ad36c881f70f317f793d99e6ec07301128e556acef616` |

Metadata verificati come normale utente fuori dal sandbox, che rimappa gli UID.
La verifica RPM iniziale segnala solo il noto kde-fingerprint personalizzato.
I drop-in 90/95/96 selezionano il daemon login-early; PAM plasmalogin locale usa
il modulo login-early con max-tries=3 timeout=8 debug; kde-fingerprint usa Fedora
con max-tries=3 timeout=45. Managed state/current assenti.

## Decisione tecnica e nuova ipotesi

Cambiare solo ordine PAM o timeout non rende pronta la password. La modifica
attuale è sostanziale: password iniziale normale, Invio vuoto per una scelta
biometrica, autenticazione fingerprint in un figlio interrompibile e limite
per UID tra conversazioni. Il padre resta disponibile all'input anche durante
Claim/Verify; non aggiunge un nuovo protocollo sensor-reaching. Tre scelte,
stop al primo MATCH, nessun riavvio automatico del figlio. Anche le cancellazioni
consumano una scelta; il reset richiede teardown PAM riuscito.

La nuova ipotesi da osservare live è che il dialogo KDE stock inoltri l'input
nel workflow previsto e che la chiusura della connessione liberi il consumer
senza regressione. Il sorgente e i test offline sostengono questa ipotesi;
non provano ancora la UI o il target. Il vero handler fprintd conferma che
pending Claim viene drenato e chiuso, mentre Verify viene cancellata e chiusa.
Non si afferma che tutta l'attività USB cessi nello stesso istante del cancel.

Se la prova fallisce allo stesso punto, fare rollback e localizzare il failure:
conversazione/UI, diniego SELinux, Claim/owner-loss oppure driver. Richiedere solo
il messaggio e la lettura mirata necessaria; niente ritentativo equivalente con
un timeout diverso. Una modifica a KDE/Polkit o al profilo hardware richiederebbe
nuova evidenza e review del confine, non è parte di questa patch.

## Closure e limiti

- Build completa normale e modulo PAM con RELRO/NOW/stack protection: PASS.
- 18 test libpam normali + 18 ASan/UBSan: PASS; password/fingerprint sintetiche.
- Deadline con figlio bloccato: 45,029 s, un figlio, fallback password PASS.
- 7 test transazione locale e 30 test managed: PASS, comprese failure parziali,
  collisioni, drift, presenza/assenza PAM, pairing update/rollback e contatori.
- Vero daemon su bus privato: PASS pending Claim/idle/Verify owner-loss,
  18 open/18 close sintetiche, nessuna riapertura implicita.
- Hardware, credenziali reali, template e materiale protetto: non utilizzati.

Il sandbox vieta audit NETLINK_AUDIT e invio su socketpair; il runner offline
isola l'audit e la suite completa viene eseguita come normale utente fuori dal
sandbox. Il nuovo modulo production non contiene tali hook. Le librerie
sanitizer corrispondenti a gcc 16.2.1-2.fc44 sono estratte temporaneamente dagli
RPM ufficiali Fedora, mai installate. Leak detection non inclusa nella prova.

Il design, i file posseduti e i vincoli sono in `production/polkit/README.md`.
La patch minima per il PC è `development/patches/polkit-fingerprint/`; il nuovo
lifecycle candidate è in `deployment/managed-install/`. Le versioni managed
pre-Polkit richiedono uninstall originale e fresh install, senza dipendere da
D285. Le regole host rimangono stabili tra versioni compatibili; il binario
Polkit segue il symlink current insieme al runtime, i contatori restano invariati.

```text
OUTCOME=HUMAN_REQUIRED
ADVANCEMENT=INTERRUPTIBLE_PAM_AND_OWNED_POLKIT_LIFECYCLE_IMPLEMENTED_OFFLINE
EXECUTABLE_CLOSURE=OFFLINE_VERIFIED_LIVE_PENDING
RESIDUAL_BLOCKER_OR_RISK=DISCOVER_UX_TARGET_CLEANUP_SELINUX_LIVE_AND_CLEAN_SUDO_RELEASE_GAP
CANONICAL_DOCUMENTATION=Goodix 27c6 5125 manuale tecnico.md
REVIEW_SET=GIT_NATIVE_DEVELOPMENT
LIVE_EXECUTION_PERFORMED=false
```

Fonti lette, senza copiarne codice nel progetto:

- [pam_fprintd: limitazioni](https://man.archlinux.org/man/pam_fprintd.8.en).
- [Polkit #650](https://github.com/polkit-org/polkit/issues/650), consultata aperta.
- [Helper PAM Polkit 127](https://raw.githubusercontent.com/polkit-org/polkit/127/src/polkitagent/polkitagenthelper-pam.c), SHA-256 `477f00755e8153638d3796772f9ebfc3cd9798f5ce09741a0eccba51c2f71f55`.
- [Sessione Polkit 127](https://raw.githubusercontent.com/polkit-org/polkit/127/src/polkitagent/polkitagentsession.c).
- [Listener KDE v6.7.5](https://raw.githubusercontent.com/KDE/polkit-kde-agent-1/v6.7.5/policykitlistener.cpp), SHA-256 `2c10093d6cd8a0e5c1e0a9cf56c91ea4f26074e50ea07bd841ef62e98d495449`.
- [Dialogo KDE v6.7.5](https://raw.githubusercontent.com/KDE/polkit-kde-agent-1/v6.7.5/qml/QuickAuthDialog.qml), SHA-256 `66b84de1b6450e919507b095a0243e49d28a0781d56d8f1b70ec8bf583176874`.
- Reference locale `reference/fprintd-fedora44-1.94.5/PROVENANCE.md`, sorgente PAM
  e patch `production/login/`; documentazione e codice managed-install.

Il sorgente KDE della versione Fedora è stato successivamente verificato nel
[source RPM ufficiale](https://kojipkgs.fedoraproject.org/packages/polkit-kde/6.7.5/1.fc44/src/polkit-kde-6.7.5-1.fc44.src.rpm):
lo spec non applica patch downstream. Sono state lette anche le implementazioni
[pam_get_authtok](https://github.com/linux-pam/linux-pam/blob/v1.7.2/libpam/pam_get_authtok.c)
e [pam_unix](https://github.com/linux-pam/linux-pam/blob/v1.7.2/modules/pam_unix/pam_unix_auth.c).
Queste sono reference comportamentali, non codice incorporato né prova hardware.
