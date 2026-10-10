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

Interoperability evidence additionally uses the same reader passed through to a
Windows 11 virtual machine.

| Function | Evidence and boundary |
| --- | --- |
| Enrollment and standard verification | Enrollment completed and a subsequent verification matched the enrolled finger |
| Fixed-21 live recognition qualification | The fixed-21 candidate was exercised on the physical target through real enrollment and continued day-to-day use. Across 100 valid matcher probes, 97 produced at least one positive SIGFM comparison score and 3 produced only zero scores, for an observed all-zero incidence of 3.00%. In this qualification sample, missed recognition attributable to the all-zero condition was operationally negligible and the resulting day-to-day recognition experience was close to the Windows Hello experience observed on the same hardware. This is a bounded target qualification, not a universal false-reject-rate claim. |
| Enrollment zero-mask recovery | A logged zero at the third contact preserved the primary, skipped auxiliary acquisition and continued to 8 accepted stages in 8 contacts with one zero-specific re-arm; final audit recorded no persistent writes and complete host drain/close |
| Duplicate detection | A manual duplicate-detection check with recovery enabled was reported successful, alongside ordinary enrollment and verification |
| KScreenLocker | Password unlock and fingerprint unlock reached the desktop |
| Ordinary sudo | Correct password and fingerprint authentication succeeded |
| PolicyKit | Correct password and fingerprint authentication succeeded through the KDE agent |
| Plasma Login | Nonempty password reached the desktop without forced fingerprint wait; explicit fingerprint selection reached the desktop after one contact without a password |
| Normal removal | Software paths removed, Fedora fprintd exposed without private library environment, password login and KDE desktop remained usable |
| Preserved-state/template metadata | File inode, size, owner, mode and modification time unchanged across reported normal removal; metadata evidence does not establish a cryptographic comparison of all bytes |
| Reinstallation | Installation and subsequent Plasma fingerprint login succeeded; corrected reinstallation with the reader continuously present was also reported successful |
| Complete public installation | Fresh Fedora 44 KDE VM installation passed; installation on the physical Fedora 44 KDE qualification system passed with SELinux Enforcing, followed by working Plasma Login, ordinary sudo, KScreenLocker, PolicyKit and password fallback |
| Reader-absent host lifecycle | On the clean reader-absent VM, a fresh install with no prior host state, update, normal removal, reinstall, controlled transaction rollback and emergency recovery from a missing runtime receipt passed while stock fprintd, vendor PAM, SELinux Enforcing, password access and KDE usability were preserved |
| Emergency removal | Successful text-console removal was reported with the reader connected; separately, the clean VM force-removal test passed after normal removal rejected a deliberately incomplete project receipt, with project paths removed and the empty host pairing state root preserved across reboot |
| Self-contained pairing activation | On the qualification reader one authorized action journaled the host pairing state `PREPARED` reservation, performed exactly one logical `E0`, confirmed the current `BB010002` byte-for-byte and the new `BB020003` validator, proved TLS and promoted the record to `ACTIVE`; no second write was requested and the epoch reported zero unexpected persistent writes |
| Zero-`E0` ACTIVE reopen | A later ordinary no-finger identify reused the `ACTIVE` record through the read-only preflight and the pairing-activation reuse disposition, with zero `E0`, zero persistent writes, a matching E4 contract, and complete drain and close |
| Zero-seed FDT bootstrap | With no imported FDT cache, an ordinary no-finger action completed the three-sample zero-seed bootstrap, including a first manual sample carrying a nonzero touch mask, and reached FDT learning; operator-reported against the declared counters, and the sanitized audit line is not retained in the repository |
| Interrupted-transaction recovery (offline) | The crash-window matrix and the host-shaped superseded-`PREPARED` recovery test show that reopening after an interrupted post-`E0`/pre-ACTIVE transaction reuses the durable reservation, proves TLS and promotes to `ACTIVE` with zero persistent writes and zero `E0`; no live reproduction exists for this boundary |
| Windows/Linux ping-pong | A bounded `L1 -> W1 -> L1 -> W2 -> L1` sequence on the qualification reader, with the same Windows 11 VM and USB passthrough, produced: a Linux baseline and two same-OS reopens that reused `ACTIVE` `L1` with zero persistent writes and zero `E0`; two Windows transitions that each replaced the pairing; and two Linux returns that each classified the change read-only as an external replacement and restored the same stored `L1` with exactly one qualified write, byte-for-byte preserved Windows `BB010002`, matching readback and validator, TLS proof and `ACTIVE` promotion. No new Linux key, no loop, no second writer, and no firmware/IAP/ClearApp/OTP path |
| Windows autonomous recovery boundary | Within that sequence, Windows recovery is evidenced by clean OEM enumeration without a warning indicator plus a pairing replacement that Linux then read back as a structurally valid `BB010002` through the read-only preflight. The sequence itself included no Windows fingerprint enrollment or authentication |
| Windows Hello functional round-trip (supplemental) | After the biometric qualification, a real functional round-trip passed on the same reader and Windows 11 VM: Windows Hello fingerprint enrollment and authentication, Linux fingerprint authentication, then authentication again with the previously enrolled Windows Hello finger and once more on Linux. No reset, firmware operation, driver reinstall, manual PSK manipulation or deliberate reprovisioning occurred. This is supplemental interoperability evidence, not a reopened pairing gate |
| Self-contained biometric stack | On the new self-contained bootstrap, enrollment through the canonical KDE Users/Fingerprint path completed for two fingers (`enroll_stages=8`, `enroll_contacts=8`, `enroll_retry_scans=0`, zero pairing writes); stock `fprintd-verify` returned `verify-match` on the first contact and `verify-no-match` for a non-enrolled finger; with two fingers enrolled, `fprintd-verify -f any` ran a real `FPI_DEVICE_ACTION_IDENTIFY` that matched on attempt 1. Plasma Login, KScreenLocker, ordinary sudo and PolicyKit each authenticated with the fingerprint and no password. Every action reported `secure_e4_contract=MATCH`, `persistent=0`, `pairing_writes=0`, `pairing_active_reused=1`, `outstanding=0`, `drained=1`, `context_closed=1` |
| Bounded physical series | Each failed authentication series stopped at three `NO_MATCH` attempts with no fourth attempt, in KScreenLocker, sudo, PolicyKit and Plasma Login, and password fallback then succeeded (`pam_unix`/`unix_chkpwd`) with the desktop, sudo and PolicyKit request completing. A second login `1 -> 2 -> 3` series was explicitly operator-triggered, not an automatic retry. This matches the implementation, which reuses a login context only while `login_attempts < 3` and only after a completed NO_MATCH release tail |
| Cancel and release paths | A verify cancelled before contact captured no image (`first_image=0`, `release_tail=0`) and still drained and closed the context with zero writes; matched paths reported `release_tail=1` and `single_terminal=1` |
| Baseline/FDT during live biometrics | Enrollment, verify, identify, NO_MATCH and bounded-failure actions consistently reported `fdt_samples=3`, `fdt_learned_once=1`, `fdt_delta_within=2`, `fdt_delta_outside=0`, `fdt36_submits=3`, `fdt_baseline_b0=1`, `fdt_baseline_decode=1` with `secure_failure=0`. This confirms the bootstrap stayed clean under real biometric use; it is not a new seedless-FDT qualification |
| Temperature path boundary | The driver defines no Goodix-specific thermal override: it sets no `temp_hot_seconds` and adds no custom thermal branch, so the stock libfprint `FpTemperature` model and its automatic `fpi_device_update_temp()` lifecycle apply unchanged and were exercised through the normal device lifecycle. No synthetic forced-HOT transition was performed, and none is claimed |
| Cold login | A real cold login succeeded with the fingerprint and no password, with the known readiness delay: after submitting at the greeter, allow roughly one second before contact, because reader preparation starts with the authentication action |

