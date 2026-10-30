"""Contratos que os adaptadores (LLM, banco, ...) precisam cumprir."""

from __future__ import annotations

from typing import Protocol, Sequence

from biony.core.models import ChatMessage, LLMReply
from biony.core.tools import ToolDefinition


class LLMError(RuntimeError):
    """Falha ao falar com o LLM (rede, autenticação, resposta inválida)."""


class AudioError(ValueError):
    """Áudio que não dá para decodificar."""


class LLMClient(Protocol):
    async def chat(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolDefinition]
    ) -> LLMReply:
        """Envia a conversa e as ferramentas disponíveis; devolve a próxima resposta."""


class ConversationStore(Protocol):
    def append(self, session_id: str, message: ChatMessage) -> None:
        """Acrescenta uma mensagem ao histórico da sessão."""

    def recent(self, session_id: str, limit: int) -> list[ChatMessage]:
        """Últimas `limit` mensagens da sessão, da mais antiga para a mais nova."""


class SpeechToText(Protocol):
    async def transcribe(self, audio: bytes) -> str:
        """Transcreve um arquivo de áudio (WAV, WebM, OGG...). Silêncio vira ""."""


class TextToSpeech(Protocol):
    async def synthesize(self, text: str) -> bytes:
        """Gera a fala do texto como um arquivo WAV."""
