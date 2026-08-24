# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline closure for the D266/03 D267 one-shot authority corrective."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import inspect
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import core.d267_first_image_operator as d267
import core.future_first_image_operator as d265_operator
import core.live_capability as capability
from core.fdt_lifecycle import COMMAND_TIMEOUT_MS
from core.post_d4 import build_finger_image, parse_outer, parse_payload
from core.runtime_transport import SubmissionMode, operational_fdt_a0_policy
from core.usb_runtime import LibusbRuntimeTransport, _RouterEventSource
import tools.d267_live_first_image_once as tool
import tests.test_d266_irq_event_router as router_test_support


REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "operator_kit/d267-first-image-once.sh"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (str(LAUNCHER), *args),
        cwd=cwd or REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *args),
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _git_fixture(root: Path) -> tuple[Path, str]:
    repo = root / "repo"
    repo.mkdir()
    subprocess.run(("git", "init", "-q"), cwd=repo, check=True)
    subprocess.run(
        ("git", "config", "user.email", "offline@example.invalid"),
        cwd=repo,
        check=True,
    )
    subprocess.run(
        ("git", "config", "user.name", "Offline"), cwd=repo, check=True
    )
    for relative in d267.D267_FIRST_IMAGE_LIVE_CRITICAL_PATHS:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((relative + "\n").encode())
    subprocess.run(("git", "add", "."), cwd=repo, check=True)
    subprocess.run(("git", "commit", "-qm", "approved"), cwd=repo, check=True)
    sha = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=repo, text=True
    ).strip()
    return repo, sha


