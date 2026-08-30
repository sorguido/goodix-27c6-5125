# SPDX-License-Identifier: GPL-2.0-or-later
"""Small fail-closed JSONL client for one long-lived Codex App Server."""

from __future__ import annotations

import json
import os
import selectors
import shutil
import subprocess
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar

from .persistence import (
    ContextRecord,
    DispatchRecord,
    SQLiteStateStore,
    TurnActivityRecord,
    TurnActivityStatus,
)
from .protocols import ProtocolValidationError
from .structured_output import ContextClass, ModelRoute, ModelRouter


MAX_MESSAGE_BYTES = 2 * 1024 * 1024
MAX_STDERR_BYTES = 64 * 1024
DEFAULT_TIMEOUT = 30.0


class MessageKind(StrEnum):
    RESPONSE = "RESPONSE"
    SERVER_NOTIFICATION = "SERVER_NOTIFICATION"
    SERVER_REQUEST = "SERVER_REQUEST"


@dataclass(frozen=True, slots=True)
class AdapterError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True, slots=True)
class ThreadContext:
    thread_id: str
    context_class: ContextClass
    route: ModelRoute
    cwd: str
    sandbox: str


@dataclass(frozen=True, slots=True)
class TurnResult:
    turn_id: str
    status: str
    final_text: str
    error_class: str | None = None


T = TypeVar("T")


def classify_server_message(message: Any) -> MessageKind:
    if not isinstance(message, dict):
        raise AdapterError("MALFORMED_PROTOCOL_FRAME", "frame is not an object")
    has_id = "id" in message
    has_method = isinstance(message.get("method"), str)
    if has_method and has_id:
        return MessageKind.SERVER_REQUEST
    if has_method and not has_id:
        return MessageKind.SERVER_NOTIFICATION
    if has_id and not has_method and (("result" in message) ^ ("error" in message)):
        return MessageKind.RESPONSE
    raise AdapterError("MALFORMED_PROTOCOL_FRAME", "ambiguous JSON-RPC shape")


