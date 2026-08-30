# SPDX-License-Identifier: GPL-2.0-or-later
"""Operator CLI for the local-first O003 service."""

from __future__ import annotations

import argparse
import importlib.resources
import json
import os
import subprocess
import sys
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Callable

from .persistence import SQLiteStateStore
from .branch_lifecycle import BranchLifecycle
from .coordinator import CodexCoordinatorDriver, ProductionCoordinator, persist_unresolved_turn_pause
from .engine import DeterministicEngine
from .gate_adapter import GhCliTransport, HumanGateAdapter
from .persistence import EffectStatus, GitStateRecord, TurnActivityStatus
from .policy import CapabilityPolicy, HOST_ONLY_CAPABILITIES
from .service import (
    CodexRouteAvailabilityProbe,
    LocalService,
    OperatorController,
    ReprobeController,
    RuntimePaths,
    ServiceError,
    SingleInstanceLock,
    git_snapshot,
    log_event,
    systemctl_user,
)
from .state import OrchestratorState
from .structured_output import ContextClass, ModelRoute, RoutingClass


def _read_config(paths: RuntimePaths) -> dict[str, Any]:
    config_path = paths.config_dir / "config.json"
    if not config_path.exists():
        return {}
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ServiceError("CONFIG_INVALID", "top-level object required")
    forbidden = {key for key in data if any(word in key.lower() for word in ("token", "email", "password", "secret"))}
    if forbidden:
        raise ServiceError("CONFIG_SECRET_FIELD_DENIED", repr(sorted(forbidden)))
    return data


def _write_config(paths: RuntimePaths, data: dict[str, Any]) -> None:
    paths.ensure()
    destination = paths.config_dir / "config.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(destination)


def _repository(config: dict[str, Any]) -> Path:
    value = config.get("repository_root")
    if not isinstance(value, str) or not value:
        raise ServiceError("REPOSITORY_NOT_CONFIGURED", "run configure")
    return Path(value).resolve(strict=True)


def _git_ancestor(repository: Path, old: str, new: str) -> bool:
    result = subprocess.run(
        ("git", "-C", str(repository), "merge-base", "--is-ancestor", old, new),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=20,
    )
    if result.returncode not in (0, 1):
        raise ServiceError("GIT_ANCESTRY_AMBIGUOUS", f"{old}->{new}")
    return result.returncode == 0


