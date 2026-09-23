<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Internal qualification install: continuously present reader

**Internal development procedure, excluded from publication.** Public installation
status is in [INSTALLATION.md](INSTALLATION.md); final packaging is not available.
This procedure reuses the accepted software outputs in the existing Fedora 44
KDE x86_64 VM. It does not start R6. A five-file device-material set and retained
template already exist; there is no material acquisition/import or enrollment.

Keep the Goodix reader connected and visible throughout. Start from a working
desktop with SELinux Enforcing and normal sudo credentials. Close fingerprint
settings and authentication dialogs. Do not touch the reader during lifecycle
operations; if stock sudo offers fingerprint first, wait for its normal password
prompt. Do not edit PAM, unplug, unbind or disable the integrated reader.
Use the clean `development` checkout delivered with the current corrective.
If existing project software needs replacement, use `goodix-uninstall` first.

The accepted outputs are:

| Component | Original source commit | Preserved VM output |
| --- | --- | --- |
| R3 private runtime | `b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226` | `/home/guido/goodix-r3-20260922-111144` |
| R4 Plasma Login selector | `6fc6e640710885954d9e6fd603b3bc47b45d2ac6` | `development/build-artifacts/plasma-login-opt-in/goodix-login-build.OeCmF8Ja` inside the VM clone |

Use those original outputs and manifests; there is no reason to rebuild the
qualified binaries for an uninstall-only change. If either output is missing or
does not verify, stop and report it. Do not generate a replacement build or use
the historical managed installer. The runtime installer checks its unchanged
production inputs against the original build commit. The current repository login manager verifies the preserved original output
and installs its corrected inverse; the old saved manager is never executed.
The original binary, PAM input and build manifest are not rewritten.

## Install

From a Bash terminal inside the VM clone, paste this block in full. Stop at the
first error. It installs recovery commands first so they are available if a
later component fails. The usual sudo password is expected.

```bash
(
    set -euo pipefail
    cd "$(git rev-parse --show-toplevel)"
    test "$(git branch --show-current)" = development
    test -z "$(git status --porcelain)"
    printf 'R5_INSTALL_CHECKOUT=%s\n' "$(git rev-parse HEAD)"
    systemd-detect-virt --vm --quiet
    test "$(getenforce)" = Enforcing
    r5_runtime=/home/guido/goodix-r3-20260922-111144
    r5_login="$PWD/development/build-artifacts/plasma-login-opt-in/goodix-login-build.OeCmF8Ja"
    test "$(sed -n '1p' "$r5_runtime/build-provenance.txt")" = \
        SOURCE_COMMIT=b8cdd17f57c9453cc1e89ba5c83da9eb2de8d226
    test "$(sed -n '2p' "$r5_runtime/build-provenance.txt")" = BUILD_MODE=normal
    (cd "$r5_runtime/runtime" && sha256sum -c SHA256SUMS)
    git show 6fc6e640710885954d9e6fd603b3bc47b45d2ac6:deployment/plasma-login-opt-in/manage.py | cmp - "$r5_login/manage.py"
    git show 6fc6e640710885954d9e6fd603b3bc47b45d2ac6:deployment/plasma-login-opt-in/plasmalogin.pam | cmp - "$r5_login/plasmalogin.pam"
    test "$(cat "$r5_login/SOURCE_COMMIT")" = 6fc6e640710885954d9e6fd603b3bc47b45d2ac6
    test "$(cat "$r5_login/VM_TESTS_PASS")" = PASS
    (cd "$r5_login" && sha256sum -c SHA256SUMS)
    ./deployment/recovery/install.sh
    sudo ./deployment/minimal-runtime/install.sh "$r5_runtime"
    sudo python3 -I -B deployment/plasma-login-opt-in/manage.py install "$r5_login"
    test "$(command -v goodix-uninstall)" = /usr/local/bin/goodix-uninstall
    test "$(command -v goodix-force-remove)" = /usr/local/bin/goodix-force-remove
    matchpathcon -V /etc/pam.d/plasmalogin \
        /usr/local/lib64/goodix-plasma-login \
        /usr/local/lib64/goodix-plasma-login/pam_goodix_login_gate.so \
        /usr/local/lib64/goodix-plasma-login/manage.py \
        /usr/local/lib64/goodix-plasma-login/receipt.json
    sudo -N -- systemctl stop fprintd.service
    test "$(systemctl show fprintd.service -p ActiveState --value)" = inactive
    test "$(systemctl show fprintd.service -p MainPID --value)" = 0
    test "$(systemctl show fprintd.service -p LoadState --value)" = loaded
    test ! -e /run/systemd/system/fprintd.service
    test ! -L /run/systemd/system/fprintd.service
    systemctl show fprintd.service -p ExecStart -p Environment -p ActiveState -p MainPID -p LoadState
    test -z "$(git status --porcelain)"
    printf '%s\n' 'R5_INSTALL=PASS READER_PRESENT_ALLOWED=true'
)
```

The original installers enforce the VM, platform, source, payload and existing
material prerequisites, and refuse collisions. The R3 installer creates the
private runtime, library environment drop-in and narrow material SELinux
mapping. The R4 installer publishes its login entry after its module and labels
are ready. Fedora still owns the daemon, greeter and vendor PAM; no authselect,
sudo, PolicyKit or template change is performed. The recovery installer adds
the [removal commands](UNINSTALL.md) to `/usr/local/bin`.

Expected results are component install success, matching default login file
labels, Fedora `/usr/libexec/fprintd` as `ExecStart`, only the private runtime
directory added to `LD_LIBRARY_PATH`, and fprintd inactive/MainPID 0. Lifecycle
code inhibits activation temporarily, stops and verifies the service before
runtime writes, then removes only its own temporary mask without starting the
service. Stock sudo authentication is separate and may briefly use fingerprint;
leave the reader untouched and use its password prompt. The final explicit stop
prepares the lifecycle checkpoint without initiating biometric capture.

**PASS_IF:** all commands succeed and `R5_INSTALL=PASS` is printed, desktop is
usable, reader continuously present, existing materials/templates preserved.
Continue only with the [corrective VM procedure](../deployment/recovery/R5_VM.md).
The install marker alone does not prove fingerprint functionality.

**FAIL_IF / STOP_IF:** a prerequisite, provenance, install or label check fails,
an unexpected project path is occupied, or desktop/password behavior regresses.
Do not overwrite, rebuild, modify Fedora policy or retry authentication. Retain
the exact error and point of failure. If any component was installed, leave the
reader connected and run `goodix-uninstall`; if the desktop cannot be reached,
follow the four [emergency steps](UNINSTALL.md#emergency-graphical-login-is-unavailable).
If normal removal refuses a partial installation, stop and report the refusal;
the fixed-path emergency command is available without the build or repository.

A stop caused by active service state reports that state; close authentication
dialogs and report it, rather than hiding the reader. Replacing an older version
of only the recovery tools uses the current `deployment/recovery/uninstall.sh`
followed by `install.sh`; it does not touch runtime or login integration.

Successful full removal returns the software state to current Fedora and keeps
device materials/templates. A successful installation normally stays installed;
R5 deliberately removes it once more to qualify the agreed emergency path.
