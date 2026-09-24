#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Unprivileged reconstruction of the exact historical recovery policy.
set -euo pipefail
umask 077
[[ $# == 1 && $EUID != 0 && $1 == /* && ! -e $1 && ! -L $1 ]] || exit 2
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(git -C "$here" rev-parse --show-toplevel)
out=$1
mkdir -m 0700 "$out"
name=goodix_fprint_account_delete
for ext in te fc; do
  git -C "$root" show "232e9401ca3ce72a0f9f08448deb46c6251aaa2a:deployment/d293-phase-b-account-lifecycle/$name.$ext" >"$out/$name.$ext"
done
[[ $(sha256sum "$out/$name.te" | cut -d' ' -f1) == 57dd5d66823a4a295e56bf4c23dc14054058dd32ebc3c1afc8f3991790cce01c ]]
[[ $(sha256sum "$out/$name.fc" | cut -d' ' -f1) == 98578cb5bbd6474eff13a8218d7fc5b7606200491502a88ec6ce4c63ffa204b5 ]]
checkmodule -M -m -E -o "$out/$name.mod" "$out/$name.te"
semodule_package -o "$out/$name.pp" -m "$out/$name.mod" -f "$out/$name.fc"
[[ $(sha256sum "$out/$name.pp" | cut -d' ' -f1) == 674740ba782b501a68dbaff9bef04d725cc9e88adad6f37c6f3c468a2cc71d03 ]]
[[ $(/usr/libexec/selinux/hll/pp "$out/$name.pp" | sha256sum | cut -d' ' -f1) == e993729e97ad84f2a89e6cd41bbdb2e5f557a9898f0d96962183053bea0a69f3 ]]
echo HISTORICAL_RECOVERY_POLICY_REPRODUCTION=PASS
