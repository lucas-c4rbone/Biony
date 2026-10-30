from __future__ import annotations

from datetime import datetime

import pytest

from biony.adapters.sqlite_store import Database, SqliteMemoryStore, SqliteReminderStore
from biony.core.memory import memory_context
from biony.core.models import LLMReply, ToolCall
from biony.core.reminder_service import ReminderService
from biony.tools.memory import MemoryForgetTool, MemorySaveTool
from biony.tools.tasks import task_tools

from conftest import TZ, ScriptedLLM, make_engine
from test_reminders import POLICY, Clock, FakeScheduler, at

pytestmark = pytest.mark.anyio


@pytest.fixture
def tools():
    service = ReminderService(
        SqliteReminderStore(Database(":memory:")), FakeScheduler(), None, timezone=TZ, policy=POLICY, clock=Clock(at(1, 12))
    )
    return {tool.definition.name: tool for tool in task_tools(service)}


async def test_create_task_reports_notices(tools):
    result = await tools["tarefa_criar"].execute({"titulo": "Trabalho", "prazo": "2026-11-15", "observacoes": "dupla"})

    assert result.ok
    assert result.content == "Tarefa 1 salva: Trabalho (prazo domingo, 15/11; avisos: 12/11 09:00, 14/11 09:00, 15/11 09:00)."
    listing = (await tools["tarefas_listar"].execute({})).content
    assert "tarefa 1: Trabalho (prazo domingo, 15/11; avisos: 12/11 09:00" in listing and "— dupla" in listing


async def test_create_task_validation(tools):
    create = tools["tarefa_criar"]

    assert not (await create.execute({"titulo": " "})).ok
    assert "inválido" in (await create.execute({"titulo": "x", "prazo": "amanhã"})).content
    assert "já passou" in (await create.execute({"titulo": "x", "prazo": "2026-10-01"})).content
    assert not (await create.execute({"titulo": "x", "prazo": "2026-11-15", "avisar_dias_antes": [-1]})).ok
    assert "sem prazo" in (await create.execute({"titulo": "comprar filamento"})).content


async def test_custom_notice_days(tools):
    result = await tools["tarefa_criar"].execute({"titulo": "x", "prazo": "2026-11-15", "avisar_dias_antes": [7]})

    assert "avisos: 08/11 09:00" in result.content


async def test_reminder_create_and_quiet_note(tools):
    ok = await tools["lembrete_criar"].execute({"texto": "varal", "quando": "2026-11-01T18:00"})
    late = await tools["lembrete_criar"].execute({"texto": "remédio", "quando": "2026-11-01T23:00"})
    past = await tools["lembrete_criar"].execute({"texto": "x", "quando": "2026-11-01T08:00"})
    bad = await tools["lembrete_criar"].execute({"texto": "x", "quando": "às 18h"})

    assert ok.ok and "01/11 às 18:00" in ok.content and "silêncio" not in ok.content
    assert late.ok and "silêncio" in late.content
    assert not past.ok and not bad.ok
    assert "lembrete 1: varal (01/11 às 18:00)" in (await tools["tarefas_listar"].execute({})).content


async def test_complete_delete_and_cancel(tools):
    await tools["tarefa_criar"].execute({"titulo": "Prova", "prazo": "2026-11-15"})
    await tools["lembrete_criar"].execute({"texto": "varal", "quando": "2026-11-01T18:00"})

    assert tools["tarefa_apagar"].definition.requires_confirmation
    assert tools["lembrete_cancelar"].definition.requires_confirmation
    assert tools["tarefa_apagar"].describe({"id": 1}) == "apagar a tarefa 'Prova'"
    assert tools["lembrete_cancelar"].describe({"id": 4}) == "cancelar o lembrete 'varal' de 01/11 às 18:00"

    assert (await tools["tarefa_concluir"].execute({"id": 1})).ok
    assert not (await tools["tarefa_concluir"].execute({"id": 1})).ok
    assert (await tools["lembrete_cancelar"].execute({"id": 4})).ok
    assert (await tools["tarefas_listar"].execute({})).content.startswith("Nenhuma tarefa")


async def test_memory_tools_and_context():
    store = SqliteMemoryStore(Database(":memory:"))
    save, forget = MemorySaveTool(store), MemoryForgetTool(store)

    assert (await save.execute({"fato": "  Faz Cálculo 2   às terças "})).content == "Memória 1 guardada: Faz Cálculo 2 às terças"
    assert not (await save.execute({"fato": "x" * 600})).ok
    assert forget.definition.requires_confirmation
    assert forget.describe({"id": 1}) == 'esquecer que "Faz Cálculo 2 às terças"'
    assert "[1] Faz Cálculo 2 às terças" in memory_context(store.all())

    assert (await forget.execute({"id": 1})).ok
    assert store.all() == []
    assert "nenhuma memória" in memory_context([])


async def test_memories_go_into_the_system_prompt(store):
    memories = SqliteMemoryStore(Database(":memory:"))
    memories.add("Gosta de luz roxa")
    llm = ScriptedLLM(LLMReply("ok"))
    engine = make_engine(llm, store)
    engine._extra_context = lambda: memory_context(memories.all())

    await engine.handle("oi", "s1")

    assert "[1] Gosta de luz roxa" in llm.calls[0][0].content


async def test_forget_needs_confirmation_through_engine(store):
    memories = SqliteMemoryStore(Database(":memory:"))
    memories.add("Mora em Campinas")
    llm = ScriptedLLM(LLMReply(tool_calls=(ToolCall("c1", "memoria_esquecer", {"id": 1}),)), LLMReply("Esqueci."))
    engine = make_engine(llm, store, MemoryForgetTool(memories))

    ask = await engine.handle("esquece onde eu moro", "s1")
    assert ask.awaiting_confirmation and 'esquecer que "Mora em Campinas"' in ask.text
    assert len(memories.all()) == 1

    await engine.handle("sim", "s1")
    assert memories.all() == []
