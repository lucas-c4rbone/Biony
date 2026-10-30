"""Transcrição local com faster-whisper (CPU, int8)."""

from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
import time

from biony.core.ports import AudioError

log = logging.getLogger(__name__)

# Palavras que o Whisper costuma errar; ajudam a acertar a grafia.
DEFAULT_VOCABULARY = "Biony, Lucas, ar-condicionado, fita LED, setup, PC, quarto, modo dormir, Moonlight."


class WhisperSTT:
    def __init__(
        self,
        *,
        model: str,
        models_dir: Path,
        beam_size: int = 1,
        language: str = "pt",
        vocabulary: str = DEFAULT_VOCABULARY,
    ) -> None:
        from faster_whisper import WhisperModel

        started = time.perf_counter()
        log.info("Carregando Whisper '%s' (na primeira vez ele é baixado para %s)...", model, models_dir)
        self._model = WhisperModel(model, device="cpu", compute_type="int8", download_root=str(models_dir))
        log.info("Whisper pronto em %.1f s.", time.perf_counter() - started)
        self._beam_size = beam_size
        self._language = language
        self._vocabulary = vocabulary
        # Uma transcrição por vez: em paralelo, as duas ficariam lentas e a RAM aperta.
        self._lock = asyncio.Lock()

    async def transcribe(self, audio: bytes) -> str:
        async with self._lock:
            return await asyncio.to_thread(self._transcribe, audio)

    def _transcribe(self, audio: bytes) -> str:
        started = time.perf_counter()
        try:
            segments, _ = self._model.transcribe(
                io.BytesIO(audio),
                language=self._language,
                beam_size=self._beam_size,
                vad_filter=True,
                initial_prompt=self._vocabulary,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as error:
            # O PyAV levanta tipos variados para arquivo corrompido ou formato desconhecido.
            if error.__class__.__module__.startswith("av"):
                raise AudioError(f"não consegui ler o áudio: {error}") from error
            raise
        log.info("STT %.2f s: %r", time.perf_counter() - started, text)
        return text
