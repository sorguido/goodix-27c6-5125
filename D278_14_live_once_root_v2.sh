#!/usr/bin/env bash
# D278/14 operator kit v2 — phase 2: exactly ONE integrated LIVE run
set -euo pipefail

APPROVED_BASELINE="2172e750ae7c100a3a891ba25d0797286230a4ab"
OPERATION="D278_13_INTEGRATED_PATH_ONCE"
STATIC_AUTH="D278_13_ONE_INTEGRATED_TWO_ACQUISITION_RUN_NO_RETRY"
WRAPPER_GUARD="/var/tmp/goodix-d278-14-${APPROVED_BASELINE}-one-shot-consumed"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

blocking_git_status_root () {
  local root=$1
  local line
  local status
  status="$(git -c "safe.directory=$root" -C "$root" status --porcelain=v1 --untracked-files=all)"
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    case "$line" in
      "?? D278_14_prepare_operator_v2.sh"|"?? D278_14_live_once_root_v2.sh")
        ;;
      *)
        printf '%s\n' "$line"
        ;;
    esac
  done <<<"$status"
}

[[ $EUID -eq 0 ]] || die "This live script must be launched manually with sudo."
[[ $# -eq 2 ]] || die "Usage: sudo $0 <repository-root> <prepared-build-dir>"

ROOT="$(readlink -f -- "$1")"
BUILD_DIR="$(readlink -f -- "$2")"
STATE="$BUILD_DIR/d278-14-prepared.state"
BINARY="$BUILD_DIR/d278_integrated_path_once"

[[ -d "$ROOT/.git" ]] || die "Repository root invalid."
[[ -f "$STATE" && ! -L "$STATE" ]] || die "Prepared state missing/unsafe."
[[ -f "$BINARY" && ! -L "$BINARY" && -x "$BINARY" ]] || die "Prepared binary missing/unsafe."

declare D278_14_APPROVED_BASELINE=""
declare D278_14_REPOSITORY=""
declare D278_14_BINARY=""
declare D278_14_BINARY_SHA256=""

while IFS='=' read -r key value; do
  case "$key" in
    D278_14_APPROVED_BASELINE) D278_14_APPROVED_BASELINE="$value" ;;
    D278_14_REPOSITORY) D278_14_REPOSITORY="$value" ;;
    D278_14_BINARY) D278_14_BINARY="$value" ;;
    D278_14_BINARY_SHA256) D278_14_BINARY_SHA256="$value" ;;
    "") ;;
    *) die "Unexpected prepared-state field: $key" ;;
  esac
done <"$STATE"

[[ "$D278_14_APPROVED_BASELINE" == "$APPROVED_BASELINE" ]] || die "Prepared baseline mismatch."
[[ "$(readlink -f -- "$D278_14_REPOSITORY")" == "$ROOT" ]] || die "Prepared repository mismatch."
[[ "$(readlink -f -- "$D278_14_BINARY")" == "$BINARY" ]] || die "Prepared binary path mismatch."
[[ "$D278_14_BINARY_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "Invalid binary SHA-256."
[[ "$(sha256sum "$BINARY" | awk '{print $1}')" == "$D278_14_BINARY_SHA256" ]] || die "Prepared binary SHA-256 mismatch."

branch="$(git -c "safe.directory=$ROOT" -C "$ROOT" branch --show-current)"
head="$(git -c "safe.directory=$ROOT" -C "$ROOT" rev-parse HEAD)"
blocking="$(blocking_git_status_root "$ROOT")"

[[ "$branch" == "main" ]] || die "Expected main."
[[ "$head" == "$APPROVED_BASELINE" ]] || die "Live baseline mismatch."
[[ -z "$blocking" ]] || {
  echo "$blocking" >&2
  die "Repository has changes beyond the two allowed D278/14 v2 operator-kit files."
}

[[ -f /var/lib/goodix-5125-poc/target-material-manifest.json ]] || die "Protected manifest missing."
[[ -f /var/lib/goodix-5125-poc/transport-material.bin ]] || die "Protected transport material missing."
[[ -f /var/lib/goodix-5125-poc/target-config-90.bin ]] || die "Protected CONFIG90 missing."
[[ -f "$ROOT/analysis/D230/work/GoodixExport/gfusb.dll" ]] || die "Canonical gfusb.dll missing."
[[ -f "$ROOT/captures/D255_20260822T205631772Z_85c8c41f/raw/cache_before/9f5327731cff3046e31d18356a6334c9e1494330f434f3fe75ad0a4c80db09e2.bin" ]] || die "Canonical D255 cache seed missing."

echo "=== D278/14 LIVE ONE-SHOT v2 ==="
echo "Baseline: $APPROVED_BASELINE"
echo "All root-side prechecks passed."
echo "The next step consumes the single authorization."
echo

if ! mkdir -m 0700 -- "$WRAPPER_GUARD" 2>/dev/null; then
  die "D278/14 authorization already consumed: $WRAPPER_GUARD"
fi

AUTH_DIR="$WRAPPER_GUARD/auth"
AUTH_TICKET="$AUTH_DIR/d278-14.ticket"
LIVE_LOG="$WRAPPER_GUARD/d278-14-live-output.txt"
mkdir -m 0700 -- "$AUTH_DIR"

AUTH_NONCE="$(openssl rand -hex 24)"
umask 077
cat >"$AUTH_TICKET" <<EOF
D278_13_BASELINE_SHA=$APPROVED_BASELINE
D278_13_OPERATION=$OPERATION
D278_13_NONCE=$AUTH_NONCE
EOF
chmod 0600 "$AUTH_TICKET"
unset AUTH_NONCE

echo "D278_14_WRAPPER_ONE_SHOT_CONSUMED=true"
echo "Starting the ONE authorized sensor-reaching execution now..."

cd "$ROOT"
set +e
env \
  D278_13_APPROVED_LIVE_BASELINE_SHA="$APPROVED_BASELINE" \
  D278_13_OPERATOR_AUTHORIZATION="$STATIC_AUTH" \
  D278_13_OPERATION="$OPERATION" \
  D278_13_AUTHORIZATION_TICKET="$AUTH_TICKET" \
  LD_LIBRARY_PATH="$BUILD_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$BINARY" --live-integrated-once 2>&1 | tee "$LIVE_LOG"
live_rc=${PIPESTATUS[0]}
set -e

chmod 0600 "$LIVE_LOG" 2>/dev/null || true

echo
echo "============================================================"
echo "D278/14 LIVE EXECUTION FINISHED"
echo "EXIT_CODE=$live_rc"
echo "D278_14_LIVE_EXECUTION_COUNT=1"
echo "D278_14_ONE_SHOT_CONSUMED=true"
echo "D278_14_RERUN_AUTHORIZED=false"
echo "RETRY_PERFORMED=false"
echo "LIVE_LOG=$LIVE_LOG"
echo "============================================================"
echo "DO NOT run this script again."

exit "$live_rc"
