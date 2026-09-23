<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R3: one native enrollment in the VM

**COMPLETED — acquisition/storage PASS with a reported finger-label mismatch.**
On 22 September 2026, `guido` enrolled the physical **RIGHT index** under the
label `left-index-finger`, as clarified by the user before any verify. Eight
stages/contacts completed; the final listing contains that label. Both epochs
closed/drained, fprintd inactive/MainPID 0, sensor detached, runtime/template
retained, no rollback.
The canonical manual contains the complete telemetry and review. Preserve the
procedure below as evidence; **do not repeat it**. Subsequent
[native verification of the RIGHT index using that stored label](R3_VERIFY_VM.md)
also passed at the first attempt. R3 is closed; the current human gate is
[R4 stock PolicyKit live procedure](R4_POLKIT_VM.md), password first with reader detached.
KScreenLocker and ordinary sudo are SUPPORTED on the tested baseline, with a
documented recurring non-fatal nr_hugepages read denial. Their completed tests
must not be repeated.
The historical procedure below records the requested slot, not evidence that
the physical left index was presented. No storage relabeling has been performed.

## Completed procedure

**HUMAN_REQUIRED — real USB and enrollment are human-executed only.**
Claim/Release is closed by the 22 September user handoff. This gate advances
into biometric activation and host template storage using stock `fprintd-enroll`.
It does not repeat open/close qualification or qualify verify, PAM/KDE or R5.

Use the existing Fedora 44 KDE x86_64 VM and the same local user. Retain build
`b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`, install
`264cd7ff1ba77857e1985502f299e4375f9a0516`, corrected runtime-v1 manifest,
reconciled receipt and SELinux Enforcing. The handoff identity is the full
`development` SHA printed below; it is provenance, not another approval step.

No new runtime patch is needed. The deployment JSON corrective runs from the
checkout during preflight; it does not replace the installed inverse or libraries.
The retained installation/rollback pair is [install.sh](install.sh) and the
**saved** `/usr/local/lib64/goodix-27c6-5125/uninstall.sh`. Do not reinstall,
rebuild, relabel or reconcile again. If that baseline is missing/drifted, STOP.
Its original installation is documented in [README.md](README.md).

## 1. Preflight with the sensor disconnected

Run from the VM's repository in one ordinary-user Bash terminal. No fingerprint
settings or other biometric client may run during the test. Sudo and standard
PolicyKit password prompts are expected; do not change authentication policies.
Stop on every failed block. No dependencies or protected inputs are provisioned.

The previous preflight stopped at `require_stopped` before any live attempt;
the later observation was inactive/dead, MainPID 0, Result success, with no
start timestamp. The state at the failed check was not recorded, so a specific
activation/exit cause is not established. This revision explicitly stops
fprintd once, **after VM/root/reader-absence checks**, then verifies its state.
The check itself remains read-only and reports the observed fields on failure.
No polling, automatic retry, masking or service configuration change is added.

