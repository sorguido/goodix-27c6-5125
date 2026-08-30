# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded JSON Schemas supplied to O002 model turns."""

from __future__ import annotations

from typing import Any


# Codex models are fine-tuned models.  Their Structured Outputs subset rejects
# string/number/array constraint keywords (pattern, minLength, minimum,
# minItems, ...).  Keep the wire schema inside that documented subset; the
# typed from_dict validators enforce those stronger invariants locally before
# any state transition or Git effect.
SHA = {"type": "string"}
TASK_ID = {"type": "string"}


TASK_MANIFEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "protocol_version",
        "task_id",
        "parent_task_id",
        "title",
        "objective",
        "baseline_sha",
        "integration_branch",
        "task_branch",
        "model_policy",
        "gate_class",
        "capabilities_required",
        "scope",
        "acceptance_criteria",
        "manual_update_required",
        "stop_conditions",
    ],
    "properties": {
        "protocol_version": {"enum": ["1.0"]},
        "task_id": TASK_ID,
        "parent_task_id": {"anyOf": [TASK_ID, {"type": "null"}]},
        "title": {"type": "string"},
        "objective": {"type": "string"},
        "baseline_sha": SHA,
        "integration_branch": {"type": "string"},
        "task_branch": {"type": "string"},
        "model_policy": {
            "type": "object",
            "additionalProperties": False,
            "required": ["preferred", "allowed"],
            "properties": {
                "preferred": {"type": "string"},
                "allowed": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "gate_class": {"enum": ["HOST_ONLY"]},
        "capabilities_required": {
            "type": "array",
            "items": {
                "enum": [
                    "HOST_READ",
                    "WORKTREE_WRITE",
                    "TASK_COMMIT",
                    "INTEGRATION_FF",
                    "CODEX_APP_SERVER",
                ]
            },
        },
        "scope": {
            "type": "object",
            "additionalProperties": False,
            "required": ["paths", "non_goals"],
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "non_goals": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "acceptance_criteria": {
            "type": "array",
            "items": {"type": "string"},
        },
        "manual_update_required": {"type": "boolean"},
        "stop_conditions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}


PM_PLANNING_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["task_manifest", "execution_class"],
    "properties": {
        "task_manifest": TASK_MANIFEST_SCHEMA,
        "execution_class": {
            "enum": [
                "MECHANICAL",
                "LOCAL_CORRECTIVE",
                "BOUNDED_IMPLEMENTATION",
                "ARCHITECTURAL_OR_HIGH_RISK",
            ]
        },
    },
}


CANONICAL_DOCUMENTATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["manual_updated", "sections"],
    "properties": {
        "manual_updated": {"type": "boolean"},
        "sections": {"type": "array", "items": {"type": "string"}},
    },
}


POLICY_ASSERTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "usb_open_count",
        "sudo_used",
        "protected_material_accessed",
        "main_modified",
    ],
    "properties": {
        "usb_open_count": {"type": "integer"},
        "sudo_used": {"type": "boolean"},
        "protected_material_accessed": {"type": "boolean"},
        "main_modified": {"type": "boolean"},
    },
}


HUMAN_GATE_MANIFEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "protocol_version", "gate_id", "task_id", "decision_required", "reason",
        "commit_sha", "action_id", "action_digest", "action_to_unlock",
        "residual_risks", "still_forbidden", "requested_by", "status",
        "approval_state", "denial_state",
    ],
    "properties": {
        "protocol_version": {"enum": ["1.0"]},
        "gate_id": {"type": "string"},
        "task_id": TASK_ID,
        "decision_required": {"type": "string"},
        "reason": {"type": "string"},
        "commit_sha": {"anyOf": [SHA, {"type": "null"}]},
        "action_id": {"type": "string"},
        "action_digest": {"type": "string"},
        "action_to_unlock": {"type": "string"},
        "residual_risks": {"type": "array", "items": {"type": "string"}},
        "still_forbidden": {"type": "array", "items": {"type": "string"}},
        "requested_by": {"enum": ["AI_PM"]},
        "status": {"enum": ["PENDING"]},
        "approval_state": {"enum": ["PM_PLANNING", "TASK_READY", "DONE"]},
        "denial_state": {"enum": ["PM_PLANNING", "DONE"]},
    },
}


EXECUTOR_WORK_REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "task_id",
        "outcome",
        "advancement",
        "executable_closure",
        "residual_blocker_or_risk",
        "canonical_documentation",
        "tests",
        "policy_assertions",
    ],
    "properties": {
        "task_id": TASK_ID,
        "outcome": {"enum": ["READY", "BLOCKED"]},
        "advancement": {"type": "string"},
        "executable_closure": {"enum": ["PASS", "FAIL", "NOT_APPLICABLE"]},
        "residual_blocker_or_risk": {"type": "string"},
        "canonical_documentation": CANONICAL_DOCUMENTATION_SCHEMA,
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["command", "status"],
                "properties": {
                    "command": {"type": "string"},
                    "status": {"enum": ["PASS", "FAIL", "SKIP", "NOT_AVAILABLE"]},
                },
            },
        },
        "policy_assertions": POLICY_ASSERTIONS_SCHEMA,
    },
}


PM_DISPOSITION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "protocol_version",
        "task_id",
        "disposition",
        "reason",
        "reviewed_head_sha",
        "findings",
        "accept_target",
        "gate",
        "pause_reason",
        "next_task_id",
    ],
    "properties": {
        "protocol_version": {"enum": ["1.0"]},
        "task_id": TASK_ID,
        "disposition": {"enum": ["ACCEPT", "CORRECTIVE", "REPLAN", "HUMAN_GATE", "PAUSE", "DONE"]},
        "reason": {"type": "string"},
        "reviewed_head_sha": {"anyOf": [SHA, {"type": "null"}]},
        "findings": {"type": "array", "items": {"type": "string"}},
        "accept_target": {
            "anyOf": [
                {"enum": ["PM_PLANNING", "DONE"]},
                {"type": "null"},
            ]
        },
        "gate": {"anyOf": [HUMAN_GATE_MANIFEST_SCHEMA, {"type": "null"}]},
        "pause_reason": {
            "anyOf": [
                {"enum": ["RATE_LIMIT", "MODEL_UNAVAILABLE", "INFRASTRUCTURE"]},
                {"type": "null"},
            ]
        },
        "next_task_id": {"anyOf": [TASK_ID, {"type": "null"}]},
    },
}


PM_REVIEW_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "disposition",
        "corrective_execution_class",
        "replan_planning_class",
    ],
    "properties": {
        "disposition": PM_DISPOSITION_SCHEMA,
        "corrective_execution_class": {
            "anyOf": [
                {
                    "enum": [
                        "MECHANICAL",
                        "LOCAL_CORRECTIVE",
                        "BOUNDED_IMPLEMENTATION",
                        "ARCHITECTURAL_OR_HIGH_RISK",
                    ]
                },
                {"type": "null"},
            ]
        },
        "replan_planning_class": {
            "anyOf": [
                {"enum": ["STANDARD", "ESCALATED"]},
                {"type": "null"},
            ]
        },
    },
}
