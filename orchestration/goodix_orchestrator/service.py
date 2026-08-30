# SPDX-License-Identifier: GPL-2.0-or-later
"""Local-first O003 service, operator controls, locking and re-probe policy."""

from __future__ import annotations

import fcntl
import json
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol

from .codex_adapter import CodexAppServer
from .engine import DeterministicEngine
from .persistence import (
    EffectStatus,
    MaintenanceEpochRecord,
    OperatorStateRecord,
    SQLiteStateStore,
)
from .state import OrchestratorState
from .structured_output import ModelRoute


@dataclass(frozen=True, slots=True)
class ServiceError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    config_dir: Path
    state_dir: Path
    state_db: Path
    lock_file: Path
    backup_dir: Path

    @classmethod
    def discover(cls, env: dict[str, str] | None = None) -> "RuntimePaths":
        values = os.environ if env is None else env
        home = Path(values.get("HOME", str(Path.home())))
        config_base = Path(values.get("XDG_CONFIG_HOME", home / ".config"))
        state_base = Path(values.get("XDG_STATE_HOME", home / ".local" / "state"))
        config = config_base / "goodix-orchestrator"
        state = state_base / "goodix-orchestrator"
        return cls(config, state, state / "state.sqlite", state / "service.lock", state / "backups")

    def ensure(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)


class SingleInstanceLock:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._handle: Any = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="ascii")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise ServiceError("SINGLE_INSTANCE_COLLISION", str(self.path)) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        self._handle = handle

    def release(self) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


_SECRET_KEYS = re.compile(r"token|authorization|password|secret|email|psk", re.I)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SECRET_KEYS.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str) and re.search(r"(?:gh[opusr]_|Bearer\s+)[A-Za-z0-9_-]{12,}", value):
        return "[REDACTED]"
    return value


def log_event(event: str, **fields: Any) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "event": event,
        **redact(fields),
    }
    print(json.dumps(payload, sort_keys=True, ensure_ascii=True), flush=True)


@dataclass(frozen=True, slots=True)
class GitSnapshot:
    main_sha: str
    development_sha: str | None
    task_id: str | None = None
    task_branch: str | None = None


class AvailabilityProbe(Protocol):
    def probe_exact_route(self) -> tuple[bool, str]: ...


class CodexRouteAvailabilityProbe:
    """Read-only account/model/rate-limit probe for one exact route."""

    def __init__(
        self,
        store: SQLiteStateStore,
        route: ModelRoute,
        *,
        executable: str = "codex",
    ) -> None:
        self.store = store
        self.route = route
        self.executable = executable

    def probe_exact_route(self) -> tuple[bool, str]:
        server = CodexAppServer(executable=self.executable, store=self.store)
        try:
            server.start()
            if server.account_mode() != "CHATGPT":
                return False, "AUTH_NOT_CHATGPT"
            server.require_route(self.route)
            telemetry = server.rate_limit_telemetry()
            if not telemetry.get("available", False):
                return False, "RATE_LIMIT_SIGNAL_UNAVAILABLE"
            buckets = telemetry.get("buckets", ())
            if any(bool(bucket.get("reached")) for bucket in buckets if isinstance(bucket, dict)):
                return False, "RATE_LIMIT_REACHED"
            return True, "EXACT_ROUTE_AVAILABLE"
        except Exception as exc:  # Adapter exceptions are reduced to a redacted class.
            return False, f"PROBE_{type(exc).__name__}"
        finally:
            server.close()


