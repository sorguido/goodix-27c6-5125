<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Licensing and provenance

## Directory map

| Scope | Default for new project-authored work | Rule |
| --- | --- | --- |
| `core/` | `GPL-2.0-or-later` | Userspace transport, protocol, TLS, FDT, capture and image code. |
| `tools/` | `GPL-2.0-or-later` | Tools connected to or derived from the GPL core. |
| `libfprint-driver/` | `LGPL-2.1-or-later` | Upstream-facing driver/glue; separate copyright boundary. |
| `src/`, `operator_kit/`, historical `analysis/D239`–`D246` | historical status retained | Frozen/reproducibility paths are not mass-moved or mass-relicensed by D247. |
| `docs/`, `analysis/` | file-specific | Check the file header and provenance; private evidence is not made open source by location. |

The canonical GPL and LGPL texts are in `LICENSES/`. The earlier
BSD-2-Clause grant remains effective for revisions already distributed under
it and is preserved in `LICENSES/BSD-2-Clause.txt`; D247 does not revoke it.
Third-party content keeps its own license.

No blanket open-source grant covers OEM firmware/binaries, private captures,
TLS/PSK secrets, biometric samples/templates, factory data, or any other asset
that cannot be redistributed. Such material must remain outside review bundles
and future public exports.

## Evidence authority and implementation reuse

Target-specific evidence authority and implementation provenance are separate:

```text
EVIDENCE AUTHORITY:
local 12509 capture/DLL/APP/live evidence and repeatable local tests
    > external implementation

IMPLEMENTATION REUSE:
Rockytkg GPL-2.0-or-later code = approved implementation source for core/tools
    only, subject to verified source license, attribution and provenance
```

External behavior does not prove that an operation is safe, non-persistent,
factory-preserving, correct for `GF_ST411SEC_APP_12509`, or compatible with the
factory/Windows PSK. The hardware invariant and all no-flash/no-IAP/no-OTP/
no-provisioning/no-persistent-write rules continue to apply.

## Import procedure and ledger

Before copying or adapting external code:

1. retrieve the source read-only and record an immutable commit;
2. verify the source path's license/SPDX, notices, relevant copyright holders,
   and whether third-party components have different terms;
3. confirm the destination domain is license-compatible;
4. preserve applicable SPDX, copyright and attribution notices;
5. add one ledger row recording source repository, commit, path, original
   license, known copyright, local import step/date, destination and changes;
6. review the diff for unintended proprietary, secret or biometric material;
7. validate sensor-reaching behavior independently against target-local
   evidence before any separately authorized live execution.

An author's permission covers only rights that author actually controls.

