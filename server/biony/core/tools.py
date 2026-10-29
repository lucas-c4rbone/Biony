"""Contrato e registro das ferramentas que o LLM pode chamar."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ToolDefinition:
    """O que o LLM enxerga de uma ferramenta.

    `parameters` é um JSON Schema (formato do tool calling OpenAI).
    """

    name: str
    description: str
    parameters: Mapping[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    requires_confirmation: bool = False


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    content: str


class Tool(ABC):
    """Uma ação explícita que o Biony sabe executar."""

    definition: ToolDefinition

    @abstractmethod
    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        """Executa a ação. Erros esperados viram ToolResult(ok=False)."""

    def describe(self, arguments: Mapping[str, Any]) -> str:
        """Frase curta usada ao pedir confirmação ("desligar o PC")."""
        if not arguments:
            return self.definition.name
        args = ", ".join(f"{key}={value}" for key, value in arguments.items())
        return f"{self.definition.name} ({args})"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        name = tool.definition.name
        if name in self._tools:
            raise ValueError(f"Ferramenta '{name}' já registrada.")
        self._tools[name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def definitions(self) -> list[ToolDefinition]:
        return [tool.definition for tool in self._tools.values()]