class OperatorController:
    def __init__(
        self,
        store: SQLiteStateStore,
        *,
        snapshot: Callable[[], GitSnapshot],
        fetch: Callable[[], None] | None = None,
        is_ancestor: Callable[[str, str], bool] | None = None,
    ) -> None:
        self.store = store
        self.snapshot = snapshot
        self.fetch = fetch or (lambda: None)
        self.is_ancestor = is_ancestor or (lambda old, new: old == new)

    def _operator(self) -> OperatorStateRecord:
        return self.store.load_operator_state()

    def status(self, engine: DeterministicEngine | None = None) -> dict[str, Any]:
        operator = self._operator()
        runtime = engine.runtime if engine is not None else self.store.load_runtime()
        git = self.store.load_git_state()
        snapshot = self.snapshot()
        contexts = self.store.list_contexts(active_only=True)
        active = contexts[-1] if contexts else None
        return redact(
            {
                "service_state": "LOCAL_PROCESS_QUERY",
                "state_machine_state": runtime.current_state.value if runtime else "UNINITIALIZED",
                "RUN_ID": runtime.run_id if runtime else None,
                "TASK_ID": runtime.task_id if runtime else None,
                "TURN_ID": runtime.turn_id if runtime else None,
                "active_role": active.role if active else None,
                "effective_model": active.effective_model_id if active else None,
                "effective_reasoning_effort": active.effective_reasoning_effort if active else None,
                "task_branch": snapshot.task_branch,
                "integration_branch": "development",
                "main_sha": snapshot.main_sha,
                "development_sha": snapshot.development_sha,
                "last_significant_event": operator.last_event,
                "pending_GATE_ID": runtime.gate_id if runtime else None,
                "pause_reason": runtime.current_state.value if runtime and runtime.current_state.value.startswith("PAUSED_") else None,
                "availability_class": operator.availability_class,
                "operator_pause": operator.operator_paused,
                "maintenance_lock": operator.maintenance_id,
                "emergency_stop_latch": operator.emergency_stop_latched,
                "NO_INFLIGHT_TURN": not operator.inflight_turn,
                "NO_INFLIGHT_EFFECT": not operator.inflight_effect,
                "last_redacted_error_class": operator.last_error_class,
                "persisted_integration_sha": git.integration_sha if git else None,
            }
        )

    def pause(self) -> OperatorStateRecord:
        state = replace(self._operator(), operator_paused=True, last_event="OPERATOR_PAUSE")
        return self.store.save_operator_state(state)

    def resume(self) -> OperatorStateRecord:
        state = self._operator()
        if state.emergency_stop_latched:
            raise ServiceError("EMERGENCY_STOP_LATCHED", "use emergency-clear after reconciliation")
        if state.maintenance_id is not None:
            raise ServiceError("MAINTENANCE_LOCKED", state.maintenance_id)
        if state.inflight_turn or state.inflight_effect:
            raise ServiceError("NOT_QUIESCENT", "turn/effect remains in flight")
        return self.store.save_operator_state(
            replace(state, operator_paused=False, last_event="OPERATOR_RESUME")
        )

    def emergency_stop(self) -> OperatorStateRecord:
        state = replace(
            self._operator(),
            operator_paused=True,
            emergency_stop_latched=True,
            last_event="EMERGENCY_STOP_LATCHED",
        )
        return self.store.save_operator_state(state)

    def emergency_clear(self) -> OperatorStateRecord:
        state = self._operator()
        if state.inflight_turn or state.inflight_effect:
            raise ServiceError("RECONCILIATION_REQUIRED", "in-flight state is not reconciled")
        unresolved = self.store.effects_with_statuses(
            (EffectStatus.IN_PROGRESS, EffectStatus.AMBIGUOUS)
        )
        if unresolved:
            raise ServiceError(
                "RECONCILIATION_REQUIRED",
                ",".join(effect.effect_id for effect in unresolved),
            )
        git = self.store.load_git_state()
        snapshot = self.snapshot()
        if git is not None and (
            snapshot.development_sha != git.integration_sha
            or (git.main_sha is not None and snapshot.main_sha != git.main_sha)
        ):
            raise ServiceError("RECONCILIATION_REQUIRED", "Git state mismatch")
        return self.store.save_operator_state(
            replace(state, emergency_stop_latched=False, last_event="EMERGENCY_STOP_CLEARED")
        )

    def maintenance_enter(self, maintenance_id: str) -> MaintenanceEpochRecord:
        state = self._operator()
        if state.inflight_turn or state.inflight_effect:
            raise ServiceError("MAINTENANCE_ENTRY_DENIED_NOT_QUIESCENT", maintenance_id)
        if state.maintenance_id is not None:
            raise ServiceError("MAINTENANCE_ALREADY_ACTIVE", state.maintenance_id)
        snapshot = self.snapshot()
        runtime = self.store.load_runtime()
        git = self.store.load_git_state()
        epoch = MaintenanceEpochRecord(
            maintenance_id=maintenance_id,
            entered_at=datetime.now(UTC).isoformat(timespec="seconds"),
            main_sha=snapshot.main_sha,
            development_sha=snapshot.development_sha,
            task_id=snapshot.task_id,
            task_branch=snapshot.task_branch,
            orchestrator_state=runtime.current_state.value if runtime else "UNINITIALIZED",
            integration_baseline=git.integration_sha if git else snapshot.development_sha,
        )
        self.store.save_maintenance_epoch(epoch)
        self.store.save_operator_state(
            replace(
                state,
                operator_paused=True,
                maintenance_id=maintenance_id,
                last_event="MAINTENANCE_ENTERED",
            )
        )
        return epoch

    def maintenance_exit(self) -> MaintenanceEpochRecord:
        state = self._operator()
        if state.maintenance_id is None:
            raise ServiceError("MAINTENANCE_NOT_ACTIVE", "no epoch")
        if state.inflight_turn or state.inflight_effect:
            raise ServiceError("MAINTENANCE_EXIT_DENIED_NOT_QUIESCENT", state.maintenance_id)
        epoch = self.store.load_maintenance_epoch(state.maintenance_id)
        if epoch is None or epoch.exited_at is not None:
            raise ServiceError("MAINTENANCE_EPOCH_INVALID", state.maintenance_id)
        self.fetch()
        current = self.snapshot()
        reconciliation = self._classify_reconciliation(epoch, current)
        if reconciliation in {"DIVERGED", "NON_FF_DEVELOPMENT"}:
            self.store.save_operator_state(
                replace(
                    state,
                    operator_paused=True,
                    last_event="MAINTENANCE_RECONCILIATION_BLOCKED",
                    last_error_class="PAUSED_INFRASTRUCTURE",
                )
            )
            raise ServiceError("PAUSED_INFRASTRUCTURE", reconciliation)
        closed = replace(
            epoch,
            exited_at=datetime.now(UTC).isoformat(timespec="seconds"),
            reconciliation=reconciliation,
        )
        self.store.save_maintenance_epoch(closed)
        event = "MAINTENANCE_EXITED"
        if epoch.task_id is not None and (
            current.development_sha != epoch.development_sha or current.main_sha != epoch.main_sha
        ):
            event = "MAINTENANCE_EXITED_REPLAN_REQUIRED"
        self.store.save_operator_state(
            replace(state, maintenance_id=None, operator_paused=True, last_event=event)
        )
        return closed

    def _classify_reconciliation(
        self,
        epoch: MaintenanceEpochRecord, current: GitSnapshot
    ) -> str:
        if current.main_sha == epoch.main_sha and current.development_sha == epoch.development_sha:
            return "NO_RELEVANT_GIT_CHANGE"
        if current.development_sha is None and epoch.development_sha is not None:
            return "DIVERGED"
        if current.development_sha != epoch.development_sha:
            if epoch.development_sha is None or current.development_sha is None:
                return "DIVERGED"
            if not self.is_ancestor(epoch.development_sha, current.development_sha):
                return "NON_FF_DEVELOPMENT"
            if current.main_sha != epoch.main_sha:
                return "DIVERGED"
            return "DEVELOPMENT_CHANGED_REPLAN_REQUIRED"
        if current.main_sha != epoch.main_sha and epoch.development_sha is not None:
            if not self.is_ancestor(epoch.development_sha, current.main_sha):
                return "DIVERGED"
        return "MAIN_CHANGED_OPERATOR_RECONCILIATION_REQUIRED"


