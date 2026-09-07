"""Orquestração central inicial dos serviços do Biony Core."""

from __future__ import annotations

from dataclasses import dataclass, field
import unicodedata
from uuid import uuid4

from core.conversation import ConversationService
from core.events import EventPublisher
from core.memory import MemoryStore
from core.models import BrainResponse, ConversationRequest, CoreEvent, Memory, PendingAction
from core.models import ToolRequest, ToolResult
from core.permissions import PermissionDecision, PermissionPolicy
from core.state_machine import BionyState, StateMachine
from core.tools import ToolCatalog


@dataclass(frozen=True)
class ConversationMessage:
    """Mensagem mantida temporariamente no contexto de uma sessão."""

    role: str
    content: str


@dataclass
class ConversationSession:
    """Contexto temporário e limites de uma conversa identificada."""

    identifier: str
    max_messages: int
    max_context_characters: int
    history: list[ConversationMessage] = field(default_factory=list)
    continuation_active: bool = False

    def __post_init__(self) -> None:
        if self.max_messages < 0 or self.max_context_characters < 0:
            raise ValueError("Context limits must not be negative.")

    def add_message(self, role: str, content: str) -> None:
        if len(content) > self.max_context_characters:
            content = content[-self.max_context_characters :]

        self.history.append(ConversationMessage(role=role, content=content))
        self._trim_history()

    def context(self) -> tuple[ConversationMessage, ...]:
        """Retorna o histórico temporário já limitado da sessão."""
        return tuple(self.history)

    def _trim_history(self) -> None:
        while len(self.history) > self.max_messages:
            self.history.pop(0)

        while sum(len(message.content) for message in self.history) > self.max_context_characters:
            self.history.pop(0)


