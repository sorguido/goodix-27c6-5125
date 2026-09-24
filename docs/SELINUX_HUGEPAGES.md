<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# SELinux and the optional huge-page probe

## Cause and lifetime

The library chain is Goodix libfprint → OpenCV core → oneTBB → `libtbbmalloc`.
Fedora 44 packages checked offline were `opencv-core-4.13.0-1.fc44`,
`tbb-2022.3.0-3.fc44` and `fprintd-1.94.5-5.fc44` on x86_64. OpenCV's ELF
dependencies include `libtbb.so.12`; oneTBB dynamically selects `libtbbmalloc.so.2`.

In oneTBB 2022.3.0, library initialization acquires global controls through
`cache_aligned_allocate`. The first allocator initialization calls
`HugePagesStatus::parseSystemMemInfo`, which opens `/proc/sys/vm/nr_hugepages`.
This happens **before** reading `TBB_MALLOC_USE_HUGE_PAGES`. Setting that variable
to zero does not prevent the probe. Neither does limiting OpenCV's thread count.
There is no supported probe-disable switch in this version's allocator path.

A native offline test loading only Fedora OpenCV reproduced one attempted open
during `dlopen`, with no further attempts across 100 allocations. Both a simulated
`EACCES` and EOF allowed those allocations to complete. Each fresh process
repeated the probe. No reader, libfprint, fprintd or protected material was used.
This corroborates the source; it does not count actions in a running user's daemon.

The trigger is **library initialization**, normally during each fprintd process
startup, before fingerprint actions. Ordinary repeated actions in the same
initialized process do not reinitialize this allocator. Unload/reload or exceptional
allocator teardown/reinitialization is a separate boundary, not the normal
fprintd action path. Stock fprintd exits after 30 seconds unused; the next D-Bus
client starts a fresh process. Repeated activations explain why different
consumers can show the same alert. Historical alert counts alone do not establish
one notification per contact or map every event to a specific process restart.

```text
ROOT_CAUSE_COMPONENT=oneTBB_libtbbmalloc_HugePagesStatus
TRIGGER_BOUNDARY=library-init
GOODIX_PROTOCOL_CAUSE=false
```

Primary sources:

