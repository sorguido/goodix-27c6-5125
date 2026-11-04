<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Goodix Manager 3.0.1 — draft, not released

Goodix Manager 3.0.0 prevents upgrading Fedora 44 to Fedora 45 because of an
outdated package dependency. Version 3.0.1 removes that restriction.

Once 3.0.1 is officially released, install it on Fedora 44 before upgrading to
Fedora 45. You do not need to uninstall the fingerprint driver first. Your saved
fingerprints and pairing information are kept.

The new RPM no longer limits installation to one Fedora release. It is designed
to remain installable on later Fedora versions as long as the required system
components remain compatible. This is an expectation, not a promise that future
Fedora versions have been tested.

Earlier fingerprint testing passed on Fedora 44. Testing this 3.0.1 candidate
on Fedora 44 and Fedora 45 is still in progress; Fedora 45 fingerprint login
has not yet been qualified for this version.