class CodexAppServer:
    """Synchronous request client with an explicit pending table and event queue."""

    def __init__(
        self,
        executable: str = "codex",
        *,
        app_server_args: tuple[str, ...] = ("app-server",),
        process_cwd: str | Path | None = None,
        store: SQLiteStateStore | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_message_bytes: int = MAX_MESSAGE_BYTES,
    ) -> None:
        resolved = shutil.which(executable) if not Path(executable).is_absolute() else executable
        if not resolved or not Path(resolved).is_file():
            raise AdapterError("CODEX_NOT_FOUND", executable)
        if timeout <= 0 or max_message_bytes < 1024:
            raise AdapterError("INVALID_ADAPTER_BOUND", "timeout/message bound")
        self.executable = str(Path(resolved).resolve())
        self.app_server_args = tuple(app_server_args)
        self.process_cwd = str(Path(process_cwd).resolve()) if process_cwd else None
        self.store = store
        self.timeout = timeout
        self.max_message_bytes = max_message_bytes
        self.process: subprocess.Popen[bytes] | None = None
        self.codex_version = self._probe_version()
        self._next_request_id = 1
        self._pending: dict[int, str] = {}
        self._notifications: list[dict[str, Any]] = []
        self._read_buffer = bytearray()
        self._handshake_complete = False
        self._unexpected_server_request: str | None = None
        self._stderr_summary = ""

    def _probe_version(self) -> str:
        try:
            completed = subprocess.run(
                [self.executable, "--version"],
                cwd=self.process_cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=self.timeout,
                text=True,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AdapterError("CODEX_VERSION_PROBE_FAILED", type(exc).__name__) from exc
        if completed.returncode != 0:
            raise AdapterError("CODEX_VERSION_PROBE_FAILED", f"exit={completed.returncode}")
        version = completed.stdout.strip() or completed.stderr.strip()
        if not version or len(version) > 512:
            raise AdapterError("CODEX_VERSION_PROBE_FAILED", "invalid version response")
        return version.splitlines()[0]

    def start(self) -> None:
        if self.process is not None:
            raise AdapterError("APP_SERVER_ALREADY_STARTED", "duplicate start")
        try:
            self.process = subprocess.Popen(
                [self.executable, *self.app_server_args],
                cwd=self.process_cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                bufsize=0,
            )
        except OSError as exc:
            raise AdapterError("APP_SERVER_START_FAILED", type(exc).__name__) from exc
        assert self.process.stdout is not None
        os.set_blocking(self.process.stdout.fileno(), False)
        result = self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "goodix_orchestrator",
                    "title": "Goodix Autonomous Orchestrator",
                    "version": "0.2.0",
                }
            },
            allow_before_handshake=True,
        )
        if not isinstance(result, dict):
            self.close()
            raise AdapterError("INITIALIZE_FAILED", "non-object response")
        self._send({"method": "initialized", "params": {}})
        self._handshake_complete = True

    def __enter__(self) -> "CodexAppServer":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    @property
    def stderr_summary(self) -> str:
        return self._stderr_summary

    @property
    def pending_request_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._pending))

    def _send(self, message: Mapping[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise AdapterError("APP_SERVER_NOT_RUNNING", "stdin unavailable")
        encoded = json.dumps(
            message, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8") + b"\n"
        if len(encoded) > self.max_message_bytes:
            raise AdapterError("PROTOCOL_MESSAGE_TOO_LARGE", str(len(encoded)))
        try:
            self.process.stdin.write(encoded)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise AdapterError("TRANSPORT_LOST_AMBIGUOUS", type(exc).__name__) from exc

    def _read_line(self, timeout: float | None = None) -> bytes:
        if self.process is None or self.process.stdout is None:
            raise AdapterError("APP_SERVER_NOT_RUNNING", "stdout unavailable")
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        fd = self.process.stdout.fileno()
        while True:
            newline = self._read_buffer.find(b"\n")
            if newline >= 0:
                line = bytes(self._read_buffer[:newline])
                del self._read_buffer[: newline + 1]
                return line
            if len(self._read_buffer) > self.max_message_bytes:
                raise AdapterError(
                    "PROTOCOL_MESSAGE_TOO_LARGE", str(len(self._read_buffer))
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AdapterError("APP_SERVER_TIMEOUT", "bounded read expired")
            with selectors.DefaultSelector() as selector:
                selector.register(fd, selectors.EVENT_READ)
                ready = selector.select(remaining)
            if not ready:
                raise AdapterError("APP_SERVER_TIMEOUT", "bounded read expired")
            try:
                chunk = os.read(fd, min(65536, self.max_message_bytes + 1))
            except BlockingIOError:
                continue
            if not chunk:
                raise AdapterError(
                    "TRANSPORT_LOST_AMBIGUOUS",
                    f"exit={self.process.poll()}",
                )
            self._read_buffer.extend(chunk)

    def _read_message(self, timeout: float | None = None) -> dict[str, Any]:
        line = self._read_line(timeout)
        if not line or len(line) > self.max_message_bytes:
            raise AdapterError("MALFORMED_PROTOCOL_FRAME", "empty/oversized line")
        try:
            value = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AdapterError("MALFORMED_PROTOCOL_FRAME", type(exc).__name__) from exc
        classify_server_message(value)
        return value

    def _request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        allow_before_handshake: bool = False,
    ) -> dict[str, Any]:
        if not self._handshake_complete and not allow_before_handshake:
            raise AdapterError("HANDSHAKE_REQUIRED", method)
        request_id = self._next_request_id
        self._next_request_id += 1
        self._pending[request_id] = method
        self._send({"method": method, "id": request_id, "params": dict(params or {})})
        while True:
            message = self._read_message()
            kind = classify_server_message(message)
            if kind is MessageKind.SERVER_NOTIFICATION:
                self._notifications.append(message)
                continue
            if kind is MessageKind.SERVER_REQUEST:
                self._deny_server_request(message)
                self._pending.pop(request_id, None)
                raise AdapterError(
                    "UNEXPECTED_APPROVAL_OR_SERVER_REQUEST",
                    str(message.get("method")),
                )
            response_id = message.get("id")
            if not isinstance(response_id, int) or response_id not in self._pending:
                self._pending.pop(request_id, None)
                raise AdapterError("UNKNOWN_RESPONSE_ID", repr(response_id))
            response_method = self._pending.pop(response_id)
            if response_id != request_id:
                raise AdapterError(
                    "UNEXPECTED_OUT_OF_ORDER_RESPONSE",
                    f"{response_method}:{response_id}",
                )
            if "error" in message:
                error = message["error"]
                error_code = "APP_SERVER_RPC_ERROR"
                if isinstance(error, dict):
                    detail = str(error.get("message", "rpc error"))[:512]
                    data = error.get("data")
                    if isinstance(data, dict):
                        codex_class = data.get("codexErrorInfo") or data.get("errorType")
                        error_code = self._map_error_class(codex_class)
                else:
                    detail = "rpc error"
                raise AdapterError(error_code, f"{method}:{detail}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise AdapterError("MALFORMED_PROTOCOL_RESPONSE", method)
            return result

    @staticmethod
    def _map_error_class(value: Any) -> str:
        if isinstance(value, dict) and value:
            value = next(iter(value))
        return {
            "usageLimitExceeded": "PAUSED_RATE_LIMIT",
            "sessionBudgetExceeded": "PAUSED_RATE_LIMIT",
            "unauthorized": "UNAUTHORIZED",
            "sandboxError": "SANDBOX_ERROR",
            "serverOverloaded": "SERVER_OVERLOADED",
            "responseStreamDisconnected": "TRANSPORT_LOST_AMBIGUOUS",
            "responseStreamConnectionFailed": "TRANSPORT_LOST_AMBIGUOUS",
        }.get(str(value), "APP_SERVER_RPC_ERROR")

    def _deny_server_request(self, message: Mapping[str, Any]) -> None:
        request_id = message.get("id")
        method = str(message.get("method"))
        if not isinstance(request_id, (int, str)):
            raise AdapterError("MALFORMED_SERVER_REQUEST", method)
        if method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "execCommandApproval",
            "applyPatchApproval",
        }:
            result: dict[str, Any] = {"decision": "decline"}
        elif method == "item/permissions/requestApproval":
            result = {"permissions": {}}
        elif method in {
            "tool/requestUserInput",
            "mcpServer/elicitation/request",
        }:
            result = {"action": "decline", "content": None}
        else:
            self._send(
                {
                    "id": request_id,
                    "error": {"code": -32601, "message": "Denied by O002 policy"},
                }
            )
            self._unexpected_server_request = method
            return
        self._send({"id": request_id, "result": result})
        self._unexpected_server_request = method

    def account_mode(self) -> str:
        result = self._request("account/read", {"refreshToken": False})
        account = result.get("account")
        if not isinstance(account, dict):
            raise AdapterError("AUTH_NOT_CHATGPT", "unauthenticated")
        account_type = account.get("type")
        if account_type != "chatgpt":
            raise AdapterError("AUTH_NOT_CHATGPT", str(account_type)[:64])
        return "CHATGPT"

    def model_catalog(self) -> dict[str, set[str]]:
        catalog: dict[str, set[str]] = {}
        cursor: str | None = None
        for _ in range(20):
            params: dict[str, Any] = {"limit": 100, "includeHidden": True}
            if cursor is not None:
                params["cursor"] = cursor
            result = self._request("model/list", params)
            data = result.get("data")
            if not isinstance(data, list):
                raise AdapterError("MODEL_CATALOG_MALFORMED", "data")
            for item in data:
                if not isinstance(item, dict):
                    raise AdapterError("MODEL_CATALOG_MALFORMED", "entry")
                model_id = item.get("id")
                if not isinstance(model_id, str) or not model_id:
                    raise AdapterError("MODEL_CATALOG_MALFORMED", "id")
                efforts_raw = item.get("supportedReasoningEfforts")
                if not isinstance(efforts_raw, list):
                    raise AdapterError("MODEL_CATALOG_MALFORMED", model_id)
                efforts: set[str] = set()
                for effort in efforts_raw:
                    if not isinstance(effort, dict) or not isinstance(
                        effort.get("reasoningEffort"), str
                    ):
                        raise AdapterError("MODEL_CATALOG_MALFORMED", model_id)
                    efforts.add(effort["reasoningEffort"])
                catalog[model_id] = efforts
            cursor_value = result.get("nextCursor")
            if cursor_value is None:
                return catalog
            if not isinstance(cursor_value, str) or not cursor_value:
                raise AdapterError("MODEL_CATALOG_MALFORMED", "nextCursor")
            cursor = cursor_value
        raise AdapterError("MODEL_CATALOG_MALFORMED", "pagination bound")

    def require_route(self, route: ModelRoute) -> None:
        try:
            ModelRouter.require_catalog(route, self.model_catalog())
        except ProtocolValidationError as exc:
            raise AdapterError("PAUSED_MODEL_UNAVAILABLE", str(exc)) from exc

    def rate_limit_telemetry(self) -> dict[str, Any]:
        try:
            result = self._request("account/rateLimits/read")
        except AdapterError as exc:
            if exc.code == "APP_SERVER_RPC_ERROR":
                return {"available": False}
            raise
        buckets = result.get("rateLimitsByLimitId")
        if not isinstance(buckets, dict):
            single = result.get("rateLimits")
            buckets = {"default": single} if isinstance(single, dict) else {}
        redacted: list[dict[str, Any]] = []
        for bucket in buckets.values():
            if not isinstance(bucket, dict):
                continue
            primary = bucket.get("primary")
            redacted.append(
                {
                    "reached": bucket.get("rateLimitReachedType") is not None,
                    "resets_at": primary.get("resetsAt")
                    if isinstance(primary, dict)
                    else None,
                }
            )
        return {"available": True, "buckets": redacted}

    @staticmethod
    def _sandbox_name(context_class: ContextClass) -> str:
        # thread/start and thread/resume use the legacy kebab-case enum.  The
        # returned thread settings describe the effective SandboxPolicy with
        # the newer camel-case tagged union; _verify_thread_response handles
        # that protocol-level spelling difference explicitly.
        return "workspace-write" if context_class is ContextClass.AI_EXECUTOR else "read-only"

    @staticmethod
    def _permission_profile_name(context_class: ContextClass) -> str:
        return (
            "o002-executor-workspace"
            if context_class is ContextClass.AI_EXECUTOR
            else "o002-pm-read-only"
        )

    def _permission_config(
        self, context_class: ContextClass, cwd: str, effort: str
    ) -> dict[str, Any]:
        name = self._permission_profile_name(context_class)
        access = "write" if context_class is ContextClass.AI_EXECUTOR else "read"
        return {
            "model_reasoning_effort": effort,
            "features": {"apps": False},
            "default_permissions": name,
            "permissions": {
                name: {
                    "description": "O002 synthetic qualification least-privilege profile",
                    "filesystem": {
                        ":minimal": "read",
                        self.executable: "read",
                        cwd: access,
                    },
                    "network": {"enabled": False},
                }
            },
        }

    def start_thread(self, route: ModelRoute, cwd: str | Path) -> ThreadContext:
        self.require_route(route)
        resolved_cwd = str(Path(cwd).resolve(strict=True))
        sandbox = self._sandbox_name(route.context_class)
        result = self._request(
            "thread/start",
            {
                "model": route.model_id,
                "cwd": resolved_cwd,
                "approvalPolicy": "never",
                "config": self._permission_config(
                    route.context_class, resolved_cwd, route.reasoning_effort
                ),
                "serviceName": "goodix_orchestrator",
            },
        )
        self._verify_thread_response(result, route, resolved_cwd, sandbox)
        thread = result.get("thread")
        assert isinstance(thread, dict)
        thread_id = thread.get("id")
        if not isinstance(thread_id, str) or not thread_id:
            raise AdapterError("THREAD_ID_MISSING", "thread/start")
        context = ThreadContext(
            thread_id, route.context_class, route, resolved_cwd, sandbox
        )
        self._persist_context(context)
        return context

    def resume_thread(
        self, thread_id: str, route: ModelRoute, cwd: str | Path
    ) -> ThreadContext:
        self.require_route(route)
        resolved_cwd = str(Path(cwd).resolve(strict=True))
        sandbox = self._sandbox_name(route.context_class)
        result = self._request(
            "thread/resume",
            {
                "threadId": thread_id,
                "model": route.model_id,
                "cwd": resolved_cwd,
                "approvalPolicy": "never",
                "config": self._permission_config(
                    route.context_class, resolved_cwd, route.reasoning_effort
                ),
            },
        )
        self._verify_thread_response(result, route, resolved_cwd, sandbox)
        thread = result.get("thread")
        if not isinstance(thread, dict) or thread.get("id") != thread_id:
            raise AdapterError("THREAD_RESUME_MISMATCH", thread_id)
        context = ThreadContext(thread_id, route.context_class, route, resolved_cwd, sandbox)
        self._persist_context(context)
        return context

    def reroute_context(
        self, context: ThreadContext, route: ModelRoute
    ) -> ThreadContext:
        """Prepare an in-thread turn override, verified after that turn completes.

        App Server applies model/effort turn overrides to the current and later
        turns.  A pre-turn thread/resume only reports the old loaded settings,
        so it cannot prove a corrective reroute. Every turn, rerouted or not,
        is observed after completion before its dispatch is persisted.
        """

        self.require_route(route)
        if route.context_class is not context.context_class:
            raise AdapterError(
                "CONTEXT_CLASS_REROUTE_DENIED",
                f"{context.context_class.value}->{route.context_class.value}",
            )
        return ThreadContext(
            context.thread_id,
            context.context_class,
            route,
            context.cwd,
            context.sandbox,
        )

    def _observe_thread_route(self, context: ThreadContext) -> None:
        result = self._request(
            "thread/resume",
            {"threadId": context.thread_id},
        )
        self._verify_thread_response(
            result, context.route, context.cwd, context.sandbox
        )
        self._persist_context(context)

    @classmethod
    def _verify_thread_response(
        cls, result: Mapping[str, Any], route: ModelRoute, cwd: str, sandbox: str
    ) -> None:
        try:
            ModelRouter.verify_effective(
                route, result.get("model"), result.get("reasoningEffort")
            )
        except ProtocolValidationError as exc:
            raise AdapterError("PAUSED_MODEL_UNAVAILABLE", str(exc)) from exc
        if result.get("cwd") != cwd:
            raise AdapterError("THREAD_CWD_MISMATCH", repr(result.get("cwd")))
        observed_sandbox = result.get("sandbox")
        sandbox_type = (
            observed_sandbox.get("type")
            if isinstance(observed_sandbox, dict)
            else observed_sandbox
        )
        expected_sandbox_type = {
            "read-only": "readOnly",
            "workspace-write": "workspaceWrite",
        }[sandbox]
        if sandbox_type != expected_sandbox_type:
            raise AdapterError("SANDBOX_ROUTING_MISMATCH", repr(sandbox_type))
        active_profile = result.get("activePermissionProfile")
        if active_profile is not None:
            profile_id = (
                active_profile.get("id")
                if isinstance(active_profile, dict)
                else None
            )
            expected_profile = cls._permission_profile_name(route.context_class)
            if profile_id != expected_profile:
                raise AdapterError(
                    "PERMISSION_PROFILE_ROUTING_MISMATCH", repr(profile_id)
                )
        if result.get("approvalPolicy") != "never":
            raise AdapterError(
                "APPROVAL_POLICY_MISMATCH", repr(result.get("approvalPolicy"))
            )

    def _persist_context(self, context: ThreadContext) -> None:
        if self.store is None:
            return
        role = "AI_EXECUTOR" if context.context_class is ContextClass.AI_EXECUTOR else "AI_PM"
        self.store.record_context(
            ContextRecord(
                thread_id=context.thread_id,
                context_class=context.context_class,
                role=role,
                effective_model_id=context.route.model_id,
                effective_reasoning_effort=context.route.reasoning_effort,
                routing_class=context.route.routing_class,
                cwd=context.cwd,
                codex_version=self.codex_version,
            )
        )

    def run_turn(
        self,
        context: ThreadContext,
        prompt: str,
        *,
        output_schema: Mapping[str, Any],
        dispatch_id: str,
        schema_repair: bool = False,
    ) -> TurnResult:
        self.require_route(context.route)
        activity_id = f"ACTIVITY-{dispatch_id}"
        turn_id: str | None = None
        terminal_observed = False
        if self.store is not None:
            self.store.start_turn_activity(
                TurnActivityRecord(
                    activity_id=activity_id,
                    dispatch_id=dispatch_id,
                    thread_id=context.thread_id,
                    context_class=context.context_class,
                    routing_class=context.route.routing_class,
                    requested_model_id=context.route.model_id,
                    requested_reasoning_effort=context.route.reasoning_effort,
                    status=TurnActivityStatus.IN_PROGRESS,
                )
            )
        try:
            result = self._request(
                "turn/start",
                {
                    "threadId": context.thread_id,
                    "input": [{"type": "text", "text": prompt}],
                    "cwd": context.cwd,
                    "model": context.route.model_id,
                    "effort": context.route.reasoning_effort,
                    "approvalPolicy": "never",
                    "outputSchema": dict(output_schema),
                },
            )
            turn = result.get("turn")
            if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
                raise AdapterError("TURN_START_MALFORMED", context.thread_id)
            turn_id = turn["id"]
            if self.store is not None:
                self.store.update_turn_activity(
                    activity_id,
                    status=TurnActivityStatus.IN_PROGRESS,
                    turn_id=turn_id,
                )
            completed = self._wait_turn(turn_id)
            terminal_observed = True
            # A successful thread/start or an earlier observation is not evidence
            # for this dispatch. Re-observe and verify the effective route after
            # every completed turn before persisting or using its output.
            self._observe_thread_route(context)
            if self.store is not None:
                self.store.record_dispatch(
                    DispatchRecord(
                        dispatch_id=dispatch_id,
                        thread_id=context.thread_id,
                        turn_id=turn_id,
                        context_class=context.context_class,
                        routing_class=context.route.routing_class,
                        effective_model_id=context.route.model_id,
                        effective_reasoning_effort=context.route.reasoning_effort,
                        codex_version=self.codex_version,
                        schema_repair=schema_repair,
                    )
                )
                self.store.update_turn_activity(
                    activity_id,
                    status=TurnActivityStatus.COMPLETED,
                    turn_id=turn_id,
                )
            return completed
        except Exception as exc:
            if self.store is not None:
                code = getattr(exc, "code", type(exc).__name__)
                terminal_failure = (
                    isinstance(exc, AdapterError)
                    and turn_id is not None
                    and exc.detail.startswith(f"turn={turn_id},status=")
                )
                ambiguous = (
                    turn_id is not None
                    and not terminal_observed
                    and not terminal_failure
                ) or code in {
                    "TRANSPORT_LOST_AMBIGUOUS",
                    "TURN_TIMEOUT_AMBIGUOUS",
                    "APP_SERVER_TIMEOUT",
                }
                self.store.update_turn_activity(
                    activity_id,
                    status=(
                        TurnActivityStatus.RECONCILIATION_REQUIRED
                        if ambiguous
                        else TurnActivityStatus.FAILED
                    ),
                    turn_id=turn_id,
                    error_class=str(code)[:256],
                )
            raise

    def _next_event(self, timeout: float) -> dict[str, Any]:
        if self._notifications:
            return self._notifications.pop(0)
        while True:
            message = self._read_message(timeout)
            kind = classify_server_message(message)
            if kind is MessageKind.SERVER_REQUEST:
                self._deny_server_request(message)
                raise AdapterError(
                    "UNEXPECTED_APPROVAL_OR_SERVER_REQUEST",
                    str(message.get("method")),
                )
            if kind is MessageKind.RESPONSE:
                response_id = message.get("id")
                if response_id not in self._pending:
                    raise AdapterError("UNKNOWN_RESPONSE_ID", repr(response_id))
                raise AdapterError("UNEXPECTED_OUT_OF_ORDER_RESPONSE", repr(response_id))
            return message

    def _wait_turn(self, turn_id: str) -> TurnResult:
        deadline = time.monotonic() + self.timeout
        final_texts: list[str] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AdapterError("TURN_TIMEOUT_AMBIGUOUS", turn_id)
            event = self._next_event(remaining)
            method = event.get("method")
            params = event.get("params")
            if method == "item/completed" and isinstance(params, dict):
                item = params.get("item")
                if isinstance(item, dict) and item.get("type") == "agentMessage":
                    text = item.get("text")
                    if isinstance(text, str):
                        final_texts.append(text)
            if method != "turn/completed" or not isinstance(params, dict):
                continue
            turn = params.get("turn")
            if not isinstance(turn, dict) or turn.get("id") != turn_id:
                continue
            status = turn.get("status")
            if status == "completed":
                return TurnResult(turn_id, status, final_texts[-1] if final_texts else "")
            error = turn.get("error")
            error_class = None
            if isinstance(error, dict):
                error_class = self._map_error_class(error.get("codexErrorInfo"))
            code = error_class or "TURN_FAILED"
            raise AdapterError(code, f"turn={turn_id},status={status}")

    def run_structured_turn(
        self,
        context: ThreadContext,
        prompt: str,
        *,
        output_schema: Mapping[str, Any],
        validator: Callable[[Mapping[str, Any]], T],
        dispatch_id: str,
    ) -> T:
        validation_error: ProtocolValidationError | AdapterError | None = None
        for repair in range(2):
            turn_prompt = prompt
            if repair:
                assert validation_error is not None
                code = getattr(validation_error, "code", "STRUCTURED_OUTPUT_INVALID")
                if (
                    not isinstance(code, str)
                    or not code.isascii()
                    or not 1 <= len(code) <= 64
                    or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for character in code)
                ):
                    code = "STRUCTURED_OUTPUT_INVALID"
                turn_prompt = (
                    f"VALIDATION_FAILURE_CODE={code}\n"
                    "Correct every disposition-specific field consistently, using JSON null "
                    "for fields that do not belong to the selected disposition. Return only "
                    "one JSON object matching the previously supplied output contract."
                )
            result = self.run_turn(
                context,
                turn_prompt,
                output_schema=output_schema,
                dispatch_id=f"{dispatch_id}-R{repair}",
                schema_repair=bool(repair),
            )
            try:
                payload = json.loads(result.final_text)
                if not isinstance(payload, dict):
                    raise AdapterError("STRUCTURED_OUTPUT_INVALID", "not an object")
                return validator(payload)
            except (json.JSONDecodeError, ProtocolValidationError, AdapterError) as exc:
                validation_error = exc
        raise AdapterError(
            "PAUSED_INFRASTRUCTURE",
            f"schema repair exhausted:{getattr(validation_error, 'code', 'INVALID')}",
        )

    def close(self) -> None:
        process = self.process
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.terminate()
            process.wait(timeout=3.0)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                process.kill()
                process.wait(timeout=3.0)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                pass
        if process.stderr is not None:
            try:
                data = process.stderr.read(MAX_STDERR_BYTES + 1)
            except OSError:
                data = b""
            if data:
                # Keep only a bounded classification-safe summary. Never persist
                # stderr verbatim; it may contain paths or account information.
                self._stderr_summary = f"stderr_bytes={min(len(data), MAX_STDERR_BYTES)}"
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass
        self.process = None
