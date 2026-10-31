from __future__ import annotations

import httpx
import pytest

from biony.adapters.azure_tts import AzureTTS, TtsUnavailable, build_ssml
from biony.core.voice import FallbackTextToSpeech

pytestmark = pytest.mark.anyio

WAV = b"RIFF" + b"\x00" * 40


def test_ssml_escapes_text_and_sets_language_and_prosody():
    ssml = build_ssml("Tom & Jerry <3 **oi**", "pt-BR-AntonioNeural", pitch="-10%", rate="-5%")
    assert 'xml:lang="pt-BR"' in ssml and 'name="pt-BR-AntonioNeural"' in ssml
    assert 'pitch="-10%"' in ssml and 'rate="-5%"' in ssml
    assert "Tom &amp; Jerry &lt;3 oi" in ssml


async def test_posts_ssml_with_key_and_returns_wav():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=WAV)

    tts = AzureTTS(key=" KEY ", region="brazilsouth", voice="pt-BR-AntonioNeural", transport=httpx.MockTransport(handler))
    assert await tts.synthesize("oi") == WAV
    request = seen[0]
    assert str(request.url) == "https://brazilsouth.tts.speech.microsoft.com/cognitiveservices/v1"
    assert request.headers["Ocp-Apim-Subscription-Key"] == "KEY"
    assert request.headers["X-Microsoft-OutputFormat"] == "riff-22050hz-16bit-mono-pcm"
    assert b"oi" in request.content


@pytest.mark.parametrize("status, message", [(401, "chave"), (429, "limite"), (500, "HTTP 500")])
async def test_errors_become_tts_unavailable(status, message):
    tts = AzureTTS(key="k", region="r", voice="pt-BR-X",
                   transport=httpx.MockTransport(lambda r: httpx.Response(status, text="erro")))
    with pytest.raises(TtsUnavailable, match=message):
        await tts.synthesize("oi")


class Voice:
    def __init__(self, audio: bytes | None) -> None:
        self.audio = audio

    async def synthesize(self, text: str) -> bytes:
        if self.audio is None:
            raise TtsUnavailable("fora do ar")
        return self.audio


async def test_fallback_uses_local_voice_when_cloud_fails():
    assert await FallbackTextToSpeech(Voice(b"nuvem"), Voice(b"local")).synthesize("oi") == b"nuvem"
    assert await FallbackTextToSpeech(Voice(None), Voice(b"local")).synthesize("oi") == b"local"
