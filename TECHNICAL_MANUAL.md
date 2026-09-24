<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Technical manual

## Hardware and operating-system boundary

This implementation targets Goodix USB `27c6:5125`, firmware
`GF_ST411SEC_APP_12509`, and Fedora 44 KDE x86_64 with local accounts.
Successful authentication and complete public installation have been reported on
the tested configuration. Other firmware, readers, desktop environments and
network accounts are not qualified. [Validation](docs/VALIDATION.md) distinguishes
observations from unverified behavior. The root installer builds and installs from
this tree and has been exercised on both a freshly installed and updated Fedora VM
and the physical Fedora 44 KDE qualification system with SELinux Enforcing.

## Architecture

```text
Goodix reader
    ↕
Goodix-enabled libfprint + image matching
    ↕
Fedora fprintd
    ↕
Fedora PAM / KDE / sudo / PolicyKit
```

The device implementation belongs in libfprint. Fedora continues to provide
`/usr/libexec/fprintd`, its service and D-Bus interface, the Plasma daemon and
greeter, and normal authentication consumers. No private fprintd or Plasma
binary is needed. The root `install.sh` builds the library and selector as the
ordinary user from current source, then requests sudo for deployment. Build
provenance uses source-content hashes and installed Fedora package versions,
without depending on Git history or a particular clone location.

The project-owned library directory is `/usr/local/lib64/goodix-27c6-5125/`. It contains
libfprint and the four required OpenCV libraries. Fedora supplies libgusb and
OpenSSL. One service drop-in,
`/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf`, sets
`LD_LIBRARY_PATH` for fprintd. It does not replace the service's `ExecStart`.

The bundled OpenCV libraries come from the installed Fedora development packages;
the build records their actual versions, notices and SONAMEs. The library is based on libfprint 1.94.100 with the Goodix device implementation,
SIGFM matching and image preprocessing. Source provenance and applicable
licenses are described in [Licensing and provenance](docs/LICENSING_AND_PROVENANCE.md).

## Plasma Login and other consumers

The tested Fedora Plasma Login password stack does not itself offer the required
fingerprint choice. A small project-owned PAM selector adds that choice through
`/etc/pam.d/plasmalogin` and
`/usr/local/lib64/goodix-plasma-login/pam_goodix_login_gate.so`.

A nonempty password proceeds to the current Fedora password stack. Empty-field
submission explicitly selects stock `pam_fprintd` with `max-tries=3 timeout=30`;
the timeout applies per attempt. The integration includes the current Fedora
vendor PAM for password, account and session processing. It does not copy or
freeze a vendor configuration. Removing the project entry exposes Fedora's
current configuration.

The vendor path is a compatibility dependency. A future incompatible PAM layout
can affect login; successful authentication on the tested system does not prove
compatibility with all future packages. The removal commands never require the
old vendor path to exist before removing the project override.

KScreenLocker, ordinary sudo and PolicyKit use their Fedora authentication
paths where the current Fedora policy enables fingerprint authentication. The
installer does not change authselect or add global PAM rules. No project PAM
bridge, daemon or policy is installed for them. Console
and sudo conversation order follows the current Fedora policy: fingerprint can
precede password, without a user-facing method selector.

## Enrollment, verification and templates

The driver performs asynchronous, bounded transfers and owns one action at a
time. A clean NO_MATCH may be followed by another explicit action after cleanup;
MATCH and processing-error paths prevent hidden capture resubmission. Consumers
control their explicit attempt series. The Plasma Login series is bounded to
three attempts and stops on the first match.

Enrollment gathers eight accepted samples, checks diversity and waits for
terminal finger release before reporting completion. The image pipeline decodes
an 80×64 raster from the packed image record, preprocesses it and uses SIGFM to
construct and match templates. This is not a claim of a measured false-match or
false-rejection rate.

Fedora fprintd stores templates under `/var/lib/fprint/`. Runtime removal and
reinstallation preserve them. Use normal KDE/fprintd interfaces to manage or
delete enrolled fingers; do not put templates into source archives or reports.

## Protected device material

The user stages five pre-existing files in `$HOME/goodix-5125-materials/`, outside
the clone. The installer validates that exact set and imports it into
`/var/lib/goodix-5125-poc/`. These files bind the host runtime
to the intended reader and OEM compatibility input. The directory is root-owned
mode `0700`; regular files are root-owned mode `0600`. The loader rejects unsafe
metadata, malformed records and mismatched digests before using the material.
Validation uses the supplied reader's own manifest and file digests; no fixed
reference-reader bundle is required. Offline checks validate format and file
cross-bindings, while typed device-response bindings are checked at runtime.
An already-valid installed set is retained. See the complete
[material contract](docs/DEVICE_MATERIALS.md).

The secure transport uses TLS 1.2 with a pre-existing reader PSK. The host acts
as server; the reader acts as client. The OEM DLL is parsed for validated data,
not executed. The project does not generate, replace or provision reader keys,
and does not distribute protected material or acquisition tooling.

SELinux uses an exact local file-context mapping for this directory and its
contents to `fprintd_var_lib_t`. No custom permission-granting SELinux module is
required by this architecture. Removal returns the explicit material paths to
current policy defaults when removing an owned mapping, while preserving bytes
and Unix ownership/mode. Templates and their labels are not changed.

## Lifecycle with the reader present

An integrated reader remains connected and visible throughout installation,
update, removal and recovery. Presence in sysfs is not an error or permission to
start capture. Recovery-tool installation does not access the device or operate
fprintd. Runtime replacement/removal must stop fprintd and verify an inactive
service with no main process before changing its loaded library files.

The lifecycle implementation temporarily prevents service activation during
runtime mutation, preserves an existing service mask, removes only a mask it
created and never starts fprintd as an installation check. It uses ordinary
host service controls, not direct USB commands or a private hardware daemon.
If service activation cannot be inhibited or fprintd cannot be quiesced, the
operation fails with a precise error; the reader stays connected. Reader-present
reinstallation has been reported successful. The complete source-built public
installer has now passed physical-system qualification on the tested Fedora 44 KDE
system; synthetic checks do not extend that evidence to unrelated hosts or future
PAM and SELinux policy changes.

## Removal and recovery

`goodix-uninstall` checks the project's software receipts, ownership and hashes.
`goodix-force-remove` uses a fixed inventory of project paths and tolerates
missing receipts and partial installations. It removes authentication entry
points first and does not execute saved installer code. Neither depends on the
repository, build output, Fedora version, vendor-file hash or vendor-file
existence to remove the project.

Installed binaries and standalone removal scripts do not import from the clone;
it can be moved or removed after installation. Both preserve material and templates. They remove project software, service
integration and owned label effects, then remove recovery tooling last when
cleanup succeeds. Failure output identifies unfinished cleanup. A normal restart
closes old authentication sessions that may retain loaded code. These commands
expose the current Fedora state; they cannot repair unrelated Fedora failures
or bypass console/sudo authentication. See [Uninstall and recovery](docs/UNINSTALL.md).

## Safety and support limits

Flashing, IAP, ClearApp, OTP writes, PSK replacement/provisioning, factory-data
writes and persistent identity changes are outside the supported path. Unknown
or unsafe protocol states fail closed. The design preserves the factory/Windows
path; exhaustive Windows compatibility and factory readback are not established
by a successful fingerprint match.

Keep password access available. Password-encrypted KWallet can request its own
password after fingerprint login. Full recovery with unavailable biometrics,
all future package changes and independent hardware remain qualification limits.
Use [Installation](docs/INSTALLATION.md) for the single install/update procedure
and the current qualification status.
