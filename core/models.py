"""Modelos de dados compartilhados pelo Biony Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Mapping


class DeviceKind(Enum):
    """Categorias de clientes e dispositivos previstas para o Core."""

    BIONY = auto()
    MOBILE_APP = auto()
    PC = auto()
    PRINTER = auto()


@dataclass
class ConversationRequest:
    """Mensagem enviada por um cliente ao fluxo de conversa."""

    message: str


@dataclass(frozen=True)
class MemoryRequest:
    """Pedido do Brain para consultar memórias por texto."""

    query: str


@dataclass
class ToolRequest:
    """Pedido para executar uma ferramenta registrada no Core."""

    name: str
    arguments: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PendingAction:
    """Solicitação de ferramenta que aguarda confirmação explícita."""

    identifier: str
    session_id: str
    tool_name: str
    arguments: Mapping[str, object]


@dataclass
class BrainResponse:
    """Resposta textual e eventuais pedidos de ferramenta do Brain."""

    message: str | None = None
    tool_requests: tuple[ToolRequest, ...] = ()
    memory_request: MemoryRequest | None = None


@dataclass
class ToolResult:
    """Resultado devolvido após uma tentativa de executar uma ferramenta."""

    tool_name: str
    success: bool
    value: object | None = None


@dataclass
class Memory:
    """Conteúdo de uma memória explicitamente autorizada pelo usuário."""

    content: str


@dataclass
class Device:
    """Cliente ou dispositivo conhecido pelo Core."""

    identifier: str
    kind: DeviceKind
    is_available: bool = False
    capabilities: frozenset[str] = field(default_factory=frozenset)


@dataclass
class CoreEvent:
    """Evento publicado pelo Core para seus clientes e adaptadores."""

    event_type: str
    data: Mapping[str, object] = field(default_factory=dict)