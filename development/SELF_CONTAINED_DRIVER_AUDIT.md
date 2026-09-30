<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix 27c6:5125 self-contained driver architecture audit

## Scope, evidence rules, and recommendation

This is an architecture and gap-analysis report. It makes no driver, installer,
material-contract, USB, firmware, or host integration change. It was prepared
from repository state `1c970631d751cb98572230aba296c23cb5027575` on branch
`development`, the current source and tests, the qualified PSK PoC, and the
project-local Rockytkg snapshot pinned to commit
`227eba219fa9e3fbac5bd59aca79f624f67cd11b`.

Evidence terms have their repository meanings:

- **OBSERVED**: directly present in current code, tests, captures, or qualified
  result records.
- **PROVEN**: supported by a qualifying test or experiment for APP12509.
- **INFERRED**: the evidence supports the conclusion, but the exact proposed
  production path has not yet been qualified.
- **ASSUMED**: a design premise that must not become a production gate without
  evidence.
- **UNKNOWN**: evidence needed for a safe decision is absent.

The Rockytkg snapshot is a source-level comparator, not target-specific proof.
Its firmware update/IAP path, dummy `BB010002`, retry policy, and automatic
persistent-write behavior are explicitly excluded.

## A. Executive conclusion

**Yes, `git clone -> ./install.sh -> enroll` is technically realistic, with three
qualification conditions.** The normal installation can be completely free of
Windows, USBPcap, DPAPI recovery, `gfusb.dll`, and a user-supplied five-file
bundle. Hardware initialization should happen automatically on the first
libfprint activation under stock Fedora `fprintd`, not in `install.sh`.

The recommended architecture is:

1. retain the current exact `27c6:5125` and
   `GF_ST411SEC_APP_12509` fail-closed gates;
2. derive the 224-byte CONFIG90 from a qualified type-12 target template plus
   live OTP patches;
3. generate a 32-byte Linux PSK from the OS CSPRNG and durably journal it
   **before** the one permitted `E0`;
4. preserve the reader's current real `BB010002` verbatim in the `E0`, rather
   than synthesizing a Rockytkg dummy value;
5. derive `BB010003` and its `BB020003` validator in project code, then require
   the already-qualified ACK, readback/hash, and TLS 1.2 proof;
6. bootstrap FDT with a no-finger live sample, retain at most the small learned
   table needed for restart, and continue acquiring the image baseline fresh as
   the current driver does;
7. replace the external manifest with versioned, root-only internal state bound
   to APP identity, chip profile, and OTP digest;
8. reuse the same Linux PSK on ordinary Linux reopen and after a Windows return.
   Reprovision only after a read-only `BB020003` comparison proves that the
   reader no longer holds the Linux pairing.

Three blockers remain before implementation may reach a sensor:

- **CONFIG90 qualification**: the type-12 template plus OTP patch algorithm
  must reproduce the current qualified CONFIG90 byte-for-byte (or every
  difference must be explained and independently qualified).
- **zero-seed first-run FDT qualification**: current code consumes a nonzero
  12-byte seed, while Rockytkg starts FDT-manual learning from zero. The proposed
  zero-seed/no-finger bootstrap is source-supported but not yet PROVEN on the
  project's production path.
- **general `BB010002` acceptance**: the qualified writer preserved one exact
  332-byte OEM value. A future driver must qualify a narrow structural parser
  across legitimate Windows pairings; absent or malformed values remain
  unsupported because the Rockytkg dummy is not Windows-qualified.

The PSK writer itself is no longer the architectural blocker. The repository
records one logical `E0`, qualified response, unchanged `BB010002`, matching
`BB020003`, and successful TLS 1.2 PSK handshake in
`development/psk/README.md:51-104`.

## B. Current bundle dependency matrix

### End-to-end acquisition, validation, import, and runtime path

The Windows builder creates all five files in
`tools/windows_material_builder/backend.py:build` and publishes exactly that set
in `backend.py:publish` (`71-145`). Its inputs are `Goodix_Cache.bin`,
`goodix.dat`, `gfusb.dll`, and captured USB evidence. The capture parser selects
one CONFIG90 OUT and A2, chip-82, A6, and APP identity IN evidence in
`tools/windows_material_builder/capture.py:analyze_bytes` (`150-280`).

The Linux installer validates the set with
`deployment/materials.py:validate_bundle` (`168-215`), revalidates it with the
native USB-free `deployment/check-material.c`, and atomically imports root-owned
`0700/0600` files with `deployment/materials.py:install_materials` (`240-290`).
`deployment/install.py:select_materials` and `apply` (`340-432`) require the
bundle on first installation and preserve an identical installed set on update.

At runtime `libfprint-driver/goodix_runtime_material.c` fixes the five paths
under `/var/lib/goodix-5125-poc` (`50-62`).
`goodix_runtime_material_load` (`127-216`) calls the target loader, extracts the
DLL and FDT inputs, binds them, and exposes a `GoodixSecureSessionMaterial` plus
12-byte FDT seed. `libfprint-driver/goodix_fpimage_device.c` acquires that
material in `acquire_default_material` (`949-976`), passes the secure fields to
the pre-TLS state machine, and passes the FDT seed into the post-TLS lifecycle.

| Current file | Created from / producer | Validation and import | Actual runtime layout and consumer | Classification and necessity |
| --- | --- | --- | --- | --- |
| `target-material-manifest.json` | `backend.py:build` creates schema/identity, three file hashes, and hashes of captured A2, chip-82, and A6 responses (`101-108`). | `materials.py:parse_manifest`, `validate_bytes`, `validate_bundle`; native `goodix_target_material.c:parse_manifest` (`297-382`). | Ten exact string fields. `goodix_target_material_load` uses file hashes, fixed VID/PID/APP, and the three response hashes. The latter enter `GoodixSecureSessionMaterial`; `goodix_secure_session.c:validate_material` and typed-response handling compare live responses with them. | Mixed: fixed target identity is `HARDCODED_TARGET_CONSTANT`; file hashes are qualification/integrity metadata; A6 is reader-specific; chip-82 selects a sensor profile; stability of the full A2 and chip-82 response across readers is **UNKNOWN**. The external file is not protocol-required, but equivalent internal binding and corruption detection are required. |
| `transport-material.bin` | `backend.py:build` recovers a 32-byte PSK with `windows.py:recover_dpapi`, derives a validator with `binding._bind_validator`, and emits the 88-byte record with `binding._build_poc`. | Exact size/header/hash checked by `materials.py:validate_bytes`; native load in `goodix_target_material.c:goodix_target_material_load` (`467-504`); DLL-derived rebinding in `goodix_target_material_bind` (`568-610`). | `[0:24]` fixed header, `[24:56]` PSK, `[56:88]` validator. PSK configures the TLS server; validator is the expected E4/`BB020003` value. `goodix_secure_session.c` uses both. | PSK is `LOCAL_PERSISTENT_STATE`; validator is derivable from the PSK and target WB algorithm. Both are live-protocol inputs today, but neither needs to be a user-provided file. |
| `target-config-90.bin` | One 224-byte CONFIG90 OUT selected from the Windows USB capture by `capture.py:config_valid/analyze_bytes`; copied by `backend.py:build`. | Exact hash, finalizer, register layout, and four DAC correlations checked by `materials.py:validate_bytes` and `goodix_target_material.c:config_finalizer_valid/config_correlations_valid` (`385-420`, `506-539`). | Exactly 224 bytes. Sent as the 0x90 body by `goodix_secure_session.c:build_phase_frame`; four two-byte DAC values at offsets 119, 123, 127, and 131 are also used as later register-write values. | Type-12 base is a firmware/sensor-profile constant; DAC and other calibration fields are OTP-derived. It is protocol-required but can plausibly be generated as template + OTP patch. |
| `gfusb.dll` | The qualified OEM DLL is copied unchanged by `backend.py`. | Exact size 5,771,496 and SHA-256, PE layout, RVAs, and unique instruction checked in `materials.py:validate_pe`, `backend.py:validate_sources`, and `goodix_runtime_inputs.c`. | It is never loaded or executed. `goodix_runtime_extract_producer_seeds` reads seed A (6 bytes at RVA `0x56f030`) and seed B (4+2 bytes from the instruction at RVA `0x69d0`), after the exact SHA-256 pin. `goodix_d190_bind_validator` consumes only those 12 bytes. | The DLL is qualification/provenance scaffolding around two target constants. It is not a live-protocol input and can be eliminated after direct-WB differential tests replace the DLL pin. |
| `fdt-cache.bin` | Windows `goodix.dat` is copied unchanged by `backend.py`. | Exact size 13,520, full hash, CRC-32/MPEG-2, first-64-byte OTP hash, and nonzero seed checked in `materials.py` and `goodix_runtime_inputs.c:goodix_runtime_extract_fdt_seed` (`347-420`). | Layout is `[OTP 64][FDT table 12][navigation baseline 3200][image baseline 10240][CRC 4]`. Runtime copies only `[64:76]` into the first post-TLS 0x36. The entire file and OTP prefix participate in integrity/binding checks; the navigation and image baselines are not otherwise consumed. | OTP is `DERIVED_FROM_LIVE_USB`; the 12-byte table is `LEARNED_BASELINE`; navigation data is unused; the current driver learns fresh FDT and image baselines during each action. The external file can be eliminated after first-run zero-seed learning is qualified. |

