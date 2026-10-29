"""Adapters para Wake Word (openWakeWord), STT (OpenAI) e TTS (OpenAI)."""

from __future__ import annotations

import io
import os
import struct
from typing import Mapping
import wave
from uuid import uuid4

from core.audio import (
    AudioChunk,
    AudioError,
    SpeechAudio,
    SpeechToText,
    TextToSpeech,
    TranscriptionResult,
    WakeWordDetector,
)


class OpenWakeWordDetector(WakeWordDetector):
    """Adapter para detecção local de palavra de ativação usando openWakeWord."""

    def __init__(
        self,
        model_path: str | None = None,
        threshold: float | None = None,
        model_instance: object | None = None,
        inference_framework: str = "onnx",
    ) -> None:
        self._model_path = model_path or os.environ.get("OPENWAKEWORD_MODEL_PATH")
        env_threshold = os.environ.get("OPENWAKEWORD_THRESHOLD")
        if threshold is not None:
            self.threshold = float(threshold)
        elif env_threshold is not None:
            try:
                self.threshold = float(env_threshold)
            except ValueError as err:
                raise ValueError("OPENWAKEWORD_THRESHOLD must be numeric.") from err
        else:
            self.threshold = 0.5

        self._inference_framework = inference_framework
        self._model = model_instance
        self._is_closed = False

        if self._model is None and not self._model_path:
            raise AudioError("OPENWAKEWORD_MODEL_PATH is not configured.")

    def detect(self, chunk: AudioChunk) -> bool:
        if self._is_closed:
            raise AudioError("OpenWakeWordDetector has been closed.")

        if not chunk.data:
            return False

        model = self._get_or_create_model()

        try:
            pcm_data = self._chunk_to_pcm(chunk)
            predictions = model.predict(pcm_data)
            return self._evaluate_predictions(predictions)
        except AudioError:
            raise
        except Exception as err:
            raise AudioError(f"openWakeWord detection failed: {err}") from err

    def _get_or_create_model(self) -> object:
        if self._model is not None:
            return self._model

        if not self._model_path:
            raise AudioError("OPENWAKEWORD_MODEL_PATH is not configured.")

        try:
            import openwakeword
        except ImportError as err:
            raise AudioError("The openwakeword package is not installed.") from err

        try:
            self._model = openwakeword.Model(
                wakeword_models=[self._model_path],
                inference_framework=self._inference_framework,
            )
        except Exception as err:
            raise AudioError(f"Failed to initialize openWakeWord model: {err}") from err

        return self._model

    def _chunk_to_pcm(self, chunk: AudioChunk) -> object:
        try:
            import numpy as np
            return np.frombuffer(chunk.data, dtype=np.int16)
        except ImportError:
            num_samples = len(chunk.data) // 2
            return struct.unpack(f"<{num_samples}h", chunk.data[: num_samples * 2])

    def _evaluate_predictions(self, predictions: object) -> bool:
        if isinstance(predictions, dict):
            return any(
                isinstance(val, (int, float)) and val >= self.threshold
                for val in predictions.values()
            )
        if isinstance(predictions, (list, tuple)):
            return any(
                isinstance(val, (int, float)) and val >= self.threshold
                for val in predictions
            )
        if isinstance(predictions, (int, float)):
            return predictions >= self.threshold
        return False

    def close(self) -> None:
        """Libera recursos do detector."""
        self._model = None
        self._is_closed = True

    def delete(self) -> None:
        """Alias para close()."""
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


