"""Contrato do cérebro conversacional do Biony."""

from __future__ import annotations

from typing import Protocol


class Brain(Protocol):
    """Componente capaz de transformar uma mensagem em uma resposta textual."""

    def respond(self, message: str) -> str:
        """Retorna a resposta a uma mensagem do usuário."""
