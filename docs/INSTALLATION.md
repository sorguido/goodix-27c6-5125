<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Installation and updates

## Supported configuration

Fedora 44 KDE on x86_64, a local user account, Goodix USB `27c6:5125` running
`GF_ST411SEC_APP_12509`, and Fedora's stock fprintd, PAM and Plasma Login.
Other hardware, firmware, distributions and network accounts are unsupported.
The complete installer still needs physical-system confirmation; see
[validation](VALIDATION.md) before treating it as a qualified release.

## Prerequisites

Use a working, supported Fedora installation with SELinux Enforcing, password
login and ordinary sudo access. Finish authentication dialogs and close fingerprint settings.
**Leave the reader connected and visible throughout installation and removal.**
Keep your finger off it during administrative prompts.

You need network access for the public clone and Fedora packages, disk space for
a native source build, and an existing valid [device-material bundle](DEVICE_MATERIALS.md)
for your own reader. The installer builds from the source you clone; it requires
no previously compiled output. It does not obtain materials from the reader.

## Prepare the five protected files

Create or use **`$HOME/goodix-5125-materials/`**, outside the clone, and place
exactly these five files directly inside it:

```text
target-material-manifest.json
transport-material.bin
target-config-90.bin
gfusb.dll
fdt-cache.bin
```

Do not rename them, put them in a subfolder, or place them inside the repository.
In the file manager, enable hidden-file display and check that these are the only
five entries and are ordinary files, not links. Keep this folder private and do
not share or commit it. The directory and files must belong to your normal user;
files must not be executable and must not allow other users to modify them. The installer checks names, metadata, formats and file
bindings before importing anything; another reader's bundle is not a substitute.
If you do not already have the complete five-file bundle, follow the detailed
[device-material acquisition reference](DEVICE_MATERIALS.md) before continuing.
That procedure is documented separately because it uses the reader's OEM Windows
environment and capture evidence; the Linux installer itself does not extract
secrets or open USB to manufacture the bundle.

## Install

The only bootstrap that must remain outside `install.sh` is obtaining the public
repository itself: the script cannot run before it exists on disk. Everything
after that — protected-material staging check, Fedora prerequisites, build,
installation and failure reporting — is handled by `install.sh`.

Paste this **single bootstrap block** into a normal desktop terminal. It uses
`$HOME/goodix-27c6-5125` for the public clone. It never clears or replaces the
terminal, redirects installer output, or runs the installation in the background:
all clone, package-manager, build and installer output remains visible in the same
terminal for the full operation.

```bash
_goodix_bootstrap() {
    local REPO="$HOME/goodix-27c6-5125"
    local rc

    printf '\n==> [bootstrap 1/2] Ensuring Git is available\n'
    if ! command -v git >/dev/null 2>&1; then
        sudo dnf install git || {
            rc=$?
            printf 'GOODIX_BOOTSTRAP=STOP STEP=git_dependency EXIT_CODE=%d\n' "$rc" >&2
            return "$rc"
        }
    fi

    printf '\n==> [bootstrap 2/2] Cloning or updating the public repository\n'
    if [ -d "$REPO/.git" ]; then
        git -C "$REPO" pull --ff-only || {
            rc=$?
            printf 'GOODIX_BOOTSTRAP=STOP STEP=update EXIT_CODE=%d\n' "$rc" >&2
            return "$rc"
        }
    elif [ -e "$REPO" ]; then
        printf 'GOODIX_BOOTSTRAP=STOP STEP=clone REASON=path_exists_not_git PATH=%s\n' "$REPO" >&2
        return 11
    else
        git clone https://github.com/sorguido/goodix-27c6-5125.git "$REPO" || {
            rc=$?
            printf 'GOODIX_BOOTSTRAP=STOP STEP=clone EXIT_CODE=%d\n' "$rc" >&2
            return "$rc"
        }
    fi

    cd "$REPO" || {
        rc=$?
        printf 'GOODIX_BOOTSTRAP=STOP STEP=enter_repository EXIT_CODE=%d\n' "$rc" >&2
        return "$rc"
    }

    ./install.sh
}

if _goodix_bootstrap; then
    printf '\nGOODIX_BOOTSTRAP=PASS\n'
else
    rc=$?
    printf '\nGOODIX_BOOTSTRAP=STOP EXIT_CODE=%d\n' "$rc" >&2
    printf 'The terminal remains open. Copy the complete output above before retrying.\n' >&2
fi

unset -f _goodix_bootstrap
```

