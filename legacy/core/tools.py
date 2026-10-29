"""Contratos e catálogo de ferramentas permitidas do Biony Core."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

from core.models import DeviceKind, ToolRequest, ToolResult


class ToolRisk(Enum):
    """Níveis gerais de risco declarados por uma ferramenta."""

    LOW = auto()
    HIGH = auto()


@dataclass(frozen=True)
class ToolDefinition:
    """Metadados declarados por uma ferramenta disponível no Core."""

    name: str
    description: str
    expected_arguments: tuple[str, ...] = ()
    risk: ToolRisk = ToolRisk.LOW
    requires_confirmation: bool = False
    target: DeviceKind | None = None


class Tool(Protocol):
    """Contrato para uma ferramenta explícita e registrada."""

    @property
    def definition(self) -> ToolDefinition:
        """Descreve a ferramenta e seus limites."""

    def execute(self, request: ToolRequest) -> ToolResult:
        """Executa uma solicitação recebida pelo Core."""


class ToolCatalog:
    """Mantém as ferramentas que podem ser encontradas pelo Core."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Registra ou substitui uma ferramenta pelo seu nome declarado."""
        self._tools[tool.definition.name] = tool

    def find(self, name: str) -> Tool | None:
        """Encontra uma ferramenta registrada pelo nome."""
        return self._tools.get(name)

    def list_definitions(self) -> list[ToolDefinition]:
        """Lista as descrições das ferramentas registradas."""
        return [tool.definition for tool in self._tools.values()]