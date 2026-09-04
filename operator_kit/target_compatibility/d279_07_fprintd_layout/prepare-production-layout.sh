#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
umask 077

target=/var/lib/goodix-5125-poc
apply=false
declare -A sources=()
declare -A original_contexts=()
names=(
  target-material-manifest.json
  transport-material.bin
  target-config-90.bin
  gfusb.dll
  fdt-cache.bin
)
declare -A sizes=(
  [target-material-manifest.json]=2305
  [transport-material.bin]=88
  [target-config-90.bin]=224
  [gfusb.dll]=5771496
  [fdt-cache.bin]=13520
)
declare -A hashes=(
  [target-material-manifest.json]=1b5c3891c99b4ee71d37a69942e08dcf9d3985740958687ac4b0d6eb7ccdcf15
  [transport-material.bin]=eb47bbed40e079ca780cd9cd4b2324520a67584ad3d576674914152fd6080a75
  [target-config-90.bin]=e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82
  [gfusb.dll]=904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2
  [fdt-cache.bin]=9f5327731cff3046e31d18356a6334c9e1494330f434f3fe75ad0a4c80db09e2
)
label_paths=(
  "$target"
  "$target/target-material-manifest.json"
  "$target/transport-material.bin"
  "$target/target-config-90.bin"
  "$target/gfusb.dll"
  "$target/fdt-cache.bin"
)
label_regexes=(
  '/var/lib/goodix-5125-poc'
  '/var/lib/goodix-5125-poc/target-material-manifest\.json'
  '/var/lib/goodix-5125-poc/transport-material\.bin'
  '/var/lib/goodix-5125-poc/target-config-90\.bin'
  '/var/lib/goodix-5125-poc/gfusb\.dll'
  '/var/lib/goodix-5125-poc/fdt-cache\.bin'
)
created=()
fcontexts_created=()
temporary=
directory_created=false
committed=false

usage ()
{
  cat >&2 <<'EOF'
Uso: prepare-production-layout.sh --apply \
  --manifest PATH --transport PATH --config90 PATH --gfusb PATH --fdt-cache PATH

Lo script non sovrascrive file esistenti. L'esecuzione richiede una distinta
autorizzazione umana per sudo, accesso/copia dei file e configurazione SELinux.
EOF
  exit 2
}

cleanup ()
{
  rc=$?
  if [[ $committed != true ]]; then
    [[ -z $temporary ]] || rm -f -- "$temporary"
    for path in "${created[@]}"; do rm -f -- "$path"; done
    for regex in "${fcontexts_created[@]}"; do
      semanage fcontext -d "$regex" >/dev/null 2>&1 || true
    done
    for path in "${!original_contexts[@]}"; do
      [[ -e $path && ! -L $path ]] &&
        chcon -- "${original_contexts[$path]}" "$path" >/dev/null 2>&1 || true
    done
    if [[ $directory_created == true ]]; then rmdir -- "$target" 2>/dev/null || true; fi
  fi
  exit "$rc"
}
trap cleanup EXIT HUP INT TERM

while (($#)); do
  case $1 in
    --apply) apply=true; shift ;;
    --manifest|--transport|--config90|--gfusb|--fdt-cache)
      (($# >= 2)) || usage
      case $1 in
        --manifest) name=target-material-manifest.json ;;
        --transport) name=transport-material.bin ;;
        --config90) name=target-config-90.bin ;;
        --gfusb) name=gfusb.dll ;;
        --fdt-cache) name=fdt-cache.bin ;;
      esac
      [[ -z ${sources[$name]+x} ]] || usage
      sources[$name]=$2
      shift 2 ;;
    *) usage ;;
  esac
done

[[ $apply == true ]] || usage
[[ $EUID -eq 0 ]] || { echo "ERRORE: eseguire manualmente con sudo" >&2; exit 3; }
for command in install sha256sum stat semanage restorecon matchpathcon chcon ln; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "ERRORE: comando richiesto assente: $command" >&2
    exit 3
  }
done

echo "Scopo: predisporre cinque input privati read-only per fprintd."
echo "Target: $target (root:root 0700; file root:root 0600)."
echo "Non saranno avviati servizi e non sarà aperto alcun dispositivo USB."
read -r -p "Digitare INSTALLA_LAYOUT_D279_07 per continuare: " confirmation
[[ $confirmation == INSTALLA_LAYOUT_D279_07 ]] || {
  echo "Operazione annullata senza modifiche."
  exit 4
}

