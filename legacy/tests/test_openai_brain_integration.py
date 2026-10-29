import unittest

from core.biony_core import BionyCore
from core.conversation import ConversationService
from core.events import EventDispatcher
from core.memory import InMemoryMemoryStore
from core.models import ConversationRequest, CoreEvent, Memory, ToolRequest, ToolResult
from core.openai_brain import OpenAIBrain, OpenAIFunctionCall, OpenAIInteraction
from core.permissions import SimplePermissionPolicy
from core.state_machine import StateMachine
from core.tools import ToolCatalog, ToolDefinition


class FakeOpenAIClient:
    def __init__(self, interactions: list[OpenAIInteraction]) -> None:
        self.interactions = interactions
        self.interaction_calls: list[tuple[str, str, tuple[dict[str, object], ...]]] = []
        self.continuation_calls: list[tuple[str, str, str, object]] = []

    def create_response(self, *, model: str, message: str) -> str:
        return "Resposta textual fake."

    def create_interaction(
        self, *, model: str, message: str, tools: tuple[dict[str, object], ...]
    ) -> OpenAIInteraction:
        self.interaction_calls.append((model, message, tools))
        return self.interactions.pop(0)

    def continue_interaction(
        self, *, model: str, response_id: str, call_id: str, result: object
    ) -> OpenAIInteraction:
        self.continuation_calls.append((model, response_id, call_id, result))
        return self.interactions.pop(0)


class FakeTool:
    def __init__(self, requires_confirmation: bool = False) -> None:
        self.definition = ToolDefinition(
            name="fake_status",
            description="Returns a fake status.",
            expected_arguments=("status",),
            requires_confirmation=requires_confirmation,
        )
        self.requests: list[ToolRequest] = []

    def execute(self, request: ToolRequest) -> ToolResult:
        self.requests.append(request)
        return ToolResult(tool_name=request.name, success=True, value="status ok")


class OpenAIBrainIntegrationTests(unittest.TestCase):
    def test_core_executes_an_openai_tool_request_and_returns_its_result(self) -> None:
        client = FakeOpenAIClient([
            OpenAIInteraction("response-1", function_calls=(
                OpenAIFunctionCall("call-1", "fake_status", {"status": "ok"}),
            )),
            OpenAIInteraction("response-2", text="O status está ok."),
        ])
        tool = FakeTool()
        core, _ = self._create_core(OpenAIBrain(client=client), tool)

        response = core.handle_message(ConversationRequest(message="Qual o status?"), "session-1")

        self.assertEqual(response.message, "O status está ok.")
        self.assertEqual(tool.requests[0].identifier, "call-1")
        self.assertEqual(client.continuation_calls[0][1:], ("response-1", "call-1", {"success": True, "value": "status ok"}))
        tool_names = [definition["name"] for definition in client.interaction_calls[0][2]]
        self.assertIn("fake_status", tool_names)

    def test_core_respects_denial_and_confirmation_for_openai_tool_requests(self) -> None:
        denied_client = FakeOpenAIClient([
            OpenAIInteraction("response-1", function_calls=(OpenAIFunctionCall("call-1", "fake_status", {}),)),
            OpenAIInteraction("response-2", text="Não posso executar."),
        ])
        denied_tool = FakeTool()
        denied_core, _ = self._create_core(
            OpenAIBrain(client=denied_client),
            denied_tool,
            SimplePermissionPolicy(denied_tool_names=frozenset({"fake_status"})),
        )

        denied_core.handle_message(ConversationRequest(message="Use a ferramenta"), "session-1")

        self.assertEqual(denied_tool.requests, [])
        self.assertFalse(denied_client.continuation_calls[0][3]["success"])

        confirmation_client = FakeOpenAIClient([
            OpenAIInteraction("response-3", function_calls=(OpenAIFunctionCall("call-3", "fake_status", {}),)),
            OpenAIInteraction("response-4", text="Ferramenta executada."),
        ])
        confirmation_tool = FakeTool(requires_confirmation=True)
        confirmation_core, events = self._create_core(
            OpenAIBrain(client=confirmation_client), confirmation_tool
        )

        confirmation_core.handle_message(ConversationRequest(message="Use a ferramenta"), "session-2")
        action_id = next(event.data["action_id"] for event in events if event.event_type == "confirmation_required")
        response = confirmation_core.confirm_pending_action("session-2", action_id, "sim")

        self.assertEqual(response.message, "Ferramenta executada.")
        self.assertEqual(len(confirmation_tool.requests), 1)

    def test_core_provides_relevant_memory_and_handles_openai_memory_requests(self) -> None:
        client = FakeOpenAIClient([
            OpenAIInteraction("response-1", text="Seu filamento é preto."),
            OpenAIInteraction("response-2", function_calls=(
                OpenAIFunctionCall("call-memory", "search_memory", {"query": "câmera"}),
            )),
            OpenAIInteraction("response-3", text="Você precisa testar a câmera."),
        ])
        store = InMemoryMemoryStore()
        store.save(Memory(content="Filamento preto"))
        store.save(Memory(content="Testar a câmera"))
        core, _ = self._create_core(OpenAIBrain(client=client), memory_store=store)

        first_response = core.handle_message(ConversationRequest(message="filamento"), "session-1")
        second_response = core.handle_message(ConversationRequest(message="Preciso de um lembrete"), "session-1")

        self.assertEqual(first_response.message, "Seu filamento é preto.")
        self.assertIn("Filamento preto", client.interaction_calls[0][1])
        self.assertEqual(second_response.message, "Você precisa testar a câmera.")
        self.assertEqual(
            client.continuation_calls[0][1:],
            ("response-2", "call-memory", {"memories": ["Testar a câmera"]}),
        )

    def test_openai_brain_keeps_multiple_sessions_in_the_core_isolated(self) -> None:
        client = FakeOpenAIClient([
            OpenAIInteraction("response-1", text="Primeira resposta."),
            OpenAIInteraction("response-2", text="Segunda resposta."),
        ])
        core, _ = self._create_core(OpenAIBrain(client=client))

        core.handle_message(ConversationRequest(message="Primeira mensagem"), "session-1")
        core.handle_message(ConversationRequest(message="Segunda mensagem"), "session-2")

        self.assertEqual(core.get_context("session-1")[0].content, "Primeira mensagem")
        self.assertEqual(core.get_context("session-2")[0].content, "Segunda mensagem")

    @staticmethod
    def _create_core(
        brain: OpenAIBrain,
        tool: FakeTool | None = None,
        permission_policy: SimplePermissionPolicy | None = None,
        memory_store: InMemoryMemoryStore | None = None,
    ) -> tuple[BionyCore, list[CoreEvent]]:
        catalog = ToolCatalog()
        if tool is not None:
            catalog.register(tool)
        events: list[CoreEvent] = []
        dispatcher = EventDispatcher()
        dispatcher.subscribe(events.append)
        return BionyCore(
            state_machine=StateMachine(),
            conversation_service=ConversationService(brain),
            memory_store=memory_store or InMemoryMemoryStore(),
            tool_catalog=catalog,
            permission_policy=permission_policy or SimplePermissionPolicy(),
            event_publisher=dispatcher,
        ), events