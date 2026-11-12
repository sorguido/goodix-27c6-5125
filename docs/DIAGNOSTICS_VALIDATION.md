<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Diagnostic Center: offline qualification

The initial Diagnostic Center implementation is committed on branch `diagnostic`
at `dbdff8dc70f33cd8cc6a9b141942ad3371a28080`. The current corrective changes are
in the working tree on that commit. Evidence from the initial qualification and
from this corrective pass is distinguished below. Offline checks qualify software
contracts and synthetic UI behavior, not real Fedora installation, authentication,
reader safety or biometric performance.

Scope: the user authorized DIAG1–DIAG4 offline and required a stop before RPM
packaging and the Fedora 45 VM campaign. The subsequent corrective request permits
updating staging code and manifests, while retaining the stop before an RPM build
or installation. No sensor, protected biometric/pairing
data, root operation, host runtime or Fedora authentication configuration was
used or changed. No new commit, merge, release or publication was performed by the
corrective pass.

## Corrective offline evidence

| Checks in this corrective pass | Result | Evidence |
| --- | --- | --- |
| Collector and shared installation-time contract | 27 PASS | `python3 -m unittest discover -s packaging/rpm/manager -p test_diagnostics.py`; includes concurrent Security findings and subsecond future timestamps |
| Manager staging contract | 3 PASS | `python3 packaging/rpm/test_stage.py -v`; temporary fixtures and isolated imports of staged modules, without building a payload or RPM |
| Controller and diagnostic QML | 22 PASS (13 Controller, 9 QML) | `python3 packaging/rpm/manager/test_diagnostics_ui.py --render-dir development/diagnostic-qualification/corrective/screens`; final availability/cancellation guards included |
| Manager palette/layout regression | PASS | `python3 packaging/rpm/manager/test_ui.py --initial-palette dark` and the same command with `--initial-palette light`; 13 in-memory render states per run |
| QML disk-cache regression | PASS | `python3 packaging/rpm/manager/test_qml_cache.py`; both QML pages load current bytes, with SVG resources available |

The first three corrective rows contain **52 distinct unit/integration cases**
(`27 + 3 + 22`). Palette/cache script gates and the Reviewer's three targeted repeats are
separate; they are not added to this count or to the historical baseline total.

Staging now explicitly includes `diagnostics.py`, `reader.py`,
`DiagnosticPage.qml` and fourteen local SVG icons alongside the existing Manager
files. Tests verify the exact allowlist, modes, exclusion of unrelated files,
isolated module imports and the existing recursive Manager `%files` ownership.
The future spec adds the staging contract test. These are source/fixture checks,
not a package build or installation result.

The Security group retains SELinux mode and software metadata findings together,
including concurrent anomalies and unavailable sources, with separate stable
codes and readable details in the UI and report. The shared pure
`installation_reference()` accepts only a usable, timezone-aware, nonfuture
install/update time; remove-only, malformed and unavailable references cannot
enable the latest-installation choice. The collector validates the same window.
New collection, failure, denial and cancellation clear previous checks, overview
and collection timestamp; failure remains explicit instead of displaying old
results as fresh. Descriptions do not claim D-Bus, SELinux policy or file-label
coverage beyond the observations actually collected.

The independent Reviewer checked all seven points against the corrective request,
including the HTML layout/navigation and the icon style of
`development/diagnostic/mokeup icon to be used.png`, without blocking findings.
Final independent review accepted the complete corrective pass
(`ACCEPT_AND_CONTINUE`), with 52 cases PASS and no blocking findings. Layout and
navigation match the HTML reference; icon morphology/style match the PNG at
24 pixels in dark/light palettes. Icon style follows the PNG reference; this does not
introduce the concept board's earlier sidebar into the HTML navigation.

Nineteen current synthetic captures are in
`development/diagnostic-qualification/corrective/screens/`, including latest-time
availability, failed recollection and 24-pixel icon contacts in both palettes.
The Reviewer explicitly compared overview/check/problem/reader views and the
corrective views/icon contacts with the approved references. All these PNGs are
Git-ignored generated evidence, not approved source artwork or real-host results.
The icon comparison includes fingerprint, gear, USB and checklist morphology at
24 pixels, rounded line style and readable palette contrast in dark/light mode.

