import unittest

from goodix_orchestrator.policy import (
    Capability,
    CapabilityDeniedError,
    CapabilityPolicy,
)


class PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = CapabilityPolicy(
            (Capability.HOST_READ, Capability.WORKTREE_WRITE, Capability.TASK_COMMIT)
        )

    def test_explicit_host_only_grants_pass(self) -> None:
        decision = self.policy.require((Capability.HOST_READ, Capability.TASK_COMMIT))
        self.assertTrue(decision.allowed)

    def test_missing_grant_is_denied(self) -> None:
        decision = self.policy.evaluate((Capability.TASK_PUSH,))
        self.assertFalse(decision.allowed)
        self.assertIn("NOT_EXPLICITLY_GRANTED:TASK_PUSH", decision.reasons)

    def test_unknown_capability_is_denied(self) -> None:
        decision = self.policy.evaluate(("PROMPT_OVERRIDE",))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.denied, ("PROMPT_OVERRIDE",))
        with self.assertRaises(CapabilityDeniedError):
            self.policy.require(("PROMPT_OVERRIDE",))

    def test_every_protected_capability_is_denied(self) -> None:
        protected = (
            Capability.PROTECTED_MATERIAL_REAL,
            Capability.USB_GOODIX,
            Capability.ROOT_SUDO,
            Capability.WINDOWS_USB_GOODIX,
            Capability.RUNTIME_INSTALL,
            Capability.MAIN_MERGE,
            Capability.HISTORY_REWRITE,
            Capability.PUBLICATION,
            Capability.LIVE_RUNNER,
        )
        decision = self.policy.evaluate(protected)
        self.assertFalse(decision.allowed)
        self.assertEqual(set(decision.denied), {item.value for item in protected})

    def test_protected_capability_cannot_be_configured_as_grant(self) -> None:
        with self.assertRaises(ValueError):
            CapabilityPolicy((Capability.USB_GOODIX,))


if __name__ == "__main__":
    unittest.main()
