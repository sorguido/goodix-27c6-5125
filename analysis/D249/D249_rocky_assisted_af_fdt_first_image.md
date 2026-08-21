<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# D249 — Rocky-assisted AF → FDT → first-image offline implementation

## Correction baseline and scope

The requested PR head was
`a49321c028d3bc288c7e6a3226b079c8ee667bfe`. The object is not present in this
clone. The observed initial workspace head was
`25724f9cac638bf3c744156b22961e847d0e1910` on branch `work`, containing the
current D249 implementation commit. This correction stays on that branch and
adds a normal commit; it performs no amend, rebase, reset, history rewrite,
branch switch, merge, new D-number, or new PR.

The exact canonical guideline path found in the root is
`Linee Guida di Progetto Goodix 27c6 5125 per AI.md`. D249 correction execution
is offline only: no USB enumeration/open, `sudo`, secret, live TLS, sensor
command, finger interaction, persistence, retry, reconnect, provisioning or
firmware operation occurred.

## Rocky pin and per-file verification

The reachable Rocky checkout was reconfirmed at immutable commit
`227eba219fa9e3fbac5bd59aca79f624f67cd11b`. The relevant per-file SPDX headers
are `GPL-2.0-or-later`; the repository-level notice is Copyright (C) 2026
liushicong (Rockytkg).

| Component | Classification | SOURCE_REPO | SOURCE_COMMIT | SOURCE_PATH | Adaptation |
| --- | --- | --- | --- | --- | --- |
| command/A0 framing and AF | `ADAPTED_FROM_ROCKY` | `https://github.com/Rockytkg/goodix-linux-27c6-5125` | `227eba219fa9e3fbac5bd59aca79f624f67cd11b` | `src/goodix_cmd.c`, `src/goodix_frame.c` | Python, local AF direct-response contract, strict allowlist/checksum |
| FDT/POV/image sequencing and mixed receive shape | `ADAPTED_FROM_ROCKY` | same | same | `src/goodix_capture.c` | bounded monotonic mock state machine; no retry/reconnect/persistence/lifecycle |
| 7684-byte codec | `LOCAL_EXISTING_REUSED` | local project | initial local D249 parent `bc377c820fa661c889d61b17a4c81e42507fc78a` | `src/goodix5125_cleanroom.py` | imported and called directly; no Rocky decoder and no third algorithm |
| typed failures, abstract transport and scripted closure | `NEW_LOCAL_IMPLEMENTATION` | local project | D249 correction | `core/post_d4.py`, `tests/test_d249_post_d4.py` | offline-only adapter/harness |

No Rocky USB lifecycle, retry/backoff, TLS reconnect, PSK, MCU write, baseline
persistence, firmware updater, IAP, ClearApp, producer write, E0/A4/F0/F4 or
vendor blob is imported or reachable. Rocky remains implementation
corroboration, not target-specific evidence for APP12509.

## Differential contract retained

| Field | Classification | Result |
| --- | --- | --- |
| D4 → AF position | **osservato** | local capture has D4/ACK followed by plaintext AF |
| AF request/response | **osservato/verificato** | wire AF with `55,ts16le,00,00`; direct AE, exactly 16 state bytes, no intervening ACK in the local occurrence |
| AF flags | **verificato** DLL + Rocky, locally consistent | state byte 1 bits 0/1/3 are POV-valid/TLS-connected/locked; unknown bits are preserved |
| Fresh FDT path | **osservato** command/event classes; exact full causal minimum remains **inferito** | FDT down 32 → IRQ 2 → SetMode Image 20 → type-2 image payload |
| Cached POV path | **verificato** host implementation, externally corroborated; target occurrence incomplete | AF POV bit → D2 → cached image payload |
| Complete mixed ordering on 12509 | **non noto** | offline demux proves parser behavior, not every target ordering |
| FDT disarm/restore | **non noto** | 34 is finger-up detection, not proven deterministic cleanup |

## Codec blocker correction

The rejected D249 decoder was removed. `decode_image_record()` now delegates
directly to the canonical local `src/goodix5125_cleanroom.py` implementation
and only normalizes its failures into D249 typed errors. Therefore the actual
contract is unchanged: 7684 bytes; 7680 packed bytes; 6 bytes → 4 samples;
5120 samples; the established wire-index transpose into 80×64; CRC-32/MPEG-2;
and trailer byte order `(crc>>8, crc, crc>>24, crc>>16)`.

Independent equivalence tests create a record with
`encode_synthetic_record()` from the canonical module, decode it with both the
canonical module and D249, and compare every pixel. They explicitly assert the
non-big-endian trailer, corrupt a packed byte and require CRC failure, and use
the non-trivial KAT `cfff23ab4561 ↔ (fff,abc,123,456)`. These tests fail against
the prior D249 decoder rather than merely proving a new encoder/decoder pair
self-consistent.

