"""WebSocket do totem (ESP32): áudio em tempo real nos dois sentidos.

O protocolo está em protocol/PROTOCOL.md (seção "Totem"). Resumo:
  totem → servidor: {"tipo":"ola","token":…}, {"tipo":"ouvir_inicio"}, áudio PCM16 16 kHz em
                    frames binários, {"tipo":"ouvir_fim"}, {"tipo":"texto",…}, {"tipo":"ping"}
  servidor → totem: {"tipo":"ola_ok"}, {"tipo":"estado"}, {"tipo":"transcricao"}, {"tipo":"resposta"},
                    {"tipo":"audio_inicio"}, frames binários PCM16, {"tipo":"audio_fim"}, {"tipo":"erro"}
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
from typing import Any
import wave

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from biony.api.auth import Auth
from biony.core.conversation import ConversationEngine
from biony.core.models import Channel, Emotion
from biony.core.ports import AudioError, LLMError
from biony.core.voice import VoiceSlot

log = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
MIC_RATE = 16_000  # o totem manda PCM 16 bits mono nessa taxa
MAX_UTTERANCE_SECONDS = 30
MAX_UTTERANCE_BYTES = MIC_RATE * 2 * MAX_UTTERANCE_SECONDS
MIN_UTTERANCE_BYTES = int(MIC_RATE * 2 * 0.25)  # menos que 0,25 s: toque sem fala
AUDIO_CHUNK = 4096  # bytes por frame de áudio enviado ao totem
HELLO_TIMEOUT = 10.0
CLOSE_BAD_HELLO = 4400
CLOSE_UNAUTHORIZED = 4401


def pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def wav_to_pcm(data: bytes) -> tuple[bytes, int]:
    """Tira o cabeçalho do WAV: o totem escreve o PCM direto no I2S."""
    with wave.open(io.BytesIO(data)) as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise AudioError("a fala precisa ser mono, 16 bits")
        return wav.readframes(wav.getnframes()), wav.getframerate()


def register_device_ws(app: FastAPI, engine: ConversationEngine, auth: Auth, voice: VoiceSlot) -> None:
    @app.websocket("/ws/dispositivo")
    async def device_socket(ws: WebSocket) -> None:
        await ws.accept()
        session = await _hello(ws, auth, voice)
        if session is not None:
            await DeviceConnection(ws, engine, voice, session).run()


async def _hello(ws: WebSocket, auth: Auth, voice: VoiceSlot) -> str | None:
    """A primeira mensagem autentica (o token não vai na URL, para não aparecer em logs)."""
    try:
        hello = json.loads(await asyncio.wait_for(ws.receive_text(), HELLO_TIMEOUT))
    except (asyncio.TimeoutError, ValueError, KeyError, WebSocketDisconnect):
        await _close(ws, CLOSE_BAD_HELLO, "A primeira mensagem precisa ser {\"tipo\": \"ola\", ...}.")
        return None
    if not isinstance(hello, dict) or hello.get("tipo") != "ola":
        await _close(ws, CLOSE_BAD_HELLO, "A primeira mensagem precisa ser {\"tipo\": \"ola\", ...}.")
        return None
    token = hello.get("token")
    if not isinstance(token, str) or not auth.check(token):
        log.warning("Totem recusado: token inválido.")
        await _close(ws, CLOSE_UNAUTHORIZED, "Token inválido.")
        return None
    name = re.sub(r"[^a-z0-9_-]", "", str(hello.get("dispositivo") or "totem").lower())[:40] or "totem"
    session = f"totem-{name}"
    await ws.send_json({
        "tipo": "ola_ok",
        "versao": PROTOCOL_VERSION,
        "sessao": session,
        "voz": voice.status,
        "microfone": {"formato": "pcm16", "taxa": MIC_RATE, "max_segundos": MAX_UTTERANCE_SECONDS},
    })
    log.info("Totem conectado: %s", session)
    return session


async def _close(ws: WebSocket, code: int, message: str) -> None:
    try:
        await ws.send_json({"tipo": "erro", "mensagem": message})
        await ws.close(code=code)
    except (WebSocketDisconnect, RuntimeError):
        pass


class DeviceConnection:
    def __init__(self, ws: WebSocket, engine: ConversationEngine, voice: VoiceSlot, session: str) -> None:
        self._ws = ws
        self._engine = engine
        self._voice = voice
        self._session = session
        self._recording: bytearray | None = None

    async def run(self) -> None:
        try:
            while True:
                message = await self._ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    await self._on_audio(message["bytes"])
                elif message.get("text") is not None:
                    await self._on_text(message["text"])
        except WebSocketDisconnect:
            pass
        log.info("Totem desconectado: %s", self._session)

    async def _on_audio(self, chunk: bytes) -> None:
        if self._recording is None:
            await self._error("Mande {\"tipo\": \"ouvir_inicio\"} antes do áudio.")
            return
        self._recording.extend(chunk)
        if len(self._recording) > MAX_UTTERANCE_BYTES:
            self._recording = None
            await self._error(f"Fala longa demais (máximo {MAX_UTTERANCE_SECONDS} s).")

    async def _on_text(self, raw: str) -> None:
        try:
            data: Any = json.loads(raw)
            kind = data["tipo"]
        except (ValueError, KeyError, TypeError):
            await self._error("Mensagem inválida: esperava JSON com \"tipo\".")
            return
        if kind == "ouvir_inicio":
            self._recording = bytearray()
        elif kind == "ouvir_fim":
            pcm, self._recording = bytes(self._recording or b""), None
            await self._answer_voice(pcm)
        elif kind == "cancelar":
            self._recording = None
        elif kind == "texto" and isinstance(data.get("texto"), str) and data["texto"].strip():
            await self._answer_text(data["texto"].strip())
        elif kind == "ping":
            await self._ws.send_json({"tipo": "pong"})
        else:
            await self._error(f"Tipo de mensagem desconhecido: {kind!r}.")

    async def _answer_voice(self, pcm: bytes) -> None:
        assistant = self._voice.assistant
        if assistant is None:
            await self._error(f"Voz {self._voice.status}.")
            return
        if len(pcm) < MIN_UTTERANCE_BYTES:
            await self._send_state("ocioso")
            return
        await self._send_state("pensando")
        try:
            result = await assistant.handle(pcm_to_wav(pcm, MIC_RATE), self._session, with_audio=True)
        except (AudioError, LLMError) as error:
            await self._error(str(error))
            return
        await self._ws.send_json({"tipo": "transcricao", "texto": result.transcript})
        await self._send_reply(
            result.reply.text, result.reply.emotion, result.reply.awaiting_confirmation, result.audio is not None
        )
        if result.audio is not None:
            await self._send_speech(result.audio)

    async def _answer_text(self, text: str) -> None:
        await self._send_state("pensando")
        try:
            reply = await self._engine.handle(text, self._session, Channel.VOICE)
        except LLMError as error:
            await self._error(str(error))
            return
        assistant = self._voice.assistant
        await self._send_reply(reply.text, reply.emotion, reply.awaiting_confirmation, assistant is not None)
        if assistant is not None:
            await self._send_speech(await assistant.speak(reply.text))

    async def _send_reply(self, text: str, emotion: Emotion, awaiting: bool, audio: bool) -> None:
        """`audio` avisa se vem fala em seguida (senão o totem não fica esperando)."""
        await self._ws.send_json({
            "tipo": "resposta",
            "texto": text,
            "emocao": emotion.value,
            "aguardando_confirmacao": awaiting,
            "audio": audio,
        })

    async def _send_speech(self, wav: bytes) -> None:
        pcm, rate = wav_to_pcm(wav)
        await self._ws.send_json({"tipo": "audio_inicio", "formato": "pcm16", "taxa": rate, "bytes": len(pcm)})
        for start in range(0, len(pcm), AUDIO_CHUNK):
            await self._ws.send_bytes(pcm[start : start + AUDIO_CHUNK])
        await self._ws.send_json({"tipo": "audio_fim"})

    async def _send_state(self, state: str) -> None:
        await self._ws.send_json({"tipo": "estado", "estado": state})

    async def _error(self, message: str) -> None:
        log.warning("Totem %s: %s", self._session, message)
        await self._ws.send_json({"tipo": "erro", "mensagem": message, "emocao": Emotion.SAD.value})
