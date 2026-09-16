<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Validation scope

The current source and managed installer were qualified on Fedora 44 KDE
x86_64 with Goodix USB `27c6:5125` / APP12509.

Verified product behavior includes:

- reproducible network-isolated source build;
- libfprint ABI compatibility with Fedora's fprintd;
- reader discovery through fprintd and KDE;
- bounded eight-sample enrollment;
- serialized template persistence across fprintd restart;
- same-finger match and different-finger no-match;
- Plasma login, real locked-session unlock, and `sudo` authentication;
- password fallback;
- multiple local users and multiple enrolled fingers;
- account deletion blocked while fingerprints remain;
- update, single-slot rollback, uninstall, and reinstall;
- preservation of protected material and templates across uninstall;
- restoration of Fedora PAM and fprintd state.

Offline validation commands for the distributed release surface are:

```bash
production/check-source.sh
python3 deployment/managed-install/test_offline.py
```

Per-reader runtime material handling is device-dynamic and has host-only
regression coverage, including distinct synthetic valid bundles and fail-closed
manifest cases. That validates runtime acceptance logic; it is **not** a claim
that this release provides or qualifies acquisition of a fresh five-file bundle.
Device-material acquisition is outside the supported release scope.

The qualified library hash is:

```text
acf6d19af4e22a364390c61485259fa7fb3bcd10126a03ded53d4acd7e90593e
```

This digest applies to the normal production build with the pinned Fedora 44
inputs. It is not a support claim for another compiler, SDK, package set,
distribution, sensor, firmware revision, or desktop environment.

No statistically meaningful false-acceptance or false-rejection rate is
claimed. Functional match/no-match observations are not a substitute for a
population study.
