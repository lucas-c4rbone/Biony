from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import threading
import urllib.error
import urllib.request

import httpx
import pytest

from biony.adapters.pc_agent import PcAgentClient
from biony.tools.home import HomeController
from biony.tools.home_config import parse_home_config
from biony.tools.pc import PcAgentError, PcController, PcOffTool, pc_tools

from test_home import FakeHA

pytestmark = pytest.mark.anyio

CONFIG = {"dispositivos": {"setup": {"nome": "setup", "entidade": "switch.filtro", "confirmar_desligar": True}}}


class FakeAgent:
    """Responde a `status` com a sequência dada (None = PC não respondeu); repete o último."""

    def __init__(self, *states) -> None:
        self.states = list(states)
        self.shutdowns: list[int] = []

    async def status(self):
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        if isinstance(state, Exception):
            raise state
        return state

    async def shutdown(self, seconds: int) -> None:
        self.shutdowns.append(seconds)


class Inbox:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> None:
        self.messages.append(text)


def make_pc(agent, presumed, ha=None, warn=30):
    ha = ha or FakeHA()
    home = HomeController(ha, parse_home_config(CONFIG), presumed)
    inbox = Inbox()
    pc = PcController(agent, home, "setup", inbox, warn_seconds=warn, poll_interval=0.01, timeout=0.5, settle=0.01, misses_to_off=3)
    return pc, ha, inbox


async def finish(pc: PcController) -> None:
    await asyncio.wait_for(pc._watcher, 2)


@pytest.fixture
def presumed():
    from biony.adapters.sqlite_store import Database, SqlitePresumedStateStore

    return SqlitePresumedStateStore(Database(":memory:"))


async def test_turn_off_waits_for_pc_to_go_dark_before_cutting(presumed):
    ON = {"online": True}
    agent = FakeAgent(ON, ON, ON, None, ON, None, None, None)  # um "soluço" no meio não conta
    pc, ha, inbox = make_pc(agent, presumed)

    result = await pc.turn_off()
    assert result.ok and agent.shutdowns == [30] and ha.calls == []  # não corta na hora
    await finish(pc)

    assert ha.calls == [("switch", "turn_off", {"entity_id": "switch.filtro"})]
    assert inbox.messages == ["🔌 PC desligado e filtro cortado."]


async def test_pc_that_never_turns_off_keeps_power(presumed):
    agent = FakeAgent({"online": True})
    pc, ha, inbox = make_pc(agent, presumed, warn=0)  # o prazo inclui o aviso na tela

    await pc.turn_off()
    await finish(pc)

    assert ha.calls == []
    assert "Deixei o filtro ligado" in inbox.messages[0]


async def test_turn_off_when_pc_already_off_does_not_cut(presumed):
    agent = FakeAgent(None)
    pc, ha, _ = make_pc(agent, presumed)

    result = await pc.turn_off()

    assert not result.ok and "Não cortei" in result.content
    assert agent.shutdowns == [] and ha.calls == []


async def test_agent_errors_are_reported(presumed):
    class Broken(FakeAgent):
        async def shutdown(self, seconds):
            raise PcAgentError("o agente do PC recusou: x")

    pc, ha, _ = make_pc(Broken({"online": True}), presumed)

    result = await pc.turn_off()

    assert not result.ok and "recusou" in result.content and ha.calls == []


async def test_turn_on_powers_setup_and_announces_online(presumed):
    agent = FakeAgent(None, None, None, {"online": True})
    pc, ha, inbox = make_pc(agent, presumed)

    result = await pc.turn_on()
    await finish(pc)

    assert result.ok
    assert ha.calls == [("switch", "turn_on", {"entity_id": "switch.filtro"})]
    assert inbox.messages == ["💻 Seu PC está online. Pode conectar pelo Moonlight."]


async def test_turn_on_when_already_on_and_bios_warning(presumed):
    pc, ha, _ = make_pc(FakeAgent({"online": True}), presumed)
    assert (await pc.turn_on()).content == "O PC já está ligado." and ha.calls == []

    pc, ha, inbox = make_pc(FakeAgent(None), presumed)
    await pc.turn_on()
    await finish(pc)
    assert "BIOS" in inbox.messages[0]


async def test_status_and_tools(presumed):
    pc, _, _ = make_pc(FakeAgent({"online": True, "usuario_logado": False}), presumed)

    assert "tela de bloqueio" in (await pc.status()).content
    names = [tool.definition.name for tool in pc_tools(pc)]
    assert names == ["pc_ligar", "pc_desligar", "pc_status"]
    assert PcOffTool(pc).definition.requires_confirmation


# ------------------------------------------------------------------ cliente HTTP


