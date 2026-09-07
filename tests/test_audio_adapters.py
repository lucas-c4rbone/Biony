import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from core.audio import (
    AudioChunk,
    AudioError,
    SpeechAudio,
    SpeechToText,
    TextToSpeech,
    TranscriptionResult,
    WakeWordDetector,
)
from core.audio_adapters import (
    OpenAISpeechToText,
    OpenAITextToSpeech,
    PorcupineWakeWordDetector,
)


class FakePorcupineInstance:
    def __init__(self, detected_indices: list[int] | None = None, should_fail: bool = False) -> None:
        self.detected_indices = detected_indices or []
        self.should_fail = should_fail
        self.processed_frames: list[tuple[int, ...]] = []
        self.frame_length = 512
        self.deleted = False

    def process(self, frame: tuple[int, ...]) -> int:
        if self.should_fail:
            raise RuntimeError("Porcupine internal failure")
        self.processed_frames.append(frame)
        if self.detected_indices:
            return self.detected_indices.pop(0)
        return -1

    def delete(self) -> None:
        self.deleted = True


class FakeOpenAIAudioClient:
    def __init__(
        self,
        transcription_text: str = "Transcrição de teste",
        speech_bytes: bytes = b"fake_mp3_speech",
        stt_error: Exception | None = None,
        tts_error: Exception | None = None,
    ) -> None:
        self.transcription_text = transcription_text
        self.speech_bytes = speech_bytes
        self.stt_error = stt_error
        self.tts_error = tts_error

        self.stt_calls: list[dict[str, object]] = []
        self.tts_calls: list[dict[str, object]] = []

        outer = self

        class AudioTranscriptions:
            def create(self, model: str, file: object, **kwargs: object) -> object:
                outer.stt_calls.append({"model": model, "file": file, **kwargs})
                if outer.stt_error:
                    raise outer.stt_error

                class TranscriptionResponse:
                    text = outer.transcription_text

                return TranscriptionResponse()

        class AudioSpeech:
            def create(
                self, model: str, voice: str, input: str, response_format: str, **kwargs: object
            ) -> object:
                outer.tts_calls.append(
                    {
                        "model": model,
                        "voice": voice,
                        "input": input,
                        "response_format": response_format,
                        **kwargs,
                    }
                )
                if outer.tts_error:
                    raise outer.tts_error

                class SpeechResponse:
                    content = outer.speech_bytes

                return SpeechResponse()

        class AudioService:
            def __init__(self) -> None:
                self.transcriptions = AudioTranscriptions()
                self.speech = AudioSpeech()

        self.audio = AudioService()


