"""Transcrição na nuvem pela Groq (Whisper large-v3-turbo, API no formato OpenAI)."""

from __future__ import annotations

import logging
import time

import httpx

from biony.adapters.whisper_stt import DEFAULT_VOCABULARY
from biony.core.ports import AudioError

log = logging.getLogger(__name__)


class SttUnavailable(RuntimeError):
    """O serviço de transcrição não respondeu (rede, limite, chave): vale tentar outro."""


def guess_filename(audio: bytes) -> str:
    """A Groq decide o formato pela extensão do arquivo."""
    if audio[:4] == b"RIFF":
        return "fala.wav"
    if audio[:4] == b"OggS":
        return "fala.ogg"
    if audio[:4] == b"\x1aE\xdf\xa3":
        return "fala.webm"
    if audio[4:8] == b"ftyp":
        return "fala.m4a"
    if audio[:3] == b"ID3" or audio[:2] in (b"\xff\xfb", b"\xff\xf3"):
        return "fala.mp3"
    return "fala.wav"


class GroqSTT:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "whisper-large-v3-turbo",
        language: str = "pt",
        vocabulary: str = DEFAULT_VOCABULARY,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._language = language
        self._vocabulary = vocabulary
        self._http = httpx.AsyncClient(
            base_url="https://api.groq.com/openai/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def transcribe(self, audio: bytes) -> str:
        started = time.perf_counter()
        try:
            response = await self._http.post(
                "/audio/transcriptions",
                files={"file": (guess_filename(audio), audio)},
                data={
                    "model": self._model,
                    "language": self._language,
                    "prompt": self._vocabulary,
                    "response_format": "json",
                    "temperature": "0",
                },
            )
        except httpx.HTTPError as error:
            raise SttUnavailable(f"Groq sem resposta ({error.__class__.__name__})") from error
        if response.status_code == 400:
            raise AudioError(f"a Groq não conseguiu ler o áudio: {response.text[:200]}")
        if response.status_code != 200:
            raise SttUnavailable(f"Groq respondeu HTTP {response.status_code}: {response.text[:200]}")
        try:
            text = str(response.json()["text"]).strip()
        except (ValueError, KeyError, TypeError) as error:
            raise SttUnavailable(f"resposta inesperada da Groq: {response.text[:200]}") from error
        log.info("STT groq %.2f s: %r", time.perf_counter() - started, text)
        return text
