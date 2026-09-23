# Plasma Login: explicit empty-field fingerprint choice

**Installation and file/default-label verification accepted PASS at
`24c3018071e8d120687ff8fbd2f344cde620692d`; keep the installed candidate.**
Build, installation and [real VM login](R4_PLASMA_LOGIN_VM.md) are completed PASS.
Password had no forced fingerprint wait; fingerprint reached the desktop with
one RIGHT-index contact and no password. Plasma Login is SUPPORTED_ON_TESTED_BASELINE.
**R4 is closed. R5 removal qualification is now authorized:** use the
[current removal commands](../../docs/UNINSTALL.md) and
[R5 VM procedure](../recovery/R5_VM.md). The component procedure below is historical.
Do not repeat the completed tests or provoke a failure to exercise B fallback,
which remains NOT_EXERCISED. The qualified R3 runtime and
RIGHT-index template stored as `left-index-finger` stay unchanged.

[Architecture, alternatives and evidence](../../docs/R4_PLASMA_LOGIN_INTEGRATION.md)
explain the current-vendor composition and its remaining qualification limits.
This is a small independent PAM selector, not a rebuilt Plasma component.

## Accepted build and preserved output

The user reports `PLASMA_LOGIN_VM_BUILD_TESTS=PASS`, `Ran 11 tests / OK` and
`INSTALLATION=NOT_PERFORMED` from source
`6fc6e640710885954d9e6fd603b3bc47b45d2ac6`. The initial missing pam-devel STOP
was before compilation; the user installed that build dependency in the VM
and completed the gate. No runtime/PAM corrective or repeat build is required.

The original output `/tmp/goodix-login-build.OeCmF8Ja` was copied intact to
`development/build-artifacts/plasma-login-opt-in/goodix-login-build.OeCmF8Ja`
inside the VM clone. It is excluded only through that clone's `.git/info/exclude`,
not tracked or added to `.gitignore`. Keep the copy and its original manifests.
The production module has fixed vendor paths, independent of its build directory.
The test-only `gate-test.so` embeds temporary fixture paths: do not install it
or rerun the relocated test binaries. The manager selects only the production
module, its PAM entry and the saved inverse.

## Completed installation procedure — do not rerun

`CODEX_MINI_RESUME_R4_PLASMA_INSTALL_PASS.md` reports every success marker below,
all five paths verified against default SELinux labels, unchanged vendor PAM
hash and clean Git status. Desktop open, sensor detached, no logout/reboot/login,
R3 runtime/template preserved. The read-only byte/metadata/receipt checks and
manifest/source comparisons match the versioned procedure; this is accepted
human-reported deployment evidence, not an AI inspection of guest files.
No new fprintd state measurement or runtime SELinux-load result was supplied.

The original instructions below are retained for provenance. Both installation
and the linked login procedure are completed; keep this installation and inverse.

Use the existing Fedora 44 KDE VM, with SELinux Enforcing, reader detached,
and your working desktop session open. Run the block from the ordinary user's
private clone. The sole privileged step is the explicit sudo install; the usual
sudo password may be requested. sudo's stock PAM may activate fprintd with the
reader absent; the installer does not operate services or authenticate a login.

This gate verifies deployment paths and Fedora's actual SELinux file labels
before a later login test. It does not prove that the login helper can load the
module or authenticate. Do not logout, reboot, attach the reader, change policy,
run enroll/verify, restart the display manager or perform a login during this gate.

Paste the entire block; any failure stops it:

