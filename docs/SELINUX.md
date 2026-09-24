<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Optional SELinux notification suppression on Fedora

On the tested Fedora 44 configuration, starting `fprintd` can produce a recurring
SELinux desktop notification for a denied read of `nr_hugepages`.

The denial originates from the OpenCV/oneTBB runtime used by the fingerprint
matching path. The read is optional: SELinux denies it and fingerprint operation
continues. The project does **not** need to grant this access.

## Optional suppression

If the notification is unwanted, the repository provides an opt-in helper:

```bash
sudo ./tools/goodix-selinux-hugepages enable
```

This installs exactly one reviewed `dontaudit` rule:

```text
(dontaudit fprintd_t sysctl_vm_t (file (read)))
```

A `dontaudit` rule does **not** grant the read. SELinux continues to deny matching
accesses; it only stops recording that denial as an AVC notification.

The rule is type-based rather than pathname-based. Therefore it can also suppress
other denied `read` attempts made by `fprintd_t` against files carrying the same
`sysctl_vm_t` SELinux type. Other source domains, target types, object classes and
permissions remain unaffected by this rule.

The helper never runs `audit2allow` and never builds policy from the host's current
logs.

Check status with:

```bash
sudo ./tools/goodix-selinux-hugepages status
```

Restore Fedora's normal audit behavior with:

```bash
sudo ./tools/goodix-selinux-hugepages disable
```

If the source clone is no longer available, the same project module can be removed
with:

```bash
sudo semodule -X 400 -r goodix_5125_hugepage
```

The fingerprint driver itself does not depend on this optional module. Leaving the
module disabled only means the known SELinux notification may appear again.
