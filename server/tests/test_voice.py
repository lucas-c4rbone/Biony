from __future__ import annotations

import base64

from fastapi.testclient import TestClient
import pytest

from biony.adapters.piper_tts import speakable
from biony.api.app import MAX_AUDIO_BYTES, create_app
from biony.core.models import Channel, LLMReply
from biony.core.ports import AudioError
from biony.core.voice import NOTHING_HEARD, VoiceAssistant

from conftest import ScriptedLLM, make_engine

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeSTT:
    def __init__(self, text: str = "liga a luz", error: Exception | None = None) -> None:
        self.text, self.error, self.received = text, error, []

    async def transcribe(self, audio: bytes) -> str:
        self.received.append(audio)
        if self.error:
            raise self.error
        return self.text


class FakeTTS:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.spoken.append(text)
        return b"RIFF" + text.encode()


@pytest.mark.anyio
async def test_voice_uses_voice_style_and_returns_speech(store):
    llm = ScriptedLLM(LLMReply("Liguei!"))
    tts = FakeTTS()
    voice = VoiceAssistant(make_engine(llm, store), FakeSTT("liga a luz"), tts)

    result = await voice.handle(b"audio", "s1")

    assert result.transcript == "liga a luz"
    assert result.reply.text == "Liguei!"
    assert result.audio == b"RIFFLiguei!"
    system = llm.calls[0][0].content
    assert "por voz" in system and "por texto" not in system
    assert llm.calls[0][-1].content == "liga a luz"


@pytest.mark.anyio
async def test_silence_skips_llm(store):
    llm = ScriptedLLM()
    tts = FakeTTS()

    result = await VoiceAssistant(make_engine(llm, store), FakeSTT(""), tts).handle(b"audio")

    assert result.reply.text == NOTHING_HEARD
    assert tts.spoken == [NOTHING_HEARD]
    assert llm.calls == []
    assert result.reply.session_id


@pytest.mark.anyio
async def test_audio_reply_is_optional(store):
    tts = FakeTTS()
    voice = VoiceAssistant(make_engine(ScriptedLLM(LLMReply("ok")), store), FakeSTT(), tts)

    result = await voice.handle(b"audio", with_audio=False)

    assert result.audio is None and tts.spoken == []


@pytest.mark.anyio
async def test_text_channel_is_default(store):
    llm = ScriptedLLM(LLMReply("ok"))

    await make_engine(llm, store).handle("oi", "s1")

    assert "por texto" in llm.calls[0][0].content
    assert Channel.TEXT.value == "texto"


def client(store, stt=None, llm=None, voice_enabled=True) -> tuple[TestClient, FakeTTS]:
    tts = FakeTTS()
    engine = make_engine(llm or ScriptedLLM(LLMReply("Liguei!")), store)
    voice = VoiceAssistant(engine, stt or FakeSTT(), tts) if voice_enabled else None
    return TestClient(create_app(engine, TOKEN, voice)), tts


def test_voz_endpoint(store):
    api, _ = client(store)

    response = api.post("/voz", files={"audio": ("fala.wav", b"wav", "audio/wav")}, data={"sessao": "s1"}, headers=AUTH)

    body = response.json()
    assert response.status_code == 200
    assert body["sessao"] == "s1"
    assert body["transcricao"] == "liga a luz"
    assert body["resposta"] == "Liguei!"
    assert base64.b64decode(body["audio_wav_base64"]) == b"RIFFLiguei!"


def test_voz_without_audio_reply(store):
    api, tts = client(store)

    body = api.post(
        "/voz", files={"audio": ("f.wav", b"wav")}, data={"responder_com_audio": "false"}, headers=AUTH
    ).json()

    assert body["audio_wav_base64"] is None and tts.spoken == []


def test_voz_errors(store):
    assert client(store)[0].post("/voz", files={"audio": ("f.wav", b"x")}).status_code == 401
    assert client(store, voice_enabled=False)[0].post("/voz", files={"audio": ("f.wav", b"x")}, headers=AUTH).status_code == 503

    big = b"0" * (MAX_AUDIO_BYTES + 1)
    assert client(store)[0].post("/voz", files={"audio": ("f.wav", big)}, headers=AUTH).status_code == 413

    broken = client(store, stt=FakeSTT(error=AudioError("formato estranho")))[0]
    response = broken.post("/voz", files={"audio": ("f.wav", b"x")}, headers=AUTH)
    assert response.status_code == 422 and "formato estranho" in response.json()["detail"]


def test_speakable_strips_markdown_and_emoji():
    assert speakable("**Pronto!** Liguei a `fita` 😄🎉\n\n# ok") == "Pronto! Liguei a fita ok"
    assert speakable("ar-condicionado às 20h") == "ar-condicionado às 20h"
