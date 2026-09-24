<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Source build and offline checks

Users install and update through the root `install.sh` using
[the single installation block](../docs/INSTALLATION.md). No separate build
command or manual payload selection is needed.

## Build architecture

`build-public.py` resolves the source root from its own location and builds as
an ordinary user on Fedora 44 x86_64. It uses the checked-in libfprint base,
Goodix driver and SIGFM sources, plus the installed Fedora development packages.
It does not require Git history, a branch name, a particular clone directory or
pre-existing build output.

The payload contains Goodix-enabled libfprint, four required OpenCV libraries,
the Plasma Login selector and PAM entry, an offline material checker, license
notices and source/build provenance. Fedora supplies fprintd, libgusb, OpenSSL,
PAM, Plasma and the ordinary authentication consumers.

The builder verifies the library ABI, dependency resolution, absence of test-only
entry points, exact payload inventory and content hashes. OpenCV notices come
from installed Fedora RPM license files. Build provenance records the current
source-content digest and package versions, rather than requiring Git objects.

The [source ledger](source-files.tsv) and [matching digests](source-files.sha256)
record the driver sources and per-file origins. [Licensing and provenance](../docs/LICENSING_AND_PROVENANCE.md)
describes the combined library's terms.

## Offline checks

These checks use synthetic inputs and temporary fixtures. They substitute host
service, privilege and device operations, and do not install software or open USB:

```bash
python3 -B production/test_build_public.py
python3 -B deployment/test_materials.py
python3 -B deployment/test_install.py
python3 -B deployment/recovery/test_remove.py
python3 -B deployment/test_hugepage_probe.py
```

The suites cover the public builder and payload contract, distinct valid reader
bundles, invalid material rejection, installer failure/rollback paths and removal
without the clone. Running them does not prove hardware support or real Fedora
PAM/SELinux behavior. See [Validation](../docs/VALIDATION.md) for observations and
remaining limits.

The optional huge-page regression test requires Fedora's OpenCV 4.13 and a C
compiler. It loads only OpenCV/oneTBB, intercepts the single huge-page file open
with either an artificial denial or `/dev/null`, and checks repeated allocations.
It never loads libfprint or starts fprintd. This validates the allocator's EOF
behavior, not an actual systemd mount or SELinux transition.
