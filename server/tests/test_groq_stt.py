from __future__ import annotations

import httpx
import pytest

from biony.adapters.groq_stt import GroqSTT, SttUnavailable, guess_filename
from biony.core.ports import AudioError
from biony.core.voice import FallbackSpeechToText

pytestmark = pytest.mark.anyio


def groq(handler) -> GroqSTT:
    return GroqSTT(api_key="chave", transport=httpx.MockTransport(handler))


async def test_sends_audio_and_reads_text():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"text": " liga o setup "})

    text = await groq(handler).transcribe(b"RIFF....WAVEfmt ")

    request = seen[0]
    body = request.content.decode("latin-1")
    assert request.url == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert request.headers["Authorization"] == "Bearer chave"
    assert 'filename="fala.wav"' in body and "whisper-large-v3-turbo" in body and "Biony" in body
    assert text == "liga o setup"


@pytest.mark.parametrize("status, error", [(400, AudioError), (429, SttUnavailable), (500, SttUnavailable)])
async def test_errors(status, error):
    with pytest.raises(error):
        await groq(lambda r: httpx.Response(status, text="x")).transcribe(b"RIFF")


async def test_network_error_is_unavailable():
    def handler(request):
        raise httpx.ConnectError("sem rede")

    with pytest.raises(SttUnavailable):
        await groq(handler).transcribe(b"RIFF")


def test_guess_filename():
    assert guess_filename(b"RIFF1234WAVE") == "fala.wav"
    assert guess_filename(b"OggS") == "fala.ogg"
    assert guess_filename(b"\x1aE\xdf\xa3") == "fala.webm"
    assert guess_filename(b"\x00\x00\x00\x18ftypM4A ") == "fala.m4a"


class Fixed:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.calls = text, error, 0

    async def transcribe(self, audio):
        self.calls += 1
        if self.error:
            raise self.error
        return self.text


async def test_fallback_uses_local_only_when_cloud_fails():
    cloud, local = Fixed("nuvem"), Fixed("local")
    assert await FallbackSpeechToText(cloud, local).transcribe(b"x") == "nuvem" and local.calls == 0

    cloud = Fixed(error=SttUnavailable("caiu"))
    assert await FallbackSpeechToText(cloud, local).transcribe(b"x") == "local"

    unreadable = Fixed(error=AudioError("lixo"))
    with pytest.raises(AudioError):
        await FallbackSpeechToText(unreadable, Fixed("local")).transcribe(b"x")
