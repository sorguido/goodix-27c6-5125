<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# R2: minimal library build on the Fedora VM

**R2 VM BUILD = PASS (22 September 2026).** The user completed this procedure
at `c5df71772b3ade7cf3d1ea2d418a65e0ab75b1f6`. Keep the existing VM output
`/home/guido/goodix-r2-20260922-081148/`; do not rebuild for R3. The instructions
below remain a build reference for future source changes. R3-A stock loading
has also passed at install `92311c5`. Synthetic normal and ASan/UBSan suites
now pass 44/44 at `b8cdd17`, whose normal runtime build is already complete
at `/home/guido/goodix-r3-20260922-111144`, per the user. The next gate is the
[clean replacement](../../../../deployment-history/public-release-transition/deployment/minimal-runtime/README.md), ending with
fprintd stopped before load-check. Do not repeat either completed build.

Run this procedure manually in the Fedora 44
KDE x86_64 VM, as its ordinary user, after pulling `development`. Keep the
Goodix reader disconnected from the guest. No protected material is needed.
The AI uses the physical workspace for source work and safe offline checks;
it does not connect to the VM or execute its builds.

Purpose: build the extracted driver/library set and check its dynamic linkage
against the VM's Fedora fprintd. This was the R2 gate, now completed; the
original R3-A load check is also complete. Do not rebuild for the current
clean replacement handoff.
It does not install the project, run fprintd, enroll/verify, test authentication,
exercise USB, or establish update survivability. No new installer/uninstaller
is appropriate at this build-only boundary: no host runtime file is changed.
The existing managed installer is historical and must not be used.

The [runtime audit](../../../../docs/MINIMAL_RUNTIME.md) lists inputs, output,
exclusions, host-file boundaries and outstanding R3 work. Both the build's
`build-provenance.txt` and the terminal result record the full source commit.
The commit is provenance, not a separate approval requirement.

## Prerequisites and STOP

Use an existing private clone in the VM. From that clone, with no local changes:

```bash
cd "$(git rev-parse --show-toplevel)"
test "$(git branch --show-current)" = development
git status --short
git pull --ff-only origin development
git rev-parse HEAD
```

STOP if the branch differs, status is non-empty, pull fails, the guest is not
Fedora 44 x86_64, the sensor is passed through, the fprintd RPM payload has
drifted, or any command below fails. Do not switch branches, discard changes, import materials or start fprintd to
make this build pass. Source and output paths must have no whitespace, `&`,
backslash or `|`; output must be outside the checkout and must not exist.

The user-installed `org.freedesktop.Sdk//25.08` and the pinned five OpenCV RPMs
are build inputs. The VM also needs stock fprintd, libgusb and Fedora OpenCV
runtime dependencies. If prerequisites are missing, install them **in the VM
only**, using ordinary Fedora/Flatpak packages:

```bash
sudo dnf5 install git flatpak cpio binutils rpm-build dnf5-plugins \
  fprintd libfprint libgusb opencv-core
flatpak remote-add --user --if-not-exists flathub \
  https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.freedesktop.Sdk//25.08
```

These are distro/SDK prerequisites, not a Goodix deployment. The build itself
refuses root. Keep the reader disconnected throughout prerequisite setup.
Download the exact build RPMs without installing the pinned copies:

```bash
mkdir -p GoodixArtifacts/opencv-4.13-rpms
dnf5 download --destdir GoodixArtifacts/opencv-4.13-rpms \
  opencv-core-4.13.0-1.fc44.x86_64 \
  opencv-devel-4.13.0-1.fc44.x86_64 \
  opencv-features2d-4.13.0-1.fc44.x86_64 \
  opencv-flann-4.13.0-1.fc44.x86_64 \
  opencv-imgproc-4.13.0-1.fc44.x86_64
```

If a pinned RPM or SDK is unavailable, STOP and return the error. Do not alter
source manifests or substitute packages. The builder validates every RPM hash
and extracts only those five packages, ignoring unrelated files in the cache.

## Run one normal build

From the repository root in the same VM shell:

```bash
build_out="$HOME/goodix-r2-$(date +%Y%m%d-%H%M%S)"
set -o pipefail
production/minimal-runtime/build.sh normal "$build_out" 2>&1 | tee "$build_out.log"
```

**PASS_IF:** the command exits zero, ends with `MINIMAL_RUNTIME_BUILD=PASS`,
reports the expected full `SOURCE_COMMIT`, and the checks below pass. The VM's
fprintd must resolve libfprint from `runtime/`, with no missing dependency.
The payload contains five shared-library regular files and two libfprint
symlinks, plus licensing/source metadata; no fprintd, PAM module or greeter.

```bash
cat "$build_out/build-provenance.txt"
cat "$build_out/fprintd.ldd"
(cd "$build_out/runtime" && sha256sum -c SHA256SUMS)
```

**FAIL_IF:** compilation, symbol coverage, dependency resolution or hashes fail.
**STOP_IF:** failure, missing prerequisite, unexpected host mutation, USB access,
material request, or any demand to execute the old managed workflow. Do not
install the output or try enrollment/verification after a successful build.
R3 needs a separate offline review and reversible installation handoff.

## Cleanup and evidence to return

On PASS, keep the output for R3. On FAIL, preserve the log and any partial output
until the failure has been reviewed; no service/configuration rollback is
needed. If discarding this build later, the inverse is removal of its output:

```bash
rm -r -- "$build_out"
```

This removes only the named build directory, not packages, the SDK, source,
materials or templates. The `.log` file remains available. Never use sudo for
this cleanup. Prerequisite distro packages are not part of the project rollback.

Return the full `SOURCE_COMMIT`, final build result, `build-provenance.txt`,
`fprintd.ldd` and hash-check outcome. On failure, return the exact command/stage
and the relevant error from the saved build log. No USB captures, device
materials, fingerprint data or authentication logs are requested.
