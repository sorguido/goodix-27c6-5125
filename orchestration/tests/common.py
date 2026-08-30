# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

from goodix_orchestrator.policy import Capability
from goodix_orchestrator.protocols import (
    CanonicalDocumentation,
    ExecutableClosure,
    ExecutorOutcome,
    ExecutorResult,
    GateRequester,
    GateStatus,
    HumanGateManifest,
    ModelPolicy,
    PolicyAssertions,
    PROTOCOL_VERSION,
    ReviewSet,
    TaskManifest,
    TaskScope,
    TestRecord,
    TestStatus,
)
from goodix_orchestrator.state import OrchestratorState


BASELINE = "a" * 40
HEAD_ONE = "b" * 40
HEAD_TWO = "c" * 40


def task_manifest(
    task_id: str = "TASK-20260830-001",
    *,
    baseline: str = BASELINE,
    parent_task_id: str | None = None,
) -> TaskManifest:
    return TaskManifest(
        protocol_version=PROTOCOL_VERSION,
        task_id=task_id,
        parent_task_id=parent_task_id,
        title="Synthetic host-only task",
        objective="Exercise the deterministic core without external effects",
        baseline_sha=baseline,
        integration_branch="orchestration/integration",
        task_branch=f"ai-executor/{task_id.lower()}",
        model_policy=ModelPolicy(preferred="gpt-5.6-sol-high", allowed=("gpt-5.6-sol-high",)),
        gate_class="HOST_ONLY",
        capabilities_required=(
            Capability.HOST_READ,
            Capability.WORKTREE_WRITE,
            Capability.TASK_COMMIT,
        ),
        scope=TaskScope(paths=("orchestration/",), non_goals=("No real adapters",)),
        acceptance_criteria=("Fake flow passes",),
        manual_update_required=True,
        stop_conditions=("Any protected capability is requested",),
    )


def executor_result(
    task_id: str = "TASK-20260830-001",
    *,
    baseline: str = BASELINE,
    head: str = HEAD_ONE,
) -> ExecutorResult:
    return ExecutorResult(
        protocol_version=PROTOCOL_VERSION,
        task_id=task_id,
        outcome=ExecutorOutcome.READY,
        advancement="Synthetic deterministic execution",
        executable_closure=ExecutableClosure.PASS,
        residual_blocker_or_risk="No real adapter has been qualified",
        canonical_documentation=CanonicalDocumentation(
            manual_updated=True, sections=("Orchestration bootstrap",)
        ),
        review_set=ReviewSet(
            baseline_sha=baseline,
            head_sha=head,
            changed_paths=("orchestration/goodix_orchestrator/state.py",),
        ),
        tests=(TestRecord(command="python -m unittest", status=TestStatus.PASS),),
        policy_assertions=PolicyAssertions(
            usb_open_count=0,
            sudo_used=False,
            protected_material_accessed=False,
            main_modified=False,
        ),
    )


def pending_gate(
    task_id: str = "TASK-20260830-001",
    gate_id: str = "HG-20260830-001",
) -> HumanGateManifest:
    return HumanGateManifest(
        protocol_version=PROTOCOL_VERSION,
        gate_id=gate_id,
        task_id=task_id,
        decision_required="Approve a synthetic continuation",
        reason="Exercise deterministic gate semantics",
        commit_sha=HEAD_ONE,
        action_to_unlock="Return to PM planning",
        residual_risks=("No real identity validation exists in O001",),
        still_forbidden=("USB_GOODIX", "MAIN_MERGE"),
        requested_by=GateRequester.AI_PM,
        status=GateStatus.PENDING,
        approval_state=OrchestratorState.PM_PLANNING,
        denial_state=OrchestratorState.DONE,
    )
