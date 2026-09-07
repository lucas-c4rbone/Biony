"""Cérebro local temporário para testar o fluxo de conversa do Biony."""

from __future__ import annotations

from datetime import datetime
import unicodedata


class SimulatedBrain:
    """Responde a poucos padrões sem usar serviços externos ou IA."""

    def respond(self, message: str) -> str:
        normalized = self._normalize(message)

        if self._contains_greeting(normalized):
            return "Opa, Lucas! Que bom falar com você."
        if "qual seu nome" in normalized or "como voce se chama" in normalized:
            return "Eu sou o Biony, seu companheiro de mesa."
        if "que horas sao" in normalized or "qual a hora" in normalized:
            return f"Agora são {datetime.now():%H:%M}."
        return "Meu cérebro real ainda será conectado, mas já estou pronto para conversar com você."

    @staticmethod
    def _normalize(message: str) -> str:
        decomposed = unicodedata.normalize("NFKD", message.casefold())
        return "".join(character for character in decomposed if not unicodedata.combining(character))

    @staticmethod
    def _contains_greeting(message: str) -> bool:
        words = set(message.replace("?", " ").replace("!", " ").replace(",", " ").split())
        return bool(words & {"oi", "ola"})
