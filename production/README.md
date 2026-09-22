<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Reproducible production build

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

The active **build-only** R2 entry point is
[`minimal-runtime/build.sh`](minimal-runtime/build.sh), with the
[manual VM procedure](minimal-runtime/README.md). It creates no host
installation. The first VM build is PASS at `c5df717`; R3-A stock loading is
PASS at install `92311c5`. Keep that installation and the retained R2 output.
The next gate is the [synthetic stock-attempt regression](minimal-runtime/STOCK_ATTEMPTS_VM.md),
before a driver update or sensor test. No replacement release candidate is qualified yet.

## Component classification for the active roadmap

| Path | Classification | Active use |
| --- | --- | --- |
| `source-files.tsv`, `source-files.sha256`, `build-support/`, `build-inner.sh` | R2 extraction inputs | Driver/libfprint/SIGFM and necessary libraries; audit before a VM build |
| `minimal-runtime/`, `check-source.sh --driver-only` | Active R2 extraction | Build/audit only the library set; VM build PASS at c5df717 |
| `build.sh`, default `check-source.sh` | Historical complete stack | Include login/consumer dependencies; not the active minimal runtime path |
| `login/` | HISTORICAL_ONLY / REJECTED_ARCHITECTURE | Preserve private daemon/PAM/greeter sources and evidence |
| `plasma-vt/` | HISTORICAL_ONLY / REJECTED_ARCHITECTURE | Preserve VT bug evidence for possible upstream work |
| `sudo/`, `polkit/` | HISTORICAL_ONLY / REJECTED_ARCHITECTURE | Preserve source/tests; excluded from release |
| `../deployment/managed-install/` | HISTORICAL_ONLY / REJECTED_ARCHITECTURE | Preserve original rollback/recovery; no new deployment |

The classification does not delete or alter historical executables, tests,
digests or saved rollback implementations. The following build description is
historical, including its former claim to be the production build authority.

## Historical build description

This directory is the build authority for Fedora 44 KDE x86_64 and Goodix
`27c6:5125` / APP12509. It builds directly from the publishable source tree and
does not require private Git history or any excluded directory.

The build combines:

- `reference/libfprint-fedora44-1.94.100/source/`;
- the 62 hash-pinned files listed in `source-files.tsv`;
- the fixed build support under `build-support/`;
- five pinned Fedora 44 OpenCV RPMs under
  `GoodixArtifacts/opencv-4.13-rpms/`;
- immutable upstream fprintd 1.94.5 under `reference/`, its canonical patch
  and the GIO greeter in `login/`;
- two pinned PAM/polkit header RPMs under `GoodixArtifacts/login-header-rpms/`
  (or the directory set by `GOODIX_HEADER_RPMS`).

Obtain the five OpenCV RPMs using the command in
`GoodixArtifacts/opencv-4.13-rpms/README.md`. Obtain the two header RPMs without
installing them:

```bash
mkdir -p GoodixArtifacts/login-header-rpms
dnf5 download --destdir GoodixArtifacts/login-header-rpms \
  pam-devel-1.7.2-2.fc44.x86_64 polkit-devel-127-2.fc44.2.x86_64
(cd GoodixArtifacts/login-header-rpms && \
  sha256sum -c ../../production/login/headers.sha256)
```

These seven public, digest-pinned RPMs are external build prerequisites,
excluded from the source export. Reproduction must retrieve them independently
instead of inheriting the working tree's ignored cache. The SDK and Fedora
system libraries/toolchain are also required; this is not a hermetic build
from Git bytes alone. No ignored or untracked *source* file is required.

Run the source audit:

```bash
production/check-source.sh
```

Build into a new or empty absolute directory:

```bash
production/build.sh normal /absolute/path/to/output
production/build.sh sanitizer /absolute/path/to/output
```

The build must run unprivileged. It uses the user-installed Flatpak SDK
`org.freedesktop.Sdk//25.08` with network access disabled. It does not enumerate
USB, load device material, install host files, or start fprintd.

The normal output contains `libfprint-2.so.2.0.0`, staged runtime libraries,
OpenCV notices, ABI reports, and `artifact.sha256`. The script verifies the
Fedora fprintd symbol set, rejects RPATH/RUNPATH, rejects host-only symbols, and
reports a zero dependency count for excluded private content.

The output also contains `fprintd`, `pam_fprintd.so` and `greeter`. SDK objects
are linked with the host Fedora libraries because Fedora PAM requires the host
GLIBC ABI. No host headers/packages are installed by the build. The upstream
fprintd source and downstream login inputs have separate complete digest
manifests; the original prototype's unchanged patch/greeter hashes remain checked
by `login/prototype-equivalence.sha256`. The subsequent
`fprintd-attempts.patch` bounds prepared login to three physical attempts;
current driver/lifecycle hashes are in `source-files.sha256`.
`fprintd-cleanup.patch` blocks late preparation if suspend/abandon invalidated
the request during open; the original patch remains independently verifiable. Build outputs are not claimed identical
to the historical overlay, which used different material loaders.

Run the focused offline closure after both builds:

```bash
production/login/check-offline.sh /absolute/normal /absolute/sanitizer
```

It compiles the actual canonical Fedora core with synthetic USB and matching
seams, exercises private-bus fprintd and real greeter ordering, and runs managed
filesystem transaction tests. It never opens the host system bus or hardware.

Use `deployment/managed-install/manage.sh prepare` to turn a normal build into
an installable, content-addressed candidate with licenses, notices, and SBOM.
