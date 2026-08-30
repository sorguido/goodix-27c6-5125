"""Single-file SQLite persistence and idempotency ledger for O001."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterator, Mapping

from .protocols import (
    GateStatus,
    HumanGateManifest,
    PROTOCOL_VERSION,
    ProtocolValidationError,
)
from .state import OrchestratorState, PAUSED_STATES


SCHEMA_VERSION = 1
_RUN_ID_RE = re.compile(r"^ORCH-[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "auth",
        "authorization",
        "biometric",
        "credential",
        "password",
        "private_key",
        "protected_material",
        "psk",
        "secret",
        "token",
    }
)


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
        object.__setattr__(self, "current_state", state)
        object.__setattr__(self, "previous_recoverable_state", previous)


@dataclass(frozen=True, slots=True)
class EffectRecord:
    effect_id: str
    idempotency_key: str
    kind: EffectKind
    status: EffectStatus
    intent: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EffectRequest:
    action: EffectRequestAction
    record: EffectRecord


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _validate_safe_metadata(value: Any, path: str = "intent") -> None:
    if isinstance(value, bytes):
        raise UnsafePersistenceDataError(f"binary data rejected at {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise UnsafePersistenceDataError(f"non-string key at {path}")
            normalized = key.lower().replace("-", "_")
            if normalized in _FORBIDDEN_METADATA_KEYS or any(
                token in normalized for token in ("password", "private_key", "secret", "token", "psk")
            ):
                raise UnsafePersistenceDataError(f"forbidden metadata key at {path}.{key}")
            _validate_safe_metadata(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_safe_metadata(item, f"{path}[{index}]")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise UnsafePersistenceDataError(f"unsupported metadata type at {path}: {type(value).__name__}")


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

    def _validate_schema(self, connection: sqlite3.Connection) -> None:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        try:
            schema_version = int(metadata["schema_version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StoreCorruptionError("missing or malformed schema_version") from exc
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
        return RuntimeRecord(
            current_state=row["current_state"],
            previous_recoverable_state=row["previous_recoverable_state"],
            run_id=row["run_id"],
            task_id=row["task_id"],
            turn_id=row["turn_id"],
            gate_id=row["gate_id"],
            baseline_sha=row["baseline_sha"],
            result_sha=row["result_sha"],
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
                                   result_sha, protocol_version, revision
                               ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            values,
                        )
                    except sqlite3.IntegrityError as exc:
                        raise ConcurrentStateError("runtime state already exists") from exc
                else:
                    cursor = connection.execute(
                        """UPDATE runtime_state
                           SET current_state = ?, previous_recoverable_state = ?,
                               run_id = ?, task_id = ?, turn_id = ?, gate_id = ?,
                               baseline_sha = ?, result_sha = ?, protocol_version = ?,
                               revision = ?
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

    def request_effect(
        self,
        *,
        effect_id: str,
        idempotency_key: str,
        kind: EffectKind | str,
        intent: Mapping[str, Any],
    ) -> EffectRequest:
        if not effect_id or not idempotency_key:
            raise IdempotencyIntentMismatchError("effect_id and idempotency_key must be non-empty")
        try:
            parsed_kind = kind if isinstance(kind, EffectKind) else EffectKind(kind)
        except (TypeError, ValueError) as exc:
            raise IdempotencyIntentMismatchError(f"unknown effect kind: {kind!r}") from exc
        intent_data = dict(intent)
        _validate_safe_metadata(intent_data)
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
                    effect_id, idempotency_key, parsed_kind, EffectStatus.NOT_STARTED, intent_data
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
            intent = json.loads(row["intent_json"])
            if not isinstance(intent, dict):
                raise TypeError("effect intent is not an object")
            _validate_safe_metadata(intent)
            return EffectRecord(
                effect_id=row["effect_id"],
                idempotency_key=row["idempotency_key"],
                kind=EffectKind(row["kind"]),
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
