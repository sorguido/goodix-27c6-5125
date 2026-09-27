<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Installation and updates

## Supported configuration

Fedora 44 KDE on x86_64, a local user account, Goodix USB `27c6:5125` running
`GF_ST411SEC_APP_12509`, and Fedora's stock fprintd, PAM and Plasma Login.
Other hardware, firmware, distributions and network accounts are unsupported.
The complete installer has been exercised successfully on a freshly installed and
updated Fedora 44 KDE VM and on the physical Fedora 44 KDE qualification system
with SELinux Enforcing; see [validation](VALIDATION.md) for the evidence boundary.

## Prerequisites

Use a working, supported Fedora installation with SELinux Enforcing, password
login and ordinary sudo access. Finish authentication dialogs and close fingerprint settings.
**Leave the reader connected and visible throughout installation and removal.**
Keep your finger off it during administrative prompts.

You need Git, network access for the public clone and Fedora packages, and disk
space for a native source build. When no installed material set exists, you also
need a valid [device-material bundle](DEVICE_MATERIALS.md) for your own reader.
The installer builds from the source you clone; it requires no previously compiled
output. It does not obtain materials from the reader.

## Prepare materials for the first installation

Skip this preparation when `/var/lib/goodix-5125-poc/` already holds the valid
material preserved by an earlier installation or removal. Updates and reinstalls
validate and reuse that installed set automatically, even without a Home copy.

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
files must not be executable and must not allow other users to modify them. The
installer checks names, metadata, formats and file bindings before importing
anything; another reader's bundle is not a substitute.
If you do not already have the complete five-file bundle, follow the detailed
[device-material acquisition reference](DEVICE_MATERIALS.md) before continuing.
That procedure is documented separately because it uses the reader's OEM Windows
environment and capture evidence; the Linux installer itself does not extract
secrets or open USB to manufacture the bundle.

## Install, update or reinstall

Use this same block in a normal desktop terminal for first installation, update,
or reinstall after normal or emergency removal, including after deleting the clone:

```bash
(
set -e
REPO="$HOME/goodix-27c6-5125"

if [ -d "$REPO/.git" ] && [ ! -L "$REPO" ]; then
    case "$(git -C "$REPO" remote get-url origin)" in
        https://github.com/sorguido/goodix-27c6-5125.git|git@github.com:sorguido/goodix-27c6-5125.git) ;;
        *) echo "STOP: $REPO is not the Goodix Git repository."; exit 1 ;;
    esac
    git -C "$REPO" pull --ff-only
elif [ ! -e "$REPO" ] && [ ! -L "$REPO" ]; then
    git clone https://github.com/sorguido/goodix-27c6-5125.git "$REPO"
else
    echo "STOP: $REPO exists but is not the Goodix Git repository."
    exit 1
fi

cd "$REPO"
./install.sh
)
```

The subshell stops on errors without closing your terminal. A failed clone or
fast-forward pull does not launch the installer.

`install.sh` automatically selects `FIRST_INSTALL`, `UPDATE` or `REINSTALL`.
It handles the available-material check, supported Fedora prerequisites, source
build, installation and failure reporting. All package-manager,
build and installer output remains visible in the same terminal; the script does
not clear or replace the terminal, redirect the user-visible output, or run the
installation in the background.

Fedora may ask for your sudo password and confirmation before installing packages.
The installer first requests sudo for a read-only material check, and later for
packages and system changes. If Fedora offers fingerprint first, leave the reader
untouched and wait about 30 seconds for the
password prompt. If password authentication is unavailable, stop; do not bypass it.

The installer builds the Goodix library and Plasma Login selector as your normal
user. It reuses valid installed material, or imports the first-install bundle into
`/var/lib/goodix-5125-poc/` with root-only permissions and SELinux labels.
It installs the runtime and login entry, and
`goodix-uninstall` and `goodix-force-remove` in the normal command search path.
It quiesces fprintd during replacement and does not start a fingerprint test.
Fedora's daemon, greeter and vendor authentication files remain package-owned.

Expect **`GOODIX_BUILD=PASS`**, a **`GOODIX_INSTALL_MODE`** of **`FIRST_INSTALL`**,
**`UPDATE`** or **`REINSTALL`**, and material validation success, followed by
**`GOODIX_INSTALL=PASS`** with **`READER_PRESENT_ALLOWED=true`**, and finally
**`GOODIX_INSTALL_BLOCK=PASS`**. Any error or missing final success marker means
installation did not complete. Neither runtime nor either removal command needs the
clone after successful installation. The repository clone may be removed; the
same bootstrap block clones it again automatically when needed. The Home staging
copy is not technically required for ordinary updates or reinstalls as long as
the preserved installed set remains valid. Keep an independent secure backup of
the original bundle; do not delete your only backup.

An invalid installed set stops the operation, even if a valid Home bundle exists.
If both material sources are absent, the installer stops before installing packages
or changing the project installation and requests the original five-file bundle.

Advanced users may clone elsewhere: the installer resolves its own location.
`./install.sh --materials /some/other/path` allows another first-install staging
directory. With installed material, an explicit bundle must be valid and
byte-identical; a mismatch stops without replacing the installed identity.
The standard procedure above needs no override.

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
configuration enables it. The installer does not modify authselect or global PAM
policy. The qualified fresh Fedora baseline had authselect `with-fingerprint`
enabled; systems with an altered Fedora authentication policy may not offer
fingerprint to those consumers until that host policy is corrected.

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

## What updates and reinstalls preserve

The same bootstrap block checks dependencies and rebuilds from current source.
Existing project software is replaced while fprintd is quiescent. A valid installed
material set and existing
templates are preserved; changing a reader's protected bundle is not an implicit
update operation.

After normal or emergency removal, the block reinstalls the software and
restores its material labels. Existing templates remain available. Incompatible
Fedora changes may disable fingerprint functionality; report them or remove the
project instead of replacing Fedora's own authentication components.
