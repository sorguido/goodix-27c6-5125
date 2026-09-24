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
| Complete public installation | Fresh Fedora 44 KDE VM installation passed; installation on the physical Fedora 44 KDE qualification system passed with SELinux Enforcing, followed by working Plasma Login, ordinary sudo, KScreenLocker, PolicyKit and password fallback |
| Emergency removal | Successful text-console removal was reported with the reader connected; exact final output and every resulting file/service/label check were not supplied |

## Complete installation path

The public root installer builds from current source, validates and imports the
user's five files, installs the runtime and login integration, and installs
standalone removal commands. It is independent of clone location and private
build outputs. The reader remains connected throughout the lifecycle.

The complete public procedure has now been exercised successfully on a freshly
installed and updated Fedora 44 KDE VM and on the physical Fedora 44 KDE
qualification system. On the physical system, installation completed with SELinux
Enforcing; fingerprint authentication then passed for Plasma Login, ordinary sudo,
KScreenLocker and PolicyKit, while password fallback remained available. These
results qualify the combined build/import/install transaction for the tested
configuration; they do not extend qualification to other readers, firmware,
distributions or future Fedora changes.

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
- Console/sudo authentication can offer fingerprint before password. The expected
  untouched-reader timeout is about 30 seconds, depending on Fedora policy; no
  immediate method selector is provided. A fully broken password stack cannot
  be repaired by the removal command.
- At Plasma Login on the tested system, after explicitly selecting fingerprint
  authentication by submitting the empty password field, allow roughly one
  second before placing the finger. This is not an artificial delay: with the
  stock Fedora fprintd path, reader preparation starts only when PAM enters
  `pam_fprintd`, so the Goodix device must still be opened and brought through
  its secure-session/TLS and FDT preparation before it can accept the first
  capture. Eliminating that startup interval would require preparing the device
  before the authentication action and handing the prepared session into the
  later verification step; stock fprintd does not expose that early-login
  handoff. A project-specific implementation of it would therefore require a
  modified or tightly coupled fprintd/greeter integration. The current release
  deliberately accepts this small UX cost so Fedora can continue to own the
  stock fprintd daemon and greeter, substantially reducing the authentication
  surface the project must replace, maintain, roll back and keep compatible with
  future Fedora updates.
- The Plasma Login selector depends on the current Fedora vendor PAM path.
  Compatibility with all future package changes is not established.
- Stock consumers use fingerprints only where current Fedora policy enables them;
  the installer does not modify authselect or global PAM policy. The qualified
  fresh Fedora baseline had authselect `with-fingerprint` enabled; a host with an
  altered authentication policy may not offer fingerprint to sudo, PolicyKit or
  KScreenLocker.
- Password-encrypted KWallet may require a separate password after fingerprint login.
- Ordinary sudo evidence does not separately qualify every login-shell variant.
- The integrated SELinux `dontaudit` rule suppresses the known non-fatal oneTBB
  `nr_hugepages` read probe without granting access; it does not classify
  unrelated future denials.
- Full factory-state readback, exhaustive Windows compatibility, power-loss recovery
  and every future update combination have not been demonstrated.

Report exact behavior and errors without protected data. See
[Security](SECURITY.md), [Installation](INSTALLATION.md) and [Removal](UNINSTALL.md).