## Complete installation path

The public root installer builds from current source, prepares or preserves the
root-only host pairing state directory, installs the runtime and login
integration, and installs standalone removal commands. It is independent of clone
location and private build outputs. These host lifecycle operations do not access
the reader, which may be connected or absent.

The unified bootstrap and automatic reuse of preserved host state are covered by
offline synthetic tests. The clean-VM user lifecycle that follows the published
instructions end to end is qualified in
[Release-candidate lifecycle qualification](#release-candidate-lifecycle-qualification).

The complete public procedure has now been exercised successfully on a freshly
installed and updated Fedora 44 KDE VM and on the physical Fedora 44 KDE
qualification system. On the physical system, installation completed with SELinux
Enforcing; fingerprint authentication then passed for Plasma Login, ordinary sudo,
KScreenLocker and PolicyKit, while password fallback remained available. These
results qualify the combined build/import/install transaction for the tested
configuration; they do not extend qualification to other readers, firmware,
distributions or future Fedora changes.

The reader-absent host lifecycle was also exercised on a clean
SELinux-Enforcing Fedora 44 KDE VM. A fresh installation
created only the empty root-only host pairing state location.
Update, removal, reinstall, injected transaction rollback and emergency recovery
preserved that location and left Fedora's fprintd service and vendor PAM as the
service boundary. Password login, ordinary sudo and the KDE desktop remained
usable after the required reboots. No USB access, pairing write or biometric
operation occurred in this host-only qualification.

## Release-candidate lifecycle qualification

The complete published user lifecycle was qualified end to end on a clean Fedora
44 KDE x86_64 VM with SELinux Enforcing, a stock Fedora authentication stack, no
prior project installation and no legacy Windows material bundle, with the Goodix
`27c6:5125` reader present through USB passthrough for the whole sequence. Each
step followed the published instructions for this release candidate literally,
with no development shortcut, runtime workaround or private knowledge.

| Lifecycle step | Qualified result and boundary |
| --- | --- |
| Fresh install | Canonical installation from source completed without Windows Material Builder, USBPcap, DPAPI recovery or any legacy five-file material bundle; the reader self-initialized through the automatic first-use path |
| Real biometric use | Ordinary representative use after the fresh install confirmed a working biometric system on the stock Fedora/KDE stack: enrollment, password login and fingerprint login all succeeded |
| Canonical update | The published update path completed with the reader present, preserving the operational state, password access and desktop |
| Normal removal | `goodix-uninstall` from a normal desktop session removed the project from the authentication path with the reader present, preserved the host pairing state and fingerprint templates and performed no reader write; reboot, password login and desktop remained available |
| Canonical reinstall | Reinstallation after normal removal reused the preserved host pairing state and the existing fingerprint templates, and fingerprint login worked again without the legacy bundle |
| Emergency removal | `goodix-force-remove` run from a TTY with the reader present completed, preserved host pairing state and fingerprint templates, performed no reader write, and left password login and the desktop recoverable after reboot |

Across the entire lifecycle password authentication and the KDE desktop stayed
available and recoverable, and no step introduced a firmware, IAP, ClearApp, OTP
or factory-data write or any other unexpected persistent reader mutation.

Scope and limitations: this qualifies the published lifecycle for the tested
configuration only - one reader running `GF_ST411SEC_APP_12509` on Fedora 44 KDE
x86_64. It is a linear user-lifecycle qualification, not an exhaustive matrix of
artificial reader-present/reader-absent, rollback or migration combinations, and
it does not repeat the full biometric qualification reported above. The candidate
was qualified on the pre-merge release-candidate branch; once `main` is aligned,
the public bootstrap continues to install the default branch normally.

## Offline evidence

Synthetic checks exercise host state preparation and preservation, unsafe file
types, source/payload validation,
service quiescence and activation inhibition, partial installation rollback,
project ownership/drift handling and standalone normal/emergency removal.
They also cover bootstrap clone/pull/conflict behavior, automatic installation
modes, and reinstall after both removal paths.
Tests use temporary filesystem fixtures and substitute privileged host operations;
they do not read real secrets, open USB or authenticate through host PAM.

Driver checks cover explicit attempts, MATCH termination, processing-error fences
and cleanup using synthetic inputs. A source-only copy can be checked without
Git history. [Build and offline checks](../production/README.md) identifies the
relevant suites. These checks support implementation review; they do not establish
recognition accuracy, hardware behavior or complete operating-system recovery.

The fixed-21 enrollment policy has deterministic normal and sanitizer
coverage for completion exactly at the 21st accepted sample, the absence of a
22nd accepted sample, poor-sample retry without progress, unbounded physical
contacts, duplicate/near-duplicate acceptance and non-decisional diversity
diagnostics.

The policy is also qualified on the physical target for real enrollment and
continued day-to-day verification. The observed qualification sample contains
100 valid matcher probes: 3 were all-zero across the enrolled SIGFM samples and
97 produced at least one positive score, giving an all-zero incidence of
3.00%. In practical use this made missed recognition attributable to the
all-zero condition substantially negligible and produced a recognition
experience close to the Windows Hello experience observed on the same hardware.
The measurement is intentionally reported as a bounded project qualification;
it does not establish a universal false-reject rate, population-level accuracy
claim or equivalence with the proprietary Windows template construction.

## Known limitations

- No broad independent-reader, cross-firmware or cross-distribution qualification.
- Zero-mask recovery has one observed successful continuation without a late IRQ0200.
  Its bounded host rule does not distinguish an old release from a current one
  if both have identical bytes in a later compatible release slot; see the
  [protocol boundary](../TECHNICAL_MANUAL.md#74-enrollment-zero-mask-recovery).
- No measured universal false-acceptance or false-rejection rate.
- Console/sudo authentication can offer fingerprint before password. The expected
  untouched-reader timeout is about 30 seconds, depending on Fedora policy; no
  immediate method selector is provided. A consumer with a shorter application
  timeout can therefore abandon its authorization request before PAM reaches the
  password fallback. That timing interaction belongs to the stock Fedora
  PAM/fprintd/consumer path rather than the Goodix protocol or biometric driver.
  When a temporary password-only session is required, such as remote access with
  no physical access to the reader, the supported operational mitigation is to
  runtime-mask `fprintd.service` with
  `sudo systemctl mask --runtime --now fprintd.service` and later restore it,
  without rebooting, with
  `sudo systemctl unmask --runtime fprintd.service`. This does not delete
  templates, alter host pairing state, or rewrite PAM/authselect configuration.
  The runtime mask is also cleared automatically by a reboot. A fully broken
  password stack cannot be repaired by this mechanism or by the removal command.
- At Plasma Login on the tested system, after explicitly selecting fingerprint
  authentication by submitting the empty password field - including at a cold
  login - allow roughly one second before placing the finger. This is not an
  artificial delay: with the
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
  real reader, as are the one-shot host pairing transaction - a single
  logical `E0`, the exact `BB010002` and `BB020003` readbacks, the TLS proof and
  ACTIVE promotion - the ordinary zero-`E0` ACTIVE reopen and the zero-seed FDT
  no-finger bootstrap that follows them. The read-only recovery from an
  interrupted post-`E0`/pre-ACTIVE transaction remains offline-qualified only:
  the successful live pairing consumed that window, and reproducing it on the
  reader would require either a further `E0` or replacing the qualified ACTIVE
  record. That residual risk is accepted; the qualified evidence for the
  boundary is the offline crash-window matrix plus the host-shaped
  superseded-`PREPARED` recovery test, which proves `RECOVER_PREPARED_TLS` with
  zero writes and zero `E0`.

Report exact behavior and errors without protected data. See
[Security](SECURITY.md), [Installation](INSTALLATION.md) and [Removal](UNINSTALL.md).