### What is reader-specific, firmware-specific, or merely qualification data

| Value | Current source | Classification | Runtime role |
| --- | --- | --- | --- |
| VID:PID `27c6:5125` | Manifest/header/code | `HARDCODED_TARGET_CONSTANT` | Exact device gate. |
| APP string `GF_ST411SEC_APP_12509` | Manifest/captured A8/code | `DERIVED_FROM_FIRMWARE_ID` checked against a hardcoded allow-list of one | Mandatory no-flash firmware gate. |
| 32-byte PSK | Windows DPAPI cache | `LOCAL_PERSISTENT_STATE` | TLS identity and PSK. Reader-specific only because reader state currently holds its WB envelope. |
| E4 validator | DLL algorithm + PSK | Derived value, currently stored | Read-only pairing equality proof. It is not an independent secret. |
| CONFIG90 template bytes | Windows capture | `HARDCODED_TARGET_CONSTANT` for the qualified sensor profile, subject to differential qualification | Sensor configuration. |
| CONFIG90 calibration fields | Captured target CONFIG90 | `DERIVED_FROM_OTP` | DAC/tcode/delta/offset values and finalizer. |
| Full A2 response hash | Windows capture | `DERIVED_FROM_LIVE_USB`; cross-reader stability `UNKNOWN` | Current exact typed-response pin. |
| Full chip-82 response hash | Windows capture | `DERIVED_FROM_LIVE_USB` | Sensor type/profile gate; full-response stability remains to qualify. |
| Full A6 response/OTP hash | Windows capture and `goodix.dat` | `DERIVED_FROM_LIVE_USB` and reader binding | Config derivation and physical-reader identity. |
| DLL full-file hash and PE structure | OEM file | Qualification/provenance only | Guards extraction of 12 constant bytes; no protocol consumer. |
| FDT full-file hash/CRC | Windows cache | Integrity/provenance only | Protects the 12-byte seed and OTP binding. |
| Navigation/image baseline in cache | Windows cache | `NOT_EQUIVALENT` to current runtime need | No direct consumer in the current driver. |

## C. Rockytkg comparison matrix

The comparator below uses the preserved snapshot's source, whose provenance and
license map are recorded in
`development/Rockytkg/snapshot/PROVENANCE.md:27-36,50-85`.

| Dependency/result | Current project source/function | Rockytkg source/function | Rockytkg algorithm, inputs, output, persistence | Classification | Risk / Windows compatibility conclusion |
| --- | --- | --- | --- | --- | --- |
| Target and firmware identity | Manifest plus `goodix_secure_session` A8 pin | `goodix_init.c:evk_with_retry`, `init_mcu`; transport target matching | Reads version live, with several resets/retries; also invokes firmware update. | `DERIVED_FROM_FIRMWARE_ID` | Reuse only the live read concept. Retain exact APP fail-closed behavior and exclude all firmware/IAP/reset escalation not already qualified. |
| PSK generation | Windows DPAPI recovery in `backend.py:build` | `goodix_init.c:init_mcu` (`305-382`) | Loads local PSK, compares MCU hash, otherwise reads/decrypts MCU WB or generates 32 random bytes and writes/persists. | `GENERATED_RANDOMLY` + `LOCAL_PERSISTENT_STATE` | The high-level model is valid. Rockytkg's MCU WB read is not qualified here, and its retries/dummy `BB010002` violate project gates. Use the qualified single-write PoC instead. |
| WB envelope / E4 validator | DLL seeds -> `goodix_d190_bind_validator` | `goodix_psk.c:gx_wb_encrypt`, `gx_psk_host_hash`, `gx_psk_verify_mcu_hash` | Fixed KDF key/AAD, SHA-256-derived IV, AES-256-GCM, HMAC envelope; validator is SHA-256 of the 102-byte WB envelope. | `HARDCODED_TARGET_CONSTANT` + deterministic derivation | `gx_wb_encrypt` is PROVEN byte-for-byte against OEM APP12509 material, and the PoC proves its hash against E4. Reimplement/refactor under controlled provenance; do not copy GPL expression into an LGPL file without respecting the resulting license. |
| `BB010002` | Recovered Windows DPAPI blob; qualified writer preserves it | `goodix_psk.c:gx_psk_write_to_mcu` (`234-283`) | Synthesizes 64 bytes of `0x5a` plus deterministic 8-byte pseudo-entropy. | `NOT_EQUIVALENT` | Explicitly reject. Preserve the current live value unchanged. This is the only currently qualified Windows-compatible write shape. |
| CONFIG90 | Captured `target-config-90.bin` | `goodix_init.c:gf_config_type12`, `gf_sensor_by_chipid`, `init_fpsensor`; `goodix_otp.c:gx_otp_patch_config` | Reads chip ID and 64-byte OTP, chooses the 224-byte type-12 template for `0x2503/0x2504`, patches DAC/tcode/delta/offset fields, recomputes finalizer, sends 0x90. | `HARDCODED_TARGET_CONSTANT` + `DERIVED_FROM_OTP` + `DERIVED_FROM_LIVE_USB` | Best candidate is template + OTP patch. It must first be differentially compared to the current captured target CONFIG90. Unknown chip/profile is fail-closed. |
| OTP binding | Manifest A6 hash + first 64 cache bytes | `goodix_init.c:cmd_read_otp`; `goodix_base.c:gx_base_load` | Reads A6 live; requires persisted `goodix.dat` OTP bytes to match exactly. | `DERIVED_FROM_LIVE_USB` | Use a digest as stable reader identity and read OTP live for config. No OTP write is needed or permitted. |
| FDT seed/table | 12 bytes from `fdt-cache.bin` | `goodix_capture.c:gx_fdt_sample_base` (`539-600`) | First request may carry an all-zero table; up to three no-finger samples learn a 12-byte base. | `LEARNED_BASELINE` | Source-supported, but the zero-seed production path needs bounded APP12509 live qualification. Finger/touch evidence must abort or invalidate the attempt. |
| Image baseline | Current post-TLS fresh action baseline; cache portion unused | `goodix_capture.c:gx_capture_base_image` (`632-649`) | Captures a no-finger 10,240-byte image and persists it. Rebuilds on temperature drift (`770-820`). | `LEARNED_BASELINE` | Not equivalent lifecycle. Prefer the current fresher per-action acquisition; do not add persistent images unless evidence shows a need. |
| Baseline persistence | External Windows `goodix.dat`; only seed consumed | `goodix_base.c:gx_base_load/gx_base_save` (`137-252`) | Root-private 13,520-byte `goodix.dat`, CRC and full OTP binding. | `LOCAL_PERSISTENT_STATE` | A compatible full layout is unnecessary. Persist only the minimum 12-byte learned seed if first-start latency/reliability needs it, with schema/profile/OTP binding. |
| Manifest/receipt | External ten-field JSON | No equivalent central receipt; separate `psk.bin` and `goodix.dat` | File mode and content checks are distributed. | `NOT_EQUIVALENT` | Keep the stronger project design as an internal versioned receipt/journal. |