```bash
r3_repo=$(git rev-parse --show-toplevel)
r3_user=$(id -un)
(
  set -euo pipefail
  cd "$r3_repo"
  test "$(git branch --show-current)" = development
  test -z "$(git status --porcelain)"
  git pull --ff-only origin development
  git rev-parse HEAD
  test "$r3_user" != root
  getent -s files passwd "$r3_user" >/dev/null
  command -v fprintd-list fprintd-enroll timeout >/dev/null
  sudo python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.machine_gate()                    # VM, root, reader absent; no USB handle
d.run('systemctl', 'stop', d.UNIT)   # Human VM preparation, synchronous, once
d.require_stopped()
d.install_preflight()               # Fedora, stock service/RPM, Enforcing
d.run('rpm', '-V', 'libfprint')
state = d.inspect_owned()           # Saved files, hashes, links and drop-in
assert d.DROPIN.exists()
assert state['install_commit'] == '264cd7ff1ba77857e1985502f299e4375f9a0516'
assert state.get('material_manifest_reconciled') is True
assert state['material_selinux']['phase'] == 'ready'
d.check_material_record(state['material_selinux'])
assert d.runtime_manifest_preflight() == '1b98bf54925cf9608ee8bf4e7d2f811f535c3c9395ea2eaf38fe18fb017aacc8'
critical = ['libfprint-driver', 'reference/libfprint-fedora44-1.94.100',
            'Rockytkg/libfprint/libfprint/sigfm', 'production/build-inner.sh',
            'production/build-support', 'production/minimal-runtime/build.sh',
            'production/check-source.sh', 'production/source-files.tsv',
            'production/source-files.sha256', 'production/host-test-only-symbols.txt']
d.git('diff', '--exit-code', d.BUILD_COMMIT, 'HEAD', '--', *critical)
d.require_stopped()                 # Still inactive after the read-only checks
print('R3_ENROLL_PREFLIGHT=PASS SENSOR_CONNECTED=false')
PY
)
```

This reads the non-secret manifest and runtime software only; the four binary
materials are checked by metadata. The production driver will load them read-only
during the human live action. Any preflight failure means STOP before attachment.
If the service is reactivated or state collection fails, return the complete
observed-state error; do not repeatedly stop it or rerun the block. This is a
continuation of the first enrollment gate, not a second biometric attempt.

## 2. Select a free finger slot, then enroll once

**Human step:** connect/pass through exactly one Goodix `27c6:5125` to the VM.
Use a finger not previously enrolled for any VM account. The example chooses
`left-index-finger`; change that assignment if necessary to another standard
finger name. **Do not choose an existing slot:** stock fprintd deletes its old
template before replacement. No template deletion/overwrite is part of this gate.

Paste the block once. It lists existing slots and refuses an occupied choice
before EnrollStart. It uses the ordinary CLI, with one invocation and a finite
timeout; there is no wrapper-driven retry or second enrollment on failure.

```bash
r3_finger=left-index-finger
r3_since=$(date -u '+%Y-%m-%d %H:%M:%S.%6N UTC')
(
  set -euo pipefail
  export LC_ALL=C
  cd "$r3_repo"
  systemd-detect-virt --vm --quiet
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
  case "$r3_finger" in
    left-thumb|left-index-finger|left-middle-finger|left-ring-finger|left-little-finger|right-thumb|right-index-finger|right-middle-finger|right-ring-finger|right-little-finger) ;;
    *) echo 'STOP: invalid finger name' >&2; exit 1 ;;
  esac
  trap 'sudo systemctl stop fprintd.service' EXIT
  sudo systemctl start fprintd.service
  r3_list=$(timeout --signal=TERM --kill-after=2s 15s fprintd-list "$r3_user")
  printf '%s\n' "$r3_list"
  printf '%s\n' "$r3_list" | grep -Fxq 'found 1 devices'
  printf '%s\n' "$r3_list" | grep -Fq 'Goodix 27c6:5125 Fingerprint Sensor'
  case "$r3_list" in
    *"$r3_finger"*) echo 'STOP: selected finger already enrolled; preserve it' >&2; exit 1 ;;
  esac
  timeout --signal=TERM --kill-after=5s 180s fprintd-enroll -f "$r3_finger" "$r3_user"
  timeout --signal=TERM --kill-after=2s 15s fprintd-list "$r3_user"
)
```

Follow the normal enrollment prompt with the selected finger, lifting fully
between contacts and slightly varying its placement. The stock duplicate check
may consume one initial contact; a duplicate terminates this invocation. The
enrollment policy accepts at most eight template stages and technically bounds
its diversity retries to 20 physical contacts. Thus this invocation permits at
most **one duplicate-check contact + 20 enrollment contacts**, stopping earlier
at completion/error. `enroll-retry-scan` during enrollment can be a normal
bounded diversity rejection; it is not permission to restart the command.
Stop touching immediately at a terminal result. A request beyond the bound,
crash, timeout, duplicate or unexpected error means STOP, no new attempt.

