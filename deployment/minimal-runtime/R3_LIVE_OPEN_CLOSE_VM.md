<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R3 first live gate: enumeration and one Claim/Release

**HUMAN_REQUIRED. VM execution by the user only.** No reinstall or rebuild.
The user reports clean replacement and stock load **PASS**: source
`b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`, install
`264cd7ff1ba77857e1985502f299e4375f9a0516`, five private libraries, system
libgusb, stock `/usr/libexec/fprintd`, no Fedora replacement. The service is
inactive/MainPID 0 and the sensor has not yet been accessed in this VM.
Normal and ASan/UBSan synthetic results are 44/44 PASS each.

This gate is explicitly **one open/close, zero physical capture contacts**,
not the three-attempt recognition series. Claim <= 1, Release <= 1, no retry.
Do not use fingerprint settings, lock the session, enroll, verify, delete
prints or run another fingerprint client during the gate. Normal sudo/Polkit
password authorization is allowed; no policy/configuration changes.

## Source review before handoff

Reviewed the qualified source against the following paths:

- Stock `reference/fprintd-fedora44-1.94.5/source/src/device.c`:
  `fprint_device_claim()` calls `fp_device_open()` once; Release calls close.
  Both use the D-Bus sender's session. Client disappearance only cleans up;
  failed open/close is not retried. `utils/list.c` and
  `fprint_device_list_enrolled_fingers()` list host-stored templates without
  Claim/open. No enrolled fingers is an acceptable listing result.
- Canonical libfprint `fp-device.c` opens GUsb before `fp-image-device.c`
  forwards to `img_open`; successful open stays INACTIVE. Goodix has no
  device-specific probe callback. Enumeration includes normal USB discovery
  and libfprint's transient kernel wakeup/USB-persist settings, not firmware
  or factory-state writes.
- `libfprint-driver/goodix_fpimage_device.c`: production `img_open` acquires
  existing protected material read-only, then claims interface 0 with
  `G_USB_DEVICE_CLAIM_INTERFACE_NONE`. Context/backend construction submits
  nothing; open does not begin a generation. Activation starts the protocol.
  Close releases interface/materials, cleanses memory and logs the existing
  `GOODIX_PRODUCTION_EPOCH_AUDIT`. The private login-preparation signal is
  another protocol entry, but stock fprintd and this helper never invoke it.
- `goodix_runtime_material.c`, `goodix_target_material.c` and
  `goodix_runtime_inputs.c`: directory root:root 0700, five direct regular
  files root:root 0600, no-follow/read-only loader. Metadata preflight cannot
  prove contents or SELinux access; the real loader performs those checks
  during Claim. No copying, printing, hashing or regenerating protected data.

Classification confirmed: below biometric activation. The helper opens one
private **system-bus connection**, uses GetDefaultDevice, Claim("") and one
finally-path Release on that same connection. Calls have 15-second deadlines
and NO_AUTO_START; failed calls are not retried. Even a local reporting error
after successful Claim reaches Release. An ambiguous Claim timeout is FAIL:
close the bus and let stock owner-loss cleanup run, never issue another Claim.

## 1. Preflight — sensor still absent

Use the same ordinary VM user and shell for all blocks. Stop at any failure.
Do not install missing dependencies or provision materials for this gate.
These files remain in the checkout; nothing is installed in the runtime.

```bash
r3_repo=$(git rev-parse --show-toplevel)
r3_out=$(mktemp -d "$HOME/goodix-r3-open-close-XXXXXXXX")
(
  set -euo pipefail
  cd "$r3_repo"
  test "$(git branch --show-current)" = development
  test -z "$(git status --porcelain)"
  git pull --ff-only origin development
  git rev-parse HEAD
  systemd-detect-virt --vm
  . /etc/os-release
  test "$ID" = fedora
  test "$VERSION_ID" = 44
  test "$(uname -m)" = x86_64
  test "$(getenforce)" = Enforcing
  test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
  test "$(systemctl show fprintd.service -p MainPID --value)" = 0
  rpm -V fprintd libfprint
  test "$(systemctl show fprintd.service -p FragmentPath --value)" = /usr/lib/systemd/system/fprintd.service
  systemctl show fprintd.service -p ExecStart -p Environment
  python3 -B -c 'import gi; gi.require_version("Gio", "2.0"); from gi.repository import Gio, GLib; print("R3_GIO_DEPENDENCY=PASS")'
  command -v fprintd-list timeout >/dev/null
  for device in /sys/bus/usb/devices/*; do
    if [[ -f $device/idVendor && -f $device/idProduct &&
          $(<"$device/idVendor") == 27c6 && $(<"$device/idProduct") == 5125 ]]; then
      echo R3_PREFLIGHT=FAIL_SENSOR_PRESENT >&2
      exit 1
    fi
  done
  sudo python3 -B - <<'PY'
import hashlib
import json
from pathlib import Path
import stat
runtime = Path('/usr/local/lib64/goodix-27c6-5125')
state = json.loads((runtime / 'installation.json').read_text())
assert state['build_commit'] == 'b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226'
assert state['install_commit'] == '264cd7ff1ba77857e1985502f299e4375f9a0516'
for name in ('libfprint-2.so.2.0.0', 'libopencv_core.so.413',
             'libopencv_features2d.so.413', 'libopencv_flann.so.413', 'libopencv_imgproc.so.413'):
    assert hashlib.sha256((runtime / name).read_bytes()).hexdigest() == state['files'][name]
print('R3_INSTALLED_PROVENANCE_AND_LIBRARY_HASHES=PASS')
# Metadata only below: never open/read/hash protected file contents.
material = Path('/var/lib/goodix-5125-poc')
assert material.resolve(strict=True) == material
info = material.lstat()
assert stat.S_ISDIR(info.st_mode) and (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 0, 0o700)
for name in ('target-material-manifest.json', 'transport-material.bin',
             'target-config-90.bin', 'gfusb.dll', 'fdt-cache.bin'):
    info = (material / name).lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_size > 0
    assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 0, 0o600)
print('R3_MATERIAL_METADATA=PASS DIRECTORY=root:root:0700 FILES=5_root:root:0600')
PY
  echo R3_PREFLIGHT=PASS
)
```