| LOCAL_PATH | SOURCE_REPO | SOURCE_COMMIT | SOURCE_PATH | LICENSE | COPYRIGHT | IMPORT_STEP | NOTES |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `core/post_d4.py` (AF builder/state parser and command framing portions) | `https://github.com/Rockytkg/goodix-linux-27c6-5125` | `227eba219fa9e3fbac5bd59aca79f624f67cd11b` (2026-08-17) | `src/goodix_cmd.c`; `src/goodix_frame.c` | `GPL-2.0-or-later` (per-file SPDX verified at import) | `Copyright (C) 2026 liushicong (Rockytkg)` | `D249` | `ADAPTED_FROM_ROCKY` to Python and the local 12509 AF contract; fixed allowlist; USB chunks, lifecycle, retries, production writes, PSK, ClearApp and firmware paths excluded. |
| `core/post_d4.py` (FDT builders/events and mixed receive design portions) | `https://github.com/Rockytkg/goodix-linux-27c6-5125` | `227eba219fa9e3fbac5bd59aca79f624f67cd11b` (2026-08-17) | `src/goodix_capture.c` | `GPL-2.0-or-later` (per-file SPDX verified at import) | `Copyright (C) 2026 liushicong (Rockytkg)` | `D249` | `ADAPTED_FROM_ROCKY`; only framing/parsing above an abstract transport. Retry, TLS reconnect, baseline persistence, direct exposure debug bypass, USB/power lifecycle and automatic re-arming excluded. |
| `core/post_d4.py` (image codec adapter) | local project | `bc377c820fa661c889d61b17a4c81e42507fc78a` | `src/goodix5125_cleanroom.py` | Historical local implementation reused by the GPL core; `GPL-2.0-or-later` distribution is license-compatible | Goodix 27c6:5125 project contributors | `D249` | `LOCAL_EXISTING_REUSED`: direct delegation to the already validated exact 7684-byte codec, real CRC trailer order, 6-byte/4-sample unpack and target transpose; no Rocky decoder and no reimplementation. |
| `core/post_d4.py` (`FirstImageMachine`, typed failures and abstract `Transport`) | local project | D249 correction commit | `N/A — project-authored adapter` | `GPL-2.0-or-later` | Goodix 27c6:5125 project contributors | `D249` | `NEW_LOCAL_IMPLEMENTATION`: bounded offline composition of the locally evidenced/adapted facts; no USB/TLS backend, lifecycle, secret, retry, reconnect, persistence or live integration. |
| `libfprint-driver/goodix_d190_binder.[ch]` | local project history | `b475a6eca72e340816779afae917334a6146c986` | `poc/goodix5125/tools/binding_reference/crypto_reference.py`; `poc/goodix5125/tools/binding_reference/known_answers.py` | `BSD-2-Clause` at source revision; adapted destination distributed as `LGPL-2.1-or-later` with BSD notice/provenance preserved | Copyright (c) 2026 sorguido | `D278/02` | `ADAPTED_FROM_PROJECT_BSD`: bounded native OpenSSL 3 port of the D190 crypto reference. Five independent historical known-answer validators are fixed test evidence; no runtime oracle or second implementation. All project-owned secret intermediates are explicitly cleansed. |
| `tools/goodix_d190_pe.[ch]` | local project history | `b475a6eca72e340816779afae917334a6146c986` | `poc/goodix5125/tools/binding_reference/pe_parser.py`; `poc/goodix5125/tools/binding_reference/runtime.py` | `BSD-2-Clause` at source revision; adapted destination distributed as `GPL-2.0-or-later` with BSD notice/provenance preserved | Copyright (c) 2026 sorguido | `D278/02` | `ADAPTED_FROM_PROJECT_BSD`: bounded inert-byte PE parsing and producer-seed extraction only. The canonical DLL is hash-pinned and never loaded, executed, mapped executable or passed to Wine. |

### Externally verified Rockytkg baseline

The AI Supervisor verified the ledger baseline through authenticated GitHub
access outside this Codex workspace. At commit
`227eba219fa9e3fbac5bd59aca79f624f67cd11b` (observed commit date
2026-08-17), the repository `LICENSE` states that original project code is
GPL-2.0-or-later, `src/goodixgf.c` is LGPL-2.1-or-later, `libfprint/` retains
upstream third-party terms, and vendor firmware at
`firmware/st411sec_app.bin` or embedded in `include/goodix_fw.h` is outside the
project's open-source license. Sampled headers confirm GPL-2.0-or-later for
`src/goodix_capture.c`, `src/goodix_init.c`, and `src/goodix_tls.c`, and
LGPL-2.1-or-later for `src/goodixgf.c`. The repository-level copyright notice
names `liushicong (Rockytkg)`; this is not generalized to third-party work or
every historical contribution.

The Supervisor also verified issue #1: Rockytkg reports direct hardware
validation on a 12508 unit, not an unmodified 12509 unit. Therefore this
verified implementation source remains subordinate to local evidence for every
target-specific APP12509 claim. Per-file rights and SPDX validation remains a
future import-time gate, not a D247 blocker because D247 imports no functional
file.

## GPL/LGPL firewall

GPL-only expression must not be copied, translated or adapted into
`libfprint-driver/`. Crossing is permitted only when the particular code is
already compatibly dual-licensed, every relevant rights holder supplies a
compatible alternative license, or the LGPL implementation is independently
created from specifications, protocol facts, tests and evidence without
transferring GPL expression. Keep design/evidence records sufficient to audit
that separation.

## Publication boundary

```text
private repository = canonical development workspace
public repository  = frozen publication surface pending a separate audited export
```

A clean final working tree does not make private Git history safe to publish.
Before release, perform a separate audit of content and history for proprietary
binaries/firmware, captures, secrets and biometric/private data. Use a clean
export, new history or a purpose-built filter when needed; never automatically
push or expose the private history. D247 does not modify the public repository.

