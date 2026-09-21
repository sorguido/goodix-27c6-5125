# Plasma Login Manager — immutable Fedora source

Target: `plasma-login-manager-6.7.5-1.fc44.x86_64`.
Source package downloaded read-only from Fedora Koji:
[exact SRPM](https://kojipkgs.fedoraproject.org/packages/plasma-login-manager/6.7.5/1.fc44/src/plasma-login-manager-6.7.5-1.fc44.src.rpm).
SRPM SHA-256: `8f06c70db1113f015b4ad7273ade5aced172c0e3576266153cd3bf2ca73f6be3`.
The SRPM is an acquisition input, not installed or shipped as runtime payload.

`source/` contains all 256 upstream tarball files, unchanged, including notices,
license texts and build definitions. Tar SHA-256:
`6ed7c3bbac1c79bc1a21c330923804aa6c3f720fafd6accb1a6a1fada684e84f`.
Tar SHA-512 matches the Fedora dist-git `sources` entry:
`b875d2537f140482af2bdbbc2fedc9b6ecadb9060f037d5e3109610fde72299bde6cfd5b07dda5295c0132545b3a9dd2d99429d8ed2f550049aa43d29dc1cf95`.
`fedora/` retains the exact SRPM spec and all four patches, unchanged.
`SOURCE_SHA256SUMS` authenticates every retained source/spec/patch file.

Build order follows `%autosetup -p1`: 170, 200, environment-file, tmpfiles.
170 modifies the VT switch wait, not VT allocation or TIOCSCTTY. 200 modifies
vendor wallet PAM entries; this project does not install those files.
The local delta lives separately in `production/plasma-vt/session-vt.patch`
and `SessionVt.*` / `vt-policy.h`; the immutable source is never edited.
Only the daemon target is built. Fedora's installed helper, session programs,
PAM files, greeter, logind and getty remain the corresponding vendor components
(except the already existing, separately managed Goodix integrations).

## Per-file licensing

Daemon/common C++ and headers retain upstream GPL-2.0-or-later notices.
`src/auth/Auth*` (except GPL AuthMessages.h) retain LGPL-2.1-or-later.
`mainconfig.kcfgc` is CC0-1.0. Unmarked generated-input configuration and D-Bus
interface descriptions retain their upstream source/package context; no new
per-file grant is asserted. Unbuilt frontend and helper files retain all their
original licenses. The complete license corpus is preserved; no third-party
file is relicensed. The local additions/patch/build/tests are GPL-2.0-or-later.
The daemon is conveyed using applicable later grants as GPL-3.0-or-later,
consistent with the candidate and its Qt/KDE dynamic dependencies.
Full corresponding source and notices remain in this private checkout; public
export remains a separate audit, not authorized by this import.