class BionyCore:
    """Coordena serviços centrais e o contexto temporário de conversas."""

    def __init__(
        self,
        state_machine: StateMachine,
        conversation_service: ConversationService,
        memory_store: MemoryStore,
        tool_catalog: ToolCatalog,
        permission_policy: PermissionPolicy,
        event_publisher: EventPublisher,
        *,
        max_context_messages: int = 20,
        max_context_characters: int = 4_000,
    ) -> None:
        self.state_machine = state_machine
        self.conversation_service = conversation_service
        self.memory_store = memory_store
        self.tool_catalog = tool_catalog
        self.permission_policy = permission_policy
        self.event_publisher = event_publisher
        self._max_context_messages = max_context_messages
        self._max_context_characters = max_context_characters
        self._sessions: dict[str, ConversationSession] = {}
        self._pending_actions: dict[str, PendingAction] = {}

    def get_or_create_session(self, identifier: str | None = None) -> ConversationSession:
        """Obtém uma sessão existente ou cria um novo contexto temporário."""
        session_id = identifier or str(uuid4())
        session = self._sessions.get(session_id)
        if session is None:
            session = ConversationSession(
                identifier=session_id,
                max_messages=self._max_context_messages,
                max_context_characters=self._max_context_characters,
            )
            self._sessions[session_id] = session
            self._publish("session_created", session)
        return session

    def respond(self, request: ConversationRequest, session_id: str | None = None) -> BrainResponse:
        """Processa uma mensagem, atualiza seu contexto e produz uma resposta."""
        session = self.get_or_create_session(session_id)
        if self._starts_with_wake_word(request.message):
            self._cancel_pending_actions_for_session(session.identifier)
        session.continuation_active = True
        self._publish("conversation_started", session)
        session.add_message("user", request.message)

        memories = self._find_relevant_memories(request.message, session)
        response = self.conversation_service.respond(request, memories)
        if response.memory_request is not None:
            response = self._respond_after_memory_request(session, response.memory_request.query)
        if response.tool_requests:
            response = self._respond_after_tool_request(session, response.tool_requests[0])

        if response.message is not None:
            session.add_message("assistant", response.message)
        self._publish("response_produced", session)
        return response

    def get_context(self, session_id: str) -> tuple[ConversationMessage, ...]:
        """Retorna o contexto temporário relevante da sessão informada."""
        return self.get_or_create_session(session_id).context()

    def set_continuation_active(self, session_id: str, active: bool) -> None:
        """Atualiza o estado da futura janela de continuação da sessão."""
        self.get_or_create_session(session_id).continuation_active = active

    def get_pending_action(self, identifier: str) -> PendingAction | None:
        """Retorna uma ação pendente pelo seu identificador próprio."""
        return self._pending_actions.get(identifier)

    def confirm_pending_action(
        self, session_id: str, action_id: str, response: str
    ) -> BrainResponse | None:
        """Processa a resposta do usuário para uma ação pendente da sessão."""
        action = self._pending_actions.get(action_id)
        if action is None or action.session_id != session_id:
            return None

        session = self.get_or_create_session(session_id)
        session.add_message("user", response)
        decision = self._confirmation_decision(response)
        if decision == "negative":
            self._pending_actions.pop(action_id)
            self._publish("confirmation_rejected", session, action_id=action_id)
            return BrainResponse(message="Ação cancelada.")
        if decision != "positive":
            return BrainResponse(message="Confirme ou cancele a ação pendente.")

        self._pending_actions.pop(action_id)
        self._publish("confirmation_accepted", session, action_id=action_id)
        result = self._execute_tool(
            ToolRequest(name=action.tool_name, arguments=action.arguments), session, confirmed=True
        )
        session.add_message("tool", str(result.value))
        final_response = self.conversation_service.respond_to_tool_result(result)
        if final_response.message is not None:
            session.add_message("assistant", final_response.message)
        self._publish("response_produced", session)
        return final_response

    def save_memory(self, memory: Memory) -> None:
        """Salva uma memória após uma decisão explícita da camada chamadora."""
        self.memory_store.save(memory)
        self.event_publisher.publish(CoreEvent(event_type="memory_saved"))

    def remove_memory(self, memory: Memory) -> bool:
        """Remove uma memória e publica o resultado quando ela existir."""
        removed = self.memory_store.remove(memory)
        if removed:
            self.event_publisher.publish(CoreEvent(event_type="memory_removed"))
        return removed

    def transition_to(self, state: BionyState) -> bool:
        """Solicita uma transição de estado e publica mudanças efetivas."""
        changed = self.state_machine.transition_to(state)
        if changed:
            self.event_publisher.publish(CoreEvent(event_type="state_changed", data={"state": state.name}))
        return changed

    def _respond_after_tool_request(self, session: ConversationSession, request: ToolRequest) -> BrainResponse:
        session.add_message("tool_request", request.name)
        self._publish("tool_requested", session, tool_name=request.name)
        tool = self.tool_catalog.find(request.name)
        if tool is not None and self.permission_policy.decide(tool.definition) is PermissionDecision.REQUIRES_CONFIRMATION:
            action = PendingAction(
                identifier=str(uuid4()),
                session_id=session.identifier,
                tool_name=request.name,
                arguments=request.arguments,
            )
            self._pending_actions[action.identifier] = action
            self._publish("confirmation_required", session, action_id=action.identifier, tool_name=request.name)
            return BrainResponse(message="Ação requer confirmação.")

        result = self._execute_tool(request, session)
        session.add_message("tool", str(result.value))
        return self.conversation_service.respond_to_tool_result(result)

    def _respond_after_memory_request(self, session: ConversationSession, query: str) -> BrainResponse:
        memories = tuple(self.memory_store.search(query))
        self._publish("memory_searched", session)
        return self.conversation_service.respond_to_memory_result(memories)

    def _find_relevant_memories(
        self, message: str, session: ConversationSession
    ) -> tuple[Memory, ...]:
        if not self.conversation_service.supports_memory:
            return ()
        memories = tuple(self.memory_store.search(message))
        self._publish("memory_searched", session)
        return memories

    def _execute_tool(
        self, request: ToolRequest, session: ConversationSession, confirmed: bool = False
    ) -> ToolResult:
        tool = self.tool_catalog.find(request.name)
        if tool is None:
            result = ToolResult(tool_name=request.name, success=False, value="Tool not found.")
            self._publish("tool_failed", session, tool_name=request.name)
            return result

        decision = self.permission_policy.decide(tool.definition, confirmed=confirmed)
        if decision is PermissionDecision.DENIED:
            result = ToolResult(tool_name=request.name, success=False, value="Tool permission denied.")
            self._publish("permission_denied", session, tool_name=request.name)
            return result
        if decision is PermissionDecision.REQUIRES_CONFIRMATION:
            result = ToolResult(tool_name=request.name, success=False, value="Tool requires confirmation.")
            self._publish("tool_failed", session, tool_name=request.name)
            return result

        try:
            result = tool.execute(request)
        except Exception as error:
            result = ToolResult(tool_name=request.name, success=False, value=f"Tool execution failed: {error}")

        self._publish("tool_executed" if result.success else "tool_failed", session, tool_name=request.name)
        return result

    def _publish(self, event_type: str, session: ConversationSession, **data: object) -> None:
        self.event_publisher.publish(
            CoreEvent(event_type=event_type, data={"session_id": session.identifier, **data})
        )

    def _cancel_pending_actions_for_session(self, session_id: str) -> None:
        action_ids = [
            action_id
            for action_id, action in self._pending_actions.items()
            if action.session_id == session_id
        ]
        session = self.get_or_create_session(session_id)
        for action_id in action_ids:
            self._pending_actions.pop(action_id)
            self._publish("pending_action_cancelled", session, action_id=action_id)

    @staticmethod
    def _confirmation_decision(response: str) -> str | None:
        normalized = BionyCore._normalize_text(response)
        words = set(normalized.replace("?", " ").replace("!", " ").replace(",", " ").split())
        if words & {"nao", "negativo", "cancela", "cancelar", "esquece", "no"} or "deixa pra la" in normalized:
            return "negative"
        if words & {"sim", "pode", "manda", "vai", "afirmativo", "yes", "confirmo"}:
            return "positive"
        return None

    @staticmethod
    def _starts_with_wake_word(message: str) -> bool:
        return BionyCore._normalize_text(message).startswith("biony")

    @staticmethod
    def _normalize_text(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        return "".join(character for character in decomposed if not unicodedata.combining(character))