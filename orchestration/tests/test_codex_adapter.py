# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from goodix_orchestrator.codex_adapter import (
    AdapterError,
    CodexAppServer,
    MessageKind,
    TurnResult,
    classify_server_message,
)
from goodix_orchestrator.persistence import SQLiteStateStore
from goodix_orchestrator.protocols import ProtocolValidationError
from goodix_orchestrator.structured_output import (
    ExecutionClass,
    ModelRouter,
)


FIXTURE = Path(__file__).parent / "fixtures" / "fake_app_server.py"


class CodexAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def adapter(self, scenario="normal", *, store=False, extra=()):
        state_store = None
        if store:
            state_store = SQLiteStateStore(self.root / "state.sqlite3")
            state_store.initialize()
        return CodexAppServer(
            sys.executable,
            app_server_args=(str(FIXTURE), scenario, *extra),
            process_cwd=self.root,
            store=state_store,
            timeout=3.0,
        )

    def test_message_classification(self) -> None:
        self.assertEqual(classify_server_message({"id": 1, "result": {}}), MessageKind.RESPONSE)
        self.assertEqual(
            classify_server_message({"method": "turn/completed", "params": {}}),
            MessageKind.SERVER_NOTIFICATION,
        )
        self.assertEqual(
            classify_server_message({"id": "s1", "method": "approval", "params": {}}),
            MessageKind.SERVER_REQUEST,
        )
        with self.assertRaises(AdapterError):
            classify_server_message({"id": 1, "result": {}, "error": {}})

    def test_handshake_auth_models_contexts_resume_and_turn(self) -> None:
        adapter = self.adapter(store=True)
        with adapter:
            permission_config = adapter._permission_config(
                ModelRouter.review().context_class, str(self.root), "high"
            )
            profile = permission_config["permissions"]["o002-pm-read-only"]
            self.assertEqual(profile["filesystem"][adapter.executable], "read")
            self.assertEqual(adapter.pending_request_ids, ())
            self.assertEqual(adapter.account_mode(), "CHATGPT")
            self.assertIn("gpt-5.6-sol", adapter.model_catalog())
            plan = adapter.start_thread(ModelRouter.planning("STANDARD"), self.root)
            review = adapter.start_thread(ModelRouter.review(), self.root)
            executor = adapter.start_thread(
                ModelRouter.execution(ExecutionClass.BOUNDED_IMPLEMENTATION), self.root
            )
            self.assertEqual(len({plan.thread_id, review.thread_id, executor.thread_id}), 3)
            resumed = adapter.resume_thread(plan.thread_id, plan.route, self.root)
            self.assertEqual(resumed.thread_id, plan.thread_id)
            result = adapter.run_turn(
                executor,
                "fixture",
                output_schema={"type": "object"},
                dispatch_id="DISPATCH-001",
            )
            self.assertEqual(json.loads(result.final_text), {"ok": True})
            corrective = adapter.reroute_context(
                executor,
                ModelRouter.execution(ExecutionClass.LOCAL_CORRECTIVE),
            )
            result = adapter.run_turn(
                corrective,
                "fixture corrective",
                output_schema={"type": "object"},
                dispatch_id="DISPATCH-002",
            )
            self.assertEqual(json.loads(result.final_text), {"ok": True})
            contexts = adapter.store.list_contexts(active_only=True)
            self.assertEqual(len(contexts), 3)
            self.assertEqual(
                adapter.store.routing_counts(),
                {"EXEC_BOUNDED_IMPLEMENTATION": 1, "EXEC_LOCAL_CORRECTIVE": 1},
            )

    def test_every_completed_dispatch_reobserves_effective_route(self) -> None:
        adapter = self.adapter(store=True)
        with adapter, patch.object(
            adapter, "_observe_thread_route", wraps=adapter._observe_thread_route
        ) as observe:
            plan = adapter.start_thread(ModelRouter.planning("STANDARD"), self.root)
            review = adapter.start_thread(ModelRouter.review(), self.root)
            executor = adapter.start_thread(
                ModelRouter.execution(ExecutionClass.BOUNDED_IMPLEMENTATION), self.root
            )
            contexts = (plan, plan, review, review, executor, executor)
            for index, context in enumerate(contexts):
                adapter.run_turn(
                    context,
                    "fixture",
                    output_schema={"type": "object"},
                    dispatch_id=f"DISPATCH-REVERIFY-{index}",
                )
            corrective = adapter.reroute_context(
                executor, ModelRouter.execution(ExecutionClass.LOCAL_CORRECTIVE)
            )
            adapter.run_turn(
                corrective,
                "fixture",
                output_schema={"type": "object"},
                dispatch_id="DISPATCH-REVERIFY-CORRECTIVE",
            )
            self.assertEqual(observe.call_count, 7)

    def test_post_turn_route_mismatch_is_not_persisted(self) -> None:
        adapter = self.adapter("post-turn-effort-mismatch", store=True)
        with adapter:
            context = adapter.start_thread(ModelRouter.review(), self.root)
            with self.assertRaises(AdapterError) as caught:
                adapter.run_turn(
                    context,
                    "fixture",
                    output_schema={"type": "object"},
                    dispatch_id="DISPATCH-POST-TURN-MISMATCH",
                )
            self.assertEqual(caught.exception.code, "PAUSED_MODEL_UNAVAILABLE")
            self.assertEqual(adapter.store.list_dispatches(), ())

    def test_schema_repair_does_not_echo_invalid_content(self) -> None:
        adapter = self.adapter()
        invalid = TurnResult("turn-1", "completed", '{"bad":"SECRET_SENTINEL"}')
        valid = TurnResult("turn-2", "completed", '{"ok":true}')

        def validator(payload):
            if payload.get("ok") is not True:
                raise ProtocolValidationError("MISSING_FIELD", "ok", repr(payload))
            return payload

        with patch.object(adapter, "run_turn", side_effect=(invalid, valid)) as run:
            result = adapter.run_structured_turn(
                object(),
                "ORIGINAL",
                output_schema={"type": "object"},
                validator=validator,
                dispatch_id="DISPATCH-REPAIR",
            )
        self.assertEqual(result, {"ok": True})
        repair_prompt = run.call_args_list[1].args[1]
        self.assertIn("VALIDATION_FAILURE_CODE=MISSING_FIELD", repair_prompt)
        self.assertNotIn("VALIDATION_FAILURE_DETAIL", repair_prompt)
        self.assertNotIn("SECRET_SENTINEL", repair_prompt)

    def test_api_key_and_unknown_auth_are_denied_without_email_output(self) -> None:
        for scenario in ("api-key", "unknown-auth"):
            adapter = self.adapter(scenario)
            with self.subTest(scenario=scenario), adapter:
                with self.assertRaises(AdapterError) as caught:
                    adapter.account_mode()
                self.assertEqual(caught.exception.code, "AUTH_NOT_CHATGPT")
                self.assertNotIn("@", str(caught.exception))

    def test_model_and_effort_mismatch_pause_without_downgrade(self) -> None:
        for scenario in ("model-mismatch", "effort-mismatch", "model-unavailable"):
            adapter = self.adapter(scenario)
            with self.subTest(scenario=scenario), adapter:
                with self.assertRaises(AdapterError) as caught:
                    adapter.start_thread(ModelRouter.review(), self.root)
                self.assertEqual(caught.exception.code, "PAUSED_MODEL_UNAVAILABLE")

    def test_unexpected_approval_is_declined_and_pauses(self) -> None:
        log = self.root / "denial.json"
        adapter = self.adapter("unexpected-approval", extra=(str(log),))
        with adapter:
            context = adapter.start_thread(ModelRouter.review(), self.root)
            with self.assertRaises(AdapterError) as caught:
                adapter.run_turn(
                    context,
                    "fixture",
                    output_schema={"type": "object"},
                    dispatch_id="DISPATCH-APPROVAL",
                )
            self.assertEqual(caught.exception.code, "UNEXPECTED_APPROVAL_OR_SERVER_REQUEST")
            deadline = time.monotonic() + 1.0
            while not log.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
        denial = json.loads(log.read_text(encoding="utf-8"))
        self.assertEqual(denial["result"]["decision"], "decline")

    def test_protocol_failures_are_fail_closed(self) -> None:
        for scenario, code in (
            ("malformed-frame", "MALFORMED_PROTOCOL_FRAME"),
            ("unknown-response-id", "UNKNOWN_RESPONSE_ID"),
        ):
            adapter = self.adapter(scenario)
            with self.subTest(scenario=scenario), self.assertRaises(AdapterError) as caught:
                adapter.start()
            self.assertEqual(caught.exception.code, code)
            adapter.close()

    def test_transport_loss_during_turn_is_not_retried(self) -> None:
        adapter = self.adapter("transport-loss")
        with adapter:
            context = adapter.start_thread(ModelRouter.review(), self.root)
            with self.assertRaises(AdapterError) as caught:
                adapter.run_turn(
                    context,
                    "fixture",
                    output_schema={"type": "object"},
                    dispatch_id="DISPATCH-LOSS",
                )
            self.assertEqual(caught.exception.code, "TRANSPORT_LOST_AMBIGUOUS")

    def test_turn_error_classes(self) -> None:
        for scenario, code in (
            ("usage-limit", "PAUSED_RATE_LIMIT"),
            ("session-budget", "PAUSED_RATE_LIMIT"),
            ("unauthorized", "UNAUTHORIZED"),
            ("sandbox-error", "SANDBOX_ERROR"),
        ):
            adapter = self.adapter(scenario)
            with self.subTest(scenario=scenario), adapter:
                context = adapter.start_thread(ModelRouter.review(), self.root)
                with self.assertRaises(AdapterError) as caught:
                    adapter.run_turn(
                        context,
                        "fixture",
                        output_schema={"type": "object"},
                        dispatch_id=f"DISPATCH-{scenario}",
                    )
                self.assertEqual(caught.exception.code, code)


if __name__ == "__main__":
    unittest.main()
