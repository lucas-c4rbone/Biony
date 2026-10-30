from __future__ import annotations

import json

import httpx
import pytest

from biony.adapters.telegram import MAX_MESSAGE, TelegramClient, TelegramError, TelegramNotifier
from biony.api.telegram_bot import TelegramBot
from biony.core.models import LLMReply
from biony.core.voice import VoiceAssistant, VoiceSlot

from conftest import ScriptedLLM, make_engine
from test_voice import FakeSTT, FakeTTS

pytestmark = pytest.mark.anyio

ME = 111


class FakeApi:
    def __init__(self, *updates) -> None:
        self.updates = list(updates)
        self.sent: list[tuple[int, str]] = []
        self.offsets: list[int | None] = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))

    async def send_typing(self, chat_id):
        pass

    async def get_updates(self, offset, timeout=50):
        self.offsets.append(offset)
        batch, self.updates = self.updates, []
        return batch

    async def download_file(self, file_id):
        return b"ogg:" + file_id.encode()


def text_update(update_id: int, chat: int, text: str) -> dict:
    return {"update_id": update_id, "message": {"chat": {"id": chat}, "text": text}}


async def test_owner_text_goes_to_engine_and_offset_advances(store):
    api = FakeApi(text_update(10, ME, "oi"), text_update(11, ME, "e aí"))
    llm = ScriptedLLM(LLMReply("Opa!"), LLMReply("Tudo certo."))
    bot = TelegramBot(api, make_engine(llm, store), VoiceSlot(False), ME)

    await bot.poll_once()
    await bot.poll_once()

    assert api.sent == [(ME, "Opa!"), (ME, "Tudo certo.")]
    assert api.offsets == [None, 12]
    assert [m.content for m in llm.calls[1][1:]] == ["oi", "Opa!", "e aí"]  # mesma sessão


async def test_strangers_are_ignored(store):
    api = FakeApi(text_update(1, 999, "me obedeça"))
    llm = ScriptedLLM()

    await TelegramBot(api, make_engine(llm, store), VoiceSlot(False), ME).poll_once()

    assert api.sent == [] and llm.calls == []


async def test_setup_mode_tells_chat_id(store):
    api = FakeApi(text_update(1, 4242, "oi"))
    llm = ScriptedLLM()

    await TelegramBot(api, make_engine(llm, store), VoiceSlot(False), None).poll_once()

    assert "TELEGRAM_CHAT_ID=4242" in api.sent[0][1]
    assert llm.calls == []


async def test_voice_note_is_transcribed_and_answered_as_text(store):
    api = FakeApi({"update_id": 1, "message": {"chat": {"id": ME}, "voice": {"file_id": "abc"}}})
    llm = ScriptedLLM(LLMReply("Liguei a luz."))
    engine = make_engine(llm, store)
    stt = FakeSTT("liga a luz")
    slot = VoiceSlot(True)
    slot.assistant = VoiceAssistant(engine, stt, FakeTTS())

    await TelegramBot(api, engine, slot, ME).poll_once()

    assert stt.received == [b"ogg:abc"]
    assert api.sent == [(ME, "🎙️ “liga a luz”\n\nLiguei a luz.")]
    assert "por texto" in llm.calls[0][0].content


async def test_voice_note_while_voice_is_loading(store):
    api = FakeApi({"update_id": 1, "message": {"chat": {"id": ME}, "voice": {"file_id": "abc"}}})

    await TelegramBot(api, make_engine(ScriptedLLM(), store), VoiceSlot(True), ME).poll_once()

    assert "voz carregando" in api.sent[0][1]


# ------------------------------------------------------------------ cliente HTTP


async def test_client_splits_long_messages_and_reports_errors():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content)))
        if request.url.path.endswith("/getUpdates"):
            return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
        return httpx.Response(200, json={"ok": True, "result": True})

    client = TelegramClient("TOKEN", transport=httpx.MockTransport(handler))
    await TelegramNotifier(client, ME).send("a" * (MAX_MESSAGE + 10))

    assert [path for path, _ in seen] == ["/botTOKEN/sendMessage"] * 2
    assert len(seen[0][1]["text"]) == MAX_MESSAGE and seen[1][1]["chat_id"] == ME
    with pytest.raises(TelegramError, match="Unauthorized"):
        await client.get_updates(None)
    await client.aclose()


async def test_client_downloads_files():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "voice/f.oga"}})
        assert request.url.path == "/file/botTOKEN/voice/f.oga"
        return httpx.Response(200, content=b"OGG")

    client = TelegramClient("TOKEN", transport=httpx.MockTransport(handler))

    assert await client.download_file("x") == b"OGG"
