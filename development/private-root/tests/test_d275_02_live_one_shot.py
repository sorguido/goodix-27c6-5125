# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline D275/02 corrective gates: authority, report, marker, leakage."""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from core.persistent_runtime import FIRST_IMAGE_IRQ2_TIMEOUT_MS, TerminalBoundary
import core.d268_first_image_operator as d268
import core.d275_second_b0_operator as d275
import core.live_capability as capability
import tools.d275_live_second_b0_once as tool


REPO = Path(__file__).resolve().parents[1]
D268_HISTORICAL_MANIFEST = REPO / "analysis/D268/D268_01_live_critical_manifest.json"


class D275EntrypointTests(unittest.TestCase):
    def test_fake_live_same_entrypoint_closes_second_b0(self):
        process = subprocess.run(
            [
                "./operator_kit/d275-second-b0-once.sh",
                "--fake-live",
                "--terminal-boundary",
                "STOP_AFTER_SECOND_IMAGE",
            ],
            cwd=REPO,
            text=True,
            capture_output=True,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        document = json.loads(process.stdout)
        self.assertEqual(document["OUTCOME"], "PASS")
        self.assertFalse(document["third_cycle_started"])
        self.assertEqual(
            document["execution_mode"],
            "FAKE_TRANSPORT_SAME_PRODUCTION_COORDINATOR",
        )

    def test_historical_default_is_not_silently_promoted(self):
        self.assertEqual(
            TerminalBoundary.STOP_AFTER_FIRST_IMAGE.value, "STOP_AFTER_FIRST_IMAGE"
        )
        self.assertEqual(tool.main(["--fake-live"]), 2)

    def test_gate_is_exact_and_precedes_usb(self):
        with mock.patch.dict("os.environ", {tool.BASELINE_ENV: "a" * 40}), mock.patch.object(
            tool, "verify_d275_authoritative_baseline"
        ) as verify:
            self.assertEqual(tool.live_once("vague"), 1)
            verify.assert_not_called()

    def test_d268_runner_default_remains_first_image(self):
        self.assertNotIn(
            "terminal_mode", d268.run_d268_first_image_candidate.__kwdefaults__ or {}
        )
        self.assertIn(
            "TerminalBoundary.STOP_AFTER_FIRST_IMAGE",
            (REPO / "core/d268_first_image_operator.py").read_text(),
        )

    def test_allowlist_has_no_persistent_families(self):
        source = (REPO / "core/persistent_runtime.py").read_text()
        self.assertIn("control not in {0x34, 0x20, 0x50, 0x32, 0x22}", source)
        fragment = source[
            source.index("class _ProductionMultiFrameChannel") : source.index(
                "class PersistentRuntimeCoordinator"
            )
        ]
        for forbidden in ("0xA2, 0x70", "flash", "enrollment_commit", "factory_reset"):
            self.assertNotIn(forbidden, fragment)

    def test_failure_matrix_is_owned_by_production_suite(self):
        self.assertEqual(tool.BOUNDARY, TerminalBoundary.STOP_AFTER_SECOND_IMAGE)

    def test_helper_is_named_d275_not_d268(self):
        self.assertTrue(hasattr(d275, "verify_d275_authoritative_baseline"))
        self.assertFalse(hasattr(d275, "verify_d268_authoritative_baseline"))
        self.assertNotIn("verify_d268_authoritative_baseline", tool.__dict__)


class D275ReportIsolationTests(unittest.TestCase):
    def test_report_paths_are_distinct(self):
        self.assertEqual(
            d275.D275_REPORT_PATH,
            Path("/var/lib/goodix-5125-poc/d261-results/d275-second-b0-final.json"),
        )
        self.assertNotEqual(d275.D275_REPORT_PATH, d268.D268_REPORT_PATH)
        self.assertNotEqual(d275.D275_MARKER_PATH, d268.D268_SINGLE_USE_MARKER_PATH)

    def test_safe_preflight_uses_d275_path(self):
        seen: list[Path] = []

        def capture(path):
            seen.append(path)

        with mock.patch(
            "tools.d261_live_fdt_arm_once.prepare_report_directory"
        ), mock.patch(
            "tools.d261_live_fdt_arm_once.require_safe_report_destination",
            side_effect=capture,
        ):
            d275._require_d275_safe_directories()
        self.assertEqual(seen, [d275.D275_REPORT_PATH])
        self.assertNotIn(d268.D268_REPORT_PATH, seen)

    def test_d268_report_path_untouched_when_candidate_publishes(self):
        published: list[tuple[Path, dict]] = []

        def fake_publish(path, report, **_kwargs):
            published.append((path, dict(report)))

        report = {
            "result": "PASS_STOP_AFTER_FIRST_IMAGE",
            "phase_reached": "STOP_AFTER_FIRST_IMAGE",
            "report_destination_preflight_passed": True,
        }
        with mock.patch(
            "tools.d261_live_fdt_arm_once.publish_report", side_effect=fake_publish
        ):
            finalized = d275._finalize_second_image_report(report)
            d275._publish_d275_final_report(finalized)
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0][0], d275.D275_REPORT_PATH)
        self.assertNotEqual(published[0][0], d268.D268_REPORT_PATH)
        self.assertEqual(published[0][1]["result"], "PASS_STOP_AFTER_SECOND_IMAGE")
        self.assertEqual(
            published[0][1]["phase_reached"], "STOP_AFTER_SECOND_IMAGE"
        )

    def test_publication_failure_is_fail_closed(self):
        report = {
            "result": "PASS_STOP_AFTER_SECOND_IMAGE",
            "phase_reached": "STOP_AFTER_SECOND_IMAGE",
            "report_destination_preflight_passed": True,
        }
        with mock.patch(
            "tools.d261_live_fdt_arm_once.publish_report",
            side_effect=RuntimeError("disk"),
        ):
            d275._publish_d275_final_report(report)
        self.assertEqual(report["result"], "FAIL_CLOSED_REPORT_UNPUBLISHED")
        self.assertIn("report_publication_failure", report)

    def test_production_dependencies_defer_d268_publish(self):
        fake = mock.Mock()
        intent = capability.issue_d275_intent(capability.D275_LIVE_AUTHORIZATION_FLAG)
        with mock.patch.object(d268.D268ProductionDependencies, "build", return_value=fake):
            deps = d275.build_dependencies(REPO, intent)
        self.assertEqual(deps.require_safe_directories, d275._require_d275_safe_directories)
        deps.publish_report({"result": "PASS_STOP_AFTER_FIRST_IMAGE"})

    def test_construct_forces_second_image_boundary(self):
        seen: dict[str, object] = {}
        coordinator = mock.Mock()

        def run(*_args, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(command_trace=(), first_image_raster_shape=None)

        coordinator.run = run
        intent = capability.issue_d275_intent(capability.D275_LIVE_AUTHORIZATION_FLAG)
        with mock.patch.object(
            d268.D268ProductionDependencies, "build", return_value=mock.Mock()
        ), mock.patch.object(
            d268.D268ProductionDependencies, "construct_runtime", return_value=coordinator
        ):
            deps = d275.build_dependencies(REPO, intent)
            deps.construct_coordinator(object(), object(), object()).run(ts16=1)
        self.assertEqual(seen["terminal_mode"], TerminalBoundary.STOP_AFTER_SECOND_IMAGE)

    def test_d268_publish_is_deferred_until_after_finalization(self):
        events: list[str] = []
        intent = capability.issue_d275_intent(capability.D275_LIVE_AUTHORIZATION_FLAG)

        class Secret:
            def close(self) -> None:
                events.append("secret_close")

        class Coordinator:
            def run(self, **kwargs):
                events.append("run")
                return SimpleNamespace(
                    command_trace=(), first_image_raster_shape=None
                )

            def audit(self):
                return {"retry_count": 0, "persistent_device_write_count": 0}

        with tempfile.TemporaryDirectory() as temporary:
            marker_path = Path(temporary) / "marker"

            def claim(sha, token):
                events.append("marker")
                return d275.claim_d275_marker(marker_path, sha, token)

            def construct(live, _secret, _target):
                capability.require_known_live_io_capability(live)
                events.append("construct")
                return Coordinator()

            dependencies = d268.D268OperatorDependencies(
                observe_baseline_verified=lambda: None,
                require_operator_context=lambda: None,
                require_safe_directories=lambda: events.append("safe_dirs"),
                verify_protected_metadata=lambda: None,
                verify_gfusb_hash=lambda: None,
                resolve_exact_target=lambda: object(),
                stop_fprintd=lambda: None,
                block_signals=lambda: None,
                require_no_holders=lambda _target: None,
                validate_non_secret_material=lambda: None,
                require_marker_absent=lambda: None,
                materialize_secret_once=Secret,
                claim_marker_once=claim,
                observe_live_io_issue=lambda: events.append("live_io"),
                construct_coordinator=construct,
                restore_signals=lambda: events.append("restore_signals"),
                restore_fprintd=lambda: events.append("restore_fprintd"),
                publish_report=lambda _report: None,
            )
            with mock.patch.object(d275, "verify_d275_authoritative_baseline"), mock.patch.object(
                d275,
                "_publish_d275_final_report",
                side_effect=lambda report: events.append(
                    f"d275_publish:{report['result']}:{report['phase_reached']}"
                ),
            ):
                report = d275.run_candidate(
                    intent,
                    dependencies,
                    repo=REPO,
                    sha="a" * 40,
                    ts16=1,
                )
        self.assertEqual(report["result"], "PASS_STOP_AFTER_SECOND_IMAGE")
        self.assertEqual(report["phase_reached"], "STOP_AFTER_SECOND_IMAGE")
        self.assertEqual(
            events[-1],
            "d275_publish:PASS_STOP_AFTER_SECOND_IMAGE:STOP_AFTER_SECOND_IMAGE",
        )
        self.assertLess(events.index("restore_signals"), events.index(events[-1]))
        self.assertLess(events.index("restore_fprintd"), events.index(events[-1]))


class D275MarkerTests(unittest.TestCase):
    def test_schema_is_d275_specific(self):
        self.assertEqual(d275.D275_MARKER_SCHEMA, "D275_SECOND_B0_SINGLE_USE_MARKER_V1")
        with tempfile.TemporaryDirectory() as temporary:
            intent = capability.issue_d275_intent(capability.D275_LIVE_AUTHORIZATION_FLAG)
            capability.consume_d275_intent(intent)
            marker_path = Path(temporary) / "d275.marker"
            with mock.patch("core.d275_second_b0_operator.os.fsync", wraps=os.fsync) as fsync:
                marker = d275.claim_d275_marker(marker_path, "a" * 40, intent)
            fsync.assert_called_once()
            document = json.loads(marker_path.read_text(encoding="utf-8"))
            self.assertEqual(document["schema"], d275.D275_MARKER_SCHEMA)
            self.assertEqual(document["approved_baseline_sha"], "a" * 40)
            self.assertEqual(document["terminal_boundary"], "STOP_AFTER_SECOND_IMAGE")
            live = capability.issue_d275_live_io(marker)
            capability.require_known_live_io_capability(live)

    def test_fsync_happens_before_capability(self):
        order: list[str] = []
        with tempfile.TemporaryDirectory() as temporary:
            intent = capability.issue_d275_intent(capability.D275_LIVE_AUTHORIZATION_FLAG)
            capability.consume_d275_intent(intent)
            marker_path = Path(temporary) / "d275.marker"

            def fsync(_fd):
                order.append("fsync")

            original = d275._issue_d275_marker_after_durable_claim

            def after(token):
                order.append("capability")
                return original(token)

            with mock.patch("core.d275_second_b0_operator.os.fsync", side_effect=fsync), mock.patch(
                "core.d275_second_b0_operator._issue_d275_marker_after_durable_claim",
                side_effect=after,
            ):
                d275.claim_d275_marker(marker_path, "b" * 40, intent)
        self.assertEqual(order, ["fsync", "capability"])

    def test_marker_is_single_use(self):
        with tempfile.TemporaryDirectory() as temporary:
            intent = capability.issue_d275_intent(capability.D275_LIVE_AUTHORIZATION_FLAG)
            capability.consume_d275_intent(intent)
            marker = d275.claim_d275_marker(Path(temporary) / "m", "c" * 40, intent)
            capability.issue_d275_live_io(marker)
            with self.assertRaises(capability.CapabilityFailure):
                capability.issue_d275_live_io(marker)

    def test_d268_capability_cannot_mint_d275_authority(self):
        old = capability.issue_d268_intent(capability.D268_LIVE_AUTHORIZATION_FLAG)
        capability.consume_d268_intent(old)
        with self.assertRaises(capability.CapabilityFailure):
            capability._issue_d275_marker_after_durable_claim(old)
        with self.assertRaises(capability.CapabilityFailure):
            capability.issue_d275_live_io(old)

    def test_d275_capability_cannot_mint_d268_authority(self):
        current = capability.issue_d275_intent(capability.D275_LIVE_AUTHORIZATION_FLAG)
        capability.consume_d275_intent(current)
        with self.assertRaises(capability.CapabilityFailure):
            capability._issue_d268_marker_after_durable_claim(current)
        with self.assertRaises(capability.CapabilityFailure):
            capability.issue_d268_live_io(current)

    def test_claim_does_not_patch_d268_marker_writer(self):
        original = d268._issue_d268_marker_after_durable_claim
        with tempfile.TemporaryDirectory() as temporary:
            intent = capability.issue_d275_intent(capability.D275_LIVE_AUTHORIZATION_FLAG)
            capability.consume_d275_intent(intent)
            d275.claim_d275_marker(Path(temporary) / "m", "d" * 40, intent)
        self.assertIs(d268._issue_d268_marker_after_durable_claim, original)


class D275AuthorityTests(unittest.TestCase):
    def test_live_critical_set_covers_real_dependencies(self):
        required = {
            "operator_kit/d275-second-b0-once.sh",
            "tools/d275_live_second_b0_once.py",
            "core/d275_second_b0_operator.py",
            "core/d268_first_image_operator.py",
            "core/live_capability.py",
            "core/persistent_runtime.py",
            "core/multiframe_validation.py",
            "core/fdt_lifecycle.py",
            "core/runtime_transport.py",
            "core/usb_runtime.py",
            "core/tls_b0.py",
            "core/cold_start.py",
            "core/fdt_seed.py",
            "core/post_d4.py",
            "core/protected_runtime.py",
            "src/goodix5125_cleanroom.py",
            "tools/d261_live_fdt_arm_once.py",
            "poc/goodix5125/tools/binding_reference/__init__.py",
            "poc/goodix5125/tools/binding_reference/runtime.py",
            "poc/goodix5125/tools/binding_reference/crypto_reference.py",
            "poc/goodix5125/tools/binding_reference/pe_parser.py",
        }
        self.assertEqual(set(d275.D275_LIVE_CRITICAL_PATHS), required)
        self.assertEqual(
            len(d275.D275_LIVE_CRITICAL_PATHS),
            len(set(d275.D275_LIVE_CRITICAL_PATHS)),
        )
        self.assertNotIn("Goodix 27c6 5125 manuale tecnico.md", d275.D275_LIVE_CRITICAL_PATHS)
        self.assertNotIn(
            "analysis/D268/D268_01_live_critical_manifest.json",
            d275.D275_LIVE_CRITICAL_PATHS,
        )

    def test_wrong_path_set_is_rejected(self):
        with self.assertRaisesRegex(
            d275.D275OperatorFailure, "authoritative_path_set_mismatch"
        ):
            d275.verify_d275_authoritative_baseline(
                REPO, "a" * 40, d268.D268_FIRST_IMAGE_LIVE_CRITICAL_PATHS
            )

    def test_sha_must_be_full_lowercase(self):
        for invalid in ("", "a" * 39, "A" * 40, "g" * 40):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(
                    d275.D275OperatorFailure, "full_sha_required"
                ):
                    d275.validate_full_sha(invalid)

    def test_d268_historical_manifest_is_not_current_authority(self):
        document = json.loads(D268_HISTORICAL_MANIFEST.read_text(encoding="utf-8"))
        historical = tuple(row["path"] for row in document["live_critical_files"])
        self.assertNotEqual(historical, d275.D275_LIVE_CRITICAL_PATHS)
        self.assertFalse(document["baseline_approved"])
        self.assertNotIn("core/multiframe_validation.py", historical)


class D275AdapterLeakageTests(unittest.TestCase):
    def _originals(self):
        return (
            d268._consume_intent,
            d268.issue_d268_live_io_after_marker,
            d268.verify_d268_authoritative_baseline,
            d268._issue_d268_marker_after_durable_claim,
        )

    def test_adapters_restore_on_success_and_failure(self):
        originals = self._originals()
        with d275._d268_host_adapters():
            self.assertIsNot(d268._consume_intent, originals[0])
            self.assertIsNot(d268.issue_d268_live_io_after_marker, originals[1])
            self.assertIsNot(d268.verify_d268_authoritative_baseline, originals[2])
        self.assertEqual(self._originals(), originals)
        with self.assertRaises(RuntimeError):
            with d275._d268_host_adapters():
                raise RuntimeError("boom")
        self.assertEqual(self._originals(), originals)

    def test_run_candidate_restores_d268_globals(self):
        originals = self._originals()
        intent = capability.issue_d275_intent(capability.D275_LIVE_AUTHORIZATION_FLAG)
        dependencies = mock.Mock()
        dependencies.require_safe_directories.side_effect = RuntimeError("preflight")
        with mock.patch.object(d275, "verify_d275_authoritative_baseline"), mock.patch.object(
            d275, "_publish_d275_final_report"
        ):
            report = d275.run_candidate(
                intent, dependencies, repo=REPO, sha="a" * 40, ts16=1
            )
        self.assertEqual(report["result"], "FAIL_CLOSED")
        self.assertEqual(self._originals(), originals)


class D275OperatorUxTests(unittest.TestCase):
    def _run_fake_live(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "./operator_kit/d275-second-b0-once.sh",
                "--fake-live",
                "--terminal-boundary",
                "STOP_AFTER_SECOND_IMAGE",
            ],
            cwd=REPO,
            text=True,
            capture_output=True,
        )

    def _empty_lines_before(self, text: str, pos: int) -> int:
        count = 0
        end = pos
        while True:
            start = text.rfind("\n", 0, end)
            if start == -1:
                break
            line = text[start + 1 : end]
            if line.strip() == "":
                count += 1
                end = start
            else:
                break
        return count

    def test_fake_live_stdout_is_json_stderr_is_operator_ux(self):
        process = self._run_fake_live()
        self.assertEqual(process.returncode, 0, process.stderr)
        document = json.loads(process.stdout)
        self.assertEqual(document["OUTCOME"], "PASS")
        self.assertIn("D275 — PREPARAZIONE", process.stderr)
        self.assertNotIn("D275 — PREPARAZIONE", process.stdout)

    def test_fake_live_operator_sequence_order_and_no_duplicates(self):
        process = self._run_fake_live()
        err = process.stderr
        blocks = [
            "D275 — PREPARAZIONE",
            "D275 — AZIONE OPERATORE 1/3",
            "D275 — AZIONE OPERATORE 2/3",
            "D275 — AZIONE OPERATORE 3/3",
            "D275 — TEST COMPLETATO",
        ]
        positions = [err.find(header) for header in blocks]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(len(set(positions)), len(positions))
        for header in blocks:
            self.assertEqual(err.count(header), 1, f"duplicate or missing {header}")

    def test_fake_live_blocks_have_two_empty_lines_between(self):
        process = self._run_fake_live()
        err = process.stderr
        # Each block is: ====, header, body lines, ====.  Verify that the gap
        # between the closing separator of one block and the opening separator
        # of the next contains at least two completely empty lines.
        blocks = list(
            re.finditer(r"={60}\nD275 — [^\n]+(?:\n[^\n]+)*\n={60}", err)
        )
        self.assertEqual(len(blocks), 5)
        for i in range(len(blocks) - 1):
            gap = err[blocks[i].end() : blocks[i + 1].start()]
            self.assertIn(
                "\n\n\n",
                gap,
                f"block {i} -> {i + 1} lacks two empty lines: {gap!r}",
            )

    def test_fake_live_simulation_line_in_every_block(self):
        process = self._run_fake_live()
        err = process.stderr
        for marker in [
            "D275 — PREPARAZIONE",
            "D275 — AZIONE OPERATORE 1/3",
            "D275 — AZIONE OPERATORE 2/3",
            "D275 — AZIONE OPERATORE 3/3",
            "D275 — TEST COMPLETATO",
        ]:
            pos = err.find(marker)
            end = err.find("=", pos)
            block = err[pos:end]
            self.assertIn("SIMULAZIONE — NON TOCCARE IL SENSORE", block)

    def test_prompts_attach_exactly_to_irq2_timeout_waits(self):
        state = d275.D275OperatorPromptState()
        delegate = mock.Mock()
        frames = [b"first_irq2", b"irq_0200", b"second_irq2"]
        delegate.wait_event = mock.Mock(side_effect=frames)
        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            es = d275.D275OperatorPromptingEventSource(
                delegate, state=state, simulation=True
            )
            for expected, frame in zip(
                [
                    "AZIONE OPERATORE 1/3",
                    "AZIONE OPERATORE 2/3",
                    "AZIONE OPERATORE 3/3",
                ],
                frames,
            ):
                returned = es.wait_event(FIRST_IMAGE_IRQ2_TIMEOUT_MS)
                self.assertEqual(returned, frame)
                self.assertIn(expected, stderr.getvalue())
        self.assertEqual(delegate.wait_event.call_count, 3)
        for call in delegate.wait_event.call_args_list:
            self.assertEqual(call.args[0], FIRST_IMAGE_IRQ2_TIMEOUT_MS)

    def test_prompts_do_not_consume_or_modify_events(self):
        state = d275.D275OperatorPromptState()
        expected = b"event_bytes"
        delegate = mock.Mock()
        delegate.wait_event = mock.Mock(return_value=expected)
        es = d275.D275OperatorPromptingEventSource(
            delegate, state=state, simulation=True
        )
        self.assertEqual(es.wait_event(FIRST_IMAGE_IRQ2_TIMEOUT_MS), expected)
        self.assertEqual(es.wait_event(FIRST_IMAGE_IRQ2_TIMEOUT_MS), expected)
        self.assertEqual(es.wait_event(FIRST_IMAGE_IRQ2_TIMEOUT_MS), expected)

    def test_non_irq2_waits_do_not_emit_operator_prompts(self):
        state = d275.D275OperatorPromptState()
        delegate = mock.Mock()
        delegate.wait_event = mock.Mock(return_value=b"event")
        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            es = d275.D275OperatorPromptingEventSource(
                delegate, state=state, simulation=True
            )
            es.wait_event(500)
            es.wait_event(2000)
            es.wait_event(12345)
        self.assertNotIn("AZIONE OPERATORE", stderr.getvalue())

    def test_wait_failure_emits_failure_block_and_no_repeat(self):
        state = d275.D275OperatorPromptState()
        delegate = mock.Mock()
        delegate.wait_event = mock.Mock(side_effect=RuntimeError("boom"))
        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            es = d275.D275OperatorPromptingEventSource(
                delegate, state=state, simulation=True
            )
            for _ in range(2):
                with self.assertRaises(RuntimeError):
                    es.wait_event(FIRST_IMAGE_IRQ2_TIMEOUT_MS)
        err = stderr.getvalue()
        self.assertIn("D275 — AZIONE OPERATORE 1/3", err)
        self.assertIn("D275 — TEST INTERROTTO", err)
        self.assertEqual(err.count("TEST INTERROTTO"), 1)

    def test_failure_reported_after_action_one_hides_later_prompts(self):
        state = d275.D275OperatorPromptState()
        delegate = mock.Mock()
        delegate.wait_event = mock.Mock(return_value=b"frame1")
        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            es = d275.D275OperatorPromptingEventSource(
                delegate, state=state, simulation=True
            )
            es.wait_event(FIRST_IMAGE_IRQ2_TIMEOUT_MS)
            state.show_failure(simulation=True)
        err = stderr.getvalue()
        self.assertIn("D275 — AZIONE OPERATORE 1/3", err)
        self.assertIn("D275 — TEST INTERROTTO", err)
        self.assertNotIn("D275 — AZIONE OPERATORE 2/3", err)
        self.assertNotIn("D275 — AZIONE OPERATORE 3/3", err)
        self.assertNotIn("D275 — TEST COMPLETATO", err)

    def test_failure_reported_after_action_two_hides_action_three(self):
        state = d275.D275OperatorPromptState()
        delegate = mock.Mock()
        delegate.wait_event = mock.Mock(return_value=b"frame")
        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            es = d275.D275OperatorPromptingEventSource(
                delegate, state=state, simulation=True
            )
            es.wait_event(FIRST_IMAGE_IRQ2_TIMEOUT_MS)
            es.wait_event(FIRST_IMAGE_IRQ2_TIMEOUT_MS)
            state.show_failure(simulation=True)
        err = stderr.getvalue()
        self.assertIn("D275 — AZIONE OPERATORE 1/3", err)
        self.assertIn("D275 — AZIONE OPERATORE 2/3", err)
        self.assertIn("D275 — TEST INTERROTTO", err)
        self.assertNotIn("D275 — AZIONE OPERATORE 3/3", err)
        self.assertNotIn("D275 — TEST COMPLETATO", err)

    def test_failure_block_is_single_shot(self):
        state = d275.D275OperatorPromptState()
        delegate = mock.Mock()
        delegate.wait_event = mock.Mock(side_effect=RuntimeError("boom"))
        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            es = d275.D275OperatorPromptingEventSource(
                delegate, state=state, simulation=True
            )
            for _ in range(2):
                with self.assertRaises(RuntimeError):
                    es.wait_event(FIRST_IMAGE_IRQ2_TIMEOUT_MS)
        self.assertEqual(stderr.getvalue().count("TEST INTERROTTO"), 1)


if __name__ == "__main__":
    unittest.main()
