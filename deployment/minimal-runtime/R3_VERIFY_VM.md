<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R3: verify the right index stored as left-index-finger in the VM

**COMPLETED — stock VERIFY PASS at the first attempt; R3 biometric boundary closed.**
The user reported `verify-match (done)`, CLI exit 0, one capture/epoch,
release_tail=1/single_terminal=1 and closed/drained resources, with zero
retry/reset/persistent families observed. No second verify or rollback;
runtime/template retained, sensor detached, fprintd inactive/MainPID 0.
The canonical manual contains the complete evidence and review. The RIGHT-index
template still has the left-index label; preserve it as known laboratory state.
**Do not repeat the completed procedure below.** The current human gate is
[R4 native stock KScreenLocker unlock](R4_KSCREENLOCKER_VM.md);
the configuration query has passed without a configuration change.

## Completed procedure and its original criteria

**HUMAN_REQUIRED — VM service operations, real USB and verification are human-only.**
The 22 September enrollment is accepted for acquisition/storage/cleanup:
`enroll-completed`, eight enrollment contacts/stages and closed, drained epochs.
The user clarified which physical finger was used before any verification: the template
contains the **RIGHT index**, but its stored label is **`left-index-finger`**.
The earlier instruction to touch with the left index was superseded before the
successful verify. The label mismatch has not been repaired in host storage.

| Item | Value for this gate |
| --- | --- |
| Account | `guido` |
| Stored template label / CLI `-f` argument | `left-index-finger` |
| Physical finger to present | **RIGHT index** |

Keep `-f left-index-finger`: it selects the existing template. Changing the
argument to `right-index-finger` would select a different slot. Stock prompts
will still say `left-index-finger`; for this documented mismatch, present the
**RIGHT index**. The matcher compares biometric samples, not anatomical labels.
Do not rename/move/edit template files, delete a slot or enroll again for this
gate. Correct label-to-anatomy assignment remains unresolved for normal consumer
use; a MATCH here would qualify recognition of the reported right index only.

This gate tests recognition through stock `fprintd-verify`, using that template.
It does not qualify PAM/KDE, update survivability, wrong-finger rejection or a
series inside one Claim. Use up to **three explicitly started CLI invocations**
with the physical right index. Stop at the first MATCH; continue after the first
or second clean NO_MATCH only. No fourth invocation, automatic loop or retry.

Stock CLI makes one VerifyStart per Claim; the driver bounds each admitted
capture and fences processing errors before automatic resubmission can reach
the sensor again. Each CLI invocation starts a fresh Claim and its telemetry
starts at `attempt=1`. The three-invocation scope is the human test boundary,
not a driver-enforced cumulative series. The user's stock-consumer policy and
the absence of a driver cap after clean NO_MATCH remain unchanged. See
[the source audit](../../docs/STOCK_FPRINTD_ATTEMPTS.md).

## Retained installation and preflight

Keep build `b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`, install
`264cd7ff1ba77857e1985502f299e4375f9a0516`, corrected runtime-v1 manifest,
reconciled receipt, SELinux Enforcing and the new host template. No runtime
patch, rebuild, reinstall, enrollment or repeated Claim/Release test is needed.
The installation/rollback pair remains [install.sh](install.sh) and the
**saved** `/usr/local/lib64/goodix-27c6-5125/uninstall.sh`; the completed
installation is recorded in [README.md](README.md).

With the sensor disconnected, use one ordinary-user Bash terminal in the
existing Fedora 44 KDE x86_64 VM clone, logged in as `guido`. Close fingerprint
settings and all other biometric clients. Normal sudo/PolicyKit password prompts
are expected; do not change authentication policies. Stop on a failed block.

```bash
r3_repo=$(git rev-parse --show-toplevel)
(
  set -euo pipefail
  cd "$r3_repo"
  test "$(git branch --show-current)" = development
  test -z "$(git status --porcelain)"
  git pull --ff-only origin development
  git rev-parse HEAD
  test "$(id -un)" = guido
  getent -s files passwd guido >/dev/null
  command -v fprintd-list fprintd-verify timeout >/dev/null
  sudo python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.machine_gate()                    # VM, root, reader absent; no USB handle
d.run('systemctl', 'stop', d.UNIT)   # Human VM preparation, synchronous, once
d.require_stopped()
d.install_preflight()               # Fedora, stock service/RPM, Enforcing
d.run('rpm', '-V', 'libfprint')
print(d.run('rpm', '-q', 'fprintd', 'libfprint'))
state = d.inspect_owned()
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
d.require_stopped()
print('R3_VERIFY_PREFLIGHT=PASS SENSOR_CONNECTED=false')
PY
)
```

The full checkout SHA and installed package versions are evidence for review,
not another authorization step. Only the non-secret manifest and runtime
software are read; protected binary materials are checked by metadata. If the
baseline has drifted or the service is reactivated, STOP and return the error.
Do not repeatedly stop/retry the preflight or change the installed inverse.

## One native invocation, then inspect its result

**Human step:** attach exactly one Goodix `27c6:5125` to the VM. Paste this block
once. Touch with the **RIGHT index finger** only when prompted; lift fully when
the result appears and wait for the command and cleanup to finish. Do not touch
again within this invocation. A retry prompt, error or timeout means STOP.

