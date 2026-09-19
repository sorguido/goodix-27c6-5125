# fprintd Fedora 44 exact production reference

Target package:

- Fedora 44 x86_64
- installed NEVRA: `fprintd-1.94.5-5.fc44.x86_64`
- source RPM reported by RPM: `fprintd-1.94.5-5.fc44.src.rpm`

The source RPM was downloaded from the enabled Fedora 44 repositories and
extracted without installing it. Its spec uses:

`Source0: https://gitlab.freedesktop.org/libfprint/fprintd/-/archive/v%{version}/fprintd-v%{version}.tar.gz`

and:

`%autosetup -S git -n %{name}-v%{version}`

No `Patch`, `%patch` or `%autopatch` directive is present. Therefore
`source/` contains the unpatched upstream fprintd v1.94.5 runtime sources corresponding
to the installed Fedora package source. This canonical upstream tree is immutable. The production build copies it to
staging and applies `production/login/fprintd.patch` with zero fuzz. The patch
is the sole maintained downstream fprintd/PAM implementation. Its initial
bytes are identical to the live-validated prototype at
`9671e02e19504e20e0097f598fa960f2c13e7a1e`. Upstream GPL-2.0-or-later notices
and copyright remain intact; the new integration has the same license.
`SOURCE_SHA256SUMS` covers every retained upstream source file.

Source material SHA-256:

- `fprintd-1.94.5-5.fc44.src.rpm`
  `886d192ad57e52d3f953e86d78ba72b389bc09d433d6ff999421542ea381f292`
- `fprintd-v1.94.5.tar.gz`
  `a026ef34c31b25975275cc29a5e4eba2b54524769672095a5228098a08acd82c`
- `fprintd.spec`
  `b87b2786e5b4b0e69735ac0c3a8bab6ad1f5393660f738d5d052d62bb3ebadbd`

The live RPM itself was not changed, replaced or executed against the Goodix
sensor during this audit.

The canonical import omits only the eight NIST example JPEG/PNG fingerprint
images from `tests/prints/`. Their README/provenance is retained. No runtime
source is changed; runtime builds and the project's synthetic tests do not use
those images. The original complete reference remains private historical
evidence. No local or upstream biometric image/template is added to this
canonical candidate surface.

The import retains upstream whitespace and the README heading underline.
Scoped Git attributes avoid treating these pre-existing bytes as new defects;
all retained source bytes are independently pinned by SOURCE_SHA256SUMS.
Project patches and their expanded changes are reviewed separately.
