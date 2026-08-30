# SPDX-License-Identifier: GPL-2.0-or-later
import sqlite3
import tempfile
import unittest
from pathlib import Path

from goodix_orchestrator.engine import DeterministicEngine, EngineError
from goodix_orchestrator.persistence import (
    CommitIntent,
    ConcurrentStateError,
    EffectKind,
    RuntimeRecord,
    SQLiteStateStore,
    StoreCorruptionError,
    StoreIncompatibleError,
    SCHEMA_VERSION,
)
from goodix_orchestrator.policy import Capability, CapabilityPolicy
from goodix_orchestrator.state import OrchestratorState


class PersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.store = SQLiteStateStore(self.path)
        self.store.initialize()

    def test_transactional_compare_and_swap_and_reload(self) -> None:
        self.assertEqual(SCHEMA_VERSION, 3)
        first = self.store.save_runtime(
            RuntimeRecord(OrchestratorState.BOOTSTRAP, "ORCH-20260830-001"),
            expected_revision=None,
        )
        second = self.store.save_runtime(
            RuntimeRecord(
                OrchestratorState.IDLE,
                "ORCH-20260830-001",
                revision=first.revision,
            ),
            expected_revision=first.revision,
        )
        self.assertEqual(second.revision, 1)
        self.assertEqual(self.store.load_runtime(), second)
        with self.assertRaises(ConcurrentStateError):
            self.store.save_runtime(first, expected_revision=first.revision)
        self.assertEqual(self.store.load_runtime(), second)

    def test_clean_engine_restart(self) -> None:
        policy = CapabilityPolicy((Capability.HOST_READ,))
        engine = DeterministicEngine.create(
            self.store, policy, run_id="ORCH-20260830-002"
        )
        engine.bootstrap_complete()
        recovered = DeterministicEngine.recover(
            self.path, policy, expected_run_id="ORCH-20260830-002"
        )
        self.assertEqual(recovered.state, OrchestratorState.IDLE)
        self.assertIsNotNone(recovered.engine)

    def test_create_is_fresh_only_and_second_create_is_denied(self) -> None:
        policy = CapabilityPolicy((Capability.HOST_READ,))
        engine = DeterministicEngine.create(
            self.store, policy, run_id="ORCH-20260830-006"
        )
        self.assertEqual(engine.state, OrchestratorState.BOOTSTRAP)
        with self.assertRaises(EngineError) as caught:
            DeterministicEngine.create(
                self.store, policy, run_id="ORCH-20260830-006"
            )
        self.assertEqual(
            caught.exception.code, "EXISTING_STATE_REQUIRES_RECOVERY"
        )

    def test_direct_engine_construction_is_denied(self) -> None:
        runtime = self.store.save_runtime(
            RuntimeRecord(OrchestratorState.BOOTSTRAP, "ORCH-20260830-007"),
            expected_revision=None,
        )
        with self.assertRaises(EngineError) as caught:
            DeterministicEngine(self.store, CapabilityPolicy(), runtime)
        self.assertEqual(caught.exception.code, "DIRECT_CONSTRUCTION_FORBIDDEN")

    def test_create_rejects_nonfresh_store_even_without_runtime(self) -> None:
        self.store.request_effect(
            effect_id="EFFECT-FRESHNESS",
            idempotency_key="TASK-001:COMMIT:freshness",
            kind=EffectKind.COMMIT,
            intent=CommitIntent(
                "TASK-001", "ai-executor/task-001", "a" * 40
            ),
        )
        with self.assertRaises(EngineError) as caught:
            DeterministicEngine.create(
                self.store, CapabilityPolicy(), run_id="ORCH-20260830-008"
            )
        self.assertEqual(
            caught.exception.code, "EXISTING_STATE_REQUIRES_RECOVERY"
        )

    def test_corrupt_file_fails_closed_without_replacement(self) -> None:
        corrupt = Path(self.temp.name) / "corrupt.sqlite3"
        payload = b"not a sqlite database"
        corrupt.write_bytes(payload)
        recovered = DeterministicEngine.recover(
            corrupt, CapabilityPolicy(), expected_run_id="ORCH-20260830-003"
        )
        self.assertEqual(recovered.state, OrchestratorState.ERROR_LOCKED)
        self.assertEqual(corrupt.read_bytes(), payload)

    def test_incompatible_schema_fails_closed(self) -> None:
        connection = sqlite3.connect(self.path)
        connection.execute(
            "UPDATE metadata SET value = '999' WHERE key = 'schema_version'"
        )
        connection.commit()
        connection.close()
        recovered = DeterministicEngine.recover(
            self.path, CapabilityPolicy(), expected_run_id="ORCH-20260830-004"
        )
        self.assertEqual(recovered.state, OrchestratorState.ERROR_LOCKED)
        self.assertEqual(recovered.error_code, "STORE_INCOMPATIBLE")

    def test_unknown_persisted_state_is_corruption(self) -> None:
        self.store.save_runtime(
            RuntimeRecord(OrchestratorState.BOOTSTRAP, "ORCH-20260830-005"),
            expected_revision=None,
        )
        connection = sqlite3.connect(self.path)
        connection.execute(
            "UPDATE runtime_state SET current_state = 'TEXT_GUESS' WHERE singleton = 1"
        )
        connection.commit()
        connection.close()
        with self.assertRaises(StoreCorruptionError):
            self.store.load_runtime()

    def create_legacy_v1(
        self,
        path: Path,
        *,
        state: str,
        task_id: str | None = None,
        baseline_sha: str | None = None,
        result_sha: str | None = None,
    ) -> None:
        connection = sqlite3.connect(path)
        connection.executescript(
            """
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO metadata VALUES ('schema_version', '1');
            INSERT INTO metadata VALUES ('protocol_version', '1.0');
            CREATE TABLE runtime_state (
                singleton INTEGER PRIMARY KEY,
                current_state TEXT NOT NULL,
                previous_recoverable_state TEXT,
                run_id TEXT NOT NULL,
                task_id TEXT,
                turn_id TEXT,
                gate_id TEXT,
                baseline_sha TEXT,
                result_sha TEXT,
                protocol_version TEXT NOT NULL,
                revision INTEGER NOT NULL
            );
            CREATE TABLE effects (
                effect_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL, status TEXT NOT NULL, intent_json TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE gates (
                gate_id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
                status TEXT NOT NULL, manifest_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """INSERT INTO runtime_state VALUES (
                   1, ?, NULL, 'ORCH-20260830-009', ?, NULL,
                   NULL, ?, ?, '1.0', 0
               )""",
            (state, task_id, baseline_sha, result_sha),
        )
        connection.commit()
        connection.close()

    @staticmethod
    def legacy_snapshot(path: Path) -> tuple[tuple, tuple, tuple[str, ...]]:
        connection = sqlite3.connect(path)
        metadata = tuple(
            connection.execute("SELECT key, value FROM metadata ORDER BY key")
        )
        runtime = connection.execute("SELECT * FROM runtime_state").fetchone()
        columns = tuple(
            row[1] for row in connection.execute("PRAGMA table_info(runtime_state)")
        )
        connection.close()
        return metadata, runtime, columns

    def test_v1_bootstrap_is_incompatible_and_remains_unmodified(self) -> None:
        legacy_path = Path(self.temp.name) / "legacy-bootstrap-v1.sqlite3"
        self.create_legacy_v1(legacy_path, state="BOOTSTRAP")
        before = self.legacy_snapshot(legacy_path)
        before_bytes = legacy_path.read_bytes()

        with self.assertRaises(StoreIncompatibleError):
            SQLiteStateStore(legacy_path).initialize()
        recovered = DeterministicEngine.recover(
            legacy_path,
            CapabilityPolicy(),
            expected_run_id="ORCH-20260830-009",
        )

        self.assertEqual(recovered.state, OrchestratorState.ERROR_LOCKED)
        self.assertEqual(recovered.error_code, "STORE_INCOMPATIBLE")
        self.assertIsNone(recovered.engine)
        self.assertEqual(self.legacy_snapshot(legacy_path), before)
        self.assertEqual(legacy_path.read_bytes(), before_bytes)
        self.assertEqual(dict(before[0])["schema_version"], "1")
        self.assertNotIn("expected_next_task_id", before[2])
        self.assertNotIn("task_envelope_json", before[2])

    def test_v1_in_flight_state_is_incompatible_and_remains_unmodified(self) -> None:
        legacy_path = Path(self.temp.name) / "legacy-in-flight-v1.sqlite3"
        self.create_legacy_v1(
            legacy_path,
            state="PM_PLANNING",
            task_id="TASK-LEGACY",
            baseline_sha="a" * 40,
            result_sha="b" * 40,
        )
        before = self.legacy_snapshot(legacy_path)
        before_bytes = legacy_path.read_bytes()

        recovered = DeterministicEngine.recover(
            legacy_path,
            CapabilityPolicy(),
            expected_run_id="ORCH-20260830-009",
        )

        self.assertEqual(recovered.state, OrchestratorState.ERROR_LOCKED)
        self.assertEqual(recovered.error_code, "STORE_INCOMPATIBLE")
        self.assertIsNone(recovered.engine)
        self.assertEqual(self.legacy_snapshot(legacy_path), before)
        self.assertEqual(legacy_path.read_bytes(), before_bytes)

    def test_v2_store_is_incompatible_and_remains_unmodified(self) -> None:
        legacy_path = Path(self.temp.name) / "legacy-v2.sqlite3"
        connection = sqlite3.connect(legacy_path)
        connection.executescript(
            """
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO metadata VALUES ('schema_version', '2');
            INSERT INTO metadata VALUES ('protocol_version', '1.0');
            CREATE TABLE runtime_state (
                singleton INTEGER PRIMARY KEY, current_state TEXT NOT NULL,
                previous_recoverable_state TEXT, run_id TEXT NOT NULL,
                task_id TEXT, turn_id TEXT, gate_id TEXT, baseline_sha TEXT,
                result_sha TEXT, expected_next_task_id TEXT,
                task_envelope_json TEXT, protocol_version TEXT NOT NULL,
                revision INTEGER NOT NULL
            );
            CREATE TABLE effects (
                effect_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL, status TEXT NOT NULL, intent_json TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE gates (
                gate_id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
                status TEXT NOT NULL, manifest_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        connection.commit()
        connection.close()
        before = legacy_path.read_bytes()
        recovered = DeterministicEngine.recover(legacy_path, CapabilityPolicy())
        self.assertEqual(recovered.error_code, "STORE_INCOMPATIBLE")
        self.assertEqual(legacy_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