Require `ExecStart=/usr/libexec/fprintd` and only the accepted project library
environment, with no new override. If preflight fails, **STOP before attaching
or claiming**. In particular, absent Gio or invalid material metadata is a
preflight failure, not permission to install packages/copy materials. Metadata
checks use stat only; they do not touch timestamps for evidence.

## 2. Human attachment, then one invocation

Only after preflight PASS, record the start of the journal window:

```bash
r3_since=$(date -u '+%Y-%m-%d %H:%M:%S.%6N UTC')
```

**HUMAN PHYSICAL STEP: pass through/connect exactly one Goodix `27c6:5125`
to the VM now. Do not touch the sensor surface.** Do not attach another
fingerprint device. Then paste this entire block once. It checks the guest
sysfs identity, starts the stock service, lists templates and runs the helper.
The listing must identify exactly one `Goodix 27c6:5125 Fingerprint Sensor`.
The output may say no enrolled fingers; that does not prevent this gate.

```bash
(
  set -euo pipefail
  export LC_ALL=C
  cd "$r3_repo"
  # Always stop the service on success/error; this is cleanup, not a retry.
  trap 'sudo systemctl stop fprintd.service' EXIT
  test "$(getenforce)" = Enforcing
  test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
  test "$(systemctl show fprintd.service -p MainPID --value)" = 0
  r3_devices=0
  for device in /sys/bus/usb/devices/*; do
    if [[ -f $device/idVendor && -f $device/idProduct &&
          $(<"$device/idVendor") == 27c6 && $(<"$device/idProduct") == 5125 ]]; then
      r3_devices=$((r3_devices + 1))
    fi
  done
  test "$r3_devices" = 1
  echo R3_VM_SENSOR_COUNT=1
  sudo systemctl start fprintd.service
  r3_pid=$(systemctl show fprintd.service -p MainPID --value)
  test "$r3_pid" -gt 0
  test "$(sudo readlink "/proc/$r3_pid/exe")" = /usr/libexec/fprintd
  timeout --signal=TERM --kill-after=2s 15s fprintd-list "$USER" | tee "$r3_out/list.txt"
  grep -Fxq 'found 1 devices' "$r3_out/list.txt"
  grep -Fq 'Goodix 27c6:5125 Fingerprint Sensor' "$r3_out/list.txt"
  timeout --signal=TERM --kill-after=2s 55s python3 -B \
    deployment/minimal-runtime/r3_open_close.py | tee "$r3_out/helper.txt"
)
```

A stock idle exit, error or timeout is **not** an invitation to restart/retry
this live run. Preserve the result. The helper's PASS is only its method
sequence; the journal/final-state checks below are also mandatory. If the
stop trap failed, run `sudo systemctl stop fprintd.service` for cleanup only.
Do not run the helper a second time or use separate gdbus Claim/Release calls.

## 3. Human detachment and bounded evidence — also after failure

**HUMAN PHYSICAL STEP: detach/remove the sensor passthrough from the VM now.**
Keep the qualified R3 runtime installed, including on failure. Then:

```bash
(
  set -euo pipefail
  test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
  test "$(systemctl show fprintd.service -p MainPID --value)" = 0
  for device in /sys/bus/usb/devices/*; do
    if [[ -f $device/idVendor && -f $device/idProduct &&
          $(<"$device/idVendor") == 27c6 && $(<"$device/idProduct") == 5125 ]]; then
      echo R3_FINAL=FAIL_SENSOR_STILL_PRESENT >&2
      exit 1
    fi
  done
  systemctl show fprintd.service -p ActiveState -p MainPID
  echo R3_FINAL=PASS SENSOR_CONNECTED=false RUNTIME_PRESERVED=true
)
r3_until=$(date -u '+%Y-%m-%d %H:%M:%S.%6N UTC')
sudo journalctl -b -u fprintd.service --since "$r3_since" --until "$r3_until" \
  --no-pager -n 201 -o cat > "$r3_out/fprintd.log"
```

