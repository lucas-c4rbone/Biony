"""Mecanismo interno de publicação de eventos do Biony Core."""

from __future__ import annotations

from typing import Callable, Protocol

from core.models import CoreEvent


EventListener = Callable[[CoreEvent], None]


class EventPublisher(Protocol):
    """Contrato para mecanismos substituíveis de publicação de eventos."""

    def subscribe(self, listener: EventListener) -> None:
        """Registra um listener para receber eventos futuros."""

    def unsubscribe(self, listener: EventListener) -> None:
        """Remove um listener registrado."""

    def publish(self, event: CoreEvent) -> None:
        """Entrega um evento aos listeners registrados."""


class EventDispatcher:
    """Publica eventos para listeners registrados nesta instância."""

    def __init__(self) -> None:
        self._listeners: list[EventListener] = []

    def subscribe(self, listener: EventListener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: EventListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def publish(self, event: CoreEvent) -> None:
        for listener in tuple(self._listeners):
            listener(event)