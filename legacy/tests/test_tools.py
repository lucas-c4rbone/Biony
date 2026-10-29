from pathlib import Path
import unittest

from core.models import DeviceKind, ToolRequest, ToolResult
from core.tools import ToolCatalog, ToolDefinition, ToolRisk


class FakeTool:
    def __init__(self) -> None:
        self.definition = ToolDefinition(
            name="fake_tool",
            description="Ferramenta usada somente em testes.",
            expected_arguments=("message",),
            risk=ToolRisk.LOW,
            target=DeviceKind.PC,
        )

    def execute(self, request: ToolRequest) -> ToolResult:
        return ToolResult(tool_name=request.name, success=True, value=request.arguments["message"])


class ToolCatalogTests(unittest.TestCase):
    def test_registers_and_finds_a_tool_definition(self) -> None:
        catalog = ToolCatalog()
        tool = FakeTool()

        catalog.register(tool)

        self.assertIs(catalog.find("fake_tool"), tool)
        self.assertEqual(catalog.list_definitions(), [tool.definition])

    def test_executes_a_fake_tool_and_returns_a_result(self) -> None:
        tool = FakeTool()

        result = tool.execute(ToolRequest(name="fake_tool", arguments={"message": "ok"}))

        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.success)
        self.assertEqual(result.value, "ok")

    def test_tool_can_require_confirmation(self) -> None:
        definition = ToolDefinition(
            name="dangerous_tool",
            description="Ferramenta de teste.",
            risk=ToolRisk.HIGH,
            requires_confirmation=True,
        )

        self.assertTrue(definition.requires_confirmation)
        self.assertEqual(definition.risk, ToolRisk.HIGH)

    def test_has_no_ui_or_system_access(self) -> None:
        source = Path("core/tools.py").read_text(encoding="utf-8")

        self.assertNotIn("PySide6", source)
        self.assertNotIn("subprocess", source)