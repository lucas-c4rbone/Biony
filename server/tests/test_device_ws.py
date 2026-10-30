from __future__ import annotations

import io
import wave

from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from biony.api.app import create_app
from biony.api.device_ws import AUDIO_CHUNK, MAX_UTTERANCE_BYTES, MIC_RATE, pcm_to_wav, wav_to_pcm
from biony.core.models import LLMReply, ToolCall
from biony.core.voice import VoiceAssistant, VoiceSlot

from conftest import RecordingTool, ScriptedLLM, make_engine

TOKEN = "t" * 32
SPEECH_RATE = 22050


class WavTTS:
    """TTS falso que devolve um WAV de verdade (o totem recebe PCM cru)."""

    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.spoken.append(text)
        return pcm_to_wav(b"\x01\x00" * (len(text) * 1000), SPEECH_RATE)


class WavSTT:
    def __init__(self, text: str = "liga a luz") -> None:
        self.text = text
        self.received: list[tuple[int, int, int]] = []  # (taxa, canais, frames)

    async def transcribe(self, audio: bytes) -> str:
        with wave.open(io.BytesIO(audio)) as wav:
            self.received.append((wav.getframerate(), wav.getnchannels(), wav.getnframes()))
        return self.text


def make_client(store, llm=None, stt=None, voice_ready=True, tools=()):
    engine = make_engine(llm or ScriptedLLM(LLMReply("Liguei!")), store, *tools)
    slot = VoiceSlot(enabled=True)
    tts = WavTTS()
    stt = stt or WavSTT()
    if voice_ready:
        slot.assistant = VoiceAssistant(engine, stt, tts)
    return TestClient(create_app(engine, TOKEN, slot)), stt, tts


def hello(ws, token=TOKEN):
    ws.send_json({"tipo": "ola", "token": token, "dispositivo": "Quarto!"})
    return ws.receive_json()


def receive_speech(ws):
    start = ws.receive_json()
    assert start["tipo"] == "audio_inicio" and start["formato"] == "pcm16"
    pcm = b""
    while len(pcm) < start["bytes"]:
        pcm += ws.receive_bytes()
    assert ws.receive_json() == {"tipo": "audio_fim"}
    return start, pcm


def test_full_voice_turn(store):
    llm = ScriptedLLM(LLMReply(tool_calls=(ToolCall("c", "luz", {}),)), LLMReply("Liguei!"))
    client, stt, tts = make_client(store, llm=llm, tools=[RecordingTool("luz")])

    with client.websocket_connect("/ws/dispositivo") as ws:
        ok = hello(ws)
        assert ok["tipo"] == "ola_ok" and ok["sessao"] == "totem-quarto" and ok["voz"] == "pronta"
        assert ok["microfone"]["taxa"] == MIC_RATE

        ws.send_json({"tipo": "ouvir_inicio"})
        for _ in range(4):
            ws.send_bytes(b"\x00\x01" * 4000)  # 4 pedaços de 0,25 s
        ws.send_json({"tipo": "ouvir_fim"})

        assert ws.receive_json() == {"tipo": "estado", "estado": "pensando"}
        assert ws.receive_json() == {"tipo": "transcricao", "texto": "liga a luz"}
        assert ws.receive_json() == {"tipo": "resposta", "texto": "Liguei!", "emocao": "feliz", "aguardando_confirmacao": False, "audio": True}
        start, pcm = receive_speech(ws)

    assert stt.received == [(MIC_RATE, 1, 16000)]  # o servidor montou um WAV de 1 s
    assert start["taxa"] == SPEECH_RATE and len(pcm) == start["bytes"] == len("Liguei!") * 2000
    assert "por voz" in llm.calls[0][0].content


def test_text_message_is_answered_with_speech(store):
    client, _, tts = make_client(store, llm=ScriptedLLM(LLMReply("São vinte horas.")))

    with client.websocket_connect("/ws/dispositivo") as ws:
        hello(ws)
        ws.send_json({"tipo": "texto", "texto": "que horas são?"})
        assert ws.receive_json()["estado"] == "pensando"
        assert ws.receive_json()["texto"] == "São vinte horas."
        _, pcm = receive_speech(ws)

    assert tts.spoken == ["São vinte horas."] and len(pcm) > AUDIO_CHUNK  # foi em vários pedaços


def test_session_keeps_context_between_connections(store):
    llm = ScriptedLLM(LLMReply("primeira"), LLMReply("segunda"))
    client, _, _ = make_client(store, llm=llm)

    for text in ("oi", "lembra?"):
        with client.websocket_connect("/ws/dispositivo") as ws:
            hello(ws)
            ws.send_json({"tipo": "texto", "texto": text})
            ws.receive_json(), ws.receive_json()
            receive_speech(ws)

    assert [m.content for m in llm.calls[1][1:]] == ["oi", "primeira", "lembra?"]


def test_bad_token_and_bad_hello_are_closed(store):
    client, _, _ = make_client(store)

    with client.websocket_connect("/ws/dispositivo") as ws:
        assert hello(ws, token="errado")["mensagem"] == "Token inválido."
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4401

    with client.websocket_connect("/ws/dispositivo") as ws:
        ws.send_json({"tipo": "ouvir_inicio"})
        assert ws.receive_json()["tipo"] == "erro"
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4400


def test_protocol_errors_keep_the_connection(store):
    client, stt, _ = make_client(store)

    with client.websocket_connect("/ws/dispositivo") as ws:
        hello(ws)
        ws.send_bytes(b"\x00" * 100)
        assert "ouvir_inicio" in ws.receive_json()["mensagem"]
        ws.send_text("isso não é json")
        assert ws.receive_json()["tipo"] == "erro"
        ws.send_json({"tipo": "dancar"})
        assert "desconhecido" in ws.receive_json()["mensagem"]

        ws.send_json({"tipo": "ouvir_inicio"})
        ws.send_bytes(b"\x00" * (MAX_UTTERANCE_BYTES + 2))
        assert "longa demais" in ws.receive_json()["mensagem"]

        ws.send_json({"tipo": "ouvir_inicio"})
        ws.send_bytes(b"\x00" * 100)  # toque sem fala
        ws.send_json({"tipo": "ouvir_fim"})
        assert ws.receive_json() == {"tipo": "estado", "estado": "ocioso"}

        ws.send_json({"tipo": "ping"})
        assert ws.receive_json() == {"tipo": "pong"}
    assert stt.received == []


def test_voice_not_ready(store):
    client, _, _ = make_client(store, voice_ready=False)

    with client.websocket_connect("/ws/dispositivo") as ws:
        assert hello(ws)["voz"] == "carregando"
        ws.send_json({"tipo": "ouvir_inicio"})
        ws.send_bytes(b"\x00" * 20000)
        ws.send_json({"tipo": "ouvir_fim"})
        assert ws.receive_json()["mensagem"] == "Voz carregando."


def test_wav_helpers_roundtrip():
    pcm = bytes(range(256)) * 10
    assert wav_to_pcm(pcm_to_wav(pcm, 16000)) == (pcm, 16000)


def test_text_reply_without_voice_says_no_audio(store):
    client, _, _ = make_client(store, llm=ScriptedLLM(LLMReply("Oi!")), voice_ready=False)

    with client.websocket_connect("/ws/dispositivo") as ws:
        hello(ws)
        ws.send_json({"tipo": "texto", "texto": "oi"})
        ws.receive_json()
        assert ws.receive_json()["audio"] is False
        ws.send_json({"tipo": "ping"})
        assert ws.receive_json() == {"tipo": "pong"}  # nada de áudio pendente no caminho
