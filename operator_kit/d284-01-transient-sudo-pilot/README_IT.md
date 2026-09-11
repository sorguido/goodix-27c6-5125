<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D284/01 — pilot transiente `sudo` con impronta

> **HUMAN REQUIRED:** questo kit non è stato eseguito live. Raggiunge il
> sensore, usa `sudo` e modifica temporaneamente configurazione PAM/sudoers.
> Deve essere avviato manualmente dall'Utente soltanto dopo la closure offline.

## Perché questo boundary

Sul target Fedora 44 `with-fingerprint` è già attivo. `sudo` e il blocco
schermo includono `system-auth`, ma la regola installata `pam_fprintd.so` non
specifica `max-tries` e usa quindi il default di tre tentativi. Plasma Login
usa invece `password-auth` e non è il primo target corretto.

Il pilot non abilita il driver globalmente. Avvia la candidate in `/run`, usa
uno storage fprintd isolato e devia temporaneamente soltanto `sudo` del singolo
utente verso `goodix-d284-01-sudo`. La stack impone `max-tries=1` e conserva
`pam_unix.so` dopo l'impronta come fallback password. Login, Plasma Login,
authselect e i file PAM esistenti non vengono modificati.

## Sequenza e rischio

1. otto contatti dell'indice destro per un enrollment isolato;
2. invalidazione del timestamp `sudo` dell'utente;
3. una sola autenticazione reale `sudo -v` con l'indice destro;
4. rimozione immediata degli override PAM/sudoers;
5. delete del template isolato e rollback completo.

Budget: due action biometriche e massimo nove contatti. Non sono consentiti
retry automatici o impliciti. Non digitare la password durante il test: se
compare il prompt password, premere `Ctrl-C`; il processo root già attivo
esegue comunque il rollback. La password resta strutturalmente disponibile
come recovery, ma non deve rendere ambiguo l'esito biometrico.

Durante la breve finestra staged non bloccare lo schermo, non aprire un altro
terminale `sudo` e non avviare altri consumer PAM/fprintd. In caso di qualsiasi
anomalia non ripetere il kit.

## Prerequisiti

- Fedora 44 x86_64, profilo authselect `local ... with-fingerprint` valido;
- `sudo-1.9.17-8.p2.fc44.x86_64`, PAM 1.7.2, fprintd/fprintd-pam 1.94.5;
- utente operatore già autorizzato da sudoers; il launcher lo verifica prima
  dello staging;
- branch `development`, HEAD allineato a `origin/development`, worktree
  live-critical pulito;
- RPM OpenCV già presenti in `/tmp/goodix-opencv-4.13-rpms`;
- esattamente un Goodix USB `27c6:5125`;
- nessun altro uso contemporaneo di fprintd, PAM biometrico o blocco schermo.

## Comando operativo

Dalla root del repository, come utente normale:

```bash
operator_kit/d284-01-transient-sudo-pilot/run-d284-01.sh \
  --operator-run /tmp/goodix-opencv-4.13-rpms
```

Il launcher costruisce la candidate, espone il budget e chiede `ESEGUI`.
Richiede poi `DESTRO` prima dell'enrollment e `INDICE DESTRO` immediatamente
prima di `sudo -v`. Al termine stampa `EXPORT_DIRECTORY` e
`TERMINAL_TRANSCRIPT`. Allegare `operator.log`, `summary.env` e transcript;
non allegare `private/`.

## Preflight offline facoltativo

```bash
operator_kit/d284-01-transient-sudo-pilot/run-d284-01.sh \
  --offline-preflight /tmp/goodix-opencv-4.13-rpms
```

Il preflight non chiama modalità live, non usa `sudo`, non enumera USB e non
raggiunge il sensore.
