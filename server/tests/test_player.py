from __future__ import annotations

from pathlib import Path

import pytest

from biony.adapters.sqlite_store import Database, SqlitePresumedStateStore
from biony.tools.home import HomeAssistantError, HomeController, home_tools
from biony.tools.home_config import HomeConfigError, load_home_config, parse_home_config
from biony.tools.player import PlayerTool

from test_home import FakeHA

pytestmark = pytest.mark.anyio

ENTITY = "media_player.fire"
CONFIG = {
    "players": {
        "firetv": {
            "nome": "Fire Stick",
            "entidade": ENTITY,
            "observacao": "volume é o da TV",
            "apps": {"Netflix": "com.netflix.ninja", "YouTube": "com.amazon.firetv.youtube"},
        }
    }
}


def tool(ha: FakeHA) -> PlayerTool:
    return PlayerTool(ha, parse_home_config(CONFIG).players)


def online(state: str = "paused", source: str = "com.netflix.ninja") -> FakeHA:
    return FakeHA({ENTITY: {"state": state, "attributes": {"source": source}}})


def test_repo_config_has_the_fire_stick():
    config = load_home_config(Path(__file__).resolve().parents[2] / "config" / "casa.toml")
    assert config.players["firetv"].entity.startswith("media_player.")


@pytest.mark.parametrize(
    "broken, message",
    [
        ({"entidade": "light.fita"}, "media_player"),
        ({"apps": {"Netflix": ""}}, "apps"),
        ({"apps": ["com.netflix.ninja"]}, "apps"),
        ({"nome": ""}, "nome"),
    ],
)
def test_invalid_player_config(broken, message):
    raw = {**CONFIG["players"]["firetv"], **broken}
    with pytest.raises(HomeConfigError, match=message):
        parse_home_config({"players": {"firetv": raw}})


@pytest.mark.parametrize(
    "action, service",
    [
        ("pausar", "media_pause"),
        ("continuar", "media_play"),
        ("proxima", "media_next_track"),
        ("anterior", "media_previous_track"),
        ("parar", "media_stop"),
        ("ligar", "turn_on"),
        ("desligar", "turn_off"),
    ],
)
async def test_actions_call_the_matching_service(action, service):
    ha = online()
    result = await tool(ha).execute({"player": "firetv", "acao": action})
    assert result.ok
    assert ha.calls == [("media_player", service, {"entity_id": ENTITY})]


async def test_open_app_uses_the_configured_package():
    ha = online()
    result = await tool(ha).execute({"player": "firetv", "acao": "abrir_app", "app": "YouTube"})
    assert result.ok and "YouTube" in result.content
    assert ha.calls == [("media_player", "select_source", {"entity_id": ENTITY, "source": "com.amazon.firetv.youtube"})]


@pytest.mark.parametrize(
    "arguments",
    [
        {"player": "firetv", "acao": "abrir_app", "app": "Disney"},   # app que não está na lista
        {"player": "firetv", "acao": "abrir_app"},                    # sem app
        {"player": "firetv", "acao": "formatar"},                     # ação fora da lista
        {"player": "outro", "acao": "pausar"},                        # player que não existe
    ],
)
async def test_unknown_requests_never_reach_home_assistant(arguments):
    ha = online()
    result = await tool(ha).execute(arguments)
    assert not result.ok and ha.calls == []


async def test_unavailable_player_is_reported_not_sent():
    ha = online("unavailable")
    result = await tool(ha).execute({"player": "firetv", "acao": "pausar"})
    assert not result.ok and "indisponível" in result.content and ha.calls == []


async def test_home_assistant_failure_becomes_a_result():
    result = await tool(FakeHA(fail=True)).execute({"player": "firetv", "acao": "pausar"})
    assert not result.ok and "fora do ar" in result.content


def test_schema_lists_players_and_apps_and_warns_not_to_use_mute():
    definition = tool(online()).definition
    props = definition.parameters["properties"]
    assert props["player"]["enum"] == ["firetv"]
    assert props["app"]["enum"] == ["Netflix", "YouTube"]
    assert "volume é o da TV" in props["player"]["description"]
    assert "nunca o mudo" in definition.description


async def test_status_names_the_app_and_falls_back_to_the_package():
    presumed = SqlitePresumedStateStore(Database(":memory:"))

    async def status(ha):
        return (await HomeController(ha, parse_home_config(CONFIG), presumed).status()).content

    assert await status(online("playing", "com.netflix.ninja")) == "Fire Stick: tocando, no app Netflix"
    assert await status(online("paused", "com.desconhecido")) == "Fire Stick: pausado, no app com.desconhecido"
    assert await status(online("standby", "com.netflix.ninja")) == "Fire Stick: em repouso, no app Netflix"
    assert await status(online("unavailable", "x")) == "Fire Stick: indisponível"


def test_player_tool_exists_only_when_a_player_is_configured():
    presumed = SqlitePresumedStateStore(Database(":memory:"))
    with_player = HomeController(online(), parse_home_config({**CONFIG, "dispositivos": {}}), presumed)
    assert "player_controlar" in [t.definition.name for t in home_tools(with_player)]
    without = HomeController(online(), parse_home_config({"dispositivos": {}}), presumed)
    assert "player_controlar" not in [t.definition.name for t in home_tools(without)]
