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

## D278/02 — D190 binder e parser PE

La determinazione di engineering provenance AI-PM, eseguita read-only sul
repository canonico completo, ha verificato il commit storico
`b475a6eca72e340816779afae917334a6146c986`, il `LICENSE` BSD-2-Clause blob
`42fd7050a89d195cacb4b002f91a2f679a8b5285` (Copyright (c) 2026 sorguido) e
gli esatti blob D190: `crypto_reference.py` `98c45c87c91b5d3e64e003788df31b5c3d8fb12e`,
`pe_parser.py` `c2f6451308f1f0e78942c02b46daa3b85b061577`, `runtime.py`
`9e6643e7c77fcc53947b87cca22ef9eb565fb95c` e `known_answers.py`
`eb804cc713f90f9b0ba0d5bcbb9516b5525e76a5`. Il clone Cloud shallow non
contiene quell'oggetto; questa è una determinazione di provenance ingegneristica
del progetto, non una conclusione legale generale.

| LOCAL_PATH | SOURCE_REPO | SOURCE_COMMIT | SOURCE_PATH | LICENSE | COPYRIGHT | IMPORT_STEP | NOTES |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `libfprint-driver/goodix_d190_binder.[ch]` | `sorguido/goodix-27c6-5125-private` | `b475a6eca72e340816779afae917334a6146c986` | `poc/goodix5125/tools/binding_reference/crypto_reference.py` | `BSD-2-Clause` | Copyright (c) 2026 sorguido | `D278/02` | Adapted to C/OpenSSL under LGPL-2.1-or-later; only `secret32 + seed[6]x2 -> validator32`; Python runtime and PE architecture excluded. |
| `tools/goodix_d190_pe.[ch]` | `sorguido/goodix-27c6-5125-private` | `b475a6eca72e340816779afae917334a6146c986` | `poc/goodix5125/tools/binding_reference/pe_parser.py` | `BSD-2-Clause` | Copyright (c) 2026 sorguido | `D278/02` | Tool-only GPL adaptation; bounded read-only canonical-hash PE parsing, never loading/executing the DLL. |
