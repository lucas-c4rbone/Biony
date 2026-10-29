from __future__ import annotations

import pytest

from biony.core.conversation import AWAITING_RESULT
from biony.core.models import LLMReply, Role, ToolCall

from conftest import RecordingTool, ScriptedLLM, make_engine

pytestmark = pytest.mark.anyio


def roles(messages):
    return [message.role for message in messages]


async def test_plain_reply_is_saved_and_history_is_sent_back(store):
    llm = ScriptedLLM(LLMReply("Opa, Lucas!"), LLMReply("Você disse oi."))
    engine = make_engine(llm, store)

    first = await engine.handle("oi", "s1")
    await engine.handle("o que eu disse?", "s1")

    assert first.text == "Opa, Lucas!"
    assert not first.awaiting_confirmation
    second_context = llm.calls[1]
    assert second_context[0].role is Role.SYSTEM
    assert "quinta-feira, 29/10/2026 15:42" in second_context[0].content
    assert [m.content for m in second_context[1:]] == ["oi", "Opa, Lucas!", "o que eu disse?"]


async def test_sessions_are_isolated(store):
    llm = ScriptedLLM(LLMReply("a"), LLMReply("b"))
    engine = make_engine(llm, store)

    await engine.handle("primeira", "s1")
    await engine.handle("segunda", "s2")

    assert [m.content for m in llm.calls[1][1:]] == ["segunda"]


async def test_new_session_id_is_generated(store):
    engine = make_engine(ScriptedLLM(LLMReply("ok")), store)

    reply = await engine.handle("oi")

    assert reply.session_id


async def test_tool_loop_runs_several_calls_then_answers(store):
    light, ac = RecordingTool("luz"), RecordingTool("ar")
    llm = ScriptedLLM(
        LLMReply(tool_calls=(ToolCall("c1", "luz", {"on": True}), ToolCall("c2", "ar", {}))),
        LLMReply("Pronto, liguei tudo."),
    )
    engine = make_engine(llm, store, light, ac)

    reply = await engine.handle("cheguei", "s1")

    assert reply.text == "Pronto, liguei tudo."
    assert light.executions == [{"on": True}] and ac.executions == [{}]
    last_context = llm.calls[1]
    assert roles(last_context[1:]) == [Role.USER, Role.ASSISTANT, Role.TOOL, Role.TOOL]
    assert [m.tool_call_id for m in last_context[3:]] == ["c1", "c2"]
    assert last_context[3].content == "luz feito"


async def test_tool_errors_are_reported_to_the_llm(store):
    llm = ScriptedLLM(
        LLMReply(
            tool_calls=(
                ToolCall("c1", "nao_existe", {}),
                ToolCall("c2", "quebrada", {}),
                ToolCall("c3", "luz", {}, arguments_error="JSON inválido"),
            )
        ),
        LLMReply("Deu ruim."),
    )
    engine = make_engine(llm, store, RecordingTool("quebrada", fail=True), RecordingTool("luz"))

    await engine.handle("faz", "s1")

    results = [m.content for m in llm.calls[1] if m.role is Role.TOOL]
    assert "desconhecida" in results[0]
    assert "quebrou" in results[1]
    assert "Argumentos inválidos" in results[2]


async def test_tool_round_limit(store):
    call = LLMReply(tool_calls=(ToolCall("c", "luz", {}),))
    engine = make_engine(ScriptedLLM(call, call), store, RecordingTool("luz"), max_tool_rounds=2)

    reply = await engine.handle("loop", "s1")

    assert "enrolei" in reply.text


async def test_confirmation_yes_executes(store):
    shutdown = RecordingTool("desligar_pc", requires_confirmation=True)
    llm = ScriptedLLM(
        LLMReply(tool_calls=(ToolCall("c1", "desligar_pc", {}),)),
        LLMReply("Desliguei o PC."),
    )
    engine = make_engine(llm, store, shutdown)

    ask = await engine.handle("desliga o pc", "s1")
    assert ask.awaiting_confirmation
    assert "Confirma?" in ask.text
    assert shutdown.executions == []

    done = await engine.handle("sim, pode", "s1")

    assert done.text == "Desliguei o PC."
    assert shutdown.executions == [{}]
    context = llm.calls[1]
    assert roles(context[1:]) == [
        Role.USER, Role.ASSISTANT, Role.TOOL, Role.ASSISTANT,  # pedido e "Confirma?"
        Role.USER, Role.ASSISTANT, Role.TOOL,                  # "sim" e execução
    ]
    assert context[3].content == AWAITING_RESULT
    assert context[7].tool_call_id == "c1-ok" and context[7].content == "desligar_pc feito"


async def test_confirmation_no_cancels_without_calling_llm(store):
    shutdown = RecordingTool("desligar_pc", requires_confirmation=True)
    llm = ScriptedLLM(LLMReply(tool_calls=(ToolCall("c1", "desligar_pc", {}),)))
    engine = make_engine(llm, store, shutdown)

    await engine.handle("desliga o pc", "s1")
    reply = await engine.handle("não, deixa", "s1")

    assert reply.text == "Beleza, cancelei."
    assert shutdown.executions == []
    assert len(llm.calls) == 1


async def test_unclear_answer_drops_action_and_handles_new_request(store):
    shutdown = RecordingTool("desligar_pc", requires_confirmation=True)
    llm = ScriptedLLM(
        LLMReply(tool_calls=(ToolCall("c1", "desligar_pc", {}),)),
        LLMReply("São 15:42."),
        LLMReply("Sim o quê?"),
    )
    engine = make_engine(llm, store, shutdown)

    await engine.handle("desliga o pc", "s1")
    reply = await engine.handle("que horas são?", "s1")
    # A ação já foi descartada: um "sim" atrasado não pode executá-la.
    await engine.handle("sim", "s1")

    assert reply.text == "São 15:42."
    assert shutdown.executions == []


async def test_safe_calls_in_same_turn_run_while_risky_one_waits(store):
    light = RecordingTool("luz")
    shutdown = RecordingTool("desligar_pc", requires_confirmation=True)
    llm = ScriptedLLM(LLMReply(tool_calls=(ToolCall("c1", "luz", {}), ToolCall("c2", "desligar_pc", {}))))
    engine = make_engine(llm, store, light, shutdown)

    reply = await engine.handle("apaga tudo", "s1")

    assert reply.awaiting_confirmation
    assert light.executions == [{}] and shutdown.executions == []


async def test_history_window_never_starts_with_orphan_tool_result(store):
    llm = ScriptedLLM(
        LLMReply(tool_calls=(ToolCall("c1", "luz", {}),)),
        LLMReply("feito"),
        LLMReply("ok"),
    )
    # 4 mensagens no primeiro turno; com limite 4 o segundo turno corta no meio dele.
    engine = make_engine(llm, store, RecordingTool("luz"), history_limit=4)

    await engine.handle("liga", "s1")
    await engine.handle("valeu", "s1")

    assert roles(llm.calls[2][1:]) == [Role.USER]
