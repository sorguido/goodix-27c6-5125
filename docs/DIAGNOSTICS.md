<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Diagnostic Center: scope, matrix and evidence contract

Offline results, mockup comparison and remaining qualification boundaries are in
[DIAGNOSTICS_VALIDATION.md](DIAGNOSTICS_VALIDATION.md).

This decision artifact defines the offline diagnostic work on branch `diagnostic`.
The approved local statement supplies the desiderata; the approved HTML supplies
the binding presentation. Neither simulated HTML results nor offline tests prove
that authentication works on a real Fedora host. Implementation status must be
reported separately from this design.

## Existing capabilities and smallest extension

**OBSERVED in source:** `packaging/rpm/helper.py` verifies the Manager RPM with
`rpm -V --noscripts --nodeps`, validates trusted package metadata, and exposes
ordinary software receipts, source identity, runtime integrity, lifecycle result
codes and USB enumeration. Its `status` operation requires PolicyKit/root;
`sensor_present()` reads kernel enumeration, without opening the reader.
`deployment/recovery/remove.py:normal_preflight()` verifies project software,
PAM selector, drop-in and recovery receipts. It does not validate Fedora packages
or prove that a biometric action succeeds.

`deployment/install.py:host_preflight()` checks Fedora/architecture, Enforcing,
vendor Plasma PAM ownership, effective fprintd unit, executable, drop-ins and
library environment. Unknown overrides are rejected before installation mutations.
However, `helper.py:execute()` collapses backend exceptions into `operation_failed`
unless rollback is proven. Its `status` path does not run `host_preflight()`.
Thus a healthy software receipt cannot exclude the two independent defects in
issue #55: an incompatible service override and missing Fedora libfprint files.

`manager/model.py:Status.diagnostic()` already exports an explicit field allowlist.
`manager/main.py:copy_diagnostics()` adds the last result and release-check state;
it has no report profiles, event history, consent or file preview. Release lookup
is an existing separate network operation; diagnostics must not depend on it.

**Decision:** add a small unprivileged collector and pure parsers/presentation,
using fixed commands and fixed software paths. Reuse the latest validated helper
status as a dated snapshot, without obtaining new privileges for diagnostics.
Do not invoke installer/preflight wholesale: those entry points have wider
privileges and material-related paths. Do not extend PolicyKit, read protected
receipts as root, run a privileged helper automatically, or change lifecycle
acceptance rules. Static evidence remains useful before driver activation.
Code additions and their tested capabilities will be recorded in this artifact;
the following matrix is the implementation target, not a claim of availability.

## Check matrix

P0 covers direct known blockers; P1 covers useful context and intermittent events.
Cost budgets are maximums, not estimated performance. All static checks run as the
desktop user. Permission denial is `unavailable`; there is no elevation fallback.
Privacy M means host metadata; C means configuration metadata; E means event
metadata. All are potentially identifying. No check below opens `/dev/bus/usb`,
claims a reader, reads protected pairing/biometric directories or starts fprintd.
The separately explicit runtime reader action is the sole dynamic exception;
its implementation is tested only against fake D-Bus in this offline campaign.

