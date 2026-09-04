<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D279/07 — layout production privato e gate identità fprintd Fedora 44

## Esito

```text
D279_07_OUTCOME=HUMAN_REQUIRED
D279_07_BASELINE=ba8750874df3f7c38d515be7d6b0412a5f0ab478
ADVANCEMENT=MATERIAL_ARCHITECTURAL_OR_REPOSITORY_ADVANCEMENT
EXECUTABLE_CLOSURE=PASS_OFFLINE_SYNTHETIC;REAL_TARGET_PROBE_PENDING
REAL_TARGET_COMPATIBILITY=BLOCKED_HUMAN_REQUIRED
PRODUCTION_LAYOUT_API=READY_OFFLINE
PRODUCTION_LAYOUT_PROVISIONED=false
AUTHENTIC_PROTECTED_INPUTS_ACCESSED=false
SUDO_EXECUTED=false
FPRINTD_EXECUTED=false
REAL_USB_ACCESS=0
LIVE_EXECUTION_PERFORMED=false
```

L'autorizzazione Utente del 4 settembre 2026 rende canonico, per sola
progettazione/implementazione offline e preparazione del kit, il riuso di
`/var/lib/goodix-5125-poc` con i tre nomi preesistenti e due nuovi nomi:

```text
/var/lib/goodix-5125-poc                              root:root 0700
/var/lib/goodix-5125-poc/target-material-manifest.json root:root 0600
/var/lib/goodix-5125-poc/transport-material.bin        root:root 0600
/var/lib/goodix-5125-poc/target-config-90.bin           root:root 0600
/var/lib/goodix-5125-poc/gfusb.dll                      root:root 0600
/var/lib/goodix-5125-poc/fdt-cache.bin                  root:root 0600
```

Non sono autorizzati né avvenuti sudo, creazione/copia dei file reali,
lettura di materiale autentico, installazione, esecuzione di fprintd, USB o
live.

## Implementazione offline

`goodix_runtime_material_paths_production()` espone i cinque path assoluti
senza discovery, fallback o I/O. `GoodixRuntimeMaterialPaths` porta anche la
directory comune. Il loader accetta soltanto path assoluti figli diretti di
quella directory, apre la directory con
`O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW`, richiede owner/group/mode
coerenti con la policy e verifica pre/post device+inode+metadata anche sul path
corrente prima di pubblicare l'owner.

La policy production fissa directory uid/gid `0:0`, mode `0700`; entrambi i
reader di file ora verificano davvero uid **e gid** `0:0`, oltre a mode `0600`,
tipo, size, hash e gli altri pin già esistenti. Questo corregge una discrasia
emersa durante la review: il commento precedente dichiarava `root:root`, ma
il codice controllava solo UID root.

La suite sintetica non chiama la funzione di load sui path production. Prova
invece path temporanei, policy parametrizzata con uid/gid correnti, rifiuto di
un GID errato, composizione, pubblicazione atomica e cleanse.

## Verifica autonoma dell'identità runtime Fedora 44

Evidenza letta dal target Fedora 44 corrente, senza avviare il servizio:

```text
fprintd_package=fprintd-1.94.5-5.fc44.x86_64
libfprint_package=libfprint-1.94.100-1.fc44.x86_64
systemd_package=systemd-259.8-1.fc44.x86_64
fprintd_unit_sha256=da6722b0404c3a8e4ab3b3a6247be0bf9f0e8bf10f99e9f9457004f8a202c050
User=UNSET
Group=UNSET
DynamicUser=UNSET
ProtectSystem=strict
ProtectHome=true
StateDirectory=fprint
StateDirectoryMode=0700
ReadWritePaths=/sys/devices
```

`systemd-analyze cat-config systemd/system/fprintd.service` mostra soltanto la
unit vendor, senza drop-in. Per una system service, `User=` e `Group=` non
impostati significano root. La documentazione systemd 259 installata specifica
che `ProtectSystem=strict` monta l'intera gerarchia sola lettura, con eccezioni
esplicite per i path scrivibili: non la rende invisibile. Il driver deve solo
leggere i cinque input. Quindi:

