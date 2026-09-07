from pathlib import Path
import unittest

from core.conversation import ConversationService
from core.models import BrainResponse, ConversationRequest
from core.simulated_brain import SimulatedBrain


class RecordingBrain:
    def __init__(self) -> None:
        self.received_messages: list[str] = []

    def respond(self, message: str) -> str:
        self.received_messages.append(message)
        return "Resposta de teste"


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

    def test_does_not_depend_on_pyside6(self) -> None:
        source = Path("core/conversation.py").read_text(encoding="utf-8")

        self.assertNotIn("PySide6", source)