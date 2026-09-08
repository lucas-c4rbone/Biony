"""Composicao do simulador virtual, sem dependencia de Qt."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import unicodedata
from typing import Callable

from core.biony_core import BionyCore
from core.biony_device import create_biony_device
from core.conversation import ConversationService
from core.devices import DeviceCommand, DeviceManager
from core.events import EventDispatcher
from core.memory import InMemoryMemoryStore
from core.models import BrainResponse, ConversationRequest, CoreEvent, Memory
from core.openai_brain import OpenAIBrain
from core.openrouter_brain import OpenRouterBrain
from core.permissions import SimplePermissionPolicy
from core.simulated_brain import SimulatedBrain
from core.state_machine import BionyState, StateMachine
from core.tools import ToolCatalog
from core.virtual_device import VirtualBionyDevice
from face.expressions import FaceExpression


@dataclass
class SimulatorSnapshot:
    state: BionyState = BionyState.IDLE
    response: str = ""
    last_event: str = ""
    pending_action_id: str | None = None
    animation: str = ""
    animation_revision: int = 0
    events: list[str] = field(default_factory=list)


class SimulatorModel:
    """Liga o Core ao dispositivo virtual e expoe um estado observavel pela UI."""

    def __init__(self, brain: object | None = None) -> None:
        self.events = EventDispatcher()
        self.state_machine = StateMachine()
        self.device_manager = DeviceManager(self.events)
        self.device = VirtualBionyDevice(self._on_device_command)
        self.device_manager.register_device(create_biony_device("virtual-biony"))
        self.device_manager.connect("virtual-biony", self.device)
        self.core = BionyCore(
            state_machine=self.state_machine,
            conversation_service=ConversationService(brain or SimulatedBrain()),
            memory_store=InMemoryMemoryStore(),
            tool_catalog=ToolCatalog(),
            permission_policy=SimplePermissionPolicy(),
            event_publisher=self.events,
            device_manager=self.device_manager,
        )
        self.session_id = "virtual-session"
        self.snapshot = SimulatorSnapshot()
        self._listeners: list[Callable[[SimulatorSnapshot], None]] = []
        self.events.subscribe(self._on_event)

    @property
    def brain_name(self) -> str:
        return type(self.core.conversation_service._brain).__name__

    def subscribe(self, listener: Callable[[SimulatorSnapshot], None]) -> None:
        self._listeners.append(listener)
        listener(self.snapshot)

    def handle_message(self, message: str) -> BrainResponse:
        self.core.transition_to(BionyState.LISTENING)
        self.core.transition_to(BionyState.THINKING)
        response = self._handle_memory_command(message)
        if response is None:
            response = self.core.handle_message(ConversationRequest(message), self.session_id)
        self.snapshot.response = response.message or ""
        self.core.transition_to(BionyState.SPEAKING)
        self.core.transition_to(BionyState.IDLE)
        self._notify()
        return response

    def _handle_memory_command(self, message: str) -> BrainResponse | None:
        normalized = self._normalize(message)
        for marker in ("guarda que ", "anota que "):
            if normalized.startswith(marker):
                self.save_memory(message[message.casefold().find(marker) + len(marker) :].strip())
                return BrainResponse(message="Memoria guardada.")
        memories = self.core.memory_store.list_all()
        if memories and ("qual e" in normalized or "o que" in normalized):
            words = {word for word in normalized.split() if len(word) > 3}
            for memory in reversed(memories):
                if words & set(self._normalize(memory.content).split()):
                    return BrainResponse(message=f"Lembro: {memory.content}")
        return None

    @staticmethod
    def _normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        return "".join(character for character in decomposed if not unicodedata.combining(character))

    def set_expression(self, expression: FaceExpression) -> None:
        self.core.set_device_expression(expression, device_id="virtual-biony")
        self._notify()

    def play_animation(self, animation: str) -> None:
        self.core.play_device_animation(animation, device_id="virtual-biony")
        self.snapshot.animation = animation
        self._notify()

    def save_memory(self, content: str) -> None:
        self.core.save_memory(Memory(content=content))
        self.snapshot.response = "Memoria guardada."
        self._notify()

    def search_memory(self, query: str) -> list[Memory]:
        return self.core.memory_store.search(query)

    def confirm_pending_action(self, action_id: str, response: str) -> BrainResponse | None:
        result = self.core.confirm_pending_action(self.session_id, action_id, response)
        if result is not None:
            self.snapshot.response = result.message or ""
            self._notify()
        return result

    def _on_event(self, event: CoreEvent) -> None:
        self.snapshot.last_event = event.event_type
        self.snapshot.events.append(event.event_type)
        self.snapshot.events = self.snapshot.events[-20:]
        if event.event_type == "state_changed":
            self.snapshot.state = BionyState[str(event.data["state"])]
        if event.event_type == "confirmation_required":
            self.snapshot.pending_action_id = str(event.data["action_id"])
        if event.event_type in {"confirmation_accepted", "confirmation_rejected"}:
            self.snapshot.pending_action_id = None
        self._notify()

    def _on_device_command(self, command: DeviceCommand) -> None:
        if command.command_type == "play_animation":
            self.snapshot.animation = str(command.arguments["animation"])
            self.snapshot.animation_revision += 1

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener(self.snapshot)


def create_brain(mode: str) -> object:
    """Cria o brain selecionado; OpenAI continua opt-in e usa o ambiente."""
    if mode == "openai":
        return OpenAIBrain()
    if mode == "openrouter":
        return OpenRouterBrain()
    return SimulatedBrain()


def brain_mode_from_environment() -> str:
    return os.environ.get("BIONY_BRAIN", "simulated").casefold()