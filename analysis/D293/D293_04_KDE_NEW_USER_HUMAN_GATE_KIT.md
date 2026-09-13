<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D293/04 — kit Human Gate KDE/new-user

## Esito offline

`operator_kit/live_probe/experiments/d293-kde-new-user/` materializza il primo
discriminante live rimasto per B3/B4 sul common harness esistente, che non è
stato modificato. Il kit è pronto offline ma non è stato eseguito: ogni accesso
USB, uso di privilegi e azione sensor-reaching resta dell'Utente.

```text
D293_04_OPERATOR_KIT=READY_OFFLINE
D293_04_LIVE_EXECUTION=HUMAN_REQUIRED_NOT_PERFORMED
CURRENT_PHASE=B
PHASE_B_CLOSED=false
PRODUCTION_READY=false
```

## Confine provato dal futuro operator-run

La preparazione richiede `development`, `HEAD=origin/development`, critical set
pulito, un solo `27c6:5125`, target Fedora 44/Plasma 6.7.5 esatto e runtime
D285/D286 integro. Costruisce la candidate dalla source-of-truth `production/`
e la rende disponibile a fprintd esclusivamente sotto `/run`, con manifest
SHA-256, drop-in systemd transiente e rollback. Non modifica PAM né file
package-owned.

Solo dopo il deployment l'operatore crea da KCM Users il principal locale
fisso `d293-phase-b-test`. Il supervisore attende la chiusura del KCM della
sessione originale, arresta l'eventuale fprintd socket-activated e pubblica
`READY_FOR_NEW_USER` soltanto a daemon inattivo. Il nuovo UID usa una vera
sessione Plasma/Wayland e il solo KCM standard per registrare e cancellare una
impronta. `fprintd-verify <utente>` esercita `VerifyStart(any)` fino a tre volte,
con stop al primo MATCH e nessun quarto tentativo.

Il budget tecnico deriva dagli audit production, non da un conteggio manuale:
una epoch IDENTIFY, una ENROLL con otto stage e fino a venti contatti, più una,
due o tre epoch VERIFY. Sono quindi imposti `MAX_ACTIONS=5`,
`MAX_CONTACTS=24` e retry transport/secure/post pari a zero. Le eventuali
ripetizioni biometriche richieste esplicitamente dall'enrollment KCM restano
distinte dai retry automatici.

Il namespace fprintd dell'utente preesistente è digestato internamente su
contenuto e metadata prima e dopo; viene esportato soltanto il booleano di
uguaglianza. Cleanup e recovery richiedono cancellazione KCM del template del
test user, rollback runtime, logout, rimozione dell'account/home esatto e audit
D285/D286 finale. Il supervisore termina esplicitamente dopo il rollback anche
su signal; la recovery post-reboot ricava l'identità originale dal chiamante
`pkexec`. La capture vive sotto `/var/tmp`, non nella home eliminabile del test
user; al recovery vengono rifiutati file speciali/ownership inattesa e il tree
viene trasferito all'utente originale prima di `userdel -r`. Capture e journal
sono sanitizzati e non contengono password, template, immagini, hash template
o materiale protetto.

## Riesame metodologico

1. D291 usava il principal già esistente e un percorso CLI; D293/04 usa la
   source production corrente, crea il principal dopo il deployment e passa
   dalla UI KDE realmente installata in una nuova sessione.
2. L'ipotesi è che driver device-wide e materiale runtime globale si integrino
   con risoluzione, storage e isolamento per un UID creato post-deployment,
   mantenendo invariato il principal preesistente.
3. Un fallimento non abilita retry live automatici: rollback e capture
   identificano il boundary discovery/PolicyKit/handoff/storage/verify/cleanup;
   la decisione successiva sarà specifica a quel boundary oppure `REPLAN`.

Due dita, delete singolo/re-enroll, rename/name-reuse e reboot non sono inclusi
in questo primo gate e restano B5. Phase B non può chiudersi senza l'esecuzione
umana e la review della relativa capture.

## Verifiche offline

Il validator statico è `analysis/D293/validate_d293_04.py`. Verifica sintassi ed
eseguibilità degli hook, budget, marker audit production, derivazione dei
contatti, stage enrollment, digest del principal, quiescenza prima di READY,
mount read-only, Git `safe.directory` solo via environment e assenza di
modifiche al common harness. Il percorso `--offline-test` prova inoltre la
compatibilità executable del payload col common harness senza USB o privilegi.

Risultati Executor:

- `python3 analysis/D293/validate_d293_04.py`: PASS;
- operator-run simulata con `--offline-test` da cwd `/tmp`: PASS;
- common harness regression: 14/14 PASS;
- clean build production `normal`: PASS, ABI `LIBFPRINT_2.0.0`, nessun
  RPATH/host-test symbol, rete non condivisa e zero enumerazione USB;
- `production/check-source.sh`: PASS, inclusi source/digest/patch/path set;
- `analysis/D293/validate_d293_03.py`: PASS;
- `git diff --check`: PASS.

```text
EXECUTABLE_CLOSURE=READY_OFFLINE_HUMAN_GATE_PENDING
REAL_USB=0
SUDO_OR_PKEXEC_EXECUTED_BY_AI=0
PROTECTED_MATERIAL_READ=0
```
