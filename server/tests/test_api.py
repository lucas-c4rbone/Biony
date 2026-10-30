from __future__ import annotations

from fastapi.testclient import TestClient

from biony.api.app import create_app
from biony.core.models import LLMReply
from biony.core.ports import LLMError

from conftest import ScriptedLLM, make_engine

TOKEN = "t" * 32


class FailingLLM:
    async def chat(self, messages, tools):
        raise LLMError("fora do ar")


def client_for(llm, store) -> TestClient:
    return TestClient(create_app(make_engine(llm, store), TOKEN))


def test_health_is_public(store):
    assert client_for(ScriptedLLM(), store).get("/health").json() == {"status": "ok", "voz": "desativada"}


def test_texto_requires_token(store):
    client = client_for(ScriptedLLM(), store)

    assert client.post("/texto", json={"texto": "oi"}).status_code == 401
    wrong = client.post("/texto", json={"texto": "oi"}, headers={"Authorization": "Bearer errado"})
    assert wrong.status_code == 401


def test_texto_answers_and_keeps_session(store):
    client = client_for(ScriptedLLM(LLMReply("Opa!"), LLMReply("De novo?")), store)
    auth = {"Authorization": f"Bearer {TOKEN}"}

    first = client.post("/texto", json={"texto": "oi"}, headers=auth).json()
    second = client.post("/texto", json={"texto": "oi", "sessao": first["sessao"]}, headers=auth).json()

    assert first["resposta"] == "Opa!"
    assert first["aguardando_confirmacao"] is False
    assert second["sessao"] == first["sessao"]


def test_llm_failure_becomes_502(store):
    client = client_for(FailingLLM(), store)

    response = client.post("/texto", json={"texto": "oi"}, headers={"Authorization": f"Bearer {TOKEN}"})

    assert response.status_code == 502
    assert "fora do ar" in response.json()["detail"]
