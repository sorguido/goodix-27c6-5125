# D274/03 SIGFM real-build — Execution Manifest (host-only)

```text
ARTIFACT_CLASS=SIGFM_REAL_OPENCV4_HOST_ONLY_BUILD_CLOSURE
DEPENDS_ON_D274_03_QUALIFICATION=false
MODIFIES_D274_03=false
MODIFIES_LIVE_CRITICAL=false
REAL_USB_OPEN_COUNT=0
REAL_COMMAND_SEND_COUNT=0
PERSISTENT_DEVICE_WRITE_COUNT=0
LIVE_EXECUTION=NOT_PERFORMED
ENVIRONMENT=HOST_ONLY_SANDBOX_OPENCV4_DEV_INSTALLED_VIA_APT
```

## Precondition (Git)

| Check | Value |
| --- | --- |
| `git rev-parse HEAD` | `b88edaa44e124ea7b6cd5b0464fca630f5d2da51` |
| `git rev-parse origin/main` | `b88edaa44e124ea7b6cd5b0464fca630f5d2da51` |
| `git merge-base HEAD origin/main` | `b88edaa44e124ea7b6cd5b0464fca630f5d2da51` |
| `git status --short --branch` | clean, branch `session/agent_*` |
| Verdict | `HEAD == origin/main`, no divergence, clean -> precondition PASS |

## Environment acquisition (bounded, reversible)

```sh
apt-get update
apt-get install -y build-essential pkg-config libopencv-dev
# -> libopencv-dev 4.5.4+dfsg-9ubuntu4 ; pkg-config opencv4 -> 4.5.4
```

No target Goodix, no USB, no fprintd, no vendoring, no committed binaries.

## Normalized build commands (run from repo root)

```sh
REPO=$(pwd)
SIGFM=$REPO/Rockytkg/libfprint/libfprint/sigfm
DRV=$REPO/libfprint-driver
TEST=$REPO/libfprint-driver/tests
OCV_CFLAGS=$(pkg-config --cflags opencv4)   # -I/usr/include/opencv4
OCV_LIBS=$(pkg-config --libs opencv4)
B=$(mktemp -d /tmp/goodix-sigfm-real.XXXXXX)

# 1) adapter (project C, full -Werror)
gcc -std=c11 -O2 -g -Wall -Wextra -Werror -Wconversion \
    -I"$DRV" -c "$DRV/goodix_u16_to_fpimage.c" -o "$B/adapter.o"

# 2) metrics wrapper (project C++, full -Werror; third-party headers via -isystem)
g++ -std=c++17 -O2 -g -Wall -Wextra -Werror -Wconversion -Wshadow -Wold-style-cast \
    -I"$DRV" -isystem"$SIGFM" $OCV_CFLAGS \
    -c "$DRV/goodix_sigfm_metrics.cpp" -o "$B/metrics.o"

# 3) sigfm.cpp (THIRD_PARTY reference, relaxed: -Wall -Wextra only)
g++ -std=c++17 -O2 -g -Wall -Wextra \
    -I"$SIGFM" $OCV_CFLAGS -c "$SIGFM/sigfm.cpp" -o "$B/sigfm.o"

# 4) real test (project C++, full -Werror)
g++ -std=c++17 -O2 -g -Wall -Wextra -Werror -Wconversion -Wshadow -Wold-style-cast \
    -I"$DRV" -isystem"$SIGFM" -I"$TEST" \
    -c "$TEST/test_goodix_sigfm_metrics_real.cpp" -o "$B/test.o"

# 5) link
g++ "$B/adapter.o" "$B/metrics.o" "$B/sigfm.o" "$B/test.o" $OCV_LIBS \
    -o "$B/test-goodix-sigfm-real"

# 6) synthetic runtime (SYNTHETIC_ONLY, NO_TARGET_IMAGE, NO_CAPTURE)
"$B/test-goodix-sigfm-real"
# -> goodix real SIGFM synthetic plumbing: PASS
```

## Sanitizer pass (classified separately)

Same sources with `-O1 -fno-omit-frame-pointer -fsanitize=address,undefined`
on compiler invocations; run with
`ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1`.
Result: **PASS (ASan/UBSan clean)**.