## Baseline qualification retained

The PM and independent Reviewer accepted the initial DIAG3/DIAG4 offline
qualification recorded in the committed baseline. The following results are
retained prior evidence; they do not mean that every baseline test was rerun in
this corrective pass. Commands are run from the repository root. Host sources,
lifecycle operations and public-network responses in these tests are synthetic
or mocked.

| Checks | Result | Evidence command / scope |
| --- | --- | --- |
| Diagnostic collector | 24 PASS | `python3 -m unittest discover -s packaging/rpm/manager -p test_diagnostics.py` |
| Reader state and Qt adapter | 21 PASS | `python3 packaging/rpm/manager/test_reader.py`: 19 fake-state cases plus two actual Qt/private-bus cases |
| Controller and diagnostic QML flows | 18 PASS | `python3 packaging/rpm/manager/test_diagnostics_ui.py --render-dir development/diagnostic-qualification/screens`: 11 Controller cases plus seven QTest/QML cases |
| Restricted lifecycle helper regression | 28 PASS | `python3 packaging/rpm/test_helper.py`; helper source unchanged |
| Presentation/release model regression | 17 PASS | `python3 packaging/rpm/manager/test_model.py`; model source unchanged |
| Existing network/lifecycle UI regression | 15 PASS | `python3 packaging/rpm/manager/test_network_ui.py`; synthetic network and process responses |
| Existing Manager light/dark and compact layout | PASS | `python3 packaging/rpm/manager/test_ui.py --initial-palette dark` and `python3 packaging/rpm/manager/test_ui.py --initial-palette light`; 13 render states per run |
| QML disk-cache regression | PASS | `python3 packaging/rpm/manager/test_qml_cache.py`; fresh process reads current Manager and Diagnostic Center bytes despite old disk caches |

There were **123 distinct unit/integration cases** in the baseline's first six rows
(`24 + 21 + 18 + 28 + 17 + 15`). Rendering/cache script gates and repeated targeted
checks are reported separately and are not added to that count. After the final
reader-header label correction, the affected QML flow was rerun separately: one
targeted case PASS using `python3 packaging/rpm/manager/test_diagnostics_ui.py UiTests.test_reader_requires_consent_and_cancel_is_explicit`.

The two real Qt adapter cases used a temporary private `dbus-daemon` and a fake
fprintd service as the normal user. Sandbox approval covered the necessary UNIX
socket capability; it did not grant root, access a real fprintd instance or touch
the reader. These cases exercise real object-path-array/variant deserialization,
VerifyStatus signal delivery and actual peer disconnection while Claim is pending.

Collector fixtures exercise independent #55 override and missing-libfprint-file
findings, missing/changed/unverifiable RPM attributes, query errors, denied or
partial history, previous boot and custom intervals, unknown source messages,
microsecond ordering and mixed-boot refusal. Synthetic subprocesses test stdout
and stderr limits, invalid encoding, timeout/cancellation after pipe EOF and
cleanup of pipe-holding descendants after the leader exits. Export fixtures cover
0600 mode, existing targets, symlinks and preservation of a replacement path on
I/O failure. No host RPM, service, journal or sensor query is used by these tests.

Reader tests cover exact target selection, missing/ambiguous targets, consent,
permission denial, one physical result per explicit action, at most three attempts,
stop after MATCH, retry statuses, cancellation, late replies, timeout, disconnection
and failed cleanup. Offline tests cannot prove the behavior of the physical
device or ordinary first-use pairing.

The cache test preserves mtimes for both QML files. It also preserves byte length
for the Diagnostic Center substitution. The Manager seed removes a control and
therefore has a different byte length; a same-size Manager replacement is not
claimed by this test.

## Baseline comparison with approved GUI references

