"""Síntese de voz local com Piper."""

from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
import re
import time
import wave

log = logging.getLogger(__name__)

_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")
_MARKDOWN = re.compile(r"[*_#`~>|]+")


def speakable(text: str) -> str:
    """Remove o que o sintetizador leria como lixo (emojis, markdown)."""
    text = _EMOJI.sub("", text)
    text = _MARKDOWN.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


class PiperTTS:
    def __init__(self, *, voice: str, voices_dir: Path) -> None:
        from piper import PiperVoice
        from piper.download_voices import download_voice

        model = voices_dir / f"{voice}.onnx"
        if not model.exists():
            log.info("Baixando a voz %s para %s...", voice, voices_dir)
            voices_dir.mkdir(parents=True, exist_ok=True)
            download_voice(voice, voices_dir)
        self._voice = PiperVoice.load(model)
        self._lock = asyncio.Lock()
        log.info("Voz %s pronta.", voice)

    async def synthesize(self, text: str) -> bytes:
        async with self._lock:
            return await asyncio.to_thread(self._synthesize, text)

    def _synthesize(self, text: str) -> bytes:
        started = time.perf_counter()
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            self._voice.synthesize_wav(speakable(text) or "...", wav)
        log.info("TTS %.2f s para %d caracteres.", time.perf_counter() - started, len(text))
        return buffer.getvalue()
