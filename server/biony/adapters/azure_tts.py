"""Síntese de voz na nuvem pelo Azure (vozes neurais). O Piper local fica de reserva."""

from __future__ import annotations

import logging
import time
from xml.sax.saxutils import escape, quoteattr

import httpx

from biony.adapters.piper_tts import speakable

log = logging.getLogger(__name__)

# Mesmo formato do Piper e do protocolo do totem: WAV 22050 Hz, mono, 16 bits.
OUTPUT_FORMAT = "riff-22050hz-16bit-mono-pcm"


class TtsUnavailable(RuntimeError):
    """O serviço de voz não respondeu (rede, limite, chave): vale usar a reserva."""


def build_ssml(text: str, voice: str, pitch: str = "0%", rate: str = "0%") -> str:
    language = "-".join(voice.split("-")[:2])  # "pt-BR-AntonioNeural" → "pt-BR"
    return (
        f"<speak version='1.0' xml:lang={quoteattr(language)}>"
        f"<voice name={quoteattr(voice)}>"
        f"<prosody pitch={quoteattr(pitch)} rate={quoteattr(rate)}>{escape(speakable(text) or '...')}</prosody>"
        "</voice></speak>"
    )


class AzureTTS:
    def __init__(
        self,
        *,
        key: str,
        region: str,
        voice: str,
        pitch: str = "0%",
        rate: str = "0%",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._voice = voice
        self._pitch = pitch
        self._rate = rate
        self._http = httpx.AsyncClient(
            base_url=f"https://{region.strip()}.tts.speech.microsoft.com",
            headers={
                "Ocp-Apim-Subscription-Key": key.strip(),
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
                "User-Agent": "biony",
            },
            timeout=10.0,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def synthesize(self, text: str) -> bytes:
        started = time.perf_counter()
        ssml = build_ssml(text, self._voice, self._pitch, self._rate)
        try:
            response = await self._http.post("/cognitiveservices/v1", content=ssml.encode("utf-8"))
        except httpx.HTTPError as error:
            raise TtsUnavailable(f"sem conexão com o Azure ({error.__class__.__name__})") from error
        if response.status_code in (401, 403):
            raise TtsUnavailable("chave do Azure inválida ou de outra região (AZURE_SPEECH_REGION)")
        if response.status_code == 429:
            raise TtsUnavailable("limite do Azure atingido")
        if response.status_code != 200 or response.content[:4] != b"RIFF":
            raise TtsUnavailable(f"Azure respondeu HTTP {response.status_code}: {response.text[:200]}")
        log.info("TTS Azure %.2f s para %d caracteres.", time.perf_counter() - started, len(text))
        return response.content