class AudioAdaptersTests(unittest.TestCase):
    def test_porcupine_initializes_with_valid_config(self) -> None:
        inst = FakePorcupineInstance()
        detector = PorcupineWakeWordDetector(access_key="valid-key", porcupine_instance=inst)
        self.assertIsNotNone(detector)

    def test_porcupine_missing_credential_raises_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AudioError) as ctx:
                PorcupineWakeWordDetector()
            self.assertIn("PICOVOICE_ACCESS_KEY is not configured", str(ctx.exception))

    def test_porcupine_frame_detected_returns_true(self) -> None:
        inst = FakePorcupineInstance(detected_indices=[0])
        detector = PorcupineWakeWordDetector(porcupine_instance=inst)
        pcm_bytes = struct.pack("<512h", *([100] * 512))
        chunk = AudioChunk(pcm_bytes)

        self.assertTrue(detector.detect(chunk))
        self.assertEqual(len(inst.processed_frames), 1)

    def test_porcupine_frame_not_detected_returns_false(self) -> None:
        inst = FakePorcupineInstance(detected_indices=[-1])
        detector = PorcupineWakeWordDetector(porcupine_instance=inst)
        pcm_bytes = struct.pack("<512h", *([100] * 512))
        chunk = AudioChunk(pcm_bytes)

        self.assertFalse(detector.detect(chunk))

    def test_porcupine_resources_released(self) -> None:
        inst = FakePorcupineInstance()
        detector = PorcupineWakeWordDetector(porcupine_instance=inst)
        detector.delete()

        self.assertTrue(inst.deleted)
        with self.assertRaises(AudioError):
            detector.detect(AudioChunk(b"\x00" * 1024))

    def test_openai_stt_receives_audio(self) -> None:
        client = FakeOpenAIAudioClient()
        stt = OpenAISpeechToText(client=client)
        chunk = AudioChunk(data=b"\x00\x00" * 100)

        stt.transcribe(chunk)

        self.assertEqual(len(client.stt_calls), 1)
        self.assertEqual(client.stt_calls[0]["model"], "gpt-4o-mini-transcribe")

    def test_openai_stt_returns_transcription_result(self) -> None:
        client = FakeOpenAIAudioClient(transcription_text="Biony, bom dia")
        stt = OpenAISpeechToText(client=client)
        chunk = AudioChunk(data=b"\x00\x00" * 100)

        result = stt.transcribe(chunk)

        self.assertIsInstance(result, TranscriptionResult)
        self.assertEqual(result.text, "Biony, bom dia")

    def test_openai_stt_error_becomes_adapter_error(self) -> None:
        client = FakeOpenAIAudioClient(stt_error=RuntimeError("API Network Error"))
        stt = OpenAISpeechToText(client=client)
        chunk = AudioChunk(data=b"\x00\x00" * 100)

        with self.assertRaises(AudioError) as ctx:
            stt.transcribe(chunk)
        self.assertIn("OpenAI STT transcription failed", str(ctx.exception))

    def test_openai_tts_receives_text(self) -> None:
        client = FakeOpenAIAudioClient()
        tts = OpenAITextToSpeech(client=client)

        tts.synthesize("Bom dia, Lucas!")

        self.assertEqual(len(client.tts_calls), 1)
        self.assertEqual(client.tts_calls[0]["input"], "Bom dia, Lucas!")

    def test_openai_tts_returns_speech_audio(self) -> None:
        client = FakeOpenAIAudioClient(speech_bytes=b"synth_wav_data")
        tts = OpenAITextToSpeech(client=client)

        speech = tts.synthesize("Olá!")

        self.assertIsInstance(speech, SpeechAudio)
        self.assertEqual(speech.data, b"synth_wav_data")
        self.assertEqual(speech.text, "Olá!")

    def test_openai_tts_error_becomes_adapter_error(self) -> None:
        client = FakeOpenAIAudioClient(tts_error=RuntimeError("TTS Quota Exceeded"))
        tts = OpenAITextToSpeech(client=client)

        with self.assertRaises(AudioError) as ctx:
            tts.synthesize("Olá")
        self.assertIn("OpenAI TTS synthesis failed", str(ctx.exception))

    def test_configurable_stt_model(self) -> None:
        client = FakeOpenAIAudioClient()
        stt = OpenAISpeechToText(client=client, model="custom-stt-v2")

        stt.transcribe(AudioChunk(b"\x00\x00" * 100))

        self.assertEqual(client.stt_calls[0]["model"], "custom-stt-v2")

    def test_configurable_tts_model_and_voice(self) -> None:
        client = FakeOpenAIAudioClient()
        tts = OpenAITextToSpeech(client=client, model="custom-tts-v2", voice="nova")

        tts.synthesize("Teste de voz")

        self.assertEqual(client.tts_calls[0]["model"], "custom-tts-v2")
        self.assertEqual(client.tts_calls[0]["voice"], "nova")

    def test_no_secret_keys_in_code(self) -> None:
        source = Path("core/audio_adapters.py").read_text(encoding="utf-8")
        self.assertNotIn("porcupine_access_key_", source.lower())
        self.assertNotIn("sk-proj-", source.lower())

    def test_stage_16_interfaces_compatibility(self) -> None:
        inst = FakePorcupineInstance()
        client = FakeOpenAIAudioClient()

        porcupine = PorcupineWakeWordDetector(access_key="test", porcupine_instance=inst)
        stt = OpenAISpeechToText(client=client)
        tts = OpenAITextToSpeech(client=client)

        self.assertIsInstance(porcupine, WakeWordDetector)
        self.assertIsInstance(stt, SpeechToText)
        self.assertIsInstance(tts, TextToSpeech)
