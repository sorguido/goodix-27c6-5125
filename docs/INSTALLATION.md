<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Installation and lifecycle management

## Requirements

- Fedora 44 KDE x86_64;
- Goodix USB reader `27c6:5125` running APP12509;
- a clean committed checkout of this source tree;
- `git`, `flatpak`, `cpio`, `binutils`, `rpm-build`, `dnf5-plugins`, `fprintd`,
  `fprintd-pam`, `libfprint`, `libgusb`, `selinux-policy-targeted`,
  `checkpolicy`, `policycoreutils`, and `policycoreutils-devel`;
- Flatpak SDK `org.freedesktop.Sdk//25.08` installed for the current user;
- the legitimate protected-material set for the same physical reader.

Install host prerequisites:

```bash
sudo dnf5 install git flatpak cpio binutils rpm-build dnf5-plugins \
  fprintd fprintd-pam libfprint libgusb selinux-policy-targeted checkpolicy \
  policycoreutils policycoreutils-devel
flatpak remote-add --user --if-not-exists flathub \
  https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.freedesktop.Sdk//25.08
```

## Clone the repository

Clone the project and enter its source directory:

```bash
git clone https://github.com/sorguido/goodix-27c6-5125.git
cd goodix-27c6-5125
```

Verify that the checkout is clean:

```bash
git status --short
```

The command should produce no output. All commands in the following sections
are intended to be run from the repository root unless stated otherwise.

## Pinned OpenCV build inputs

Download, but do not install, the five Fedora RPMs expected by the build:

```bash
mkdir -p GoodixArtifacts/opencv-4.13-rpms
dnf5 download --destdir GoodixArtifacts/opencv-4.13-rpms \
  opencv-core-4.13.0-1.fc44.x86_64 \
  opencv-devel-4.13.0-1.fc44.x86_64 \
  opencv-features2d-4.13.0-1.fc44.x86_64 \
  opencv-flann-4.13.0-1.fc44.x86_64 \
  opencv-imgproc-4.13.0-1.fc44.x86_64
(cd GoodixArtifacts/opencv-4.13-rpms && \
  sha256sum -c ../../production/build-support/opencv-rpms.sha256)
```

Stop if a pinned package is unavailable or a digest differs.

## Build a candidate

The checkout must be clean and committed. Use a new or empty absolute output
directory outside the repository:

```bash
mkdir -m 700 "$HOME/goodix-candidate"
deployment/managed-install/manage.sh prepare "$HOME/goodix-candidate"
(cd "$HOME/goodix-candidate/candidate" && sha256sum -c SHA256SUMS)
```

The build is unprivileged, runs with networking disabled, does not enumerate
USB, and does not load protected material. A successful run prints
`GOODIX_MANAGED_PREPARE=PASS`.

## Import device-specific material

The material directory supplied to the importer must contain exactly the five
files listed in [Device-specific material](DEVICE_MATERIALS.md). That document
explains which files come from the OEM Windows environment, which are
project-derived, and how the historical transfer envelope differs from the
runtime record. Every file must belong to the same physical reader and must
have been obtained lawfully. Do not use a random, null, replacement, or
cross-device PSK. Do not commit, upload, print, or attach this material to bug
reports.

```bash
deployment/managed-install/manage.sh import-materials \
  /absolute/path/to/the/device-material-set
```

The importer copies the files to root-only storage and leaves the source set
unchanged. Success is `GOODIX_MANAGED_MATERIAL_IMPORT=PASS`.

## Install

Review the candidate and keep a text console or other recovery path available.
Then run:

```bash
deployment/managed-install/manage.sh install \
  "$HOME/goodix-candidate/candidate"
deployment/managed-install/manage.sh status
```

The transaction verifies the candidate, source commit, Fedora version, PAM
package ownership, SELinux prerequisites, file metadata, and protected-material
readiness. It fails closed on drift or collision.

After installation, connect the reader and use KDE System Settings > Users to
enroll a fingerprint. Exercise the normal workflows in this order:

1. password login;
2. fingerprint verification in KDE;
3. Plasma login with fingerprint;
4. real session lock and fingerprint unlock;
5. `sudo` with fingerprint;
6. password fallback.

For a verification series, allow at most three physical attempts and stop on
the first match. Do not create a fourth attempt or an unbounded retry loop.

## Update and rollback

Prepare a candidate from the new clean commit, then:

```bash
deployment/managed-install/manage.sh update /absolute/path/to/candidate
deployment/managed-install/manage.sh status
```

Only one previous runtime is retained. A second update is rejected until the
rollback slot is cleared by a supported lifecycle operation. To exchange the
current and previous versions:

```bash
deployment/managed-install/manage.sh rollback
```

Rollback includes the managed PAM state. It does not delete protected material
or fingerprint templates.

## Uninstall and recovery

```bash
deployment/managed-install/manage.sh uninstall
```

Uninstall restores Fedora's fprintd runtime, removes the managed Plasma Login
override, restores the original KDE fingerprint PAM file, and removes the
managed SELinux policy and account hook. Protected material and fprintd
templates are preserved deliberately.

If graphical login is unavailable, use a text console and run the same
uninstall command. Useful non-secret diagnostics are:

```bash
deployment/managed-install/manage.sh status
systemctl status fprintd.service --no-pager
journalctl -b -u fprintd.service --no-pager
getenforce
```

Never attach `/var/lib/goodix-5125-poc`, `/var/lib/fprint`, a fingerprint
image, a template, an OEM binary, or a capture. If the manager reports PAM or
package drift, do not edit around the check; uninstall when permitted or wait
for a reviewed compatibility update.

## Reader-specific material prerequisite

Before installation, generate `target-material-manifest.json` from the same
reader's transport, CONFIG90, FDT cache and typed OEM responses as documented
in `docs/DEVICE_MATERIALS.md`. Do not substitute published/example hashes.
Installation preserves the root-owned `0700` directory and regular `0600`
files required by the runtime.
