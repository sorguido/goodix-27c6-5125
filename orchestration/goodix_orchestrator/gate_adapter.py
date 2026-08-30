# SPDX-License-Identifier: GPL-2.0-or-later
"""Deterministic private-GitHub Human Gate adapter for O003."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, replace
from typing import Any, Protocol

from .engine import DeterministicEngine
from .persistence import (
    AmbiguousEffectError,
    EffectKind,
    EffectRequestAction,
    EffectStatus,
    GateCreateIntent,
    GateDecisionIntent,
    GateExternalRecord,
    GateReplayError,
    IdempotencyIntentMismatchError,
    ReconciliationOutcome,
    SQLiteStateStore,
)
from .protocols import GateStatus, HumanGateManifest


_COMMAND_RE = re.compile(r"^/(approve|deny) (HG-[A-Za-z0-9][A-Za-z0-9._-]{0,119})$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True, slots=True)
class GateAdapterError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class GateCommand:
    approve: bool
    gate_id: str


@dataclass(frozen=True, slots=True)
class GateAction:
    action_id: str
    payload: dict[str, str]

    def canonical_bytes(self) -> bytes:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,79}", self.action_id):
            raise GateAdapterError("INVALID_ACTION_ID", self.action_id)
        if not isinstance(self.payload, dict) or len(self.payload) > 16:
            raise GateAdapterError("INVALID_ACTION_PAYLOAD", "not a bounded object")
        checked: dict[str, str] = {}
        for key, value in self.payload.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key):
                raise GateAdapterError("INVALID_ACTION_FIELD", repr(key))
            if not isinstance(value, str) or not value or len(value) > 512:
                raise GateAdapterError("INVALID_ACTION_VALUE", key)
            checked[key] = value
        return json.dumps(
            {"action_id": self.action_id, "payload": checked},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class GitHubIssue:
    repository: str
    number: int
    node_id: str
    title: str
    body: str


@dataclass(frozen=True, slots=True)
class GitHubComment:
    comment_id: int
    author_id: int
    author_login: str
    body: str


class GitHubGateTransport(Protocol):
    def find_gate_issue(self, repository: str, marker: str) -> GitHubIssue | None: ...
    def create_issue(self, repository: str, title: str, body: str) -> GitHubIssue: ...
    def read_issue(self, repository: str, number: int) -> GitHubIssue: ...
    def list_comments(self, repository: str, number: int) -> tuple[GitHubComment, ...]: ...


def parse_gate_command(body: str) -> GateCommand | None:
    if not isinstance(body, str) or "\n" in body or "\r" in body:
        return None
    match = _COMMAND_RE.fullmatch(body)
    if match is None:
        return None
    return GateCommand(match.group(1) == "approve", match.group(2))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class GhCliTransport:
    """Narrow ``gh api`` wrapper; credentials remain owned by gh."""

    def __init__(self, executable: str = "gh") -> None:
        self.executable = executable

    def _api(self, *args: str, stdin: str | None = None) -> Any:
        try:
            completed = subprocess.run(
                (self.executable, "api", *args),
                input=stdin,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
                env=None,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise GateAdapterError("GH_PREREQUISITE_UNAVAILABLE", type(exc).__name__) from exc
        if completed.returncode != 0:
            raise GateAdapterError("GH_API_FAILED", f"exit={completed.returncode}")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise GateAdapterError("GH_RESPONSE_INVALID", "non-JSON response") from exc

    @staticmethod
    def _issue(repository: str, data: dict[str, Any]) -> GitHubIssue:
        return GitHubIssue(
            repository=repository,
            number=int(data["number"]),
            node_id=str(data["node_id"]),
            title=str(data["title"]),
            body=str(data.get("body") or ""),
        )

    def find_gate_issue(self, repository: str, marker: str) -> GitHubIssue | None:
        gate_id = marker.removeprefix("<!-- goodix-orchestrator-gate:").removesuffix(" -->")
        result = self._api(
            "search/issues",
            "--method",
            "GET",
            "-f",
            f"q=repo:{repository} in:title \"[Human Gate] {gate_id}\"",
            "-f",
            "per_page=100",
        )
        issues = result.get("items", ()) if isinstance(result, dict) else ()
        matches = [self._issue(repository, item) for item in issues if marker in str(item.get("body") or "")]
        if len(matches) > 1:
            raise GateAdapterError("DUPLICATE_GATE_ISSUE", marker)
        return matches[0] if matches else None

    def create_issue(self, repository: str, title: str, body: str) -> GitHubIssue:
        data = self._api(
            f"repos/{repository}/issues",
            "--method",
            "POST",
            "-f",
            f"title={title}",
            "-f",
            f"body={body}",
        )
        return self._issue(repository, data)

    def read_issue(self, repository: str, number: int) -> GitHubIssue:
        return self._issue(repository, self._api(f"repos/{repository}/issues/{number}"))

    def list_comments(self, repository: str, number: int) -> tuple[GitHubComment, ...]:
        data = self._api(
            f"repos/{repository}/issues/{number}/comments",
            "--method",
            "GET",
            "-f",
            "per_page=100",
        )
        return tuple(
            GitHubComment(
                comment_id=int(item["id"]),
                author_id=int(item["user"]["id"]),
                author_login=str(item["user"]["login"]),
                body=str(item.get("body") or ""),
            )
            for item in data
        )


class HumanGateAdapter:
    def __init__(
        self,
        store: SQLiteStateStore,
        transport: GitHubGateTransport,
        *,
        repository: str,
        authorized_user_id: int,
        authorized_login: str,
    ) -> None:
        if _REPOSITORY_RE.fullmatch(repository) is None:
            raise GateAdapterError("INVALID_REPOSITORY", repository)
        if not isinstance(authorized_user_id, int) or authorized_user_id <= 0:
            raise GateAdapterError("AUTHORITY_ID_REQUIRED", repr(authorized_user_id))
        if not authorized_login or len(authorized_login) > 256:
            raise GateAdapterError("AUTHORITY_LOGIN_REQUIRED", repr(authorized_login))
        self.store = store
        self.transport = transport
        self.repository = repository
        self.authorized_user_id = authorized_user_id
        self.authorized_login = authorized_login

    @staticmethod
    def _marker(gate_id: str) -> str:
        return f"<!-- goodix-orchestrator-gate:{gate_id} -->"

    def _body(self, manifest: HumanGateManifest, action: GateAction) -> str:
        commit = manifest.commit_sha or "NONE"
        lines = [
                self._marker(manifest.gate_id),
                "# Goodix orchestrator Human Gate",
                "",
                f"GATE_ID: `{manifest.gate_id}`",
                f"TASK_ID: `{manifest.task_id}`",
                f"COMMIT_REF: `{commit}`",
                f"ACTION_ID: `{action.action_id}`",
                f"ACTION_DIGEST_SHA256: `{action.digest}`",
                "",
                f"Decision: {manifest.decision_required}",
                f"Reason: {manifest.reason}",
                "Residual risks:",
                *(f"- {item}" for item in manifest.residual_risks),
                "Still forbidden:",
                *(f"- {item}" for item in manifest.still_forbidden),
                "",
                manifest.decision_required,
                "",
                f"Approve exactly with `/approve {manifest.gate_id}` or deny with `/deny {manifest.gate_id}`.",
                "Free-form prose is not authoritative.",
        ]
        return "\n".join(lines)

    def create_or_reconcile(
        self,
        manifest: HumanGateManifest,
        action: GateAction,
        *,
        effect_id: str,
    ) -> GateExternalRecord:
        if manifest.status is not GateStatus.PENDING:
            raise GateAdapterError("GATE_NOT_PENDING", manifest.gate_id)
        if manifest.action_id != action.action_id or manifest.action_digest != action.digest:
            raise GateAdapterError(
                "GATE_ACTION_BINDING_MISMATCH",
                f"{manifest.action_id}/{manifest.action_digest}",
            )
        body = self._body(manifest, action)
        marker = self._marker(manifest.gate_id)
        intent = GateCreateIntent(manifest.task_id, manifest.gate_id, manifest.commit_sha)
        effect = self.store.load_effect(effect_id)
        if effect is not None and effect.status is EffectStatus.IN_PROGRESS:
            issue = self.transport.find_gate_issue(self.repository, marker)
            if issue is None:
                raise GateAdapterError("GATE_CREATE_OUTCOME_AMBIGUOUS", manifest.gate_id)
            self.store.reconcile_effect(effect_id, ReconciliationOutcome.COMPLETED)
        else:
            try:
                request = self.store.request_effect(
                    effect_id=effect_id,
                    idempotency_key=f"{manifest.gate_id}:GITHUB_ISSUE",
                    kind=EffectKind.GATE_CREATE,
                    intent=intent,
                )
            except AmbiguousEffectError as exc:
                raise GateAdapterError("GATE_CREATE_RECONCILIATION_REQUIRED", manifest.gate_id) from exc
            except IdempotencyIntentMismatchError as exc:
                raise GateAdapterError("GATE_BINDING_MUTATION", manifest.gate_id) from exc
            issue = self.transport.find_gate_issue(self.repository, marker)
            if request.action is EffectRequestAction.EXECUTE:
                self.store.begin_effect(effect_id)
                if issue is None:
                    issue = self.transport.create_issue(
                        self.repository,
                        f"[Human Gate] {manifest.gate_id}",
                        body,
                    )
                self.store.complete_effect(effect_id)
        if issue is None:
            raise GateAdapterError("GATE_ISSUE_MISSING_AFTER_COMPLETED_EFFECT", manifest.gate_id)
        if issue.repository != self.repository or issue.body != body:
            raise GateAdapterError("GATE_ISSUE_INTEGRITY_FAILURE", manifest.gate_id)
        record = GateExternalRecord(
            gate_id=manifest.gate_id,
            task_id=manifest.task_id,
            repository=self.repository,
            issue_number=issue.number,
            issue_node_id=issue.node_id,
            issue_body_digest=_sha256_text(body),
            action_id=action.action_id,
            action_digest=action.digest,
            commit_sha=manifest.commit_sha,
            authorized_user_id=self.authorized_user_id,
            authorized_login=self.authorized_login,
        )
        existing = self.store.load_gate_external(manifest.gate_id)
        if existing is not None:
            if existing != record:
                raise GateAdapterError("GATE_BINDING_MUTATION", manifest.gate_id)
            return existing
        return self.store.save_gate_external(record)

    def reconcile_issue(self, gate_id: str) -> GateExternalRecord:
        record = self.store.load_gate_external(gate_id)
        if record is None:
            raise GateAdapterError("MISSING_GATE_BINDING", gate_id)
        issue = self.transport.read_issue(self.repository, record.issue_number)
        if (
            issue.repository != record.repository
            or issue.node_id != record.issue_node_id
            or _sha256_text(issue.body) != record.issue_body_digest
        ):
            raise GateAdapterError("GATE_ISSUE_INTEGRITY_FAILURE", gate_id)
        return record

    def reconcile_decision_before_engine_recovery(self) -> bool:
        """Close the persisted decision crash boundary before engine recovery.

        This performs no transition itself.  ``DeterministicEngine.recover``
        observes the terminal local gate and applies its already-encoded
        continuation exactly once.
        """
        runtime = self.store.load_runtime()
        if runtime is None or runtime.gate_id is None:
            return False
        record = self.store.load_gate_external(runtime.gate_id)
        manifest = self.store.load_gate(runtime.gate_id)
        if (
            record is None
            or manifest is None
            or record.decision is GateStatus.PENDING
            or manifest.status is not GateStatus.PENDING
        ):
            return False
        self.reconcile_issue(record.gate_id)
        self.store.decide_gate(record.gate_id, record.decision)
        effect_id = f"EFFECT-GATE-DECISION-{record.gate_id}"
        effect = self.store.load_effect(effect_id)
        if effect is None or effect.status is not EffectStatus.IN_PROGRESS:
            raise GateAdapterError("GATE_DECISION_EFFECT_MISSING", record.gate_id)
        self.store.complete_effect(effect_id)
        return True

    def poll(self, engine: DeterministicEngine) -> bool:
        gate_id = engine.runtime.gate_id
        if gate_id is None:
            return False
        manifest = self.store.load_gate(gate_id)
        record = self.reconcile_issue(gate_id)
        if manifest is None or manifest.status is not GateStatus.PENDING:
            raise GateAdapterError("LOCAL_GATE_NOT_PENDING", gate_id)
        if manifest.task_id != record.task_id or manifest.commit_sha != record.commit_sha:
            raise GateAdapterError("LOCAL_GATE_BINDING_MISMATCH", gate_id)
        if record.decision is not GateStatus.PENDING:
            return self._finish_persisted_decision(engine, record)
        for comment in self.transport.list_comments(self.repository, record.issue_number):
            command = parse_gate_command(comment.body)
            if command is None or command.gate_id != gate_id:
                continue
            if (
                comment.author_id != record.authorized_user_id
                or comment.author_login != record.authorized_login
            ):
                continue
            decision = GateStatus.APPROVED if command.approve else GateStatus.DENIED
            intent = GateDecisionIntent(
                record.task_id, gate_id, decision.value, comment.comment_id
            )
            effect_id = f"EFFECT-GATE-DECISION-{gate_id}"
            request = self.store.request_effect(
                effect_id=effect_id,
                idempotency_key=f"{gate_id}:DECISION",
                kind=EffectKind.GATE_DECISION_CONSUME,
                intent=intent,
            )
            if request.action is EffectRequestAction.EXECUTE:
                self.store.begin_effect(effect_id)
                record = self.store.save_gate_external(
                    replace(
                        record,
                        decision_comment_id=comment.comment_id,
                        decision_author_id=comment.author_id,
                        decision=decision,
                    )
                )
            return self._finish_persisted_decision(engine, record)
        return False

    def _finish_persisted_decision(
        self, engine: DeterministicEngine, record: GateExternalRecord
    ) -> bool:
        if record.decision is GateStatus.PENDING:
            return False
        manifest = self.store.load_gate(record.gate_id)
        if manifest is not None and manifest.status is GateStatus.PENDING:
            engine.resolve_gate(
                gate_id=record.gate_id,
                approve=record.decision is GateStatus.APPROVED,
            )
        effect_id = f"EFFECT-GATE-DECISION-{record.gate_id}"
        effect = self.store.load_effect(effect_id)
        if effect is not None and effect.status is EffectStatus.IN_PROGRESS:
            self.store.complete_effect(effect_id)
        return True
