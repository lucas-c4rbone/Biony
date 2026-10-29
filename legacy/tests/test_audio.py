import unittest

from core.audio import (
    AudioChunk,
    AudioError,
    AudioProcessor,
    AudioService,
    SimpleAudioProcessor,
    SpeechAudio,
    TranscriptionResult,
)
from core.biony_core import BionyCore
from core.conversation import ConversationService
from core.devices import DeviceManager
from core.events import EventDispatcher
from core.memory import InMemoryMemoryStore
from core.models import CoreEvent
from core.permissions import SimplePermissionPolicy
from core.simulated_brain import SimulatedBrain
from core.state_machine import BionyState, StateMachine
from core.tools import ToolCatalog


class FakeAudioInput:
    def __init__(self, chunks: list[AudioChunk] | None = None, should_fail: bool = False) -> None:
        self.chunks = chunks or []
        self._is_capturing = False
        self.should_fail = should_fail
        self.start_calls = 0
        self.stop_calls = 0

    @property
    def is_capturing(self) -> bool:
        return self._is_capturing

    def start_capture(self) -> None:
        if self.should_fail:
            raise RuntimeError("FakeAudioInput hardware error")
        self._is_capturing = True
        self.start_calls += 1

    def stop_capture(self) -> None:
        if self.should_fail:
            raise RuntimeError("FakeAudioInput hardware error")
        self._is_capturing = False
        self.stop_calls += 1

    def read_chunk(self) -> AudioChunk | None:
        if self.should_fail:
            raise RuntimeError("FakeAudioInput read error")
        if self.chunks:
            return self.chunks.pop(0)
        return None


class FakeAudioOutput:
    def __init__(self, should_fail: bool = False) -> None:
        self._is_playing = False
        self.should_fail = should_fail
        self.played_audios: list[SpeechAudio] = []
        self.stop_calls = 0

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def play(self, audio: SpeechAudio) -> bool:
        if self.should_fail:
            raise RuntimeError("FakeAudioOutput play error")
        self._is_playing = True
        self.played_audios.append(audio)
        self._is_playing = False
        return True

    def stop(self) -> None:
        if self.should_fail:
            raise RuntimeError("FakeAudioOutput stop error")
        self.stop_calls += 1
        self._is_playing = False


class FakeWakeWordDetector:
    def __init__(self, detected: bool = True) -> None:
        self.detected = detected
        self.checked_chunks: list[AudioChunk] = []

    def detect(self, chunk: AudioChunk) -> bool:
        self.checked_chunks.append(chunk)
        return self.detected


class FakeSpeechToText:
    def __init__(self, text: str = "Olá, Biony", should_fail: bool = False) -> None:
        self.text = text
        self.should_fail = should_fail
        self.transcribed_chunks: list[AudioChunk] = []

    def transcribe(self, chunk: AudioChunk) -> TranscriptionResult:
        if self.should_fail:
            raise RuntimeError("STT provider offline")
        self.transcribed_chunks.append(chunk)
        return TranscriptionResult(text=self.text, confidence=0.98)


class FakeTextToSpeech:
    def __init__(self, audio_data: bytes = b"fake_wav_data", should_fail: bool = False) -> None:
        self.audio_data = audio_data
        self.should_fail = should_fail
        self.synthesized_texts: list[str] = []

    def synthesize(self, text: str) -> SpeechAudio:
        if self.should_fail:
            raise RuntimeError("TTS provider offline")
        self.synthesized_texts.append(text)
        return SpeechAudio(audio_id="speech_001", data=self.audio_data, text=text)


class AudioArchitectureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = EventDispatcher()
        self.received_events: list[CoreEvent] = []
        self.events.subscribe(self.received_events.append)

        self.state_machine = StateMachine(initial_state=BionyState.IDLE)
        self.core = BionyCore(
            state_machine=self.state_machine,
            conversation_service=ConversationService(SimulatedBrain()),
            memory_store=InMemoryMemoryStore(),
            tool_catalog=ToolCatalog(),
            permission_policy=SimplePermissionPolicy(),
            event_publisher=self.events,
            device_manager=DeviceManager(event_publisher=self.events),
        )

        self.audio_input = FakeAudioInput()
        self.audio_output = FakeAudioOutput()
        self.wake_detector = FakeWakeWordDetector(detected=True)
        self.stt = FakeSpeechToText("Olá, Biony")
        self.tts = FakeTextToSpeech()

        self.service = AudioService(
            core=self.core,
            audio_input=self.audio_input,
            audio_output=self.audio_output,
            wake_word_detector=self.wake_detector,
            stt=self.stt,
            tts=self.tts,
            event_publisher=self.events,
        )

    def test_audio_input_start_stop(self) -> None:
        self.assertFalse(self.audio_input.is_capturing)
        self.service.start_listening()
        self.assertTrue(self.audio_input.is_capturing)
        self.assertEqual(self.audio_input.start_calls, 1)

        self.service.stop_listening()
        self.assertFalse(self.audio_input.is_capturing)
        self.assertEqual(self.audio_input.stop_calls, 1)

    def test_audio_output_play(self) -> None:
        speech = SpeechAudio("speech_01", b"pcm_bytes", "Olá")
        success = self.audio_output.play(speech)

        self.assertTrue(success)
        self.assertEqual(self.audio_output.played_audios, [speech])

    def test_audio_output_interrupt(self) -> None:
        self.audio_output._is_playing = True
        self.service.interrupt_speech()

        self.assertFalse(self.audio_output.is_playing)
        self.assertEqual(self.audio_output.stop_calls, 1)
        self.assertIn("audio_stopped", [e.event_type for e in self.received_events])

    def test_wake_word_detected(self) -> None:
        chunk = AudioChunk(b"wake_pcm")
        detected = self.service.check_wake_word(chunk)

        self.assertTrue(detected)
        self.assertEqual(self.core.state_machine.state, BionyState.LISTENING)
        self.assertIn("wake_detected", [e.event_type for e in self.received_events])

    def test_wake_word_not_detected(self) -> None:
        self.wake_detector.detected = False
        chunk = AudioChunk(b"silence_pcm")
        detected = self.service.check_wake_word(chunk)

        self.assertFalse(detected)
        self.assertEqual(self.core.state_machine.state, BionyState.IDLE)
        self.assertNotIn("wake_detected", [e.event_type for e in self.received_events])

    def test_stt_receives_audio(self) -> None:
        chunk = AudioChunk(b"speech_pcm")
        self.service.transcribe(chunk)

        self.assertEqual(self.stt.transcribed_chunks, [chunk])

    def test_stt_returns_transcription(self) -> None:
        self.stt.text = "Qual seu nome?"
        chunk = AudioChunk(b"speech_pcm")
        result = self.service.transcribe(chunk)

        self.assertEqual(result.text, "Qual seu nome?")
        self.assertEqual(result.confidence, 0.98)

    def test_tts_receives_text(self) -> None:
        self.service.synthesize_and_speak("Eu sou o Biony")

        self.assertEqual(self.tts.synthesized_texts, ["Eu sou o Biony"])

    def test_tts_returns_audio(self) -> None:
        speech = self.tts.synthesize("Teste")

        self.assertEqual(speech.data, b"fake_wav_data")
        self.assertEqual(speech.text, "Teste")

    def test_pipeline_wake_listening_transcription(self) -> None:
        chunk = AudioChunk(b"voice_data")
        self.service.process_voice_interaction(chunk)

        event_types = [e.event_type for e in self.received_events]
        self.assertIn("wake_detected", event_types)
        self.assertIn("transcription_started", event_types)
        self.assertIn("transcription_finished", event_types)

    def test_pipeline_transcription_to_core(self) -> None:
        self.stt.text = "Qual seu nome?"
        chunk = AudioChunk(b"voice_data")
        self.service.process_voice_interaction(chunk, session_id="voice_session")

        ctx = self.core.get_context("voice_session")
        self.assertEqual(ctx[0].content, "Qual seu nome?")
        self.assertIn("Biony", ctx[1].content)

    def test_pipeline_response_tts_output(self) -> None:
        self.stt.text = "Olá, Biony"
        chunk = AudioChunk(b"voice_data")
        response_text = self.service.process_voice_interaction(chunk)

        self.assertIn("Lucas", response_text)
        self.assertEqual(len(self.audio_output.played_audios), 1)
        self.assertEqual(self.audio_output.played_audios[0].text, response_text)

    def test_audio_interruption(self) -> None:
        self.audio_output._is_playing = True
        self.service.interrupt_speech()

        self.assertEqual(self.audio_output.stop_calls, 1)

    def test_new_wake_word_during_speaking(self) -> None:
        self.core.state_machine.transition_to(BionyState.SPEAKING)
        self.audio_output._is_playing = True

        chunk = AudioChunk(b"new_wake_pcm")
        detected = self.service.check_wake_word(chunk)

        self.assertTrue(detected)
        self.assertEqual(self.audio_output.stop_calls, 1)
        self.assertEqual(self.core.state_machine.state, BionyState.LISTENING)
        self.assertIn("audio_stopped", [e.event_type for e in self.received_events])

    def test_stt_error_handling(self) -> None:
        self.stt.should_fail = True
        chunk = AudioChunk(b"audio_pcm")

        with self.assertRaises(AudioError):
            self.service.transcribe(chunk)

        self.assertEqual(self.core.state_machine.state, BionyState.IDLE)
        self.assertIn("audio_error", [e.event_type for e in self.received_events])

    def test_tts_error_handling(self) -> None:
        self.tts.should_fail = True

        with self.assertRaises(AudioError):
            self.service.synthesize_and_speak("Fala com erro")

        self.assertEqual(self.core.state_machine.state, BionyState.IDLE)
        self.assertIn("audio_error", [e.event_type for e in self.received_events])

    def test_audio_input_error_handling(self) -> None:
        failing_input = FakeAudioInput(should_fail=True)
        service = AudioService(
            core=self.core,
            audio_input=failing_input,
            audio_output=self.audio_output,
            wake_word_detector=self.wake_detector,
            stt=self.stt,
            tts=self.tts,
            event_publisher=self.events,
        )

        with self.assertRaises(AudioError):
            service.start_listening()

        with self.assertRaises(AudioError):
            service.read_audio_chunk()

        self.assertIn("audio_error", [e.event_type for e in self.received_events])

    def test_events_published_during_pipeline(self) -> None:
        chunk = AudioChunk(b"full_pipeline_pcm")
        self.service.process_voice_interaction(chunk)

        event_types = [e.event_type for e in self.received_events]
        expected_types = [
            "wake_detected",
            "transcription_started",
            "transcription_finished",
            "speech_started",
            "audio_started",
            "speech_finished",
            "audio_finished",
        ]
        for evt in expected_types:
            self.assertIn(evt, event_types)

    def test_processor_integration(self) -> None:
        class FakeProcessor(AudioProcessor):
            def process(self, chunk: AudioChunk) -> AudioChunk:
                return AudioChunk(chunk.data + b"_filtered")

        processor = FakeProcessor()
        service = AudioService(
            core=self.core,
            audio_input=self.audio_input,
            audio_output=self.audio_output,
            wake_word_detector=self.wake_detector,
            stt=self.stt,
            tts=self.tts,
            audio_processor=processor,
            event_publisher=self.events,
        )

        chunk = AudioChunk(b"raw")
        service.check_wake_word(chunk)

        self.assertEqual(self.wake_detector.checked_chunks[0].data, b"raw_filtered")
