"""Contratos que os adaptadores (LLM, banco, ...) precisam cumprir."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence

from biony.core.memory import Memory
from biony.core.models import ChatMessage, LLMReply
from biony.core.reminders import Due, Reminder, Task
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


class NotificationError(RuntimeError):
    """A notificação não chegou (sem internet, token errado...)."""


class Notifier(Protocol):
    async def send(self, text: str) -> None:
        """Manda uma notificação para o Lucas."""


class Scheduler(Protocol):
    def schedule(self, reminder_id: int, at: datetime) -> None:
        """Agenda o disparo do lembrete (substitui um agendamento anterior do mesmo id)."""

    def cancel(self, reminder_id: int) -> None:
        """Remove o agendamento, se existir."""


class ReminderStore(Protocol):
    def add_task(self, title: str, due: Due | None, notes: str = "") -> Task: ...
    def get_task(self, task_id: int) -> Task | None: ...
    def open_tasks(self) -> list[Task]: ...
    def complete_task(self, task_id: int) -> bool: ...
    def delete_task(self, task_id: int) -> bool: ...

    def add_reminder(self, fire_at: datetime, task_id: int | None = None, text: str | None = None) -> Reminder: ...
    def get_reminder(self, reminder_id: int) -> Reminder | None: ...
    def pending_reminders(self, task_id: int | None = None) -> list[Reminder]:
        """Lembretes ainda não enviados nem cancelados (todos, ou só os de uma tarefa)."""
    def mark_sent(self, reminder_id: int) -> None: ...
    def record_failure(self, reminder_id: int) -> int:
        """Conta uma tentativa de envio que falhou; devolve o total de tentativas."""
    def cancel_reminder(self, reminder_id: int) -> bool: ...
    def cancel_task_reminders(self, task_id: int) -> int: ...


class MemoryStore(Protocol):
    def add(self, content: str) -> Memory: ...
    def all(self) -> list[Memory]: ...
    def remove(self, memory_id: int) -> bool: ...