## D276/03 — componente router LGPL indipendente

`libfprint-driver/goodix_usb_router.[ch]` e i relativi test/launcher D276/03
sono nuovo codice di progetto `LGPL-2.1-or-later`. Sono stati implementati
indipendentemente dai fatti neutrali di framing e ownership canonizzati nel
manuale e in `analysis/D276/D276_01_libfprint_device_architecture.md`; durante
il slice non sono stati consultati, copiati, tradotti o adattati `core/`,
`tools/` o sorgenti Rockytkg GPL. Non è stato importato codice esterno. Le sole
dipendenze sono le API GLib pubbliche; transcript e payload sono sintetici,
senza secret, capture o biometria. L'etichetta clean-room descrive il controllo
ingegneristico di provenance e non costituisce una conclusione legale.

## D276/04 — TLS nativo e adapter FpiUsbTransfer LGPL

`libfprint-driver/goodix_tls_server.[ch]`, `goodix_fpi_usb_backend.[ch]` e i
relativi test sono nuovo codice indipendente `LGPL-2.1-or-later`. La scelta
OpenSSL usa esclusivamente le API pubbliche OpenSSL 3 (`SSL_CTX`, `SSL`, BIO di
memoria, callback PSK e `OPENSSL_cleanse`) e i fatti neutrali canonici TLS 1.2,
`PSK-AES128-GCM-SHA256`/`0x00a8` e identity `Client_identity`. Il backend usa
le API pubbliche della copia locale libfprint 1.94.5, anch'essa LGPL. Non sono
stati copiati o tradotti runtime GPL, Rockytkg driver code, secret o capture.
OpenSSL è una dipendenza build-time unica e dichiarata; non esistono fallback,
`dlopen`, subprocess, socket o helper.

### D276/04 corrective integration

Il correttivo estende gli stessi moduli LGPL indipendenti con state machine
application-data, adapter B0 neutrale, ownership nel `GoodixDeviceContext` e
pending-token generation per `FpiUsbTransfer`. Le fonti restano esclusivamente
i fatti canonici D242/D276, le API pubbliche OpenSSL 3 e gli header LGPL
libfprint 1.94.5. Non è stato consultato o trasferito codice GPL. `libgusb-dev`
serve soltanto al compile/API-shape probe host-only; nessun device viene aperto.

Il corrective post-merge D276/04 modifica soltanto questa espressione LGPL
indipendente: rende esplicito il token generation fornito dal context e aggiunge
fixture A0 sintetiche multi-activation. Non sono stati consultati, copiati o
tradotti `core/`, Rockytkg o implementazioni esterne; le fixture non contengono
secret reali né dati biometrici reali.

Il final corrective D276/04 aggiunge al medesimo backend LGPL API checked di
drain/begin-generation e una seam asincrona host-only. L'implementazione deriva
dal contratto pubblico `FpiUsbTransfer` della copia repository-local libfprint
1.94.5 e da fixture sintetiche; non incorpora espressione GPL, secret o dati
biometrici.

## D278/01 — secure-session nativa LGPL indipendente

`libfprint-driver/goodix_a0_protocol.[ch]`,
`libfprint-driver/goodix_secure_session.[ch]` e i test D278 sono nuova
espressione locale `LGPL-2.1-or-later`. Le fonti implementative sono soltanto i
fatti neutrali e i vettori canonici registrati in `docs/EVIDENCE.md`, D232,
D242/D243 e D245, le API pubbliche GLib/OpenSSL 3 e le API LGPL della copia
repository-local libfprint 1.94.5. Il serializer storico GPL è stato usato
unicamente come oracle black-box per confermare vettori/fatti già canonizzati;
non ne sono stati letti, copiati, adattati o tradotti gli algoritmi nel dominio
LGPL. Non è stato importato codice da `tools/d277_native_a8_once.c`, `src/`,
`core/` o Rockytkg.

Le fixture contengono soltanto validator, response body, CONFIG_90 e PSK
sintetici non factory e non biometrici. I pin target restano riferimenti
hash-only negli artefatti canonici; raw CONFIG_90, raw response target, capture
e secret autentici non sono incorporati. L'estensione del backend e del
`GoodixDeviceContext` preserva la stessa provenance D276/04 e aggiunge solo
single-OUT ownership, completion generation-captured e wiring della nuova
state machine.