| ID / priority | Question / source and existing capability | Cost / privilege / USB | Privacy | Sustainable interpretation and limit |
| --- | --- | --- | --- | --- |
| host / P0 | Fedora ID/version, architecture, kernel; os-release and platform. Existing installer defines Fedora >=44 x86_64. | <=5 s; user; no | M | Observed compatibility metadata only; no guarantee on future Fedora releases. Missing/malformed data unavailable. |
| driver / P0 | Latest validated `Status` snapshot: runtime/payload/package versions, integrity/result code. Existing helper/model. | Cached; no new privilege; no | M | Report absent/installed/blocked and snapshot time. Missing/stale snapshot unavailable; never infer runtime integrity from version text. Absence is an observed installation state, not proof of malfunction. |
| manager_rpm / P0 | Fixed `rpm -q` and `rpm -V --noscripts --nodeps goodix-manager`; new unprivileged projection of existing RPM strategy. | <=30 s per command; user; no | M | Exact successful verification proves only checked RPM files. Nonzero verification with recognized records identifies drift; malformed output/command failure is unavailable. No signature/provenance guarantee from a version alone. |
| components / P0 | Fixed `rpm -q` for libfprint, fprintd, fprintd-pam; `rpm -V --noscripts --nodeps` for libfprint/fprintd. New probes. | <=30 s per command; user; no | M | Distinguish absent package, missing file, changed file and failed query. Missing libfprint files are an independent observed problem; do not infer that they caused a previous exit 127. |
| service / P0 | `systemctl show fprintd.service` with selected properties: LoadState, ActiveState, SubState, FragmentPath, ExecStart, DropInPaths, Environment. Existing installer baseline, new read-only parser. | <=5 s; user; no | C | Compare effective fragment/executable/drop-in/library environment to existing baseline. A stopped on-demand service is not itself a fault. Unavailable system manager or unparseable state cannot PASS. Successful systemctl does not prove fprintd D-Bus functionality. |
| override / P0 | Effective DropInPaths and exact project drop-in bytes at its fixed path; existing host-preflight rule. | <=5 s; user; no | C | Unknown `/etc` or `/run` drop-ins are known install blockers. Keep observed path only in sanitized form or a bounded known namespace. Never read arbitrary referenced files or export Environment values. Supported vendor paths do not prove their content is safe. |
| plasma / P1 | Fixed vendor PAM path, RPM owner; recognized project selector compared to packaged expected bytes if readable. Existing installer/removal checks. | <=5 s plus bounded RPM query; user; no | C | Recognized selector/vendor ownership is configuration evidence only. Unsupported, changed or unreadable selectors are not PASS; no login test or password-security assertion. Export classifications, not PAM file contents. |
| sudo_polkit / P1 | Existing diagnostic status contains no validated sudo/polkit configuration baseline. | Not collected; no privilege; no | C | Explicit `not_checked`; selected login event summaries may add evidence, but never infer all PAM integration is configured from Plasma alone. No authentication calls. |
| security / P1 | Fixed getenforce command and ownership/type/mode of ordinary Manager/software paths. Labels remain explicitly unverified. | <=5 s; user; no | C | Enforcing and trusted metadata are separate observations. Missing command, labels and excluded protected paths remain unavailable/not checked. No access to pairing state or templates even for label checks. |
| reader / P1 | Allowlisted idVendor/idProduct kernel-enumeration files; existing helper pattern. | <=5 s, bounded enumeration; user; no USB I/O | M | 27c6:5125 detected/absent means enumeration only. No serial numbers, descriptors, claim, initialization or health claim. Offline tests use fixtures, not host sensor enumeration. |
| operation / P0 | Cached helper result/code with known operation and collection time. Existing fields. | Cached; user; no | M | `rolled_back` only if supplied by validated helper; `operation_failed` alone cannot identify stage, rollback, or current activation. Contemporary override finding explains a blocker but does not prove the historical failure used it. |
| recognition_events / P1 | Bounded journal fprintd events classified against exact known driver/fprintd markers from source; new parser. | <=15 s; existing user journal permissions; no | E | Distinguish explicit no-match, FDT/acquisition failure, transport, initialization/authentication errors and unknown. Do not equate missing acquisition logs with acquisition failure or infer TLS fault from generic timeout. |
| login_events / P1 | Selected Plasma Login/SDDM, fprintd, sudo, polkit journal event summaries for selected time/boot. New probe. | <=15 s per bounded query; user journal access; no | E | Correlate only within same boot/time and source context. A driver match followed by auth failure is coexistence/order evidence, not proof of PAM causality. Missing records or denied access mean insufficient evidence. |
| security_events / P1 | Extended profile only: relevant SELinux denial markers inside the selected service journal events; new projection. Kernel/audit records are not collected. | Included in bounded journal query; user journal access; no | E | Report denial category if present; incomplete access/no visible records cannot prove absence of denials. No general SELinux audit coverage is claimed. Never run audit tools as root or weaken policy. |
| reader_action / P1 | Ordinary fprintd verification through QDBus; new Manager action, documented Device/Manager interfaces. | Runtime only, <=30 s per explicit attempt; current user's fprintd authorization; USB through stock stack | Protected action; report only fixed outcome | Disclose possible first-use pairing before start. One physical result per click, at most three per session; stop after MATCH. VerifyStop/Release and cancellation on all paths. Offline tests use fake bus only, never a real Claim/VerifyStart. A match proves only that attempt, not future login. |

