<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Validation scope and known limitations

## Tested configuration

The evidence concerns one Goodix USB `27c6:5125` reader running
`GF_ST411SEC_APP_12509`, on Fedora 44 KDE x86_64 with local accounts. Fedora's
stock fprintd and authentication consumers are used with the project's libfprint
runtime and minimal Plasma Login selector. Results below are operator-reported
observations reviewed against the implementation and available telemetry.

| Function | Evidence and boundary |
| --- | --- |
| Enrollment and standard verification | Enrollment completed and a subsequent verification matched the enrolled finger |
| KScreenLocker | Password unlock and fingerprint unlock reached the desktop |
| Ordinary sudo | Correct password and fingerprint authentication succeeded |
| PolicyKit | Correct password and fingerprint authentication succeeded through the KDE agent |
| Plasma Login | Nonempty password reached the desktop without forced fingerprint wait; explicit fingerprint selection reached the desktop after one contact without a password |
| Normal removal | Software paths removed, Fedora fprintd exposed without private library environment, password login and KDE desktop remained usable |
| Material/template preservation | File inode, size, owner, mode and modification time unchanged across reported normal removal; this is metadata evidence, not a cryptographic proof of all bytes |
| Reinstallation | Installation completed and one subsequent Plasma fingerprint login matched with clean drain/close telemetry |
| Emergency removal | Operator reported successful text-console removal while the reader remained connected; exact final output/state confirmation remains incomplete |

## Reader-present lifecycle

The lifecycle contract permits a connected, visible integrated reader for all
management operations. Recovery-tool installation previously rejected a present
reader, before runtime installation began. The current lifecycle implementation
replaces device-absence checks with software service controls. The corrected
installation and remaining password-fallback
behavior still need on-system qualification.

Successful reinstall evidence above predates that correction and does not prove
the corrected reader-present installation path. A successful emergency command
report alone does not prove every final file, service, label or password check.
The public installer and update package are not yet ready for release.

## Offline evidence

Synthetic tests exercise software ownership and hash checks, partial and missing
installations, vendor-file absence, active/inactive fprintd, command invocation
without source/build directories, preserved material/template sentinels and
repeat removal. Lifecycle tests substitute host service and privileged operations;
they do not open real USB or authenticate through host PAM.

Driver tests cover explicit attempts, MATCH termination, processing-error fences
and cleanup using synthetic inputs. These checks support implementation review,
not claims of recognition accuracy, hardware behavior or complete operating-system
recovery. A normal unit-test pass is not a substitute for observing password and
desktop access after installation/removal.

## Known limitations

- No broad independent-reader, cross-firmware or cross-distribution qualification.
- No measured universal false-acceptance or false-rejection rate.
- No supported acquisition or construction of the five protected input files.
- No finished public installer, updater or package migration contract.
- Console/sudo authentication can offer fingerprint before password; an immediate
  method selector or fixed fallback delay is not promised. Unavailable-biometric
  password fallback still needs confirmation for the tested console configuration.
- The Plasma Login selector depends on the current Fedora vendor PAM path.
  Compatibility with all future package changes is not established.
- Password-encrypted KWallet may require a separate password after fingerprint login.
- Ordinary sudo evidence does not separately qualify every login-shell variant.
- A recurring SELinux read denial involving `nr_hugepages` was non-fatal during
  tested successful authentication; this does not classify every future denial.
- Full factory-state readback, exhaustive Windows compatibility, power-loss recovery
  and every future update combination have not been demonstrated.

Report exact behavior and errors without protected data. See
[Security](SECURITY.md), [Installation](INSTALLATION.md) and [Removal](UNINSTALL.md).