```bash
(
    set -euo pipefail
    cd "$(git rev-parse --show-toplevel)"
    test "$(git branch --show-current)" = development
    test -z "$(git status --porcelain)"
    git pull --ff-only origin development
    printf 'GUIDE_CHECKOUT=%s\n' "$(git rev-parse HEAD)"
    r4_source=6fc6e640710885954d9e6fd603b3bc47b45d2ac6
    git diff --exit-code "$r4_source" HEAD -- \
        deployment/plasma-login-opt-in/manage.py \
        deployment/plasma-login-opt-in/pam_goodix_login_gate.c \
        deployment/plasma-login-opt-in/plasmalogin.pam
    r4_build="$PWD/development/build-artifacts/plasma-login-opt-in/goodix-login-build.OeCmF8Ja"
    # Read-only: validate all four manifest entries before executing the saved inverse.
    python3 -I -B - "$r4_build" "$r4_source" <<'PY'
import importlib.util
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location('manager', 'deployment/plasma-login-opt-in/manage.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
data = m.candidate(Path(sys.argv[1]))
m.require(data['SOURCE_COMMIT'] == (sys.argv[2] + '\n').encode(), 'unexpected build source')
m.require(data['plasmalogin.pam'] == Path('deployment/plasma-login-opt-in/plasmalogin.pam').read_bytes(), 'PAM source mismatch')
print('R4_LOGIN_SAVED_BUILD=PASS SOURCE_COMMIT=' + sys.argv[2])
PY
    r4_vendor_before=$(sha256sum /usr/lib/pam.d/plasmalogin)
    sudo python3 -I -B "$r4_build/manage.py" install "$r4_build"

    # Read-only activation checks; no PAM transaction is invoked.
    python3 -I -B - "$r4_build" <<'PY'
import importlib.util
import json
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location('manager', 'deployment/plasma-login-opt-in/manage.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
data = m.candidate(Path(sys.argv[1]))
m.trusted(m.SUPPORT, directory=True, mode=0o755)
m.require({p.name for p in m.SUPPORT.iterdir()} == {m.MODULE, 'manage.py', 'receipt.json'}, 'unexpected support contents')
for installed, expected in ((m.CONFIG, data['plasmalogin.pam']), (m.SUPPORT / m.MODULE, data[m.MODULE]), (m.SUPPORT / 'manage.py', data['manage.py'])):
    m.trusted(installed, mode=0o644)
    m.require(m.read_regular(installed) == expected, 'installed bytes differ: ' + str(installed))
m.trusted(m.SUPPORT / 'receipt.json', mode=0o644)
expected = {'schema': 1, 'source_commit': data['SOURCE_COMMIT'].decode().strip(), 'files': {name: m.digest(data[name]) for name in (m.MODULE, 'manage.py')}, 'config_sha256': m.digest(data['plasmalogin.pam'])}
m.require(json.loads(m.read_regular(m.SUPPORT / 'receipt.json')) == expected, 'receipt mismatch')
print('R4_LOGIN_INSTALLED_FILES=PASS')
PY
    test "$(sha256sum /usr/lib/pam.d/plasmalogin)" = "$r4_vendor_before"
    matchpathcon -V /etc/pam.d/plasmalogin \
        /usr/local/lib64/goodix-plasma-login \
        /usr/local/lib64/goodix-plasma-login/pam_goodix_login_gate.so \
        /usr/local/lib64/goodix-plasma-login/manage.py \
        /usr/local/lib64/goodix-plasma-login/receipt.json
    test -z "$(git status --porcelain)"
    printf '%s\n' 'R4_PLASMA_INSTALL=PASS SENSOR_CONNECTED=false LOGIN_TEST=NOT_PERFORMED'
)
```

The unchanged installer enforces root, VM/Fedora 44/x86_64, Enforcing and reader
absence from USB metadata, verifies the current vendor file's ownership, and
refuses existing project paths. It prepares and labels the module/inverse before
publishing the PAM entry last. The vendor hash comparison is only a before/after
check for this installation, not a saved Fedora copy or a runtime version pin.

**PASS_IF:** exit 0, `R4_LOGIN_SAVED_BUILD=PASS`, `PLASMA_LOGIN_INSTALL=PASS`,
`R4_LOGIN_INSTALLED_FILES=PASS`, matching default contexts and the final
`R4_PLASMA_INSTALL=PASS ... LOGIN_TEST=NOT_PERFORMED`. The desktop stays usable,
reader detached, R3 runtime/template unchanged. Keep this successful installation.

