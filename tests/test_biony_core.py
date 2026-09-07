import unittest

from core.biony_core import BionyCore
from core.conversation import ConversationService
from core.events import EventDispatcher
from core.memory import InMemoryMemoryStore
from core.models import ConversationRequest, CoreEvent
from core.permissions import SimplePermissionPolicy
from core.simulated_brain import SimulatedBrain
from core.state_machine import BionyState, StateMachine
from core.tools import ToolCatalog


class BionyCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state_machine = StateMachine()
        self.memory_store = InMemoryMemoryStore()
        self.tool_catalog = ToolCatalog()
        self.permission_policy = SimplePermissionPolicy()
        self.events = EventDispatcher()
        self.core = BionyCore(
            state_machine=self.state_machine,
            conversation_service=ConversationService(SimulatedBrain()),
            memory_store=self.memory_store,
            tool_catalog=self.tool_catalog,
            permission_policy=self.permission_policy,
            event_publisher=self.events,
        )

    def test_creates_a_session(self) -> None:
        session = self.core.get_or_create_session()

        self.assertTrue(session.identifier)
        self.assertEqual(session.context(), ())

    def test_reuses_a_session_with_the_same_identifier(self) -> None:
        first = self.core.get_or_create_session("mobile-session")
        second = self.core.get_or_create_session("mobile-session")

        self.assertIs(first, second)

    def test_processes_a_conversation_request_and_updates_context(self) -> None:
        response = self.core.respond(ConversationRequest(message="Olá, Biony"), "session-1")
        context = self.core.get_context("session-1")

        self.assertIn("Lucas", response.message)
        self.assertEqual(len(context), 2)
        self.assertEqual(context[0].content, "Olá, Biony")
        self.assertEqual(context[1].role, "assistant")

    def test_limits_the_number_of_context_messages(self) -> None:
        core = self._create_core(max_context_messages=2, max_context_characters=1_000)

        core.respond(ConversationRequest(message="Primeira mensagem"), "session-1")
        core.respond(ConversationRequest(message="Segunda mensagem"), "session-1")

        context = core.get_context("session-1")
        self.assertEqual(len(context), 2)
        self.assertEqual(context[0].content, "Segunda mensagem")

    def test_limits_the_approximate_context_size(self) -> None:
        core = self._create_core(max_context_messages=10, max_context_characters=20)

        core.respond(ConversationRequest(message="Mensagem longa para limitar"), "session-1")

        context = core.get_context("session-1")
        self.assertLessEqual(sum(len(message.content) for message in context), 20)

    def test_publishes_session_and_conversation_events(self) -> None:
        received: list[CoreEvent] = []
        self.events.subscribe(received.append)

        self.core.respond(ConversationRequest(message="Olá"), "session-1")

        self.assertEqual(
            [event.event_type for event in received],
            ["session_created", "conversation_started", "response_produced"],
        )
        self.assertTrue(all(event.data["session_id"] == "session-1" for event in received))

    def test_uses_the_injected_state_machine(self) -> None:
        changed = self.core.transition_to(BionyState.LISTENING)

        self.assertTrue(changed)
        self.assertEqual(self.state_machine.state, BionyState.LISTENING)

    def test_exposes_injected_dependencies(self) -> None:
        self.assertIs(self.core.memory_store, self.memory_store)
        self.assertIs(self.core.tool_catalog, self.tool_catalog)
        self.assertIs(self.core.permission_policy, self.permission_policy)
        self.assertIs(self.core.event_publisher, self.events)

    @staticmethod
    def _create_core(max_context_messages: int, max_context_characters: int) -> BionyCore:
        return BionyCore(
            state_machine=StateMachine(),
            conversation_service=ConversationService(SimulatedBrain()),
            memory_store=InMemoryMemoryStore(),
            tool_catalog=ToolCatalog(),
            permission_policy=SimplePermissionPolicy(),
            event_publisher=EventDispatcher(),
            max_context_messages=max_context_messages,
            max_context_characters=max_context_characters,
        )