async def test_client_maps_responses():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tok"
        if request.url.path == "/status":
            return httpx.Response(200, json={"online": True})
        assert json.loads(request.content) == {"segundos": 30}
        return httpx.Response(200, json={"ok": True})

    client = PcAgentClient(base_url="http://pc:8421", token="tok", transport=httpx.MockTransport(handler))
    assert await client.status() == {"online": True}
    await client.shutdown(30)

    offline = PcAgentClient(base_url="http://pc:8421", token="tok",
                            transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("x"))))
    assert await offline.status() is None
    with pytest.raises(PcAgentError):
        await offline.shutdown(30)

    refused = PcAgentClient(base_url="http://pc:8421", token="x", transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(PcAgentError, match="token"):
        await refused.status()


# ------------------------------------------------------------------ o agente do Windows


def load_agent():
    path = Path(__file__).resolve().parents[2] / "clients" / "pc-agente" / "biony_agente.py"
    spec = importlib.util.spec_from_file_location("biony_agente", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_agent_http_api(monkeypatch):
    agent = load_agent()
    commands: list[tuple] = []

    class Done:
        returncode, stdout, stderr = 0, "", ""

    monkeypatch.setattr(agent, "run", lambda *cmd: commands.append(cmd) or Done())  # NUNCA desliga de verdade
    agent.Handler.token = "t" * 32
    server = agent.ThreadingHTTPServer(("127.0.0.1", 0), agent.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(method, path, body=None, token="t" * 32):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(base + path, data=data, method=method, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    try:
        assert call("GET", "/status", token="errado")[0] == 401
        assert call("GET", "/status") == (200, {"online": True, "usuario_logado": True})
        assert call("POST", "/desligar", {"segundos": 5})[0] == 400  # fora da faixa permitida
        assert call("POST", "/desligar", {"segundos": "rm -rf"})[0] == 400
        assert call("POST", "/desligar", {"segundos": 30}) == (200, {"ok": True, "segundos": 30})
        assert call("POST", "/cancelar", {}) == (200, {"ok": True})
        assert call("POST", "/qualquer-coisa", {})[0] == 404
    finally:
        server.shutdown()

    assert commands[0] == ("query", "user")
    assert commands[1][:4] == ("shutdown", "/s", "/t", "30")
    assert commands[2] == ("shutdown", "/a")


ROUTINES = {
    "dispositivos": {
        "setup": {"nome": "setup", "entidade": "switch.filtro", "confirmar_desligar": True},
        "fita": {"nome": "fita", "entidade": "light.fita"},
    },
    "rotinas": {
        "cheguei": {"descricao": "chegou", "passos": [{"pc": "ligar"}, {"dispositivo": "fita", "acao": "ligar"}]},
        "dormir": {"descricao": "boa noite", "passos": [{"pc": "desligar"}, {"dispositivo": "fita", "acao": "desligar"}]},
    },
}


def routine_home(agent, presumed):
    from biony.tools.home import HomeRoutineTool

    ha = FakeHA()
    home = HomeController(ha, parse_home_config(ROUTINES), presumed)
    pc = PcController(agent, home, "setup", Inbox(), poll_interval=0.01, timeout=0.5, settle=0.01)
    home.pc = pc
    return home, pc, ha, HomeRoutineTool(home)


async def test_routine_turns_pc_on_and_off(presumed):
    home, pc, ha, tool = routine_home(FakeAgent(None, None, {"online": True}), presumed)

    on = await home.run_routine("cheguei")
    await finish(pc)
    assert on.ok
    assert ha.calls[:2] == [("switch", "turn_on", {"entity_id": "switch.filtro"}), ("light", "turn_on", {"entity_id": "light.fita"})]

    assert tool.needs_confirmation({"rotina": "dormir"})
    assert not tool.needs_confirmation({"rotina": "cheguei"})


async def test_goodnight_with_pc_already_off_is_fine(presumed):
    agent = FakeAgent(None)
    home, _, ha, _ = routine_home(agent, presumed)

    result = await home.run_routine("dormir")

    assert result.ok and "já estava desligado" in result.content
    assert agent.shutdowns == [] and ha.calls == [("light", "turn_off", {"entity_id": "light.fita"})]


async def test_routine_pc_step_without_agent(presumed):
    from biony.tools.home_config import HomeConfigError

    home = HomeController(FakeHA(), parse_home_config(ROUTINES), presumed)
    result = await home.run_routine("cheguei")
    assert not result.ok and "agente do PC" in result.content
    with pytest.raises(HomeConfigError, match="pc"):
        parse_home_config({"rotinas": {"x": {"descricao": "x", "passos": [{"pc": "reiniciar"}]}}})
