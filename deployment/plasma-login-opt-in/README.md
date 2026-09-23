# Plasma Login: explicit empty-field fingerprint choice

**Current gate: human VM build and synthetic tests only. No installation or
login test yet.** R4 is open and R5 is blocked. The qualified R3 runtime and
RIGHT-index template stored as `left-index-finger` stay unchanged.

[Architecture, alternatives and evidence](../../docs/R4_PLASMA_LOGIN_INTEGRATION.md)
explain the current-vendor composition and its remaining qualification limits.
This is a small independent PAM selector, not a rebuilt Plasma component.

## Run now, in the existing VM

Keep the desktop open, the Goodix reader detached from the VM, and SELinux
Enforcing. Use the ordinary user, not root. This builds only the new selector
and its synthetic tests; it does not rebuild or reinstall R3. Required existing
tools are gcc, pam-devel, Python 3, Git, RPM and the normal Fedora utilities.
If a dependency is missing, stop and report that error; do not improvise a
package transaction in this step.

From the VM's private clone on `development`, paste this block as a whole:

```bash
(
    set -euo pipefail
    cd "$(git rev-parse --show-toplevel)"
    test "$(git branch --show-current)" = development
    test -z "$(git status --porcelain)"
    git pull --ff-only origin development
    git rev-parse HEAD
    bash deployment/plasma-login-opt-in/build-vm.sh
)
```

The build script enforces VM/Fedora 44/x86_64, non-root, Enforcing, reader
absence from USB metadata and a clean `development` checkout. It records the
full source commit and hashes its output. The temporary directory printed as
`BUILD_OUTPUT` contains the candidate and can remain for review.

The C unit test supplies fake tokens and temporary configuration text. The
dispatcher test uses the VM's actual libpam with `pam_start_confdir`, a private
temporary service and synthetic modules, including a test-path variant of the
real selector. Every module/include path is restricted to test inputs. It never
loads pam_unix, pam_fprintd, the real SELinux module or the system login service.
There is no real user authentication, secret, fprintd call, service action, USB
open or sensor command. Python lifecycle tests mock host/privilege operations.

**PASS_IF:** the command exits 0, all unit/dispatch/lifecycle cases pass, and the
last output includes `PLASMA_LOGIN_VM_BUILD_TESTS=PASS`, `BUILD_OUTPUT=...` and
`INSTALLATION=NOT_PERFORMED`.

**FAIL_IF / STOP_IF:** any command, compilation, assertion, prerequisite or
source-integrity check fails. Do not bypass a check, install the output, use
sudo, connect the reader, log out, reboot, or try a password/fingerprint login.
The missing-reset negative test is expected to observe a synthetic credential
failure internally; the overall test must nevertheless exit successfully.

Report the full checkout SHA, output from this small build/test block and its
`BUILD_OUTPUT` path. Confirm reader detached, no install/login/USB action and
runtime/template unchanged. No additional system log query is requested.
After PASS, stop for review; no automatic continuation to installation.

**Rollback for this gate:** none is needed on the system because no runtime
configuration was changed. Keep the build directory for review. A failed build
does not require uninstalling the working R3 runtime or deleting its template.

## Owned installation and inverse (prepared, not the current procedure)

The installation/removal implementation is supplied now for audit. It becomes
an operator procedure only after the VM results and a separate concrete login
handoff have been reviewed. Do not execute it during the build/test gate.

Future installation entry point, from the printed build directory:
`sudo python3 "$BUILD_OUTPUT/manage.py" install "$BUILD_OUTPUT"`.
This is one ordinary sudo authorization, with the sensor detached. It verifies
the build manifest and completed VM tests, environment, current vendor package
ownership and absence of colliding files. It labels the support files before
publishing the PAM entry atomically, last. It starts/restarts no service and
performs no authentication. The directory variable must be set explicitly to
the actual output; it is not populated in the parent shell by the build script.

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

The corresponding future rollback is:
`sudo python3 /usr/local/lib64/goodix-plasma-login/manage.py uninstall`.
Run it on a real installation FAIL, instability/regression, or explicit request;
keep a successful validated advancement by default. The reader must be detached.
The inverse checks ownership and hashes, refuses foreign modifications, removes
the project entry before its module, and exposes the **current** packaged PAM.
It does not restore an old Fedora snapshot. A repeated removal with everything
already absent is harmless when using the same saved candidate's `manage.py`.
Keep this candidate/versioned inverse available even after later source changes.

For later install/remove review, expected state is the exact table above or its
complete absence respectively, with vendor files unchanged and normal stock
login available after removal. SELinux loading, real login/password fallback,
contact telemetry and package-update behavior are still untested. Their normal
workflow, observable PASS/FAIL criteria and any necessary targeted diagnosis
will be specified in the later login handoff; this README does not grant a live.