Rockytkg therefore proves feasibility, not production acceptability. The project
can reuse three concepts—live OTP derivation, locally generated PSK, and learned
FDT—but must use its own bounded state machine and existing qualified protocol
gates.

## D. Material elimination plan

| Material | Final action | Replacement | Preconditions |
| --- | --- | --- | --- |
| `target-material-manifest.json` | **ELIMINATE** as a user input; **GENERATE/PERSIST** an internal v2 receipt | Versioned state with target, firmware, chip profile, OTP digest, config derivation version/hash, pairing generation/status, expected E4 hash, FDT state, and integrity metadata. | State parser, atomic update, migration, corruption and downgrade tests. |
| `transport-material.bin` | **ELIMINATE** as a bundle file; **GENERATE/PERSIST** PSK state | OS CSPRNG 32-byte PSK, direct WB/hash derivation, root-only journal. | Direct-WB KATs and crash-safe single-E0 coordinator. |
| `target-config-90.bin` | **DERIVE** at runtime | Qualified type-12 template selected by live chip response, patched from live OTP, finalizer recomputed. | Byte-level differential proof and later gated live CONFIG90 qualification. |
| `gfusb.dll` | **ELIMINATE** | Project-owned WB derivation using fixed APP12509 KDF/AAD constants and the already-known algorithm. | Match all existing D190/OEM KATs and E4 results; licensing/provenance review. |
| `fdt-cache.bin` | **LEARN**, optionally **PERSIST** only 12-byte FDT state | Zero-seed FDT-manual no-finger bootstrap, current fresh per-action baseline path. | First-run zero-seed qualification and bounded finger-present failure behavior. |

### Transport material and local PSK decision

`transport-material.bin` can be eliminated. The future driver should generate a
PSK only when a qualified reader has no usable local state, or local state is
irrecoverably missing/corrupt. For an ordinary return from Windows, it should
prefer the existing Linux PSK and rewrite that same pairing once; generating
`L2`, `L3`, and so on gives no interoperability benefit and complicates crash
recovery.

Recommended storage:

- root-owned directory `/var/lib/goodix-5125/state-v2/`, mode `0700`, labelled
  for the stock `fprintd` domain;
- one subdirectory keyed by a non-secret reader identifier derived from exact
  VID/PID, APP, accepted chip response/profile, and SHA-256 of the live 64-byte
  OTP; never select state by VID/PID alone;
- PSK and transaction state in regular, non-linked files mode `0600`, opened
  with `O_NOFOLLOW`, bounded sizes, pre/post metadata checks, cleansed scratch
  buffers, atomic replace, file `fsync`, and parent-directory `fsync`;
- a versioned non-secret receipt recording `PREPARED` or `ACTIVE`, generation,
  expected `BB020003`, prior generation where applicable, config profile/hash,
  FDT state version, and reader binding.

The secret must be durably journaled in `PREPARED` state **before** sending E0.
Persisting only after TLS, as in the conceptual prompt diagram, leaves no
deterministic recovery after `E0 succeeds -> host crashes`. After hash and TLS
proof the state is atomically promoted to `ACTIVE`.

#### Persistence alternatives

| Option | Boot/service availability | Security gain and failure modes | Decision |
| --- | --- | --- | --- |
| Root-only `0600` file | Available to system `fprintd` before login; simple SELinux labeling; backup can be explicit | Root can read it, but root can already replace the driver and intercept the key. Disk encryption remains the meaningful at-rest boundary. Atomic recovery is straightforward. | **Recommended now**. |
| Kernel keyring | Not durable across reboot without another persistent source; service/keyring lifetime and namespace are fragile | Reduces file exposure only while recreating the original persistence problem. | Reject as primary store. It may cache the key in memory. |
| Desktop/system secret service | Usually tied to a user session and login unlock; awkward for root `fprintd`, PAM login, and multiple users | Creates availability and circular-login failures with little gain. | Reject. |
| Encrypted local file | Requires an independent boot-available key; storing that key beside the file is security theatre | TPM/systemd credential integration adds recovery, hardware, and update complexity. | Defer as an optional future backend, not a launch blocker. |

The direct validator replacement should produce the 102-byte APP12509 WB
envelope and `SHA256(envelope)`. Current project code already implements the
same envelope chain in `goodix_action_binding.c:goodix_d190_bind_validator`
(`261-388`); the DLL contributes only the producer-key seed. The replacement
should be a small, independently testable module, derived by refactoring current
project code or by a clean implementation of documented protocol facts. Its
constants are the APP12509 WB producer/KDF key (or equivalently the two
qualified six-byte producer seeds plus their derivation), fixed 16-byte GCM
AAD, KDF label/counters, envelope header `02 ff 20 00 00 00`, and envelope
layout. None is the per-host PSK.

Tests replacing the DLL SHA-256 pin must include:

1. the existing five non-circular D190 OEM oracle KATs;
2. byte-for-byte `gx_wb_encrypt`/OEM `BB010003` equivalence already qualified;
3. validator equality with captured `BB020003` values;
4. deterministic envelope/validator tests for boundary and random PSKs;
5. negative tests for changed key, AAD, header, IV derivation, tag, and HMAC;
6. the qualified PoC's post-write hash and TLS proof as the later live gate.

### CONFIG90 conclusion

CONFIG90 is a 224-byte command-0x90 sensor configuration, not an opaque secret.
The best-supported choice is **C: target template + reader-specific OTP patch**.
Rockytkg maps chip IDs `0x2503/0x2504` to type 12 and its 224-byte
`gf_config_type12` (`goodix_init.c:74-89,107-132`).
`goodix_otp.c:gx_otp_patch_config` patches:

- registers `0x0220`, `0x0236`, `0x0238`, `0x023a` from OTP DAC values—the
  same register layout the current loader checks at byte offsets
  117/121/125/129;
- `0x005c` tcode, `0x0082` FDT delta, and `0x0056` offset from parsed OTP;
- the two-byte finalizer so the 112 little-endian words plus `0xa5a5` sum to
  zero.

This is strong source-level evidence, and the matching DAC layout is current
code evidence. It is not yet proof that every nonpatched template byte is the
qualified APP12509 value. The first milestone must therefore run an offline
differential over every available legitimate bundle:

```text
live/cached A6 OTP + accepted chip profile
    -> proposed generator
    -> exact 224-byte comparison with captured target-config-90.bin
```

Any difference must be explained by a named patch field or treated as a
blocker. Learning a whole CONFIG90 once (option D) is acceptable only as a
migration fallback; it does not meet the net-new self-contained goal. A fully
hardcoded configuration (A) is rejected because current and Rockytkg evidence
both show reader calibration fields. An OEM source requirement (E) is not yet
supported by the evidence.

### FDT cache conclusion

The exact current cache layout is:

