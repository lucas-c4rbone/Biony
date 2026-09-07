"""Contrato do cérebro conversacional do Biony."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.models import BrainResponse, Memory, ToolResult


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