`CODEC_EQUIVALENCE=PASS_PIXEL_FOR_PIXEL_AGAINST_LOCAL_CANONICAL_CODEC`

## Real offline first-image closure

`FirstImageMachine` is monotonic and consumes only an injected abstract
`Transport`. Both bounded paths reach the explicit terminal
`FIRST_IMAGE_RECEIVED`:

```text
fresh:  POST_D4 → AF_OK/FRESH_FDT → 32 ACK → WAIT_FDT_DOWN
        → IRQ 2 → 20 ACK → WAIT_IMAGE → strict type-2 image payload
        → canonical record decode → FIRST_IMAGE_RECEIVED

cached: POST_D4 → AF_OK/POV → D2 ACK → WAIT_IMAGE
        → strict type-2 image payload → canonical record decode
        → FIRST_IMAGE_RECEIVED
```

This is executable closure of the offline model, not proof that either full
sequence is safe or causally complete on the target. The harness rejects ACK
duplicates/wrong echo/status, FDT events out of order, early image payloads,
unexpected controls, corrupt framing/checksums, EOF before terminal, short/long
records, image CRC failures, repeated/regressive transitions and non-allowlisted
commands. There are no retries or unbounded loops.

`FIRST_IMAGE_OFFLINE_CLOSURE=PASS_FRESH_FDT_AND_CACHED_POV_FIXTURES`

## Checksum 0x88 policy

Local DLL disassembly at `function_18005f098_non_b0_dispatch.txt` observes a
comparison with `0x88`, and the known NOP/no-check form uses a 0x88 trailer.
Rocky's generic receive code also treats it as a no-check marker. Neither fact
establishes that every D249 AF/FDT/image payload may bypass its checksum.

The D249 subset does not need a no-check class. `parse_payload()` therefore
always computes and compares the additive checksum. A byte value 0x88 is valid
only if the arithmetic checksum for that exact control/data is itself 0x88;
otherwise it raises `ChecksumMismatch`. NOP is outside the D249 allowlist. A
negative test supplies a deliberately wrong 0x88, and a positive test finds a
payload whose genuine computed checksum equals 0x88. There is no global bypass.

`CHECKSUM_0X88_POLICY=STRICT_COMPUTED_CHECKSUM_ONLY_NO_BYPASS_IN_D249`

## Executable closure and results

- `timeout 30s python3 -m unittest -v tests.test_d249_post_d4`: 12/12 passed;
  this includes three codec-equivalence tests, both first-image paths and the
  adversarial matrix.
- `python3 -m py_compile core/post_d4.py tests/test_d249_post_d4.py`: passed.
- `timeout 120s python3 -m unittest discover -s tests -v`: 53 run; 36 passed,
  1 skipped, 3 failed and 13 import errors. Every non-pass is a legacy path
  blocked by the pre-existing missing `cryptography` dependency. The command is
  environment-limited and is not declared PASS; all 12 D249 tests passed inside it.
- `git diff --check`: passed after final changes.

## Next-live decision

The correction improves only the offline implementation. It does not close
physical AF tail/pacing, target FDT arming/disarm/restore, all mixed-channel
ordering, or target-side persistence behavior. It therefore does not justify a
finger request or a first-image live run.

`MIN_SAFE_LIVE_BOUNDARY=EXACTLY_ONE_AF_QUERY_AFTER_THE_ALREADY_PROVEN_D4_ACK_THEN_STOP`

`MAX_JUSTIFIED_LIVE_BOUNDARY=AF_RESPONSE_VALIDATED_AND_STATE_TELEMETRY_RECORDED_THEN_STOP_BEFORE_ANY_FDT_OR_FINGER_INTERACTION`

Both remain candidates requiring separate review, approved full Git live
baseline, guardrails and explicit authorization; neither is authorized here.

## Closure

`OUTCOME=READY_OFFLINE`

`ADVANCEMENT=OFFLINE_CORRECTION_AND_EXECUTABLE_MODEL_CLOSURE_NO_DEVICE_SIDE_ADVANCEMENT`

`EXECUTABLE_CLOSURE=PASS`

`RESIDUAL_BLOCKER_OR_RISK=AF_PHYSICAL_LIVE_CONTRACT_AND_FDT_ARM_DISARM_RESTORE_REMAIN_TARGET_UNCLOSED;NO_FINGER_LIVE_JUSTIFIED`

`CANONICAL_DOCUMENTATION=UPDATED`

`BUNDLE=analysis/D249/D249_rocky_assisted_af_fdt_first_image_bundle.zip.b64 (Base64 transport only; report remains the external hash-bearing index to avoid self-reference)`

`ROCKY_PINNED_COMMIT=227eba219fa9e3fbac5bd59aca79f624f67cd11b`

`RECONSTRUCTED_ZIP_SHA256=27e85910998a5873571aec44500f42ecdb2b11c063b6e5bcbc10871f198f70cc`
