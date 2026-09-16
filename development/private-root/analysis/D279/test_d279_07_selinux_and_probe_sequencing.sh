#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(git -C "$script_dir" rev-parse --show-toplevel)
kit=$root/operator_kit/target_compatibility/d279_07_fprintd_layout
temporary=$(mktemp -d /tmp/goodix-d279-07-corrective.XXXXXX)
mock_bin=$temporary/bin
sentinel=$temporary/selinux-mutator-called
mkdir -p "$mock_bin"

cleanup ()
{
  find "$temporary" -type f -delete 2>/dev/null || true
  rmdir "$mock_bin" 2>/dev/null || true
  rmdir "$temporary" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

write_getenforce ()
{
  state=$1
  printf '#!/bin/sh\nprintf "%%s\\n" "%s"\n' "$state" >"$mock_bin/getenforce"
  chmod 0755 "$mock_bin/getenforce"
}

for command in semanage restorecon matchpathcon chcon stat python3; do
  printf '#!/bin/sh\nprintf "%%s\\n" "$0" >>"$D279_07_SENTINEL"\nexit 97\n' \
    >"$mock_bin/$command"
  chmod 0755 "$mock_bin/$command"
done

write_getenforce Disabled
disabled=$(D279_07_SENTINEL="$sentinel" PATH="$mock_bin:$PATH" \
  "$kit/prepare-production-layout.sh" --check-selinux-plan)
grep -Fx 'SELINUX_ENFORCEMENT=Disabled' <<<"$disabled" >/dev/null
grep -Fx 'SELINUX_PROVISIONING=NOT_APPLICABLE_DISABLED' <<<"$disabled" >/dev/null
grep -Fx 'SELINUX_MUTATION_COMMANDS_REQUIRED=false' <<<"$disabled" >/dev/null
grep -Fx 'FILES_ACCESSED=false' <<<"$disabled" >/dev/null
grep -Fx 'SYSTEM_STATE_CHANGED=false' <<<"$disabled" >/dev/null
[[ ! -e $sentinel ]]

for state in Enforcing Permissive; do
  write_getenforce "$state"
  active=$(D279_07_SENTINEL="$sentinel" PATH="$mock_bin:$PATH" \
    "$kit/prepare-production-layout.sh" --check-selinux-plan)
  grep -Fx "SELINUX_ENFORCEMENT=$state" <<<"$active" >/dev/null
  grep -Fx 'SELINUX_PROVISIONING=REQUIRED_FPRINTD_VAR_LIB_T' <<<"$active" >/dev/null
  grep -Fx 'SELINUX_MUTATION_COMMANDS_REQUIRED=true' <<<"$active" >/dev/null
  [[ ! -e $sentinel ]]
done

write_getenforce Unexpected
if D279_07_SENTINEL="$sentinel" PATH="$mock_bin:$PATH" \
  "$kit/prepare-production-layout.sh" --check-selinux-plan \
  >"$temporary/unexpected.out" 2>"$temporary/unexpected.err"; then
  echo 'ERRORE: stato SELinux sconosciuto accettato' >&2
  exit 1
fi
grep -F 'stato SELinux sconosciuto: Unexpected' "$temporary/unexpected.err" >/dev/null
[[ ! -e $sentinel ]]

cat >"$mock_bin/systemd-analyze" <<'EOF'
#!/bin/sh
cat <<'UNIT'
[Service]
ProtectSystem=strict
StateDirectory=fprint
StateDirectoryMode=0700
UNIT
EOF
chmod 0755 "$mock_bin/systemd-analyze"
write_getenforce Disabled
environment=$(D279_07_SENTINEL="$sentinel" PATH="$mock_bin:$PATH" \
  "$kit/probe-fprintd-layout.sh" --environment-only)
grep -Fx 'FPRINTD_RUNTIME_IDENTITY=root:root' <<<"$environment" >/dev/null
grep -Fx 'SELINUX_FPRINTD_READ_POLICY=NOT_APPLICABLE_DISABLED' \
  <<<"$environment" >/dev/null
grep -Fx 'REAL_TARGET_ENVIRONMENT=PASS' <<<"$environment" >/dev/null
grep -Fx 'LAYOUT_PROVISIONING_STATE=NOT_CHECKED' <<<"$environment" >/dev/null
grep -Fx 'MOTIVO=LAYOUT_POST_PROVISION_NON_VERIFICATO' <<<"$environment" >/dev/null
[[ ! -e $sentinel ]]

bash -n "$kit/prepare-production-layout.sh"
bash -n "$kit/probe-fprintd-layout.sh"
echo D279_07_SELINUX_DISABLED_NO_MUTATORS=PASS
echo D279_07_SELINUX_ACTIVE_PLAN=PASS
echo D279_07_UNKNOWN_SELINUX_FAIL_CLOSED=PASS
echo D279_07_ENVIRONMENT_ONLY_BEFORE_LAYOUT=PASS
echo REAL_FILE_CONTENT_ACCESSED=false
echo SYSTEM_STATE_CHANGED=false
echo FPRINTD_STARTED=false
echo USB_ACCESSED=false