class D267LauncherTests(unittest.TestCase):
    def test_dry_run_from_external_cwd_has_zero_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = _run("--dry-run", cwd=Path(temporary))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["D267_OPERATOR_DRY_RUN"], "PASS")
        self.assertEqual(report["OUTCOME"], "PASS_OFFLINE_OPERATOR_KIT")
        for key in (
            "REAL_USB_ACCESS_COUNT",
            "REAL_SECRET_READ_COUNT",
            "REAL_DEVICE_COMMAND_COUNT",
            "MARKER_MUTATION_COUNT",
            "FPRINTD_MUTATION_COUNT",
            "PERSISTENT_DEVICE_WRITE_COUNT",
            "LIVE_TLS_HANDSHAKE_COUNT",
        ):
            self.assertEqual(report[key], 0, key)
        self.assertFalse(report["approved_baseline_value_consumed"])
        self.assertFalse(report["live_capability_reachable"])

    def test_default_wrong_old_and_multiple_flags_are_hard_disabled(self) -> None:
        cases = (
            (),
            ("wrong",),
            ("--dry-run", "extra"),
            (tool.LIVE_FLAG, "extra"),
            ("--i-authorize-one-d265-first-image-live-attempt",),
            (capability.D265_FUTURE_LIVE_AUTHORIZATION_FLAG,),
            (capability.D261_LIVE_AUTHORIZATION_FLAG,),
        )
        for args in cases:
            with self.subTest(args=args):
                result = _run(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("HARD_DISABLED_DEFAULT", result.stderr)

    def test_full_lowercase_sha_is_required_before_production_dependencies(self) -> None:
        values = ("", "a" * 39, "A" * 40, "g" * 40, "HEAD", "main")
        for value in values:
            with self.subTest(value=value):
                build = mock.Mock()
                verify = mock.Mock()
                output = io.StringIO()
                with mock.patch.dict(
                    os.environ, {tool.APPROVED_BASELINE_ENV: value}, clear=False
                ), mock.patch.object(
                    tool.D267ProductionDependencies, "build", build
                ), mock.patch.object(
                    tool, "verify_d267_authoritative_baseline", verify
                ), redirect_stdout(output):
                    self.assertEqual(tool.main([tool.LIVE_FLAG]), 1)
                build.assert_not_called()
                verify.assert_not_called()


class D267BaselineAuthorityTests(unittest.TestCase):
    def test_approved_head_clean_exact_bytes_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, sha = _git_fixture(Path(temporary))
            d267.verify_d267_authoritative_baseline(repo, sha)

    def test_head_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, approved = _git_fixture(Path(temporary))
            (repo / "noncritical").write_text("next\n")
            subprocess.run(("git", "add", "noncritical"), cwd=repo, check=True)
            subprocess.run(
                ("git", "commit", "-qm", "next"), cwd=repo, check=True
            )
            with self.assertRaisesRegex(
                d267.D267OperatorFailure, "baseline_head_mismatch"
            ):
                d267.verify_d267_authoritative_baseline(repo, approved)

    def test_dirty_worktree_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, sha = _git_fixture(Path(temporary))
            (repo / "untracked").write_text("dirty\n")
            with self.assertRaisesRegex(
                d267.D267OperatorFailure, "baseline_worktree_dirty"
            ):
                d267.verify_d267_authoritative_baseline(repo, sha)

    def test_authoritative_path_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, sha = _git_fixture(Path(temporary))
            drifted = d267.D267_FIRST_IMAGE_LIVE_CRITICAL_PATHS[:-1]
            with self.assertRaisesRegex(
                d267.D267OperatorFailure, "authoritative_path_set_mismatch"
            ):
                d267.verify_d267_authoritative_baseline(repo, sha, drifted)

    def test_single_byte_drift_in_each_critical_class_fails_closed(self) -> None:
        representatives = (
            "operator_kit/d267-first-image-once.sh",
            "tools/d267_live_first_image_once.py",
            "core/live_capability.py",
            "core/d267_first_image_operator.py",
            "core/usb_runtime.py",
            "core/persistent_runtime.py",
            "core/post_d4.py",
            "core/protected_runtime.py",
            "core/runtime_transport.py",
            "core/tls_b0.py",
            "poc/goodix5125/tools/binding_reference/runtime.py",
            "tools/d261_live_fdt_arm_once.py",
        )
        for relative in representatives:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                repo, sha = _git_fixture(Path(temporary))
                subprocess.run(
                    ("git", "update-index", "--assume-unchanged", relative),
                    cwd=repo,
                    check=True,
                )
                path = repo / relative
                value = bytearray(path.read_bytes())
                value[0] ^= 1
                path.write_bytes(value)
                self.assertEqual(_git(repo, "status", "--porcelain").stdout, "")
                with self.assertRaisesRegex(
                    d267.D267OperatorFailure, "live_critical_byte_mismatch"
                ):
                    d267.verify_d267_authoritative_baseline(repo, sha)

    def test_manifest_is_exact_and_router_hash_is_post_d266(self) -> None:
        document = json.loads(
            (REPO / "analysis/D266/D266_03_live_critical_manifest.json").read_text()
        )
        paths = tuple(row["path"] for row in document["live_critical_files"])
        self.assertEqual(paths, d267.D267_FIRST_IMAGE_LIVE_CRITICAL_PATHS)
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(document["live_critical_file_count"], len(paths))
        self.assertFalse(document["baseline_approved"])
        rows = {row["path"]: row for row in document["live_critical_files"]}
        expected_router = "c4e62b0786d7710eb0625b033258636597b9aa8f40259ce5a1f669b0e160385b"
        self.assertEqual(rows["core/usb_runtime.py"]["sha256"], expected_router)
        self.assertEqual(
            hashlib.sha256((REPO / "core/usb_runtime.py").read_bytes()).hexdigest(),
            expected_router,
        )
        for relative, row in rows.items():
            actual = hashlib.sha256((REPO / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, row["sha256"], relative)


class D267CapabilityNamespaceTests(unittest.TestCase):
    def test_namespaces_are_distinct_from_d261_and_d265(self) -> None:
        self.assertNotEqual(d267.D267_SINGLE_USE_MARKER_PATH, d267.D261_MARKER_PATH)
        self.assertNotEqual(d267.D267_SINGLE_USE_MARKER_PATH, d267.D265_MARKER_PATH)
        self.assertNotEqual(d267.D267_REPORT_PATH, d265_operator.D265_FUTURE_REPORT_PATH)
        self.assertNotEqual(tool.LIVE_FLAG, "--i-authorize-one-d265-first-image-live-attempt")
        self.assertNotEqual(tool.LIVE_FLAG, capability.D265_FUTURE_LIVE_AUTHORIZATION_FLAG)
        self.assertNotEqual(tool.LIVE_FLAG, capability.D261_LIVE_AUTHORIZATION_FLAG)

    def test_d265_intent_cannot_mint_d267_marker_or_live_io(self) -> None:
        old = capability.issue_future_intent(
            capability.D265_FUTURE_LIVE_AUTHORIZATION_FLAG
        )
        capability.consume_future_intent(old)
        with self.assertRaises(capability.CapabilityFailure):
            capability._issue_d267_marker_after_durable_claim(old)
        with self.assertRaises(capability.CapabilityFailure):
            capability.issue_d267_live_io(old)

    def test_d267_intent_cannot_mint_d265_marker_or_live_io(self) -> None:
        new = capability.issue_d267_intent(capability.D267_LIVE_AUTHORIZATION_FLAG)
        capability.consume_d267_intent(new)
        with self.assertRaises(capability.CapabilityFailure):
            capability._issue_future_marker_after_durable_claim(new)
        with self.assertRaises(capability.CapabilityFailure):
            capability.issue_future_live_io(new)

    def test_live_io_requires_durable_claim_and_marker_capability_is_one_shot(self) -> None:
        intent = capability.issue_d267_intent(capability.D267_LIVE_AUTHORIZATION_FLAG)
        with self.assertRaises(capability.CapabilityFailure):
            capability.issue_d267_live_io(intent)
        capability.consume_d267_intent(intent)
        with tempfile.TemporaryDirectory() as temporary, mock.patch(
            "core.d267_first_image_operator.os.fsync", wraps=os.fsync
        ) as fsync:
            marker = d267.claim_d267_marker(
                Path(temporary) / "d267.marker", "a" * 40, intent
            )
            fsync.assert_called_once()
        live = capability.issue_d267_live_io(marker)
        capability.require_known_live_io_capability(live)
        with self.assertRaisesRegex(
            capability.CapabilityFailure, "already_used"
        ):
            capability.issue_d267_live_io(marker)

    def test_d267_marker_rejects_historical_namespace(self) -> None:
        for path in (d267.D261_MARKER_PATH, d267.D265_MARKER_PATH):
            with self.subTest(path=path):
                intent = capability.issue_d267_intent(
                    capability.D267_LIVE_AUTHORIZATION_FLAG
                )
                capability.consume_d267_intent(intent)
                with self.assertRaisesRegex(
                    d267.D267OperatorFailure, "historical_marker_namespace"
                ):
                    d267.claim_d267_marker(path, "a" * 40, intent)


class D267ProductionPathTests(unittest.TestCase):
    def _live_capability(self, directory: Path) -> capability.D267LiveIoCapability:
        intent = capability.issue_d267_intent(capability.D267_LIVE_AUTHORIZATION_FLAG)
        capability.consume_d267_intent(intent)
        marker = d267.claim_d267_marker(directory / "marker", "a" * 40, intent)
        return capability.issue_d267_live_io(marker)

    def test_concrete_graph_uses_one_router_event_source_and_coordinator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            live = self._live_capability(Path(temporary))
            backend = SimpleNamespace()
            secret = SimpleNamespace()
            target = {"material": SimpleNamespace()}
            with mock.patch(
                "core.usb_runtime.CtypesLibusbBackend", return_value=backend
            ):
                coordinator = d267.D267ProductionDependencies.construct_runtime(
                    live, secret, target
                )
        self.assertIsInstance(coordinator.transport, LibusbRuntimeTransport)
        self.assertIs(coordinator.transport.backend, backend)
        self.assertIsInstance(coordinator.event_source, _RouterEventSource)
        self.assertIs(coordinator.event_source.router, coordinator.transport.router)
        source = inspect.getsource(d267.D267ProductionDependencies.construct_runtime)
        self.assertIn("LibusbRuntimeTransport", source)
        self.assertIn("transport.event_source", source)
        self.assertNotIn("ScriptedEventSource", source)

    def test_orchestration_claims_marker_before_live_io_and_selects_first_image(self) -> None:
        events: list[str] = []
        run_kwargs: dict[str, object] = {}

        class Secret:
            def close(self) -> None:
                events.append("outer_secret_close")

        class Coordinator:
            def run(self, **kwargs: object) -> SimpleNamespace:
                events.append("run")
                run_kwargs.update(kwargs)
                return SimpleNamespace(command_trace=(), first_image_raster_shape=None)

            def audit(self) -> dict[str, object]:
                return {"retry_count": 0, "persistent_device_write_count": 0}

        intent = capability.issue_d267_intent(capability.D267_LIVE_AUTHORIZATION_FLAG)
        with tempfile.TemporaryDirectory() as temporary:
            marker_path = Path(temporary) / "marker"

            def claim(sha: str, token: capability.D267IntentCapability):
                events.append("durable_marker_claim")
                return d267.claim_d267_marker(marker_path, sha, token)

            def construct(live: object, secret: object, target: object) -> Coordinator:
                capability.require_known_live_io_capability(live)
                self.assertTrue(marker_path.is_file())
                events.append("live_io_then_construct")
                return Coordinator()

            no_arg = lambda: None
            dependencies = d267.D267OperatorDependencies(
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
                observe_live_io_issue=lambda: events.append("live_io_issued"),
                construct_coordinator=construct,
                restore_signals=no_arg,
                restore_fprintd=no_arg,
                publish_report=lambda _report: None,
            )
            with mock.patch.object(d267, "verify_d267_authoritative_baseline"):
                report = d267.run_d267_first_image_candidate(
                    intent,
                    dependencies,
                    repo=REPO,
                    approved_baseline_sha="a" * 40,
                    ts16=1,
                )
        self.assertEqual(report["result"], "PASS_STOP_AFTER_FIRST_IMAGE")
        self.assertLess(
            events.index("durable_marker_claim"), events.index("live_io_issued")
        )
        self.assertLess(events.index("live_io_issued"), events.index("run"))
        self.assertEqual(
            run_kwargs["terminal_mode"],
            d267.TerminalBoundary.STOP_AFTER_FIRST_IMAGE,
        )

    def test_prompt_is_exactly_once_immediately_before_15000ms_wait(self) -> None:
        events: list[tuple[str, int]] = []

        class Delegate:
            def wait_event(self, timeout_ms: int) -> bytes:
                events.append(("wait", timeout_ms))
                return b"frame"

        tracker = tool.PhaseTracker()
        wrapped = tool.PromptingEventSource(Delegate(), tracker)
        output = io.StringIO()
        with redirect_stdout(output):
            wrapped.wait_event(500)
            self.assertNotIn("APPOGGIA_UN_DITO_ORA", output.getvalue())
            wrapped.wait_event(15000)
            wrapped.wait_event(15000)
        self.assertEqual(
            output.getvalue().count("D267_OPERATOR_ACTION = APPOGGIA_UN_DITO_ORA"),
            1,
        )
        self.assertEqual(events, [("wait", 500), ("wait", 15000), ("wait", 15000)])
        self.assertEqual(tracker.operator_prompt_count, 1)

    def test_without_irq2_zero_0x22_attempts_and_no_bypass(self) -> None:
        backend = router_test_support._BulkInFixture([])
        case = router_test_support.ConcreteRouterFirstImageSeamTests()
        coordinator, transport, router = case._coordinator(backend, [])
        tracker = tool.PhaseTracker(coordinator=coordinator)
        coordinator.event_source = tool.PromptingEventSource(
            coordinator.event_source, tracker
        )
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(
            TimeoutError, "synthetic_bulk_in_timeout"
        ):
            coordinator._run_first_image_terminal()
        self.assertEqual(transport.requests, [])
        self.assertEqual(coordinator.lifecycle.image_command_attempt_count, 0)
        self.assertEqual(router.event_delivery_count, 0)
        self.assertEqual(coordinator.retry_count, 0)
        self.assertEqual(coordinator.lifecycle.persistent_write_family_count, 0)

    def test_irq2_reaches_one_fixed64_0x22_without_retry_recovery_or_reopen(self) -> None:
        backend = router_test_support._BulkInFixture(
            [router_test_support._event(0x32, 2)]
        )
        case = router_test_support.ConcreteRouterFirstImageSeamTests()
        coordinator, transport, router = case._coordinator(
            backend,
            [router_test_support._ack(0x22), router_test_support._first_image_b0()],
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
        self.assertEqual(physical[0][: len(build_finger_image())], build_finger_image())
        self.assertFalse(any(physical[0][len(build_finger_image()) :]))
        self.assertEqual(router.event_delivery_count, 1)
        self.assertEqual(coordinator.retry_count, 0)
        self.assertEqual(coordinator.lifecycle.persistent_write_family_count, 0)
        self.assertFalse(hasattr(coordinator, "reopen"))
        self.assertFalse(hasattr(coordinator, "recover"))

    def test_summary_and_report_surface_exclude_sensitive_payloads(self) -> None:
        audit = {
            "usb_transport_session_count": 1,
            "transport_cleanup_count": 1,
            "tls_server_session_object_count": 1,
            "tls_server_handshake_count": 1,
            "retry_count": 0,
            "persistent_device_write_count": 0,
            "secret_boundary_zeroized": True,
            "a2_special_recovery_count": 0,
            "0x70_special_recovery_count": 0,
            "exact_fdt_command_trace": [
                "0x36", "0x50", "0x36", "0x82", "0x20", "0x36", "0x32", "0x22"
            ],
            "first_image_irq2_observed_count": 1,
            "image_command_attempt_count": 1,
            "first_image_ack_validation_count": 1,
            "first_image_b0_count": 1,
            "first_image_received": True,
            "cleanup_failures": [],
        }
        coordinator = SimpleNamespace(
            audit=lambda: audit,
            transport=SimpleNamespace(backend=SimpleNamespace(open_count=1)),
        )
        summary = tool._summary(
            "a" * 40,
            {
                "result": "PASS_STOP_AFTER_FIRST_IMAGE",
                "first_image_raster_shape": [80, 64],
            },
            tool.PhaseTracker(1, 1, 1, 1, 1, coordinator),
        )
        serialized = json.dumps(summary).lower()
        for forbidden in (
            "psk",
            "raster_bytes",
            "pixel_samples",
            "biometric_payload",
            "plaintext",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(summary["FIRST_IMAGE_RASTER_SHAPE"], [80, 64])
        self.assertEqual(summary["RETRY_COUNT"], 0)
        self.assertEqual(summary["RECOVERY_COUNT"], 0)
        self.assertTrue(summary["SECRET_ZEROIZED"])


class D265HistoricalImmutabilityTests(unittest.TestCase):
    def test_historical_d265_authority_and_operator_are_unchanged(self) -> None:
        expected = {
            "analysis/D265/D265_01_live_critical_manifest.json":
                "c1cb60cce1deb9a43008c3adf6f8e179df1f01fb6aabd3318a6374d8630dc673",
            "operator_kit/d265-first-image-once.sh":
                "d4f49fc2699790984175e5feea505f712194ebce2a4baac30715e57e9dd70bf6",
            "tools/d265_live_first_image_once.py":
                "f5501cf1d90bb5b2b873c7a22f8d41b4db23c6b96bffd2ce1243b71665dab1e4",
        }
        for relative, digest in expected.items():
            with self.subTest(relative=relative):
                self.assertEqual(
                    hashlib.sha256((REPO / relative).read_bytes()).hexdigest(), digest
                )
                diff = subprocess.run(
                    ("git", "diff", "--exit-code", "HEAD", "--", relative),
                    cwd=REPO,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(diff.returncode, 0)


if __name__ == "__main__":
    unittest.main()