```text
FPRINTD_RUNTIME_UID_GID=root:root
UNIX_DAC_ACCESS_TO_ROOT_ROOT_0700_0600=COMPATIBLE
PROTECT_SYSTEM_STRICT_READ_ONLY_ACCESS=COMPATIBLE
```

### SELinux

Il target osservato contiene `selinux-policy-targeted-44.8-1.fc44`, ma
`getenforce` e `sestatus` riportano `Disabled`. Il path non personalizzato ha
expected type `var_lib_t`; `/var/lib/fprint` usa invece
`fprintd_var_lib_t`.

Una query read-only con la libreria SETools sul policy binary installato
`policy.35` mostra:

- `fprintd_t -> fprintd_var_lib_t:dir` include `getattr/open/read/search`;
- `fprintd_t -> fprintd_var_lib_t:file` include `getattr/open/read`;
- sul generico `var_lib_t` non emerge un allow equivalente di apertura e
  lettura file per `fprintd_t`.

Il provisioning preparato registra quindi mapping persistenti
`fprintd_var_lib_t` soltanto per la directory e i cinque file, e applica
`restorecon` agli stessi path. Non usa una regola ricorsiva: report, marker e
altri contenuti storici nella directory restano fuori scope. Queste operazioni
non sono state eseguite.

## Real Target Compatibility Gate e operator kit

Il namespace dell'ambiente AI non espone in modo affidabile gli UID/GID host
di `/var/lib/goodix-5125-poc`, e l'AI non è autorizzata a usare sudo o a fare
stat dei cinque file privati. Manca perciò la prova target-specific finale che
directory e file reali abbiano metadata conformi. Con SELinux disabilitato sul
target osservato, la policy mandatory non interviene; se sul target della
prova è Enforcing/Permissive, anche expected/actual label e allow rules devono
passare.

Il kit è in:

```text
operator_kit/target_compatibility/d279_07_fprintd_layout/
```

Contiene:

- `probe-fprintd-layout.sh`: probe metadata/policy read-only, non legge il
  contenuto dei file e non avvia servizi o USB;
- `prepare-production-layout.sh`: provisioning futuro fail-closed con sorgenti
  esplicite, pin size/SHA-256, nessun overwrite, copia temporanea, rollback
  dei soli file creati dalla run, rollback simmetrico delle label e mapping
  SELinux persistenti limitati ai sei path autorizzati;
- `README.md`: prerequisiti, rischi, stop condition e invocazioni in italiano.

Entrambi gli script richiedono un'azione futura dell'operatore. Il provisioning
richiede una distinta autorizzazione per sudo, accesso/copia dei file reali e
modifica SELinux. Il probe richiede almeno sudo read-only perché la directory
`0700` non è attraversabile dall'utente ordinario. Finché il probe non produce
`REAL_TARGET_COMPATIBILITY=PASS`, la compatibilità production del layout non è
chiusa.

## Verifiche

```text
bash -n operator_kit/target_compatibility/d279_07_fprintd_layout/*.sh=PASS
git diff --check=PASS
runtime_material_normal=9/9_PASS
runtime_material_ASAN_UBSAN=9/9_PASS
D278_loader_normal=63/63_PASS
D278_loader_ASAN_UBSAN=63/63_PASS
Fedora44_libfprint_1.94.100_build=PASS
Fedora44_standard_registry=PASS
registered_USB_ID=27c6:5125_EXACTLY_ONCE
REAL_PRODUCTION_SECRET_READ=false
REAL_USB_ENUMERATION_COUNT=0
REAL_USB_OPEN_COUNT=0
REAL_USB_CLAIM_COUNT=0
REAL_USB_SUBMIT=0
```

Le warning `-Wswitch-enum` della build Meson sono preesistenti e fuori dal
delta D279/07. `shellcheck` non è installato; la validazione sintattica bash è
passata.

## Review set

```text
REVIEW_SET=BASELINE_ba8750874df3f7c38d515be7d6b0412a5f0ab478_PLUS_WORKTREE_DIFF_PLUS_analysis/D279/D279_07_offline_production_layout_and_fprintd_identity_gate.md_PLUS_operator_kit/target_compatibility/d279_07_fprintd_layout_PLUS_Goodix_27c6_5125_manuale_tecnico.md
```
