<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Library build and offline checks

The software architecture builds a Goodix-enabled libfprint and the four OpenCV
libraries it needs. Fedora supplies fprintd, libgusb, PAM and the desktop.
A finished public installer, update package and generally supported public build
recipe are not yet available; see [Installation status](../docs/INSTALLATION.md).

## Build inputs and outputs

The library uses the Fedora libfprint 1.94.100 source base, the source files named
in `source-files.tsv`, their matching digests in `source-files.sha256`, and the
inputs covered by `build-support/SHA256SUMS`. OpenCV package digests are recorded
in `build-support/opencv-rpms.sha256`; downloaded packages are external inputs,
not included source artifacts.

The current library builder produces libfprint, four OpenCV libraries, source
and build provenance, ABI/dependency checks and license notices. It does not
build a private fprintd, PAM consumer, greeter or Plasma daemon. Build inputs are
separate from installed device material and fingerprint templates.

Build scripts currently include environment-specific qualification constraints.
They are available for source review and are not presented here as a universal
installation procedure. Publishing a release requires checking its build and
package path from the selected source surface, including all external inputs.

## Source audit

From the source root, this read-only audit verifies the active driver source
manifest and build-support hashes without opening USB or changing host services:

```bash
production/check-source.sh --driver-only
```

Use that explicit scope. A successful source audit proves manifest consistency,
not hardware support, password safety or installability.

## Synthetic lifecycle tests

The following checks use temporary filesystem fixtures and substitute host
service, privilege and device operations:

```bash
python3 -B deployment/recovery/test_remove.py
python3 -B deployment/recovery/test_manage.py
python3 -B deployment/minimal-runtime/test_offline.py
python3 -B deployment/minimal-runtime/test_material_labels.py
python3 -B deployment/plasma-login-opt-in/test_manage.py
```

They exercise reader-present lifecycle control, ownership/drift handling,
removal, preserved data and standalone command invocation. They are not a live
authentication or hardware test. See [Validation](../docs/VALIDATION.md) for
actual observations and [the publication manifest](../PUBLICATION_MANIFEST.md)
for the source boundary.