class OpenAISpeechToText(SpeechToText):
    """Adapter para transcrição de áudio em texto (STT) usando OpenAI."""

    def __init__(
        self,
        client: object | None = None,
        *,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model or os.environ.get("OPENAI_STT_MODEL") or "gpt-4o-mini-transcribe"

        if self._client is None and not self._api_key:
            raise AudioError("OPENAI_API_KEY is not configured.")

    def transcribe(self, chunk: AudioChunk) -> TranscriptionResult:
        if not chunk.data:
            return TranscriptionResult(text="", confidence=1.0)

        client = self._get_or_create_client()

        wav_bytes = self._chunk_to_wav_bytes(chunk)
        file_payload = ("audio.wav", wav_bytes, "audio/wav")

        try:
            response = client.audio.transcriptions.create(
                model=self.model,
                file=file_payload,
            )
            text = getattr(response, "text", None)
            if text is None and isinstance(response, dict):
                text = response.get("text")
            if not isinstance(text, str):
                text = str(response) if response else ""
            return TranscriptionResult(text=text.strip(), confidence=1.0)
        except Exception as err:
            raise AudioError(f"OpenAI STT transcription failed: {err}") from err

    def _get_or_create_client(self) -> object:
        if self._client is not None:
            return self._client

        if not self._api_key:
            raise AudioError("OPENAI_API_KEY is not configured.")

        try:
            from openai import OpenAI
        except ImportError as err:
            raise AudioError("The openai package is not installed.") from err

        try:
            timeout = float(os.environ.get("OPENAI_TIMEOUT", "30.0"))
        except ValueError:
            timeout = 30.0

        self._client = OpenAI(api_key=self._api_key, timeout=timeout)
        return self._client

    @staticmethod
    def _chunk_to_wav_bytes(chunk: AudioChunk) -> bytes:
        buffer = io.BytesIO()
        try:
            with wave.open(buffer, "wb") as wav_file:
                wav_file.setnchannels(chunk.channels)
                wav_file.setsampwidth(2)
                wav_file.setframerate(chunk.sample_rate)
                wav_file.writeframes(chunk.data)
            return buffer.getvalue()
        except Exception as err:
            raise AudioError(f"Failed to encode audio chunk to WAV: {err}") from err


class OpenAITextToSpeech(TextToSpeech):
    """Adapter para síntese de fala (TTS) usando OpenAI."""

    def __init__(
        self,
        client: object | None = None,
        *,
        model: str | None = None,
        voice: str | None = None,
        response_format: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model or os.environ.get("OPENAI_TTS_MODEL") or "gpt-4o-mini-tts"
        self.voice = voice or os.environ.get("OPENAI_TTS_VOICE") or "alloy"
        self.response_format = response_format or os.environ.get("OPENAI_TTS_FORMAT") or "mp3"

        if self._client is None and not self._api_key:
            raise AudioError("OPENAI_API_KEY is not configured.")

    def synthesize(self, text: str) -> SpeechAudio:
        if not text or not text.strip():
            raise AudioError("Text for TTS synthesis cannot be empty.")

        client = self._get_or_create_client()

        try:
            response = client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=text,
                response_format=self.response_format,
            )
            audio_bytes = self._extract_audio_bytes(response)
            audio_id = f"speech_{uuid4().hex[:8]}"
            return SpeechAudio(audio_id=audio_id, data=audio_bytes, text=text)
        except Exception as err:
            raise AudioError(f"OpenAI TTS synthesis failed: {err}") from err

    def _get_or_create_client(self) -> object:
        if self._client is not None:
            return self._client

        if not self._api_key:
            raise AudioError("OPENAI_API_KEY is not configured.")

        try:
            from openai import OpenAI
        except ImportError as err:
            raise AudioError("The openai package is not installed.") from err

        try:
            timeout = float(os.environ.get("OPENAI_TIMEOUT", "30.0"))
        except ValueError:
            timeout = 30.0

        self._client = OpenAI(api_key=self._api_key, timeout=timeout)
        return self._client

    @staticmethod
    def _extract_audio_bytes(response: object) -> bytes:
        if hasattr(response, "content") and isinstance(response.content, bytes):
            return response.content
        if hasattr(response, "read") and callable(response.read):
            data = response.read()
            if isinstance(data, bytes):
                return data
        if isinstance(response, bytes):
            return response
        raise AudioError("Invalid response format received from OpenAI TTS.")