| Offset | Length | Meaning | Current runtime use |
| ---: | ---: | --- | --- |
| 0 | 64 | OTP copy | SHA-256 binding only. |
| 64 | 12 | learned FDT down/base table | Copied into the first post-TLS 0x36 request. |
| 76 | 3,200 | navigation baseline | No direct consumer. Covered only by full-file hash/CRC. |
| 3,276 | 10,240 | no-finger image baseline | No direct consumer. Covered only by full-file hash/CRC. |
| 13,516 | 4 | CRC-32/MPEG-2 | File integrity only. |

The current driver then obtains three fresh IRQ0100 FDT samples, derives a fresh
table, learns release state, and acquires/decodes a fresh image baseline during
the action (`goodix_post_tls_lifecycle.c:653-740,833-851`). Therefore a future
driver need not reproduce the full Rockytkg `goodix.dat`.

On first activation it should send the already-shaped FDT-manual request with a
zero 12-byte initial table, collect bounded no-finger samples, reject touch/down
or inconsistent samples, and persist only the resulting 12-byte table if doing
so measurably improves subsequent startup. Rockytkg permits three sampling
attempts; the production design should use a similarly explicit bound, no
hidden action retry, and a clear “remove finger and retry later” result. It must
not accept an image baseline while a finger is present.

Temperature drift should continue to use the current per-action refresh and
fail/restart the affected action cleanly. Persistent image baselines add privacy,
staleness, and upgrade burdens without a current consumer. A persisted 12-byte
FDT table must be bound to OTP digest, chip/config profile, and state schema; an
upgrade may discard and safely relearn it.

## E. Proposed final architecture

### Component boundary

Add a small pairing/state coordinator inside the Goodix libfprint driver. It
must run only after libfprint owns the USB device for a real `fprintd` claim and
before the existing strict secure-session sequence. It should reuse the current
transport, response parser, TLS server, cancellation, and cleanup paths. It must
not become a second daemon or a private fprintd replacement.

The coordinator has four narrow responsibilities:

1. read exact APP/chip/OTP/pairing identity without persistent writes;
2. derive CONFIG90 and the WB validator from in-tree algorithms/constants;
3. load/reconcile a versioned per-reader local state transaction;
4. if and only if reconciliation requires it, execute the single qualified E0
   transaction and its readback/TLS gates.

Firmware update, IAP, ClearApp, OTP writes, mode/VID:PID persistence, synthetic
factory data, and unknown commands are outside this component and remain absent.

### Internal state receipt

The external manifest should become **B + D: an internal state receipt using a
new schema**, rather than preserving the current ten-field contract. A suggested
logical schema is:

```text
schema: goodix-5125-self-state-v2
reader_binding:
  vid, pid, exact_app, accepted_chip_profile, otp_sha256
derivation:
  wb_algorithm_version, config_profile_version, config90_sha256
pairing:
  state = PREPARED | ACTIVE | RECOVERY_REQUIRED
  generation, expected_bb020003, prior_expected_bb020003?
  e0_attempted, terminal_proof
fdt:
  format_version, seed_present, seed_sha256?
integrity:
  lengths, state_digest, creation/update generation
```

The PSK remains in a separate fixed-size protected file or protected transaction
slot referenced by generation. A plain SHA-256 receipt detects accidental
corruption but not malicious root modification; an HMAC keyed by the PSK can
bind receipt and secret without inventing another key. Neither protects against
root, which is outside the realistic threat boundary.

Full live A2/chip response pins cannot simply disappear without replacement.
For migration, retain the existing hashes. For a net-new reader:

- APP is an exact constant and mandatory gate;
- chip-82 must decode to the single qualified type-12 profile; structural bytes
  outside the chip value must be validated, not blindly learned;
- A6/OTP must pass the known length/format/CRC/calibration checks and supplies
  the reader binding;
- whether the full A2 and chip-82 response bytes are constant across qualified
  readers is **UNKNOWN**. Until multi-reader evidence resolves it, do not turn
  first-seen arbitrary response bytes into trusted policy. Accept only a narrow
  parsed form, and preserve full hashes as diagnostic state.

### Pairing state machine

The following corrects the prompt's conceptual order by placing the durable
`PREPARED` journal before E0:

```text
DRIVER_ACTIVATION
  |
  +-- claim/own USB; exact VID:PID
  +-- read A8 -> exact GF_ST411SEC_APP_12509 or UNSUPPORTED
  +-- read/parse chip-82 + A6 OTP -> derive reader_id/profile
  +-- derive CONFIG90; validate length/registers/finalizer
  +-- read BB020003 and current BB010002 (read-only)
  |
  v
LOAD_STATE(reader_id)
  |
  +-- state bound to another reader/profile -----------------> FAIL_CLOSED
  +-- corrupt but recoverable previous generation -----------> RESTORE_ATOMIC_BACKUP
  +-- corrupt/unrecoverable or absent ------------------------> NEW_LOCAL_SECRET
  +-- PREPARED ------------------------------------------------> RECONCILE_PREPARED
  +-- ACTIVE --------------------------------------------------> COMPARE_E4

COMPARE_E4
  |
  +-- live E4 == expected(active PSK) ------------------------> TLS_PROOF (NO E0)
  +-- live E4 != expected; identity and BB010002 valid --------> EXTERNAL_REPLACEMENT
  +-- readback absent/ambiguous -------------------------------> FAIL_CLOSED (NO E0)

NEW_LOCAL_SECRET
  +-- require qualified real BB010002 shape; otherwise FAIL_CLOSED
  +-- CSPRNG PSK; compute WB and expected E4
  +-- persist+fsync PREPARED transaction ----------------------> SINGLE_E0

EXTERNAL_REPLACEMENT
  +-- reuse active Linux PSK (generate only if none is usable)
  +-- preserve current BB010002 exactly
  +-- persist+fsync PREPARED transaction ----------------------> SINGLE_E0

SINGLE_E0
  +-- one logical E0 maximum for transaction; no retry
  +-- exact B0 ACK + qualified E0/E2 completion
  +-- BB010002 unchanged
  +-- BB020003 == SHA256(locally generated BB010003)
  +-- TLSv1.2 / PSK-AES128-GCM-SHA256 proof
  |
  +-- all pass -> atomic ACTIVE promotion + fsync ------------> SECURE_INIT
  +-- any fail -> keep recoverable journal; release/cleanup --> RECOVERY_REQUIRED

RECONCILE_PREPARED (read-only first)
  +-- E4 == candidate -> TLS; promote ACTIVE; NO E0
  +-- E4 == prior active -> discard/close failed candidate; use prior; NO E0
  +-- neither/ambiguous -> RECOVERY_REQUIRED; NO speculative E0

SECURE_INIT
  +-- existing pre-TLS configuration and strict responses
  +-- TLS
  +-- existing post-TLS FDT/baseline/capture lifecycle
```

`BB010002` is an important remaining input boundary. The qualified writer proves
that preserving the live OEM value unchanged supports Windows recovery; it does
not prove that a synthetic or absent value is safe. Net-new initialization may
therefore proceed automatically only when the field is readable, strictly
bounded, structurally accepted, and copied byte-for-byte into the single E0.
A factory reader with absent or malformed `BB010002` must fail closed until a
separate interoperability experiment qualifies a fallback. This is a real
scope limit, not a reason to require Windows capture for the normal target.

### First-run FDT and normal action lifecycle

After pairing/TLS succeeds:

1. if a state-bound 12-byte FDT seed exists, use it only as the initial 0x36
   input; otherwise use the to-be-qualified zero seed;
2. collect the current driver's bounded set of fresh IRQ0100 readings;
3. reject touch/down/up disturbance and inconsistent/delta-invalid readings;
4. derive the fresh down table and acquire a no-finger baseline image using the
   existing post-TLS path;