## Reproducible harness

`libfprint-driver/tests/run_goodix_sigfm_metrics_real_host.sh` replays the above
with fail-closed behavior:

- if `pkg-config --exists opencv4` is false -> prints
  `REAL_SIGFM_EXECUTABLE_CLOSURE=BLOCKED_ENVIRONMENT` and
  `REAL_SIGFM_DEPENDENCY=BLOCKED_OPENCV4_DEV_UNAVAILABLE`, then **exits 77**
  (conventional SKIP, not a fake PASS);
- dependency present + all PASS -> exit 0; real build/link/runtime failure ->
  exit 1;
- prints `SKIP/NOT_AVAILABLE` vs `FAIL` vs `PASS` explicitly;
- no USB / fprintd / secret / mandatory network at runtime;
- no package auto-install, no system modification, no OpenCV vendoring, no
  production-threshold change;
- objects/binaries only under `mktemp -d /tmp/...`, cleaned on exit;
- sanitizer pass prints `REAL_SIGFM_ASAN_UBSAN_STATUS`, `LEAK_DETECTION=DISABLED`
  and `MEMORY_SAFETY_SCOPE=ASAN_UBSAN_RUNTIME_NO_DETECTED_ADDRESS_OR_UB_ERRORS_LEAKS_NOT_ASSESSED`.

## Source artifacts & git blob SHAs (reference state)

| Path | Blob SHA |
| --- | --- |
| libfprint-driver/goodix_u16_to_fpimage.c | 84ae49ca23bc0e4496f18e3f2a5c84327ddf269d |
| libfprint-driver/goodix_u16_to_fpimage.h | e07710e625a367afad20dc8f1cfc5e76389b07e4 |
| libfprint-driver/goodix_sigfm_metrics.cpp | 16f92888fae8eb6fffc0be07d429a43ec8b1a452 |
| libfprint-driver/goodix_sigfm_metrics.h | 0a697b1aa8444021c65109fde84e81f7d027ed2c |
| libfprint-driver/tests/test_goodix_sigfm_metrics_real.cpp | ccf752d56d029a54a2c664852ceb2453e2d74914 |
| Rockytkg/libfprint/libfprint/sigfm/sigfm.cpp | 1ade7b30b5bb65a2d1e9528aaf0fd5c8716662ff |
| Rockytkg/libfprint/libfprint/sigfm/sigfm.h | 671a2b6df9140b729cf52651d0c395a9d54fceb6 |
| Rockytkg/libfprint/libfprint/sigfm/binary.hpp | f76b5dabd9c5c336f2d294f830631f892ba01481 |
| Rockytkg/libfprint/libfprint/sigfm/img-info.hpp | 42967b69d534784abb7951735aca144bb5b7ec2e |
| libfprint-driver/tests/run_goodix_sigfm_metrics_real_host.sh | 44249118d3264f440761c59f6dd1f3fe002037a5 |

Third-party SIGFM files: explicit LGPL-2.1-or-later license header verified
(NO literal SPDX tag claimed), **unmodified** in `Rockytkg/`. No new ledger
entry required (no new import/adaptation).

## Windows operator kit integrity

`analysis/D274/D274_03_windows_oem_second_cycle_operator_kit/invoke-d274-03-live-once.ps1`
git blob SHA = `fca3c40d4a3fcd7c6c21ce6809de794d69908e7a` (preserved).
`D274_03_OPERATOR_KIT_MODIFIED=false`, `LIVE_CRITICAL_SET_MODIFIED=false`.

## Regression executed (host-only)

- `goodix_u16_to_fpimage` unit test: PASS
- `goodix_sigfm_metrics` synthetic/double (+ forbidden-symbol audit): PASS
- `goodix_fpimage_pipeline` test: NOT_RUN_ENVIRONMENT_LIMITATION — its historical
  Flatpak SDK harness (`run_goodix_fpimage_pipeline_test.sh`) requires the
  Flatpak SDK + libfprint framework headers, unavailable in this executor. This
  is an environment/toolchain limitation, **not** caused by
  `LOCAL_LIBFPRINT_DEVICE_GLUE=NOT_YET_IMPLEMENTED` (the pipeline helper is an
  independent D270 component).