def _fetch(repository: Path) -> None:
    result = subprocess.run(
        ("git", "-C", str(repository), "fetch", "--prune", "origin"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        raise ServiceError("GIT_FETCH_FAILED", f"exit={result.returncode}")


def _controller(paths: RuntimePaths, config: dict[str, Any]) -> OperatorController:
    repository = _repository(config)
    store = SQLiteStateStore(paths.state_db)
    store.initialize()
    return OperatorController(
        store,
        snapshot=lambda: git_snapshot(repository),
        fetch=lambda: _fetch(repository),
        is_ancestor=lambda old, new: _git_ancestor(repository, old, new),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="goodix-orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)
    configure = sub.add_parser("configure", help="configure repository and explicit GitHub authority")
    configure.add_argument("--repository-root", required=True)
    configure.add_argument("--github-repository", required=True)
    configure.add_argument("--authorized-github-user-id", type=int, required=True)
    configure.add_argument("--authorized-github-login", required=True)
    configure.add_argument("--reprobe-seconds", type=int, default=900)
    for name in ("status", "pause", "resume", "stop", "emergency-stop", "emergency-clear", "maintenance-exit", "backup", "service-run", "install-service", "uninstall-service"):
        sub.add_parser(name)
    enter = sub.add_parser("maintenance-enter")
    enter.add_argument("--maintenance-id")
    return parser


def _unit_path(value: Path, *, require_directory: bool = True) -> str:
    if value.is_symlink():
        raise ServiceError("SYSTEMD_WRITABLE_PATH_UNSAFE", str(value))
    resolved = value.resolve(strict=True)
    if require_directory and not resolved.is_dir():
        raise ServiceError("SYSTEMD_WRITABLE_PATH_INVALID", str(resolved))
    if resolved.is_symlink() or "\n" in str(resolved) or "\r" in str(resolved):
        raise ServiceError("SYSTEMD_WRITABLE_PATH_UNSAFE", str(resolved))
    if resolved.stat().st_uid != os.getuid():
        raise ServiceError("SYSTEMD_WRITABLE_PATH_OWNERSHIP_MISMATCH", str(resolved))
    return str(resolved).replace("\\", "\\\\").replace('"', '\\"')


def _install_service(paths: RuntimePaths, config: dict[str, Any]) -> Path:
    repository = _repository(config)
    top = subprocess.run(
        ("git", "-C", str(repository), "rev-parse", "--show-toplevel"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=20,
    )
    if top.returncode != 0 or Path(top.stdout.strip()).resolve(strict=True) != repository:
        raise ServiceError("REPOSITORY_ROOT_BINDING_MISMATCH", str(repository))
    common_raw = subprocess.run(
        ("git", "-C", str(repository), "rev-parse", "--git-common-dir"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=20,
    )
    if common_raw.returncode != 0:
        raise ServiceError("GIT_COMMON_DIR_UNAVAILABLE", str(repository))
    common = Path(common_raw.stdout.strip())
    if not common.is_absolute():
        common = repository / common
    if common.is_symlink():
        raise ServiceError("GIT_COMMON_DIR_SYMLINK_DENIED", str(common))
    common = common.resolve(strict=True)
    paths.ensure()
    resource = importlib.resources.files("goodix_orchestrator").joinpath(
        "resources/goodix-orchestrator.service"
    )
    if not resource.is_file():
        raise ServiceError("SERVICE_UNIT_MISSING", str(resource))
    destination_dir = paths.config_dir.parent / "systemd" / "user"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "goodix-orchestrator.service"
    executable_path = Path(sys.executable)
    if not executable_path.is_absolute() or not executable_path.exists():
        raise ServiceError("PYTHON_EXECUTABLE_INVALID", str(executable_path))
    # Preserve a virtualenv interpreter path: resolving its symlink would lose
    # the installed environment's site-packages at service start.
    executable = str(executable_path.absolute()).replace("\\", "\\\\").replace('"', '\\"')
    unit_text = resource.read_text(encoding="utf-8").replace("@PYTHON_EXECUTABLE@", executable)
    if "@PYTHON_EXECUTABLE@" in unit_text:
        raise ServiceError("SERVICE_UNIT_TEMPLATE_INVALID", "unresolved executable")
    destination.write_text(unit_text, encoding="utf-8")
    dropin_dir = destination_dir / "goodix-orchestrator.service.d"
    dropin_dir.mkdir(parents=True, exist_ok=True)
    writable = (
        _unit_path(common),
        _unit_path(paths.state_dir),
        _unit_path(paths.config_dir),
        _unit_path(paths.worktree_dir),
    )
    dropin = dropin_dir / "10-exact-writable-paths.conf"
    dropin.write_text(
        "[Service]\nReadWritePaths=\n"
        + "ReadWritePaths="
        + " ".join(f'"{item}"' for item in writable)
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(("systemctl", "--user", "daemon-reload"), check=False, timeout=30)
    return destination


def _systemd_state() -> str:
    try:
        result = subprocess.run(
            ("systemctl", "--user", "is-active", "goodix-orchestrator.service"),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "UNAVAILABLE"
    value = result.stdout.strip()
    return value.upper() if value else "INACTIVE_OR_UNAVAILABLE"


def _service_tick(
    store: SQLiteStateStore,
    config: dict[str, Any],
    repository: Path,
) -> tuple[Callable[[], None], Callable[[], None], DeterministicEngine | None]:
    runtime = store.load_runtime()
    fresh = runtime is None
    if fresh:
        snapshot = git_snapshot(repository)
        if snapshot.development_sha is None:
            store.save_operator_state(
                replace(
                    store.load_operator_state(),
                    operator_paused=True,
                    last_event="FRESH_BOOTSTRAP_PAUSED",
                    last_error_class="DEVELOPMENT_NOT_ACTIVATED",
                )
            )
            return (lambda: None), (lambda: None), None
        if snapshot.task_id is not None:
            store.save_operator_state(
                replace(
                    store.load_operator_state(),
                    operator_paused=True,
                    last_event="FRESH_BOOTSTRAP_PAUSED",
                    last_error_class="FRESH_BOOTSTRAP_TASK_REF_PRESENT",
                )
            )
            return (lambda: None), (lambda: None), None
        engine = DeterministicEngine.create(
            store,
            CapabilityPolicy(HOST_ONLY_CAPABILITIES),
            run_id=f"ORCH-SERVICE-{uuid.uuid4().hex}",
        )
        store.save_git_state(
            GitStateRecord(
                "development",
                snapshot.development_sha,
                None,
                main_sha=snapshot.main_sha,
            )
        )
        runtime = engine.runtime
    adapter = HumanGateAdapter(
        store,
        GhCliTransport(),
        repository=str(config.get("github_repository", "")),
        authorized_user_id=int(config.get("authorized_github_user_id", 0)),
        authorized_login=str(config.get("authorized_github_login", "")),
    )
    if runtime.current_state is OrchestratorState.HUMAN_GATE_WAIT:
        adapter.reconcile_decision_before_engine_recovery()
    if not fresh:
        recovered = DeterministicEngine.recover(
            store.path,
            CapabilityPolicy(HOST_ONLY_CAPABILITIES),
            expected_run_id=runtime.run_id,
        )
        if recovered.engine is None:
            raise ServiceError(recovered.error_code or "RECOVERY_FAILED", recovered.detail or "")
        engine = recovered.engine
    active_contexts = store.list_contexts(active_only=True)
    active = active_contexts[-1] if active_contexts else None
    reprobe: ReprobeController | None = None
    def reconciled() -> bool:
        git = store.load_git_state()
        snapshot = git_snapshot(repository)
        unresolved = store.effects_with_statuses((EffectStatus.IN_PROGRESS, EffectStatus.AMBIGUOUS))
        unresolved_turns = store.turn_activities((TurnActivityStatus.IN_PROGRESS, TurnActivityStatus.RECONCILIATION_REQUIRED))
        current = store.load_runtime()
        gate_ok = current is not None and (current.gate_id is None or (store.load_gate(current.gate_id) is not None and store.load_gate_external(current.gate_id) is not None))
        effective_state = current.previous_recoverable_state if current is not None and current.current_state in {OrchestratorState.PAUSED_RATE_LIMIT, OrchestratorState.PAUSED_MODEL_UNAVAILABLE, OrchestratorState.PAUSED_INFRASTRUCTURE} else current.current_state if current is not None else None
        coordinator_ok = not (effective_state in {OrchestratorState.TASK_READY, OrchestratorState.EXECUTOR_RUNNING, OrchestratorState.EXECUTOR_RESULT_READY, OrchestratorState.PM_REVIEWING, OrchestratorState.HUMAN_GATE_WAIT} and store.load_coordinator_state() is None)
        return not unresolved and not unresolved_turns and git is not None and snapshot.development_sha == git.integration_sha and (git.main_sha is None or snapshot.main_sha == git.main_sha) and snapshot.task_id == git.task_id and snapshot.task_branch == git.task_branch and snapshot.task_worktree == git.task_worktree and gate_ok and coordinator_ok

    if active is not None:
        route = ModelRoute(active.routing_class, active.context_class, active.effective_model_id, active.effective_reasoning_effort)
        reprobe = ReprobeController(
            store,
            CodexRouteAvailabilityProbe(store, route, cwd=repository),
            interval_seconds=int(config.get("reprobe_seconds", 900)),
            reconcile=reconciled,
        )

    coordinator: ProductionCoordinator | None = None

    def ensure_coordinator() -> ProductionCoordinator:
        nonlocal coordinator
        if coordinator is None:
            coordinator = ProductionCoordinator(
                engine=engine,
                lifecycle=BranchLifecycle(repository, store),
                driver=CodexCoordinatorDriver(store, repository),
                gate_adapter=adapter,
            )
        return coordinator

    def ensure_failed_route_reprobe() -> ReprobeController | None:
        nonlocal reprobe
        raw = store.load_coordinator_state() or {}
        failed = raw.get("failed_route")
        if not isinstance(failed, dict):
            return reprobe
        required = ("routing_class", "context_class", "model_id", "reasoning_effort")
        if any(not isinstance(failed.get(key), str) for key in required):
            return reprobe
        route = ModelRoute(RoutingClass(failed["routing_class"]), ContextClass(failed["context_class"]), failed["model_id"], failed["reasoning_effort"])
        reprobe = ReprobeController(store, CodexRouteAvailabilityProbe(store, route, cwd=repository), interval_seconds=int(config.get("reprobe_seconds", 900)), reconcile=reconciled)
        return reprobe

    def tick() -> None:
        nonlocal coordinator
        try:
            if engine.state is OrchestratorState.HUMAN_GATE_WAIT:
                checkpoint = store.load_coordinator_state() or {}
                if checkpoint.get("phase") == "GATE_BINDING_PENDING":
                    ensure_coordinator().tick()
                else:
                    adapter.poll(engine)
            elif engine.state in {
                OrchestratorState.PAUSED_RATE_LIMIT,
                OrchestratorState.PAUSED_MODEL_UNAVAILABLE,
            }:
                current_reprobe = ensure_failed_route_reprobe()
                if current_reprobe is not None:
                    current_reprobe.tick(engine)
            elif engine.state not in {
                OrchestratorState.PAUSED_INFRASTRUCTURE,
                OrchestratorState.DONE,
                OrchestratorState.ERROR_LOCKED,
            }:
                unresolved_turns = store.turn_activities(
                    (
                        TurnActivityStatus.IN_PROGRESS,
                        TurnActivityStatus.RECONCILIATION_REQUIRED,
                    )
                )
                if unresolved_turns:
                    persist_unresolved_turn_pause(store, engine, unresolved_turns)
                else:
                    ensure_coordinator().tick()
        except Exception as exc:
            if coordinator is not None:
                coordinator.driver.close()
                coordinator = None
            current = store.load_operator_state()
            store.save_operator_state(
                replace(
                    current,
                    operator_paused=True,
                    last_event="SERVICE_FAIL_CLOSED",
                    last_error_class=str(getattr(exc, "code", type(exc).__name__))[:256],
                )
            )
            log_event(
                "SERVICE_TICK_FAIL_CLOSED",
                error_class=getattr(exc, "code", type(exc).__name__),
            )

    def close() -> None:
        nonlocal coordinator
        if coordinator is not None:
            coordinator.driver.close()
            coordinator = None

    return tick, close, engine


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = RuntimePaths.discover()
    paths.ensure()
    try:
        if args.command == "configure":
            repository = Path(args.repository_root).resolve(strict=True)
            if not 60 <= args.reprobe_seconds <= 86400:
                raise ServiceError("INVALID_REPROBE_INTERVAL", str(args.reprobe_seconds))
            data = {
                "repository_root": str(repository),
                "github_repository": args.github_repository,
                "authorized_github_user_id": args.authorized_github_user_id,
                "authorized_github_login": args.authorized_github_login,
                "reprobe_seconds": args.reprobe_seconds,
            }
            _write_config(paths, data)
            print(json.dumps({"configured": True, "config": str(paths.config_dir / "config.json")}))
            return 0
        config = _read_config(paths)
        if args.command == "install-service":
            print(_install_service(paths, config))
            return 0
        if args.command == "uninstall-service":
            try:
                systemctl_user("stop")
            except ServiceError:
                pass
            unit = paths.config_dir.parent / "systemd" / "user" / "goodix-orchestrator.service"
            if unit.exists():
                unit.unlink()
            dropin = unit.parent / "goodix-orchestrator.service.d" / "10-exact-writable-paths.conf"
            if dropin.exists():
                dropin.unlink()
            subprocess.run(("systemctl", "--user", "daemon-reload"), check=False, timeout=30)
            return 0
        controller = _controller(paths, config)
        if args.command == "status":
            status = controller.status()
            status["service_state"] = _systemd_state()
            print(json.dumps(status, indent=2, sort_keys=True))
        elif args.command == "pause":
            controller.pause()
            print("OPERATOR_PAUSE=true")
        elif args.command == "resume":
            controller.resume()
            print("OPERATOR_PAUSE=false")
        elif args.command == "stop":
            systemctl_user("stop")
        elif args.command == "emergency-stop":
            controller.emergency_stop()
            try:
                systemctl_user("stop")
            except ServiceError:
                # The persistent latch is authoritative even when no user manager is available.
                pass
            print("EMERGENCY_STOP_LATCH=true")
        elif args.command == "emergency-clear":
            controller.emergency_clear()
            print("EMERGENCY_STOP_LATCH=false")
        elif args.command == "maintenance-enter":
            maintenance_id = args.maintenance_id or f"MAINT-{uuid.uuid4().hex}"
            print(json.dumps(asdict(controller.maintenance_enter(maintenance_id)), sort_keys=True))
        elif args.command == "maintenance-exit":
            print(json.dumps(asdict(controller.maintenance_exit()), sort_keys=True))
        elif args.command == "backup":
            store = SQLiteStateStore(paths.state_db)
            store.initialize()
            print(
                store.backup_with_effect(
                    paths.backup_dir,
                    effect_id=f"EFFECT-STATE-BACKUP-{uuid.uuid4().hex}",
                    retain=5,
                )
            )
        elif args.command == "service-run":
            repository = _repository(config)
            tick, close, _engine = _service_tick(controller.store, config, repository)
            service = LocalService(
                controller.store,
                SingleInstanceLock(paths.lock_file),
                tick=tick,
            )
            try:
                return service.run()
            finally:
                close()
        return 0
    except Exception as exc:
        code = getattr(exc, "code", type(exc).__name__)
        print(json.dumps({"error_class": code, "detail": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
