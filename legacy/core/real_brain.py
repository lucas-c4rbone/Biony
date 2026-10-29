"""Cérebro real que usa a API do OpenRouter para respostas, mas mantém a interface do SimulatedBrain."""

from __future__ import annotations

from datetime import datetime
import unicodedata

from core.openrouter_brain import OpenRouterBrain


class RealBrain:
    """Responde usando a API do OpenRouter, mantendo a interface do SimulatedBrain."""
    
    def __init__(self) -> None:
        self._brain = OpenRouterBrain()
    
    def respond(self, message: str) -> str:
        """Envia a mensagem para o OpenRouter e retorna a resposta."""
        try:
            return self._brain.respond(message)
        except Exception as e:
            # Em caso de erro na API, retorna uma mensagem amigável
            return f"Desculpe, tive um problema ao processar sua mensagem: {str(e)}"

    @staticmethod
    def _normalize(message: str) -> str:
        decomposed = unicodedata.normalize("NFKD", message.casefold())
        return "".join(character for character in decomposed if not unicodedata.combining(character))

    @staticmethod
    def _contains_greeting(message: str) -> bool:
        words = set(message.replace("?", " ").replace("!", " ").replace(",", " ").split())
        return bool(words & {"oi", "ola"})