<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/07 — layout privato production e compatibilità fprintd

Questo kit è stato preparato offline. **Non è stato eseguito.** Non autorizza
installazione, accesso ai cinque input autentici, avvio/arresto di `fprintd`,
USB Goodix o una run live.

## Layout autorizzato

Directory:

```text
/var/lib/goodix-5125-poc                    root:root 0700
```

File:

```text
target-material-manifest.json              root:root 0600
transport-material.bin                     root:root 0600
target-config-90.bin                       root:root 0600
gfusb.dll                                  root:root 0600
fdt-cache.bin                              root:root 0600
```

I primi tre nomi sono preservati; gli ultimi due sono i nuovi input del
provider runtime. Non esistono fallback o ricerca in altre directory.

## Perché esiste ancora un Real Target Compatibility Gate

Sul Fedora 44 ispezionato offline, `fprintd.service` non imposta `User=`,
`Group=` o `DynamicUser=`: per una system service systemd usa quindi root.
`ProtectSystem=strict` rende il layout sola lettura ma non lo nasconde.

La policy SELinux installata assegna però al path non configurato il tipo
generico `var_lib_t`. Le regole per `fprintd_t` permettono lettura completa di
`fprintd_var_lib_t`, non dei normali file `var_lib_t`. La macchina osservata ha
SELinux disabilitato e il namespace dell'ambiente AI non conserva in modo
affidabile gli UID/GID host: una prova finale sul target reale richiede quindi
intervento umano.

## Probe read-only (azione futura separata)

Solo dopo un'autorizzazione esplicita per il probe, l'operatore può eseguire:

```bash
sudo ./operator_kit/target_compatibility/d279_07_fprintd_layout/probe-fprintd-layout.sh
```

Il probe non legge il contenuto dei cinque file, non calcola hash, non cambia
label/configurazioni, non avvia `fprintd` e non apre USB. Legge soltanto unit,
metadata e policy SELinux. Termina fail-closed se il layout non è esattamente
quello previsto o se non può dimostrare l'accesso.

## Provisioning (preparato, non autorizzato all'esecuzione)

`prepare-production-layout.sh` è destinato a una successiva azione operatore
esplicitamente autorizzata per `sudo`, accesso/copia dei cinque input reali e
modifica della configurazione SELinux. Richiede cinque sorgenti esplicite,
non sovrascrive mai un file esistente e installa solo file già verificati per
size e SHA-256. Esempio puramente illustrativo:

```bash
sudo ./operator_kit/target_compatibility/d279_07_fprintd_layout/prepare-production-layout.sh \
  --apply \
  --manifest /PERCORSO/PRIVATO/target-material-manifest.json \
  --transport /PERCORSO/PRIVATO/transport-material.bin \
  --config90 /PERCORSO/PRIVATO/target-config-90.bin \
  --gfusb /PERCORSO/PRIVATO/gfusb.dll \
  --fdt-cache /PERCORSO/PRIVATO/fdt-cache.bin
```

Lo script richiede la conferma testuale
`INSTALLA_LAYOUT_D279_07`, imposta regole persistenti `fprintd_var_lib_t`
soltanto per la directory e i cinque file (non per gli altri contenuti
storici), applica `restorecon` ai medesimi path e, in caso di errore, ripristina
le label originali e rimuove soltanto file/regole creati dalla stessa
invocazione. Non
elimina o modifica file già presenti. Non avvia servizi e non contiene alcun
accesso USB.

Output prodotti: solo stdout/stderr dell'operatore. Il kit non crea report con
contenuti privati. La closure production resta sospesa finché il probe non
produce `REAL_TARGET_COMPATIBILITY=PASS` sul target reale.
