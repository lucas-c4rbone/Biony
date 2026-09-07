"""Serviço de aplicação para orquestrar conversas do Biony Core."""

from __future__ import annotations

from core.brain import Brain
from core.models import BrainResponse, ConversationRequest


class ConversationService:
    """Encaminha pedidos de conversa para uma implementação de Brain."""

    def __init__(self, brain: Brain) -> None:
        self._brain = brain

    def respond(self, request: ConversationRequest) -> BrainResponse:
        """Produz uma resposta para a mensagem recebida."""
        return BrainResponse(message=self._brain.respond(request.message))