```bash
(
  set -euo pipefail
  export LC_ALL=C
  cd "$r3_repo"
  test "$(id -un)" = guido
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
  r3_since=$(date -u '+%Y-%m-%d %H:%M:%S.%6N UTC')
  trap 'sudo systemctl stop fprintd.service' EXIT
  sudo systemctl start fprintd.service
  r3_list=$(timeout --signal=TERM --kill-after=2s 15s fprintd-list guido)
  printf '%s\n' "$r3_list"
  printf '%s\n' "$r3_list" | grep -Fxq 'found 1 devices'
  printf '%s\n' "$r3_list" | grep -Fq 'Goodix 27c6:5125 Fingerprint Sensor'
  printf '%s\n' "$r3_list" | grep -Eq '^[[:space:]]*- #[0-9]+: left-index-finger$'
  printf '%s\n' 'Stored label: left-index-finger; physically use the RIGHT index finger.'
  r3_cli_exit=0
  timeout --signal=TERM --kill-after=5s 60s fprintd-verify -f left-index-finger guido || r3_cli_exit=$?
  printf 'R3_VERIFY_CLI_EXIT=%s\n' "$r3_cli_exit"
  sudo systemctl stop fprintd.service
  trap - EXIT
  r3_until=$(date -u '+%Y-%m-%d %H:%M:%S.%6N UTC')
  systemctl show fprintd.service -p ActiveState -p MainPID
  sudo journalctl -b -u fprintd.service --since "$r3_since" --until "$r3_until" \
    --no-pager -o cat -n 21 \
    --grep='GOODIX_(PRODUCTION_EPOCH_AUDIT|STOCK_CAPTURE_(BEGIN|RESULT|REJECT))'
)
```

The block retains the CLI exit status while allowing cleanup and existing
safety telemetry to print. Its own exit status is not the biometric result.
Exit `1` alone is **not** a clean NO_MATCH: stock CLI also uses it for errors.
No code in the block schedules another invocation. The only loop counts USB
identities through sysfs; it does not open the reader or run verification.

Inspect each invocation before deciding whether another is permitted:

| Observation | Action |
| --- | --- |
| `Verify result: verify-match (done)`, CLI exit 0 and complete safety evidence below | PASS, stop the series immediately |
| `verify-no-match (done)`, CLI exit 1, driver `outcome=NO_MATCH terminal=0` and clean release/cleanup; this was invocation 1 or 2 | Lift fully; manually run the same block once more with the same finger |
| Third consecutive clean NO_MATCH | FAIL, no fourth invocation |
| Retry prompt, timeout, error, missing template, unexpected action/client, incomplete evidence or bad cleanup | STOP, no further invocation; report the exact failure |

Each completed verification must show one `GOODIX_STOCK_CAPTURE_BEGIN`
(`attempt=1 action=VERIFY`), one matching RESULT and one final EPOCH_AUDIT:
`action=FPI_DEVICE_ACTION_VERIFY attempts=1 rejected=0 logical_actions=1
transport_epochs=1 capture_attempts=1 consumed=1 tls=1 first_image=1`.
`capture_terminal`/RESULT `terminal` must be 1 for MATCH, 0 for clean NO_MATCH.
No IDENTIFY/ENROLL action, handoff or enrollment contacts/stages are expected.
Require `secure_retry=0 post_retry=0 reopen=0 explicit_verify_reopen=0
explicit_identify_reopen=0 rearm32=0 reset=0 clear_halt=0 persistent=0
sigfm_baseline_pinned=1 sigfm_baseline_reused=0 outstanding=0 drained=1
context_closed=1`, plus final inactive/MainPID 0.

After NO_MATCH, continuation additionally requires `release_tail=1
single_terminal=1`. MATCH can be reported before the release tail; stock
VerifyStop can cancel while waiting for completion. Therefore preserve those
two counters after MATCH, but do not reject an otherwise closed/drained MATCH
solely because they are zero, or infer clean device quiescence from cancellation.
Unexpected extra BEGIN/RESULT/audit lines or REJECT, an empty journal result,
or hitting the 21-line limit means STOP for review, not another live run.

## Final state and rollback

At MATCH, the third clean NO_MATCH, or any STOP, stop touching and **detach the
sensor from the VM**. If the block failed to stop fprintd, use
`sudo systemctl stop fprintd.service` for cleanup only. Verify inactive/MainPID 0
with `systemctl show fprintd.service -p ActiveState -p MainPID`.

**PASS_IF:** at least one MATCH using the physical RIGHT index in at most three
invocations against stored `left-index-finger`, with the evidence above, service
inactive and reader detached. Keep the runtime/template and record the mismatch.
**FAIL_IF:** three clean NO_MATCH, live error, instability or cleanup failure.
Do not reenroll, delete templates, adjust matching or authentication policy.
An inconclusive STOP needs review; never repeat live to replace missing evidence.

After live FAIL/instability, stop fprintd and detach the sensor, then use the
saved inverse. A preflight STOP before live needs no uninstall. No rollback
on PASS.

```bash
sudo /usr/local/lib64/goodix-27c6-5125/uninstall.sh
systemctl show fprintd.service -p FragmentPath -p ExecStart -p Environment -p ActiveState -p MainPID
rpm -V fprintd libfprint
test ! -e /usr/local/lib64/goodix-27c6-5125
test ! -e /etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf
```

The inverse removes the private runtime and environment drop-in, removes only
its owned material mapping, restores current Fedora default labels, reloads the
unit and restores the previously recorded service state. Expected: vendor
`/usr/libexec/fprintd`, no project library environment, clean RPM verification.
It preserves the converted manifest, four materials and all host templates.
If inverse integrity or removal fails, retain the state and report it; do not
force deletion or substitute the current checkout's inverse.

Return the full checkout SHA, package versions, number of invocations/contacts,
confirmation that the physical RIGHT index was used against stored
`left-index-finger`, each CLI result/exit and complete safety lines in invocation
order, final inactive/detached state and whether runtime/template were kept or rolled back.
No images, template contents, protected material or broad logs are needed.
