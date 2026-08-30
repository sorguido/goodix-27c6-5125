import tempfile
import unittest
from pathlib import Path

from goodix_orchestrator.engine import DeterministicEngine, EngineError
from goodix_orchestrator.persistence import (
    AmbiguousEffectError,
    EffectKind,
    EffectRequestAction,
    EffectStatus,
    IdempotencyIntentMismatchError,
    ReconciliationOutcome,
    SQLiteStateStore,
    UnsafePersistenceDataError,
)
from goodix_orchestrator.policy import Capability, CapabilityPolicy
from goodix_orchestrator.state import OrchestratorState


class IdempotencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.store = SQLiteStateStore(self.path)
        self.store.initialize()

    def request(self, intent=None):
        return self.store.request_effect(
            effect_id="EFFECT-001",
            idempotency_key="TASK-001:COMMIT:one",
            kind=EffectKind.COMMIT,
            intent=intent or {"task_id": "TASK-001", "tree": "abc"},
        )

    def test_completed_same_identity_skips_duplicate(self) -> None:
        self.assertEqual(self.request().action, EffectRequestAction.EXECUTE)
        self.store.begin_effect("EFFECT-001")
        self.store.complete_effect("EFFECT-001")
        replay = self.request()
        self.assertEqual(replay.action, EffectRequestAction.SKIP_COMPLETED)
        self.assertEqual(replay.record.status, EffectStatus.COMPLETED)

    def test_same_identity_different_intent_fails_closed(self) -> None:
        self.request()
        with self.assertRaises(IdempotencyIntentMismatchError):
            self.request({"task_id": "TASK-001", "tree": "different"})

    def test_crash_before_effect_start_is_recoverable(self) -> None:
        self.request()
        reopened = SQLiteStateStore(self.path)
        reopened.initialize()
        retry = reopened.request_effect(
            effect_id="EFFECT-001",
            idempotency_key="TASK-001:COMMIT:one",
            kind=EffectKind.COMMIT,
            intent={"task_id": "TASK-001", "tree": "abc"},
        )
        self.assertEqual(retry.action, EffectRequestAction.EXECUTE)
        self.assertEqual(retry.record.status, EffectStatus.NOT_STARTED)

    def test_in_progress_requires_explicit_reconciliation(self) -> None:
        self.request()
        self.store.begin_effect("EFFECT-001")
        with self.assertRaises(AmbiguousEffectError):
            self.request()
        recovered = self.store.reconcile_effect(
            "EFFECT-001", ReconciliationOutcome.COMPLETED
        )
        self.assertEqual(recovered.status, EffectStatus.COMPLETED)
        self.assertEqual(self.request().action, EffectRequestAction.SKIP_COMPLETED)

    def test_unknown_external_outcome_locks_engine(self) -> None:
        policy = CapabilityPolicy((Capability.HOST_READ,))
        engine = DeterministicEngine.create(
            self.store, policy, run_id="ORCH-20260830-010"
        )
        engine.bootstrap_complete()
        self.request()
        self.store.begin_effect("EFFECT-001")
        with self.assertRaises(EngineError) as caught:
            engine.reconcile_effect("EFFECT-001", ReconciliationOutcome.UNKNOWN)
        self.assertEqual(caught.exception.code, "AMBIGUOUS_SIDE_EFFECT")
        self.assertEqual(engine.state, OrchestratorState.ERROR_LOCKED)
        self.assertEqual(
            self.store.load_effect("EFFECT-001").status, EffectStatus.AMBIGUOUS
        )

    def test_restart_with_unreconciled_in_progress_effect_locks(self) -> None:
        policy = CapabilityPolicy((Capability.HOST_READ,))
        engine = DeterministicEngine.create(
            self.store, policy, run_id="ORCH-20260830-011"
        )
        engine.bootstrap_complete()
        self.request()
        self.store.begin_effect("EFFECT-001")
        recovered = DeterministicEngine.recover(
            self.path, policy, expected_run_id="ORCH-20260830-011"
        )
        self.assertEqual(recovered.state, OrchestratorState.ERROR_LOCKED)
        self.assertEqual(recovered.error_code, "AMBIGUOUS_SIDE_EFFECT")

    def test_secret_shaped_effect_intent_is_rejected(self) -> None:
        with self.assertRaises(UnsafePersistenceDataError):
            self.request({"task_id": "TASK-001", "auth_token": "must-not-persist"})


if __name__ == "__main__":
    unittest.main()
