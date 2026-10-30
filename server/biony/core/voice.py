"""Conversa por voz: áudio → transcrição → mesma conversa do texto → fala."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from biony.core.conversation import ConversationEngine
from biony.core.models import Channel, Reply
from biony.core.ports import SpeechToText, TextToSpeech

NOTHING_HEARD = "Não consegui ouvir nada. Pode repetir?"


@dataclass(frozen=True)
class VoiceReply:
    transcript: str
    reply: Reply
    audio: bytes | None


class VoiceAssistant:
    def __init__(self, engine: ConversationEngine, stt: SpeechToText, tts: TextToSpeech) -> None:
        self._engine = engine
        self._stt = stt
        self._tts = tts

    async def handle(self, audio: bytes, session_id: str | None = None, with_audio: bool = True) -> VoiceReply:
        transcript = await self._stt.transcribe(audio)
        if transcript:
            reply = await self._engine.handle(transcript, session_id, Channel.VOICE)
        else:
            # Silêncio ou ruído: não vale gastar uma chamada ao LLM nem sujar o histórico.
            reply = Reply(session_id or uuid4().hex, NOTHING_HEARD)
        speech = await self._tts.synthesize(reply.text) if with_audio else None
        return VoiceReply(transcript, reply, speech)


class VoiceSlot:
    """Lugar do VoiceAssistant, que pode levar minutos para carregar (download dos modelos).

    Enquanto carrega, o resto do Biony (texto, casa) já funciona.
    """

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.assistant: VoiceAssistant | None = None
        self.error: str | None = None

    @property
    def status(self) -> str:
        if not self.enabled:
            return "desativada"
        if self.assistant is not None:
            return "pronta"
        if self.error is not None:
            return f"erro: {self.error}"
        return "carregando"
