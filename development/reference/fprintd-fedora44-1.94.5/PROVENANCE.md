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
`source/` is the exact unpatched upstream fprintd v1.94.5 tree corresponding
to the installed Fedora package source. It is retained read-only as the
D282/01 control-plane reference; project code does not link against or modify
this tree.

Source material SHA-256:

- `fprintd-1.94.5-5.fc44.src.rpm`
  `886d192ad57e52d3f953e86d78ba72b389bc09d433d6ff999421542ea381f292`
- `fprintd-v1.94.5.tar.gz`
  `a026ef34c31b25975275cc29a5e4eba2b54524769672095a5228098a08acd82c`
- `fprintd.spec`
  `b87b2786e5b4b0e69735ac0c3a8bab6ad1f5393660f738d5d052d62bb3ebadbd`

The live RPM itself was not changed, replaced or executed against the Goodix
sensor during this audit.

The unmodified upstream tree includes its own public `tests/prints/` fixtures.
They are source-package test data, not target captures, local-user templates or
D282 evidence; no target/local biometric material is present.