5. optionally persist the 12-byte table atomically, never the image, and proceed
   to normal enrollment/verify only after no-finger initialization completes;
6. on temperature or action drift, discard/reacquire the current action
   baseline. Do not silently promote a suspect sample to persistent state.

Expected first initialization includes one pairing proof/provisioning sequence
when needed plus bounded FDT and image baseline acquisition. It will be slower
than a normal reopen but requires no operator procedure beyond removing the
finger if the UI reports a disturbed baseline. Timeouts must be explicit and
tested; no claim here assigns an unmeasured wall-clock duration.

### Where initialization should run

| Placement | Privilege/USB and UX | Recovery/SELinux/update impact | Decision |
| --- | --- | --- | --- |
| Install-time provisioning | Installer has root but may run offline, with reader absent or fprintd active. It would couple package mutation to sensor state. | Hardest rollback: software rollback cannot undo E0. Adds USB/SELinux behavior to installation. | Reject. `install.sh` installs software/state policy only and must not start a sensor test. |
| First `fprintd` open | Stock fprintd/libfprint already owns the reader. Any first client can pay initialization latency. | Natural service confinement and cleanup. Must distinguish mere discovery from a claimed operation to avoid writes caused by enumeration. | Accept only when open is tied to a real claim/activation. |
| First biometric action | Clear user intent and normal UI; latency appears on first enroll/verify. | Easy to report/retry, but login must never become the first destructive initialization path. | Recommended trigger is first enrollment/settings action; verification may bootstrap read-only but should not unexpectedly write at login unless explicitly product-qualified. |
| Dedicated one-shot helper | Can own USB and files explicitly. | Competes with fprintd, needs systemd/DBus/SELinux/locking and a second protocol implementation or IPC. | Reject initially; disproportionate complexity. |
| Libfprint driver activation | Reuses exact target transport and secure state machine under stock fprintd. | Smallest code and policy boundary; rollback remains software plus protected state. | **Recommended execution boundary**, gated by a user-initiated fprintd operation. |

The public UX remains `./install.sh`, then KDE or `fprintd-enroll`. The deferred
hardware bootstrap is automatic. Installation and updates remain possible with
no reader present, and an initialization failure leaves password login, desktop,
sudo, and PolicyKit unchanged.

## F. Windows interoperability model

### Deterministic ping-pong

The robust model is not to make Linux understand or mint Windows DPAPI. It is to
let each OS own its host-side PSK state while preserving the reader's current
Windows blob during the Linux write.

```text
Linux first use
  local L1 -> WB(L1), preserve current BB010002 -> one E0 -> E4=H(WB(L1))

ordinary Linux reopen
  E4 == H(WB(L1)) -> no E0 -> TLS with L1

Windows return
  Windows detects its DPAPI/WB mismatch -> OEM fresh provisioning -> W1

Linux return
  exact reader identity still matches
  E4 != H(WB(L1)) and current BB010002 is valid -> external replacement
  preserve the new Windows BB010002, rewrite WB(L1) once -> E4/TLS proof
```

Thus the conceptual `L1 -> W1 -> L2 -> W2` sequence should normally be
`L1 -> W1 -> L1 -> W2 -> L1`: one Linux key is reused unless it is lost or
deliberately rotated. There is no write on ordinary Linux reopen. A write occurs
only after a read-only mismatch plus exact reader/firmware/field-shape gates.

The current project has **PROVEN** one Linux-to-Windows recovery and one later
qualified Linux write. Repeated alternation using the proposed state coordinator
is **INFERRED** until a bounded multi-cycle test qualifies it. The design is
recoverable and non-destructive with respect to firmware/factory data, but it
does change the mutable host pairing field once per OS transition.

The reader cannot reliably hold both Windows and Linux PSKs simultaneously in
the observed single pairing slot. Sharing one PSK would require one of:

- Linux obtaining the Windows PSK from a Windows DPAPI context;
- Linux creating a DPAPI blob that Windows can decrypt for the same PSK; or
- a documented multi-slot/shared-key protocol not present in current evidence.

All three are unavailable or undesirable. Exporting the Linux PSK into Windows
would add secret transfer and account/machine binding, defeating the product
goal. The OEM-coherent solution is bounded reprovisioning on actual OS switch,
not a cross-OS secret-sharing mechanism.

The code must call a mismatch “external pairing replacement,” not assert that
Windows caused it. Identity mismatch, corrupt readback, and unsupported response
shape are different states and must never trigger the writer.

## G. Failure and recovery matrix

| Case | Detection | Required behavior | E0 allowance / recovery |
| --- | --- | --- | --- |
| First install, valid existing `BB010002`, no local state | Exact target/APP/chip/OTP gates; no reader state directory | Generate PSK, durably persist PREPARED, one E0, readback/hash/TLS, promote ACTIVE | One. If interrupted, reconcile PREPARED read-only. |
| Normal Linux reopen | Live E4 equals validator derived from active local PSK | No write; TLS and normal initialization | Zero. |
| Return from Windows/external replacement | Same reader binding; E4 differs; current `BB010002` is valid and unambiguous | Reuse active Linux PSK, preserve current `BB010002`, journal, one qualified E0 | One per explicit provisioning transaction/OS return, never a hidden retry. |
| New physical reader with same VID:PID | Different OTP digest and/or chip profile | Never use or overwrite old reader state. Create a distinct reader slot only after all exact supported-target gates pass. | May use one first-install E0 for the new qualified reader; zero if firmware/profile unsupported. |
| Different firmware/app | A8 not exact APP12509 | Unsupported, release device, no mutation | Zero. No flash/IAP fallback. |
| Local state belongs to another reader | Receipt binding differs from live APP/chip/OTP | Fail closed for that state; preserve it for the original reader | Zero against mismatched state. |
| Recoverable state corruption | Active generation invalid but a previously fsynced generation validates | Restore/activate the last valid generation and compare E4 | Zero unless later comparison independently proves external replacement. |
| Unrecoverable/corrupt local state or lost PSK | No valid generation; exact reader still qualifies | Cannot recover PSK through the unqualified direct BB010003 read. Generate a fresh PSK only after current `BB010002` validates; journal before E0 | One new transaction. Preserve corrupt evidence without logging secrets. |
| `BB010002` absent/malformed/ambiguous | Read parser/length/metadata rejects it | Fail closed. Do not use the Rockytkg dummy and do not guess an OEM shape | Zero until a separate qualified fallback exists. |
| E4/readback ambiguous | Timeout, duplicate/conflicting frames, wrong tag/length/control | Release/cleanup; keep state diagnostic; no speculative writer | Zero. A later explicit action starts with read-only reconciliation. |
| E0 transfer/response failure | Missing exact ACK/completion or parser terminal failure | Mark transaction RECOVERY_REQUIRED and stop; no automatic E0 retry | The transaction has consumed its one allowance even if commit is uncertain. |
| TLS failure after E0 but E4 matches candidate | Candidate hash proves WB landed, TLS proof absent | Keep PREPARED, release cleanly. Next activation reads E4 then retries TLS without E0; only promote on TLS success | Zero additional E0. Repeated TLS failure quarantines the pairing for diagnosis. |
| TLS failure and E4 equals prior active | E0 did not replace the reader pairing | Discard candidate transaction, return to prior active state, surface failure | Zero additional E0 in that transaction. |
| TLS failure and E4 matches neither | Ambiguous/external state | RECOVERY_REQUIRED, no write. Require a new discriminating diagnosis/user action | Zero automatic E0. |
| Power loss before E0 | PREPARED record exists; reader E4 still prior/foreign | Read-only reconciliation chooses prior state or allows a new explicit transaction | No write solely because PREPARED exists. |
| Power loss/crash after E0 before final persist | Candidate PSK and expected E4 were already fsynced in PREPARED | E4 match -> TLS -> promote; prior match -> discard; neither -> quarantine | Zero recovery E0. This is why pre-write journaling is mandatory. |
| Finger present during FDT/image bootstrap | Touch IRQ, delta inconsistency, or finger classification | Discard sample, bounded retry or return a user-visible remove-finger error; never persist it | No pairing write is involved. |
| Temperature drift | Current action's baseline/finger classifier detects drift | Reacquire fresh action baseline within explicit bounds or fail the action | Do not mutate pairing; optional FDT seed update only after valid no-finger proof. |
| State schema newer than driver after rollback | Unsupported schema/version | Preserve state, use compatible read-only path if defined, otherwise disable fingerprint cleanly | Zero; password login remains available. |