During initial qualification, the independent Reviewer compared the realized GUI with the approved local HTML,
navigation diagram and overview/workflow boards, and with the current Goodix
Manager. Result: **ACCEPT_AND_CONTINUE for DIAG3 offline**.

| Approved structure / behavior | Reviewed implementation |
| --- | --- |
| Existing Manager entry point | Diagnostic Center replaces Copy diagnostics; existing installation/update/removal and document/bug controls remain in their current Manager context. |
| Dashboard | Four status summaries and three action cards: Check my system, I have a problem, Test the reader; initial unchecked/incomplete state, no invented healthy result. |
| System checks and problem choice | Six check groups with details; installation, sign-in, recognition and other-problem choices follow the approved navigation. #55 findings remain separate. |
| Report workflow | Time and inclusion options, explicit privacy consent before collection, local summary/preview and explicit Copy/Save; cancelled/denied/invalid collection never produces a ready report. |
| Reader workflow | Approved reader page and visual hierarchy; separate runtime consent, explicit attempts and cancellation, no simulated production MATCH. |
| Visual coherence | Existing Manager/KDE typography, hierarchy, card structure and spacing remain the reference; no concept-board sidebar was substituted for the approved HTML navigation. |

Reviewed and justified adaptations are native Qt controls/system palette to
preserve the current Manager and its light theme; explicit ISO date/time input
with timezone for an unambiguous custom interval; and real reader consent,
Cancel, cleanup and the three-attempt safety bound instead of demo controls.
These adaptations preserve the approved structure and navigation.

Thirteen local captures are in
`development/diagnostic-qualification/screens/`: Manager, overview, checks,
problem choice, preparation, consent, preview, reader, history denial, light and
compact variants, and the #55 preview using the real collector with fixture
sources. **All captures are synthetic generated qualification outputs, not
approved design references or evidence from a real host.** All 13 PNG files are
Git-ignored and remain separate from `development/diagnostic/`.

The offscreen keyboard/back test exercises native PageRow pop and verifies
cancellation/invalidation when the page is removed. Where Alt+Left is not mapped
by the offscreen platform it calls that same native pop directly. Actual KDE
window-manager shortcut behavior remains unqualified.

## Evidence boundaries and remaining work

- Cached helper status and last-operation evidence retain separate observation
  times. Current static checks do not prove the historical failure cause, runtime
  health, rollback or future login success.
- Empty, partial, inaccessible or missing boot history is not a healthy result.
  Event correlation retains source/time/boot scope; causal attribution remains
  UNKNOWN. Raw journal text, secrets, templates and pairing data are not exported.
- Plasma selector bytes and vendor ownership can be checked. sudo/polkit behavior,
  complete PAM authentication and real login/unlock/recovery remain unqualified.
  Protected SELinux labels are not read; kernel/audit history is not collected.
- Save failure is reported and may leave a partial 0600 file. The exporter does
  not unlink a pathname after I/O failure because another process may have
  replaced it. Cancelling the file dialog creates no file.
- Manager staging code/manifests are now corrected and fixture-tested. Actual RPM
  build, package-content verification, installation and Fedora 45 VM qualification
  remain unperformed and require separate authorization.

The branch and HEAD are `diagnostic` /
`dbdff8dc70f33cd8cc6a9b141942ad3371a28080`. The initial implementation is committed;
only the corrective delta is uncommitted. The former `78a5924` reference described
the earlier qualification epoch and is not the current HEAD.
The PM rechecked all six approved local assets against their initial SHA-256
inventory: unchanged. The previous-milestone cache is unchanged. Governance files
`AGENTS.md`/`START.md`/`ROADMAP.md`, helper, deployment, driver and production code
were not modified in the corrective pass. RPM staging/spec source changes are
explicitly authorized corrections; no build or activation followed them.

**Stop before RPM packaging and the Fedora 45 VM campaign.** DIAG4 real-target
qualification and DIAG5/live acceptance remain pending separate authorization.
This is an offline qualification record, not `MILESTONE_COMPLETE` or a claim that
the full real-system DIAG4 EXIT_GATE has been demonstrated.
