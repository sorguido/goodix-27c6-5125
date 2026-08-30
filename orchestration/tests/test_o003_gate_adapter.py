# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from goodix_orchestrator.engine import DeterministicEngine
from goodix_orchestrator.gate_adapter import (
    GateAction,
    GateAdapterError,
    GitHubComment,
    GitHubIssue,
    HumanGateAdapter,
    parse_gate_command,
)
from goodix_orchestrator.persistence import (
    EffectKind,
    GateCreateIntent,
    GateDecisionIntent,
    GateExternalRecord,
    SQLiteStateStore,
)
from goodix_orchestrator.policy import Capability, CapabilityPolicy
from goodix_orchestrator.protocols import Disposition, GateStatus, PMDisposition, PROTOCOL_VERSION
from goodix_orchestrator.state import OrchestratorState

from tests.common import executor_result, pending_gate, task_manifest


class FakeGitHub:
    def __init__(self) -> None:
        self.issue: GitHubIssue | None = None
        self.comments: list[GitHubComment] = []
        self.create_count = 0

    def find_gate_issue(self, repository: str, marker: str):
        return self.issue if self.issue and marker in self.issue.body else None

    def create_issue(self, repository: str, title: str, body: str):
        self.create_count += 1
        self.issue = GitHubIssue(repository, 41, "ISSUE_node_41", title, body)
        return self.issue

    def read_issue(self, repository: str, number: int):
        assert self.issue is not None
        return self.issue

    def list_comments(self, repository: str, number: int):
        return tuple(self.comments)