Every sensor-reaching path must release the device, cleanse PSK/WB scratch
buffers, and leave a terminal transaction state on error. Logs may contain
generation IDs and digests, never PSK or WB plaintext/decrypted material.

## H. Migration plan

Existing valid users should migrate without E0 when the reader still carries
the imported PSK:

1. leave the current five-file bundle untouched and validate it with the current
   Python and native loaders;
2. in an offline migration step, extract the existing PSK, derive the direct WB
   validator, create a v2 reader-bound candidate state from the existing
   manifest's APP/chip/OTP hashes, and record provenance from the old bundle;
3. on the next real activation, obtain the live APP/chip/OTP and E4 read-only;
4. if all bindings match and E4 equals the migrated PSK validator, prove TLS and
   atomically mark v2 ACTIVE—**no E0**;
5. derive CONFIG90 from live OTP and compare it with the migrated captured
   CONFIG90. Until exact equivalence is qualified, keep the captured CONFIG90 as
   a migration-only internal fallback, never as a requirement for new users;
6. use the old cache seed for the first v2 action if needed, then learn the fresh
   FDT state through the normal path;
7. retain the original bundle read-only for a defined rollback window. Do not
   delete it as part of migration or ordinary update;
8. after at least one successful v2 activation, update, rollback, and Windows
   return have been qualified, a later release may retire old runtime loading.

Migration must be side-by-side and monotonic: the old release continues to read
the old bundle, while the new release prefers a complete v2 state and can fall
back to a still-valid old bundle during the compatibility window. Never rewrite
the only valid old set in place. If the old PSK is missing/corrupt or live E4 no
longer matches, use the normal external-replacement/missing-state decision tree;
do not label that outcome a successful migration.

An uninstall should remove project software and, by explicit policy, may retain
the protected self-contained reader state in the same way enrolled fprintd data
is retained. A separate explicit purge operation may remove it. Removing
software must never issue E0 or attempt to restore Windows pairing.

## I. Code-change map

This is a proposed map, not an authorization to implement it.

### Add

| Proposed file/module | Narrow responsibility |
| --- | --- |
| `libfprint-driver/goodix_pairing_crypto.[ch]` | Produce and validate the 102-byte APP12509 WB envelope and `BB020003` digest from a 32-byte PSK; hold KAT-visible constants; no USB or persistence. This may instead be a focused refactor/rename of `goodix_action_binding.[ch]`. |
| `libfprint-driver/goodix_self_state.[ch]` | Parse/write v2 receipt and fixed-size PSK/FDT slots with protected metadata, atomic generation updates, fsync, reader binding, PREPARED/ACTIVE reconciliation, and cleansing. No USB. |
| `libfprint-driver/goodix_config90.[ch]` | Parse live chip/OTP, select only the qualified type-12 profile, patch named fields, recompute/validate finalizer, and expose four DAC writes. No USB. |
| `libfprint-driver/goodix_pairing_provision.[ch]` | Minimal integration of the project-authored PoC's E4 reads, OEM-shaped E0 construction, one-write guard, exact response parser, unchanged-BB010002 check, E4 hash gate, and TLS transition. No firmware commands. |
| Focused tests under `libfprint-driver/tests/` | Crypto KATs, config differential vectors, state fault injection, pairing state transitions, migration, zero-seed FDT, cancellation, and secret/log hygiene. |

Avoid a generic framework: four small domains are justified because crypto,
durable state, pure config derivation, and sensor-reaching provisioning have
different safety/test boundaries. They should not become a second driver stack.

### Modify

| Current file/symbol | Required delta |
| --- | --- |
| `libfprint-driver/goodix_action_binding.[ch]` | Either evolve the current project-owned D190 implementation to expose the WB envelope/direct fixed-key validator, or retire it after equivalent KATs move to `goodix_pairing_crypto`. Remove runtime DLL seed inputs only after equality is proved. |
| `libfprint-driver/goodix_fpimage_device.c:acquire_default_material`, activation/start functions | Replace unconditional five-file loading with read-only identity discovery, v2 state reconciliation, and the pairing coordinator. Trigger writes only from the approved activation boundary. Preserve claim/cancel/release semantics. |
| `libfprint-driver/goodix_secure_session.[ch]` | Split pre-pairing read-only probes from the existing strict session; consume generated CONFIG90/direct validator/local PSK. Replace opaque captured response hashes with parsed, qualified APP/chip/OTP policy where evidence permits. Preserve all response and TLS gates. |
| `libfprint-driver/goodix_post_tls_lifecycle.[ch]` | Permit an explicit “no persisted FDT seed” state, run bounded zero-seed learning, and return a valid learned 12-byte table to the state layer. Continue fresh per-action baseline handling. |
| `libfprint-driver/goodix_runtime_material.[ch]` | During migration, dispatch between validated old bundle and v2 state without weakening either. Later retire the old path. |
| `deployment/materials.py`, `deployment/check-material.c`, `deployment/install.py` | In a later implementation task, install the empty protected state root and policy instead of requiring a first-install bundle; add side-by-side old-bundle migration validation. Installer remains USB-free. |
| `deployment/recovery/remove.py` | Define preserve-versus-explicit-purge behavior for v2 state and its SELinux mapping. Never touch reader pairing. |
| `production/build-public.py`, `production/source-files.tsv`, hashes/notices | Add new files, exact licenses, and provenance; later remove old runtime modules only after migration support ends. |
| `docs/DEVICE_MATERIALS.md`, `docs/INSTALLATION.md`, `docs/SECURITY.md`, `docs/LICENSING_AND_PROVENANCE.md`, `README.md` | After implementation/qualification, describe automatic first use, protected local state, migration/rollback, Windows switching, and provenance. Update `TECHNICAL_MANUAL.md` only for stable, proven technical facts—not development chronology. |

### Retire only after the compatibility window

| Current component | Retirement condition |
| --- | --- |
| `goodix_runtime_inputs.[ch]` PE/FDT file readers | No supported path consumes `gfusb.dll` or full `fdt-cache.bin`; direct crypto and zero-seed/FDT tests are qualified. |
| `goodix_target_material.[ch]` and `deployment/check-material.c` old contract | All supported installed bundles migrate/rollback safely and the old-reader window is deliberately closed. |
| `tools/windows_material_builder/` normal-user workflow | Net-new install, migration, recovery, Windows return, and update qualification all pass without it. Preserve history/provenance as decided below. |

### Repository component disposition

No file should be deleted during the architecture or first implementation
milestones.

