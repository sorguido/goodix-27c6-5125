# D274/03 SIGFM real-build closure report — Sessione 3

```text
OUTCOME=READY_FOR_AI_PM_REVIEW
ADVANCEMENT=SIGFM_REAL_OPENCV4_HOST_ONLY_BUILD_CLOSURE
EXECUTABLE_CLOSURE=PASS_HOST_ONLY
REAL_SIGFM_BUILD=PASS_HOST_ONLY_WITH_REAL_OPENCV4
REAL_SIGFM_LINK=PASS
REAL_SIGFM_SYNTHETIC_RUNTIME=PASS
REAL_SIGFM_SANITIZER_STATUS=PASS
OPENCV4_DEV_ENVIRONMENT=AVAILABLE_HOST_ONLY_LIBOPENCV_DEV_4_5_4_VIA_APT

BIOMETRIC_QUALITY_STATUS=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED
PRODUCTION_MATCH_THRESHOLD=UNSET
ORIENTATION_CONTRACT=UNRESOLVED
POLARITY_CONTRACT=UNRESOLVED
TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN
TARGET_APP12509_PHYSICAL_DPI=UNKNOWN
SECOND_TARGET_CYCLE=UNOBSERVED

LINUX_TLS_REBUILD_REQUIRED=false
LIBFPRINT_ENROLLMENT_AGGREGATION=FRAMEWORK_OWNED_VERIFIED
PROJECT_EXTRA_FPIMAGE_AGGREGATOR_REQUIRED=false
LOCAL_LIBFPRINT_DEVICE_GLUE=NOT_YET_IMPLEMENTED

D274_03_OPERATOR_KIT_MODIFIED=false
LIVE_CRITICAL_SET_MODIFIED=false
REAL_USB_OPEN_COUNT=0
REAL_COMMAND_SEND_COUNT=0
REAL_SECRET_MATERIALIZATION_COUNT=0
REAL_FPRINTD_MUTATION_COUNT=0
REAL_BIOMETRIC_CAPTURE_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
```

## 1. Scope and precondition

Host-only, reversible SIGFM/OpenCV4 real-build closure (track parallel offline
forward D274/03, Sessione 3). No target Goodix, no USB, no biometric corpus, no
new protocol inference. Precondition Git satisfied: `HEAD == origin/main`
(`b88edaa44e124ea7b6cd5b0464fca630f5d2da51`), clean tree, no divergence.

The session closes the D273 blocker
`REAL_SIGFM_BUILD=BLOCKED_OPENCV4_DEV_NOT_AVAILABLE` /
`EXECUTABLE_CLOSURE=FAIL_NOT_AVAILABLE`.

## 2. Environment (Phase A + B)

Ubuntu 22.04 jammy, x86_64, GCC/G++ 11.4.0, pkg-config 0.29.2. OpenCV4-dev was
**not** present; it was installed in the executor sandbox via the distro package
manager (`apt-get install -y build-essential pkg-config libopencv-dev` ->
`libopencv-dev 4.5.4+dfsg-9ubuntu4`). This satisfies every install constraint:
no user credentials, no security bypass, no target/USB/fprintd modification, no
OpenCV vendoring in the repo, no committed binaries/libs, standard reproducible
distro package manager. The `Rockytkg/` mirror was **not** modified.

## 3. License / provenance (Phase C)

All four SIGFM reference files
(`sigfm.cpp`, `sigfm.h`, `binary.hpp`, `img-info.hpp`) carry SPDX
`LGPL-2.1-or-later` headers and belong to the upstream libfprint material
(per `Rockytkg/PROVENANCE.md` and `docs/LICENSING_AND_PROVENANCE.md`), the
expected domain for `libfprint-driver/`. No new import/adaptation was made, so
no new ledger entry is required.

## 4. Differentiated warning policy (Phase D)

- **Project code** (`goodix_u16_to_fpimage.c`, `goodix_sigfm_metrics.cpp`,
  `test_goodix_sigfm_metrics_real.cpp`): full
  `-std=c11 -O2 -g -Wall -Wextra -Werror -Wconversion` (C) and
  `-std=c++17 -O2 -g -Wall -Wextra -Werror -Wconversion -Wshadow -Wold-style-cast`
  (C++).
- **Third-party reference SIGFM** (`sigfm.cpp` + its headers): relaxed
  `-Wall -Wextra` (no `-Werror`/`-Wconversion`/`-Wold-style-cast`), headers
  included via `-isystem` so project warnings stay visible.

Result: our code compiles with zero warnings; no third-party warning is
masked inside our object. No `-Werror` patch was applied to the mirror.

## 5. Build / link / runtime (Phase D + E)