if [[ -e $target || -L $target ]]; then
  [[ -d $target && ! -L $target ]] || {
    echo "ERRORE: target esistente non è una directory reale" >&2
    exit 3
  }
  [[ $(stat -c '%u:%g:%a' -- "$target") == 0:0:700 ]] || {
    echo "ERRORE: directory esistente non conforme; nessuna correzione automatica" >&2
    exit 3
  }
else
  install -d -o 0 -g 0 -m 0700 -- "$target"
  directory_created=true
fi
if [[ $directory_created != true ]]; then
  original_contexts[$target]=$(stat -c '%C' -- "$target")
fi
for name in "${names[@]}"; do
  if [[ -e $target/$name && ! -L $target/$name ]]; then
    original_contexts[$target/$name]=$(stat -c '%C' -- "$target/$name")
  fi
done

verify_file ()
{
  path=$1 name=$2
  [[ -f $path && ! -L $path ]] || return 1
  [[ $(stat -c '%u:%g:%a:%s' -- "$path") == "0:0:600:${sizes[$name]}" ]] || return 1
  [[ $(sha256sum -- "$path" | awk '{print $1}') == "${hashes[$name]}" ]]
}

for name in "${names[@]}"; do
  destination=$target/$name
  if [[ -e $destination || -L $destination ]]; then
    verify_file "$destination" "$name" || {
      echo "ERRORE: $name esiste ma non è conforme; non sarà sovrascritto" >&2
      exit 3
    }
    echo "CONSERVATO_E_VERIFICATO=$name"
    continue
  fi
  source=${sources[$name]:-}
  [[ -n $source && -f $source && ! -L $source ]] || {
    echo "ERRORE: sorgente esplicita assente/non regolare per $name" >&2
    exit 3
  }
  [[ $(stat -c '%s' -- "$source") == "${sizes[$name]}" ]] || {
    echo "ERRORE: size sorgente non conforme per $name" >&2
    exit 3
  }
  [[ $(sha256sum -- "$source" | awk '{print $1}') == "${hashes[$name]}" ]] || {
    echo "ERRORE: SHA-256 sorgente non conforme per $name" >&2
    exit 3
  }
  temporary=$target/.d279-07.$name.$$
  install -o 0 -g 0 -m 0600 -- "$source" "$temporary"
  restorecon -F -- "$temporary"
  verify_file "$temporary" "$name" || {
    echo "ERRORE: verifica della copia temporanea fallita per $name" >&2
    exit 3
  }
  ln -- "$temporary" "$destination"
  rm -f -- "$temporary"
  temporary=
  created+=("$destination")
  echo "INSTALLATO_E_VERIFICATO=$name"
done

for index in "${!label_paths[@]}"; do
  path=${label_paths[$index]}
  regex=${label_regexes[$index]}
  if [[ $(matchpathcon -n "$path") != system_u:object_r:fprintd_var_lib_t:s0 ]]; then
    semanage fcontext -a -t fprintd_var_lib_t "$regex"
    fcontexts_created+=("$regex")
  fi
done
for path in "${label_paths[@]}"; do
  [[ $(matchpathcon -n "$path") == system_u:object_r:fprintd_var_lib_t:s0 ]] || {
    echo "ERRORE: mapping SELinux inatteso per $path" >&2
    exit 3
  }
  restorecon -F -- "$path"
  [[ $(stat -c '%C' -- "$path") == *:fprintd_var_lib_t:* ]] || {
    echo "ERRORE: label SELinux finale non conforme per $path" >&2
    exit 3
  }
done

for name in "${names[@]}"; do
  verify_file "$target/$name" "$name" || {
    echo "ERRORE: verifica finale fallita per $name" >&2
    exit 3
  }
done
committed=true
echo "LAYOUT_PRODUCTION_D279_07=PREPARATO"
echo "FPRINTD_STARTED=false"
echo "USB_ACCESSED=false"
echo "PASSO_SUCCESSIVO=ESEGUIRE_PROBE_READ_ONLY_CON_AUTORIZZAZIONE_SEPARATA"
