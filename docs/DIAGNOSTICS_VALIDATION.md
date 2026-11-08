<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Diagnostic Center: offline qualification

The Diagnostic Center implementation on branch `diagnostic` passed the offline
checks below. This qualifies software contracts and synthetic UI behavior, not
real Fedora installation, authentication, reader safety or biometric performance.
DIAG3 independent review accepted the implemented GUI against the approved
mockup. Final independent review accepted DIAG4 offline consolidation
(`ACCEPT_AND_CONTINUE` for the offline scope only).

Scope: the user authorized DIAG1–DIAG4 offline and required a stop before RPM
packaging and the Fedora 45 VM campaign. No sensor, protected biometric/pairing
data, root operation, host runtime or Fedora authentication configuration was
used or changed. No commit, merge, release or publication was performed.

## Automated evidence

The PM and independent Reviewer verified these results during this Goal. Commands
are run from the repository root. All host sources, lifecycle operations and
public-network responses in the tests are synthetic or mocked.

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

There are **123 distinct unit/integration cases** in the first six rows
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

## Explicit comparison with approved GUI references

The independent Reviewer compared the realized GUI with the approved local HTML,
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
- RPM staging manifests intentionally have **not** been updated for the new
  Python modules and `DiagnosticPage.qml`. Reviewing and updating packaging is a
  prerequisite for a future package, not a completed distribution check.

The branch and HEAD remain `diagnostic` /
`78a592475058f1b48f795883d19e9d18114f7d3e`; implementation is in the working tree.
The PM rechecked all six approved local assets against their initial SHA-256
inventory: unchanged. The previous-milestone cache is unchanged. Governance files
`AGENTS.md`/`START.md`, helper, deployment, driver, production and RPM staging code
were not modified by this Goal; `ROADMAP.md` has only the authorized scope update.

**Stop before RPM packaging and the Fedora 45 VM campaign.** DIAG4 real-target
qualification and DIAG5/live acceptance remain pending separate authorization.
This is an offline qualification record, not `MILESTONE_COMPLETE` or a claim that
the full real-system DIAG4 EXIT_GATE has been demonstrated.