All four translation units compiled, linked with `pkg-config --libs opencv4`,
and the real synthetic test ran:

```text
goodix real SIGFM synthetic plumbing: PASS
```

The test exercises the real `sigfm_extract` (SIFT + BFMatcher) and
`sigfm_match_score` through our `goodix_sigfm_extract_ephemeral` /
`goodix_sigfm_match_ephemeral` wrapper on a deterministic LCG fixture
(`80x64` u16 raster). It is **SYNTHETIC_ONLY**: no target image, no capture, no
biometric corpus.

## 6. Memory safety (Phase F)

ASan/UBSan build (`-O1 -fno-omit-frame-pointer
-fsanitize=address,undefined`) compiled and ran clean
(`ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`, `UBSAN_OPTIONS=halt_on_error=1`):

```text
REAL_SIGFM_SANITIZER_STATUS=PASS
```

## 7. Reproducible harness (Phase G)

Added `libfprint-driver/tests/run_goodix_sigfm_metrics_real_host.sh` — host-only
real-SIGFM build/test runner (the prior `run_goodix_sigfm_metrics_test.sh` is
Flatpak-based and not usable here). It is fail-closed: if `opencv4.pc` is
absent it prints `REAL_SIGFM_DEPENDENCY=BLOCKED_OPENCV4_DEV_UNAVAILABLE` and exits
0 (SKIP, never a fake PASS); it prints `SKIP/NOT_AVAILABLE` vs `FAIL` vs `PASS`
explicitly; no USB/fprintd/secret/mandatory network at runtime; no auto package
install; no system modification; no OpenCV vendoring; no threshold change;
objects only under `mktemp -d /tmp/...` cleaned on exit.

## 8. Regression (host-only)

| Test | Result |
| --- | --- |
| `goodix_u16_to_fpimage` unit | PASS |
| `goodix_sigfm_metrics` synthetic/double + forbidden-symbol audit | PASS |
| `goodix_fpimage_pipeline` | NOT_RUNNABLE_HOST_ONLY (missing libfprint `fpi-image.h`; consistent with `LOCAL_LIBFPRINT_DEVICE_GLUE=NOT_YET_IMPLEMENTED`) |

Forbidden-symbol audit on `metrics.o`: no `libusb_`/`SSL_`/`gnutls_`/`socket`/
`fopen`/`open`/`write`/`read` symbols -> PASS.

## 9. Classification (distinct axes)

| Axis | Status |
| --- | --- |
| BUILDABILITY | PASS |
| LINKABILITY | PASS |
| SYNTHETIC_REAL_SIGFM_RUNTIME | PASS |
| MEMORY_SAFETY | PASS (ASan/UBSan clean) |
| TARGET_BIOMETRIC_QUALITY | UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED |
| PRODUCTION_INTEGRATION | NOT_INTEGRATED_NO_DEVICE_GLUE |

A PASS of the first four does **not** close the last two.

## 10. What remains open (not closed by this session)

`TARGET_APP12509_PHYSICAL_PPMM=UNKNOWN`, `TARGET_APP12509_PHYSICAL_DPI=UNKNOWN`,
`ORIENTATION_CONTRACT=UNRESOLVED`, `POLARITY_CONTRACT=UNRESOLVED`,
`BIOMETRIC_QUALITY_STATUS=UNPROVEN_TARGET_REAL_EVIDENCE_REQUIRED`,
`PRODUCTION_MATCH_THRESHOLD=UNSET`, same/different-finger score distributions
NOT_COLLECTED, `VERIFY_QUALITY=UNPROVEN`, `SECOND_TARGET_CYCLE=UNOBSERVED`,
`TARGET_TIMEOUT_POLICY=UNCLOSED`, `LOCAL_LIBFPRINT_DEVICE_GLUE=NOT_YET_IMPLEMENTED`.
Rockytkg / Issue #1 remain `THIRD_PARTY_CORROBORATION`, not target-local proof.

## 11. Next real gap after this session

The SIGFM OpenCV4 build blocker is removed. The next genuine gaps are:
(1) **local libfprint device glue** (`goodixgf.c` LGPL reuse candidate after
per-file audit; excluding unsafe firmware/PSK/persistent paths), and
(2) **observation of the second capture cycle after re-arm** via a future
explicitly-authorized D274/03 live one-shot with Goodix attached — neither is
addressed here.

## 12. Windows operator kit integrity

`invoke-d274-03-live-once.ps1` git blob SHA
`fca3c40d4a3fcd7c6c21ce6809de794d69908e7a` preserved;
`D274_03_OPERATOR_KIT_MODIFIED=false`, `LIVE_CRITICAL_SET_MODIFIED=false`.
