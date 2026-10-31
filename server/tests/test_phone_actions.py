from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from biony.api.app import create_app
from biony.core.models import LLMReply, ToolCall
from biony.core.tools import client_capabilities
from biony.tools.phone import CAPABILITY, PhoneActionTool

from conftest import ScriptedLLM, make_engine

pytestmark = pytest.mark.anyio

TOKEN = "t" * 32
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def call(**arguments) -> LLMReply:
    return LLMReply(tool_calls=(ToolCall("c1", "celular_acao", arguments),))


async def run(arguments, capable=True):
    token = client_capabilities.set(frozenset({CAPABILITY}) if capable else frozenset())
    try:
        return await PhoneActionTool().execute(arguments)
    finally:
        client_capabilities.reset(token)


async def test_alarm_becomes_a_client_action():
    result = await run({"acao": "despertador", "hora": 17, "dias": ["sex", "seg", "seg"], "mensagem": "  Aula   de BD "})
    assert result.ok and "17:00" in result.content
    assert result.client_actions == (
        {"tipo": "despertador", "hora": 17, "minuto": 0, "dias": ["seg", "sex"], "mensagem": "Aula de BD"},
    )


async def test_timer_flashlight_and_open_app():
    assert (await run({"acao": "timer", "segundos": 300})).client_actions == (
        {"tipo": "timer", "segundos": 300, "mensagem": ""},
    )
    assert (await run({"acao": "lanterna", "ligar": False})).client_actions == ({"tipo": "lanterna", "ligar": False},)
    assert (await run({"acao": "abrir_app", "app": " WhatsApp "})).client_actions == ({"tipo": "abrir_app", "app": "WhatsApp"},)


@pytest.mark.parametrize(
    "arguments",
    [
        {"acao": "despertador"},
        {"acao": "despertador", "hora": 24},
        {"acao": "despertador", "hora": 7, "minuto": 60},
        {"acao": "despertador", "hora": 7, "dias": ["domingao"]},
        {"acao": "despertador", "hora": True},
        {"acao": "timer", "segundos": 0},
        {"acao": "timer", "segundos": 999_999},
        {"acao": "lanterna"},
        {"acao": "lanterna", "ligar": "sim"},
        {"acao": "abrir_app", "app": "  "},
        {"acao": "formatar"},
    ],
)
async def test_invalid_requests_are_refused_without_actions(arguments):
    result = await run(arguments)
    assert not result.ok and result.client_actions == ()


async def test_refuses_when_the_client_cannot_run_phone_actions():
    result = await run({"acao": "despertador", "hora": 17}, capable=False)
    assert not result.ok and "não controla o celular" in result.content and result.client_actions == ()


async def test_engine_returns_actions_only_to_capable_clients(store):
    llm = ScriptedLLM(call(acao="despertador", hora=17), LLMReply("Pronto, 17h."))
    engine = make_engine(llm, store, PhoneActionTool())
    reply = await engine.handle("põe um despertador às 17h", "s1", capabilities=frozenset({CAPABILITY}))
    assert reply.client_actions == ({"tipo": "despertador", "hora": 17, "minuto": 0, "dias": [], "mensagem": ""},)

    llm = ScriptedLLM(call(acao="despertador", hora=17), LLMReply("Não consigo daqui."))
    engine = make_engine(llm, store, PhoneActionTool())
    reply = await engine.handle("põe um despertador às 17h", "s2")
    assert reply.client_actions == ()
    assert "não controla o celular" in llm.calls[1][-1].content
    assert client_capabilities.get() == frozenset()  # não vaza para a próxima mensagem


def test_api_sends_actions_when_the_client_declares_the_capability(store):
    def client(*replies):
        engine = make_engine(ScriptedLLM(*replies), store, PhoneActionTool())
        return TestClient(create_app(engine, TOKEN))

    body = {"texto": "timer de 5 minutos", "sessao": "a"}
    script = (call(acao="timer", segundos=300), LLMReply("Timer de 5 minutos."))

    capable = client(*script).post("/texto", headers=HEADERS, json={**body, "capacidades": [CAPABILITY]}).json()
    assert capable["acoes"] == [{"tipo": "timer", "segundos": 300, "mensagem": ""}]

    plain = client(*script).post("/texto", headers=HEADERS, json={**body, "sessao": "b"}).json()
    assert plain["acoes"] == []
