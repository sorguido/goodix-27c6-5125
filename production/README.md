<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Public source build

Ordinary users install and update through the signed RPM and Goodix Manager
using the [documented installation procedure](../docs/INSTALLATION.md). The RPM
build uses this builder to prepare its offline payload; no compiler or source
checkout is needed on the user machine. See [RPM build and signing](../packaging/rpm/README.md)
for the maintainer release procedure.

## Build architecture

`build-public.py` resolves the source root from its own location and builds as
an ordinary user on Fedora 44 or newer x86_64. The distributed RPM is always
built on Fedora 44, the oldest supported baseline. Later Fedora versions
require compatible dependencies and runtime interfaces; Fedora 45 live
qualification remains pending. It uses the public libfprint base, Goodix
driver and a pinned native biometric backend together with supported Fedora
development packages. The native engine's original C sources are included in
the public tree under `production/chicago-native/`.
It does not require Git history, a branch name, a particular clone directory or
pre-existing build output.

The generated payload contains the Goodix-enabled libfprint runtime, the
native biometric code linked from a private static PIC archive, the Plasma Login
selector and PAM entry, the offline material checker, license notices and
source/build provenance. It does **not** contain the previous SIGFM/OpenCV
runtime or Milan diagnostic tools. Fedora supplies fprintd,
libgusb, OpenSSL, PAM, Plasma and the ordinary authentication consumers.

The builder verifies the library ABI and SONAME, stock fprintd resolution,
absence of private RPATH/RUNPATH and forbidden matcher dependencies, PAM selector
checks, source inventories and content hashes before installation. Activation
repeats the ABI and loader checks against the target host before replacing
software or stopping fprintd. It validates
the pinned source manifest for the native algorithm and retains all applicable
upstream copyright and licensing notices. Build provenance records the
source-content digest and package versions rather than depending on Git objects.

The [source ledger](source-files.tsv) and [matching digests](source-files.sha256)
record the public driver sources and their provenance. See
[Licensing and provenance](../docs/LICENSING_AND_PROVENANCE.md) for the combined
library's terms.

## Standalone build (maintainer use)

The RPM builder and optional source installer perform this build automatically.
A standalone build, without deployment, can be used to examine its generated
payload:

```text
python3 production/build-public.py --output /tmp/goodix-build-payload
```

The output location must be new and outside the source tree. No `development/`,
external matcher checkout, USB access, protected biometric input or Windows
calibration is required. The standalone command does not install software,
modify Fedora authentication or touch the reader.

## Validation boundary

The public installer performs the checks required for the supported installation
path. Additional maintainer verification is separate from the end-user procedure
and is not required to install, use, update or remove the driver.

A successful source build does not by itself establish hardware behavior or every
Fedora authentication/SELinux path. The qualified scope and remaining limits are
documented in [Validation](../docs/VALIDATION.md).

## Source installation (advanced)

The root `install.sh` remains available for source-based installation, update and
reinstallation. Ordinary users should use the [RPM procedure](../docs/INSTALLATION.md).
This alternative needs Git, network access for source and Fedora build packages,
and a working password login. Run it as your normal user; the installer requests
sudo for host checks, dependencies and the final application step. It builds
locally before changing project integration and does not open USB.

Use an official tagged checkout for a specific version. To follow `main`, the
existing bootstrap preserves other branches and refuses unrelated directories:

```bash
(
set -e
REPO="$HOME/goodix-27c6-5125"

if [ -d "$REPO/.git" ] && [ ! -L "$REPO" ]; then
    case "$(git -C "$REPO" remote get-url origin)" in
        https://github.com/sorguido/goodix-27c6-5125.git|git@github.com:sorguido/goodix-27c6-5125.git) ;;
        *) echo "STOP: $REPO is not the Goodix Git repository."; exit 1 ;;
    esac
    if [ "$(git -C "$REPO" branch --show-current)" != "main" ]; then
        echo "STOP: use a main checkout for canonical installation; no branch switch was made."
        exit 1
    fi
    git -C "$REPO" pull --ff-only
elif [ ! -e "$REPO" ] && [ ! -L "$REPO" ]; then
    git clone --branch main --single-branch https://github.com/sorguido/goodix-27c6-5125.git "$REPO"
else
    echo "STOP: $REPO exists but is not the Goodix Git repository."
    exit 1
fi

cd "$REPO"
./install.sh
)
```

The subshell stops on errors without closing the terminal. A failed clone or
fast-forward pull does not launch the installer. Output stays visible throughout.
Expect `GOODIX_BUILD=PASS`, an install mode of `FIRST_INSTALL` or `UPDATE`, then
`GOODIX_PAIRING_STATE=READY`, `GOODIX_INSTALL=PASS` and finally
`GOODIX_INSTALL_BLOCK=PASS`. Missing success markers or incomplete rollback mean
failure; use the [documented recovery procedure](../docs/UNINSTALL.md).

The installer resolves its own source directory, so a tagged checkout can live
elsewhere. Neither runtime nor removal commands need the clone after successful
installation. Source installation does not bypass ownership checks or qualify an
unverified legacy migration.
