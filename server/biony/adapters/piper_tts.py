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


def gate_noise(pcm: bytes, rate: int, threshold_db: float = -42.0) -> bytes:
    """Silencia os trechos sem fala (o chiado de fundo de algumas vozes, como a jeff)."""
    import numpy as np

    x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    frame = int(rate * 0.02)
    frames = len(x) // frame
    if frames == 0:
        return pcm
    blocks = x[: frames * frame].reshape(frames, frame)
    loud = 20 * np.log10(np.sqrt(np.mean(blocks**2, axis=1)) + 1e-9) > threshold_db
    gain = np.convolve(loud.astype(np.float32), np.ones(5) / 5, "same")  # abre/fecha sem estalo
    envelope = np.pad(np.repeat(gain, frame), (0, len(x) - frames * frame), mode="edge")
    return (x * envelope * 32767).astype(np.int16).tobytes()


class PiperTTS:
    def __init__(self, *, voice: str, voices_dir: Path, reduce_noise: bool = False) -> None:
        from piper import PiperVoice, SynthesisConfig
        from piper.download_voices import download_voice

        model = voices_dir / f"{voice}.onnx"
        if not model.exists():
            log.info("Baixando a voz %s para %s...", voice, voices_dir)
            voices_dir.mkdir(parents=True, exist_ok=True)
            download_voice(voice, voices_dir)
        self._voice = PiperVoice.load(model)
        self._reduce_noise = reduce_noise
        # Menos variação aleatória na síntese também diminui o chiado.
        self._config = SynthesisConfig(noise_scale=0.4, noise_w_scale=0.6) if reduce_noise else None
        self._lock = asyncio.Lock()
        log.info("Voz %s pronta.", voice)

    async def synthesize(self, text: str) -> bytes:
        async with self._lock:
            return await asyncio.to_thread(self._synthesize, text)

    def _synthesize(self, text: str) -> bytes:
        started = time.perf_counter()
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            self._voice.synthesize_wav(speakable(text) or "...", wav, syn_config=self._config)
        if self._reduce_noise:
            buffer.seek(0)
            with wave.open(buffer) as wav:
                rate, pcm = wav.getframerate(), wav.readframes(wav.getnframes())
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(rate)
                wav.writeframes(gate_noise(pcm, rate))
        log.info("TTS %.2f s para %d caracteres.", time.perf_counter() - started, len(text))
        return buffer.getvalue()
