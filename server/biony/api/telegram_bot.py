"""Conversa pelo Telegram: texto e mensagens de voz viram pedidos ao Biony.

Só o chat do Lucas (TELEGRAM_CHAT_ID) é atendido. Enquanto ele não estiver configurado,
o bot responde a quem escrever com o próprio chat id, para facilitar a configuração.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from biony.core.conversation import ConversationEngine
from biony.core.models import Channel
from biony.core.ports import AudioError, LLMError
from biony.core.voice import VoiceSlot

log = logging.getLogger(__name__)

RETRY_DELAY = 5.0


class TelegramApi(Protocol):
    async def send_message(self, chat_id: int, text: str) -> None: ...
    async def send_typing(self, chat_id: int) -> None: ...
    async def get_updates(self, offset: int | None, timeout: int = 50) -> list[dict[str, Any]]: ...
    async def download_file(self, file_id: str) -> bytes: ...


class TelegramBot:
    def __init__(
        self, api: TelegramApi, engine: ConversationEngine, voice: VoiceSlot, allowed_chat_id: int | None
    ) -> None:
        self._api = api
        self._engine = engine
        self._voice = voice
        self._allowed = allowed_chat_id
        self._offset: int | None = None

    async def run(self) -> None:
        """Long polling até ser cancelado. Erros de rede não derrubam o loop."""
        log.info("Bot do Telegram ouvindo%s.", "" if self._allowed else " (sem TELEGRAM_CHAT_ID: modo de configuração)")
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Falha no polling do Telegram; tentando de novo em %.0f s.", RETRY_DELAY)
                await asyncio.sleep(RETRY_DELAY)

    async def poll_once(self, timeout: int = 50) -> None:
        for update in await self._api.get_updates(self._offset, timeout):
            self._offset = update["update_id"] + 1
            message = update.get("message")
            if message:
                await self._handle(message)

    async def _handle(self, message: dict[str, Any]) -> None:
        chat_id = message["chat"]["id"]
        if self._allowed is None:
            log.warning("Mensagem do chat %s; configure TELEGRAM_CHAT_ID=%s se for você.", chat_id, chat_id)
            await self._api.send_message(
                chat_id, f"Oi! Este Biony ainda não sabe quem é o dono.\nSeu chat id é {chat_id}: coloque TELEGRAM_CHAT_ID={chat_id} no .env do servidor."
            )
            return
        if chat_id != self._allowed:
            log.warning("Mensagem ignorada de um chat não autorizado (%s).", chat_id)
            return

        session = f"telegram-{chat_id}"
        try:
            await self._api.send_typing(chat_id)
            if "voice" in message or "audio" in message:
                text = await self._handle_audio(message, session)
            elif message.get("text"):
                text = (await self._engine.handle(message["text"], session)).text
            else:
                text = "Por enquanto eu só entendo texto e áudio."
        except LLMError as error:
            log.error("LLM falhou numa mensagem do Telegram: %s", error)
            text = f"Deu erro falando com o meu cérebro (LLM): {error}"
        await self._api.send_message(chat_id, text)

    async def _handle_audio(self, message: dict[str, Any], session: str) -> str:
        assistant = self._voice.assistant
        if assistant is None:
            return f"Não consigo ouvir áudio agora (voz {self._voice.status})."
        file_id = (message.get("voice") or message.get("audio"))["file_id"]
        audio = await self._api.download_file(file_id)
        try:
            result = await assistant.handle(audio, session, with_audio=False, reply_channel=Channel.TEXT)
        except AudioError as error:
            return f"Não consegui ler esse áudio: {error}"
        if not result.transcript:
            return result.reply.text
        return f"🎙️ “{result.transcript}”\n\n{result.reply.text}"
