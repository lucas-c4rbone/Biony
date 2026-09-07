"""Adapters para Wake Word (Porcupine), STT (OpenAI) e TTS (OpenAI)."""

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


class PorcupineWakeWordDetector(WakeWordDetector):
    """Adapter para detecção local de palavra de ativação usando Picovoice Porcupine."""

    def __init__(
        self,
        access_key: str | None = None,
        keyword_path: str | None = None,
        keyword_name: str | None = None,
        porcupine_instance: object | None = None,
        sensitivities: tuple[float, ...] = (0.5,),
    ) -> None:
        self._access_key = access_key or os.environ.get("PICOVOICE_ACCESS_KEY")
        self._keyword_path = keyword_path or os.environ.get("PICOVOICE_KEYWORD_PATH")
        self._keyword_name = keyword_name or os.environ.get("PICOVOICE_KEYWORD") or "biony"
        self._sensitivities = sensitivities
        self._porcupine = porcupine_instance
        self._is_deleted = False

        if self._porcupine is None and not self._access_key:
            raise AudioError("PICOVOICE_ACCESS_KEY is not configured.")

    def detect(self, chunk: AudioChunk) -> bool:
        if self._is_deleted:
            raise AudioError("PorcupineWakeWordDetector has been closed/deleted.")

        detector = self._get_or_create_detector()

        if not chunk.data:
            return False

        try:
            num_samples = len(chunk.data) // 2
            if num_samples == 0:
                return False
            pcm = struct.unpack(f"<{num_samples}h", chunk.data[: num_samples * 2])
        except Exception as err:
            raise AudioError(f"Failed to parse audio chunk PCM data: {err}") from err

        frame_length = getattr(detector, "frame_length", 512)

        try:
            for i in range(0, len(pcm) - frame_length + 1, frame_length):
                frame = pcm[i : i + frame_length]
                result = detector.process(frame)
                if isinstance(result, int) and result >= 0:
                    return True
            if 0 < len(pcm) < frame_length:
                padded = list(pcm) + [0] * (frame_length - len(pcm))
                result = detector.process(padded)
                if isinstance(result, int) and result >= 0:
                    return True
        except AudioError:
            raise
        except Exception as err:
            raise AudioError(f"Porcupine detection failed: {err}") from err

        return False

    def _get_or_create_detector(self) -> object:
        if self._porcupine is not None:
            return self._porcupine

        if not self._access_key:
            raise AudioError("PICOVOICE_ACCESS_KEY is not configured.")

        try:
            import pvporcupine
        except ImportError as err:
            raise AudioError("The pvporcupine package is not installed.") from err

        try:
            if self._keyword_path and os.path.exists(self._keyword_path):
                self._porcupine = pvporcupine.create(
                    access_key=self._access_key,
                    keyword_paths=[self._keyword_path],
                    sensitivities=list(self._sensitivities),
                )
            else:
                try:
                    self._porcupine = pvporcupine.create(
                        access_key=self._access_key,
                        keywords=[self._keyword_name],
                        sensitivities=list(self._sensitivities),
                    )
                except Exception:
                    self._porcupine = pvporcupine.create(
                        access_key=self._access_key,
                        keywords=["porcupine"],
                        sensitivities=list(self._sensitivities),
                    )
        except Exception as err:
            raise AudioError(f"Failed to initialize Porcupine detector: {err}") from err

        return self._porcupine

    def delete(self) -> None:
        """Libera recursos do detector Porcupine."""
        if self._is_deleted:
            return
        if self._porcupine is not None:
            delete_fn = getattr(self._porcupine, "delete", None)
            if callable(delete_fn):
                try:
                    delete_fn()
                except Exception:
                    pass
            self._porcupine = None
        self._is_deleted = True

    def close(self) -> None:
        """Alias para delete()."""
        self.delete()

    def __del__(self) -> None:
        try:
            self.delete()
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
