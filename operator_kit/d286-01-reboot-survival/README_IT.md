<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D286/01 — retry manuali post-reboot del consumer sudo (chiuso)

> **CHIUSO:** la run finale è PASS. L'entrypoint `--operator-retry` rifiuta
> prima di qualunque azione e non deve essere rieseguito.

## Stato del primo ciclo

Il reboot D286 iniziale è già avvenuto ed è chiuso: gli audit root-only prima e
dopo il riavvio hanno provato la sopravvivenza di state, runtime, wrapper,
drop-in, authselect, PAM, sudoers, template ownership-pinned e libfprint di
sistema. La sola VERIFY ha prodotto un autentico `NO_MATCH`; non è stato
eseguito alcun retry automatico. Il vecchio percorso `--operator-pre-reboot` /
`--operator-post-reboot` ora rifiuta fail-closed e non va rieseguito.

## Cosa cambia nel correttivo

- il journal è delimitato con un cursor systemd, senza timestamp dipendenti
  dalla locale;
- ogni tentativo usa il vero consumer `/usr/bin/sudo -v` e il PAM D285
  `max-tries=1`;
- stdin di sudo è un FIFO privato che non riceve mai byte di password;
- se PAM raggiunge il fallback, un prompt sentinella fa terminare direttamente
  quel processo sudo prima di qualunque retry interno;
- ogni nuovo contatto richiede una conferma esplicita dell'operatore;
- l'audit per tentativo classifica `MATCH`, `NO_MATCH`, `PAM_ERROR` o
  `SAFETY_VIOLATION` dal journal, preservando epoch, keypoint, score,
  comparison, matched sample e contatori di sicurezza.

Il fallback password D285 resta disponibile per il normale uso del sistema;
soltanto questo test non dispone di un canale attraverso cui fornirla.

## Comando storico, non rieseguire

La run completata è stata avviata dalla root del repository, come utente
normale, con:

```bash
operator_kit/d286-01-reboot-survival/run-d286-01.sh --operator-retry
```

Il comando ora restituisce `D286_01_LIVE_CLOSED_DO_NOT_RERUN`. Nella run
storica, i dialoghi `pkexec` prima, durante e dopo la serie erano audit
root-only e richiedevano la password amministrativa attraverso `system-auth`,
dove fingerprint era disabilitato. Non erano tentativi biometrici.

Per il primo contatto veniva richiesto `INDICE DESTRO`. Dopo un `NO_MATCH`, il
kit chiedeva esplicitamente `TENTATIVO 2` o `TENTATIVO 3`. Non andava
appoggiato nuovamente il dito senza quella richiesta. Il primo `MATCH`
terminava immediatamente la serie. Dopo tre `NO_MATCH`, oppure su
`PAM_ERROR`/`SAFETY_VIOLATION`, il kit terminava senza un quarto tentativo e
conservava la capture per la review AI-PM.

## Contratto e stop condition

```text
MAX_VERIFY_ATTEMPTS=3
MAX_PHYSICAL_CONTACTS=3
PAM_MAX_TRIES_PER_ATTEMPT=1
AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false
STOP_ON_FIRST_MATCH=true
PASSWORD_INPUT_POSSIBLE_DURING_SUDO_TEST=false
```

Non modificare matcher, threshold, preprocessing o template dopo un
`NO_MATCH`. Non disinstallare o reinstallare D285. Non estendere la prova a
lock screen o login.

## OpenCV per build future

Il path persistente canonico degli RPM è:

```text
/home/guido/Repository/goodix-27c6-5125_private/GoodixArtifacts/opencv-4.13-rpms
```

Gli RPM sono locali e ignorati da Git; i cinque digest restano quelli del
manifest versionato `operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/opencv-rpms.sha256`.
D286 usa il runtime già installato e non ricompila né reinstalla nulla.

## Preflight offline

```bash
operator_kit/d286-01-reboot-survival/run-d286-01.sh --offline-preflight
```

Il preflight non invoca pkexec, sudo, fprintd o USB. Verifica anche che il
journal cursor sia leggibile dall'utente corrente.