The six visual check groups remain Goodix driver, Fingerprint components,
Fingerprint service, Sign-in integration, Security settings and Fingerprint reader.
Multiple probe results may populate one group. A group with missing required
evidence must show incomplete/unavailable, even if other probes pass. The overview
must not collapse partial configuration evidence into “authentication works”.

## Profiles, source limits and collection boundaries

| Profile | Entry / essential sources | Extended opt-in and limits |
| --- | --- | --- |
| A — System status | Check my system → Prepare system report. Host, driver snapshot, RPM/component integrity, service/override, Plasma, security, reader enumeration. | Additional available configuration classifications and source availability, never arbitrary configuration contents. |
| B — Installation/update | Installation or update failed. A plus operation code/result/time, observed blockers and current activation state when verified. | Relevant bounded lifecycle/service event codes. If no retained operation evidence exists, report historical phase unavailable; never manufacture “installation not activated” from a current override alone. |
| C — Recognition/acquisition | Fingerprint isn't recognized. A plus fprintd/driver event categories and timestamps in selected window. | Additional recognized diagnostic event categories, excluding biometric-derived values, template identifiers and sample/keypoint/match counts. No new biometric attempt. |
| D — Login/authentication | I can't sign in. A plus selected login/fprintd/sudo/polkit event categories and temporal relationship. | Additional source/boot availability and relevant recognized security-denial categories. No broad login history, users, command lines or auth tokens. |
| E — Other/deeper | Something else; A plus bounded union of C/D sources when explicitly requested. | Extended details must be separately opted into. E is still limited to recognized events/configuration classifications; it is not a raw archive or whole journal. |

Every report uses common schema/version, collection time, profile, selected time
window, source availability, observation time and excluded checks. Profiles A–E
select evidence; they do not force collection of unavailable or privileged data.
Before the first check the dashboard says “No checks have been run yet”. Opening
the center, selecting a problem or toggling extended details does not collect.

**Time:** allow current boot, previous boot, last 30 minutes, today, or an explicit
validated interval of at most 24 hours. “Most recent installation attempt” uses
only known dated operation evidence, with a five-minute window on each side of
the observed result time (bounded by the present); this is not the full duration
of a potentially long installation. If no dated operation is retained, ask for a
time window or report unavailable. Never silently replace a previous-boot request with current
boot. Missing boot, partial visibility, nonpersistent journal and empty results
must remain distinguishable where the source supports that distinction; otherwise
report history coverage unknown. No chronology guarantee from message text alone.

**Budgets:** commands are fixed argument lists with no shell, user executable,
unit/package/path injection or supplied journal expression. Validate options
against enums and parse time before constructing arguments. Per command stdout
cap 256 KiB, stderr cap 16 KiB; stop/terminate on overflow rather than collecting
unbounded data. RPM query/verification <=30 seconds, system metadata <=5 seconds,
journal <=15 seconds. Whole request <=120 seconds, <=1,000 journal records and
<=512 KiB encoded report, with explicit truncation/unavailable status. Read only
allowlisted regular text files, bounded to 64 KiB; reject unsafe redirection,
special files and untrusted path components. Bounded sysfs vendor/product reads
follow only the kernel enumeration layout and never escape the permitted tree.
Timeout, cancellation, signal, invalid encoding or parse failure discards partial
ambiguous conclusions. No hidden retry or automatic repeat; cleanup every process.