## D278/02 — boundary materiali e harness live-capable

`libfprint-driver/goodix_target_material.[ch]` è nuova espressione locale
`LGPL-2.1-or-later`, costruita dai contratti hash/layout canonici D232/D245 e
dalle API POSIX/GLib/OpenSSL pubbliche. Il loader non incorpora materiale
autentico: applica policy produttiva fissa uid 0/mode 0600, `O_NOFOLLOW`,
controlli `fstat` pre/post lettura, lunghezze e hash esatti, finalizer/DAC,
binding E4 e ownership/cleanse espliciti. Le fixture sono interamente
sintetiche.

`tools/goodix_d278_harness.[ch]` e
`tools/d278_native_secure_session_once.c` sono `GPL-2.0-or-later`. Il binding
libfprint/GUsb live-capable riusa soltanto la meccanica API-shape GPL del tool
D277, resta fuori dal dominio LGPL e non è stato eseguito in D278/02. Il
percorso sintetico usa la stessa orchestrazione, la state machine LGPL reale e
un peer OpenSSL TLS 1.2 reale; non contiene una seconda implementazione del
protocollo. Nessun codice Rockytkg è stato importato.

## D278/12 — decoder immagine e lifecycle post-TLS LGPL indipendenti

`libfprint-driver/goodix_image_decoder.[ch]` e
`libfprint-driver/goodix_post_tls_lifecycle.[ch]` sono nuova espressione locale
`LGPL-2.1-or-later`. Le fonti implementative sono i fatti wire neutrali e i
vettori canonizzati nel manuale e nei report D249, D252–D275: framing payload,
marker image-specific `0x88`, record 7684-byte, CRC-32/MPEG-2, KAT packed-12,
mapping raster 80×64, ordine D4/AF/FDT/acquisizione/release/rearm e derivazioni
FDT target-specific. Il serializer GPL storico è stato usato soltanto come
oracle black-box per un KAT additivo già espresso come fatto di protocollo; non
ne è stato copiato, letto, tradotto o adattato l'algoritmo nel dominio LGPL.

L'integrazione modifica i moduli LGPL D276/D278 esistenti per un handoff
callback-driven del medesimo backend e per mantenere lo stesso oggetto TLS. Non
introduce helper, IPC, Python embedded, secondo TLS, secondo reader o nuovo
backend USB. Le fixture contengono soltanto immagini sintetiche deterministiche
e PSK sintetiche; non incorporano secret, capture o biometria reale. L'audit
step-local controlla sorgenti e simboli per riferimenti GPL, reset/clear-halt,
control transfer e provider TLS indipendenti. L'etichetta clean-room descrive
il controllo ingegneristico di provenance e non costituisce una conclusione
legale.

## D278/13 — binding operatore integrato

Le modifiche a `libfprint-driver/goodix_fpimage_device.[ch]` e ai test restano
`LGPL-2.1-or-later`. Sono plumbing e osservabilità dell'oggetto già esistente:
costruzione non registrata su un `GUsbDevice`, epoch bounded, callback di fase
e consegna dei due raster alla pipeline `FpImage` senza attraversare un'azione
framework fittizia. Le fonti sono le API pubbliche GLib/GObject/GUsb e libfprint
1.94.5, più l'architettura canonica D276/D278. Non è stata trasferita
espressione GPL nel dominio LGPL.

`tools/d278_integrated_path_once.c`, gli script build/operatore D278/13 e il
relativo glue sono `GPL-2.0-or-later`. Il wrapper di caricamento materiale
riapplica, nello stesso dominio GPL, la sequenza già project-owned di
`tools/goodix_d278_harness.c` (load → estrazione PE policy-gated → bind E4 →
view → cleanse), sostituendo l'harness runtime con il solo
`GoodixDeviceContext`. Il reader FDT12 read-only deriva dal contratto GPL
project-owned `core/fdt_seed.py` e dai fatti D255/D261: blob canonico 13.520
byte, SHA-256 esatto, CRC-32/MPEG-2 little-endian, OTP64 hash-bound e campo
FDT12 offset 64. La destinazione è esclusivamente tool GPL; non sono stati
copiati algoritmi o orchestration nel driver LGPL.

