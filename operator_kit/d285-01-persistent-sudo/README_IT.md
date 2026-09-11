<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D285/01 — installazione persistente e reversibile per `sudo`

> **HUMAN REQUIRED:** il kit è chiuso offline ma non è stato eseguito. Installa
> file persistenti, modifica authselect/PAM/sudoers/systemd, raggiunge il sensore
> e conserva su disco un template biometrico. L'agente AI non deve avviarlo.

## Scelta architetturale

`pam_fprintd.so` usa il nome D-Bus globale `net.reactivated.Fprint`; non può
selezionare un daemon o uno storage per servizio PAM. Inoltre il profilo
authselect attuale inserisce pam_fprintd in `system-auth`, usato anche da
KScreenLocker. Lasciare `with-fingerprint` attivo esporrebbe quindi il template
persistente a consumer non inclusi nel boundary.

Il kit disabilita reversibilmente `with-fingerprint` e verifica che
`system-auth` non contenga più pam_fprintd e che `fingerprint-auth` fallisca
chiuso. Installa poi un servizio PAM nuovo, `goodix-d285-01-sudo`, e un override
sudoers limitato al solo utente operatore. Il fallback `pam_unix.so` resta
sempre dopo `pam_fprintd.so max-tries=1 timeout=45`.

Questo isola i consumer PAM osservati; non è isolamento assoluto del servizio
D-Bus. Programmi autorizzati da polkit possono ancora parlare direttamente con
fprintd. Non riabilitare manualmente `with-fingerprint` mentre D285 è attivo.

## File persistenti

- runtime hash-pinned sotto `/usr/local/lib64/goodix-27c6-5125/`;
- wrapper fail-closed `/usr/local/sbin/goodix-d285-01-fprintd`;
- drop-in `/etc/systemd/system/fprintd.service.d/90-goodix-d285-01.conf`;
- PAM `/etc/pam.d/goodix-d285-01-sudo`;
- sudoers `/etc/sudoers.d/90-goodix-d285-01`;
- stato root-only `/etc/goodix-27c6-5125/d285-01.state`;
- un template FP3 per l'indice destro dell'utente in `/var/lib/fprint`.

La libreria libfprint di sistema non viene sostituita. Il wrapper verifica a
ogni avvio l'hash del daemon Fedora, il manifest dei sei oggetti runtime e i
due symlink. Un aggiornamento incompatibile fa fallire fprintd chiuso; il
fallback password di sudo resta disponibile.

## Prerequisiti e stop condition

- Fedora 44 x86_64 e versioni esatte validate dal preflight;
- branch `development`, HEAD uguale a `origin/development`, review set pulito;
- RPM OpenCV integri in `/tmp/goodix-opencv-4.13-rpms`;
- esattamente un Goodix USB `27c6:5125`;
- nessun template fprintd preesistente per l'utente;
- nessun file D285 già presente;
- nessun uso concorrente di fprintd, sudo biometrico o blocco schermo.

Fermarsi con `Ctrl-C` prima della conferma se un prerequisito non è vero. Nel
test non digitare la password: se compare un prompt password, premere
`Ctrl-C`; non ripetere automaticamente la run dopo un'anomalia. Conservare gli
output e richiedere review. Il trap root tenta rollback completo in ogni
failure di installazione.

## Installazione manuale

Dalla root del repository, come utente normale:

```bash
operator_kit/d285-01-persistent-sudo/run-d285-01.sh \
  --operator-install /tmp/goodix-opencv-4.13-rpms
```

La run richiede `INSTALLA D285`, poi `DESTRO` per otto contatti enrollment e
`INDICE DESTRO` per un solo `sudo -v`. Budget di installazione: due action
biometriche, massimo nove contatti, zero retry automatico o implicito. Al
termine stampa `EXPORT_DIRECTORY` e `TERMINAL_TRANSCRIPT`; allegare i tre file
esportati, mai lo state root-only o il template. Dopo la copia byte-identica,
il result privato sotto `/var/tmp` viene rimosso; resta soltanto l'export
sanitizzato dell'utente.

## Disinstallazione manuale

Come lo stesso utente:

```bash
operator_kit/d285-01-persistent-sudo/run-d285-01.sh --operator-uninstall
```

Il rollback procede solo se file, runtime, daemon, authselect e l'unico
template corrispondono agli hash/percorsi registrati. Qualunque drift rifiuta
fail-closed prima di cancellare dati e richiede review umana. Se tutto coincide,
il kit elimina il solo template ownership-pinned, rimuove i file D285,
riabilita `with-fingerprint`, rimuove il backup authselect creato dal kit e
ripristina lo stato iniziale del servizio.

## Preflight offline

```bash
operator_kit/d285-01-persistent-sudo/run-d285-01.sh \
  --offline-preflight /tmp/goodix-opencv-4.13-rpms
```

Il preflight costruisce la candidate e verifica ABI, manifest, wrapper,
sudoers, rendering authselect e contratti. Non usa `sudo`, non enumera USB e
non raggiunge il sensore.
