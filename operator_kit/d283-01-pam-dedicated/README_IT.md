<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D283/01 — verifica PAM dedicata sul target (chiusa)

> **CHIUSO — NON RIESEGUIRE:** Attempt 01 ha completato la verifica e la review
> indipendente l'ha classificata `PASS_LIVE_CLOSED`. Gli entrypoint live del kit
> rifiutano ora fail-closed con `D283_01_LIVE_CLOSED_DO_NOT_RERUN`.

## Scopo e rischio

Il kit verifica una sola autenticazione tramite un servizio PAM dedicato
`goodix-d283-01`, senza modificare login, sudo, `system-auth` o `/etc/pam.d`.
La run raggiunge il sensore reale e usa `sudo` per staging e rollback: deve
essere avviata manualmente dall'operatore.

Sequenza massima:

1. otto contatti dell'indice destro per enrollment;
2. un contatto dello stesso indice destro tramite PAM;
3. delete host-only e rollback.

Limiti tecnici: due action biometriche, nove contatti, `max-tries=1`, nessun
retry automatico o implicito autorizzato. Il template FP3 resta nello
storage isolato durante la run, viene eliminato e non entra nell'export.

Rischio residuo: è già stato osservato un falso non-match occasionale dello
stesso dito. Se PAM non autentica, non ripetere: allegare l'evidenza. Il kit
registra sia i return code PAM sia outcome, score e sample SIGFM per distinguere
il più possibile failure PAM e false reject biometrico.

## Prerequisiti

- branch `development`, `HEAD` allineato a `origin/development` e worktree
  live-critical pulito;
- RPM OpenCV già presenti in `/home/guido/Repository/goodix-27c6-5125_private/GoodixArtifacts/opencv-4.13-rpms`;
- Fedora `fprintd-1.94.5-5.fc44.x86_64` e
  `fprintd-pam-1.94.5-5.fc44.x86_64`;
- esattamente un Goodix USB `27c6:5125` collegato;
- nessun altro utilizzo contemporaneo di fprintd.

## Comando storico (non eseguire)

Il comando usato dall'operatore è conservato soltanto per provenance:

```bash
operator_kit/d283-01-pam-dedicated/run-d283-01.sh \
  --operator-run /home/guido/Repository/goodix-27c6-5125_private/GoodixArtifacts/opencv-4.13-rpms
```

Il launcher costruisce e verifica la candidate, mostra il budget e chiede di
digitare `ESEGUI`. `sudo` è visibile e serve solo al runtime transiente; non è
autenticato tramite impronta. Prima dell'enrollment bisogna digitare `DESTRO`.
Prima della conversazione PAM bisogna digitare `INDICE DESTRO` e poi presentare
esclusivamente l'indice destro registrato.

Al termine, allegare `operator.log` e `summary.env` dalla
`EXPORT_DIRECTORY`. Il wrapper stampa anche `TERMINAL_TRANSCRIPT`: se la run
fallisce, non ripeterla e allegare anche quel file. La trascrizione resta
disponibile con permessi `0600` anche se un gate rifiuta la run prima della
creazione dell'export.

## Preflight offline facoltativo

```bash
operator_kit/d283-01-pam-dedicated/run-d283-01.sh \
  --offline-preflight /home/guido/Repository/goodix-27c6-5125_private/GoodixArtifacts/opencv-4.13-rpms
```

Il preflight compila la candidate e prova `pam_start_confdir()` con
`pam_permit`; non avvia fprintd, non enumera USB e non raggiunge il sensore.
