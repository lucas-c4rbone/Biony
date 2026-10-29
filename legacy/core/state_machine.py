"""Estados e transições do Biony sem dependências de interface gráfica."""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable


class BionyState(Enum):
    """Estados visuais e comportamentais disponíveis no protótipo."""

    BOOTING = auto()
    SLEEPING = auto()
    IDLE = auto()
    WAKING = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()


StateListener = Callable[[BionyState], None]


class StateMachine:
    """Mantém um único estado atual e comunica mudanças aos interessados."""

    def __init__(self, initial_state: BionyState = BionyState.IDLE) -> None:
        self._state = initial_state
        self._listeners: list[StateListener] = []

    @property
    def state(self) -> BionyState:
        return self._state

    def subscribe(self, listener: StateListener) -> None:
        self._listeners.append(listener)
        listener(self._state)

    def transition_to(self, state: BionyState) -> bool:
        """Troca de estado e retorna se houve uma mudança efetiva."""
        if state is self._state:
            return False

        self._state = state
        for listener in tuple(self._listeners):
            listener(state)
        return True