| Component | Disposition | Reason |
| --- | --- | --- |
| Windows Material Builder | `KEEP_FOR_MIGRATION`, then `KEEP_FOR_PROVENANCE` or remove from release payload | Existing users and evidence can produce/validate old bundles; it must not remain a normal prerequisite. |
| USBPcap acquisition path | `KEEP_FOR_DIAGNOSTICS` + `KEEP_FOR_PROVENANCE` | Useful for bounded protocol diagnosis and evidence replay, not runtime/install. |
| `Goodix_Cache.bin` handling | `KEEP_FOR_MIGRATION`, then `KEEP_FOR_PROVENANCE` | Needed only to reconstruct existing Windows-derived bundles; no net-new use. |
| DPAPI recovery code | `KEEP_FOR_MIGRATION`, later remove from normal shipped tooling or keep historical | It must not be called by the Linux runtime. |
| `gfusb.dll` acquisition/validation | `REMOVE` from future workflow after crypto KAT qualification; `KEEP_FOR_PROVENANCE` documentation | The binary itself remains undistributed; no runtime information beyond fixed WB constants is needed. |
| Device-material bundle documentation | `KEEP_FOR_MIGRATION`, then rewrite/archive as historical compatibility documentation | Existing users need a supported transition; new users should not be instructed to capture. |
| Manual capture parsing | `KEEP_FOR_DIAGNOSTICS` | Still valuable for controlled evidence, but not a product path. |
| Old bundle compatibility layer | `KEEP_FOR_MIGRATION` for a stated release window, then `REMOVE` | Prevents breaking working installations and enables software rollback. |
| Qualified standalone PSK PoC | `KEEP_FOR_PROVENANCE` and offline regression | It is evidence and a test oracle, not the production writer. Commit mode must not be rerun. |
| Rockytkg snapshot | `KEEP_FOR_PROVENANCE` | Pinned comparison and licensed source provenance; never a runtime dependency. |

## J. Test and qualification plan

No live phase below is authorized by this audit. Each future sensor-reaching,
privileged, or Windows/VM passthrough phase requires its own Human Gate and a
prepared rollback/evidence request.

### OFFLINE

1. Direct-WB implementation matches all existing D190 KATs, captured OEM
   `BB010003`, known `BB020003`, and Rockytkg output vectors byte-for-byte.
2. Mutated key/AAD/header/IV/ciphertext/tag/HMAC vectors fail independently.
3. CONFIG90 generator is compared byte-for-byte against every legitimate
   available bundle. Tests name each expected patched offset and reject unknown
   chip, malformed OTP, invalid OTP checks, bad registers, and bad finalizer.
4. FDT zero-seed request encoding and three-sample learning are tested with
   recorded/synthetic no-finger, finger-present, timeout, duplicate, malformed,
   and temperature-drift events.
5. Pairing response tests retain captured E0/E2 bodies, B0 ordering, stream
   fragmentation, late/duplicate results, timeout, and one-write guard from
   `development/psk/test_goodix_psk_response.c`.
6. State tests fault every file operation and crash boundary: before/after
   secret write, receipt write, each fsync, rename, E0 intent mark, E0 result,
   E4 proof, TLS proof, and ACTIVE promotion. On restart exactly one read-only
   reconciliation outcome is selected.
7. Reader replacement, corrupt state, rollback-to-older-schema, concurrent
   opens, cancellation, symlink/hardlink/special-file, owner/mode, TOCTOU, and
   disk-full tests fail closed.
8. Log and memory-observer tests prove PSK/envelope plaintext is never printed
   and sensitive scratch is cleansed on every terminal path.
9. Static/source tests prove production build contains no firmware blob, IAP,
   ClearApp, OTP write, dummy BB010002, or automatic E0 retry path.
10. Migration tests transform synthetic/qualified old bundles to v2 state and
    prove no byte of the old set is changed.

### VM (no physical reader required)

1. Fresh Fedora 44 KDE installation succeeds without a material directory and
   without starting fprintd or touching USB.
2. SELinux remains Enforcing; state root labeling and stock fprintd unit/drop-in
   checks pass. The audit sandbox could not query the system bus, so the actual
   production service identity/access must be rechecked in the qualification VM.
3. Update, reinstall, failed install, normal uninstall, force recovery, and
   rollback preserve password login and the desktop.
4. A missing reader and an unsupported mocked reader leave the service healthy
   and do not create pairing transactions.
5. Old-bundle and v2-state software rollback matrices pass in both directions.

### LIVE_NO_FINGER

Use the exact APP12509 target, no biometric capture, and no more than one E0 in
the authorized provisioning transaction:

1. read-only identity/chip/OTP/BB010002/E4 preflight;
2. generated CONFIG90 equality with the current qualified CONFIG90 before it is
   ever sent;
3. first-run PSK journal -> single E0 -> exact response -> unchanged
   BB010002 -> matching E4 -> TLS proof;
4. close/reopen proves zero E0 and same PSK/TLS;
5. controlled power-cut/crash injection at the post-E0/pre-ACTIVE boundary,
   followed by read-only recovery with zero additional E0;
6. zero-seed FDT no-finger learning and bounded finger-disturbance rejection;
7. cancel/error paths prove release, cleanse, and stable next open.

`PASS_IF`: all exact gates pass, the write counter is one only when required,
ordinary reopen is zero, and no persistent field outside the pairing record is
changed. `STOP_IF`: identity/profile/field shape differs, readback is ambiguous,
CONFIG90 differs unexplained, a second E0 is requested, or any firmware/IAP path
appears.

### LIVE_WITH_FINGER

Only after LIVE_NO_FINGER passes:

- enroll through KDE/fprintd, then verify/identify through the stock stack;
- exercise finger-present-during-bootstrap, release, cancellation, and
  temperature/baseline refresh behavior;
- preserve `MAX_PHYSICAL_ATTEMPTS=3`, stop on first match, and forbid a fourth or
  hidden retry;
- confirm password login, sudo, KScreenLocker, PolicyKit, and desktop fallback
  before and after failure cases.

### WINDOWS_INTEROP

1. Start from Linux ACTIVE L1, boot/pass through to Windows, and record that OEM
   recovery reaches a cryptographically coherent W1.
2. Return to Linux: read-only E4 mismatch, exact same reader binding, preservation
   of W1's `BB010002`, one rewrite of **L1**, hash/TLS proof.
3. Reopen Linux twice: zero E0 both times.
4. Repeat a bounded Windows/Linux cycle to test W2/L1 without growing Linux key
   generations or entering a loop.
5. Negative tests for malformed/absent BB010002 stop before E0.

No PSK, DPAPI plaintext, biometric data, or private capture enters public test
artifacts.

### DUAL_BOOT / USB PASSTHROUGH

- Repeat the same state transitions in the actual dual-boot and both VM
  passthrough directions, one owner at a time.
- Test abrupt VM detach and host reboot between E0 and local promotion.
- Ensure USB ownership loss cannot cause a second writer and that a stale VM
  state cannot select another reader's host state.

### UPDATE / ROLLBACK

- Update current bundle release -> migration-capable release -> fully
  self-contained release without changing pairing when E4 already matches.
- Roll back at every state schema generation; unsupported newer state disables
  fingerprint cleanly rather than rewriting it.
- Upgrade with reader absent, external Windows pairing present, PREPARED state,
  corrupt optional FDT seed, and full filesystem.
- Prove Fedora package updates may disable fingerprint but never password login,
  desktop, sudo, or PolicyKit.

## K. Security, licensing, risks, and unknowns

### Security model

- The PSK is a root-service secret, never a user credential and never logged.
  Root-only storage is proportionate because a hostile root can replace the
  driver, read process memory, or impersonate fprintd regardless of encryption.
- The pairing writer is a privileged persistent-state operation. Its authority
  must be one narrowly reviewed call site with exact identity, one logical E0,
  no automatic retry, and independent readback/TLS proof.
- `BB010002` is opaque protected Windows material. Linux may read, length-check,
  hash for diagnostics, and preserve it byte-for-byte; it must not decrypt,
  synthesize, print, or distribute it.
- OTP may be read and hashed/used for calibration. OTP writes, firmware, factory
  data, and persistent mode/VID:PID changes remain impossible from the proposed
  modules.