- [oneTBB huge-page probe and configuration ordering](https://github.com/uxlfoundation/oneTBB/blob/v2022.3.0/src/tbbmalloc/tbbmalloc_internal.h)
- [Allocator one-time initialization](https://github.com/uxlfoundation/oneTBB/blob/v2022.3.0/src/tbbmalloc/frontend.cpp)
- [Library initialization](https://github.com/uxlfoundation/oneTBB/blob/v2022.3.0/src/tbb/main.cpp), [resource acquisition](https://github.com/uxlfoundation/oneTBB/blob/v2022.3.0/src/tbb/governor.cpp), [global controls](https://github.com/uxlfoundation/oneTBB/blob/v2022.3.0/src/tbb/global_control.cpp), [allocator selection](https://github.com/uxlfoundation/oneTBB/blob/v2022.3.0/src/tbb/allocator.cpp)
- [Fedora 44 oneTBB package source and build options](https://src.fedoraproject.org/rpms/tbb/blob/f44/f/tbb.spec)
- [fprintd manager idle lifecycle](https://gitlab.freedesktop.org/libfprint/fprintd/-/blob/v1.94.5/src/manager.c) and [30-second timeout](https://gitlab.freedesktop.org/libfprint/fprintd/-/blob/v1.94.5/src/fprintd.h)

## Common correction

The installer adds one setting to its existing
`/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf`:

```ini
BindReadOnlyPaths=/dev/null:/proc/sys/vm/nr_hugepages
```

This standard systemd mechanism substitutes an empty stream at exactly that path
in the service's mount namespace. The library still calls `fopen`; it receives EOF
from `/dev/null` instead of attempting to read the real sysctl. The host sysctl
value, its label and visibility to all other services remain unchanged. OpenCV,
SIGFM and the Fedora allocator are retained without private forks or ABI changes.
Huge pages are optional and disabled by default in this allocator.

`BindReadOnlyPaths` has been supported since systemd 233. Fedora 44 uses systemd
259; its stock fprintd unit already creates a filesystem namespace.
`ProtectKernelTunables=true` makes `/proc/sys` read-only rather than inaccessible.
Systemd orders parent mounts before child paths. Fedora's existing policy allows
systemd to mount over sysctl paths and domains to read `/dev/null`; this change
adds no such permissions. The installed Fedora unit plus this drop-in passed
`systemd-analyze verify` offline. The actual mount, labeling and service startup
under Enforcing remain part of live qualification.

See [systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#BindPaths=),
[systemd 259 namespace handling](https://github.com/systemd/systemd/blob/v259/src/core/namespace.c),
[Fedora 44 domain policy](https://github.com/fedora-selinux/selinux-policy/blob/f44/policy/modules/kernel/domain.te)
and [Fedora 44 init policy](https://github.com/fedora-selinux/selinux-policy/blob/f44/policy/modules/system/init.te).

Rejected alternatives:

- Allocator environment/API huge-page settings are consulted after the probe.
  Rebuilding OpenCV/oneTBB or replacing the allocator adds unnecessary maintenance.
- A `dontaudit fprintd_t sysctl_vm_t:file read` rule grants no access, but cannot
  distinguish this pathname from other files with the same type. It could hide
  unrelated reads with the same tuple. No such rule is installed.
- Permissive SELinux, `setenforce 0`, broad `audit2allow` output, sysctl access
  grants, globally disabling alerts and per-consumer workarounds are excluded.

## Consumer coverage

The following is a source/configuration audit, **not a new live PASS**. Here
`TRIGGERS_FPRINTD_START=true` means that the path can activate an inactive daemon;
it does not force a restart of an already-running daemon. PAM paths require
fingerprint to be enabled by the existing Fedora configuration and an actual
authentication request (cached sudo/PolicyKit authorization may skip it).
`CAN_TRIGGER_NR_HUGEPAGES_PROBE` describes the library call before mitigation;
after mitigation the same call receives EOF in the service namespace.

| Path | TRIGGERS_FPRINTD_START | CAN_TRIGGER_NR_HUGEPAGES_PROBE | SAME_ROOT_CAUSE |
| --- | --- | --- | --- |
| KDE fingerprint settings / enrollment | true | true | true |
| fprintd-enroll | true | true | true |
| fprintd-verify | true | true | true |
| Plasma Login fingerprint, through existing selector | true | true | true |
| KScreenLocker fingerprint | true | true | true |
| sudo fingerprint | true | true | true |
| sudo -i fingerprint (authentication include; login-shell behavior separately unqualified) | true | true | true |
| PolicyKit fingerprint | true | true | true |
| D-Bus activation / ordinary fprintd service startup | true | true | true |
| manual systemctl start fprintd, when inactive | true | true | true |
| first fingerprint use after reboot | true | true | true |
| another action in the same initialized fprintd process | false | false | true |

CLI/KDE clients and stock pam_fprintd converge on `net.reactivated.Fprint`.
Fedora's D-Bus service file specifies `SystemdService=fprintd.service`; its
stock unit executes `/usr/libexec/fprintd`. The setting therefore covers all
listed paths without modifying them. A direct `/usr/libexec/fprintd` invocation
outside systemd does not receive the setting and is not the supported launch path.

## Ownership, removal and security

Installation automatically writes the new drop-in while fprintd is stopped and
temporarily masked. Exact legacy and current drop-in bytes are accepted during
upgrade; arbitrary edits still fail the ownership check. Reinstallation is
idempotent. Rollback restores the previous drop-in bytes, including the legacy
version. Both standalone removal commands delete this exact project file and
stop the daemon, destroying its namespace. Emergency removal also handles the
drop-in left behind by an interrupted install without receipts or runtime files.
No new artifact, package dependency or post-install source-tree dependency exists.

| Security question | Answer |
| --- | --- |
| Grants new access to fprintd? | No; no policy or capability changes |
| Can hide unrelated fprintd AVCs? | No; no audit suppression |
| Limited to known probe? | Yes; the exact path in fprintd.service only |
| Uninstall restores stock behavior? | Yes; removes drop-in and service namespace; policy was always stock |
| Force removal handles partial policy installation? | No policy is installed; partial configuration cleanup is tested |
| Increases authentication failure scope? | No; a mount setup failure can stop fingerprint service startup, not replace the password/authentication stack |

The changed file is project-owned, not RPM-owned. It neither changes Fedora's
unit in place nor overrides ExecStart. There are no version/hash runtime pins.
An incompatible future systemd/kernel change could prevent fprintd startup
(update-survivability class C: fingerprint only); removal/reinstallation is the
recovery path. Password and desktop consumers continue to use their existing
Fedora fallback behavior. Material and template preservation are unchanged.

## Live qualification

**HUMAN_REQUIRED: the fix has not yet been exercised in the Fedora VM.**
Use the existing clean Fedora 44 KDE VM, with reader connected, SELinux Enforcing,
working password/sudo access and the already-prepared materials. Close fingerprint
dialogs before installation. Install this source revision through `./install.sh`,
or apply the supplied two-file source patch to the existing public clone and run
that same entrypoint. Save the supplied patch as
`$HOME/goodix-selinux-release-fix.patch` **inside the VM**, then use its existing
public checkout:

```bash
cd "$HOME/goodix-27c6-5125" &&
git apply --check "$HOME/goodix-selinux-release-fix.patch" &&
git apply "$HOME/goodix-selinux-release-fix.patch" &&
./install.sh
```

If patch checking fails, stop and report it; do not force-apply or erase local
changes. After it has been applied, an installer retry uses only `./install.sh`.
This is the two-file runtime change from the reviewed source commit, not a
separate installer. The installer requests sudo and does not start a capture.
An older public revision will not contain the fix; use the source revision or
patch supplied for this qualification.

After successful installation record the UTC start time in your home directory
so it survives logout/reboot:

```bash
getenforce
date -u '+%m/%d/%y %H:%M:%S' > "$HOME/goodix-selinux-test-start"
```

Stop unless `getenforce` says `Enforcing`. Use ordinary workflows, sequentially:

1. Open KDE fingerprint settings. Keep an existing enrollment; otherwise enroll
   one finger using the usual sample prompts. Do not delete templates for this test.
2. Verify with `fprintd-verify` or ordinary KDE verification; then perform one
   further ordinary verification promptly. This exercises reuse if the daemon
   remains running; opening another client does not prove PID continuity.
3. Run `sudo -k -- /usr/bin/true` and authenticate by fingerprint.
4. Log out, test Plasma Login fingerprint through the empty-password selection.
5. Lock the session and unlock using the fingerprint.
6. Revoke cached PolicyKit authorization with `pkcheck --revoke-temp`, then run
   `pkexec /usr/bin/true` and authenticate in the ordinary KDE dialog. A command
   that succeeds without a dialog does not qualify fingerprint authentication.
7. Reboot and exercise the first fingerprint interaction offered by the normal
   login/settings workflow. Check `getenforce` again after returning to the desktop.

For each verification/authentication series: stop at the first MATCH; allow at
most three explicit contacts, then use password and stop on failure. Do not add
a fourth attempt or loop tests. Enrollment follows its normal multi-sample flow.
Password fallback and the desktop must continue to work.

For every row report `FINGERPRINT_FUNCTIONAL=<expected behavior>` and
`SELINUX_NR_HUGEPAGES_NOTIFICATION=ABSENT`. A cached old desktop alert is not
a new AVC; use the bounded query below to distinguish it. Record any skipped
consumer as untested, not PASS. A fresh manual service start follows the same
configuration, but needs no separate sensor test in this minimum matrix.

After the matrix, run this single read-only query. It prints only matching AVC
lines, not the other audit records or biometric data. No matching lines are
expected; query errors must be reported, not interpreted as success.

```bash
if read -r START_DATE START_TIME < "$HOME/goodix-selinux-test-start"; then
read -r END_DATE END_TIME < <(date -u '+%m/%d/%y %H:%M:%S')
sudo env LC_ALL=C TZ=UTC ausearch --input-logs -m AVC,USER_AVC -c fprintd \
    -ts "$START_DATE" "$START_TIME" -te "$END_DATE" "$END_TIME" --raw |
    awk '/^type=AVC / && (/name="nr_hugepages"/ || /path="\/proc\/sys\/vm\/nr_hugepages"/) && /scontext=[^ ]*:fprintd_t:/ && /tcontext=[^ ]*:sysctl_vm_t:/ && /tclass=file/ { print }'
printf 'AUDIT_QUERY_EXIT=%s FILTER_EXIT=%s\n' "${PIPESTATUS[0]}" "${PIPESTATUS[1]}"
else
    printf 'STOP: test start time is missing\n' >&2
fi
```

`AUDIT_QUERY_EXIT=0` means matching fprintd events were searched; there must be
no printed matching huge-page AVC. Exit 1 **without error output**, and filter
exit 0, means ausearch found no fprintd AVCs in the interval (`--raw` does not
print a "no matches" message). Any error output or other exit status needs review.
Notifications or unrelated new AVCs are also failures to report even if this
narrow filter prints nothing. No `audit2allow`, SELinux toggle or manual policy
installation is part of this procedure.

`PASS_IF`: expected fingerprint behavior for all exercised paths, Enforcing,
no new huge-page alerts/matching AVCs, password/desktop intact.
`FAIL_IF`: an authentication regression or a new matching AVC/alert.
`STOP_IF`: installation error, service namespace/startup failure, unavailable
password fallback or three failed contacts. Do not retry the same failure.

On failure use `goodix-uninstall`; if it refuses incomplete project state, use
`goodix-force-remove` following [recovery instructions](UNINSTALL.md). Both
preserve materials/templates and expose current Fedora; follow the final reboot
instruction and verify password login. Keep a passing installation in place.
Report the consumer, expected/actual behavior and exact non-secret error/query
output. Never attach materials, templates or fingerprint images.
