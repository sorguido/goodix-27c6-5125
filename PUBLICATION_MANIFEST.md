<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Public source manifest

The publishable source surface consists of these paths:

```text
.gitignore
ACKNOWLEDGEMENTS.md
LICENSE
LICENSES/
README.md
TECHNICAL_MANUAL.md
PUBLICATION_MANIFEST.md
docs/
deployment/managed-install/
GoodixArtifacts/opencv-4.13-rpms/README.md
libfprint-driver/                       (source files only)
production/
reference/libfprint-fedora44-1.94.100/
reference/fprintd-fedora44-1.94.5/
Rockytkg/libfprint/libfprint/sigfm/     (four production source files only)
```

The following local entries are not part of that surface:

- `.git/` and editor/agent workspace mounts;
- `development/`, which contains private historical/recovered project material;
- downloaded OpenCV and PAM/polkit header RPM payloads, which are external
  hash-pinned build prerequisites retrieved from Fedora using the commands in
  `production/README.md` and the OpenCV README;
- generated or acquired device material, OEM caches, private captures,
  fingerprint images, templates, secrets, and other protected input/output
  files.

The source build, offline tests, installer, and documentation do not depend on
anything under `development/`. The private Git history is not an input to the
public source transfer. Export only committed files from the paths in the allowlist above; copying a
working tree can accidentally retain ignored/untracked files. Include tracked
dotfiles and the synthetic test sources under `libfprint-driver/tests/`. The
four SIGFM files are `sigfm.cpp`, `sigfm.h`, `binary.hpp` and `img-info.hpp`.
The fprintd reference contains 141 retained upstream files under `source/`
and three reference metadata files outside it; its eight upstream biometric
test images remain excluded. External RPMs, the SDK and Fedora system libraries
are prerequisites, not source-export content. A clean local Git checkout is
required by managed preparation to record source provenance; private history
is not required.

Device-material acquisition, extraction, recovery, and generation tooling is
outside the supported public release scope. The public runtime consumes a
pre-existing, valid five-file material bundle for the user's reader and does
not provide tools for constructing that bundle from OEM Windows artifacts.

Before transferring an updated tree, run:

```bash
production/check-source.sh
python3 deployment/managed-install/test_offline.py
```

Then confirm that no unexpected binary, capture, key, firmware, protected
material, fingerprint image, template, acquisition helper, or OEM payload has
been added to the allowlisted paths.