- Internal hashes detect corruption and bind state; they do not confer trust on
  arbitrary first-seen bytes. Target trust comes from exact APP, parsed chip/OTP
  policy, qualified algorithms, and post-write cryptographic proof.
- Persisting a no-finger FDT table has low biometric content compared with an
  image, but still receives root-only handling. No baseline image is persisted.

### Licensing and provenance

Rockytkg `src/` is GPL-2.0-or-later except where a file states otherwise;
`src/goodix_psk.c`, `goodix_init.c`, `goodix_otp.c`, `goodix_base.c`, and
`goodix_capture.c` are GPL-2.0-or-later. The current Goodix protocol modules are
predominantly LGPL-2.1-or-later, while the combined library is already conveyed
under GPL-3.0-or-later because it incorporates GPL preprocessing
(`docs/LICENSING_AND_PROVENANCE.md`). These facts do not permit relabelling
copied GPL expression as LGPL.

Preferred implementation choices:

1. derive WB output by refactoring the current project-authored
   `goodix_action_binding.c`, using Rockytkg and OEM vectors as differential
   oracles; record the fixed protocol constants and evidence provenance;
2. independently specify CONFIG90 field semantics and patch tests. If the
   Rockytkg 224-byte template or patch code is copied/adapted, place it under a
   compatible GPL notice, attribute exact path and commit, and update public
   provenance;
3. adapt only the minimal project-authored response parser/writer logic from
   `development/psk`, not the monolithic experimental program;
4. never add Rockytkg firmware, OEM DLL, private captures, Goodix cache, factory
   material, real biometric data, or per-reader secrets to the public payload.

Any decision to copy GPL Rockytkg implementation into the production driver is
a material licensing/provenance choice to approve before implementation. A
clean implementation of protocol facts still requires traceable design notes
and KATs; “clean” must not be used to erase source provenance.

### Open risks and unknowns

| Item | Status / consequence | Minimum discriminating evidence |
| --- | --- | --- |
| Exact generated CONFIG90 equivalence | **UNKNOWN / blocker**. Matching register structure is not enough. | Offline byte diff for every available bundle, then one gated live ACK/session proof. |
| Zero-seed FDT on current production path | **INFERRED / blocker**. Rockytkg succeeds from zero; current driver requires nonzero input. | Offline lifecycle vectors, then bounded LIVE_NO_FINGER run. |
| General real `BB010002` structural acceptance | **UNKNOWN / blocker for arbitrary factory state**. The PoC pinned one 332-byte instance. | Compare legitimate states across qualified Windows pairings/readers and qualify a strict length/tag parser; preserve bytes unchanged. |
| Absent `BB010002` fallback | **UNKNOWN**. Dummy data is not Windows-qualified. | Separate Windows recovery experiment or declare such readers unsupported; never guess in production. |
| A2/full chip-82 stability across physical readers | **UNKNOWN**. Current manifest pins full captured responses. | Read-only multi-reader samples; define parsed constants versus reader fields. |
| Repeated L1/Wn ping-pong | One round trip is PROVEN; repeated v2 coordinator behavior is **INFERRED**. | Bounded multi-cycle Windows interoperability test. |
| Production integration of E0 | PoC is PROVEN, integrated writer is not. | Parser/KAT parity, fault injection, then single authorized live transaction. |
| State access under real Fedora service/SELinux context | Repository installer policy exists; this audit's system-bus query was unavailable. | VM/physical read-write check by stock fprintd with SELinux Enforcing. |
| First-action versus login trigger | An automatic E0 at an unattended login would be surprising and hard to diagnose. | Product decision and integration test: initial write only from explicit enrollment/settings activation. |
| State rollback/downgrade | New schema can strand an older driver. | Side-by-side generations and full update/rollback matrix before retiring bundle loader. |
| Multi-reader support | Per-OTP directories are designed but not target-qualified across units. | Two-reader read-only identity/config tests before advertising support. |

No current evidence requires firmware flashing, IAP, a distributed DLL, a full
persistent image baseline, or a private Fedora authentication component.

## L. Recommended implementation sequence

Each milestone has a stop condition and should be reviewed before the next one.

### M0 — Approve architecture and evidence contract

- Decide the recommended libfprint-activation boundary, v2 state location/schema,
  Linux-key reuse policy, preserved-BB010002 rule, and migration window.
- Resolve whether CONFIG90 code will be clean project implementation or explicit
  GPL adaptation.
- **Stop if** the project wants shared Windows/Linux PSK, firmware changes, or a
  different licensing boundary; those are new strategies, not implementation
  details.

### M1 — Remove the DLL logically, offline only

- Implement/refactor pure WB envelope and validator code.
- Pass all D190, OEM, Rockytkg differential, and negative KATs.
- Keep the current DLL-backed runtime unchanged.
- **Stop if** any byte differs without a proven explanation.

### M2 — Derive CONFIG90 and model seedless FDT, offline only

- Implement pure chip/OTP parsing and type-12 configuration derivation.
- Exact-diff all available legitimate CONFIG90 files.
- Extend post-TLS tests for absent/zero seed, disturbed samples, and optional
  12-byte persistence.
- **Stop if** template provenance, nonpatched differences, or chip/OTP semantics
  remain ambiguous.

### M3 — Build crash-safe state and migration, offline only

- Implement protected v2 state, PREPARED/ACTIVE journal, per-reader binding,
  concurrent lock, fault injection, and old-bundle importer.
- Prove recovery at every persistence boundary and no loss of the old bundle.
- **Stop if** post-E0/pre-persist recovery can require guessing or a second E0.

### M4 — Integrate read-only discovery and coordinator in host tests

- Split the secure-session preflight, add identity/config/state decisions, and
  port the minimal response parser/one-write guard without enabling production
  writes.
- Run Fedora VM install/update/uninstall/SELinux tests with no bundle required.
- **Stop if** device discovery or login can trigger a write without an explicit
  biometric activation.

### M5 — Qualify LIVE_NO_FINGER behind a Human Gate

- Prepare minimal install/rollback and exact commands/evidence.
- First qualify CONFIG90 and zero-seed FDT read/no-finger behavior.
- Only then authorize one integrated PSK provisioning transaction with all PoC
  gates and crash recovery.
- **Stop on** any unexplained response, second E0 request, field mutation outside
  pairing, or TLS/readback mismatch.

### M6 — Qualify Windows interoperability and bounded switching

- Windows recovery, Linux L1 restoration, ordinary reopen, repeated bounded
  cycle, VM passthrough, abrupt detach/reboot.
- Confirm no DPAPI extraction or Windows preparation is needed by Linux.
- **Stop if** ordinary same-OS reopen writes or either OS becomes unrecoverable.

### M7 — Qualify biometric and desktop integration

- Run enrollment/verify/identify with the three-attempt physical bound and stock
  Fedora consumers; verify baseline/temperature/cancel paths.
- Reconfirm password login and desktop survivability.
- **Stop if** failure escapes the fingerprint subsystem.

### M8 — Ship migration first; retire legacy later

- Release a compatibility version that imports old bundles and creates v2 state
  without unnecessary E0.
- Exercise update/rollback in production-equivalent Fedora.
- In a later deliberate release, remove the new-user builder requirement and
  eventually the old loader after the published compatibility window.
- Update stable public documentation and provenance only with proven facts.

## Recommended approval decision

Approve the **driver-activation, journal-before-E0, preserve-BB010002,
reuse-one-Linux-PSK, template-plus-OTP CONFIG90, live-learned FDT** architecture
as the implementation baseline, subject to M1–M4 remaining offline and M5+ each
receiving a new explicit Human Gate. Do not approve an integrated writer yet;
the three technical blockers above must
first be closed with the stated evidence.

HUMAN_REQUIRED: SELF_CONTAINED_ARCHITECTURE_APPROVAL
