<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Licensing and provenance

## Directory map

| Scope | Default for new project-authored work | Rule |
| --- | --- | --- |
| `core/` | `GPL-2.0-or-later` | Userspace transport, protocol, TLS, FDT, capture and image code. |
| `tools/` | `GPL-2.0-or-later` | Tools connected to or derived from the GPL core. |
| `libfprint-driver/` | Per-file; `LGPL-2.1-or-later` default for new local work | Existing LGPL files remain LGPL. GPL-compatible production components may be added without relicensing them; distribution of the resulting fork/combined work must satisfy every applicable license. |
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
Rockytkg = primary implementation reference for the SIGFM path
direct reuse/minimal adaptation preferred when per-file licenses,
attribution, provenance and resulting-distribution compatibility permit it
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
| `libfprint-driver/rockytkg-imgproc/goodix_imgproc.[ch]` | Rockytkg preserved snapshot | `227eba219fa9e3fbac5bd59aca79f624f67cd11b` | `Rockytkg/src/goodix_imgproc.c`; `Rockytkg/include/goodix_imgproc.h` | `GPL-2.0-or-later`; destination files retain GPL terms | Rockytkg; per-file notices preserved | `D279/49` | `ADAPTED_FROM_ROCKY`: direct algorithm reuse with the full sensor-reaching `goodix_dev`, environment overrides and debug/file dump surface removed. Pure frame view only; fixed R1/R2 parameter definitions and algorithm stages retained. KAT matches D279/48 R2 byte output. |
| `libfprint-driver/goodix_sigfm_metrics.cpp` production SIGFM dependency | Rockytkg materialized libfprint submodule | `7ebe0c809b4d1df3400e84299a4ec4acdea84590` | `Rockytkg/libfprint/libfprint/sigfm/{sigfm.cpp,sigfm.h,binary.hpp,img-info.hpp}` | source and local wrapper are `LGPL-2.1-or-later`; OpenCV Fedora terms remain separately applicable | Matthieu Charette, Natasha England-Elbro, Timur Mangliev; local wrapper project authorship | `D279/50` | `INTEGRATES_ROCKY`: extraction, match, copy and native payload serialization are compiled directly from the preserved source. Local `GSF1` wrapper adds ABI marker, exact structural bounds, finite-value checks, CRC and canonical round-trip before deserialization; it does not reimplement SIGFM. |
| `reference/libfprint-fedora44-1.94.100/source/libfprint/{fp-print.c,fpi-print.c,fpi-print.h}` SIGFM branches | Rockytkg materialized libfprint submodule, semantically forward-ported onto the preserved Fedora 44/libfprint 1.94.100 target | `7ebe0c809b4d1df3400e84299a4ec4acdea84590` | `Rockytkg/libfprint/libfprint/{fp-print.c,fpi-print.c,fpi-print.h}` | source and destination are `LGPL-2.1-or-later` | Original libfprint holders plus the Rockytkg materialized fork contributors identified by the source notices; local adaptation project authorship | `D279/51`; checked append corrective `D279/52` | `ADAPTED_FROM_ROCKY`: retains the SIGFM private print type, multi-sample template and score-dispatch semantics. Replaces raw `SigfmImgInfo` copy/storage with the D279/50 owned wrapper, strict `GSF1` envelopes, 1..21 sample bounds, canonical equality, exception/error propagation and fail-closed parsing; D279/52 makes append atomic and error-reporting before stage advancement; preserves the newer 1.94.100 NBIS path. |
| `reference/libfprint-fedora44-1.94.100/source/libfprint/{fp-image.c,fp-image-device.c,fpi-image-device.c,fpi-image.h,fpi-image-device.h,fp-image-device-private.h}` and bounded Meson delta | Rockytkg materialized libfprint submodule, semantically forward-ported onto Fedora 44/libfprint 1.94.100; local R2/ownership wrappers | `7ebe0c809b4d1df3400e84299a4ec4acdea84590`; local D279/49–50 | `Rockytkg/libfprint/libfprint/{fp-image.c,fp-image-device.c,fpi-image-device.c,fpi-image.h,fpi-image-device.h,fp-image-device-private.h}` | upstream/action and SIGFM sources `LGPL-2.1-or-later`; the linked R2 component remains `GPL-2.0-or-later`, making the Goodix-enabled combined build GPL-compatible | Original libfprint/Rockytkg holders plus local adaptation authorship | `D279/52` | `ADAPTED_FROM_ROCKY`: algorithm dispatch and asynchronous SIGFM extraction are forward-ported without replacing the newer 1.94.100 state machine. Local changes add decoded session-baseline → R2 wiring, checked atomic template append, fatal error propagation and production Meson/OpenCV closure. The upstream Fedora snapshot's historical provenance and license facts are unchanged. |
| `reference/libfprint-fedora44-1.94.100/source/libfprint/fpi-device.c` SIGFM identify-report branch | Preserved Fedora 44/libfprint 1.94.100 core plus local SIGFM type semantics | Fedora source archive digest recorded in the reference provenance; local D279/51 | `source/libfprint/fpi-device.c`; no direct equivalent in the older Rockytkg tree | `LGPL-2.1-or-later` | Original libfprint holders; local adaptation project authorship | `D279/53` | `LOCAL_FEDORA_CORE_ADAPTATION`: extends the existing NBIS exemption from byte-equality validation to the matcher-backed SIGFM scanned print. Rockytkg 1.94.5 lacks this newer validation, so no Rockytkg expression was imported. Historical upstream provenance and licensing facts remain unchanged. |
| `libfprint-driver/goodix_post_tls_lifecycle.[ch]` and production action selection in `goodix_fpimage_device.c` | Local implementation over target-observed D279/54 protocol facts; Rockytkg is architectural corroboration only | D279/54 ATTEMPT01 hashes recorded in its audit/report; local D279/55 | No Rockytkg driver expression imported | `LGPL-2.1-or-later` per existing destination files | Local project authorship | `D279/55` | `LOCAL_TARGET_EVIDENCE_ADAPTATION`: adds an explicit single-acquisition profile, NAV-before-STOP terminal and production identify allowlist. Enrollment remains separate. Facts from the OEM transcript are not copyrightable expression; Rockytkg wire identity is not claimed. |
| `analysis/D279/d279_56_dynamic_enrollment_policy.py`, `d279_56_r2_pipe.c` and `operator_kit/d279-56-offline-protected-dynamic-enrollment/` | Preserved Rockytkg enrollment policy plus local D279/49 production R2 component | `227eba219fa9e3fbac5bd59aca79f624f67cd11b`; `Rockytkg/src/goodixgf.c` SHA-256 `cb2fffe7...b4fbacd` | `Rockytkg/src/goodixgf.c`; local production preprocessing API | `GPL-2.0-or-later` | Rockytkg and local adaptation authorship | `D279/56` | `ADAPTED_FROM_ROCKY`: exact default 3/8/2/MAD<8 policy is replayed offline on in-memory R2 primary rasters. The adapter has no USB/device API and exports classifications/counts only. This experiment does not import Rockytkg wire lifecycle into production. |
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

