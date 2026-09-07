"""Arquitetura e serviço de orquestração de áudio do Biony Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable
from uuid import uuid4

from core.biony_core import BionyCore
from core.events import EventPublisher
from core.models import ConversationRequest, CoreEvent
from core.state_machine import BionyState


class AudioError(RuntimeError):
    """Exceção genérica para erros na camada de áudio."""


@dataclass(frozen=True)
class AudioChunk:
    """Bloco de dados de áudio amostrado."""

    data: bytes
    sample_rate: int = 16000
    channels: int = 1


@dataclass(frozen=True)
class TranscriptionResult:
    """Resultado de uma conversão de fala em texto (STT)."""

    text: str
    confidence: float = 1.0


@dataclass(frozen=True)
class SpeechAudio:
    """Objeto de áudio sintético (TTS) pronto para reprodução."""

    audio_id: str
    data: bytes
    text: str = ""


@runtime_checkable
class AudioInput(Protocol):
    """Porta para captura de áudio do microfone."""

    @property
    def is_capturing(self) -> bool:
        """Indica se a captura de áudio está ativa."""

    def start_capture(self) -> None:
        """Inicia a captura de áudio."""

    def stop_capture(self) -> None:
        """Encerra a captura de áudio."""

    def read_chunk(self) -> AudioChunk | None:
        """Lê um bloco de áudio capturado."""


@runtime_checkable
class AudioOutput(Protocol):
    """Porta para reprodução de áudio no alto-falante/speaker."""

    @property
    def is_playing(self) -> bool:
        """Indica se um áudio está sendo reproduzido."""

    def play(self, audio: SpeechAudio) -> bool:
        """Reproduz um áudio. Retorna True se a reprodução completou sem interrupção."""

    def stop(self) -> None:
        """Interrompe imediatamente qualquer áudio em reprodução."""


@runtime_checkable
class WakeWordDetector(Protocol):
    """Porta para detecção da palavra de ativação ("Biony")."""

    def detect(self, chunk: AudioChunk) -> bool:
        """Retorna True se a palavra de ativação for detectada no bloco de áudio."""


@runtime_checkable
class SpeechToText(Protocol):
    """Porta para transcrição de áudio em texto (STT)."""

    def transcribe(self, chunk: AudioChunk) -> TranscriptionResult:
        """Converte o bloco de áudio fornecido em texto."""


@runtime_checkable
class TextToSpeech(Protocol):
    """Porta para síntese de fala a partir de texto (TTS)."""

    def synthesize(self, text: str) -> SpeechAudio:
        """Gera um áudio a partir do texto."""


@runtime_checkable
class AudioProcessor(Protocol):
    """Porta para pré-processamento de áudio (redução de ruído, cancelamento de eco, etc.)."""

    def process(self, chunk: AudioChunk) -> AudioChunk:
        """Aplica filtros ou transformações no bloco de áudio."""


class SimpleAudioProcessor:
    """Processador de áudio pass-through sem alteração de dados."""

    def process(self, chunk: AudioChunk) -> AudioChunk:
        return chunk


class AudioService:
    """Orquestra a entrada e saída de voz e integrações com o BionyCore."""

    def __init__(
        self,
        core: BionyCore,
        audio_input: AudioInput,
        audio_output: AudioOutput,
        wake_word_detector: WakeWordDetector,
        stt: SpeechToText,
        tts: TextToSpeech,
        audio_processor: AudioProcessor | None = None,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        self.core = core
        self.audio_input = audio_input
        self.audio_output = audio_output
        self.wake_word_detector = wake_word_detector
        self.stt = stt
        self.tts = tts
        self.audio_processor = audio_processor or SimpleAudioProcessor()
        self.event_publisher = event_publisher or getattr(core, "event_publisher", None)

    def start_listening(self) -> None:
        """Inicia a captura pelo AudioInput."""
        try:
            self.audio_input.start_capture()
        except Exception as err:
            self._publish_event("audio_error", {"error": f"AudioInput start failed: {err}"})
            raise AudioError(f"Failed to start AudioInput: {err}") from err

    def stop_listening(self) -> None:
        """Encerra a captura pelo AudioInput."""
        try:
            self.audio_input.stop_capture()
        except Exception as err:
            self._publish_event("audio_error", {"error": f"AudioInput stop failed: {err}"})
            raise AudioError(f"Failed to stop AudioInput: {err}") from err

    def read_audio_chunk(self) -> AudioChunk | None:
        """Lê o próximo bloco de áudio capturado."""
        try:
            return self.audio_input.read_chunk()
        except Exception as err:
            self._publish_event("audio_error", {"error": f"AudioInput read failed: {err}"})
            raise AudioError(f"Failed to read from AudioInput: {err}") from err

    def check_wake_word(self, chunk: AudioChunk) -> bool:
        """Verifica a palavra de ativação e gerencia interrupções de fala se necessário."""
        processed_chunk = self.audio_processor.process(chunk)
        detected = self.wake_word_detector.detect(processed_chunk)

        if detected:
            if self.audio_output.is_playing or self.core.state_machine.state == BionyState.SPEAKING:
                self.interrupt_speech()

            self._publish_event("wake_detected", {"keyword": "Biony"})
            self.core.transition_to(BionyState.WAKING)
            self.core.transition_to(BionyState.LISTENING)

        return detected

    def interrupt_speech(self) -> None:
        """Interrompe imediatamente qualquer fala ou áudio em reprodução."""
        if self.audio_output.is_playing or self.core.state_machine.state == BionyState.SPEAKING:
            try:
                self.audio_output.stop()
            except Exception as err:
                self._publish_event("audio_error", {"error": f"AudioOutput stop failed: {err}"})
                raise AudioError(f"Failed to stop AudioOutput: {err}") from err
            self._publish_event("audio_stopped", {"reason": "interrupted"})

    def transcribe(self, chunk: AudioChunk) -> TranscriptionResult:
        """Converte um bloco de áudio em texto via SpeechToText (STT)."""
        self._publish_event("transcription_started", {})
        try:
            result = self.stt.transcribe(chunk)
        except Exception as err:
            self._publish_event("audio_error", {"error": f"STT failed: {err}"})
            self.core.transition_to(BionyState.IDLE)
            raise AudioError(f"SpeechToText failed: {err}") from err

        self._publish_event("transcription_finished", {"text": result.text})
        return result

    def synthesize_and_speak(self, text: str) -> SpeechAudio | None:
        """Sintetiza texto em voz (TTS) e envia para reprodução no AudioOutput."""
        if not text or not text.strip():
            return None

        try:
            speech = self.tts.synthesize(text)
        except Exception as err:
            self._publish_event("audio_error", {"error": f"TTS failed: {err}"})
            self.core.transition_to(BionyState.IDLE)
            raise AudioError(f"TextToSpeech failed: {err}") from err

        self.core.transition_to(BionyState.SPEAKING)
        self._publish_event("speech_started", {"text": text, "audio_id": speech.audio_id})
        self._publish_event("audio_started", {"audio_id": speech.audio_id})

        try:
            completed = self.audio_output.play(speech)
        except Exception as err:
            self._publish_event("audio_error", {"error": f"AudioOutput play failed: {err}"})
            self.core.transition_to(BionyState.IDLE)
            raise AudioError(f"AudioOutput failed: {err}") from err

        if completed:
            self._publish_event("speech_finished", {"audio_id": speech.audio_id})
            self._publish_event("audio_finished", {"audio_id": speech.audio_id})
            self.core.transition_to(BionyState.IDLE)

        return speech

    def process_voice_interaction(
        self, chunk: AudioChunk, session_id: str | None = None
    ) -> str | None:
        """Executa a esteira completa de interação por voz a partir de um bloco de áudio."""
        processed_chunk = self.audio_processor.process(chunk)
        detected = self.check_wake_word(processed_chunk)
        if not detected:
            return None

        transcription = self.transcribe(processed_chunk)

        self.core.transition_to(BionyState.THINKING)
        response = self.core.handle_message(
            ConversationRequest(message=transcription.text), session_id=session_id
        )

        if response.message:
            self.synthesize_and_speak(response.message)
        else:
            self.core.transition_to(BionyState.IDLE)

        return response.message

    def _publish_event(self, event_type: str, data: dict[str, object]) -> None:
        if self.event_publisher is not None:
            self.event_publisher.publish(CoreEvent(event_type=event_type, data=data))


# Re-export adapters
from core.audio_adapters import OpenAISpeechToText, OpenAITextToSpeech, PorcupineWakeWordDetector
