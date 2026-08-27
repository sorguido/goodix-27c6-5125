# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline D275/02 corrective gates: authority, report, marker, leakage."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from core.persistent_runtime import TerminalBoundary
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


if __name__ == "__main__":
    unittest.main()