**FAIL_IF / STOP_IF:** any failed prerequisite, collision, changed manifest/source,
install or verification error, unexpected label or desktop regression. Preserve
the error and stop; do not repair Fedora/PAM, change SELinux policy or permissions,
rebuild, bypass checks or force an overwrite. A failure before installation makes
no project change. On failure after installation use the inverse below while
the desktop remains open; do not proceed to login.

Report `GUIDE_CHECKOUT`, the block's output and observed failure point if any.
Confirm desktop open, sensor detached, no login test, R3 runtime/template retained,
and whether rollback was necessary. No journal or broad diagnostic query is
requested. **Stop after this checkpoint for review of the installed state.**

## Owned installation and inverse

Only the following project files become effective; there is no service restart
or load-check. File-label verification is not proof of runtime SELinux permission.

| Project-owned path | Installation effect | Inverse |
| --- | --- | --- |
| `/etc/pam.d/plasmalogin` | New small opt-in prefix and four absolute vendor includes; root:root 0644 | Remove first, reveal current Fedora file |
| `/usr/local/lib64/goodix-plasma-login/pam_goodix_login_gate.so` | New selector; root:root 0644 | Remove after entry point |
| `/usr/local/lib64/goodix-plasma-login/manage.py` | Saved identical inverse; root:root 0644 | Remove with owned support |
| `/usr/local/lib64/goodix-plasma-login/receipt.json` | Owned-file hashes and source SHA; root:root 0644 | Remove last |
| `/usr/local/lib64/goodix-plasma-login/` | New root:root 0755 directory | Remove when empty |

No symlinks, service/drop-in files or Fedora-owned files are installed/changed.
No vendor backup is replayed. The existing R3 runtime under its separate
`goodix-27c6-5125` directory and saved inverse are untouched. Authselect, template
contents, protected material, firmware and persistent device state are untouched.

The corresponding rollback, only on installation/verification/login FAIL,
instability/regression or explicit request, is below. Keep the reader detached
and use a working desktop terminal. Use the preserved candidate's identical
inverse so that partial installation/removal is also recoverable. The installed identical copy
is `/usr/local/lib64/goodix-plasma-login/manage.py`.

```bash
(
    set -euo pipefail
    cd "$(git rev-parse --show-toplevel)"
    r4_build="$PWD/development/build-artifacts/plasma-login-opt-in/goodix-login-build.OeCmF8Ja"
    git show 6fc6e640710885954d9e6fd603b3bc47b45d2ac6:deployment/plasma-login-opt-in/manage.py | cmp - "$r4_build/manage.py"
    sudo python3 -I -B "$r4_build/manage.py" uninstall
    test ! -e /etc/pam.d/plasmalogin
    test ! -L /etc/pam.d/plasmalogin
    test ! -e /usr/local/lib64/goodix-plasma-login
    test ! -L /usr/local/lib64/goodix-plasma-login
    test -f /usr/lib/pam.d/plasmalogin
    printf '%s\n' 'R4_PLASMA_ROLLBACK=PASS CURRENT_VENDOR_VISIBLE=true'
)
```

The inverse checks ownership and hashes, refuses foreign modifications, removes
the project entry before its module, and exposes the **current** packaged PAM.
It does not restore an old Fedora snapshot. A repeated removal with everything
already absent is harmless when using the same saved candidate's `manage.py`.
Keep this candidate/versioned inverse available even after later source changes.

If removal refuses a foreign/changed file, stop and report the refusal; do not
delete it manually. Expected final state is the table above after install PASS,
or its complete absence and current vendor configuration visible after rollback.
No R3 uninstall, template deletion or restoration of old Fedora files is needed.
The [completed login](R4_PLASMA_LOGIN_VM.md) demonstrated functional authentication
and session startup on the installed baseline, with clean safety telemetry.
Failure fallback and real uninstall were not exercised in that PASS; their
source/synthetic evidence is separate. Package-update safety remains unqualified;
R5 removal/recovery qualification is pending the separate human VM procedure.
