"""Contrato e registro das ferramentas que o LLM pode chamar."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Mapping

# O que o cliente da conversa atual sabe fazer (ex.: "acoes_celular"). O motor define a cada mensagem;
# ferramentas que dependem do cliente consultam aqui antes de aceitar o pedido.
client_capabilities: ContextVar[frozenset[str]] = ContextVar("client_capabilities", default=frozenset())


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
    # Ações que o CLIENTE executa depois da resposta (ex.: despertador no celular). O servidor só as repassa.
    client_actions: tuple[Mapping[str, Any], ...] = ()


class Tool(ABC):
    """Uma ação explícita que o Biony sabe executar."""

    definition: ToolDefinition

    @abstractmethod
    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        """Executa a ação. Erros esperados viram ToolResult(ok=False)."""

    def needs_confirmation(self, arguments: Mapping[str, Any]) -> bool:
        """Se ESTE pedido precisa de "sim" (ex.: só o "desligar" de um aparelho perigoso)."""
        return self.definition.requires_confirmation

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
