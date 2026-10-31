"""Mensagens trocadas entre o Biony, o usuário, o LLM e as ferramentas."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class Channel(str, Enum):
    """Por onde a mensagem chegou; muda o estilo da resposta."""

    TEXT = "texto"
    VOICE = "voz"


class Emotion(str, Enum):
    """Como o rosto do Biony deve reagir à resposta (calculado pelo que aconteceu, não pelo LLM)."""

    NEUTRAL = "neutro"
    HAPPY = "feliz"  # alguma ação deu certo
    SAD = "triste"  # alguma ação falhou
    DOUBT = "duvida"  # esperando confirmação
    CONFUSED = "confuso"  # não ouviu / se perdeu


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class ToolCall:
    """Pedido do LLM para executar uma ferramenta."""

    id: str
    name: str
    arguments: dict[str, Any]
    # Preenchido quando o LLM mandou argumentos que não são um JSON válido.
    arguments_error: str | None = None


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    # Só para role=TOOL: a qual chamada este resultado responde.
    tool_call_id: str | None = None


@dataclass(frozen=True)
class LLMReply:
    """Resposta crua do LLM: texto, chamadas de ferramenta ou ambos."""

    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class Reply:
    """O que o Biony devolve para o cliente que mandou a mensagem."""

    session_id: str
    text: str
    awaiting_confirmation: bool = False
    emotion: Emotion = Emotion.NEUTRAL
    client_actions: tuple[Mapping[str, Any], ...] = ()


@dataclass
class PendingConfirmation:
    """Chamadas de ferramenta que esperam um "sim" do usuário."""

    session_id: str
    calls: list[ToolCall] = field(default_factory=list)
