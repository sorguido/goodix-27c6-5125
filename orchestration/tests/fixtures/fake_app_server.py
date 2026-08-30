# SPDX-License-Identifier: GPL-2.0-or-later
"""Tiny deterministic JSONL fixture for O002 adapter tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path


SCENARIO = sys.argv[1] if len(sys.argv) > 1 else "normal"
LOG_PATH = Path(sys.argv[2]) if len(sys.argv) > 2 else None
THREAD_COUNTER = 0
TURN_COUNTER = 0
THREADS: dict[str, dict] = {}


def read() -> dict:
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return json.loads(line)


def send(value: dict) -> None:
    sys.stdout.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def response(request: dict, result: dict) -> None:
    send({"id": request["id"], "result": result})


def account() -> dict:
    if SCENARIO == "api-key":
        return {"account": {"type": "apiKey"}, "requiresOpenaiAuth": True}
    if SCENARIO == "unknown-auth":
        return {"account": {"type": "futureProvider"}, "requiresOpenaiAuth": True}
    return {
        "account": {"type": "chatgpt", "email": "must-not-log@example.invalid", "planType": "pro"},
        "requiresOpenaiAuth": True,
    }


def models() -> list[dict]:
    return [
        {
            "id": model,
            "model": model,
            "displayName": model,
            "description": "fixture",
            "hidden": False,
            "defaultReasoningEffort": "medium",
            "supportedReasoningEfforts": [
                {"reasoningEffort": effort, "description": "fixture"}
                for effort in ("low", "medium", "high", "xhigh", "max")
            ],
            "isDefault": model == "gpt-5.6-terra",
        }
        for model in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
    ]


def thread_result(request: dict, thread_id: str) -> dict:
    params = request["params"]
    config = params.get("config") or {}
    state = THREADS.setdefault(thread_id, {})
    for key in ("model", "cwd", "approvalPolicy"):
        if params.get(key) is not None:
            state[key] = params[key]
    if config.get("model_reasoning_effort") is not None:
        state["effort"] = config["model_reasoning_effort"]
    if config.get("default_permissions") is not None:
        state["profile_id"] = config["default_permissions"]
    effort = state.get("effort")
    model = state.get("model")
    if SCENARIO == "model-mismatch":
        model = "gpt-5.6-luna"
    if SCENARIO == "effort-mismatch":
        effort = "low"
    if SCENARIO == "post-turn-effort-mismatch" and TURN_COUNTER > 0:
        effort = "low"
    sandbox = params.get("sandbox")
    profile_id = state.get("profile_id")
    if sandbox is None:
        sandbox = (
            "workspace-write"
            if profile_id == "o002-executor-workspace"
            else "read-only"
        )
    return {
        "thread": {"id": thread_id},
        "model": model,
        "reasoningEffort": effort,
        "modelProvider": "openai",
        "cwd": state.get("cwd"),
        "sandbox": {
            "type": {
                "read-only": "readOnly",
                "workspace-write": "workspaceWrite",
            }[sandbox]
        },
        "activePermissionProfile": {"id": profile_id, "extends": None},
        "approvalPolicy": state.get("approvalPolicy"),
        "approvalsReviewer": "user",
    }


try:
    initialize = read()
    if initialize.get("method") != "initialize":
        raise SystemExit(20)
    if SCENARIO == "malformed-frame":
        sys.stdout.write("not-json\n")
        sys.stdout.flush()
        raise SystemExit(0)
    if SCENARIO == "unknown-response-id":
        send({"id": initialize["id"] + 99, "result": {}})
        raise SystemExit(0)
    response(initialize, {"serverInfo": {"name": "fake"}})
    initialized = read()
    if initialized.get("method") != "initialized" or "id" in initialized:
        raise SystemExit(21)

    while True:
        request = read()
        method = request.get("method")
        if method == "account/read":
            response(request, account())
        elif method == "account/rateLimits/read":
            response(
                request,
                {
                    "rateLimitsByLimitId": {
                        "fixture": {
                            "rateLimitReachedType": None,
                            "primary": {"resetsAt": 1234, "usedPercent": 25},
                        }
                    }
                },
            )
        elif method == "model/list":
            if SCENARIO == "model-unavailable":
                response(request, {"data": [], "nextCursor": None})
            else:
                response(request, {"data": models(), "nextCursor": None})
        elif method == "thread/start":
            THREAD_COUNTER += 1
            thread_id = f"thr-{THREAD_COUNTER}"
            response(request, thread_result(request, thread_id))
            send({"method": "thread/started", "params": {"thread": {"id": thread_id}}})
        elif method == "thread/resume":
            thread_id = request["params"]["threadId"]
            response(request, thread_result(request, thread_id))
        elif method == "turn/start":
            TURN_COUNTER += 1
            turn_id = f"turn-{TURN_COUNTER}"
            params = request["params"]
            thread_state = THREADS[params["threadId"]]
            for source, target in (
                ("model", "model"),
                ("effort", "effort"),
                ("cwd", "cwd"),
                ("approvalPolicy", "approvalPolicy"),
            ):
                if params.get(source) is not None:
                    thread_state[target] = params[source]
            response(
                request,
                {"turn": {"id": turn_id, "status": "inProgress", "items": []}},
            )
            if SCENARIO == "transport-loss":
                raise SystemExit(0)
            if SCENARIO == "unexpected-approval":
                send(
                    {
                        "id": "server-approval-1",
                        "method": "item/commandExecution/requestApproval",
                        "params": {"threadId": "thr-1", "turnId": turn_id, "itemId": "item-1"},
                    }
                )
                denial = read()
                if LOG_PATH is not None:
                    LOG_PATH.write_text(json.dumps(denial, sort_keys=True), encoding="utf-8")
                continue
            if SCENARIO in {
                "usage-limit",
                "session-budget",
                "unauthorized",
                "sandbox-error",
            }:
                error_class = {
                    "usage-limit": "usageLimitExceeded",
                    "session-budget": "sessionBudgetExceeded",
                    "unauthorized": "unauthorized",
                    "sandbox-error": "sandboxError",
                }[SCENARIO]
                send(
                    {
                        "method": "turn/completed",
                        "params": {
                            "turn": {
                                "id": turn_id,
                                "status": "failed",
                                "items": [],
                                "error": {"message": "fixture", "codexErrorInfo": error_class},
                            }
                        },
                    }
                )
                continue
            send(
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "id": f"item-{TURN_COUNTER}",
                            "type": "agentMessage",
                            "text": '{"ok":true}',
                        }
                    },
                }
            )
            send(
                {
                    "method": "turn/completed",
                    "params": {
                        "turn": {
                            "id": turn_id,
                            "status": "completed",
                            "items": [],
                            "error": None,
                        }
                    },
                }
            )
        else:
            send({"id": request.get("id"), "error": {"code": -32601, "message": "unknown"}})
except EOFError:
    pass
