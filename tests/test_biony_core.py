import unittest

from core.biony_core import BionyCore
from core.conversation import ConversationService
from core.events import EventDispatcher
from core.memory import InMemoryMemoryStore
from core.models import BrainResponse, ConversationRequest, CoreEvent, Memory, MemoryRequest, ToolRequest, ToolResult
from core.permissions import SimplePermissionPolicy
from core.simulated_brain import SimulatedBrain
from core.state_machine import BionyState, StateMachine
from core.tools import ToolCatalog, ToolDefinition


class ToolRequestingBrain:
    def __init__(self, tool_name: str = "fake_status") -> None:
        self.tool_name = tool_name
        self.received_results: list[ToolResult] = []

    def respond(self, message: str) -> str:
        return "Não usado neste fluxo."

    def respond_with_tools(self, message: str) -> BrainResponse:
        return BrainResponse(tool_requests=(ToolRequest(name=self.tool_name, arguments={"status": "ok"}),))

    def respond_to_tool_result(self, result: ToolResult) -> BrainResponse:
        self.received_results.append(result)
        return BrainResponse(message=f"Resultado final: {result.value}")


class FakeTool:
    def __init__(self, raises_error: bool = False, requires_confirmation: bool = False) -> None:
        self.definition = ToolDefinition(
            name="fake_status",
            description="Ferramenta usada somente em testes.",
            requires_confirmation=requires_confirmation,
        )
        self.raises_error = raises_error
        self.executed_requests: list[ToolRequest] = []

    def execute(self, request: ToolRequest) -> ToolResult:
        self.executed_requests.append(request)
        if self.raises_error:
            raise RuntimeError("Falha de teste")
        return ToolResult(tool_name=request.name, success=True, value="status ok")


