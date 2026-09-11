<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D286/01 — survival a reboot e rollback readiness

> **HUMAN REQUIRED:** il kit esegue un reboot reale e, dopo il riavvio, una
> sola autenticazione biometrica `sudo -v`. L'agente AI non deve avviarlo.

## Scopo

Il kit verifica prima e dopo il reboot la coerenza root-only dell'installazione
D285: state, runtime, wrapper, drop-in, authselect, PAM, sudoers, unico template
ownership-pinned, libfprint di sistema e tutti i pre-delete gate dell'uninstall.
Non disinstalla nulla e non abilita lock screen o login.

Gli audit privilegiati usano `pkexec`, non `sudo`: su questo target polkit usa
`system-auth`, dal quale D285 ha rimosso pam_fprintd. L'elevazione di audit
richiede quindi la password amministrativa ma non deve raggiungere il sensore.
Il solo contatto biometrico previsto è la `sudo -v` post-reboot.

## Prima del reboot

Salvare ogni lavoro aperto, non usare contemporaneamente fprintd/sudo e
lanciare dalla root del repository come utente normale:

```bash
operator_kit/d286-01-reboot-survival/run-d286-01.sh --operator-pre-reboot
```

Autenticare il dialogo polkit con la password. Il kit crea una capture
sanitizzata persistente nel repository, stampa il comando post-reboot e chiede
`RIAVVIA D286`. Non digitare la conferma se un gate fallisce.

## Dopo il reboot

Accedere normalmente, non bloccare lo schermo e usare esattamente il comando
stampato prima del riavvio:

```bash
operator_kit/d286-01-reboot-survival/run-d286-01.sh \
  --operator-post-reboot <capture-directory-stampata>
```

Il primo dialogo polkit esegue l'audit root-only senza sensore. Poi digitare
`INDICE DESTRO` e appoggiare il dito una sola volta. Non digitare la password
nel prompt sudo: se compare, premere `Ctrl-C`. Non ripetere automaticamente in
caso di non-match o anomalia; il rischio noto
`SAME_FINGER_FALSE_NON_MATCH_OCCASIONALE` rende un singolo non-match non
conclusivo. In caso di fallimento il kit raccoglie una volta sola, via polkit e
senza nuova verifica, la telemetria sanitizzata della prova fallita. Conservare
la capture e richiedere review.

## Guardrail

- una sola invocazione `sudo -v` post-reboot;
- `pam_fprintd max-tries=1` e nessun retry del kit;
- nessun enrollment, delete, reinstallazione o modifica PAM/authselect;
- nessuna esportazione di state, pathname/hash template o FP3;
- audit fail-closed prima del reboot e prima/dopo la verifica;
- diagnostica post-fallimento root-only senza retry del sensore;
- timestamp sudo invalidato prima e dopo la prova.

## Preflight offline

```bash
operator_kit/d286-01-reboot-survival/run-d286-01.sh --offline-preflight
```

Il preflight non invoca pkexec, sudo, systemctl reboot, fprintd o USB.
