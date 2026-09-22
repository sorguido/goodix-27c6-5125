<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Installation and lifecycle management

> **HISTORICAL_ONLY / REJECTED_ARCHITECTURE — 22 September 2026.**
> The managed candidate, private fprintd/PAM pair, Plasma daemon/greeter,
> KScreenLocker overrides and custom sudo/PolicyKit integrations described
> below are preserved as historical evidence. Their installation, build and
> live instructions are not the active release workflow. Past PASS results
> do not qualify them for the new release.
>
> Follow the [distro-decoupled roadmap](../ROADMAP_DISTRO_DECOUPLED_RELEASE.md). R0 restored the physical
> Fedora host to its stock baseline; new build/runtime validation is VM-only.
> The next runtime must use the Goodix library with Fedora stock fprintd and
> stock authentication consumers. No replacement candidate is ready yet.

## Requirements

- Fedora 44 KDE x86_64;
- Goodix USB reader `27c6:5125` running APP12509;
- a clean committed checkout of this source tree;
- `gcc`, `git`, `patch`, `flatpak`, `cpio`, `binutils`, `rpm-build`, `dnf5-plugins`, `fprintd`,
  `fprintd-pam`, `libfprint`, `libgusb`, `selinux-policy-targeted`,
  `checkpolicy`, `policycoreutils`, and `policycoreutils-devel`;
- Flatpak SDK `org.freedesktop.Sdk//25.08` installed for the current user;
- a valid five-file protected-material bundle for the same physical reader.

Install host prerequisites:

```bash
sudo dnf5 install gcc patch git flatpak cpio binutils rpm-build dnf5-plugins \
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

## Paired login build inputs

Download the two header packages without installing them:

```bash
mkdir -p GoodixArtifacts/login-header-rpms
dnf5 download --destdir GoodixArtifacts/login-header-rpms \
  pam-devel-1.7.2-2.fc44.x86_64 polkit-devel-127-2.fc44.2.x86_64
(cd GoodixArtifacts/login-header-rpms && \
  sha256sum -c ../../production/login/headers.sha256)
```

The qualified login integration requires `plasma-login-manager-6.7.5-1.fc44`
and `fprintd-1.94.5-5.fc44`, their unmodified vendor units/PAM and the existing
`plasmalogin` account. Header files are extracted only inside the build output.
No previous development runtime is required or accepted as a prerequisite.

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
files listed in [Device-specific material](DEVICE_MATERIALS.md). Every
reader-specific value must describe the same physical reader, and the OEM DLL
must match the qualified compatibility boundary. The files must have been
obtained lawfully. Do not use a random, null, replacement, or cross-device PSK.
Do not commit, upload, print, or attach this material to bug reports.

Acquisition, extraction, recovery and generation of a fresh five-file bundle
are outside the supported scope of this release. The repository does not
provide tooling for constructing the bundle from OEM Windows caches or USB
captures. If you do not already have a valid bundle, stop here.

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

The greeter drop-in takes effect on the next normal greeter startup (normally
the next boot); installation does not restart the desktop. After installation, connect the reader and use KDE System Settings > Users to
enroll a fingerprint. Exercise the normal workflows in this order:

1. password login;
2. fingerprint verification in KDE;
3. Plasma login with fingerprint;
4. real session lock and fingerprint unlock;
5. password fallback and service-local sudo/sudo-i fingerprint behavior;
6. Polkit/Discover password, explicit fingerprint choice, cancellation and fallback
   as described in `production/polkit/README.md`. Polkit support remains pending live validation.

The clean installer owns sudo/sudo-i fingerprint authentication without D285,
sudoers edits or global fingerprint. Initial password entry is immediate; Enter
selects one attempt with an 8-second total ceiling, at most three per invocation.
See `production/sudo/README.md` and
`deployment/managed-install/AUTHENTICATION-LIVE.md` for native workflow,
contention cases, exact install/rollback commands and the separate development-PC
migration gate. Both integrations remain live-unvalidated.

Polkit requires the audited local password stack without global fingerprint and
the exact versions listed in `production/polkit/README.md`. Close authentication
dialogs during lifecycle changes. The candidate owns the Polkit PAM override,
leaf service, runtime counter directory/tmpfiles rule and narrow helper socket
drop-in. The PAM bridge is paired with the immutable current runtime; update and
rollback preserve its counters. Existing managed releases without
`POLKIT_INTEGRATION=INTERRUPTIBLE_SERVICE_LOCAL_V1` or
`SUDO_INTEGRATION=PASSWORD_FIRST_SERVICE_LOCAL_V1` must use their original
installer to uninstall, then install this candidate fresh. Do not update them
in place or apply the development PC patch over a managed installation.

For the prepared cold login, press Enter once and place the finger naturally
immediately. This path permits at most three physical attempts, each bounded
by 8 seconds. After a normal NO MATCH, fully release the finger and wait for
the result before making a new contact. Stop immediately on MATCH. After
three NO MATCH, or any error/timeout, use password. Do not press Enter again
within the same authentication. For an ordinary
verification series, allow at most three physical attempts and stop on
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

Rollback switches driver, paired daemon, PAM and greeter together and includes
the managed PAM state. Older managed releases without early login, or with
the previous one-attempt PAM rule, must first be removed using their original
version of the manager and documented uninstall, then installed fresh; an
in-place update is rejected before mutation. Update/rollback within the new
three-attempt rule remains supported. Historical development overlays must also
be rolled back first. It does not delete protected material
or fingerprint templates.

## Uninstall and recovery

```bash
deployment/managed-install/manage.sh uninstall
```

Uninstall restores Fedora's fprintd runtime, removes the managed Plasma Login
override, restores the original KDE fingerprint PAM file, and removes the
managed SELinux policy and account hook, and removes the greeter drop-in and
paired components. Original daemon, PAM module and greeter binaries are never
overwritten. Protected material and fprintd
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

## Observable acceptance and recovery

`PASS_IF`: immediate natural cold login succeeds after Enter; password, ordinary
sudo and session unlock remain usable. Keep a successful candidate installed.
`FAIL_IF`: login preparation fails, fingerprint login regresses or any ordinary
workflow stops working; use password and uninstall (or rollback an update).
`STOP_IF`: missing prerequisites, package/owned-file drift, unknown overrides,
missing valid material, or repeated unexpected failures. Do not bypass checks.
Report the observed workflow, exact error and failure point; logs are needed
only when a failure requires them. Uninstall should leave vendor PAM/daemon/UI
in use and preserve templates/material. This promotion task itself performs
no installation, reboot or live acceptance run.

## Reader-specific material prerequisite

Installation requires a pre-existing valid five-file bundle for the same
reader. The runtime remains device-dynamic and validates the supplied manifest,
material digests and live typed-response pins; published/example development
hashes are not accepted as a substitute. Installation preserves the root-owned
`0700` directory and regular `0600` files required by the runtime.