The bootstrap deliberately uses a separate public clone at
`$HOME/goodix-27c6-5125`. A development checkout elsewhere is not modified.

Once the clone exists, `./install.sh` is also the direct entrypoint for subsequent
local runs. It checks the materials directory, installs the supported Fedora
prerequisites, builds the source and performs the privileged installation. A failure
prints `GOODIX_INSTALL_BLOCK=STOP` with the failing stage and exit code; success
prints `GOODIX_INSTALL_BLOCK=PASS`. Because the supported procedure is pasted
into an already-open terminal, returning from either the bootstrap or installer
does not close that terminal.

Fedora may ask for your sudo password and confirmation before installing packages.
The installer later requests sudo itself for the system changes. If Fedora offers
fingerprint first, leave the reader untouched and wait about 30 seconds for the
password prompt. If password authentication is unavailable, stop; do not bypass it.

The installer builds the Goodix library and Plasma Login selector as your normal
user. It then imports the five files into `/var/lib/goodix-5125-poc/` with root-only
permissions and SELinux labels, installs the runtime and login entry, and installs
`goodix-uninstall` and `goodix-force-remove` in the normal command search path.
It quiesces fprintd during replacement and does not start a fingerprint test.
Fedora's daemon, greeter and vendor authentication files remain package-owned.

Expect **`GOODIX_BUILD=PASS`** and material validation success, followed by
**`GOODIX_INSTALL=PASS`**
with **`READER_PRESENT_ALLOWED=true`**. Any error or missing final success marker
means installation did not complete. Neither runtime nor either removal command
needs the clone after successful installation. Keep the staging files securely
for future reinstallations.

Advanced users may clone elsewhere: the installer resolves its own location.
`./install.sh --materials /some/other/path` selects another staging directory;
the standard procedure above needs no override.

## Enrollment and basic verification

After successful installation, use KDE's normal fingerprint settings to manage
your enrolled fingers. If your finger is already enrolled, keep that enrollment;
installation preserves existing templates. Otherwise enroll one finger following
the normal prompts, without opening simultaneous fingerprint applications.

Check ordinary password login first. For the fingerprint check at Plasma Login,
submit the empty password field once and follow its prompts with the enrolled
finger. Stop on the first successful match. If it does not match, allow at most
three explicit physical attempts in that series; after the third failure use
password and report the result. Do not start repeated test series or add a fourth
attempt. A password-encrypted KWallet may ask for its own password after login.
Other consumers offer fingerprint where the current Fedora authentication
configuration enables it. The installer does not modify authselect or global
PAM policy.

## If installation or authentication fails

Stop at the first error and keep its exact non-secret message. A failed
prerequisite does not authorize bypassing a safety check. The installer reports
rollback if a system change fails; incomplete rollback is an error, not success.

If project software remains installed or authentication regresses, use
**`goodix-uninstall`** from the working desktop. If normal removal refuses damaged
project state or the desktop is unavailable, use **`goodix-force-remove`** according
to [the emergency instructions](UNINSTALL.md). Follow its final restart instruction
and verify password login. Keep the reader connected. Do not delete templates or
materials, change Fedora PAM by hand, disable SELinux or hide the reader.

Report the command, error, failure point and whether password/desktop access works.
Never attach your five files, templates, fingerprint images or raw USB captures.

## Update or reinstall

Use the **same bootstrap block** with the same materials directory. It updates the
public clone and then runs `install.sh`; the script checks dependencies and rebuilds
from the current source. The installer
checks existing project software and performs replacement while fprintd is
quiescent. A valid installed material set and existing templates are preserved;
changing a reader's protected bundle is not an implicit update operation.

After normal or emergency removal, the same block reinstalls the software and
restores its material labels. Existing templates remain available. Incompatible
Fedora changes may disable fingerprint functionality; report them or remove the
project instead of replacing Fedora's own authentication components.
