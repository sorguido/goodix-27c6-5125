<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Reproducible production build

This directory is the build authority for Fedora 44 KDE x86_64 and Goodix
`27c6:5125` / APP12509. It builds directly from the publishable source tree and
does not require private Git history or any excluded directory.

The build combines:

- `reference/libfprint-fedora44-1.94.100/source/`;
- the 62 hash-pinned files listed in `source-files.tsv`;
- the fixed build support under `build-support/`;
- five pinned Fedora 44 OpenCV RPMs under
  `GoodixArtifacts/opencv-4.13-rpms/`.

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

The expected qualified library digest is:

```text
115db4450272435c80ecb61e3540577b99c8355fb02a0f1648175104a7c3dd20
```

Use `deployment/managed-install/manage.sh prepare` to turn a normal build into
an installable, content-addressed candidate with licenses, notices, and SBOM.
