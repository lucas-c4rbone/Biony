from __future__ import annotations

from pathlib import Path

import pytest

from biony.adapters.tuya_cloud import TuyaCloud, TuyaIrBlaster
from biony.tools.home_config import HomeConfigError, load_home_config, parse_home_config
from biony.tools.ir_remote import IrSendError, RemotePressTool

pytestmark = pytest.mark.anyio

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config" / "casa.toml"

CONFIG = {
    "controles": {
        "tv": {
            "nome": "TV",
            "infravermelho": "IR1",
            "controle": "RC1",
            "categoria": 2,
            "observacao": "mesmo botão liga e desliga",
            "botoes": {
                "ligar_desligar": {"tecla": "Power", "id": 1},
                "aumentar_volume": {"tecla": "Volume+", "id": 50},
            },
        }
    }
}


class FakeBlaster:
    def __init__(self, fail_after: int | None = None) -> None:
        self.pressed = []
        self.fail_after = fail_after

    async def press(self, remote, button) -> None:
        if self.fail_after is not None and len(self.pressed) >= self.fail_after:
            raise IrSendError("Tuya fora do ar")
        self.pressed.append((remote.remote_id, button.key))


async def no_sleep(_: float) -> None:
    pass


def tool(blaster) -> RemotePressTool:
    return RemotePressTool(blaster, parse_home_config(CONFIG).remotes, sleep=no_sleep)


def test_repo_config_has_the_tv():
    remotes = load_home_config(REPO_CONFIG).remotes
    assert {"ligar_desligar", "aumentar_volume", "abaixar_volume"} <= set(remotes["tv"].buttons)


def test_schema_lists_buttons_and_note():
    definition = tool(FakeBlaster()).definition
    props = definition.parameters["properties"]
    assert props["controle"]["enum"] == ["tv"]
    assert "ligar_desligar" in props["botao"]["enum"]
    assert "mesmo botão liga e desliga" in props["controle"]["description"]


async def test_presses_once_or_many_times():
    blaster = FakeBlaster()
    result = await tool(blaster).execute({"controle": "tv", "botao": "ligar_desligar"})
    assert result.ok and blaster.pressed == [("RC1", "Power")]
    result = await tool(blaster).execute({"controle": "tv", "botao": "aumentar_volume", "vezes": 3})
    assert result.ok and "3 vezes" in result.content
    assert blaster.pressed[1:] == [("RC1", "Volume+")] * 3


@pytest.mark.parametrize(
    "arguments",
    [
        {"controle": "som", "botao": "ligar_desligar"},
        {"controle": "tv", "botao": "netflix"},
        {"controle": "tv", "botao": "aumentar_volume", "vezes": 0},
        {"controle": "tv", "botao": "aumentar_volume", "vezes": 99},
    ],
)
async def test_invalid_arguments(arguments):
    blaster = FakeBlaster()
    assert not (await tool(blaster).execute(arguments)).ok
    assert blaster.pressed == []


async def test_failure_reports_how_many_presses_went_through():
    result = await tool(FakeBlaster(fail_after=2)).execute({"controle": "tv", "botao": "aumentar_volume", "vezes": 5})
    assert not result.ok and "2 de 5" in result.content and "fora do ar" in result.content


@pytest.mark.parametrize(
    "broken, message",
    [
        ({"categoria": "2"}, "categoria"),
        ({"botoes": {}}, "botoes"),
        ({"botoes": {"x": {"tecla": "Power"}}}, "id"),
        ({"controle": ""}, "controle"),
    ],
)
def test_invalid_remote_config(broken, message):
    raw = {**CONFIG["controles"]["tv"], **broken}
    with pytest.raises(HomeConfigError, match=message):
        parse_home_config({"controles": {"tv": raw}})


class FakeApi:
    def __init__(self, fail_standard: bool = False) -> None:
        self.posts = []
        self.fail_standard = fail_standard

    def connect(self):
        return {"success": True, "result": {}}

    def is_connect(self):
        return True

    def post(self, path, body=None):
        self.posts.append((path, body))
        if self.fail_standard and path.endswith("/remotes/RC1/command"):
            return {"success": False, "code": 2008, "msg": "command or value not support"}
        return {"success": True, "result": True}


async def test_tuya_blaster_uses_standard_command_then_raw():
    remote = parse_home_config(CONFIG).remotes["tv"]
    api = FakeApi()
    await TuyaIrBlaster(TuyaCloud(access_id="a", access_secret="b", api=api)).press(remote, remote.buttons["ligar_desligar"])
    assert api.posts == [("/v2.0/infrareds/IR1/remotes/RC1/command", {"category_id": 2, "key": "Power"})]

    api = FakeApi(fail_standard=True)
    await TuyaIrBlaster(TuyaCloud(access_id="a", access_secret="b", api=api)).press(remote, remote.buttons["ligar_desligar"])
    assert api.posts[1] == ("/v2.0/infrareds/IR1/remotes/RC1/raw/command", {"category_id": 2, "key_id": 1})
