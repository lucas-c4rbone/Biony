"""Orquestração central inicial dos serviços do Biony Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from core.conversation import ConversationService
from core.events import EventPublisher
from core.memory import MemoryStore
from core.models import BrainResponse, ConversationRequest, CoreEvent
from core.permissions import PermissionPolicy
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
        session.continuation_active = True
        self._publish("conversation_started", session)
        session.add_message("user", request.message)

        response = self.conversation_service.respond(request)

        session.add_message("assistant", response.message)
        self._publish("response_produced", session)
        return response

    def get_context(self, session_id: str) -> tuple[ConversationMessage, ...]:
        """Retorna o contexto temporário relevante da sessão informada."""
        return self.get_or_create_session(session_id).context()

    def set_continuation_active(self, session_id: str, active: bool) -> None:
        """Atualiza o estado da futura janela de continuação da sessão."""
        self.get_or_create_session(session_id).continuation_active = active

    def transition_to(self, state: BionyState) -> bool:
        """Solicita uma transição de estado e publica mudanças efetivas."""
        changed = self.state_machine.transition_to(state)
        if changed:
            self.event_publisher.publish(CoreEvent(event_type="state_changed", data={"state": state.name}))
        return changed

    def _publish(self, event_type: str, session: ConversationSession) -> None:
        self.event_publisher.publish(CoreEvent(event_type=event_type, data={"session_id": session.identifier}))