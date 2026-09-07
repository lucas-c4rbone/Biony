"""Serviço de aplicação para orquestrar conversas do Biony Core."""

from __future__ import annotations

from core.brain import Brain, MemoryAwareBrain, ToolAwareBrain
from core.models import BrainResponse, ConversationRequest, Memory, ToolResult


class ConversationService:
    """Encaminha pedidos de conversa para uma implementação de Brain."""

    def __init__(self, brain: Brain) -> None:
        self._brain = brain

    @property
    def supports_memory(self) -> bool:
        """Indica se o Brain configurado pode receber memórias do Core."""
        return isinstance(self._brain, MemoryAwareBrain)

    def respond(
        self, request: ConversationRequest, memories: tuple[Memory, ...] = ()
    ) -> BrainResponse:
        """Produz uma resposta para a mensagem recebida."""
        if isinstance(self._brain, MemoryAwareBrain):
            return self._brain.respond_with_memory(request.message, memories)
        if isinstance(self._brain, ToolAwareBrain):
            return self._brain.respond_with_tools(request.message)
        return BrainResponse(message=self._brain.respond(request.message))

    def respond_to_tool_result(self, result: ToolResult) -> BrainResponse:
        """Entrega ao Brain o resultado de uma ferramenta solicitada."""
        if not isinstance(self._brain, ToolAwareBrain):
            raise TypeError("The configured Brain does not support tool results.")
        return self._brain.respond_to_tool_result(result)

    def respond_to_memory_result(self, memories: tuple[Memory, ...]) -> BrainResponse:
        """Entrega ao Brain as memórias retornadas por uma busca solicitada."""
        if not isinstance(self._brain, MemoryAwareBrain):
            raise TypeError("The configured Brain does not support memory results.")
        return self._brain.respond_to_memory_result(memories)