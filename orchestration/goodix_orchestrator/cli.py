# SPDX-License-Identifier: GPL-2.0-or-later
"""Operator CLI for the local-first O003 service."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from .persistence import SQLiteStateStore
from .engine import DeterministicEngine
from .gate_adapter import GhCliTransport, HumanGateAdapter
from .persistence import EffectStatus
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
    systemctl_user,
)
from .state import OrchestratorState
from .structured_output import ModelRoute


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


def _install_service(paths: RuntimePaths) -> Path:
    source = Path(__file__).resolve().parent.parent / "systemd" / "goodix-orchestrator.service"
    if not source.is_file():
        raise ServiceError("SERVICE_UNIT_MISSING", str(source))
    destination_dir = paths.config_dir.parent / "systemd" / "user"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    shutil.copyfile(source, destination)
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
) -> tuple[Callable[[], None], DeterministicEngine | None]:
    runtime = store.load_runtime()
    if runtime is None:
        return (lambda: None), None
    adapter = HumanGateAdapter(
        store,
        GhCliTransport(),
        repository=str(config.get("github_repository", "")),
        authorized_user_id=int(config.get("authorized_github_user_id", 0)),
        authorized_login=str(config.get("authorized_github_login", "")),
    )
    if runtime.current_state is OrchestratorState.HUMAN_GATE_WAIT:
        adapter.reconcile_decision_before_engine_recovery()
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
    if active is not None:
        route = ModelRoute(
            active.routing_class,
            active.context_class,
            active.effective_model_id,
            active.effective_reasoning_effort,
        )

        def reconciled() -> bool:
            git = store.load_git_state()
            snapshot = git_snapshot(repository)
            unresolved = store.effects_with_statuses(
                (EffectStatus.IN_PROGRESS, EffectStatus.AMBIGUOUS)
            )
            return (
                not unresolved
                and git is not None
                and snapshot.development_sha == git.integration_sha
                and (git.main_sha is None or snapshot.main_sha == git.main_sha)
            )

        reprobe = ReprobeController(
            store,
            CodexRouteAvailabilityProbe(store, route),
            interval_seconds=int(config.get("reprobe_seconds", 900)),
            reconcile=reconciled,
        )

    def tick() -> None:
        if engine.state is OrchestratorState.HUMAN_GATE_WAIT:
            adapter.poll(engine)
        elif reprobe is not None and engine.state in {
            OrchestratorState.PAUSED_RATE_LIMIT,
            OrchestratorState.PAUSED_MODEL_UNAVAILABLE,
        }:
            reprobe.tick(engine)

    return tick, engine


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
            print(_install_service(paths))
            return 0
        if args.command == "uninstall-service":
            try:
                systemctl_user("stop")
            except ServiceError:
                pass
            unit = paths.config_dir.parent / "systemd" / "user" / "goodix-orchestrator.service"
            if unit.exists():
                unit.unlink()
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
            tick, _engine = _service_tick(controller.store, config, repository)
            service = LocalService(
                controller.store,
                SingleInstanceLock(paths.lock_file),
                tick=tick,
            )
            return service.run()
        return 0
    except Exception as exc:
        code = getattr(exc, "code", type(exc).__name__)
        print(json.dumps({"error_class": code, "detail": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
