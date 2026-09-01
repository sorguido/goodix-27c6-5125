#!/usr/bin/env bash
# D278/14 operator kit v2 — phase 1: host-only preflight + approved binary build
set -euo pipefail

APPROVED_BASELINE="2172e750ae7c100a3a891ba25d0797286230a4ab"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

blocking_git_status () {
  local root=$1
  local line
  local status
  status="$(git -C "$root" status --porcelain=v1 --untracked-files=all)"
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

[[ $EUID -ne 0 ]] || die "Do not run phase 1 with sudo/root."

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

find_repo() {
  if [[ -n "${GOODIX_REPO:-}" ]]; then
    git -C "$GOODIX_REPO" rev-parse --show-toplevel 2>/dev/null
    return
  fi
  if git -C "$PWD" rev-parse --show-toplevel >/dev/null 2>&1; then
    git -C "$PWD" rev-parse --show-toplevel
    return
  fi
  if git -C "$SCRIPT_DIR" rev-parse --show-toplevel >/dev/null 2>&1; then
    git -C "$SCRIPT_DIR" rev-parse --show-toplevel
    return
  fi
  return 1
}

ROOT="$(find_repo)" || die "Goodix repository not found."
ROOT="$(cd "$ROOT" && pwd -P)"
cd "$ROOT"

echo "=== D278/14 PHASE 1 v2 — HOST-ONLY PREPARATION ==="
echo "Repository: $ROOT"
echo "Approved baseline: $APPROVED_BASELINE"
echo

branch="$(git branch --show-current)"
head="$(git rev-parse HEAD)"
blocking="$(blocking_git_status "$ROOT")"

[[ "$branch" == "main" ]] || die "Expected branch main, found: $branch"
[[ "$head" == "$APPROVED_BASELINE" ]] || die "Baseline mismatch: $head"
[[ -z "$blocking" ]] || {
  echo "$blocking" >&2
  die "Repository has changes beyond the two explicitly allowed D278/14 v2 operator-kit files."
}

echo "[1/4] Exact branch/HEAD/repository state: PASS"
echo "      Allowed untracked files:"
echo "      ?? D278_14_prepare_operator_v2.sh"
echo "      ?? D278_14_live_once_root_v2.sh"

echo "[2/4] Running existing host-only pre-live closure..."
./operator_kit/d278-13-integrated-path-once.sh --host-only-prelive

branch="$(git branch --show-current)"
head="$(git rev-parse HEAD)"
blocking="$(blocking_git_status "$ROOT")"

[[ "$branch" == "main" ]] || die "Branch changed during preflight."
[[ "$head" == "$APPROVED_BASELINE" ]] || die "HEAD changed during preflight."
[[ -z "$blocking" ]] || {
  echo "$blocking" >&2
  die "Repository changed during preflight beyond the allowed v2 operator-kit files."
}

echo "[3/4] Post-preflight baseline/repository recheck: PASS"

BUILD_DIR="$(mktemp -d /tmp/goodix-d278-14-prepared.XXXXXX)"
chmod 0700 "$BUILD_DIR"

cleanup_on_failure() {
  rc=$?
  if [[ $rc -ne 0 ]]; then
    rm -rf -- "$BUILD_DIR"
  fi
  exit $rc
}
trap cleanup_on_failure EXIT HUP INT TERM

echo "[4/4] Building exact approved live binary..."
D278_13_BUILD_DIR="$BUILD_DIR" \
D278_13_BUILD_APPROVED_BASELINE_SHA="$APPROVED_BASELINE" \
  ./libfprint-driver/tests/build_goodix_d278_13_adapter.sh

BINARY="$BUILD_DIR/d278_integrated_path_once"
[[ -x "$BINARY" ]] || die "Approved binary was not produced."

BINARY_SHA256="$(sha256sum "$BINARY" | awk '{print $1}')"
STATE="$BUILD_DIR/d278-14-prepared.state"

cat >"$STATE" <<EOF
D278_14_APPROVED_BASELINE=$APPROVED_BASELINE
D278_14_REPOSITORY=$ROOT
D278_14_BINARY=$BINARY
D278_14_BINARY_SHA256=$BINARY_SHA256
EOF
chmod 0600 "$STATE"

[[ "$(git rev-parse HEAD)" == "$APPROVED_BASELINE" ]] || die "Final HEAD mismatch."
blocking="$(blocking_git_status "$ROOT")"
[[ -z "$blocking" ]] || {
  echo "$blocking" >&2
  die "Final repository state contains unexpected changes."
}

trap - EXIT HUP INT TERM

echo
echo "============================================================"
echo "D278/14 PREPARATION v2: PASS"
echo "REAL_USB_ACCESS=false"
echo "REAL_USB_SUBMIT=0"
echo "REAL_PRODUCTION_SECRET_READ=false"
echo "LIVE_EXECUTION_PERFORMED=false"
echo "============================================================"
echo
echo "Prepared build directory:"
echo "  $BUILD_DIR"
echo
echo "NEXT STEP — manually run exactly:"
printf '  sudo %q %q %q\n' "$SCRIPT_DIR/D278_14_live_once_root_v2.sh" "$ROOT" "$BUILD_DIR"
