import tempfile
import unittest
from pathlib import Path

from goodix_orchestrator.engine import DeterministicEngine, EngineError
from goodix_orchestrator.persistence import GateReplayError, SQLiteStateStore
from goodix_orchestrator.policy import Capability, CapabilityPolicy
from goodix_orchestrator.protocols import (
    Disposition,
    GateStatus,
    PMDisposition,
    PROTOCOL_VERSION,
    PauseReason,
)
from goodix_orchestrator.state import OrchestratorState

from tests.common import BASELINE, HEAD_ONE, HEAD_TWO, executor_result, pending_gate, task_manifest


class FakeAgentFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.store = SQLiteStateStore(self.path)
        self.policy = CapabilityPolicy(
            (Capability.HOST_READ, Capability.WORKTREE_WRITE, Capability.TASK_COMMIT)
        )
        self.engine = DeterministicEngine.create(
            self.store, self.policy, run_id="ORCH-20260830-020"
        )
        self.engine.bootstrap_complete()
        self.engine.start_planning()

    def run_to_review(self, task_id="TASK-20260830-001", baseline=BASELINE, head=HEAD_ONE):
        self.engine.task_ready(task_manifest(task_id, baseline=baseline))
        self.engine.start_executor(turn_id=f"TURN-{task_id}-EXEC")
        self.engine.complete_executor(
            executor_result(task_id, baseline=baseline, head=head)
        )
        self.engine.start_review(turn_id=f"TURN-{task_id}-PM")
        self.assertEqual(self.engine.state, OrchestratorState.PM_REVIEWING)

    def test_flow_a_accept_next_task_then_done(self) -> None:
        self.run_to_review()
        self.engine.apply_disposition(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-001",
                disposition=Disposition.ACCEPT,
                reason="First synthetic task accepted",
                reviewed_head_sha=HEAD_ONE,
                accept_target=OrchestratorState.PM_PLANNING,
                next_task_id="TASK-20260830-002",
            )
        )
        self.assertEqual(self.engine.state, OrchestratorState.PM_PLANNING)
        self.run_to_review("TASK-20260830-002", baseline=HEAD_ONE, head=HEAD_TWO)
        self.engine.apply_disposition(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-002",
                disposition=Disposition.DONE,
                reason="Delegated synthetic objective completed",
            )
        )
        self.assertEqual(self.engine.state, OrchestratorState.DONE)

    def test_flow_b_corrective_then_accept(self) -> None:
        self.run_to_review()
        self.engine.apply_disposition(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-001",
                disposition=Disposition.CORRECTIVE,
                reason="Fixture requests one deterministic correction",
            )
        )
        self.assertEqual(self.engine.state, OrchestratorState.TASK_READY)
        self.engine.start_executor(turn_id="TURN-CORRECTIVE-EXEC")
        self.engine.complete_executor(executor_result(head=HEAD_TWO))
        self.engine.start_review(turn_id="TURN-CORRECTIVE-PM")
        self.engine.apply_disposition(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-001",
                disposition=Disposition.ACCEPT,
                reason="Corrective accepted",
                reviewed_head_sha=HEAD_TWO,
                accept_target=OrchestratorState.DONE,
            )
        )
        self.assertEqual(self.engine.state, OrchestratorState.DONE)

    def test_flow_c_replan_without_scope_or_capability_expansion(self) -> None:
        self.run_to_review()
        original_grants = self.policy.grants
        self.engine.apply_disposition(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-001",
                disposition=Disposition.REPLAN,
                reason="Change synthetic method within the same envelope",
            )
        )
        self.assertEqual(self.engine.state, OrchestratorState.PM_PLANNING)
        self.assertEqual(self.policy.grants, original_grants)

    def test_flow_d_human_gate_stop_approve_and_replay_denial(self) -> None:
        self.run_to_review()
        gate = pending_gate()
        self.engine.apply_disposition(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-001",
                disposition=Disposition.HUMAN_GATE,
                reason="Synthetic stop",
                gate=gate,
            )
        )
        self.assertEqual(self.engine.state, OrchestratorState.HUMAN_GATE_WAIT)
        with self.assertRaises(Exception):
            self.engine.task_ready(task_manifest())
        self.engine.resolve_gate(gate_id=gate.gate_id, approve=True)
        self.assertEqual(self.engine.state, OrchestratorState.PM_PLANNING)
        with self.assertRaises(GateReplayError):
            self.store.decide_gate(gate.gate_id, GateStatus.DENIED)

    def test_flow_d_human_gate_deny_to_done(self) -> None:
        self.run_to_review()
        gate = pending_gate(gate_id="HG-20260830-002")
        self.engine.apply_disposition(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-001",
                disposition=Disposition.HUMAN_GATE,
                reason="Synthetic stop",
                gate=gate,
            )
        )
        self.engine.resolve_gate(gate_id=gate.gate_id, approve=False)
        self.assertEqual(self.engine.state, OrchestratorState.DONE)

    def test_crash_after_gate_create_reconciles_to_wait(self) -> None:
        self.run_to_review()
        gate = pending_gate(gate_id="HG-20260830-003")
        self.store.record_gate(gate)  # simulated crash before runtime transition
        recovered = DeterministicEngine.recover(
            self.path, self.policy, expected_run_id="ORCH-20260830-020"
        )
        self.assertEqual(recovered.state, OrchestratorState.HUMAN_GATE_WAIT)
        self.assertEqual(recovered.engine.runtime.gate_id, gate.gate_id)

    def test_crash_after_terminal_gate_decision_reconciles_without_replay(self) -> None:
        self.run_to_review()
        gate = pending_gate(gate_id="HG-20260830-004")
        self.engine.apply_disposition(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-001",
                disposition=Disposition.HUMAN_GATE,
                reason="Synthetic stop",
                gate=gate,
            )
        )
        self.store.decide_gate(gate.gate_id, GateStatus.APPROVED)
        recovered = DeterministicEngine.recover(
            self.path, self.policy, expected_run_id="ORCH-20260830-020"
        )
        self.assertEqual(recovered.state, OrchestratorState.PM_PLANNING)
        self.assertIsNone(recovered.engine.runtime.gate_id)

    def test_flow_e_rate_limit_pause_persist_and_resume(self) -> None:
        self.run_to_review()
        self.engine.apply_disposition(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-001",
                disposition=Disposition.PAUSE,
                reason="Included quota exhausted",
                pause_reason=PauseReason.RATE_LIMIT,
            )
        )
        self.assertEqual(self.engine.state, OrchestratorState.PAUSED_RATE_LIMIT)
        recovered = DeterministicEngine.recover(
            self.path, self.policy, expected_run_id="ORCH-20260830-020"
        )
        self.assertEqual(recovered.state, OrchestratorState.PAUSED_RATE_LIMIT)
        recovered.engine.resume_pause()
        self.assertEqual(recovered.engine.state, OrchestratorState.PM_REVIEWING)

    def test_reviewed_sha_mismatch_locks(self) -> None:
        self.run_to_review()
        with self.assertRaises(EngineError) as caught:
            self.engine.apply_disposition(
                PMDisposition(
                    protocol_version=PROTOCOL_VERSION,
                    task_id="TASK-20260830-001",
                    disposition=Disposition.ACCEPT,
                    reason="Wrong head fixture",
                    reviewed_head_sha=HEAD_TWO,
                    accept_target=OrchestratorState.DONE,
                )
            )
        self.assertEqual(caught.exception.code, "REVIEWED_HEAD_MISMATCH")
        self.assertEqual(self.engine.state, OrchestratorState.ERROR_LOCKED)


if __name__ == "__main__":
    unittest.main()
