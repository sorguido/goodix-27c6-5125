# SPDX-License-Identifier: GPL-2.0-or-later
import unittest
from dataclasses import replace

from goodix_orchestrator.protocols import (
    Disposition,
    PMDisposition,
    PROTOCOL_VERSION,
    ProtocolValidationError,
)
from goodix_orchestrator.output_schemas import (
    EXECUTOR_WORK_REPORT_SCHEMA,
    PM_PLANNING_OUTPUT_SCHEMA,
    PM_REVIEW_OUTPUT_SCHEMA,
)
from goodix_orchestrator.state import OrchestratorState
from goodix_orchestrator.structured_output import (
    ContextClass,
    ExecutionClass,
    ModelRoute,
    ModelRouter,
    PMPlanningOutput,
    PMReviewOutput,
    RoutingClass,
)

from tests.common import HEAD_ONE, task_manifest


def routed_manifest():
    manifest = task_manifest()
    return replace(
        manifest,
        model_policy=replace(
            manifest.model_policy,
            preferred="gpt-5.6-terra",
            allowed=("gpt-5.6-terra",),
        ),
    )


class StructuredOutputTests(unittest.TestCase):
    def test_wire_schemas_use_codex_fine_tuned_supported_subset(self) -> None:
        unsupported = {
            "allOf",
            "const",
            "maxItems",
            "maxLength",
            "maximum",
            "minItems",
            "minLength",
            "minimum",
            "multipleOf",
            "not",
            "pattern",
            "patternProperties",
        }

        def walk(value):
            if isinstance(value, dict):
                self.assertFalse(unsupported.intersection(value))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        for schema in (
            PM_PLANNING_OUTPUT_SCHEMA,
            EXECUTOR_WORK_REPORT_SCHEMA,
            PM_REVIEW_OUTPUT_SCHEMA,
        ):
            walk(schema)

    def test_canonical_routes_are_exact(self) -> None:
        expected = {
            ExecutionClass.MECHANICAL: ("gpt-5.6-luna", "medium"),
            ExecutionClass.LOCAL_CORRECTIVE: ("gpt-5.6-terra", "medium"),
            ExecutionClass.BOUNDED_IMPLEMENTATION: ("gpt-5.6-terra", "high"),
            ExecutionClass.ARCHITECTURAL_OR_HIGH_RISK: ("gpt-5.6-sol", "high"),
        }
        for execution_class, pair in expected.items():
            with self.subTest(execution_class=execution_class):
                route = ModelRouter.execution(execution_class)
                self.assertEqual((route.model_id, route.reasoning_effort), pair)
        self.assertEqual(
            (ModelRouter.planning("STANDARD").model_id, ModelRouter.planning("STANDARD").reasoning_effort),
            ("gpt-5.6-sol", "medium"),
        )
        self.assertEqual(
            (ModelRouter.review().model_id, ModelRouter.review().reasoning_effort),
            ("gpt-5.6-sol", "high"),
        )

    def test_unknown_class_and_raw_overrides_fail_closed(self) -> None:
        with self.assertRaises(ProtocolValidationError) as caught:
            ModelRouter.execution("CHEAP_AUTO")
        self.assertEqual(caught.exception.code, "UNKNOWN_ROUTING_CLASS")
        payload = {
            "task_manifest": routed_manifest().to_dict(),
            "execution_class": "BOUNDED_IMPLEMENTATION",
            "model": "gpt-5.6-sol",
        }
        with self.assertRaises(ProtocolValidationError) as caught:
            PMPlanningOutput.from_dict(payload)
        self.assertEqual(caught.exception.code, "RAW_ROUTING_OVERRIDE_DENIED")

    def test_planning_route_must_fit_task_policy(self) -> None:
        output = PMPlanningOutput(routed_manifest(), ExecutionClass.BOUNDED_IMPLEMENTATION)
        self.assertEqual(PMPlanningOutput.from_dict(output.to_dict()), output)
        with self.assertRaises(ProtocolValidationError) as caught:
            PMPlanningOutput(task_manifest(), ExecutionClass.BOUNDED_IMPLEMENTATION)
        self.assertEqual(caught.exception.code, "ROUTE_OUTSIDE_TASK_MODEL_POLICY")

    def test_xhigh_and_max_are_never_autonomous_routes(self) -> None:
        catalog = {"gpt-5.6-sol": {"medium", "high", "xhigh", "max"}}
        for effort in ("xhigh", "max", "low"):
            route = ModelRoute(
                RoutingClass.AI_PM_REVIEW,
                ContextClass.AI_PM_REVIEW,
                "gpt-5.6-sol",
                effort,
            )
            with self.subTest(effort=effort), self.assertRaises(ProtocolValidationError) as caught:
                ModelRouter.require_catalog(route, catalog)
            self.assertEqual(caught.exception.code, "AUTONOMOUS_EFFORT_DENIED")

    def test_effective_model_and_effort_mismatch_fail(self) -> None:
        route = ModelRouter.review()
        for model, effort in (("gpt-5.6-terra", "high"), ("gpt-5.6-sol", "medium")):
            with self.subTest(model=model, effort=effort), self.assertRaises(
                ProtocolValidationError
            ) as caught:
                ModelRouter.verify_effective(route, model, effort)
            self.assertEqual(caught.exception.code, "MODEL_ROUTING_MISMATCH")

    def test_review_wrapper_fields_are_disposition_specific(self) -> None:
        corrective = PMReviewOutput(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-001",
                disposition=Disposition.CORRECTIVE,
                reason="Measured criterion missing",
            ),
            ExecutionClass.LOCAL_CORRECTIVE,
            None,
        )
        self.assertEqual(PMReviewOutput.from_dict(corrective.to_dict()), corrective)
        accept = PMReviewOutput(
            PMDisposition(
                protocol_version=PROTOCOL_VERSION,
                task_id="TASK-20260830-001",
                disposition=Disposition.ACCEPT,
                reason="Exact head reviewed",
                reviewed_head_sha=HEAD_ONE,
                accept_target=OrchestratorState.DONE,
            ),
            None,
            None,
        )
        self.assertEqual(PMReviewOutput.from_dict(accept.to_dict()), accept)
        with self.assertRaises(ProtocolValidationError):
            PMReviewOutput(accept.disposition, ExecutionClass.MECHANICAL, None)


if __name__ == "__main__":
    unittest.main()