class O003GateAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SQLiteStateStore(Path(self.temp.name) / "state.sqlite")
        policy = CapabilityPolicy(
            (Capability.HOST_READ, Capability.WORKTREE_WRITE, Capability.TASK_COMMIT)
        )
        self.engine = DeterministicEngine.create(self.store, policy, run_id="ORCH-O003-GATE")
        self.engine.bootstrap_complete()
        self.engine.start_planning()
        self.engine.task_ready(task_manifest())
        self.engine.start_executor(turn_id="TURN-O003-EXEC")
        self.engine.complete_executor(executor_result())
        self.engine.start_review(turn_id="TURN-O003-REVIEW")
        self.gate = pending_gate()
        self.engine.apply_disposition(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id=self.gate.task_id,
                disposition=Disposition.HUMAN_GATE,
                reason="synthetic gate",
                gate=self.gate,
            )
        )
        self.github = FakeGitHub()
        self.adapter = HumanGateAdapter(
            self.store,
            self.github,
            repository="sorguido/goodix-private",
            authorized_user_id=12345,
            authorized_login="sorguido",
        )
        self.action = GateAction("SYNTHETIC_CONTINUE", {"mode": "host-only"})

    def bind(self):
        return self.adapter.create_or_reconcile(
            self.gate, self.action, effect_id="EFFECT-GATE-ISSUE"
        )

    def test_exact_command_parser(self) -> None:
        self.assertTrue(parse_gate_command("/approve HG-abc").approve)
        self.assertFalse(parse_gate_command("/deny HG-abc").approve)
        for value in (
            "approve HG-abc", "/approve", "/approve HG-abc extra",
            "please /approve HG-abc", "/approve HG-abc\n", "> /approve HG-abc",
        ):
            with self.subTest(value=value):
                self.assertIsNone(parse_gate_command(value))

    def test_gate_binding_and_authorized_approval_resume_once(self) -> None:
        record = self.bind()
        self.assertEqual(record.action_digest, self.action.digest)
        self.github.comments.append(GitHubComment(7, 12345, "sorguido", f"/approve {self.gate.gate_id}"))
        self.assertTrue(self.adapter.poll(self.engine))
        self.assertEqual(self.engine.state, OrchestratorState.PM_PLANNING)
        self.assertEqual(self.store.load_gate(self.gate.gate_id).status, GateStatus.APPROVED)
        self.assertFalse(self.adapter.poll(self.engine))
        self.assertEqual(len(self.store.list_dispatches()), 0)

    def test_denial_is_terminal_and_not_reinterpreted(self) -> None:
        self.bind()
        self.github.comments.append(GitHubComment(8, 12345, "sorguido", f"/deny {self.gate.gate_id}"))
        self.assertTrue(self.adapter.poll(self.engine))
        self.assertEqual(self.engine.state, OrchestratorState.DONE)
        with self.assertRaises(Exception):
            self.store.decide_gate(self.gate.gate_id, GateStatus.APPROVED)

    def test_wrong_identity_wrong_gate_and_fuzzy_comments_do_not_advance(self) -> None:
        self.bind()
        self.github.comments.extend(
            (
                GitHubComment(1, 999, "intruder", f"/approve {self.gate.gate_id}"),
                GitHubComment(2, 12345, "sorguido", "/approve HG-other"),
                GitHubComment(3, 12345, "sorguido", f"please /approve {self.gate.gate_id}"),
            )
        )
        self.assertFalse(self.adapter.poll(self.engine))
        self.assertEqual(self.engine.state, OrchestratorState.HUMAN_GATE_WAIT)

    def test_wrong_repository_or_edited_issue_fails_closed(self) -> None:
        self.bind()
        assert self.github.issue is not None
        self.github.issue = replace(self.github.issue, body=self.github.issue.body + "\nedited")
        with self.assertRaises(GateAdapterError) as caught:
            self.adapter.poll(self.engine)
        self.assertEqual(caught.exception.code, "GATE_ISSUE_INTEGRITY_FAILURE")

    def test_action_or_commit_rebinding_is_denied(self) -> None:
        self.bind()
        with self.assertRaises(GateAdapterError):
            self.adapter.create_or_reconcile(
                self.gate,
                GateAction("OTHER_ACTION", {"mode": "host-only"}),
                effect_id="EFFECT-GATE-ISSUE",
            )
        with self.assertRaises(GateAdapterError):
            self.adapter.create_or_reconcile(
                replace(self.gate, commit_sha="c" * 40),
                self.action,
                effect_id="EFFECT-GATE-ISSUE",
            )

    def test_initial_manifest_action_mismatch_is_denied(self) -> None:
        mismatched = replace(self.gate, action_id="OTHER_ACTION")
        with self.assertRaises(GateAdapterError) as caught:
            self.adapter.create_or_reconcile(
                mismatched,
                self.action,
                effect_id="EFFECT-GATE-INITIAL-MISMATCH",
            )
        self.assertEqual(caught.exception.code, "GATE_ACTION_BINDING_MISMATCH")
        self.assertIsNone(self.github.issue)

    def test_crash_after_issue_creation_reconciles_without_duplicate(self) -> None:
        body = self.adapter._body(self.gate, self.action)
        self.github.create_issue("sorguido/goodix-private", "gate", body)
        self.store.request_effect(
            effect_id="EFFECT-GATE-ISSUE",
            idempotency_key=f"{self.gate.gate_id}:GITHUB_ISSUE",
            kind=EffectKind.GATE_CREATE,
            intent=GateCreateIntent(self.gate.task_id, self.gate.gate_id, self.gate.commit_sha),
        )
        self.store.begin_effect("EFFECT-GATE-ISSUE")
        self.bind()
        self.assertEqual(self.github.create_count, 1)

    def test_crash_after_decision_provenance_finishes_once(self) -> None:
        record = self.bind()
        terminal = replace(
            record,
            decision_comment_id=77,
            decision_author_id=12345,
            decision=GateStatus.APPROVED,
        )
        self.store.save_gate_external(terminal)
        self.store.request_effect(
            effect_id=f"EFFECT-GATE-DECISION-{self.gate.gate_id}",
            idempotency_key=f"{self.gate.gate_id}:DECISION",
            kind=EffectKind.GATE_DECISION_CONSUME,
            intent=GateDecisionIntent(self.gate.task_id, self.gate.gate_id, "APPROVED", 77),
        )
        self.store.begin_effect(f"EFFECT-GATE-DECISION-{self.gate.gate_id}")
        self.assertTrue(self.adapter.reconcile_decision_before_engine_recovery())
        recovered = DeterministicEngine.recover(
            self.store.path,
            self.engine.policy,
            expected_run_id="ORCH-O003-GATE",
        )
        self.assertEqual(recovered.state, OrchestratorState.PM_PLANNING)

    def test_human_gate_wait_blocks_ordinary_dispatch(self) -> None:
        with self.assertRaises(Exception):
            self.engine.start_planning()
        self.assertEqual(self.engine.state, OrchestratorState.HUMAN_GATE_WAIT)


if __name__ == "__main__":
    unittest.main()
