from pathlib import Path
import unittest

from core.permissions import PermissionDecision, SimplePermissionPolicy
from core.tools import ToolDefinition


class SimplePermissionPolicyTests(unittest.TestCase):
    def test_allows_a_tool_without_confirmation(self) -> None:
        policy = SimplePermissionPolicy()
        tool = ToolDefinition(name="safe_tool", description="Ferramenta de teste.")

        decision = policy.decide(tool)

        self.assertEqual(decision, PermissionDecision.ALLOWED)

    def test_requires_confirmation_when_declared_by_tool(self) -> None:
        policy = SimplePermissionPolicy()
        tool = ToolDefinition(
            name="guarded_tool",
            description="Ferramenta de teste.",
            requires_confirmation=True,
        )

        decision = policy.decide(tool)

        self.assertEqual(decision, PermissionDecision.REQUIRES_CONFIRMATION)

    def test_denies_an_explicitly_blocked_tool(self) -> None:
        policy = SimplePermissionPolicy(denied_tool_names=frozenset({"blocked_tool"}))
        tool = ToolDefinition(name="blocked_tool", description="Ferramenta de teste.")

        decision = policy.decide(tool)

        self.assertEqual(decision, PermissionDecision.DENIED)

    def test_has_no_ui_or_system_access(self) -> None:
        source = Path("core/permissions.py").read_text(encoding="utf-8")

        self.assertNotIn("PySide6", source)
        self.assertNotIn("subprocess", source)