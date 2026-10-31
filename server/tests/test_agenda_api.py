from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from biony.adapters.sqlite_store import Database, SqliteConversationStore, SqliteReminderStore
from biony.api.app import create_app
from biony.core.reminder_service import ReminderService

from conftest import TZ, ScriptedLLM, make_engine
from test_reminders import POLICY, Clock, FakeScheduler, at

TOKEN = "t" * 32
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def setup():
    service = ReminderService(
        SqliteReminderStore(Database(":memory:")), FakeScheduler(), None, timezone=TZ, policy=POLICY, clock=Clock(at(1, 12))
    )
    engine = make_engine(ScriptedLLM([]), SqliteConversationStore(Database(":memory:")))
    return service, TestClient(create_app(engine, TOKEN, agenda=service))


def test_agenda_requires_token(setup):
    _, client = setup
    assert client.get("/agenda").status_code == 401
    assert client.post("/agenda/tarefas", json={"titulo": "x"}).status_code == 401


def test_create_list_and_complete_task(setup):
    service, client = setup
    created = client.post("/agenda/tarefas", headers=HEADERS, json={"titulo": "  Trabalho   de BD ", "prazo": "2026-11-15T14:00"})
    assert created.status_code == 201
    body = created.json()
    assert body["titulo"] == "Trabalho de BD" and body["prazo"] == "2026-11-15T14:00"
    assert body["prazo_texto"] == "domingo, 15/11 às 14:00" and len(body["avisos"]) >= 1

    listed = client.get("/agenda", headers=HEADERS).json()
    assert [t["id"] for t in listed["tarefas"]] == [body["id"]]

    assert client.post(f"/agenda/tarefas/{body['id']}/concluir", headers=HEADERS).status_code == 204
    assert client.get("/agenda", headers=HEADERS).json()["tarefas"] == []
    assert client.post(f"/agenda/tarefas/{body['id']}/concluir", headers=HEADERS).status_code == 404


def test_standalone_reminders_are_listed(setup):
    service, client = setup
    service.create_reminder("tomar água", at(1, 15))
    reminder = client.get("/agenda", headers=HEADERS).json()["lembretes"][0]
    assert reminder["texto"] == "tomar água" and reminder["quando_texto"].endswith("às 15:00")


@pytest.mark.parametrize("prazo", ["dia 15", "2026-10-01"])
def test_invalid_or_past_due_is_rejected(setup, prazo):
    _, client = setup
    assert client.post("/agenda/tarefas", headers=HEADERS, json={"titulo": "x", "prazo": prazo}).status_code == 422


def test_task_without_due_has_no_notices(setup):
    _, client = setup
    body = client.post("/agenda/tarefas", headers=HEADERS, json={"titulo": "Ler artigo"}).json()
    assert body["prazo"] is None and body["avisos"] == []
