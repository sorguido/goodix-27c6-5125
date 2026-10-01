<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Validation scope and known limitations

## Tested configuration

The hardware evidence concerns one Goodix USB `27c6:5125` reader running
`GF_ST411SEC_APP_12509`, on Fedora 44 KDE x86_64 with local accounts. Fedora's
stock fprintd and authentication consumers are used with the project's libfprint
runtime and minimal Plasma Login selector. Results below are operator-reported
observations reviewed against the implementation and available telemetry.

A separate host-lifecycle qualification used a clean Fedora 44 KDE x86_64 VM
with SELinux Enforcing and no reader or USB passthrough. That qualification
tests installation and recovery behavior, not live reader behavior.

| Function | Evidence and boundary |
| --- | --- |
| Enrollment and standard verification | Enrollment completed and a subsequent verification matched the enrolled finger |
| Enrollment zero-mask recovery | A logged zero at the third contact preserved the primary, skipped auxiliary acquisition and continued to 8 accepted stages in 8 contacts with one zero-specific re-arm; final audit recorded no persistent writes and complete host drain/close |
| Duplicate detection | A manual duplicate-detection check with recovery enabled was reported successful, alongside ordinary enrollment and verification |
| KScreenLocker | Password unlock and fingerprint unlock reached the desktop |
| Ordinary sudo | Correct password and fingerprint authentication succeeded |
| PolicyKit | Correct password and fingerprint authentication succeeded through the KDE agent |
| Plasma Login | Nonempty password reached the desktop without forced fingerprint wait; explicit fingerprint selection reached the desktop after one contact without a password |
| Normal removal | Software paths removed, Fedora fprintd exposed without private library environment, password login and KDE desktop remained usable |
| Material/template preservation | File inode, size, owner, mode and modification time unchanged across reported normal removal; metadata evidence does not establish a cryptographic comparison of all bytes |
| Reinstallation | Installation and subsequent Plasma fingerprint login succeeded; corrected reinstallation with the reader continuously present was also reported successful |
| Complete public installation | Fresh Fedora 44 KDE VM installation passed; installation on the physical Fedora 44 KDE qualification system passed with SELinux Enforcing, followed by working Plasma Login, ordinary sudo, KScreenLocker, PolicyKit and password fallback |
| Read-only coordinator host lifecycle | On the clean reader-absent VM, state-v2-only fresh install, update, normal removal, reinstall, controlled transaction rollback and emergency recovery from a missing runtime receipt passed while stock fprintd, vendor PAM, SELinux Enforcing, password access and KDE usability were preserved |
| Emergency removal | Successful text-console removal was reported with the reader connected; separately, the clean VM force-removal test passed after normal removal rejected a deliberately incomplete project receipt, with project paths removed and the empty state-v2 root preserved across reboot |

## Complete installation path

The public root installer builds from current source, validates and imports the
user's five files, installs the runtime and login integration, and installs
standalone removal commands. It is independent of clone location and private
build outputs. The reader remains connected throughout the lifecycle.

The unified bootstrap and automatic reuse of installed material are covered by
offline synthetic tests. Live validation of that new flow, including deletion of
the clone and Home staging folder, remains pending human testing.

The complete public procedure has now been exercised successfully on a freshly
installed and updated Fedora 44 KDE VM and on the physical Fedora 44 KDE
qualification system. On the physical system, installation completed with SELinux
Enforcing; fingerprint authentication then passed for Plasma Login, ordinary sudo,
KScreenLocker and PolicyKit, while password fallback remained available. These
results qualify the combined build/import/install transaction for the tested
configuration; they do not extend qualification to other readers, firmware,
distributions or future Fedora changes.

The current read-only coordinator host lifecycle was also exercised on a clean
SELinux-Enforcing Fedora 44 KDE VM with the reader absent. A fresh installation
without legacy material created only the empty root-only state-v2 location.
Update, removal, reinstall, injected transaction rollback and emergency recovery
preserved that location and left Fedora's fprintd service and vendor PAM as the
service boundary. Password login, ordinary sudo and the KDE desktop remained
usable after the required reboots. No USB access, pairing write or biometric
operation occurred in this host-only qualification.

## Offline evidence

Synthetic checks exercise two distinct valid reader bundles, invalid and missing
materials, unsafe file types, file binding errors, source/payload validation,
service quiescence and activation inhibition, partial installation rollback,
project ownership/drift handling and standalone normal/emergency removal.
They also cover bootstrap clone/pull/conflict behavior, automatic installation
modes, installed-material precedence without Home staging, explicit bundle
mismatch rejection, and reinstall after both removal paths.
Tests use temporary filesystem fixtures and substitute privileged host operations;
they do not read real protected bundles, open USB or authenticate through host PAM.

Driver checks cover explicit attempts, MATCH termination, processing-error fences
and cleanup using synthetic inputs. A source-only copy can be checked without
Git history. [Build and offline checks](../production/README.md) identifies the
relevant suites. These checks support implementation review; they do not establish
recognition accuracy, hardware behavior or complete operating-system recovery.

## Known limitations

- No broad independent-reader, cross-firmware or cross-distribution qualification.
- Zero-mask recovery has one observed successful continuation without a late IRQ0200.
  Its bounded host rule does not distinguish an old release from a current one
  if both have identical bytes in a later compatible release slot; see the
  [protocol boundary](../TECHNICAL_MANUAL.md#74-enrollment-zero-mask-recovery).
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
- The seven-command read-only target and CONFIG90 preflight is qualified on the
  real reader. The state-v2 pairing mutation, readback/TLS proof, zero-seed FDT
  continuation and ordinary reopen remain offline-qualified only; they require
  their separate live no-finger authorization and evidence.

Report exact behavior and errors without protected data. See
[Security](SECURITY.md), [Installation](INSTALLATION.md) and [Removal](UNINSTALL.md).
