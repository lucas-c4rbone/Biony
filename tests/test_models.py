import unittest

from core.models import (
    BrainResponse,
    ConversationRequest,
    CoreEvent,
    Device,
    DeviceKind,
    Memory,
    MemoryRequest,
    PendingAction,
    ToolRequest,
    ToolResult,
)


class CoreModelsTests(unittest.TestCase):
    def test_constructs_conversation_and_brain_response(self) -> None:
        request = ConversationRequest(message="Olá, Biony")
        response = BrainResponse(message="Olá, Lucas!")

        self.assertEqual(request.message, "Olá, Biony")
        self.assertEqual(response.message, "Olá, Lucas!")
        self.assertEqual(response.tool_requests, ())

    def test_constructs_tool_models_with_defaults(self) -> None:
        request = ToolRequest(name="open_application")
        result = ToolResult(tool_name=request.name, success=True)

        self.assertEqual(request.arguments, {})
        self.assertTrue(result.success)
        self.assertIsNone(result.value)

    def test_constructs_memory_device_and_event(self) -> None:
        memory = Memory(content="Comprar filamento preto")
        device = Device(identifier="desktop-1", kind=DeviceKind.PC)
        event = CoreEvent(event_type="state_changed")

        self.assertEqual(memory.content, "Comprar filamento preto")
        self.assertFalse(device.is_available)
        self.assertEqual(device.capabilities, frozenset())
        self.assertEqual(event.data, {})

    def test_constructs_a_memory_request(self) -> None:
        request = MemoryRequest(query="filamento")

        self.assertEqual(request.query, "filamento")

    def test_constructs_a_pending_action(self) -> None:
        action = PendingAction(
            identifier="action-1",
            session_id="session-1",
            tool_name="fake_tool",
            arguments={"message": "ok"},
        )

        self.assertEqual(action.tool_name, "fake_tool")

    def test_device_kind_is_an_enum(self) -> None:
        self.assertIsInstance(DeviceKind.BIONY, DeviceKind)
        self.assertEqual({kind.name for kind in DeviceKind}, {"BIONY", "MOBILE_APP", "PC", "PRINTER"})