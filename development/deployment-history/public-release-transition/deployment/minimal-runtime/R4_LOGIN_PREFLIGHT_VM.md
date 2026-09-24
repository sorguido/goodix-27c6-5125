<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R4: identify the VM's stock graphical login route

**COMPLETED — configuration query reported PASS at guest checkout
`725b3c1f8bf879b9e56632b4f15da494968cead7`. Do not repeat this procedure.**
Stock Plasma Login uses password-auth without fingerprint. The opt-in selector's
VM build/tests, installation and [real password/fingerprint login](../../../../deployment/plasma-login-opt-in/R4_PLASMA_LOGIN_VM.md)
have since passed. **R4 is closed; R5 is not started. Wait for the user; no new gate.**
The original query below is retained as evidence.

**Original HUMAN_REQUIRED — one reader-absent configuration query in the existing VM.**
Keep the current desktop session open. No logout, reboot, lock, authentication,
USB attachment or service action is requested. No sudo is needed.

R3 and the R4 KScreenLocker, ordinary sudo and [PolicyKit](R4_POLKIT_VM.md)
tests are accepted PASS; do not repeat them. At preparation time, the VM's actual
display manager, login PAM route and autologin configuration had not yet been established.
The physical host's historical Plasma Login results do not identify this guest.
This query selects the running stock Plasma Login or SDDM service for inspection;
an unexpected service requires review, not a change of display manager.

Retain the qualified runtime build
`b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226`, install
`264cd7ff1ba77857e1985502f299e4375f9a0516`, reconciled receipt, SELinux Enforcing
and the physical **RIGHT index** stored as `guido` / `left-index-finger`.
No installation or rollback is needed for this query. The existing
[install.sh](install.sh) and saved installed inverse
`/usr/local/lib64/goodix-27c6-5125/uninstall.sh` remain recoverable; do not replace
that inverse or run it after these PASS results.

## Run once in the VM

As `guido`, use an ordinary Bash terminal in the existing private VM checkout,
with the sensor detached. Close authentication dialogs and fingerprint settings,
but keep the desktop and terminal open. The block updates only the clean Git
checkout, prints its full SHA, then reads session/unit/package metadata and
the selected display manager's configuration and PAM files. It neither invokes
the display manager executable nor changes PAM, authselect, SELinux or runtime.

```bash
(
  set -euo pipefail
  trap 'printf "R4_LOGIN_QUERY_STOP line=%s exit=%s\n" "$LINENO" "$?" >&2' ERR
  export LC_ALL=C
  cd "$(git rev-parse --show-toplevel)"
  test "$(git branch --show-current)" = development
  test -z "$(git status --porcelain)"
  git pull --ff-only origin development
  git rev-parse HEAD
  test "$(id -un)" = guido
  systemd-detect-virt --vm --quiet
  test "$(getenforce)" = Enforcing
  python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.no_sensor()
print('R4_LOGIN_QUERY_START SENSOR_CONNECTED=false')
PY
  loginctl show-session "${XDG_SESSION_ID:?Missing desktop session ID; STOP}" \
    -p Name -p Service -p Type -p Class -p Desktop -p Seat -p VTNr -p Active -p Remote
  systemctl show display-manager.service -p Id -p LoadState -p ActiveState \
    -p SubState -p MainPID -p FragmentPath -p DropInPaths -p ExecStart
  systemctl cat --no-pager display-manager.service
  r4_login_id=$(systemctl show display-manager.service -p Id --value)
  r4_login_fragment=$(systemctl show display-manager.service -p FragmentPath --value)
  test -n "$r4_login_fragment"
  rpm -qf "$r4_login_fragment"
  r4_login_package=$(rpm -qf --qf '%{NAME}\n' "$r4_login_fragment")
  rpm -q systemd plasma-workspace fprintd-pam pam authselect
  r4_login_rpm_rc=0
  rpm -V --noscript "$r4_login_package" || r4_login_rpm_rc=$?
  printf 'DISPLAY_MANAGER_RPM_VERIFY_EXIT=%s\n' "$r4_login_rpm_rc"
  case "$r4_login_id" in
    plasmalogin.service) r4_login_base=plasmalogin ;;
    sddm.service) r4_login_base=sddm ;;
    *) printf 'R4_LOGIN_QUERY_STOP unexpected display manager: %s\n' "$r4_login_id" >&2; exit 1 ;;
  esac
  authselect current --raw
  authselect check
  r4_login_paths=("/etc/$r4_login_base.conf" "/etc/sysconfig/$r4_login_base")
  shopt -s nullglob
  for r4_login_dir in "/usr/lib/$r4_login_base/$r4_login_base.conf.d" "/etc/$r4_login_base.conf.d"; do
    printf '\nCONFIG_DIRECTORY=%s\n' "$r4_login_dir"
    if [[ -e "$r4_login_dir" || -L "$r4_login_dir" ]]; then
      test -d "$r4_login_dir"
      test -r "$r4_login_dir"
      test -x "$r4_login_dir"
      for r4_login_file in "$r4_login_dir"/*; do
        [[ -d "$r4_login_file" ]] && continue
        test -f "$r4_login_file"
        r4_login_paths+=("$r4_login_file")
      done
    else
      printf 'ABSENT\n'
    fi
  done
  for r4_login_name in "$r4_login_base" "$r4_login_base-autologin" "$r4_login_base-greeter" \
                       password-auth fingerprint-auth system-auth postlogin; do
    r4_login_paths+=("/etc/pam.d/$r4_login_name" "/usr/lib/pam.d/$r4_login_name")
  done
  for r4_login_file in "${r4_login_paths[@]}"; do
    printf '\nCONFIG_OR_PAM_FILE=%s\n' "$r4_login_file"
    if [[ -e "$r4_login_file" || -L "$r4_login_file" ]]; then
      test -f "$r4_login_file"
      test -r "$r4_login_file"
      readlink -f "$r4_login_file"
      rpm -qf "$r4_login_file" || :
      cat "$r4_login_file"
    else
      printf 'ABSENT\n'
    fi
  done
  python3 -B - <<'PY'
import sys
sys.path.insert(0, 'deployment/minimal-runtime')
import deploy as d
d.no_sensor()
print('R4_LOGIN_QUERY_COMPLETE SENSOR_CONNECTED=false')
PY
)
```

**PASS_IF (collection only):** the block reaches QUERY_COMPLETE and returns the
session, actual unit/overrides, package/version verification, configuration and
PAM contents with their paths. RPM differences or unowned generated files are
observations for review, not permission to repair them. Listing configuration
files does not by itself establish precedence or prove a fingerprint login route.

**STOP_IF:** wrong environment, sensor present, unexpected display manager,
missing session ID, unreadable file, query error or authentication prompt.
Keep the session open and reader absent; return partial output and the exact
failure. Do not retry with sudo, change configuration, log out or roll back.

Return the complete output and note any known package/configuration change since
the PolicyKit PASS. No journal scan, credentials or biometric material is needed.
The final state must remain desktop open, reader detached, runtime/template
preserved and Enforcing. This query does not require or change fprintd state.

Review of the actual guest route comes before a separate stock-login procedure.
**Graphical login live is NOT READY.** No private greeter, PAM overlay, VT/logind
workaround or TTY recovery path is prepared. Password/desktop safety remains a
requirement; neither PolicyKit PASS nor this query qualifies login or R5 updates.