class MemoryAwareTestBrain:
    def __init__(self, requests_memory: bool = False) -> None:
        self.requests_memory = requests_memory
        self.received_memories: list[tuple[Memory, ...]] = []
        self.requested_results: list[tuple[Memory, ...]] = []

    def respond(self, message: str) -> str:
        return "Não usado neste fluxo."

    def respond_with_memory(self, message: str, memories: tuple[Memory, ...]) -> BrainResponse:
        self.received_memories.append(memories)
        if self.requests_memory:
            return BrainResponse(memory_request=MemoryRequest(query="câmera"))
        return BrainResponse(message="Resposta com memória.")

    def respond_to_memory_result(self, memories: tuple[Memory, ...]) -> BrainResponse:
        self.requested_results.append(memories)
        return BrainResponse(message="Resposta após busca de memória.")


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
        response = self.core.handle_message(ConversationRequest(message="Olá, Biony"), "session-1")
        context = self.core.get_context("session-1")

        self.assertIn("Lucas", response.message)
        self.assertEqual(len(context), 2)
        self.assertEqual(context[0].content, "Olá, Biony")
        self.assertEqual(context[1].role, "assistant")

    def test_respond_remains_a_compatible_wrapper_for_handle_message(self) -> None:
        response = self.core.respond(ConversationRequest(message="Olá, Biony"), "session-1")

        self.assertIn("Lucas", response.message)
        self.assertEqual(len(self.core.get_context("session-1")), 2)

    def test_keeps_contexts_separate_between_sessions(self) -> None:
        self.core.handle_message(ConversationRequest(message="Olá"), "mobile")
        self.core.handle_message(ConversationRequest(message="Qual seu nome?"), "desktop")

        mobile_context = self.core.get_context("mobile")
        desktop_context = self.core.get_context("desktop")

        self.assertEqual(mobile_context[0].content, "Olá")
        self.assertEqual(desktop_context[0].content, "Qual seu nome?")
        self.assertEqual(len(mobile_context), 2)
        self.assertEqual(len(desktop_context), 2)

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

    def test_pipeline_publishes_main_events_in_logical_order(self) -> None:
        received: list[CoreEvent] = []
        self.events.subscribe(received.append)

        self.core.handle_message(ConversationRequest(message="Olá"), "session-1")

        self.assertEqual(
            [event.event_type for event in received],
            ["session_created", "conversation_started", "response_produced"],
        )

    def test_uses_the_injected_state_machine(self) -> None:
        changed = self.core.transition_to(BionyState.LISTENING)

        self.assertTrue(changed)
        self.assertEqual(self.state_machine.state, BionyState.LISTENING)

    def test_exposes_injected_dependencies(self) -> None:
        self.assertIs(self.core.memory_store, self.memory_store)
        self.assertIs(self.core.tool_catalog, self.tool_catalog)
        self.assertIs(self.core.permission_policy, self.permission_policy)
        self.assertIs(self.core.event_publisher, self.events)

    def test_executes_a_permitted_tool_and_returns_its_result_to_the_brain(self) -> None:
        brain = ToolRequestingBrain()
        tool = FakeTool()
        core, events = self._create_tool_core(brain, tool, SimplePermissionPolicy())

        response = core.respond(ConversationRequest(message="Qual o status?"), "session-1")

        self.assertEqual(len(tool.executed_requests), 1)
        self.assertEqual(brain.received_results[0].value, "status ok")
        self.assertEqual(response.message, "Resultado final: status ok")
        self.assertEqual([message.role for message in core.get_context("session-1")], ["user", "tool_request", "tool", "assistant"])
        self.assertIn("tool_executed", [event.event_type for event in events])

    def test_returns_a_failure_result_when_a_tool_is_not_registered(self) -> None:
        brain = ToolRequestingBrain(tool_name="missing_tool")
        core, events = self._create_tool_core(brain, None, SimplePermissionPolicy())

        core.respond(ConversationRequest(message="Use uma ferramenta"), "session-1")

        self.assertFalse(brain.received_results[0].success)
        self.assertEqual(brain.received_results[0].value, "Tool not found.")
        self.assertIn("tool_failed", [event.event_type for event in events])

    def test_does_not_execute_a_tool_when_permission_is_denied(self) -> None:
        brain = ToolRequestingBrain()
        tool = FakeTool()
        core, events = self._create_tool_core(
            brain, tool, SimplePermissionPolicy(denied_tool_names=frozenset({"fake_status"}))
        )

        core.respond(ConversationRequest(message="Use uma ferramenta"), "session-1")

        self.assertEqual(tool.executed_requests, [])
        self.assertEqual(brain.received_results[0].value, "Tool permission denied.")
        self.assertIn("permission_denied", [event.event_type for event in events])

    def test_does_not_execute_a_tool_that_requires_confirmation(self) -> None:
        brain = ToolRequestingBrain()
        tool = FakeTool(requires_confirmation=True)
        core, events = self._create_tool_core(brain, tool, SimplePermissionPolicy())

        core.respond(ConversationRequest(message="Use uma ferramenta"), "session-1")

        self.assertEqual(tool.executed_requests, [])
        action_id = next(event.data["action_id"] for event in events if event.event_type == "confirmation_required")
        self.assertIsNotNone(core.get_pending_action(action_id))
        self.assertEqual(brain.received_results, [])

    def test_converts_a_tool_exception_into_a_failure_result(self) -> None:
        brain = ToolRequestingBrain()
        tool = FakeTool(raises_error=True)
        core, events = self._create_tool_core(brain, tool, SimplePermissionPolicy())

        core.respond(ConversationRequest(message="Use uma ferramenta"), "session-1")

        self.assertFalse(brain.received_results[0].success)
        self.assertIn("Falha de teste", str(brain.received_results[0].value))
        self.assertIn("tool_failed", [event.event_type for event in events])

    def test_executes_low_risk_tools_automatically(self) -> None:
        brain = ToolRequestingBrain()
        tool = FakeTool()
        core, _ = self._create_tool_core(brain, tool, SimplePermissionPolicy())

        core.respond(ConversationRequest(message="Use a ferramenta"), "session-1")

        self.assertEqual(len(tool.executed_requests), 1)

    def test_creates_pending_action_for_a_tool_requiring_confirmation(self) -> None:
        brain = ToolRequestingBrain()
        tool = FakeTool(requires_confirmation=True)
        core, events = self._create_tool_core(brain, tool, SimplePermissionPolicy())

        response = core.respond(ConversationRequest(message="Use a ferramenta"), "session-1")
        action_id = next(event.data["action_id"] for event in events if event.event_type == "confirmation_required")
        action = core.get_pending_action(action_id)

        self.assertEqual(tool.executed_requests, [])
        self.assertEqual(response.message, "Ação requer confirmação.")
        self.assertEqual(action.tool_name, "fake_status")
        self.assertEqual(action.session_id, "session-1")

    def test_positive_confirmations_execute_the_pending_action(self) -> None:
        for confirmation in ("sim", "pode fazer", "manda"):
            with self.subTest(confirmation=confirmation):
                brain = ToolRequestingBrain()
                tool = FakeTool(requires_confirmation=True)
                core, events = self._create_tool_core(brain, tool, SimplePermissionPolicy())
                core.respond(ConversationRequest(message="Use a ferramenta"), "session-1")
                action_id = next(event.data["action_id"] for event in events if event.event_type == "confirmation_required")

                response = core.confirm_pending_action("session-1", action_id, confirmation)

                self.assertEqual(len(tool.executed_requests), 1)
                self.assertEqual(response.message, "Resultado final: status ok")
                self.assertIsNone(core.get_pending_action(action_id))

    def test_negative_confirmation_cancels_the_pending_action(self) -> None:
        for confirmation in ("não quero", "cancela"):
            with self.subTest(confirmation=confirmation):
                brain = ToolRequestingBrain()
                tool = FakeTool(requires_confirmation=True)
                core, events = self._create_tool_core(brain, tool, SimplePermissionPolicy())
                core.respond(ConversationRequest(message="Use a ferramenta"), "session-1")
                action_id = next(event.data["action_id"] for event in events if event.event_type == "confirmation_required")

                response = core.confirm_pending_action("session-1", action_id, confirmation)

                self.assertEqual(tool.executed_requests, [])
                self.assertEqual(response.message, "Ação cancelada.")
                self.assertIsNone(core.get_pending_action(action_id))
                self.assertIn("confirmation_rejected", [event.event_type for event in events])

    def test_ambiguous_confirmation_keeps_the_action_pending(self) -> None:
        brain = ToolRequestingBrain()
        tool = FakeTool(requires_confirmation=True)
        core, events = self._create_tool_core(brain, tool, SimplePermissionPolicy())
        core.respond(ConversationRequest(message="Use a ferramenta"), "session-1")
        action_id = next(event.data["action_id"] for event in events if event.event_type == "confirmation_required")

        response = core.confirm_pending_action("session-1", action_id, "talvez")

        self.assertEqual(tool.executed_requests, [])
        self.assertEqual(response.message, "Confirme ou cancele a ação pendente.")
        self.assertIsNotNone(core.get_pending_action(action_id))

    def test_wake_word_cancels_a_pending_action_before_new_conversation(self) -> None:
        brain = ToolRequestingBrain()
        tool = FakeTool(requires_confirmation=True)
        core, events = self._create_tool_core(brain, tool, SimplePermissionPolicy())
        core.respond(ConversationRequest(message="Use a ferramenta"), "session-1")
        action_id = next(event.data["action_id"] for event in events if event.event_type == "confirmation_required")

        core.respond(ConversationRequest(message="Biony, outra coisa"), "session-1")

        self.assertEqual(tool.executed_requests, [])
        self.assertIsNone(core.get_pending_action(action_id))
        self.assertIn("pending_action_cancelled", [event.event_type for event in events])

    def test_confirmation_only_executes_the_matching_action_and_publishes_events(self) -> None:
        brain = ToolRequestingBrain()
        first_tool = FakeTool(requires_confirmation=True)
        second_tool = FakeTool(requires_confirmation=True)
        second_tool.definition = ToolDefinition(name="other_status", description="Outra ferramenta.", requires_confirmation=True)
        core, events = self._create_tool_core(brain, first_tool, SimplePermissionPolicy())
        core.tool_catalog.register(second_tool)
        core.respond(ConversationRequest(message="Use a ferramenta"), "session-1")
        action_id = next(event.data["action_id"] for event in events if event.event_type == "confirmation_required")

        core.confirm_pending_action("session-1", action_id, "confirmo")

        self.assertEqual(len(first_tool.executed_requests), 1)
        self.assertEqual(second_tool.executed_requests, [])
        self.assertIn("confirmation_accepted", [event.event_type for event in events])

    def test_continues_normally_when_no_memories_exist(self) -> None:
        response = self.core.respond(ConversationRequest(message="Olá, Biony"), "session-1")

        self.assertIn("Lucas", response.message)
        self.assertEqual(self.memory_store.list_all(), [])

    def test_provides_relevant_memories_to_a_memory_aware_brain(self) -> None:
        brain = MemoryAwareTestBrain()
        core, events, store = self._create_memory_core(brain)
        store.save(Memory(content="Filamento preto"))

        core.respond(ConversationRequest(message="filamento"), "session-1")

        self.assertEqual(brain.received_memories, [(Memory(content="Filamento preto"),)])
        self.assertIn("memory_searched", [event.event_type for event in events])

    def test_memory_aware_brain_continues_when_no_memory_is_relevant(self) -> None:
        brain = MemoryAwareTestBrain()
        core, _, _ = self._create_memory_core(brain)

        response = core.respond(ConversationRequest(message="filamento"), "session-1")

        self.assertEqual(brain.received_memories, [()])
        self.assertEqual(response.message, "Resposta com memória.")

    def test_returns_requested_memory_search_results_to_the_brain(self) -> None:
        brain = MemoryAwareTestBrain(requests_memory=True)
        core, events, store = self._create_memory_core(brain)
        store.save(Memory(content="Testar a câmera"))

        response = core.respond(ConversationRequest(message="Preciso de uma informação"), "session-1")

        self.assertEqual(brain.requested_results, [(Memory(content="Testar a câmera"),)])
        self.assertEqual(response.message, "Resposta após busca de memória.")
        self.assertEqual([message.role for message in core.get_context("session-1")], ["user", "assistant"])
        self.assertEqual([event.event_type for event in events].count("memory_searched"), 2)

    def test_saves_and_removes_memory_only_through_explicit_core_operations(self) -> None:
        received: list[CoreEvent] = []
        self.events.subscribe(received.append)
        memory = Memory(content="Comprar filamento preto")

        self.core.respond(ConversationRequest(message=memory.content), "session-1")
        self.assertEqual(self.memory_store.list_all(), [])
        self.core.save_memory(memory)

        self.assertEqual(self.memory_store.list_all(), [memory])
        self.assertTrue(self.core.remove_memory(memory))
        self.assertEqual(self.memory_store.list_all(), [])
        self.assertEqual(
            [event.event_type for event in received if event.event_type.startswith("memory_")],
            ["memory_saved", "memory_removed"],
        )

    def test_memory_aware_brain_has_no_direct_memory_store_access(self) -> None:
        brain = MemoryAwareTestBrain()

        self.assertFalse(hasattr(brain, "memory_store"))

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

    @staticmethod
    def _create_tool_core(
        brain: ToolRequestingBrain,
        tool: FakeTool | None,
        permission_policy: SimplePermissionPolicy,
    ) -> tuple[BionyCore, list[CoreEvent]]:
        catalog = ToolCatalog()
        if tool is not None:
            catalog.register(tool)
        dispatcher = EventDispatcher()
        events: list[CoreEvent] = []
        dispatcher.subscribe(events.append)
        return (
            BionyCore(
                state_machine=StateMachine(),
                conversation_service=ConversationService(brain),
                memory_store=InMemoryMemoryStore(),
                tool_catalog=catalog,
                permission_policy=permission_policy,
                event_publisher=dispatcher,
            ),
            events,
        )

    @staticmethod
    def _create_memory_core(
        brain: MemoryAwareTestBrain,
    ) -> tuple[BionyCore, list[CoreEvent], InMemoryMemoryStore]:
        store = InMemoryMemoryStore()
        dispatcher = EventDispatcher()
        events: list[CoreEvent] = []
        dispatcher.subscribe(events.append)
        return (
            BionyCore(
                state_machine=StateMachine(),
                conversation_service=ConversationService(brain),
                memory_store=store,
                tool_catalog=ToolCatalog(),
                permission_policy=SimplePermissionPolicy(),
                event_publisher=dispatcher,
            ),
            events,
            store,
        )