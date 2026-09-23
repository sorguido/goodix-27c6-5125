<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Public source and documentation manifest

This is an explicit eligibility list for a future audited source release.
**It is not a release announcement or permission to publish a working tree.**
Final public packaging and complete source-export build qualification are not
finished. Export only committed, reviewed files; never copy private Git history,
ignored files or arbitrary directory contents.

## Public documentation: exact file allowlist

Only these project Markdown pages are eligible. Adding a page beneath `docs/`,
`production/` or `deployment/` does not make it public automatically.

```text
README.md
TECHNICAL_MANUAL.md
PUBLICATION_MANIFEST.md
ACKNOWLEDGEMENTS.md
docs/INSTALLATION.md
docs/UNINSTALL.md
docs/DEVICE_MATERIALS.md
docs/SECURITY.md
docs/VALIDATION.md
docs/LICENSING_AND_PROVENANCE.md
docs/REFERENCES.md
production/README.md
GoodixArtifacts/opencv-4.13-rpms/README.md
reference/libfprint-fedora44-1.94.100/PROVENANCE.md
reference/libfprint-fedora44-1.94.100/source/README.md
reference/libfprint-fedora44-1.94.100/source/HACKING.md
reference/libfprint-fedora44-1.94.100/source/code-of-conduct.md
```

The first twelve pages are stable product documentation. The remaining pages
are public build/provenance references or retained upstream documentation;
upstream copyright and license statements remain unchanged. No other Markdown,
reStructuredText or project narrative document is included through a source
rule below. API documentation within the retained upstream source is technical
reference, not this project's installation guide.

## Eligible code and license inputs

The following narrowly selected source inputs may accompany those documents:

- `.gitignore`, `LICENSE`, and the license texts under `LICENSES/`.
- Exactly the source paths listed in `production/source-files.tsv`, checked
  against `production/source-files.sha256`. This selects the device code and
  the four SIGFM files without exporting a full third-party workspace.
- The committed Fedora libfprint source tree under
  `reference/libfprint-fedora44-1.94.100/source/`, excluding documentation
  formats not allowed above; retain upstream license/copyright notices,
  required build metadata and API documentation. No generated output or
  newly acquired binary/biometric test data is eligible.
- The committed synthetic source fixtures under `libfprint-driver/tests/`
  with extensions `.c`, `.h`, `.cpp`, `.hpp`, `.py` or `.sh`; no images,
  captures, templates or other fixture payloads are selected.
- These exact build files:

```text
production/check-source.sh
production/build-inner.sh
production/source-files.tsv
production/source-files.sha256
production/host-test-only-symbols.txt
production/build-support/SHA256SUMS
production/build-support/gusb.h
production/build-support/gusb.pc.in
production/build-support/opencv4.pc.in
production/build-support/opencv-rpms.sha256
production/minimal-runtime/build.sh
production/minimal-runtime/check-stock-attempts.sh
```

- These exact lifecycle and synthetic-test files:

```text
deployment/minimal-runtime/deploy.py
deployment/minimal-runtime/install.sh
deployment/minimal-runtime/uninstall.sh
deployment/minimal-runtime/test_offline.py
deployment/minimal-runtime/test_material_labels.py
deployment/plasma-login-opt-in/manage.py
deployment/plasma-login-opt-in/pam_goodix_login_gate.c
deployment/plasma-login-opt-in/plasmalogin.pam
deployment/plasma-login-opt-in/build-vm.sh
deployment/plasma-login-opt-in/test_dispatch.c
deployment/plasma-login-opt-in/test_dispatch.py
deployment/plasma-login-opt-in/test_gate.c
deployment/plasma-login-opt-in/test_manage.py
deployment/recovery/manage.py
deployment/recovery/remove.py
deployment/recovery/install.sh
deployment/recovery/uninstall.sh
deployment/recovery/test_manage.py
deployment/recovery/test_remove.py
```

Code selection preserves reviewable implementations; it does not turn the
component scripts into a finished public installer or remove their current
environment-specific constraints. New dependencies or helpers require explicit
addition and audit before an export can claim completeness.

## Excluded by default

All paths not selected above are excluded. In particular:

- entire-directory exports of `docs/`, `production/`, `deployment/` or
  `libfprint-driver/` are forbidden;
- internal milestone guides, governance, operational prompts, the internal
  technical diary, analyses and all `development/` material remain private;
- all nested project README files other than `production/README.md` are excluded
  unless explicitly listed above;
- private authentication daemons, greeters, sudo/PolicyKit bridges and the
  former managed deployment are excluded;
- Git history, editor state, generated artifacts, downloaded RPMs, caches,
  secrets, factory material, OEM binaries, firmware, biometric images/templates
  and private captures are excluded;
- acquisition, extraction, key recovery and device-material generation tools
  are excluded.

## Before a source transfer

Audit the selected **files**, their notices, imports, script dependencies,
links and synthetic fixtures. Verify source digests with
`production/check-source.sh --driver-only`. Every local documentation link must
resolve within the selected surface. Check actual build/test/package closure
from a clean committed export using independently obtained prerequisites;
no such complete public-release qualification is claimed by this manifest.

Do not publish until privacy, licensing, source completeness and required
release checks are complete. The [installation page](docs/INSTALLATION.md)
remains truthful about the availability of final packaging.
