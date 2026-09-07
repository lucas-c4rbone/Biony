"""Orquestração central inicial dos serviços do Biony Core."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING
import unicodedata
from uuid import uuid4

if TYPE_CHECKING:
    from core.audio import AudioService

from core.biony_device import validate_biony_command
from core.conversation import ConversationService
from core.devices import DeviceCommand, DeviceManager
from core.events import EventPublisher
from core.memory import MemoryStore
from core.models import BrainResponse, ConversationRequest, CoreEvent, DeviceKind, Memory, MemoryRequest, PendingAction, ToolRequest, ToolResult
from core.permissions import PermissionDecision, PermissionPolicy
from core.state_machine import BionyState, StateMachine
from core.tools import ToolCatalog
from face.expressions import FaceExpression


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    content: str


@dataclass
class ConversationSession:
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
        while len(self.history) > self.max_messages or sum(len(item.content) for item in self.history) > self.max_context_characters:
            self.history.pop(0)

    def context(self) -> tuple[ConversationMessage, ...]:
        return tuple(self.history)


class BionyCore:
    """Coordena serviços centrais e o contexto temporário de conversas."""

    def __init__(self, state_machine: StateMachine, conversation_service: ConversationService,
                 memory_store: MemoryStore, tool_catalog: ToolCatalog,
                 permission_policy: PermissionPolicy, event_publisher: EventPublisher,
                 device_manager: DeviceManager | None = None,
                 audio_service: AudioService | None = None, *,
                 max_context_messages: int = 20, max_context_characters: int = 4_000) -> None:
        self.state_machine = state_machine
        self.conversation_service = conversation_service
        self.memory_store = memory_store
        self.tool_catalog = tool_catalog
        self.permission_policy = permission_policy
        self.event_publisher = event_publisher
        self.device_manager = device_manager
        self.audio_service = audio_service
        self._max_context_messages = max_context_messages
        self._max_context_characters = max_context_characters
        self._sessions: dict[str, ConversationSession] = {}
        self._pending_actions: dict[str, PendingAction] = {}

    def get_or_create_session(self, identifier: str | None = None) -> ConversationSession:
        session_id = identifier or str(uuid4())
        session = self._sessions.get(session_id)
        if session is None:
            session = ConversationSession(session_id, self._max_context_messages, self._max_context_characters)
            self._sessions[session_id] = session
            self._publish("session_created", session)
        return session

    def handle_message(self, request: ConversationRequest, session_id: str | None = None) -> BrainResponse:
        session = self.get_or_create_session(session_id)
        if self._starts_with_wake_word(request.message):
            self._cancel_pending_actions_for_session(session.identifier)
        session.continuation_active = True
        self._publish("conversation_started", session)
        session.add_message("user", request.message)
        memories = self._find_relevant_memories(request.message, session)
        response = self.conversation_service.respond(request, memories, tuple(self.tool_catalog.list_definitions()))
        if response.memory_request is not None:
            response = self._respond_after_memory_request(session, response.memory_request)
        if response.tool_requests:
            response = self._respond_after_tool_request(session, response.tool_requests[0])
        if response.message is not None:
            session.add_message("assistant", response.message)
        self._publish("response_produced", session)
        return response

    def respond(self, request: ConversationRequest, session_id: str | None = None) -> BrainResponse:
        return self.handle_message(request, session_id)

    def get_context(self, session_id: str) -> tuple[ConversationMessage, ...]:
        return self.get_or_create_session(session_id).context()

    def set_continuation_active(self, session_id: str, active: bool) -> None:
        self.get_or_create_session(session_id).continuation_active = active

    def get_pending_action(self, identifier: str) -> PendingAction | None:
        return self._pending_actions.get(identifier)

    def confirm_pending_action(self, session_id: str, action_id: str, response: str) -> BrainResponse | None:
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
        result = self._execute_tool(ToolRequest(action.tool_name, action.arguments, action.tool_request_id), session, confirmed=True)
        session.add_message("tool", str(result.value))
        final_response = self.conversation_service.respond_to_tool_result(result)
        if final_response.message is not None:
            session.add_message("assistant", final_response.message)
        self._publish("response_produced", session)
        return final_response

    def save_memory(self, memory: Memory) -> None:
        self.memory_store.save(memory)
        self.event_publisher.publish(CoreEvent(event_type="memory_saved"))

    def remove_memory(self, memory: Memory) -> bool:
        removed = self.memory_store.remove(memory)
        if removed:
            self.event_publisher.publish(CoreEvent(event_type="memory_removed"))
        return removed

    def transition_to(self, state: BionyState, device_id: str | None = None) -> bool:
        """Solicita uma transição de estado e publica mudanças efetivas."""
        changed = self.state_machine.transition_to(state)
        if changed:
            self.event_publisher.publish(CoreEvent(event_type="state_changed", data={"state": state.name}))
            self.set_device_state(state, device_id=device_id)
        return changed

    def set_device_state(
        self, state: BionyState | str, device_id: str | None = None
    ) -> list[DeviceCommand]:
        """Envia o comando set_state para o(s) dispositivo(s) Biony 1.0."""
        state_str = state.name if isinstance(state, BionyState) else str(state)
        validated_args = validate_biony_command("set_state", {"state": state_str})
        return self._send_biony_command("set_state", validated_args, device_id=device_id)

    def set_device_expression(
        self, expression: FaceExpression | str, device_id: str | None = None
    ) -> list[DeviceCommand]:
        """Envia o comando set_expression para o(s) dispositivo(s) Biony 1.0."""
        expr_str = expression.name if isinstance(expression, FaceExpression) else str(expression)
        validated_args = validate_biony_command("set_expression", {"expression": expr_str})
        return self._send_biony_command("set_expression", validated_args, device_id=device_id)

    def play_device_animation(
        self, animation: str, device_id: str | None = None
    ) -> list[DeviceCommand]:
        """Envia o comando play_animation para o(s) dispositivo(s) Biony 1.0."""
        validated_args = validate_biony_command("play_animation", {"animation": animation})
        return self._send_biony_command("play_animation", validated_args, device_id=device_id)

    def _send_biony_command(
        self, command_type: str, arguments: dict[str, object], device_id: str | None = None
    ) -> list[DeviceCommand]:
        if self.device_manager is None:
            return []

        if device_id is not None:
            device = self.device_manager.get_device(device_id)
            if device is None:
                return []
            return [self.device_manager.send_command(device_id, command_type, arguments)]

        target_ids = [
            dev.identifier
            for dev in self.device_manager.list_devices()
            if dev.kind == DeviceKind.BIONY
        ]
        return [
            self.device_manager.send_command(target_id, command_type, arguments)
            for target_id in target_ids
        ]

    def _respond_after_tool_request(self, session: ConversationSession, request: ToolRequest) -> BrainResponse:
        session.add_message("tool_request", request.name)
        self._publish("tool_requested", session, tool_name=request.name)
        tool = self.tool_catalog.find(request.name)
        if tool is not None and self.permission_policy.decide(tool.definition) is PermissionDecision.REQUIRES_CONFIRMATION:
            action = PendingAction(str(uuid4()), session.identifier, request.name, request.arguments, request.identifier)
            self._pending_actions[action.identifier] = action
            self._publish("confirmation_required", session, action_id=action.identifier, tool_name=request.name)
            return BrainResponse(message="Ação requer confirmação.")
        result = self._execute_tool(request, session)
        session.add_message("tool", str(result.value))
        return self.conversation_service.respond_to_tool_result(result)

    def _respond_after_memory_request(self, session: ConversationSession, request: MemoryRequest) -> BrainResponse:
        memories = tuple(self.memory_store.search(request.query))
        self._publish("memory_searched", session)
        return self.conversation_service.respond_to_memory_result(memories, request)

    def _find_relevant_memories(self, message: str, session: ConversationSession) -> tuple[Memory, ...]:
        if not self.conversation_service.supports_memory:
            return ()
        memories = tuple(self.memory_store.search(message))
        self._publish("memory_searched", session)
        return memories

    def _execute_tool(self, request: ToolRequest, session: ConversationSession, confirmed: bool = False) -> ToolResult:
        tool = self.tool_catalog.find(request.name)
        if tool is None:
            result = ToolResult(request.name, False, "Tool not found.", request.identifier)
            self._publish("tool_failed", session, tool_name=request.name)
            return result
        decision = self.permission_policy.decide(tool.definition, confirmed=confirmed)
        if decision is PermissionDecision.DENIED:
            result = ToolResult(request.name, False, "Tool permission denied.", request.identifier)
            self._publish("permission_denied", session, tool_name=request.name)
            return result
        if decision is PermissionDecision.REQUIRES_CONFIRMATION:
            result = ToolResult(request.name, False, "Tool requires confirmation.", request.identifier)
            self._publish("tool_failed", session, tool_name=request.name)
            return result
        try:
            result = tool.execute(request)
        except Exception as error:
            result = ToolResult(request.name, False, f"Tool execution failed: {error}", request.identifier)
        if result.request_id is None:
            result = replace(result, request_id=request.identifier)
        self._publish("tool_executed" if result.success else "tool_failed", session, tool_name=request.name)
        return result

    def _publish(self, event_type: str, session: ConversationSession, **data: object) -> None:
        self.event_publisher.publish(CoreEvent(event_type=event_type, data={"session_id": session.identifier, **data}))

    def _cancel_pending_actions_for_session(self, session_id: str) -> None:
        session = self.get_or_create_session(session_id)
        for action_id, action in tuple(self._pending_actions.items()):
            if action.session_id == session_id:
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