## Privacy and result contract

Report preparation requires fresh explicit consent **before collection**, even
for essential profiles, because timestamps and host metadata can identify people.
The notice names selected categories, scope, local storage and sharing risk.
Cancel must perform no new collection. Extended opt-in is independent and cannot
reuse prior consent after profile/time/category changes. Static check results
display only bounded codes/classifications; export requires the report flow.

Do not return raw command output, journal `MESSAGE`, exception strings, stderr,
Environment values, arbitrary paths or PAM content to the GUI/report. Parse them
internally and project only known codes, bounded numeric timestamps, known source
names and necessary validated metadata. Unknown event text is counted as
unclassified, never copied. This positive allowlist prevents a secret embedded in
unexpected journal text from reaching an export; regex redaction alone is
insufficient. No raw log preview, whole-journal dump, directory archive or caller
file selection for collection. No PSK, credentials, passwords, fingerprint images,
templates, pairing contents, protected file reads or raw USB dumps under any
consent setting. Extended output increases relevant recognized context, not the
range of readable protected data. No anonymity guarantee.

Keep report data in memory until the user reviews it and selects Copy/Save. Save
locally with restrictive 0600 permissions, refusing symlink/special-file targets
and silent overwrites; cancel leaves no report file. Clipboard copy is explicit
and the notice explains clipboard visibility. No upload/telemetry/network calls
from diagnostics, no persistent daemon or global logging change.
An I/O error while saving reports failure and may leave a partial 0600 file.
The exporter deliberately does not unlink by pathname on error, preserving a
replacement file that another process may have created at that path.

Each check carries stable `id`, `outcome` (`pass`, `anomaly`, `not_checked`,
`unavailable`), `code`, `source`, observation time and a bounded human explanation
chosen from a fixed catalog. Separate evidence level (`OBSERVED` or deterministic
`INFERRED`) from interpretation; unknown causes remain `UNKNOWN`, assumptions
must be labeled `ASSUMED`. Parser success is not a diagnostic PASS. Report source
failure independently of any anomaly already established by another source.

For #55, produce independent service-override and package-missing-file findings.
Only a verified operation receipt can state operation stage/result; a static
finding may say “This configuration can block installation”. Never translate
missing evidence into “no problem”, infer rollback from error exit, or claim the
driver was never activated without evidence. Fresh diagnostics do not erase the
original lifecycle result or enable an otherwise blocked lifecycle action.

## Presentation and qualification

Follow the approved HTML: existing Manager entry → dashboard with four status
summaries and three action cards → checks/details, problem choice, or reader page.
Problem choice → time/options → privacy consent → report summary/preview → local
Copy/Save. Preserve back navigation, plain English and existing KDE/Manager visual
language, cards, spacing, hierarchy and icon system. The earlier concept board's
sidebar does not replace this HTML navigation. Use the existing system palette;
dark mockup colors must not break the current Manager's light-theme behavior.
Demo controls, sample results and synthetic success are not production features.
The reader page implements ordinary verification with explicit consent; all
qualification in this campaign uses fake devices, never the system bus.

Before DIAG2 acceptance, pure fixture tests must distinguish both #55 findings,
query/permission/timeout failures, absent packages, changed versus missing files,
and hostile output without exporting protected values. Before DIAG3 acceptance,
exercise real QML navigation with a fake controller, keyboard/back/cancel,
consent before collection, preview, explicit safe Save/Copy and denied actions.
The independent Reviewer must explicitly compare GUI and approved HTML for
structure, navigation, style and coherence with the current Manager; record any
justified deviation. DIAG4 tests cover synthetic event ordering, no-match versus
FDT/acquisition versus transport versus auth, missing/partial history, previous
boot, overflow, cancellation and recovery without weakening the installer.