class ReprobeController:
    def __init__(
        self,
        store: SQLiteStateStore,
        probe: AvailabilityProbe,
        *,
        interval_seconds: int = 900,
        reconcile: Callable[[], bool] = lambda: True,
    ) -> None:
        if not isinstance(interval_seconds, int) or not 60 <= interval_seconds <= 86400:
            raise ServiceError("INVALID_REPROBE_INTERVAL", repr(interval_seconds))
        self.store = store
        self.probe = probe
        self.interval_seconds = interval_seconds
        self.reconcile = reconcile

    def tick(self, engine: DeterministicEngine, *, now: datetime | None = None) -> bool:
        if engine.state not in {
            OrchestratorState.PAUSED_RATE_LIMIT,
            OrchestratorState.PAUSED_MODEL_UNAVAILABLE,
        }:
            return False
        operator = self.store.load_operator_state()
        if operator.operator_paused or operator.maintenance_id or operator.emergency_stop_latched:
            return False
        instant = now or datetime.now(UTC)
        if operator.reprobe_due_at is not None:
            due = datetime.fromisoformat(operator.reprobe_due_at)
            if instant < due:
                return False
        available, classification = self.probe.probe_exact_route()
        next_due = (instant + timedelta(seconds=self.interval_seconds)).isoformat()
        self.store.save_operator_state(
            replace(
                operator,
                reprobe_due_at=next_due,
                availability_class=classification,
                last_event="EXACT_ROUTE_REPROBE",
            )
        )
        if not available:
            return False
        if not self.reconcile():
            self.store.save_operator_state(
                replace(
                    self.store.load_operator_state(),
                    operator_paused=True,
                    last_event="REPROBE_RECOVERY_RECONCILIATION_FAILED",
                    last_error_class="PAUSED_INFRASTRUCTURE",
                )
            )
            return False
        engine.resume_pause()
        return True


