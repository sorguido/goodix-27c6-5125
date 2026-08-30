# SPDX-License-Identifier: GPL-2.0-or-later
"""Single-file SQLite persistence and typed idempotency ledger for O001."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterator

from .policy import ProtectedBranchError, require_ordinary_branch

from .protocols import (
    GateStatus,
    HumanGateManifest,
    PROTOCOL_VERSION,
    ProtocolValidationError,
    TaskEnvelope,
)
from .state import OrchestratorState, PAUSED_STATES


SCHEMA_VERSION = 2
_RUN_ID_RE = re.compile(r"^ORCH-[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_TASK_ID_RE = re.compile(r"^TASK-[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_TURN_ID_RE = re.compile(r"^TURN-[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_GATE_ID_RE = re.compile(r"^HG-[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REF_FORBIDDEN_RE = re.compile(r"[\s~^:?*\[\\]")


class PersistenceError(Exception):
    code = "PERSISTENCE_ERROR"


class StoreCorruptionError(PersistenceError):
    code = "STORE_CORRUPT"


class StoreIncompatibleError(PersistenceError):
    code = "STORE_INCOMPATIBLE"


class ConcurrentStateError(PersistenceError):
    code = "CONCURRENT_STATE_UPDATE"


class IdempotencyIntentMismatchError(PersistenceError):
    code = "IDEMPOTENCY_INTENT_MISMATCH"


class AmbiguousEffectError(PersistenceError):
    code = "AMBIGUOUS_EFFECT"


class GateReplayError(PersistenceError):
    code = "TERMINAL_GATE_REPLAY"


class UnsafePersistenceDataError(PersistenceError):
    code = "UNSAFE_PERSISTENCE_DATA"


class EffectKind(StrEnum):
    BRANCH_CREATE = "BRANCH_CREATE"
    COMMIT = "COMMIT"
    PUSH = "PUSH"
    INTEGRATION_FF = "INTEGRATION_FF"
    GATE_CREATE = "GATE_CREATE"


class EffectStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    AMBIGUOUS = "AMBIGUOUS"


class EffectRequestAction(StrEnum):
    EXECUTE = "EXECUTE"
    SKIP_COMPLETED = "SKIP_COMPLETED"


class ReconciliationOutcome(StrEnum):
    NO_EFFECT = "NO_EFFECT"
    COMPLETED = "COMPLETED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class RuntimeRecord:
    current_state: OrchestratorState
    run_id: str
    previous_recoverable_state: OrchestratorState | None = None
    task_id: str | None = None
    turn_id: str | None = None
    gate_id: str | None = None
    baseline_sha: str | None = None
    result_sha: str | None = None
    expected_next_task_id: str | None = None
    task_envelope: TaskEnvelope | None = None
    protocol_version: str = PROTOCOL_VERSION
    revision: int = 0

    def __post_init__(self) -> None:
        try:
            state = self.current_state if isinstance(self.current_state, OrchestratorState) else OrchestratorState(self.current_state)
            previous = (
                self.previous_recoverable_state
                if isinstance(self.previous_recoverable_state, OrchestratorState)
                else OrchestratorState(self.previous_recoverable_state)
                if self.previous_recoverable_state is not None
                else None
            )
        except (TypeError, ValueError) as exc:
            raise StoreCorruptionError(f"unknown persisted state: {exc}") from exc
        if not isinstance(self.run_id, str) or _RUN_ID_RE.fullmatch(self.run_id) is None:
            raise StoreCorruptionError(f"invalid RUN_ID: {self.run_id!r}")
        if self.protocol_version != PROTOCOL_VERSION:
            raise StoreIncompatibleError(f"runtime protocol version {self.protocol_version!r}")
        if not isinstance(self.revision, int) or self.revision < 0:
            raise StoreCorruptionError(f"invalid revision: {self.revision!r}")
        for field_name, pattern in (
            ("task_id", _TASK_ID_RE),
            ("expected_next_task_id", _TASK_ID_RE),
            ("turn_id", _TURN_ID_RE),
            ("gate_id", _GATE_ID_RE),
        ):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, str) or pattern.fullmatch(value) is None
            ):
                raise StoreCorruptionError(f"invalid {field_name}: {value!r}")
        for field_name in ("baseline_sha", "result_sha"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or _SHA_RE.fullmatch(value) is None):
                raise StoreCorruptionError(f"invalid {field_name}: {value!r}")
        if state in PAUSED_STATES and previous is None:
            raise StoreCorruptionError("paused state is missing previous recoverable state")
        if state not in PAUSED_STATES and previous is not None:
            raise StoreCorruptionError("non-paused state unexpectedly has previous recoverable state")
        if state is OrchestratorState.HUMAN_GATE_WAIT and self.gate_id is None:
            raise StoreCorruptionError("HUMAN_GATE_WAIT is missing GATE_ID")
        if state is not OrchestratorState.HUMAN_GATE_WAIT and self.gate_id is not None:
            raise StoreCorruptionError("GATE_ID is present outside HUMAN_GATE_WAIT")
        if self.expected_next_task_id is not None:
            if state not in {
                OrchestratorState.PM_PLANNING,
                OrchestratorState.ERROR_LOCKED,
            }:
                raise StoreCorruptionError(
                    "expected next TASK_ID exists outside PM_PLANNING/ERROR_LOCKED"
                )
            if self.task_envelope is not None:
                raise StoreCorruptionError(
                    "expected next TASK_ID conflicts with retained task envelope"
                )
        if self.task_envelope is not None:
            if not isinstance(self.task_envelope, TaskEnvelope):
                raise StoreCorruptionError("invalid task envelope object")
            if self.task_envelope.task_id != self.task_id:
                raise StoreCorruptionError("task envelope TASK_ID mismatch")
        if state is OrchestratorState.DONE and self.expected_next_task_id is not None:
            raise StoreCorruptionError("DONE retains an expected next TASK_ID")
        object.__setattr__(self, "current_state", state)
        object.__setattr__(self, "previous_recoverable_state", previous)


@dataclass(frozen=True, slots=True)
class _EffectIntentMixin:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validated_task_id(value: str) -> str:
    if not isinstance(value, str) or _TASK_ID_RE.fullmatch(value) is None:
        raise UnsafePersistenceDataError(f"invalid task_id: {value!r}")
    return value


def _validated_gate_id(value: str) -> str:
    if not isinstance(value, str) or _GATE_ID_RE.fullmatch(value) is None:
        raise UnsafePersistenceDataError(f"invalid gate_id: {value!r}")
    return value


def _validated_sha(value: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise UnsafePersistenceDataError(f"invalid SHA: {value!r}")
    return value


def _validated_ref(value: str, *, target: bool) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or value.endswith("/")
        or value.endswith(".")
        or ".." in value
        or "//" in value
        or "@{" in value
        or _REF_FORBIDDEN_RE.search(value)
    ):
        raise UnsafePersistenceDataError(f"invalid ref: {value!r}")
    if target:
        try:
            require_ordinary_branch(value)
        except ProtectedBranchError as exc:
            raise UnsafePersistenceDataError(str(exc)) from exc
    return value


@dataclass(frozen=True, slots=True)
class BranchCreateIntent(_EffectIntentMixin):
    task_id: str
    branch: str
    source_ref: str
    baseline_sha: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        object.__setattr__(self, "branch", _validated_ref(self.branch, target=True))
        object.__setattr__(self, "source_ref", _validated_ref(self.source_ref, target=False))
        object.__setattr__(self, "baseline_sha", _validated_sha(self.baseline_sha))


@dataclass(frozen=True, slots=True)
class CommitIntent(_EffectIntentMixin):
    task_id: str
    branch: str
    baseline_sha: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        object.__setattr__(self, "branch", _validated_ref(self.branch, target=True))
        object.__setattr__(self, "baseline_sha", _validated_sha(self.baseline_sha))


@dataclass(frozen=True, slots=True)
class PushIntent(_EffectIntentMixin):
    task_id: str
    branch: str
    commit_sha: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        object.__setattr__(self, "branch", _validated_ref(self.branch, target=True))
        object.__setattr__(self, "commit_sha", _validated_sha(self.commit_sha))


@dataclass(frozen=True, slots=True)
class IntegrationFFIntent(_EffectIntentMixin):
    task_id: str
    source_ref: str
    target_ref: str
    baseline_sha: str
    commit_sha: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        object.__setattr__(self, "source_ref", _validated_ref(self.source_ref, target=False))
        object.__setattr__(self, "target_ref", _validated_ref(self.target_ref, target=True))
        object.__setattr__(self, "baseline_sha", _validated_sha(self.baseline_sha))
        object.__setattr__(self, "commit_sha", _validated_sha(self.commit_sha))


@dataclass(frozen=True, slots=True)
class GateCreateIntent(_EffectIntentMixin):
    task_id: str
    gate_id: str
    commit_sha: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _validated_task_id(self.task_id))
        object.__setattr__(self, "gate_id", _validated_gate_id(self.gate_id))
        object.__setattr__(
            self, "commit_sha", _validated_sha(self.commit_sha, optional=True)
        )


EffectIntent = (
    BranchCreateIntent
    | CommitIntent
    | PushIntent
    | IntegrationFFIntent
    | GateCreateIntent
)

_EFFECT_INTENT_TYPES: dict[EffectKind, type[_EffectIntentMixin]] = {
    EffectKind.BRANCH_CREATE: BranchCreateIntent,
    EffectKind.COMMIT: CommitIntent,
    EffectKind.PUSH: PushIntent,
    EffectKind.INTEGRATION_FF: IntegrationFFIntent,
    EffectKind.GATE_CREATE: GateCreateIntent,
}


@dataclass(frozen=True, slots=True)
class EffectRecord:
    effect_id: str
    idempotency_key: str
    kind: EffectKind
    status: EffectStatus
    intent: EffectIntent


@dataclass(frozen=True, slots=True)
class EffectRequest:
    action: EffectRequestAction
    record: EffectRecord


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class SQLiteStateStore:
    """Inspectable transactional store; never replaces incompatible data."""

    _REQUIRED_TABLES = frozenset({"metadata", "runtime_state", "effects", "gates"})

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                    )
                }
                if not tables:
                    self._create_schema(connection)
                elif tables != self._REQUIRED_TABLES:
                    raise StoreCorruptionError(
                        f"unexpected schema tables: expected {sorted(self._REQUIRED_TABLES)}, got {sorted(tables)}"
                    )
                self._validate_schema(connection)
                for row in connection.execute("SELECT * FROM effects"):
                    self._effect_from_row(row)
                connection.commit()
        except (StoreCorruptionError, StoreIncompatibleError):
            raise
        except sqlite3.DatabaseError as exc:
            raise StoreCorruptionError(str(exc)) from exc

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        statements = (
            """CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )""",
            """CREATE TABLE runtime_state (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                current_state TEXT NOT NULL,
                previous_recoverable_state TEXT,
                run_id TEXT NOT NULL,
                task_id TEXT,
                turn_id TEXT,
                gate_id TEXT,
                baseline_sha TEXT,
                result_sha TEXT,
                expected_next_task_id TEXT,
                task_envelope_json TEXT,
                protocol_version TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK (revision >= 0)
            )""",
            """CREATE TABLE effects (
                effect_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                intent_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE gates (
                gate_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
        )
        for statement in statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES ('protocol_version', ?)",
            (PROTOCOL_VERSION,),
        )

    @staticmethod
    def _read_schema_version(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        try:
            return int(row[0])
        except (TypeError, ValueError, IndexError) as exc:
            raise StoreCorruptionError("missing or malformed schema_version") from exc

    def _validate_schema(self, connection: sqlite3.Connection) -> None:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        schema_version = self._read_schema_version(connection)
        if schema_version != SCHEMA_VERSION:
            raise StoreIncompatibleError(
                f"schema version {schema_version}, expected {SCHEMA_VERSION}"
            )
        if metadata.get("protocol_version") != PROTOCOL_VERSION:
            raise StoreIncompatibleError(
                f"protocol version {metadata.get('protocol_version')!r}, expected {PROTOCOL_VERSION}"
            )

    @contextmanager
    def _checked_connection(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as connection:
            try:
                self._validate_schema(connection)
                yield connection
            except PersistenceError:
                raise
            except sqlite3.DatabaseError as exc:
                raise StoreCorruptionError(str(exc)) from exc

    def load_runtime(self) -> RuntimeRecord | None:
        try:
            with self._checked_connection() as connection:
                row = connection.execute("SELECT * FROM runtime_state WHERE singleton = 1").fetchone()
        except (PersistenceError, sqlite3.DatabaseError) as exc:
            if isinstance(exc, PersistenceError):
                raise
            raise StoreCorruptionError(str(exc)) from exc
        if row is None:
            return None
        envelope = None
        if row["task_envelope_json"] is not None:
            try:
                payload = json.loads(row["task_envelope_json"])
                if not isinstance(payload, dict):
                    raise TypeError("task envelope is not an object")
                envelope = TaskEnvelope.from_dict(payload)
            except (
                json.JSONDecodeError,
                ProtocolValidationError,
                TypeError,
                ValueError,
            ) as exc:
                raise StoreCorruptionError(f"malformed task envelope: {exc}") from exc
        return RuntimeRecord(
            current_state=row["current_state"],
            previous_recoverable_state=row["previous_recoverable_state"],
            run_id=row["run_id"],
            task_id=row["task_id"],
            turn_id=row["turn_id"],
            gate_id=row["gate_id"],
            baseline_sha=row["baseline_sha"],
            result_sha=row["result_sha"],
            expected_next_task_id=row["expected_next_task_id"],
            task_envelope=envelope,
            protocol_version=row["protocol_version"],
            revision=row["revision"],
        )

    def save_runtime(
        self, record: RuntimeRecord, *, expected_revision: int | None
    ) -> RuntimeRecord:
        next_revision = 0 if expected_revision is None else expected_revision + 1
        persisted = replace(record, revision=next_revision)
        values = (
            persisted.current_state.value,
            persisted.previous_recoverable_state.value if persisted.previous_recoverable_state else None,
            persisted.run_id,
            persisted.task_id,
            persisted.turn_id,
            persisted.gate_id,
            persisted.baseline_sha,
            persisted.result_sha,
            persisted.expected_next_task_id,
            _canonical_json(persisted.task_envelope.to_dict())
            if persisted.task_envelope is not None
            else None,
            persisted.protocol_version,
            persisted.revision,
        )
        try:
            with self._checked_connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                if expected_revision is None:
                    try:
                        connection.execute(
                            """INSERT INTO runtime_state(
                                   singleton, current_state, previous_recoverable_state,
                                   run_id, task_id, turn_id, gate_id, baseline_sha,
                                   result_sha, expected_next_task_id,
                                   task_envelope_json, protocol_version, revision
                               ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            values,
                        )
                    except sqlite3.IntegrityError as exc:
                        raise ConcurrentStateError("runtime state already exists") from exc
                else:
                    cursor = connection.execute(
                        """UPDATE runtime_state
                           SET current_state = ?, previous_recoverable_state = ?,
                               run_id = ?, task_id = ?, turn_id = ?, gate_id = ?,
                               baseline_sha = ?, result_sha = ?,
                               expected_next_task_id = ?, task_envelope_json = ?,
                               protocol_version = ?, revision = ?
                           WHERE singleton = 1 AND revision = ?""",
                        values + (expected_revision,),
                    )
                    if cursor.rowcount != 1:
                        raise ConcurrentStateError(
                            f"expected runtime revision {expected_revision}"
                        )
                connection.commit()
        except PersistenceError:
            raise
        except sqlite3.DatabaseError as exc:
            raise StoreCorruptionError(str(exc)) from exc
        return persisted

    def operational_record_count(self) -> int:
        with self._checked_connection() as connection:
            runtime_count = connection.execute(
                "SELECT COUNT(*) FROM runtime_state"
            ).fetchone()[0]
            effect_count = connection.execute("SELECT COUNT(*) FROM effects").fetchone()[0]
            gate_count = connection.execute("SELECT COUNT(*) FROM gates").fetchone()[0]
        return int(runtime_count) + int(effect_count) + int(gate_count)

    def request_effect(
        self,
        *,
        effect_id: str,
        idempotency_key: str,
        kind: EffectKind | str,
        intent: EffectIntent,
    ) -> EffectRequest:
        if not effect_id or not idempotency_key:
            raise IdempotencyIntentMismatchError("effect_id and idempotency_key must be non-empty")
        try:
            parsed_kind = kind if isinstance(kind, EffectKind) else EffectKind(kind)
        except (TypeError, ValueError) as exc:
            raise IdempotencyIntentMismatchError(f"unknown effect kind: {kind!r}") from exc
        expected_intent_type = _EFFECT_INTENT_TYPES[parsed_kind]
        if type(intent) is not expected_intent_type:
            raise UnsafePersistenceDataError(
                f"{parsed_kind.value} requires {expected_intent_type.__name__}"
            )
        intent_data = intent.to_dict()
        intent_json = _canonical_json(intent_data)
        now = _utc_now()

        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            by_id = connection.execute(
                "SELECT * FROM effects WHERE effect_id = ?", (effect_id,)
            ).fetchone()
            by_key = connection.execute(
                "SELECT * FROM effects WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            existing = by_id or by_key
            if existing is None:
                connection.execute(
                    """INSERT INTO effects(
                           effect_id, idempotency_key, kind, status, intent_json,
                           created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        effect_id,
                        idempotency_key,
                        parsed_kind.value,
                        EffectStatus.NOT_STARTED.value,
                        intent_json,
                        now,
                        now,
                    ),
                )
                connection.commit()
                record = EffectRecord(
                    effect_id, idempotency_key, parsed_kind, EffectStatus.NOT_STARTED, intent
                )
                return EffectRequest(EffectRequestAction.EXECUTE, record)

            if (
                existing["effect_id"] != effect_id
                or existing["idempotency_key"] != idempotency_key
                or existing["kind"] != parsed_kind.value
                or existing["intent_json"] != intent_json
            ):
                raise IdempotencyIntentMismatchError(
                    "same effect identity used with different immutable intent"
                )
            record = self._effect_from_row(existing)
            if record.status is EffectStatus.COMPLETED:
                connection.commit()
                return EffectRequest(EffectRequestAction.SKIP_COMPLETED, record)
            if record.status in {EffectStatus.IN_PROGRESS, EffectStatus.AMBIGUOUS}:
                raise AmbiguousEffectError(
                    f"effect {effect_id} requires deterministic reconciliation"
                )
            connection.commit()
            return EffectRequest(EffectRequestAction.EXECUTE, record)

    def load_effect(self, effect_id: str) -> EffectRecord | None:
        with self._checked_connection() as connection:
            row = connection.execute(
                "SELECT * FROM effects WHERE effect_id = ?", (effect_id,)
            ).fetchone()
        return self._effect_from_row(row) if row is not None else None

    @staticmethod
    def _effect_from_row(row: sqlite3.Row) -> EffectRecord:
        try:
            kind = EffectKind(row["kind"])
            intent_data = json.loads(row["intent_json"])
            if not isinstance(intent_data, dict):
                raise TypeError("effect intent is not an object")
            intent_type = _EFFECT_INTENT_TYPES[kind]
            intent = intent_type(**intent_data)
            return EffectRecord(
                effect_id=row["effect_id"],
                idempotency_key=row["idempotency_key"],
                kind=kind,
                status=EffectStatus(row["status"]),
                intent=intent,
            )
        except (
            ValueError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            UnsafePersistenceDataError,
        ) as exc:
            raise StoreCorruptionError(f"malformed effect record: {exc}") from exc

    def effects_with_statuses(
        self, statuses: tuple[EffectStatus, ...]
    ) -> tuple[EffectRecord, ...]:
        if not statuses:
            return ()
        placeholders = ",".join("?" for _ in statuses)
        with self._checked_connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM effects WHERE status IN ({placeholders}) ORDER BY effect_id",
                tuple(status.value for status in statuses),
            ).fetchall()
        return tuple(self._effect_from_row(row) for row in rows)

    def begin_effect(self, effect_id: str) -> EffectRecord:
        return self._advance_effect(effect_id, EffectStatus.NOT_STARTED, EffectStatus.IN_PROGRESS)

    def complete_effect(self, effect_id: str) -> EffectRecord:
        current = self.load_effect(effect_id)
        if current is not None and current.status is EffectStatus.COMPLETED:
            return current
        return self._advance_effect(effect_id, EffectStatus.IN_PROGRESS, EffectStatus.COMPLETED)

    def _advance_effect(
        self, effect_id: str, expected: EffectStatus, target: EffectStatus
    ) -> EffectRecord:
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE effects SET status = ?, updated_at = ? WHERE effect_id = ? AND status = ?",
                (target.value, _utc_now(), effect_id, expected.value),
            )
            if cursor.rowcount != 1:
                row = connection.execute(
                    "SELECT status FROM effects WHERE effect_id = ?", (effect_id,)
                ).fetchone()
                observed = row["status"] if row is not None else "MISSING"
                raise AmbiguousEffectError(
                    f"effect {effect_id}: expected {expected.value}, observed {observed}"
                )
            connection.commit()
        record = self.load_effect(effect_id)
        if record is None:
            raise StoreCorruptionError(f"effect disappeared after update: {effect_id}")
        return record

    def reconcile_effect(
        self, effect_id: str, outcome: ReconciliationOutcome | str
    ) -> EffectRecord:
        try:
            parsed = outcome if isinstance(outcome, ReconciliationOutcome) else ReconciliationOutcome(outcome)
        except (TypeError, ValueError) as exc:
            raise AmbiguousEffectError(f"unknown reconciliation outcome: {outcome!r}") from exc
        target = {
            ReconciliationOutcome.NO_EFFECT: EffectStatus.NOT_STARTED,
            ReconciliationOutcome.COMPLETED: EffectStatus.COMPLETED,
            ReconciliationOutcome.UNKNOWN: EffectStatus.AMBIGUOUS,
        }[parsed]
        return self._advance_effect(effect_id, EffectStatus.IN_PROGRESS, target)

    def record_gate(self, manifest: HumanGateManifest) -> HumanGateManifest:
        payload = _canonical_json(manifest.to_dict())
        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM gates WHERE gate_id = ?", (manifest.gate_id,)
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO gates(gate_id, task_id, status, manifest_json, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (manifest.gate_id, manifest.task_id, manifest.status.value, payload, _utc_now()),
                )
            elif row["manifest_json"] != payload:
                raise GateReplayError(f"gate ID collision: {manifest.gate_id}")
            connection.commit()
        return manifest

    def load_gate(self, gate_id: str) -> HumanGateManifest | None:
        with self._checked_connection() as connection:
            row = connection.execute(
                "SELECT manifest_json FROM gates WHERE gate_id = ?", (gate_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return HumanGateManifest.from_dict(json.loads(row["manifest_json"]))
        except (json.JSONDecodeError, ProtocolValidationError, TypeError, ValueError) as exc:
            raise StoreCorruptionError(f"malformed gate record {gate_id}: {exc}") from exc

    def pending_gates_for_task(self, task_id: str) -> tuple[HumanGateManifest, ...]:
        with self._checked_connection() as connection:
            rows = connection.execute(
                "SELECT manifest_json FROM gates WHERE task_id = ? AND status = ? ORDER BY gate_id",
                (task_id, GateStatus.PENDING.value),
            ).fetchall()
        manifests: list[HumanGateManifest] = []
        for row in rows:
            try:
                manifests.append(
                    HumanGateManifest.from_dict(json.loads(row["manifest_json"]))
                )
            except (
                json.JSONDecodeError,
                ProtocolValidationError,
                TypeError,
                ValueError,
            ) as exc:
                raise StoreCorruptionError(
                    f"malformed pending gate record for {task_id}: {exc}"
                ) from exc
        return tuple(manifests)

    def decide_gate(self, gate_id: str, decision: GateStatus | str) -> HumanGateManifest:
        try:
            parsed = decision if isinstance(decision, GateStatus) else GateStatus(decision)
        except (TypeError, ValueError) as exc:
            raise GateReplayError(f"unknown gate decision: {decision!r}") from exc
        if parsed is GateStatus.PENDING:
            raise GateReplayError("PENDING is not a terminal decision")

        with self._checked_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT manifest_json, status FROM gates WHERE gate_id = ?", (gate_id,)
            ).fetchone()
            if row is None:
                raise GateReplayError(f"unknown gate: {gate_id}")
            if row["status"] != GateStatus.PENDING.value:
                raise GateReplayError(f"terminal gate replay: {gate_id}")
            try:
                manifest = HumanGateManifest.from_dict(json.loads(row["manifest_json"]))
            except (json.JSONDecodeError, ProtocolValidationError, TypeError, ValueError) as exc:
                raise StoreCorruptionError(f"malformed gate record {gate_id}: {exc}") from exc
            terminal = manifest.terminal(parsed)
            connection.execute(
                "UPDATE gates SET status = ?, manifest_json = ?, updated_at = ? WHERE gate_id = ?",
                (parsed.value, _canonical_json(terminal.to_dict()), _utc_now(), gate_id),
            )
            connection.commit()
        return terminal

    def raw_metadata(self) -> dict[str, str]:
        """Small inspection helper used by compatibility tests."""
        with self._checked_connection() as connection:
            return dict(connection.execute("SELECT key, value FROM metadata"))
