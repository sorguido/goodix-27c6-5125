import unittest

from goodix_orchestrator.state import (
    OrchestratorState,
    StateEvent,
    StateTransitionError,
    transition,
)


class StateMachineTests(unittest.TestCase):
    def test_normative_linear_path(self) -> None:
        state = OrchestratorState.BOOTSTRAP
        for event, expected in (
            (StateEvent.BOOTSTRAP_COMPLETE, OrchestratorState.IDLE),
            (StateEvent.START_PLANNING, OrchestratorState.PM_PLANNING),
            (StateEvent.TASK_PREPARED, OrchestratorState.TASK_READY),
            (StateEvent.EXECUTOR_STARTED, OrchestratorState.EXECUTOR_RUNNING),
            (StateEvent.EXECUTOR_COMPLETED, OrchestratorState.EXECUTOR_RESULT_READY),
            (StateEvent.REVIEW_STARTED, OrchestratorState.PM_REVIEWING),
        ):
            state = transition(state, event)
            self.assertEqual(state, expected)

    def test_accept_requires_explicit_allowed_target(self) -> None:
        with self.assertRaises(StateTransitionError) as caught:
            transition(OrchestratorState.PM_REVIEWING, StateEvent.ACCEPT)
        self.assertEqual(caught.exception.code, "EXPLICIT_TARGET_REQUIRED")
        self.assertEqual(
            transition(
                OrchestratorState.PM_REVIEWING,
                StateEvent.ACCEPT,
                target=OrchestratorState.PM_PLANNING,
            ),
            OrchestratorState.PM_PLANNING,
        )

    def test_invalid_transition_is_structured_and_denied(self) -> None:
        with self.assertRaises(StateTransitionError) as caught:
            transition(OrchestratorState.IDLE, StateEvent.EXECUTOR_STARTED)
        self.assertEqual(caught.exception.code, "INVALID_TRANSITION")
        self.assertEqual(caught.exception.as_dict()["current_state"], "IDLE")

    def test_unknown_state_and_event_are_denied(self) -> None:
        with self.assertRaises(StateTransitionError) as state_error:
            transition("NOT_A_STATE", StateEvent.START_PLANNING)
        self.assertEqual(state_error.exception.code, "UNKNOWN_STATE")
        with self.assertRaises(StateTransitionError) as event_error:
            transition(OrchestratorState.IDLE, "GUESS_FROM_TEXT")
        self.assertEqual(event_error.exception.code, "UNKNOWN_EVENT")

    def test_gate_target_is_bounded(self) -> None:
        with self.assertRaises(StateTransitionError) as caught:
            transition(
                OrchestratorState.HUMAN_GATE_WAIT,
                StateEvent.GATE_APPROVE,
                target=OrchestratorState.EXECUTOR_RUNNING,
            )
        self.assertEqual(caught.exception.code, "INVALID_GATE_CONTINUATION")

    def test_pause_requires_exact_reconciliation_target(self) -> None:
        with self.assertRaises(StateTransitionError) as caught:
            transition(
                OrchestratorState.PAUSED_RATE_LIMIT,
                StateEvent.RECONCILE_RESUME,
                target=OrchestratorState.TASK_READY,
                expected_resume_state=OrchestratorState.PM_REVIEWING,
            )
        self.assertEqual(caught.exception.code, "PAUSE_RECONCILIATION_MISMATCH")
        self.assertEqual(
            transition(
                OrchestratorState.PAUSED_RATE_LIMIT,
                StateEvent.RECONCILE_RESUME,
                target=OrchestratorState.PM_REVIEWING,
                expected_resume_state=OrchestratorState.PM_REVIEWING,
            ),
            OrchestratorState.PM_REVIEWING,
        )


if __name__ == "__main__":
    unittest.main()
