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
    OpenWakeWordDetector,
)


class FakeOpenWakeWordModel:
    def __init__(self, scores: list[dict[str, float] | float] | None = None, should_fail: bool = False) -> None:
        self.scores = scores or []
        self.should_fail = should_fail
        self.processed_pcm: list[object] = []

    def predict(self, pcm_data: object) -> dict[str, float] | float:
        if self.should_fail:
            raise RuntimeError("openWakeWord internal failure")
        self.processed_pcm.append(pcm_data)
        if self.scores:
            return self.scores.pop(0)
        return {"biony": 0.0}


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
    def test_openwakeword_initializes_with_valid_config(self) -> None:
        inst = FakeOpenWakeWordModel()
        detector = OpenWakeWordDetector(model_path="models/biony.onnx", model_instance=inst)
        self.assertIsNotNone(detector)

    def test_openwakeword_missing_model_path_raises_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AudioError) as ctx:
                OpenWakeWordDetector()
            self.assertIn("OPENWAKEWORD_MODEL_PATH is not configured", str(ctx.exception))

    def test_openwakeword_detection_above_threshold_returns_true(self) -> None:
        inst = FakeOpenWakeWordModel(scores=[{"biony": 0.75}])
        detector = OpenWakeWordDetector(threshold=0.5, model_instance=inst)
        chunk = AudioChunk(struct.pack("<512h", *([100] * 512)))

        self.assertTrue(detector.detect(chunk))
        self.assertEqual(len(inst.processed_pcm), 1)

    def test_openwakeword_detection_below_threshold_returns_false(self) -> None:
        inst = FakeOpenWakeWordModel(scores=[{"biony": 0.3}])
        detector = OpenWakeWordDetector(threshold=0.5, model_instance=inst)
        chunk = AudioChunk(struct.pack("<512h", *([100] * 512)))

        self.assertFalse(detector.detect(chunk))

    def test_openwakeword_configurable_threshold(self) -> None:
        inst = FakeOpenWakeWordModel(scores=[{"biony": 0.7}])
        detector = OpenWakeWordDetector(threshold=0.8, model_instance=inst)
        chunk = AudioChunk(struct.pack("<512h", *([100] * 512)))

        self.assertFalse(detector.detect(chunk))

    def test_openwakeword_audio_chunk_conversion(self) -> None:
        inst = FakeOpenWakeWordModel(scores=[0.9])
        detector = OpenWakeWordDetector(model_instance=inst)
        pcm_bytes = struct.pack("<10h", 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
        chunk = AudioChunk(pcm_bytes)

        self.assertTrue(detector.detect(chunk))
        self.assertEqual(len(inst.processed_pcm), 1)

    def test_openwakeword_resources_released(self) -> None:
        inst = FakeOpenWakeWordModel()
        detector = OpenWakeWordDetector(model_instance=inst)
        detector.close()

        with self.assertRaises(AudioError):
            detector.detect(AudioChunk(b"\x00" * 1024))

    def test_openwakeword_error_becomes_adapter_error(self) -> None:
        inst = FakeOpenWakeWordModel(should_fail=True)
        detector = OpenWakeWordDetector(model_instance=inst)

        with self.assertRaises(AudioError) as ctx:
            detector.detect(AudioChunk(b"\x00" * 1024))
        self.assertIn("openWakeWord detection failed", str(ctx.exception))

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

    def test_no_secret_keys_or_picovoice_in_code(self) -> None:
        source = Path("core/audio_adapters.py").read_text(encoding="utf-8")
        self.assertNotIn("picovoice", source.lower())
        self.assertNotIn("porcupine", source.lower())
        self.assertNotIn("sk-proj-", source.lower())

    def test_stage_16_interfaces_compatibility(self) -> None:
        inst = FakeOpenWakeWordModel()
        client = FakeOpenAIAudioClient()

        oww = OpenWakeWordDetector(model_instance=inst)
        stt = OpenAISpeechToText(client=client)
        tts = OpenAITextToSpeech(client=client)

        self.assertIsInstance(oww, WakeWordDetector)
        self.assertIsInstance(stt, SpeechToText)
        self.assertIsInstance(tts, TextToSpeech)