Review only this bounded service window. Check **all** captured messages, not
just the last audit line. More than 200 lines, missing audit, suppressed logs
or a failed journal query means incomplete evidence: STOP, no PASS and no
repeat live. Run this read-only check even if the helper failed:

```bash
python3 -B - "$r3_out/fprintd.log" <<'PY'
from pathlib import Path
import re
import sys
with Path(sys.argv[1]).open('rb') as stream:
    data = stream.read(65537)
assert len(data) <= 65536, 'STOP: journal byte bound reached'
text = data.decode('utf-8')
assert len(text.splitlines()) < 201, 'STOP: journal line bound reached'
for marker in ('GOODIX_STOCK_CAPTURE_', 'GOODIX_LOGIN_', 'GOODIX_SIGFM_',
               'Activating image device', 'Image device activation',
               'Image device captured an image', 'start verification device',
               'start identification device', 'start enrollment device'):
    assert marker not in text, 'FAIL: unexpected activation marker ' + marker
assert not re.search(r'suppressed|dropped [0-9]+ messages', text, re.I), 'STOP: incomplete journal'
audit = [line.split('GOODIX_PRODUCTION_EPOCH_AUDIT ', 1)[1] for line in text.splitlines()
         if 'GOODIX_PRODUCTION_EPOCH_AUDIT ' in line]
assert len(audit) == 1, 'FAIL/STOP: expected exactly one closed epoch audit'
fields = dict(token.split('=', 1) for token in audit[0].split())
zero = '''attempts rejected logical_actions capture_attempts capture_terminal
identify_enroll_handoffs identify_enroll_armed consumed tls first_image
release_tail single_terminal rearm32 enroll_stages enroll_rearm32 enroll_terminal
enroll_contacts enroll_retry_scans secure_retry post_retry reopen explicit_verify_reopen
explicit_identify_reopen reset clear_halt persistent sigfm_baseline_pinned
sigfm_baseline_reused real_submit outstanding'''.split()
expected = dict.fromkeys(zero, '0')
expected.update(action='FPI_DEVICE_ACTION_NONE', transport_epochs='1', drained='1', context_closed='1')
assert fields == expected, 'FAIL: unexpected action/submit/cleanup audit'
print('GOODIX_PRODUCTION_EPOCH_AUDIT ' + audit[0])
print('R3_NEGATIVE_ACTIVATION_CHECK=PASS NO_BIOMETRIC_ACTIVATION=true NO_CAPTURE=true NO_ENROLLMENT=true')
print('NO_PERSISTENT_DEVICE_WRITE=PASS_SOURCE_AND_AUDIT REAL_SUBMIT=0')
PY
```

`transport_epochs=1` counts the claimed open epoch, not an activated protocol
session. `action=FPI_DEVICE_ACTION_NONE`, zero action/capture/TLS/submit/retry/
persistent fields and drained/context_closed=1 are the expected close audit.
This combines reviewed source, bounded method calls and driver telemetry; it
is not a wire capture or a readback of factory memory. Normal USB discovery
and interface management are real USB access, not project protocol capture.

## Result and return

**PASS_IF:** preflight and exact-one enumeration pass; helper reports successful
Claim and Release once; exactly one expected epoch audit and no activation
marker; no warning/error or unexpected client/action in the window; final
inactive/MainPID 0, sensor detached, runtime preserved. Do not proceed to
recognition. A PASS of only the helper is insufficient.

**FAIL/STOP:** any unexpected activation/capture marker, wrong device/count,
failed/ambiguous Claim or Release, material/permission error, timeout, incomplete
journal or failed cleanup. Never hide logs, relax checks or retry. Stop fprintd
if possible, detach the sensor and retain the installed runtime. For this
explicit user task, failure cleanup is stop/detach, **not uninstall**. The saved
inverse stays available; the cold snapshot remains an external lab fallback.

Return helper markers, enumeration result (one Goodix; enrolled/none is enough,
no finger names needed), preflight/final result, source/install/handoff SHAs,
journal window and the one epoch audit/negative-check result. Retain `$r3_out`.
On failure return the exact stage, sanitized helper error name and at most 40
relevant fprintd/Goodix error lines from this same window, without protected or
biometric contents. No broad logs or material contents.

Classify evidence before a corrective: metadata/dependency failure =
material-preflight or fixture-helper; absent/wrong guest USB identity = VM
passthrough; D-Bus/authorization/enumeration failure = stock framework unless
evidence says otherwise; driver open/close failure = production/material access
candidate, requiring review. Never infer driver responsibility from a helper
failure. No production patch follows automatically from a failed gate.

Offline checks use `python3 -B deployment/minimal-runtime/test_r3_open_close.py`:
mock connection/method order, successful-Claim cleanup on local error/interrupt,
no failed-call retry, finite deadlines, explicit method allowlist and no live
loop. No VM, service, protected content or USB access by the AI.
