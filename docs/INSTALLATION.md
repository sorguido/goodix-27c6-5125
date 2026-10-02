<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Installation and updates

## Supported configuration

Fedora 44 KDE on x86_64, a local user account, Goodix USB `27c6:5125` running
`GF_ST411SEC_APP_12509`, Fedora's stock fprintd, PAM and Plasma Login, and SELinux
Enforcing. Other hardware, firmware, distributions and network accounts are
unsupported. See [validation](VALIDATION.md) for the qualification boundary.

## Prerequisites

Use a working, supported Fedora installation with SELinux Enforcing, password
login and ordinary sudo access. Finish authentication dialogs and close fingerprint settings.
The reader may be absent during installation, update, reinstall and removal.
When it is present, keep your finger off it during administrative prompts.

You need Git, network access for the public clone and Fedora packages, and disk
space for a native source build. Nothing has to be prepared for the reader: no
Windows machine, no capture tooling, no private key material and no
reader-specific file. The installer builds from the source you clone; it requires
no previously compiled output, and it does not open USB.

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

`install.sh` automatically selects `FIRST_INSTALL` or `UPDATE`.
It handles the host state check, supported Fedora prerequisites, source
build, installation and failure reporting. All package-manager,
build and installer output remains visible in the same terminal; the script does
not clear or replace the terminal, redirect the user-visible output, or run the
installation in the background.

Fedora may ask for your sudo password and confirmation before installing packages.
The installer first requests sudo for a read-only host state check, and later for
packages and system changes. If Fedora offers fingerprint first, leave the reader
untouched and wait about 30 seconds for the
password prompt. If password authentication is unavailable, stop; do not bypass it.

The installer builds the Goodix library and Plasma Login selector as your normal
user. It always creates or preserves
`/var/lib/fprint/goodix-5125-state-v2/` as the root-only host pairing state
location, labels it and verifies its permissions. It does not
open the reader or initialize pairing.
It installs the runtime and login entry, and
`goodix-uninstall` and `goodix-force-remove` in the normal command search path.
It quiesces fprintd during replacement and does not start a fingerprint test.
Fedora's daemon, greeter and vendor authentication files remain package-owned.

### Fingerprint temporary suspension

When a temporary password-only session is needed, for example during remote access
where the physical reader cannot be used, fingerprint authentication can be
suspended without uninstalling the driver, deleting templates, changing host
pairing state, or rewriting PAM/authselect policy:

```bash
sudo systemctl mask --runtime --now fprintd.service
```

The runtime mask prevents stock fingerprint consumers from activating `fprintd`
for the current boot, so authentication falls back to the remaining Fedora policy
instead of waiting for an unavailable fingerprint interaction. Restore fingerprint
availability at any time, without rebooting, with:

```bash
sudo systemctl unmask --runtime fprintd.service
```

There is no need to start `fprintd` manually after the unmask: the next normal
fingerprint consumer can activate it through the stock D-Bus/systemd path. Because
the mask is runtime-only, a reboot also clears it automatically; reboot is not
required for either suspension or restoration.

Expect **`GOODIX_BUILD=PASS`**, a **`GOODIX_INSTALL_MODE`** of **`FIRST_INSTALL`**
or **`UPDATE`**, then **`GOODIX_PAIRING_STATE=READY`** confirming the
host pairing state root is ready, followed by
**`GOODIX_INSTALL=PASS`** with **`READER_PRESENT_ALLOWED=true`**, and finally
**`GOODIX_INSTALL_BLOCK=PASS`**. Any error or missing final success marker means
installation did not complete. Neither runtime nor either removal command needs the
clone after successful installation. The repository clone may be removed; the
same bootstrap block clones it again automatically when needed.

A fresh install creates only the empty host pairing state root. The runtime then
initializes the reader itself on the first fingerprint action: it confirms the
target identity, derives the configuration from the reader's own OTP, stores a
locally generated pairing key and records it with a single bounded pairing write.
Ordinary later use reuses that stored key and writes nothing to the reader.
Password and desktop access remain available throughout.

Advanced users may clone elsewhere: the installer resolves its own location.
The standard procedure above needs no override.

## Enrollment and basic verification

After successful installation, use KDE's normal fingerprint settings to manage
your enrolled fingers. The first fingerprint action takes slightly longer while
the reader is initialized; later actions do not repeat that step. If your finger
is already enrolled, keep that enrollment;
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
policy. The supported Fedora configuration uses authselect `with-fingerprint`;
systems with an altered Fedora authentication policy may not offer fingerprint
to those consumers until that host policy is corrected.

## If installation or authentication fails

Stop at the first error and keep its exact non-secret message. A failed
prerequisite does not authorize bypassing a safety check. The installer reports
rollback if a system change fails; incomplete rollback is an error, not success.

If project software remains installed or authentication regresses, use
**`goodix-uninstall`** from the working desktop. If normal removal refuses damaged
project state or the desktop is unavailable, use **`goodix-force-remove`** according
to [the emergency instructions](UNINSTALL.md). Follow its final restart instruction
and verify password login. Do not delete templates or host pairing state, change
Fedora PAM by hand, disable SELinux or hide the reader.

Report the command, error, failure point and whether password/desktop access works.
Never attach host pairing state, templates, fingerprint images or raw USB captures.

## What updates and reinstalls preserve

The same bootstrap block checks dependencies and rebuilds from current source.
Existing project software is replaced while fprintd is quiescent. Host pairing
state and existing templates are preserved; a reader's pairing identity is never
changed by an update, and reinstallation after removal does not re-pair it.

After normal or emergency removal, the block reinstalls the software and
restores its SELinux labels. Existing templates remain available. Incompatible
Fedora changes may disable fingerprint functionality; report them or remove the
project instead of replacing Fedora's own authentication components.

## Using the reader with Windows

The same reader can be shared with Windows. Windows may replace the reader's
pairing when it initializes the device; Linux classifies that change read-only,
preserves the Windows record byte-for-byte and restores its own stored key with
one qualified write on the next fingerprint action. No reinstall, re-enrollment
or manual key handling is needed, and no key is shared between the two operating
systems. Coexistence is qualified for one reader and one Windows 11 virtual
machine; see [validation](VALIDATION.md) for that boundary.
