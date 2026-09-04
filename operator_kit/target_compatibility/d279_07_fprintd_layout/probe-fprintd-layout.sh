#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

target=/var/lib/goodix-5125-poc
unit=fprintd.service
mode=full
enforcement=UNKNOWN
selinux_policy_result=UNKNOWN
files=(
  target-material-manifest.json
  transport-material.bin
  target-config-90.bin
  gfusb.dll
  fdt-cache.bin
)

usage ()
{
  echo "Uso: $0 [--environment-only | --full]" >&2
  exit 2
}

fail ()
{
  echo "REAL_TARGET_COMPATIBILITY=BLOCKED_HUMAN_REQUIRED"
  echo "MOTIVO=$1" >&2
  echo "FPRINTD_STARTED=false"
  echo "FILE_CONTENT_READ=false"
  echo "USB_ACCESSED=false"
  exit 3
}

if (($#)); then
  (($# == 1)) || usage
  case $1 in
    --environment-only) mode=environment ;;
    --full) mode=full ;;
    *) usage ;;
  esac
fi

for command in systemd-analyze getenforce sed tail; do
  command -v "$command" >/dev/null 2>&1 || fail "COMANDO_ASSENTE_${command}"
done

merged=$(systemd-analyze cat-config "systemd/system/$unit") ||
  fail UNIT_NON_LEGGIBILE
user=$(sed -n 's/^User=//p' <<<"$merged" | tail -n 1)
group=$(sed -n 's/^Group=//p' <<<"$merged" | tail -n 1)
dynamic=$(sed -n 's/^DynamicUser=//p' <<<"$merged" | tail -n 1)
protect=$(sed -n 's/^ProtectSystem=//p' <<<"$merged" | tail -n 1)
[[ -z $user || $user == root || $user == 0 ]] || fail FPRINTD_USER_NON_ROOT
[[ -z $group || $group == root || $group == 0 ]] || fail FPRINTD_GROUP_NON_ROOT
[[ -z $dynamic || $dynamic == no || $dynamic == false ]] ||
  fail FPRINTD_DYNAMIC_USER_ATTIVO
[[ $protect == strict ]] || fail PROTECT_SYSTEM_INATTESO

enforcement=$(getenforce)
if [[ $enforcement == Enforcing || $enforcement == Permissive ]]; then
  for command in python3 find sort; do
    command -v "$command" >/dev/null 2>&1 || fail "COMANDO_ASSENTE_${command}"
  done
  policy=$(find /etc/selinux/targeted/policy -maxdepth 1 -type f \
    -name 'policy.*' -printf '%p\n' | sort -V | tail -n 1)
  [[ -n $policy ]] || fail SELINUX_POLICY_ASSENTE
  python3 - "$policy" <<'PY' || fail SELINUX_POLICY_NON_DIMOSTRA_LETTURA
import sys
import setools

policy = setools.SELinuxPolicy(sys.argv[1])
required = {
    "dir": {"getattr", "open", "read", "search"},
    "file": {"getattr", "open", "read"},
}
for tclass, permissions in required.items():
    rules = setools.TERuleQuery(
        policy,
        ruletype=["allow"],
        source="fprintd_t",
        target="fprintd_var_lib_t",
        tclass=[tclass],
    ).results()
    granted = set()
    for rule in rules:
        granted.update(str(permission) for permission in rule.perms)
    if not permissions <= granted:
        raise SystemExit(1)
PY
  selinux_policy_result=PASS
elif [[ $enforcement == Disabled ]]; then
  selinux_policy_result=NOT_APPLICABLE_DISABLED
else
  fail "SELINUX_STATO_SCONOSCIUTO_${enforcement}"
fi

echo "FPRINTD_RUNTIME_IDENTITY=root:root"
echo "FPRINTD_PROTECT_SYSTEM=strict_read_only_visible"
echo "SELINUX_ENFORCEMENT=$enforcement"
echo "SELINUX_FPRINTD_READ_POLICY=$selinux_policy_result"
echo "REAL_TARGET_ENVIRONMENT=PASS"

if [[ $mode == environment ]]; then
  echo "LAYOUT_PROVISIONING_STATE=NOT_CHECKED"
  echo "REAL_TARGET_COMPATIBILITY=BLOCKED_HUMAN_REQUIRED"
  echo "MOTIVO=LAYOUT_POST_PROVISION_NON_VERIFICATO"
  echo "FPRINTD_STARTED=false"
  echo "FILE_CONTENT_READ=false"
  echo "USB_ACCESSED=false"
  exit 0
fi

[[ $EUID -eq 0 ]] || fail PROBE_FULL_RICHIEDE_SUDO_READ_ONLY
command -v stat >/dev/null 2>&1 || fail COMANDO_ASSENTE_stat
if [[ $enforcement == Enforcing || $enforcement == Permissive ]]; then
  command -v matchpathcon >/dev/null 2>&1 || fail COMANDO_ASSENTE_matchpathcon
fi

[[ -e $target ]] || {
  echo "LAYOUT_PROVISIONING_STATE=NOT_PROVISIONED"
  fail DIRECTORY_LAYOUT_ASSENTE
}
[[ -d $target && ! -L $target ]] || fail DIRECTORY_LAYOUT_NON_REGOLARE_O_SYMLINK
[[ $(stat -c '%u:%g:%a' -- "$target") == 0:0:700 ]] ||
  fail DIRECTORY_METADATA_NON_CONFORMI

missing=()
invalid=()
for name in "${files[@]}"; do
  path=$target/$name
  if [[ -L $path ]]; then
    invalid+=("$name:symlink")
  elif [[ ! -e $path ]]; then
    missing+=("$name")
  elif [[ ! -f $path ]]; then
    invalid+=("$name:not_regular")
  fi
done
if ((${#missing[@]})); then
  echo "LAYOUT_PROVISIONING_STATE=INCOMPLETE"
  printf 'MISSING_FILES=%s\n' "$(IFS=,; echo "${missing[*]}")"
  fail LAYOUT_NON_PROVISIONATO_FILE_ASSENTI
fi
if ((${#invalid[@]})); then
  echo "LAYOUT_PROVISIONING_STATE=INVALID"
  printf 'INVALID_FILES=%s\n' "$(IFS=,; echo "${invalid[*]}")"
  fail LAYOUT_FILE_NON_REGOLARI_O_SYMLINK
fi

for name in "${files[@]}"; do
  path=$target/$name
  [[ $(stat -c '%u:%g:%a' -- "$path") == 0:0:600 ]] ||
    fail "FILE_METADATA_NON_CONFORMI_${name}"
done

if [[ $enforcement == Enforcing || $enforcement == Permissive ]]; then
  [[ $(matchpathcon -n "$target") == system_u:object_r:fprintd_var_lib_t:s0 ]] ||
    fail DIRECTORY_EXPECTED_LABEL_NON_CONFORME
  for name in "${files[@]}"; do
    [[ $(matchpathcon -n "$target/$name") == system_u:object_r:fprintd_var_lib_t:s0 ]] ||
      fail "FILE_EXPECTED_LABEL_NON_CONFORME_${name}"
    actual=$(stat -c '%C' -- "$target/$name")
    [[ $actual == *:fprintd_var_lib_t:* ]] ||
      fail "FILE_ACTUAL_LABEL_NON_CONFORME_${name}"
  done
fi

echo "LAYOUT_METADATA=root:root_0700_files_0600"
echo "LAYOUT_PROVISIONING_STATE=COMPLETE_METADATA_ONLY"
echo "FPRINTD_STARTED=false"
echo "FILE_CONTENT_READ=false"
echo "USB_ACCESSED=false"
echo "REAL_TARGET_COMPATIBILITY=PASS"
