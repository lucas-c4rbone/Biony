from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from biony.adapters.sqlite_store import Database, SqliteLoginTokenStore
from biony.api.app import create_app
from biony.api.auth import LOCK_SECONDS, MAX_FAILURES, Auth, LoginLocked
from biony.core.models import LLMReply, ToolCall

from conftest import RecordingTool, ScriptedLLM, make_engine

MASTER = "m" * 32
PASSWORD = "senha-forte-123"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_auth(clock=None, password=PASSWORD) -> Auth:
    return Auth(MASTER, SqliteLoginTokenStore(Database(":memory:")), password, clock or Clock())


def test_master_token_and_login_tokens():
    auth = make_auth()

    token = auth.login(PASSWORD, "celular")

    assert auth.check(MASTER) and auth.check(token)
    assert not auth.check("qualquer")
    auth.logout(token)
    assert not auth.check(token)
    assert auth.check(MASTER)


def test_wrong_password_locks_after_several_tries():
    clock = Clock()
    auth = make_auth(clock)

    for _ in range(MAX_FAILURES):
        assert auth.login("errada", "x") is None
    with pytest.raises(LoginLocked):
        auth.login(PASSWORD, "x")  # nem a certa entra durante o bloqueio

    clock.now += LOCK_SECONDS + 1
    assert auth.login(PASSWORD, "x") is not None


def test_login_disabled_without_password():
    assert not make_auth(password=None).login_enabled


def client(store, llm=None, auth=None, tools=()) -> TestClient:
    engine = make_engine(llm or ScriptedLLM(LLMReply("Opa!")), store, *tools)
    return TestClient(create_app(engine, auth or make_auth()))


def test_login_flow_over_http(store):
    api = client(store)

    assert api.post("/login", json={"senha": "errada"}).status_code == 401
    token = api.post("/login", json={"senha": PASSWORD, "aparelho": "celular"}).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}

    assert api.post("/texto", json={"texto": "oi"}, headers=auth).json()["resposta"] == "Opa!"
    assert api.post("/logout", headers=auth).status_code == 204
    assert api.post("/texto", json={"texto": "oi"}, headers=auth).status_code == 401


def test_login_lock_and_disabled_over_http(store):
    api = client(store)
    for _ in range(MAX_FAILURES):
        api.post("/login", json={"senha": "errada"})
    assert api.post("/login", json={"senha": PASSWORD}).status_code == 429

    assert client(store, auth=make_auth(password=None)).post("/login", json={"senha": "x"}).status_code == 503


def test_history_shows_only_user_and_biony(store):
    llm = ScriptedLLM(LLMReply(tool_calls=(ToolCall("c1", "luz", {}),)), LLMReply("Liguei."))
    api = client(store, llm=llm, tools=[RecordingTool("luz")])
    headers = {"Authorization": f"Bearer {MASTER}"}

    api.post("/texto", json={"texto": "liga a luz", "sessao": "pwa-1"}, headers=headers)
    history = api.get("/sessoes/pwa-1/mensagens", headers=headers).json()

    assert history == {
        "sessao": "pwa-1",
        "mensagens": [{"papel": "usuario", "texto": "liga a luz"}, {"papel": "biony", "texto": "Liguei."}],
    }
    assert api.get("/sessoes/pwa-1/mensagens").status_code == 401


def test_pwa_files_are_served_and_api_wins(store):
    api = client(store)

    page = api.get("/")
    assert page.status_code == 200 and "<title>Biony</title>" in page.text
    for path in ("/app.js", "/style.css", "/sw.js", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png"):
        assert api.get(path).status_code == 200, path
    assert api.get("/health").json()["status"] == "ok"
