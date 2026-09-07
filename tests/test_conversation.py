from pathlib import Path
import unittest

from core.conversation import ConversationService
from core.models import BrainResponse, ConversationRequest, Memory, ToolRequest, ToolResult
from core.simulated_brain import SimulatedBrain


class RecordingBrain:
    def __init__(self) -> None:
        self.received_messages: list[str] = []

    def respond(self, message: str) -> str:
        self.received_messages.append(message)
        return "Resposta de teste"


class ToolRequestingBrain:
    def respond(self, message: str) -> str:
        return "Não usado neste teste."

    def respond_with_tools(self, message: str) -> BrainResponse:
        return BrainResponse(tool_requests=(ToolRequest(name="fake_tool"),))

    def respond_to_tool_result(self, result: ToolResult) -> BrainResponse:
        return BrainResponse(message="Resultado recebido.")


class MemoryAwareTestBrain:
    def respond(self, message: str) -> str:
        return "Não usado neste teste."

    def respond_with_memory(self, message: str, memories: tuple[Memory, ...]) -> BrainResponse:
        return BrainResponse(message=memories[0].content if memories else "Sem memória")

    def respond_to_memory_result(self, memories: tuple[Memory, ...]) -> BrainResponse:
        return BrainResponse(message="Resultado recebido.")


class ConversationServiceTests(unittest.TestCase):
    def test_uses_simulated_brain_for_a_basic_conversation(self) -> None:
        service = ConversationService(SimulatedBrain())

        response = service.respond(ConversationRequest(message="Olá, Biony"))

        self.assertIsInstance(response, BrainResponse)
        self.assertIn("Lucas", response.message)

    def test_passes_request_message_to_injected_brain(self) -> None:
        brain = RecordingBrain()
        service = ConversationService(brain)

        response = service.respond(ConversationRequest(message="Mensagem de teste"))

        self.assertEqual(brain.received_messages, ["Mensagem de teste"])
        self.assertEqual(response.message, "Resposta de teste")

    def test_supports_an_optional_tool_aware_brain(self) -> None:
        service = ConversationService(ToolRequestingBrain())

        response = service.respond(ConversationRequest(message="Consulte o status"))

        self.assertIsNone(response.message)
        self.assertEqual(response.tool_requests[0].name, "fake_tool")

    def test_supports_an_optional_memory_aware_brain(self) -> None:
        service = ConversationService(MemoryAwareTestBrain())

        response = service.respond(
            ConversationRequest(message="Qual meu filamento?"),
            (Memory(content="Filamento preto"),),
        )

        self.assertTrue(service.supports_memory)
        self.assertEqual(response.message, "Filamento preto")

    def test_does_not_depend_on_pyside6(self) -> None:
        source = Path("core/conversation.py").read_text(encoding="utf-8")

        self.assertNotIn("PySide6", source)