Il tool non implementa comandi A0/B0, TLS, FDT lifecycle, decoder o pipeline e
non collega il legacy `GoodixD278Harness`. Il build host-only usa stub
link-only libfprint per extractor fuori scope, ma il percorso bounded costruisce
soltanto il vero `FpImage`; non seleziona matcher o enrollment. La fixture usa
materiale e immagini sintetici. Il raw cache privato è soltanto un input
future-live hash-gated: D278/13 non lo legge, perché il gate ordinario termina
prima di cache, secret e USB. L'etichetta clean-room descrive il controllo
ingegneristico di provenance e non costituisce una conclusione legale.

Il correttivo D278/13 successivo alla review AI-PM della baseline
`8abab4a96075ef4057226ef0c5077f483a7636c0` modifica soltanto il dominio GPL:
adapter, launcher, build e test del guard. Il binding della baseline usa
esclusivamente Git e utility POSIX per verificare/esportare il sorgente locale;
il ticket one-shot usa API POSIX/GLib pubbliche e fixture sintetiche. Non entra
nuova espressione nel dominio LGPL, non viene importato codice esterno e non
sono aggiunti secret, capture o dati biometrici. Gli oggetti LGPL già accettati
e l'architettura con un solo context/backend/router/TLS/lifecycle restano
invariati.

## D279/03 — integrazione Fedora 44/libfprint 1.94.100

La registrazione `goodix_27c6_5125`, il wrapper GType, la tabella USB e il
riallineamento NBIS/ppmm modificano esclusivamente il codice locale
`LGPL-2.1-or-later` già tracciato in `libfprint-driver/`. I due file Meson nella
reference Fedora 44 usano le normali API di build/registry upstream e puntano
ai sorgenti canonici locali; nessun file driver upstream è stato copiato o
sovrascritto e nessuna espressione Rockytkg/SIGFM è stata trasferita.

Gli header e la metadata pkg-config sotto `tests/support/d279/` sono una seam
compile-only derivata dalle chiamate API pubbliche GUsb usate da libfprint
1.94.100 e collegano il runtime Fedora `libgusb.so.2`; non implementano GUsb e
non entrano nel prodotto. Test e report D279/03 contengono solo metadata di
build e fixture non biometriche, senza secret o capture.

## D279/04 — provider LGPL degli input runtime inerti

`libfprint-driver/goodix_runtime_inputs.[ch]` è distribuito come
`LGPL-2.1-or-later`. La porzione PE è un adattamento delimitato direttamente
dalla reference project-owned `BSD-2-Clause` al commit
`b475a6eca72e340816779afae917334a6146c986`, path
`poc/goodix5125/tools/binding_reference/pe_parser.py`, blob
`c2f6451308f1f0e78942c02b46daa3b85b061577`; copyright e provenance sono
preservati nel sorgente e in questo ledger. Non deriva dal successivo port C
GPL sotto `tools/`.

La porzione FDT è nuova espressione locale dal contratto neutrale già
canonizzato D255/D261: layout 13.520 byte, hash esatto, CRC-32/MPEG-2 con word
little-endian finale, OTP64 hash-bound e FDT12 all'offset 64. Non copia
orchestrazione, filesystem provider o reporting dal modulo GPL. Il nuovo
modulo accetta esclusivamente byte caller-owned e non offre API di file, USB,
discovery, mapping eseguibile, subprocess o scrittura. Le prove eseguite usano
soltanto fixture sintetiche; i pin autentici sono compilati ma nessun secret,
cache privata o seed autentico è stato letto durante D279/04.

## D279/05 — adapter file privati per gli input runtime

D279/05 estende la medesima espressione LGPL con un reader POSIX di due soli
path espliciti. Le fonti implementative sono API POSIX/GLib/OpenSSL pubbliche e
il pattern di ownership già espresso localmente in
`goodix_target_material.c`: regular file, uid/mode/size esatti,
`O_NOFOLLOW|O_CLOEXEC`, identità e metadata `fstat` pre/post, cleanup e
pubblicazione atomica. Non viene importata espressione GPL e non vengono
aggiunti discovery, fallback, path production hard-coded, USB o write. Test e
sanitizer usano esclusivamente file sintetici temporanei mode 0600.
