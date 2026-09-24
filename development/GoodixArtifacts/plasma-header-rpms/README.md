# Offline Plasma daemon build inputs

These RPMs are downloaded and extracted, never installed. Payloads are ignored
by Git; `production/plasma-vt/headers.sha256` pins them. Fetch from Fedora Koji:

- `https://kojipkgs.fedoraproject.org/packages/qt6-qtbase/6.11.2/2.fc44/x86_64/qt6-qtbase-devel-6.11.2-2.fc44.x86_64.rpm`
- `https://kojipkgs.fedoraproject.org/packages/qt6-qtdeclarative/6.11.2/2.fc44/x86_64/qt6-qtdeclarative-devel-6.11.2-2.fc44.x86_64.rpm`
- `https://kojipkgs.fedoraproject.org/packages/kf6-kconfig/6.30.0/1.fc44/x86_64/kf6-kconfig-devel-6.30.0-1.fc44.x86_64.rpm`
- `https://kojipkgs.fedoraproject.org/packages/kf6-kcoreaddons/6.30.0/1.fc44/x86_64/kf6-kcoreaddons-devel-6.30.0-1.fc44.x86_64.rpm`

Qualified build environment: existing Freedesktop SDK 25.08 commit
`b90ed309cc1d505dea48b6a2121c5dcfac22868120eee643b0596d31f96b9bb8`,
host gcc 16.2.1-2.fc44, binutils 2.46.1-1.fc44, kf6-kconfig 6.30.0-1.fc44.
Qt moc/qdbus generators come from the pinned extracted RPM. Host kconfig compiler
is from the version above. Compilation is network-disabled inside the SDK;
native linking uses existing Fedora libraries to preserve their glibc ABI.
No new host build/runtime packages are installed.