class LocalService:
    def __init__(
        self,
        store: SQLiteStateStore,
        lock: SingleInstanceLock,
        *,
        tick: Callable[[], None],
        poll_seconds: float = 5.0,
    ) -> None:
        if poll_seconds < 0.1 or poll_seconds > 60:
            raise ServiceError("INVALID_POLL_INTERVAL", repr(poll_seconds))
        self.store = store
        self.lock = lock
        self.tick = tick
        self.poll_seconds = poll_seconds
        self._stop = False

    def request_stop(self, *_: object) -> None:
        self._stop = True

    def run(self) -> int:
        with self.lock:
            self.store.initialize()
            operator = self.store.load_operator_state()
            if operator.emergency_stop_latched:
                log_event("SERVICE_NON_DISPATCHING_EMERGENCY_LATCH")
                return 3
            previous_term = signal.signal(signal.SIGTERM, self.request_stop)
            previous_int = signal.signal(signal.SIGINT, self.request_stop)
            try:
                log_event("SERVICE_STARTED")
                while not self._stop:
                    operator = self.store.load_operator_state()
                    if not operator.operator_paused and operator.maintenance_id is None:
                        self.tick()
                    time.sleep(self.poll_seconds)
                log_event("SERVICE_STOPPED")
                return 0
            finally:
                signal.signal(signal.SIGTERM, previous_term)
                signal.signal(signal.SIGINT, previous_int)


def git_snapshot(repository: str | Path) -> GitSnapshot:
    root = Path(repository).resolve(strict=True)

    def command(*args: str, optional: bool = False) -> str | None:
        result = subprocess.run(
            ("git", "-C", str(root), *args),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=20,
        )
        if result.returncode != 0:
            if optional:
                return None
            raise ServiceError("GIT_SNAPSHOT_FAILED", args[-1])
        return result.stdout.decode("ascii", "strict").strip()

    main = command("rev-parse", "refs/heads/main")
    development = command("rev-parse", "refs/heads/development", optional=True)
    remote_main = command("rev-parse", "refs/remotes/origin/main", optional=True)
    remote_development = command(
        "rev-parse", "refs/remotes/origin/development", optional=True
    )
    assert main is not None
    if remote_main is not None and remote_main != main:
        raise ServiceError("GIT_LOCAL_REMOTE_MAIN_MISMATCH", f"{main}!={remote_main}")
    if remote_development is not None and remote_development != development:
        raise ServiceError(
            "GIT_LOCAL_REMOTE_DEVELOPMENT_MISMATCH",
            f"{development}!={remote_development}",
        )
    return GitSnapshot(main, development)


def systemctl_user(action: str) -> None:
    if action not in {"start", "stop", "restart"}:
        raise ServiceError("SYSTEMCTL_ACTION_DENIED", action)
    completed = subprocess.run(
        ("systemctl", "--user", action, "goodix-orchestrator.service"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise ServiceError("SYSTEMD_USER_UNAVAILABLE", f"exit={completed.returncode}")