Offline results establish parser/UI/software behavior only. Sensor, privileged
host checks, real Fedora install/update/login/recovery and VM Fedora 45 remain
unqualified. Stop before RPM packaging and the VM campaign; DIAG5/live acceptance
remain separate decisions.

### Implemented collector boundary

`packaging/rpm/manager/diagnostics.py` implements the six check groups and profile
selection without privilege escalation. Per-check `source`, `observedAt` and
`evidence=OBSERVED` describe the collection; separately dated `cachedEvidence`
describes helper/operation observations. Cached state never becomes a current
runtime PASS. The GUI supplies a validated `Status` plus observation time and a
separate dated lifecycle result; absent retained evidence stays unavailable.
Package integrity distinguishes missing/changed files, unverifiable `?` attributes,
and query/timeout/permission/output failures. #55 findings are independent;
an override path is displayed only in the bounded known fprintd drop-in namespace.

Plasma selector matching is byte-for-byte via the SHA-256 of the reviewed
`deployment/plasma-login-opt-in/plasmalogin.pam`, with a fixture linking the
baseline to that source file. Absence and foreign selector content are distinct.
Ordinary software ownership/type/mode checks exclude all protected state paths;
SELinux file-label validation, sudo/polkit configuration validation and actual
authentication are explicitly unverified. The static security group remains
incomplete even when Enforcing and ordinary metadata are acceptable.

Recognized event categories come from real driver markers and ordinary fprintd
status names. Secure protocol failures require `secure_failure=1` and known
phase/kind values; healthy audit counters never imply an error or success.
Trusted systemd unit metadata identifies service sources. Sender-controlled
`SYSLOG_IDENTIFIER` alone cannot establish a source; sudo additionally requires
the trusted executable and command attributes. Only microsecond timestamp,
known source and category cross the boundary. Source boot identity is used
internally to reject mixed-boot chronology and is not exported. Matching events
remain observations; cause attribution stays UNKNOWN.

`test_diagnostics.py` covers the collector with injected files, runner, enumeration,
clock and software metadata. Its synthetic subprocess tests exercise output caps,
invalid encoding, cancellation, timeout and descendant cleanup without querying
host packages, services, journals or sensors. Export tests cover overwrite,
symlink, restrictive modes and replacement preservation on I/O failure.

### Reader and GUI boundary

The ordinary runtime reader uses the documented fprintd
[Manager](https://fprint.freedesktop.org/fprintd-dev/Manager.html) and
[Device](https://fprint.freedesktop.org/fprintd-dev/Device.html) APIs. After consent
only, enumerate GetDevices and bind the exact driver device name
`Goodix 27c6:5125 Fingerprint Sensor`; do not use an arbitrary default reader.
Claim the current user (`Claim('')`), subscribe to VerifyStatus and start
`VerifyStart('any')`. Every physical outcome, including retry statuses, ends the
attempt with VerifyStop and Release. A further attempt requires a new click;
the third ends the session and MATCH prevents further attempts. No enrollment,
deletion or new pairing protocol is implemented. State that ordinary first use
may activate the existing qualified pairing path. Cancellation, timeout, late
Claim replies, errors and application close must release resources; a disconnected
reader must not receive further method calls. Qt D-Bus calls must be asynchronous
and lazy: no bus connection/introspection before an explicit authorized action.

The GUI/controller boundary is `diagnostics`, a QVariantMap containing `busy`,
`checks` (id/title/summary/outcome/detail), `overview`, `reportText`, `reportTitle`,
`reportSummary`, `reportReady`, `reportError`, `readerState`, `readerMessage`.
Slots: `run_diagnostics()`,
`create_diagnostic_report(profile,timeWindow,extended,consent,since,until)`,
`copy_diagnostic_report()`, `save_diagnostic_report()`,
`start_reader_test(consent)`, `cancel_reader_test()`.
Profile enums are system/install/recognition/login/other (A/B/C/D/E); time enums
are current/previous/last30/today/custom/installation. Unsupported values fail
closed. Implementations must enforce consent and busy state below the GUI too.
