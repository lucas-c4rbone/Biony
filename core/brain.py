"""Contrato do cérebro conversacional do Biony."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.models import BrainResponse, Memory, MemoryRequest, ToolResult


class Brain(Protocol):
    """Componente capaz de transformar uma mensagem em uma resposta textual."""

    def respond(self, message: str) -> str:
        """Retorna a resposta a uma mensagem do usuário."""


@runtime_checkable
class ToolAwareBrain(Brain, Protocol):
    """Extensão opcional para brains que podem solicitar ferramentas."""

    def respond_with_tools(self, message: str) -> BrainResponse:
        """Retorna uma resposta textual ou uma solicitação de ferramenta."""

    def respond_to_tool_result(self, result: ToolResult) -> BrainResponse:
        """Produz a resposta final após receber o resultado de uma ferramenta."""


@runtime_checkable
class MemoryAwareBrain(Brain, Protocol):
    """Extensão opcional para brains que podem receber e consultar memórias."""

    def respond_with_memory(self, message: str, memories: tuple[Memory, ...]) -> BrainResponse:
        """Produz uma resposta usando memórias relevantes fornecidas pelo Core."""

    def respond_to_memory_result(self, memories: tuple[Memory, ...]) -> BrainResponse:
        """Produz uma resposta após receber o resultado de uma busca de memória."""

@runtime_checkable
class ContextAwareBrain(Brain, Protocol):
    """Extensão opcional para brains que recebem memória e ferramentas juntas."""

    def respond_with_context(
        self, message: str, memories: tuple[Memory, ...], tools: tuple[object, ...]
    ) -> BrainResponse:
        """Produz uma resposta com o contexto disponibilizado pelo Core."""

@runtime_checkable
class MemoryResultAwareBrain(MemoryAwareBrain, Protocol):
    """Extensão que mantém a identidade de uma busca de memória solicitada."""

    def respond_to_identified_memory_result(
        self, request: MemoryRequest, memories: tuple[Memory, ...]
    ) -> BrainResponse:
        """Produz uma resposta após receber o resultado de uma busca identificada."""
