<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D290/01 — test persistente reversibile del login Plasma

Questo micro-kit sostituisce definitivamente, per D290/01, il precedente
percorso TTY3/FIFO/overlay. Installa soltanto il PAM `plasmalogin` già
revisionato, lascia un backup root-only, sopravvive al reboot e ripristina il
file Fedora durante la chiusura. Non crea servizi, daemon, mount o processi
persistenti e non modifica authselect, `password-auth`, `system-auth`,
`fingerprint-auth`, `/etc/pam.d/kde` o l'integrazione D285.

Il candidato aggiunge una sola riga `pam_fprintd.so` `sufficient`, con
`max-tries=1 timeout=45`, prima del substack `password-auth`. Un NO_MATCH non
elimina quindi il login con password. Il budget umano è una pressione Invio,
una VERIFY, un contatto e zero retry.

## Prerequisiti e stop

- branch `development`, `HEAD == origin/development` e critical set pulito;
- runtime D285/D286 e template dell'indice destro integri;
- un solo Goodix `27c6:5125`;
- PAM host e candidato con gli hash attesi;
- password dell'utente disponibile per il login e per il rollback;
- nessun aggiornamento di `plasma-login-manager` fra ARM e CLOSE.

Qualunque rifiuto è uno stop. Non eseguire ARM due volte. Dopo ARM non
modificare il PAM o il repository, non aggiornare il pacchetto e non riavviare
più volte: una seconda accensione perderebbe l'evidenza del boot del test.

## ARM

Dalla root del repository, nella normale sessione grafica:

```bash
operator_kit/d290-01-plasmalogin-persistent-test/run-d290-01.sh --operator-arm
```

Lo script richiede privilegi tramite `pkexec`, verifica backup, ownership,
mode, contesto SELinux, fallback e stato D285/D286, quindi termina. Non esegue
il reboot.

Solo dopo i quattro marker finali `true` eseguire manualmente:

```bash
sudo reboot
```

## LOGIN

Al Plasma Login Manager:

1. selezionare `guido`;
2. lasciare il campo password completamente vuoto;
3. premere Invio una sola volta;
4. appoggiare l'indice destro una sola volta.

Su MATCH entrare nel desktop senza usare nel frattempo altri consumer
biometrici. Su NO_MATCH o failure non ripetere il fingerprint: eseguire il
login normale con password.

## CLOSE

Subito dopo il login, dalla root del repository:

```bash
operator_kit/d290-01-plasmalogin-persistent-test/run-d290-01.sh --operator-close
```

CLOSE raccoglie soltanto sessione logind e journal pertinenti del boot
corrente, classifica l'esito e tenta sempre il rollback. La chiusura è completa
solo con:

```text
D290_HOST_PAM_RESTORED=true
D290_STATE_REMOVED=true
D290_ROLLBACK=PASS
```

La capture sanitizzata viene salvata sotto `captures/D290_01/`.

## Recovery eccezionale

Se il desktop non parte, usare una TTY, accedere con password, raggiungere la
root del repository ed eseguire:

```bash
operator_kit/d290-01-plasmalogin-persistent-test/run-d290-01.sh --operator-rollback
```

ROLLBACK funziona anche senza avere eseguito il test e quando il PAM è già
originale. Rifiuta un contenuto PAM inatteso o un aggiornamento del pacchetto,
per non sovrascrivere drift non attribuibile al kit; in quel caso conserva
backup e stato root-only per una review manuale.
