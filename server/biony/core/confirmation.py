"""Interpreta a resposta do usuário a um pedido de confirmação."""

from __future__ import annotations

from enum import Enum, auto
import re
import unicodedata


class Answer(Enum):
    YES = auto()
    NO = auto()
    UNCLEAR = auto()


_YES = {"sim", "pode", "confirmo", "confirma", "manda", "vai", "afirmativo", "isso", "claro", "yes"}
_NO = {"nao", "negativo", "cancela", "cancelar", "esquece", "no"}
_NO_PHRASES = ("deixa pra la", "deixa para la")


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def interpret(text: str) -> Answer:
    """"Não" sempre vence: uma resposta com sim e não é tratada como recusa."""
    normalized = normalize(text)
    words = set(re.findall(r"[a-z]+", normalized))
    if words & _NO or any(phrase in normalized for phrase in _NO_PHRASES):
        return Answer.NO
    if words & _YES:
        return Answer.YES
    return Answer.UNCLEAR
