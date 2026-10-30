"""Interpreta a resposta do usuário a um pedido de confirmação."""

from __future__ import annotations

from enum import Enum, auto
import re
import unicodedata


class Answer(Enum):
    YES = auto()
    NO = auto()
    UNCLEAR = auto()


_YES = {"sim", "pode", "confirmo", "confirma", "manda", "vai", "afirmativo", "isso", "claro", "yes", "ok", "okay", "beleza", "bora", "fechado"}
# Palavras que podem acompanhar um "sim"/"esquece" sem virar um pedido novo ("manda ver", "isso mesmo").
_FILLER = {"ver", "mesmo", "la", "por", "favor", "pf", "pfv", "ai", "entao", "pode", "isso", "biony", "e", "ta", "tudo", "certo"}
# Recusas que valem em qualquer frase: errar para o lado do "não" é seguro.
_NO = {"nao", "negativo", "cancela", "cancelar", "no"}
# "Esquece" também começa pedidos ("esquece que eu moro em X"); só é recusa sozinho.
_NO_ALONE = {"esquece"}
_NO_PHRASES = ("deixa pra la", "deixa para la")


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def interpret(text: str) -> Answer:
    """Interpreta a resposta a "Confirma?". "Não" sempre vence; na dúvida, UNCLEAR.

    O "sim" é rígido de propósito: "pode me dizer as horas?" ou "pode ligar a luz" são pedidos
    novos e não podem confirmar a ação pendente. Vale só uma resposta feita apenas de palavras de
    confirmação ("pode sim", "manda ver") ou que começa com "sim".
    """
    normalized = normalize(text)
    words = re.findall(r"[a-z]+", normalized)
    vocabulary = set(words)
    if vocabulary & _NO or any(phrase in normalized for phrase in _NO_PHRASES):
        return Answer.NO
    if vocabulary & _NO_ALONE and vocabulary <= _NO_ALONE | _FILLER:
        return Answer.NO
    if (vocabulary & _YES and vocabulary <= _YES | _FILLER) or (words and words[0] == "sim"):
        return Answer.YES
    return Answer.UNCLEAR