The duplicate IDENTIFY is the native one-shot enrollment precondition, not a
three-attempt verification series (§8.2 boundary exception). A match terminates
as duplicate; only clean NO_MATCH/cleanup permits the single ENROLL handoff.
The existing driver fences processing errors before any automatic stock
resubmission can reacquire materials/USB. This gate adds no retry mechanism.

## 3. Cleanup, observation and result

The block stops fprintd on exit. If it failed to stop, run
`sudo systemctl stop fprintd.service` for cleanup only. **Detach the sensor from
the VM now**, on success and failure. Do not launch verification yet.

```bash
r3_until=$(date -u '+%Y-%m-%d %H:%M:%S.%6N UTC')
systemctl show fprintd.service -p ActiveState -p MainPID
sudo journalctl -b -u fprintd.service --since "$r3_since" --until "$r3_until" \
  --no-pager -o cat -n 21 \
  --grep='GOODIX_(PRODUCTION_EPOCH_AUDIT|STOCK_CAPTURE_(BEGIN|RESULT|REJECT))'
```

These are existing safety counters, not a new log collector. Return their
complete lines; no images, templates, material contents or broad logs. An empty
result or the 21-line limit means incomplete evidence and STOP, never rerun live
to fill it. On success expect one IDENTIFY BEGIN/result NO_MATCH, its closed
epoch audit, and a closed ENROLL epoch audit with `identify_enroll_handoffs=1`,
`enroll_terminal=1`, `enroll_stages` at most 8 and `enroll_contacts` at most 20.
Both epochs must have `secure_retry=0 post_retry=0 reset=0 clear_halt=0
persistent=0 outstanding=0 drained=1 context_closed=1`. Unexpected activation,
rejection or cleanup counters need review before proceeding. This is source and
runtime telemetry evidence, not a readback of factory memory.

**PASS_IF:** CLI reports `enroll-completed`, exits normally, the final listing
contains the new finger and preserves previous entries, contacts respect the
bounds, the expected cleanup telemetry is present, fprintd is inactive/MainPID 0
and the reader is detached. Keep the runtime and new template after PASS.

**FAIL_IF:** enrollment cannot complete, the template is missing, prior slots
change, or errors/bounds/cleanup fail. **STOP_IF:** wrong VM/device/user,
preflight drift, occupied slot, duplicate, unexpected client/action or incomplete
evidence. Do not restart enrollment, adjust policies, copy materials or rebuild.

Return full checkout SHA, chosen finger, approximate physical contact count,
CLI result/listing, the safety lines above, final inactive/detached state and
whether runtime/template remain. On failure include the exact message and stage;
additional diagnostics will be requested only as needed after that failure.

## Rollback on live failure or instability

After stopping fprintd and detaching the sensor, use the inverse saved with the
installed baseline, not an unrelated historical uninstaller:

```bash
sudo /usr/local/lib64/goodix-27c6-5125/uninstall.sh
systemctl show fprintd.service -p FragmentPath -p ExecStart -p Environment -p ActiveState -p MainPID
rpm -V fprintd libfprint
test ! -e /usr/local/lib64/goodix-27c6-5125
test ! -e /etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf
```

It removes the private runtime and its environment drop-in, removes only its
owned material mapping and restores current Fedora default labels, reloads the
unit and restores the previously recorded service active/inactive state.
Expected: vendor `/usr/libexec/fprintd`, no project library environment and clean
RPM verification. The converted manifest, four materials and all host templates
are preserved. Any inverse drift/failure means retain the state and report it;
do not force deletion. A preflight/occupied-slot stop before enrollment needs
no uninstall because the retained baseline has not failed a live action.
No rollback on PASS. R3 verify is the next step after review of this result.
