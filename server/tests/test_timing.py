"""Os tempos de cada etapa vão para o log (é como a gente descobre onde está o atraso)."""

from __future__ import annotations

import logging

import pytest

from biony.core.models import LLMReply, ToolCall
from biony.core.voice import VoiceAssistant

from conftest import RecordingTool, ScriptedLLM, make_engine

pytestmark = pytest.mark.anyio


class FakeSTT:
    async def transcribe(self, audio: bytes) -> str:
        return "liga a luz"


class FakeTTS:
    async def synthesize(self, text: str) -> bytes:
        return b"RIFF"


async def test_conversation_logs_llm_tools_and_total(store, caplog):
    llm = ScriptedLLM(LLMReply(tool_calls=(ToolCall("c1", "luz", {}),)), LLMReply("pronto"))
    with caplog.at_level(logging.INFO, logger="biony.core.conversation"):
        await make_engine(llm, store, RecordingTool("luz")).handle("liga", "s1")
    line = next(r.getMessage() for r in caplog.records if "Tempos da conversa" in r.getMessage())
    assert "(2 chamada(s))" in line and "ferramentas" in line and "total" in line  # uma para decidir, outra para responder


async def test_voice_logs_transcription_conversation_and_speech(store, caplog):
    engine = make_engine(ScriptedLLM(LLMReply("oi")), store)
    with caplog.at_level(logging.INFO, logger="biony.core.voice"):
        await VoiceAssistant(engine, FakeSTT(), FakeTTS()).handle(b"audio", "s1")
    line = next(r.getMessage() for r in caplog.records if "Tempos da voz" in r.getMessage())
    assert "transcrição" in line and "conversa" in line and "fala" in line and "total" in line
