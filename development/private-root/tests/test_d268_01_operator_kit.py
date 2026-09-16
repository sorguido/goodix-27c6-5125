# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline closure for the D268/01 first-image Operator Kit."""

from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import core.d268_first_image_operator as d268
import core.live_capability as capability
from core.fdt_lifecycle import COMMAND_TIMEOUT_MS
from core.post_d4 import build_finger_image, parse_outer, parse_payload
from core.runtime_transport import SubmissionMode, operational_fdt_a0_policy
import tests.test_d266_irq_event_router as router_support
import tools.d268_live_first_image_once as tool


REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "operator_kit/d268-first-image-once.sh"
HISTORICAL_MANIFEST = REPO / "analysis/D267/D267_03_live_critical_manifest.json"
CURRENT_MANIFEST = REPO / "analysis/D268/D268_01_live_critical_manifest.json"


class D268RepositoryAndDryRunTests(unittest.TestCase):
    def test_d267_03_manifest_is_byte_identical_to_required_commit(self) -> None:
        expected = subprocess.run(
            (
                "git",
                "show",
                "42af60107cf21eb610de867a6de05b774ec1e37f:"
                "analysis/D267/D267_03_live_critical_manifest.json",
            ),
            cwd=REPO,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        self.assertEqual(HISTORICAL_MANIFEST.read_bytes(), expected)

    def test_current_manifest_is_exact_unapproved_and_uses_current_decoder(self) -> None:
        document = json.loads(CURRENT_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], "D268_01_LIVE_CRITICAL_MANIFEST_V1")
        self.assertFalse(document["baseline_approved"])
        self.assertFalse(document["live_authorized"])
        self.assertFalse(document["ready_for_live"])
        paths = tuple(row["path"] for row in document["live_critical_files"])
        self.assertEqual(paths, d268.D268_FIRST_IMAGE_LIVE_CRITICAL_PATHS)
        self.assertEqual(document["live_critical_file_count"], len(paths))
        rows = {row["path"]: row for row in document["live_critical_files"]}
        self.assertEqual(
            rows["core/post_d4.py"]["sha256"],
            hashlib.sha256((REPO / "core/post_d4.py").read_bytes()).hexdigest(),
        )
        for relative, row in rows.items():
            self.assertEqual(
                hashlib.sha256((REPO / relative).read_bytes()).hexdigest(),
                row["sha256"],
            )

    def test_launcher_dry_run_is_cwd_independent_and_side_effect_free(self) -> None:
        for cwd in (REPO, Path("/tmp")):
            completed = subprocess.run(
                (str(LAUNCHER), "--dry-run"),
                cwd=cwd,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            report = json.loads(completed.stdout)
            self.assertEqual(report["D268_OPERATOR_DRY_RUN"], "PASS")
            for key in (
                "REAL_USB_ACCESS_COUNT",
                "REAL_SECRET_READ_COUNT",
                "REAL_DEVICE_COMMAND_COUNT",
                "MARKER_MUTATION_COUNT",
                "FPRINTD_MUTATION_COUNT",
                "PERSISTENT_DEVICE_WRITE_COUNT",
                "LIVE_TLS_HANDSHAKE_COUNT",
            ):
                self.assertEqual(report[key], 0)
            self.assertFalse(report["BASELINE_APPROVED"])
            self.assertFalse(report["LIVE_AUTHORIZED"])
            self.assertFalse(report["READY_FOR_LIVE"])

    def test_launcher_syntax_and_import_are_inert(self) -> None:
        subprocess.run(("bash", "-n", str(LAUNCHER)), check=True)
        completed = subprocess.run(
            (
                "python3",
                "-c",
                "import core.d268_first_image_operator; "
                "import tools.d268_live_first_image_once; print('IMPORT_OK')",
            ),
            cwd=REPO,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(completed.stdout.strip(), "IMPORT_OK")
        self.assertEqual(completed.stderr, "")

    def test_live_and_unknown_flags_fail_before_any_side_effect(self) -> None:
        environment = os.environ.copy()
        environment.pop(tool.APPROVED_BASELINE_ENV, None)
        live = subprocess.run(
            (str(LAUNCHER), capability.D268_LIVE_AUTHORIZATION_FLAG),
            cwd=REPO,
            env=environment,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(live.returncode, 1)
        report = json.loads(live.stdout)
        self.assertIn("Live non autorizzato", report["MESSAGGIO_OPERATORE"])
        for key, value in tool._zero_side_effects().items():
            self.assertEqual(report[key], value)
        unknown = subprocess.run(
            (str(LAUNCHER), "--flag-non-valido"),
            cwd=REPO,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("BLOCCATO", unknown.stderr)

    def test_full_lowercase_sha_is_mandatory_and_dirty_tree_fails_closed(self) -> None:
        for invalid in ("", "a" * 39, "A" * 40, "g" * 40):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(
                    d268.D268OperatorFailure, "full_sha_required"
                ):
                    d268.validate_full_sha(invalid)
        head = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=REPO,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        with self.assertRaisesRegex(
            d268.D268OperatorFailure, "worktree_dirty"
        ):
            d268.verify_d268_authoritative_baseline(REPO, head)


class D268NamespaceAndAuthorityTests(unittest.TestCase):
    def test_d268_namespace_is_distinct_from_d267(self) -> None:
        self.assertNotEqual(
            capability.D268_LIVE_AUTHORIZATION_FLAG,
            capability.D267_LIVE_AUTHORIZATION_FLAG,
        )
        self.assertNotIn("d267", str(d268.D268_SINGLE_USE_MARKER_PATH).lower())
        self.assertNotIn("d267", str(d268.D268_REPORT_PATH).lower())
        self.assertNotEqual(
            d268.D268_SINGLE_USE_MARKER_PATH,
            Path("/var/lib/goodix-5125-poc/d267-first-image-single-use.marker"),
        )

    def test_d267_capabilities_cannot_mint_d268_authority(self) -> None:
        old = capability.issue_d267_intent(capability.D267_LIVE_AUTHORIZATION_FLAG)
        capability.consume_d267_intent(old)
        with self.assertRaises(capability.CapabilityFailure):
            capability._issue_d268_marker_after_durable_claim(old)
        with self.assertRaises(capability.CapabilityFailure):
            capability.issue_d268_live_io(old)

    def test_d268_marker_is_durable_and_cannot_reuse_historical_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            intent = capability.issue_d268_intent(
                capability.D268_LIVE_AUTHORIZATION_FLAG
            )
            capability.consume_d268_intent(intent)
            marker_path = Path(temporary) / "d268.marker"
            with mock.patch(
                "core.d268_first_image_operator.os.fsync", wraps=os.fsync
            ) as fsync:
                marker = d268.claim_d268_marker(marker_path, "a" * 40, intent)
            fsync.assert_called_once()
            document = json.loads(marker_path.read_text(encoding="utf-8"))
            self.assertEqual(document["schema"], "D268_FIRST_IMAGE_SINGLE_USE_MARKER_V1")
            live = capability.issue_d268_live_io(marker)
            capability.require_known_live_io_capability(live)
        for path in d268.HISTORICAL_MARKER_PATHS:
            intent = capability.issue_d268_intent(
                capability.D268_LIVE_AUTHORIZATION_FLAG
            )
            capability.consume_d268_intent(intent)
            with self.assertRaisesRegex(
                d268.D268OperatorFailure, "historical_marker_namespace"
            ):
                d268.claim_d268_marker(path, "a" * 40, intent)

    def test_authority_contains_full_real_call_graph_and_no_historical_launcher(self) -> None:
        paths = d268.D268_FIRST_IMAGE_LIVE_CRITICAL_PATHS
        required = {
            "operator_kit/d268-first-image-once.sh",
            "tools/d268_live_first_image_once.py",
            "core/d268_first_image_operator.py",
            "core/live_capability.py",
            "core/persistent_runtime.py",
            "core/post_d4.py",
            "core/usb_runtime.py",
            "tools/d261_live_fdt_arm_once.py",
        }
        self.assertTrue(required.issubset(paths))
        self.assertNotIn("operator_kit/d267-first-image-once.sh", paths)
        self.assertNotIn("tools/d267_live_first_image_once.py", paths)
        self.assertEqual(len(paths), len(set(paths)))


class D268BoundaryAndDiagnosticTests(unittest.TestCase):
    def test_irq2_causes_exactly_one_0x22_and_zero_retry_recovery_reopen(self) -> None:
        backend = router_support._BulkInFixture([router_support._event(0x32, 2)])
        case = router_support.ConcreteRouterFirstImageSeamTests()
        coordinator, transport, router = case._coordinator(
            backend, [router_support._ack(0x22), router_support._first_image_b0()]
        )
        coordinator.operational_physical_policy = True
        tracker = tool.PhaseTracker(coordinator=coordinator)
        coordinator.event_source = tool.PromptingEventSource(
            coordinator.event_source, tracker
        )
        with redirect_stdout(io.StringIO()):
            result = coordinator._run_first_image_terminal()
        self.assertEqual(result["image_command_attempt_count"], 1)
        self.assertEqual(len(transport.requests), 1)
        kind, payload = parse_outer(transport.requests[0])
        control, data = parse_payload(payload)
        self.assertEqual((kind, control, data), (0xA0, 0x22, b"\x01\x00"))
        policy = operational_fdt_a0_policy(0x22, COMMAND_TIMEOUT_MS[0x22])
        physical = policy.materialize(build_finger_image())
        self.assertEqual(policy.mode, SubmissionMode.FIXED64_ZERO_TAIL)
        self.assertEqual(len(physical), 1)
        self.assertEqual(len(physical[0]), 64)
        self.assertEqual(router.event_delivery_count, 1)
        self.assertEqual(coordinator.retry_count, 0)
        self.assertEqual(coordinator.lifecycle.persistent_write_family_count, 0)
        self.assertFalse(hasattr(coordinator, "reopen"))
        self.assertFalse(hasattr(coordinator, "recover"))

    def test_candidate_selects_terminal_first_image_and_claims_before_live_io(self) -> None:
        events: list[str] = []
        run_kwargs: dict[str, object] = {}

        class Secret:
            def close(self) -> None:
                events.append("secret_close")

        class Coordinator:
            def run(self, **kwargs: object) -> SimpleNamespace:
                events.append("run")
                run_kwargs.update(kwargs)
                return SimpleNamespace(command_trace=(), first_image_raster_shape=None)

            def audit(self) -> dict[str, object]:
                return {"retry_count": 0, "persistent_device_write_count": 0}

        intent = capability.issue_d268_intent(capability.D268_LIVE_AUTHORIZATION_FLAG)
        with tempfile.TemporaryDirectory() as temporary:
            marker_path = Path(temporary) / "marker"

            def claim(sha: str, token: capability.D268IntentCapability):
                events.append("marker")
                return d268.claim_d268_marker(marker_path, sha, token)

            def construct(live: object, _secret: object, _target: object) -> Coordinator:
                capability.require_known_live_io_capability(live)
                self.assertTrue(marker_path.is_file())
                events.append("construct")
                return Coordinator()

            no_arg = lambda: None
            dependencies = d268.D268OperatorDependencies(
                observe_baseline_verified=no_arg,
                require_operator_context=no_arg,
                require_safe_directories=no_arg,
                verify_protected_metadata=no_arg,
                verify_gfusb_hash=no_arg,
                resolve_exact_target=lambda: object(),
                stop_fprintd=no_arg,
                block_signals=no_arg,
                require_no_holders=lambda _target: None,
                validate_non_secret_material=no_arg,
                require_marker_absent=no_arg,
                materialize_secret_once=Secret,
                claim_marker_once=claim,
                observe_live_io_issue=lambda: events.append("live_io"),
                construct_coordinator=construct,
                restore_signals=no_arg,
                restore_fprintd=no_arg,
                publish_report=lambda _report: None,
            )
            with mock.patch.object(d268, "verify_d268_authoritative_baseline"):
                report = d268.run_d268_first_image_candidate(
                    intent,
                    dependencies,
                    repo=REPO,
                    approved_baseline_sha="a" * 40,
                    ts16=1,
                )
        self.assertEqual(report["result"], "PASS_STOP_AFTER_FIRST_IMAGE")
        self.assertLess(events.index("marker"), events.index("live_io"))
        self.assertLess(events.index("live_io"), events.index("run"))
        self.assertEqual(
            run_kwargs["terminal_mode"], d268.TerminalBoundary.STOP_AFTER_FIRST_IMAGE
        )

    def test_summary_exposes_typed_sanitized_diagnostic_without_payload(self) -> None:
        diagnostic = {
            "decode_stage": "image_record_crc",
            "plaintext_length": 7693,
            "declared_payload_length": 7690,
            "control_or_major_class": "MAJOR_0X2",
            "is_pov_notification": False,
            "payload_trailer_class": "0X88",
            "payload_checksum_match": False,
            "payload_checksum_policy": "NO_CHECK_0X88_ACCEPTED",
            "image_record_length": 7684,
            "image_record_crc_match": False,
            "exception_class": "ImageCrcError",
            "raster_shape_if_success": None,
        }
        audit = {
            "first_image_decode_diagnostic": diagnostic,
            "retry_count": 0,
            "persistent_device_write_count": 0,
            "exact_fdt_command_trace": [],
        }
        summary = tool._summary(
            "a" * 40,
            {"result": "FAIL_CLOSED", "runtime_audit": audit},
        )
        self.assertEqual(summary["FIRST_IMAGE_DECODE_STATUS"], "DECODE_FAILED")
        self.assertEqual(summary["FIRST_IMAGE_DECODE_STAGE"], "image_record_crc")
        self.assertEqual(summary["FIRST_IMAGE_DECODE_EXCEPTION"], "ImageCrcError")
        self.assertEqual(summary["FIRST_IMAGE_PAYLOAD_TRAILER_CLASS"], "0X88")
        self.assertEqual(
            summary["FIRST_IMAGE_PAYLOAD_CHECKSUM_POLICY"],
            "NO_CHECK_0X88_ACCEPTED",
        )
        self.assertFalse(summary["FIRST_IMAGE_PAYLOAD_CHECKSUM_MATCH"])
        self.assertFalse(summary["FIRST_IMAGE_RECORD_CRC_MATCH"])
        serialized = json.dumps(summary).lower()
        for forbidden in (
            "b0_raw",
            "tls_plaintext",
            "image_bytes",
            "pixel_samples",
            "biometric_payload",
            "psk",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_operator_prompts_and_failure_messages_are_italian(self) -> None:
        class Delegate:
            def wait_event(self, _timeout_ms: int) -> bytes:
                return b"frame"

        output = io.StringIO()
        tracker = tool.PhaseTracker()
        with redirect_stdout(output):
            wrapped = tool.PromptingEventSource(Delegate(), tracker)
            wrapped.wait_event(15000)
            wrapped.wait_event(15000)
        rendered = output.getvalue()
        self.assertIn("Tieni il dito lontano", rendered)
        self.assertIn("appoggia UN SOLO dito", rendered)
        self.assertIn("NON riprovare", rendered)
        self.assertEqual(rendered.count("APPOGGIA_UN_DITO_ORA"), 1)
        shell = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("BLOCCATO", shell)
        self.assertNotIn("D267", shell + rendered)


if __name__ == "__main__":
    unittest.main()
