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
Acquisition, extraction and construction of these files are outside this guide.

## Install

Paste this **single block** into a normal desktop terminal. It uses
`$HOME/goodix-27c6-5125` for the clone and the materials folder above. Use a
published revision containing `install.sh`; if the public repository does not
yet contain that entrypoint, stop and wait for its publication.

```bash
set -euo pipefail

REPO="$HOME/goodix-27c6-5125"
MATERIALS="$HOME/goodix-5125-materials"

test -d "$MATERIALS"

sudo dnf install git python3 gcc gcc-c++ meson ninja-build pkgconf-pkg-config \
    glib2-devel libgusb-devel openssl-devel opencv-devel pam-devel binutils \
    fprintd fprintd-pam policycoreutils-python-utils

if [ ! -d "$REPO/.git" ]; then
    git clone https://github.com/sorguido/goodix-27c6-5125.git "$REPO"
else
    git -C "$REPO" pull --ff-only
fi

cd "$REPO"
./install.sh
```

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

Use the **same install block** with the same materials directory. It updates the
clone, checks dependencies and rebuilds from the current source. The installer
checks existing project software and performs replacement while fprintd is
quiescent. A valid installed material set and existing templates are preserved;
changing a reader's protected bundle is not an implicit update operation.

After normal or emergency removal, the same block reinstalls the software and
restores its material labels. Existing templates remain available. Incompatible
Fedora changes may disable fingerprint functionality; report them or remove the
project instead of replacing Fedora's own authentication components.