## Per-file licensing and GPL-compatible combined work

The historical directory split is not a mandatory LGPL-only architecture.
Existing LGPL files keep their LGPL grant; GPL-only files keep GPL terms even
when used by the Goodix libfprint production path or placed next to LGPL files.
A Goodix fork or combined work may be distributed under GPL-compatible terms
when legally possible, provided that every per-file license, copyright notice,
source obligation and attribution requirement is preserved.

Do not describe GPL material as LGPL merely because of its destination, and do
not relicense third-party files without authority. Before direct reuse, record
the exact source commit/path and determine the distribution regime of the
resulting set. Independent LGPL implementation is a fallback only for a
concrete licensing or integration blocker, not the default response to a GPL
source file.

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

## D279/06 — owner materiali della open epoch

`libfprint-driver/goodix_runtime_material.[ch]` è nuova espressione locale
`LGPL-2.1-or-later` che compone esclusivamente le API LGPL D278/02 e D279/04–05.
Non contiene protocollo, USB, path predefiniti o algoritmi provenienti dal glue
GPL. Le view secure sono descrittori non-owning del singolo
`GoodixTargetMaterial`; il teardown cancella descriptor/FDT e delega al loader
esistente il cleanse di PSK, validator e CONFIG90. Il test usa cinque file
sintetici temporanei e un validator calcolato dal binder LGPL già verificato;
nessun input autentico viene letto.

## D279/48 — confronto host-only Rockytkg / NBIS / SIGFM

`analysis/D279/d279_48_rocky_imgproc_pipe.c`, il relativo header, evaluator,
operator kit e report sono nel dominio `GPL-2.0-or-later`. Il binario
preprocessor compila direttamente i file
GPL `Rockytkg/src/goodix_imgproc.c` e
`Rockytkg/include/goodix_imgproc.h` dal commit preservato
`227eba219fa9e3fbac5bd59aca79f624f67cd11b`. In D279/48 la destinazione resta
un processo host-only dell'esperimento protetto. La decisione post-run autorizza
per il successivo percorso production il riuso diretto dello stesso componente
GPL in una fork/combined work GPL-compatible, dopo audit per-file e ledger;
D279/48 in sé non aveva ancora effettuato tale import.

`libfprint-driver/tests/test_goodix_nbis_pair_pipe.c` è un target test-only
non installato `LGPL-2.1-or-later`. La conversione minutiae→XYT è tratta dal
file LGPL `reference/libfprint-fedora44-1.94.100/source/libfprint/fpi-print.c`
della reference Fedora 44 pinned; il resto è adapter locale per le API NBIS e
Bozorth dello stesso tree. La destinazione resta test/comparator, non modifica
il driver.

`libfprint-driver/tests/test_goodix_sigfm_pair_pipe.cpp` è adapter test-only
`LGPL-2.1-or-later`. Collega direttamente l'implementazione SIGFM del fork
libfprint materializzato, commit
`7ebe0c809b4d1df3400e84299a4ec4acdea84590`, conservandone copyright e licenza
LGPL-2.1-or-later, e gli RPM Fedora OpenCV 4.13.0 soggetti alle rispettive
licenze di pacchetto. Descriptor e template restano soltanto in memoria del
processo e non vengono esportati.

Il confronto non importa `goodixgf.c`, lifecycle, protocollo, USB, firmware,
PSK provisioning o scritture persistenti Rocky. I fatti osservati nello
snapshot sono corroborativi e non vengono elevati a prova APP12509. Un futuro
uso production continua a richiedere audit/ledger per-file; la decisione
architetturale post-D279/48 ha però già scelto massimo riuso diretto Rockytkg e
una distribuzione GPL-compatible quando necessaria.
