<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Public source manifest

The publishable source surface consists of these paths:

```text
.gitignore
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
Rockytkg/libfprint/libfprint/sigfm/     (four production source files only)
```

The following local entries are not part of that surface:

- `.git/` and editor/agent workspace mounts;
- `red_tag/`, which exists only in the private workspace;
- downloaded OpenCV RPM payloads, which are host-local build inputs and are
  retrieved from Fedora using the documented command.

The source build, offline tests, installer, and documentation do not consume
anything under `red_tag/`. The private Git history is not an input to the
public source transfer. Copy only the paths in the allowlist above.

Before transferring an updated tree, run:

```bash
production/check-source.sh
python3 deployment/managed-install/test_offline.py
```

Then confirm that no unexpected binary, capture, key, firmware, protected
material, fingerprint image, or template has been added to the allowlisted
paths.
