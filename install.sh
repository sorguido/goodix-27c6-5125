#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -uo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
MATERIALS="$HOME/goodix-5125-materials"
ARGS=("$@")

stop_install() {
    local step="$1"
    local rc="$2"
    shift 2
    printf '\nGOODIX_INSTALL_BLOCK=STOP STEP=%s EXIT_CODE=%d' "$step" "$rc" >&2
    if [ "$#" -gt 0 ]; then
        printf ' %s' "$*" >&2
    fi
    printf '\nThe terminal remains open. Copy the complete output above before retrying.\n' >&2
    exit "$rc"
}

if [ "${EUID}" -eq 0 ]; then
    stop_install invocation 2 "run ./install.sh as your ordinary user; sudo is requested only when needed"
fi

for ((i = 0; i < ${#ARGS[@]}; i++)); do
    case "${ARGS[i]}" in
        --materials)
            if (( i + 1 >= ${#ARGS[@]} )); then
                stop_install materials 2 "missing path after --materials"
            fi
            MATERIALS="${ARGS[i + 1]}"
            ((i++))
            ;;
        --materials=*)
            MATERIALS="${ARGS[i]#--materials=}"
            ;;
    esac
done

printf '\n==> [1/3] Checking protected-material staging directory\n'
if [ ! -d "$MATERIALS" ]; then
    stop_install materials 10 "REASON=directory_missing PATH=$MATERIALS"
fi

printf '\n==> [2/3] Installing Fedora prerequisites\n'
sudo dnf install git python3 gcc gcc-c++ meson ninja-build pkgconf-pkg-config \
    glib2-devel libgusb-devel openssl-devel opencv-devel pam-devel binutils \
    fprintd fprintd-pam policycoreutils-python-utils
rc=$?
if [ "$rc" -ne 0 ]; then
    stop_install dependencies "$rc"
fi

printf '\n==> [3/3] Building and installing Goodix support\n'
/usr/bin/python3 -I -B "$ROOT/deployment/install.py" "$@"
rc=$?
if [ "$rc" -ne 0 ]; then
    stop_install installer "$rc"
fi

printf '\nGOODIX_INSTALL_BLOCK=PASS\n'
