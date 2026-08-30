# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from goodix_orchestrator.engine import DeterministicEngine
from goodix_orchestrator.persistence import OperatorStateRecord, SCHEMA_VERSION, SQLiteStateStore
from goodix_orchestrator.policy import Capability, CapabilityPolicy
from goodix_orchestrator.protocols import Disposition, PMDisposition, PROTOCOL_VERSION, PauseReason
from goodix_orchestrator.service import (
    GitSnapshot,
    OperatorController,
    ReprobeController,
    RuntimePaths,
    ServiceError,
    SingleInstanceLock,
    redact,
)

from tests.common import executor_result, task_manifest


class FakeProbe:
    def __init__(self, available: bool, classification: str = "TEST") -> None:
        self.available = available
        self.classification = classification
        self.count = 0

    def probe_exact_route(self):
        self.count += 1
        return self.available, self.classification


class O003ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = SQLiteStateStore(self.root / "state.sqlite")
        self.store.initialize()
        self.snap = GitSnapshot("a" * 40, "b" * 40)
        self.ancestors = {("b" * 40, "c" * 40), ("b" * 40, "d" * 40)}
        self.controller = OperatorController(
            self.store,
            snapshot=lambda: self.snap,
            is_ancestor=lambda old, new: old == new or (old, new) in self.ancestors,
        )

    def engine_paused(self, reason: PauseReason) -> DeterministicEngine:
        policy = CapabilityPolicy(
            (Capability.HOST_READ, Capability.WORKTREE_WRITE, Capability.TASK_COMMIT)
        )
        engine = DeterministicEngine.create(self.store, policy, run_id="ORCH-O003-SERVICE")
        engine.bootstrap_complete()
        engine.start_planning()
        engine.task_ready(task_manifest())
        engine.start_executor(turn_id="TURN-SERVICE-EXEC")
        engine.complete_executor(executor_result())
        engine.start_review(turn_id="TURN-SERVICE-REVIEW")
        engine.apply_disposition(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-001",
                disposition=Disposition.PAUSE,
                reason="test pause",
                pause_reason=reason,
            )
        )
        return engine

    def test_schema_v4_operator_state_and_bounded_backup(self) -> None:
        self.assertEqual(SCHEMA_VERSION, 4)
        self.store.save_operator_state(OperatorStateRecord(operator_paused=True))
        for _ in range(4):
            self.store.consistent_backup(self.root / "backups", retain=2)
        backups = tuple((self.root / "backups").glob("state-*.sqlite"))
        self.assertLessEqual(len(backups), 2)
        restored = SQLiteStateStore(backups[-1])
        restored.initialize()
        self.assertTrue(restored.load_operator_state().operator_paused)
        effected = self.store.backup_with_effect(
            self.root / "effect-backups",
            effect_id="EFFECT-STATE-BACKUP-TEST",
            retain=2,
        )
        effected_store = SQLiteStateStore(effected)
        effected_store.initialize()
        self.assertEqual(
            effected_store.load_effect("EFFECT-STATE-BACKUP-TEST").status.value,
            "COMPLETED",
        )

    def test_xdg_paths_are_portable(self) -> None:
        paths = RuntimePaths.discover(
            {"HOME": str(self.root), "XDG_CONFIG_HOME": str(self.root / "cfg"), "XDG_STATE_HOME": str(self.root / "state")}
        )
        self.assertEqual(paths.state_db, self.root / "state" / "goodix-orchestrator" / "state.sqlite")
        self.assertNotIn("Repository", str(paths.state_db))

    def test_single_instance_collision(self) -> None:
        first = SingleInstanceLock(self.root / "service.lock")
        second = SingleInstanceLock(self.root / "service.lock")
        first.acquire()
        self.addCleanup(first.release)
        with self.assertRaises(ServiceError) as caught:
            second.acquire()
        self.assertEqual(caught.exception.code, "SINGLE_INSTANCE_COLLISION")

    def test_pause_resume_and_status_quiescence(self) -> None:
        self.controller.pause()
        status = self.controller.status()
        self.assertTrue(status["operator_pause"])
        self.assertTrue(status["NO_INFLIGHT_TURN"])
        self.assertTrue(status["NO_INFLIGHT_EFFECT"])
        self.controller.resume()
        self.assertFalse(self.store.load_operator_state().operator_paused)

    def test_emergency_latch_survives_restart_and_requires_explicit_clear(self) -> None:
        self.controller.emergency_stop()
        restarted = SQLiteStateStore(self.root / "state.sqlite")
        restarted.initialize()
        self.assertTrue(restarted.load_operator_state().emergency_stop_latched)
        with self.assertRaises(ServiceError):
            self.controller.resume()
        self.controller.emergency_clear()
        self.assertFalse(self.store.load_operator_state().emergency_stop_latched)

    def test_maintenance_requires_quiescence_and_remains_paused_on_exit(self) -> None:
        self.store.save_operator_state(OperatorStateRecord(inflight_effect=True))
        with self.assertRaises(ServiceError) as caught:
            self.controller.maintenance_enter("MAINT-O003-A")
        self.assertEqual(caught.exception.code, "MAINTENANCE_ENTRY_DENIED_NOT_QUIESCENT")
        self.store.save_operator_state(OperatorStateRecord())
        epoch = self.controller.maintenance_enter("MAINT-O003-B")
        self.assertEqual(epoch.development_sha, "b" * 40)
        closed = self.controller.maintenance_exit()
        self.assertEqual(closed.reconciliation, "NO_RELEVANT_GIT_CHANGE")
        state = self.store.load_operator_state()
        self.assertTrue(state.operator_paused)
        self.assertIsNone(state.maintenance_id)

    def test_maintenance_ff_development_requires_replan(self) -> None:
        self.controller.maintenance_enter("MAINT-O003-C")
        self.snap = GitSnapshot("a" * 40, "c" * 40)
        closed = self.controller.maintenance_exit()
        self.assertEqual(closed.reconciliation, "DEVELOPMENT_CHANGED_REPLAN_REQUIRED")

    def test_maintenance_divergence_stays_locked(self) -> None:
        self.controller.maintenance_enter("MAINT-O003-D")
        self.snap = GitSnapshot("e" * 40, "f" * 40)
        with self.assertRaises(ServiceError) as caught:
            self.controller.maintenance_exit()
        self.assertEqual(caught.exception.code, "PAUSED_INFRASTRUCTURE")
        self.assertEqual(self.store.load_operator_state().maintenance_id, "MAINT-O003-D")

    def test_rate_limit_reprobe_does_not_advance_when_unavailable(self) -> None:
        engine = self.engine_paused(PauseReason.RATE_LIMIT)
        probe = FakeProbe(False, "RATE_LIMIT_REACHED")
        controller = ReprobeController(self.store, probe, interval_seconds=60)
        dispatches = len(self.store.list_dispatches())
        self.assertFalse(controller.tick(engine, now=datetime.now(UTC)))
        self.assertEqual(engine.state.value, "PAUSED_RATE_LIMIT")
        self.assertEqual(len(self.store.list_dispatches()), dispatches)
        self.assertFalse(controller.tick(engine, now=datetime.now(UTC) + timedelta(seconds=10)))
        self.assertEqual(probe.count, 1)

    def test_model_reprobe_resumes_exact_previous_state_after_reconciliation(self) -> None:
        engine = self.engine_paused(PauseReason.MODEL_UNAVAILABLE)
        probe = FakeProbe(True, "EXACT_ROUTE_AVAILABLE")
        controller = ReprobeController(
            self.store, probe, interval_seconds=60, reconcile=lambda: True
        )
        self.assertTrue(controller.tick(engine, now=datetime.now(UTC)))
        self.assertEqual(engine.state.value, "PM_REVIEWING")

    def test_reprobe_reconciliation_failure_pauses_operator(self) -> None:
        engine = self.engine_paused(PauseReason.RATE_LIMIT)
        controller = ReprobeController(
            self.store, FakeProbe(True), interval_seconds=60, reconcile=lambda: False
        )
        self.assertFalse(controller.tick(engine, now=datetime.now(UTC)))
        self.assertTrue(self.store.load_operator_state().operator_paused)
        self.assertEqual(engine.state.value, "PAUSED_RATE_LIMIT")

    def test_secret_redaction(self) -> None:
        redacted = redact(
            {"token": "ghp_verysecretvalue", "message": "Bearer abcdefghijklmnop", "safe": "ok"}
        )
        self.assertEqual(redacted["token"], "[REDACTED]")
        self.assertEqual(redacted["message"], "[REDACTED]")
        self.assertEqual(redacted["safe"], "ok")


if __name__ == "__main__":
    unittest.main()
