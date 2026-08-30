# SPDX-License-Identifier: GPL-2.0-or-later
import tempfile
import unittest
from pathlib import Path

from goodix_orchestrator.engine import DeterministicEngine, EngineError
from goodix_orchestrator.persistence import (
    ContextRecord,
    DispatchRecord,
    GitStateRecord,
    SQLiteStateStore,
    UnsafePersistenceDataError,
)
from goodix_orchestrator.policy import CapabilityPolicy
from goodix_orchestrator.structured_output import ContextClass, RoutingClass


class O002PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteStateStore(Path(self.temp.name) / "state.sqlite3")
        self.store.initialize()

    def context(self, thread_id, context_class, routing_class, model, effort, cwd):
        return ContextRecord(
            thread_id=thread_id,
            context_class=context_class,
            role="AI_EXECUTOR" if context_class is ContextClass.AI_EXECUTOR else "AI_PM",
            effective_model_id=model,
            effective_reasoning_effort=effort,
            routing_class=routing_class,
            cwd=cwd,
            codex_version="codex-cli 0.fixture",
        )

    def test_three_contexts_and_dispatch_counts_persist(self) -> None:
        root = str(Path(self.temp.name).resolve())
        records = (
            self.context(
                "thread-plan", ContextClass.AI_PM_PLAN,
                RoutingClass.AI_PM_PLAN_STANDARD, "gpt-5.6-sol", "medium", root,
            ),
            self.context(
                "thread-review", ContextClass.AI_PM_REVIEW,
                RoutingClass.AI_PM_REVIEW, "gpt-5.6-sol", "high", root,
            ),
            self.context(
                "thread-exec", ContextClass.AI_EXECUTOR,
                RoutingClass.EXEC_BOUNDED_IMPLEMENTATION, "gpt-5.6-terra", "high", root,
            ),
        )
        for record in records:
            self.store.record_context(record)
        self.assertEqual(len(self.store.list_contexts(active_only=True)), 3)
        self.assertEqual(len({item.thread_id for item in self.store.list_contexts()}), 3)
        self.store.record_dispatch(
            DispatchRecord(
                "dispatch-1", "thread-exec", "turn-1", ContextClass.AI_EXECUTOR,
                RoutingClass.EXEC_BOUNDED_IMPLEMENTATION, "gpt-5.6-terra", "high",
                "codex-cli 0.fixture",
            )
        )
        self.store.record_dispatch(
            DispatchRecord(
                "dispatch-2", "thread-exec", "turn-2", ContextClass.AI_EXECUTOR,
                RoutingClass.EXEC_BOUNDED_IMPLEMENTATION, "gpt-5.6-terra", "high",
                "codex-cli 0.fixture", schema_repair=True,
            )
        )
        self.assertEqual(
            self.store.routing_counts(), {"EXEC_BOUNDED_IMPLEMENTATION": 2}
        )
        self.assertTrue(self.store.list_dispatches()[1].schema_repair)

    def test_dispatch_cannot_claim_different_context_identity(self) -> None:
        root = str(Path(self.temp.name).resolve())
        self.store.record_context(
            self.context(
                "thread-review", ContextClass.AI_PM_REVIEW,
                RoutingClass.AI_PM_REVIEW, "gpt-5.6-sol", "high", root,
            )
        )
        with self.assertRaises(UnsafePersistenceDataError):
            self.store.record_dispatch(
                DispatchRecord(
                    "dispatch-bad", "thread-review", "turn-bad", ContextClass.AI_EXECUTOR,
                    RoutingClass.EXEC_LOCAL_CORRECTIVE, "gpt-5.6-terra", "medium",
                    "codex-cli 0.fixture",
                )
            )

    def test_dispatch_must_match_context_route_model_and_effort(self) -> None:
        root = str(Path(self.temp.name).resolve())
        self.store.record_context(
            self.context(
                "thread-exec", ContextClass.AI_EXECUTOR,
                RoutingClass.EXEC_BOUNDED_IMPLEMENTATION,
                "gpt-5.6-terra", "high", root,
            )
        )
        mismatches = (
            (RoutingClass.EXEC_LOCAL_CORRECTIVE, "gpt-5.6-terra", "high"),
            (RoutingClass.EXEC_BOUNDED_IMPLEMENTATION, "gpt-5.6-sol", "high"),
            (RoutingClass.EXEC_BOUNDED_IMPLEMENTATION, "gpt-5.6-terra", "medium"),
        )
        for index, (routing, model, effort) in enumerate(mismatches):
            with self.subTest(index=index), self.assertRaises(UnsafePersistenceDataError):
                self.store.record_dispatch(
                    DispatchRecord(
                        f"dispatch-mismatch-{index}", "thread-exec", f"turn-{index}",
                        ContextClass.AI_EXECUTOR, routing, model, effort,
                        "codex-cli 0.fixture",
                    )
                )

    def test_dispatch_lookup_is_exact_and_latest_is_persisted(self) -> None:
        root = str(Path(self.temp.name).resolve())
        self.store.record_context(
            self.context(
                "thread-exec", ContextClass.AI_EXECUTOR,
                RoutingClass.EXEC_BOUNDED_IMPLEMENTATION,
                "gpt-5.6-terra", "high", root,
            )
        )
        first = DispatchRecord(
            "dispatch-first", "thread-exec", "turn-first",
            ContextClass.AI_EXECUTOR, RoutingClass.EXEC_BOUNDED_IMPLEMENTATION,
            "gpt-5.6-terra", "high", "codex-cli 0.fixture",
        )
        second = DispatchRecord(
            "dispatch-second", "thread-exec", "turn-second",
            ContextClass.AI_EXECUTOR, RoutingClass.EXEC_BOUNDED_IMPLEMENTATION,
            "gpt-5.6-terra", "high", "codex-cli 0.fixture", schema_repair=True,
        )
        self.store.record_dispatch(first)
        self.store.record_dispatch(second)
        self.assertEqual(self.store.load_dispatch(first.dispatch_id), first)
        self.assertEqual(self.store.latest_dispatch_for_thread("thread-exec"), second)

    def test_context_only_store_is_not_fresh(self) -> None:
        root = str(Path(self.temp.name).resolve())
        self.store.record_context(
            self.context(
                "thread-plan", ContextClass.AI_PM_PLAN,
                RoutingClass.AI_PM_PLAN_STANDARD, "gpt-5.6-sol", "medium", root,
            )
        )
        self.assertEqual(self.store.operational_record_count(), 1)
        with self.assertRaises(EngineError) as caught:
            DeterministicEngine.create(
                self.store, CapabilityPolicy(), run_id="ORCH-O002-RESIDUE-CONTEXT"
            )
        self.assertEqual(caught.exception.code, "EXISTING_STATE_REQUIRES_RECOVERY")

    def test_dispatch_state_store_is_not_fresh(self) -> None:
        root = str(Path(self.temp.name).resolve())
        self.store.record_context(
            self.context(
                "thread-exec", ContextClass.AI_EXECUTOR,
                RoutingClass.EXEC_BOUNDED_IMPLEMENTATION,
                "gpt-5.6-terra", "high", root,
            )
        )
        self.store.record_dispatch(
            DispatchRecord(
                "dispatch-residue", "thread-exec", "turn-residue",
                ContextClass.AI_EXECUTOR, RoutingClass.EXEC_BOUNDED_IMPLEMENTATION,
                "gpt-5.6-terra", "high", "codex-cli 0.fixture",
            )
        )
        self.assertEqual(self.store.operational_record_count(), 2)
        with self.assertRaises(EngineError):
            DeterministicEngine.create(
                self.store, CapabilityPolicy(), run_id="ORCH-O002-RESIDUE-DISPATCH"
            )

    def test_git_state_only_store_is_not_fresh(self) -> None:
        self.store.save_git_state(GitStateRecord("autopilot/integration", "a" * 40))
        self.assertEqual(self.store.operational_record_count(), 1)
        with self.assertRaises(EngineError):
            DeterministicEngine.create(
                self.store, CapabilityPolicy(), run_id="ORCH-O002-RESIDUE-GIT"
            )

    def test_git_state_round_trip_rejects_main(self) -> None:
        record = GitStateRecord("autopilot/integration", "a" * 40, "/tmp/worktree")
        self.store.save_git_state(record)
        self.assertEqual(self.store.load_git_state(), record)
        with self.assertRaises(UnsafePersistenceDataError):
            GitStateRecord("main", "a" * 40)


if __name__ == "__main__":
    unittest.main()
