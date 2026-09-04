# libfprint Fedora 44 production reference

Target host:

- Fedora 44 x86_64
- installed libfprint package: `libfprint-1.94.100-1.fc44.x86_64`
- installed fprintd package: `fprintd-1.94.5-5.fc44.x86_64`
- runtime SONAME: `libfprint-2.so.2`
- fprintd required symbol version: `LIBFPRINT_2.0.0`

Exact installed-package source RPM reported by RPM:

`libfprint-1.94.100-1.fc44.src.rpm`

The Fedora 44 source RPM contains:

- `libfprint-v1.94.100.tar.gz`
- `libfprint.spec`

No active Fedora `.patch` or `.diff` files are present.

The spec uses:

`Source0: https://gitlab.freedesktop.org/libfprint/libfprint/-/archive/v%{version}/libfprint-v%{version}.tar.gz`

and:

`%autosetup -S git -n libfprint-v%{version}`

No active `PatchN`, `%patch`, or `%autopatch` directives were observed.

Therefore `source/` is the extracted upstream libfprint v1.94.100 source tree
corresponding to the Fedora 44 `libfprint-1.94.100-1.fc44` package source.

## Local integration delta

Starting with D279/03, the preserved upstream tree has a bounded local Meson
delta in `source/meson.build` and `source/libfprint/meson.build`. It registers
the repository-owned LGPL driver `goodix_27c6_5125` and references its
canonical sources in `<repository-root>/libfprint-driver/`; no upstream driver
source was overwritten. The original tarball digest below remains the
provenance anchor, not a claim that the working `source/` directory is still
byte-identical to the archive after this documented overlay.

The D279/03 delta is recorded in
`analysis/D279/D279_03_offline_fedora44_production_usb_registration_NBIS.md`.
Starting with D279/04 the same source map also compiles the repository-owned
LGPL binder, protected-material loader and inert runtime-input providers; no
additional upstream file is replaced.

Purpose:

This tree is the production integration reference for the Goodix 27c6:5125
project on the target Fedora 44 system.

`Rockytkg/libfprint` remains a separate historical/reference tree based on
libfprint 1.94.5 and must not be treated as the target Fedora libfprint version.

Clean-room boundary:

This reference tree may be used for standard libfprint API, Meson, registry,
driver-class, lifecycle and build integration mechanics. It does not authorize
copying third-party Goodix protocol implementations into the project's clean
Goodix implementation.

Source material SHA-256:

- `libfprint-1.94.100-1.fc44.src.rpm`
  `5daf6e5b492a2b493e36d0513bea0be324235a1452d69a791b28c6157df7963e`

- `libfprint-v1.94.100.tar.gz`
  `edc90e02f330a7595ceaf37f2c6ec32ed43541347fe936d3273b0bb2524fd19c`
