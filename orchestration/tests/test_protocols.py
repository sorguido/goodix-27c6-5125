import unittest

from goodix_orchestrator.policy import Capability
from goodix_orchestrator.protocols import (
    Disposition,
    GateStatus,
    HumanGateManifest,
    PMDisposition,
    PROTOCOL_VERSION,
    ProtocolValidationError,
    TaskManifest,
)
from goodix_orchestrator.state import OrchestratorState

from tests.common import BASELINE, HEAD_ONE, executor_result, pending_gate, task_manifest


class ProtocolTests(unittest.TestCase):
    def test_task_manifest_round_trip(self) -> None:
        manifest = task_manifest()
        self.assertEqual(TaskManifest.from_dict(manifest.to_dict()), manifest)

    def test_task_rejects_bad_sha_unknown_gate_and_protocol(self) -> None:
        data = task_manifest().to_dict()
        for field, value, code in (
            ("baseline_sha", "abc", "MALFORMED_SHA"),
            ("gate_class", "LIVE_BY_PROMPT", "UNKNOWN_ENUM_VALUE"),
            ("protocol_version", "2.0", "UNSUPPORTED_PROTOCOL_VERSION"),
        ):
            mutated = dict(data)
            mutated[field] = value
            with self.subTest(field=field), self.assertRaises(ProtocolValidationError) as caught:
                TaskManifest.from_dict(mutated)
            self.assertEqual(caught.exception.code, code)

    def test_task_rejects_unknown_and_protected_capability(self) -> None:
        for capability, code in (
            ("MAKE_IT_WORK", "UNKNOWN_CAPABILITY"),
            (Capability.USB_GOODIX.value, "PROTECTED_CAPABILITY_REQUEST"),
            (Capability.ROOT_SUDO.value, "PROTECTED_CAPABILITY_REQUEST"),
        ):
            data = task_manifest().to_dict()
            data["capabilities_required"] = [capability]
            with self.subTest(capability=capability), self.assertRaises(ProtocolValidationError) as caught:
                TaskManifest.from_dict(data)
            self.assertEqual(caught.exception.code, code)

    def test_executor_result_round_trip_and_validation(self) -> None:
        result = executor_result()
        self.assertEqual(type(result).from_dict(result.to_dict()), result)
        data = result.to_dict()
        data["tests"] = []
        with self.assertRaises(ProtocolValidationError) as caught:
            type(result).from_dict(data)
        self.assertEqual(caught.exception.code, "INVALID_TESTS")

    def test_unknown_disposition_is_rejected(self) -> None:
        with self.assertRaises(ProtocolValidationError) as caught:
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-001",
                disposition="MAYBE",
                reason="Free text must not control the machine",
            )
        self.assertEqual(caught.exception.code, "UNKNOWN_ENUM_VALUE")

    def test_accept_requires_exact_sha_and_explicit_target(self) -> None:
        with self.assertRaises(ProtocolValidationError) as caught:
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-001",
                disposition=Disposition.ACCEPT,
                reason="Reviewed",
                accept_target=OrchestratorState.DONE,
            )
        self.assertEqual(caught.exception.code, "ACCEPT_REQUIRES_REVIEWED_SHA")
        valid = PMDisposition(
            protocol_version=PROTOCOL_VERSION,
            task_id="TASK-20260830-001",
            disposition=Disposition.ACCEPT,
            reason="Reviewed",
            reviewed_head_sha=HEAD_ONE,
            accept_target=OrchestratorState.PM_PLANNING,
            next_task_id="TASK-20260830-002",
        )
        self.assertEqual(PMDisposition.from_dict(valid.to_dict()), valid)

    def test_human_gate_contract_and_terminal_replay(self) -> None:
        gate = pending_gate()
        self.assertEqual(HumanGateManifest.from_dict(gate.to_dict()), gate)
        terminal = gate.terminal(GateStatus.APPROVED)
        self.assertEqual(terminal.status, GateStatus.APPROVED)
        with self.assertRaises(ProtocolValidationError) as caught:
            terminal.terminal(GateStatus.DENIED)
        self.assertEqual(caught.exception.code, "TERMINAL_GATE_REPLAY")

    def test_human_gate_disposition_requires_pending_matching_gate(self) -> None:
        disposition = PMDisposition(
            protocol_version=PROTOCOL_VERSION,
            task_id="TASK-20260830-001",
            disposition=Disposition.HUMAN_GATE,
            reason="Human decision required",
            gate=pending_gate(),
        )
        self.assertEqual(PMDisposition.from_dict(disposition.to_dict()), disposition)

    def test_done_forbids_next_task(self) -> None:
        with self.assertRaises(ProtocolValidationError) as caught:
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-001",
                disposition=Disposition.DONE,
                reason="Finished",
                next_task_id="TASK-20260830-002",
            )
        self.assertEqual(caught.exception.code, "DONE_FORBIDS_NEXT_TASK")

    def test_empty_critical_task_field_is_rejected(self) -> None:
        data = task_manifest().to_dict()
        data["objective"] = ""
        with self.assertRaises(ProtocolValidationError) as caught:
            TaskManifest.from_dict(data)
        self.assertEqual(caught.exception.code, "EMPTY_CRITICAL_FIELD")


if __name__ == "__main__":
    unittest.main()
