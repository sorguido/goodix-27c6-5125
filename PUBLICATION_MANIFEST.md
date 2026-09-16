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
Rockytkg/libfprint/libfprint/sigfm/     (four production source files only)
tools/device-materials/
```

The following local entries are not part of that surface:

- `.git/` and editor/agent workspace mounts;
- `development/`, which contains private historical/recovered project material;
- downloaded OpenCV RPM payloads, which are host-local build inputs and are
  retrieved from Fedora using the documented command;
- generated device material, OEM caches, private captures, fingerprint images,
  templates, and other protected input/output files.

The source build, offline tests, installer, documentation, and public helper
tools do not depend on anything under `development/`. The private Git history
is not an input to the public source transfer. Copy only the paths in the
allowlist above.

Before transferring an updated tree, run:

```bash
production/check-source.sh
python3 deployment/managed-install/test_offline.py
python3 tools/device-materials/Finalize-Goodix5125TransportMaterial.py --self-test
```

The Windows exporter also provides a native secret-free self-test:

```powershell
.\tools\device-materials\Export-Goodix5125TransportMaterial.ps1 -SelfTest
```

Run that Windows-only check on native Windows before a release that changes the
exporter or its wrapper.

Then confirm that no unexpected binary, capture, key, firmware, protected
material, fingerprint image, or template has been added to the allowlisted
paths.
