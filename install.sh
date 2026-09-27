#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -uo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

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

# Preserve the historical read-only/help behavior: these modes must not install
# packages or make privileged changes merely to answer a query.
for arg in "$@"; do
    case "$arg" in
        -h|--help|--check)
            exec /usr/bin/python3 -I -B "$ROOT/deployment/install.py" "$@"
            ;;
    esac
done

if [ "${EUID}" -eq 0 ]; then
    stop_install invocation 2 "run ./install.sh as your ordinary user; sudo is requested only when needed"
fi

# The orchestrator checks material availability in a read-only privileged phase
# before installing packages, then builds as this ordinary user.
/usr/bin/python3 -I -B "$ROOT/deployment/install.py" --install-dependencies "$@"
rc=$?
if [ "$rc" -ne 0 ]; then
    stop_install installer "$rc"
fi

printf '\nGOODIX_INSTALL_BLOCK=PASS\n'
