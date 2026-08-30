"""Deny-by-default O001 capability policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class Capability(StrEnum):
    HOST_READ = "HOST_READ"
    WORKTREE_WRITE = "WORKTREE_WRITE"
    TASK_COMMIT = "TASK_COMMIT"
    TASK_PUSH = "TASK_PUSH"
    INTEGRATION_FF = "INTEGRATION_FF"
    PRIVATE_PR_WRITE = "PRIVATE_PR_WRITE"
    PRIVATE_GATE_ISSUE_WRITE = "PRIVATE_GATE_ISSUE_WRITE"
    PUBLIC_NETWORK_READ = "PUBLIC_NETWORK_READ"
    CODEX_APP_SERVER = "CODEX_APP_SERVER"
    PROTECTED_MATERIAL_REAL = "PROTECTED_MATERIAL_REAL"
    USB_GOODIX = "USB_GOODIX"
    ROOT_SUDO = "ROOT_SUDO"
    WINDOWS_USB_GOODIX = "WINDOWS_USB_GOODIX"
    RUNTIME_INSTALL = "RUNTIME_INSTALL"
    MAIN_MERGE = "MAIN_MERGE"
    HISTORY_REWRITE = "HISTORY_REWRITE"
    PUBLICATION = "PUBLICATION"
    LIVE_RUNNER = "LIVE_RUNNER"


HOST_ONLY_CAPABILITIES = frozenset(
    {
        Capability.HOST_READ,
        Capability.WORKTREE_WRITE,
        Capability.TASK_COMMIT,
        Capability.TASK_PUSH,
        Capability.INTEGRATION_FF,
        Capability.PRIVATE_PR_WRITE,
        Capability.PRIVATE_GATE_ISSUE_WRITE,
        Capability.PUBLIC_NETWORK_READ,
        Capability.CODEX_APP_SERVER,
    }
)

PROTECTED_CAPABILITIES = frozenset(set(Capability) - set(HOST_ONLY_CAPABILITIES))


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    allowed: bool
    requested: tuple[str, ...]
    granted: tuple[str, ...]
    denied: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CapabilityDeniedError(Exception):
    decision: CapabilityDecision

    def __str__(self) -> str:
        return f"CAPABILITY_DENIED: {', '.join(self.decision.reasons)}"


def parse_capability(value: Capability | str) -> Capability:
    if isinstance(value, Capability):
        return value
    return Capability(value)


class CapabilityPolicy:
    """Evaluate explicit grants; missing, protected, and unknown means denied."""

    def __init__(self, explicit_grants: Iterable[Capability | str] = ()) -> None:
        parsed: set[Capability] = set()
        for item in explicit_grants:
            capability = parse_capability(item)
            if capability in PROTECTED_CAPABILITIES:
                raise ValueError(f"protected capability cannot be granted in O001: {capability.value}")
            parsed.add(capability)
        self._grants = frozenset(parsed)

    @property
    def grants(self) -> frozenset[Capability]:
        return self._grants

    def evaluate(self, requested: Iterable[Capability | str]) -> CapabilityDecision:
        requested_names: list[str] = []
        denied: list[str] = []
        reasons: list[str] = []
        for item in requested:
            raw = item.value if isinstance(item, Capability) else str(item)
            requested_names.append(raw)
            try:
                capability = parse_capability(item)
            except ValueError:
                denied.append(raw)
                reasons.append(f"UNKNOWN_CAPABILITY:{raw}")
                continue
            if capability in PROTECTED_CAPABILITIES:
                denied.append(raw)
                reasons.append(f"PROTECTED_CAPABILITY:{raw}")
            elif capability not in self._grants:
                denied.append(raw)
                reasons.append(f"NOT_EXPLICITLY_GRANTED:{raw}")

        unique_requested = tuple(sorted(set(requested_names)))
        unique_denied = tuple(sorted(set(denied)))
        return CapabilityDecision(
            allowed=not unique_denied,
            requested=unique_requested,
            granted=tuple(sorted(cap.value for cap in self._grants)),
            denied=unique_denied,
            reasons=tuple(sorted(set(reasons))),
        )

    def require(self, requested: Iterable[Capability | str]) -> CapabilityDecision:
        decision = self.evaluate(requested)
        if not decision.allowed:
            raise CapabilityDeniedError(decision)
        return decision
