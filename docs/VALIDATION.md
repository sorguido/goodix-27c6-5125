<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Validation scope and known limitations

## Tested configuration

The hardware evidence concerns one Goodix USB `27c6:5125` reader running
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
| Material/template preservation | File inode, size, owner, mode and modification time unchanged across reported normal removal; metadata evidence does not establish a cryptographic comparison of all bytes |
| Reinstallation | Installation and subsequent Plasma fingerprint login succeeded; corrected reinstallation with the reader continuously present was also reported successful |
| Emergency removal | Successful text-console removal was reported with the reader connected; exact final output and every resulting file/service/label check were not supplied |

## Complete installation path

The public root installer builds from current source, validates and imports the
user's five files, installs the runtime and login integration, and installs
standalone removal commands. It is independent of clone location and private
build outputs. The reader remains connected throughout the lifecycle.

**The complete public procedure still needs installation on a physical Fedora
system and review of its minimum lifecycle results before a qualified release.**
Previous component and reader-present success reports do not by themselves
qualify the newly combined build/import/install transaction.

## Offline evidence

Synthetic checks exercise two distinct valid reader bundles, invalid and missing
materials, unsafe file types, file binding errors, source/payload validation,
service quiescence and activation inhibition, partial installation rollback,
project ownership/drift handling and standalone normal/emergency removal.
Tests use temporary filesystem fixtures and substitute privileged host operations;
they do not read real protected bundles, open USB or authenticate through host PAM.

Driver checks cover explicit attempts, MATCH termination, processing-error fences
and cleanup using synthetic inputs. A source-only copy can be checked without
Git history. [Build and offline checks](../production/README.md) identifies the
relevant suites. These checks support implementation review; they do not establish
recognition accuracy, hardware behavior or complete operating-system recovery.

## Known limitations

- No broad independent-reader, cross-firmware or cross-distribution qualification.
- No measured universal false-acceptance or false-rejection rate.
- No automated acquisition/extraction tooling is shipped or qualified as part
  of the release; the detailed [device-material acquisition reference](DEVICE_MATERIALS.md)
  documents how the five final files are derived.
- Physical qualification of the combined public installer remains pending.
- Console/sudo authentication can offer fingerprint before password. The expected
  untouched-reader timeout is about 30 seconds, depending on Fedora policy; no
  immediate method selector is provided. A fully broken password stack cannot
  be repaired by the removal command.
- The Plasma Login selector depends on the current Fedora vendor PAM path.
  Compatibility with all future package changes is not established.
- Stock consumers use fingerprints only where current Fedora policy enables them;
  the installer does not modify authselect or global PAM policy.
- Password-encrypted KWallet may require a separate password after fingerprint login.
- Ordinary sudo evidence does not separately qualify every login-shell variant.
- A recurring SELinux read denial involving `nr_hugepages` was non-fatal during
  tested authentication; this does not classify every future denial.
- Full factory-state readback, exhaustive Windows compatibility, power-loss recovery
  and every future update combination have not been demonstrated.

Report exact behavior and errors without protected data. See
[Security](SECURITY.md), [Installation](INSTALLATION.md) and [Removal](UNINSTALL.md).
