import sqlite3
import tempfile
import unittest
from pathlib import Path

from goodix_orchestrator.engine import DeterministicEngine
from goodix_orchestrator.persistence import (
    ConcurrentStateError,
    RuntimeRecord,
    SQLiteStateStore,
    StoreCorruptionError,
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


if __name__ == "__main__":
    unittest.main()
