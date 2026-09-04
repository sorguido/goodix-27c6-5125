<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/07 — layout privato production e compatibilità fprintd

Questo kit è stato preparato offline e successivamente eseguito manualmente
dall'Utente con autorizzazioni distinte per provisioning e probe full. Entrambe
le run sono concluse con successo; non hanno avviato `fprintd`, aperto USB
Goodix o eseguito una run live.

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

## Stato del Real Target Compatibility Gate

Sul Fedora 44 ispezionato offline, `fprintd.service` non imposta `User=`,
`Group=` o `DynamicUser=`: per una system service systemd usa quindi root.
`ProtectSystem=strict` rende il layout sola lettura ma non lo nasconde.

Una prima osservazione aveva rilevato SELinux Disabled; provisioning e probe
conclusivi hanno entrambi rilevato lo stato reale corrente `Enforcing`. In
stato Disabled il controllo MAC e la configurazione delle label sono non
applicabili e il provisioning non invoca tool SELinux. Con Enforcing o
Permissive, come nella run conclusiva, la policy
assegna inizialmente il tipo generico `var_lib_t`; le regole per `fprintd_t`
permettono lettura completa di `fprintd_var_lib_t`, non dei normali file
`var_lib_t`, e il provisioning configura allora i sei path esatti.

Il primo probe manuale autorizzato ha restituito
`MOTIVO=FILE_ASSENTE_O_NON_REGOLARE_gfusb.dll`. È evidenza attesa di layout non
ancora provisionato, non evidenza di incompatibilità dell'identità fprintd. La
versione corretta separa il controllo ambiente dalla validazione layout e, nel
probe completo, elenca in una sola esecuzione tutti i file assenti. Il
provisioning successivo ha installato entrambi i file mancanti e il probe full
ha concluso `REAL_TARGET_COMPATIBILITY=PASS`.

## Sequenza corretta

1. Il controllo environment-only non richiede sudo e non esamina la directory:

```bash
./operator_kit/target_compatibility/d279_07_fprintd_layout/probe-fprintd-layout.sh --environment-only
```

2. Il provisioning viene eseguito solo dopo una distinta autorizzazione umana.
3. Dopo il provisioning, un'altra autorizzazione al solo sudo read-only
   permette il probe completo:

```bash
sudo ./operator_kit/target_compatibility/d279_07_fprintd_layout/probe-fprintd-layout.sh --full
```

Il probe completo non legge il contenuto dei cinque file, non calcola hash,
non cambia label/configurazioni, non avvia `fprintd` e non apre USB. Legge
soltanto unit, metadata e, se attiva, policy/label SELinux. Termina fail-closed
se il layout non è esattamente quello previsto o se non può dimostrare
l'accesso.

## Provisioning (run conclusa; istruzioni conservate per provenance)

`prepare-production-layout.sh` è stato eseguito dall'operatore con
autorizzazione esplicita per `sudo` e accesso/copia degli input reali mancanti;
la modifica SELinux era condizionata allo stato attivo effettivamente rilevato. Ogni
destinazione assente richiede una sorgente esplicita; un file esistente
conforme è preservato. Lo script non sovrascrive mai un file esistente e
installa solo file già verificati per size e SHA-256. Esempio puramente
illustrativo con tutte le sorgenti:

```bash
sudo ./operator_kit/target_compatibility/d279_07_fprintd_layout/prepare-production-layout.sh \
  --apply \
  --manifest /PERCORSO/PRIVATO/target-material-manifest.json \
  --transport /PERCORSO/PRIVATO/transport-material.bin \
  --config90 /PERCORSO/PRIVATO/target-config-90.bin \
  --gfusb /PERCORSO/PRIVATO/gfusb.dll \
  --fdt-cache /PERCORSO/PRIVATO/fdt-cache.bin
```

Per il corrective non serviva un altro probe privilegiato pre-provisioning per
stabilire quali dei due nuovi input mancassero. Le sorgenti già
individuate per solo nome/path, senza leggerne il contenuto, sono
`analysis/D230/work/GoodixExport/gfusb.dll` e
`captures/D255_20260822T205631772Z_85c8c41f/raw/cache_before/9f5327731cff3046e31d18356a6334c9e1494330f434f3fe75ad0a4c80db09e2.bin`.
La run autorizzata le ha passate entrambe: per una destinazione già presente e
conforme lo script preserva il file senza accedere alla sorgente
corrispondente; per una destinazione assente lo installa come `gfusb.dll` o
`fdt-cache.bin`.

Prima di qualsiasi autorizzazione, la selezione SELinux è osservabile senza
scritture con `prepare-production-layout.sh --check-selinux-plan`. Lo script
richiede la conferma testuale `INSTALLA_LAYOUT_D279_07`. Con SELinux Disabled
salta integralmente tool, mapping e label. Con SELinux attivo imposta regole
persistenti `fprintd_var_lib_t` soltanto per la directory e i cinque file (non
per gli altri contenuti storici), applica `restorecon` ai medesimi path e, in
caso di errore, ripristina le label originali. In entrambi i casi il rollback
rimuove soltanto lo stato creato dalla stessa invocazione, non elimina o
sovrascrive file già presenti, non avvia servizi e non contiene accesso USB.

Output prodotti: solo stdout/stderr dell'operatore. Il kit non crea report con
contenuti privati. Il probe conclusivo ha prodotto
`REAL_TARGET_COMPATIBILITY=PASS`; il gate D279/07 è chiuso.
