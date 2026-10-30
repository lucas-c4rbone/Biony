from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest

from biony.adapters.sqlite_store import Database, SqlitePresumedStateStore
from biony.tools.home import HomeAssistantError, HomeControlTool, HomeController, HomeRoutineTool, home_tools
from biony.tools.home_config import HomeConfigError, IrDevice, Light, load_home_config, parse_home_config

pytestmark = pytest.mark.anyio

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config" / "casa.toml"

CONFIG = {
    "dispositivos": {
        "fita": {"nome": "fita LED", "entidade": "light.fita"},
        "pc": {"nome": "PC", "entidade": "switch.pc"},
        "ar": {"nome": "ar", "tipo": "ar_ir", "ligar": "scene.ar_on", "desligar": "scene.ar_off", "sinal_alterna": True},
    },
    "rotinas": {
        "cheguei": {
            "descricao": "chegou",
            "passos": [
                {"dispositivo": "fita", "acao": "ligar", "brilho": 80, "cor": [0, 0, 255]},
                {"dispositivo": "ar", "acao": "ligar"},
                {"entidade": "script.musica"},
            ],
        }
    },
}


class FakeHA:
    def __init__(self, states: dict[str, Mapping[str, Any]] | None = None, fail: bool = False) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.states = states or {}
        self.fail = fail

    async def get_state(self, entity_id: str) -> Mapping[str, Any]:
        if self.fail:
            raise HomeAssistantError("fora do ar")
        return self.states[entity_id]

    async def call_service(self, domain: str, service: str, data: Mapping[str, Any]) -> None:
        if self.fail:
            raise HomeAssistantError("fora do ar")
        self.calls.append((domain, service, dict(data)))


@pytest.fixture
def presumed() -> SqlitePresumedStateStore:
    return SqlitePresumedStateStore(Database(":memory:"))


def controller(ha: FakeHA, presumed) -> HomeController:
    return HomeController(ha, parse_home_config(CONFIG), presumed)


def test_repo_config_is_valid():
    config = load_home_config(REPO_CONFIG)

    assert isinstance(config.devices["fita_led"], Light)
    assert isinstance(config.devices["ar"], IrDevice)
    assert "cheguei" in config.routines


@pytest.mark.parametrize(
    "broken, message",
    [
        ({"dispositivos": {"x": {"entidade": "light.x"}}}, "nome"),
        ({"dispositivos": {"x": {"nome": "x", "entidade": "lock.porta"}}}, "entidade"),
        ({"dispositivos": {"x": {"nome": "x", "tipo": "ar_ir", "ligar": "light.a", "desligar": "scene.b"}}}, "ligar"),
        ({"rotinas": {"r": {"descricao": "r", "passos": [{"dispositivo": "nada", "acao": "ligar"}]}}}, "não existe"),
        ({"dispositivos": {"p": {"nome": "p", "entidade": "switch.p"}},
          "rotinas": {"r": {"descricao": "r", "passos": [{"dispositivo": "p", "acao": "ligar", "brilho": 50}]}}}, "só valem"),
        ({"dispositivos": {"f": {"nome": "f", "entidade": "light.f"}},
          "rotinas": {"r": {"descricao": "r", "passos": [{"dispositivo": "f", "acao": "ligar", "cor": [1, 2]}]}}}, "cor"),
    ],
)
def test_invalid_config_explains_the_problem(broken, message):
    with pytest.raises(HomeConfigError, match=message):
        parse_home_config(broken)


async def test_light_on_with_brightness_and_color_then_off(presumed):
    ha = FakeHA()
    home = controller(ha, presumed)

    on = await home.control("fita", "ligar", 40, (255, 0, 0))
    off = await home.control("fita", "desligar", 40)

    assert on.ok and off.ok
    assert ha.calls == [
        ("light", "turn_on", {"entity_id": "light.fita", "brightness_pct": 40, "rgb_color": [255, 0, 0]}),
        ("light", "turn_off", {"entity_id": "light.fita"}),
    ]


async def test_switch_uses_its_domain(presumed):
    ha = FakeHA()

    await controller(ha, presumed).control("pc", "ligar")

    assert ha.calls == [("switch", "turn_on", {"entity_id": "switch.pc"})]


async def test_toggle_ir_device_never_sends_signal_twice(presumed):
    ha = FakeHA()
    home = controller(ha, presumed)

    first = await home.control("ar", "ligar")
    again = await home.control("ar", "ligar")

    assert first.ok and "desconhecido" in first.content
    assert not again.ok and "já está ligado" in again.content
    assert ha.calls == [("scene", "turn_on", {"entity_id": "scene.ar_on"})]
    assert presumed.get("ar") == "on"


async def test_toggle_ir_device_can_be_forced_and_turned_off(presumed):
    ha = FakeHA()
    home = controller(ha, presumed)
    presumed.set("ar", "on")

    forced = await home.control("ar", "ligar", force=True)
    off = await home.control("ar", "desligar")

    assert forced.ok and off.ok
    assert [c[2]["entity_id"] for c in ha.calls] == ["scene.ar_on", "scene.ar_off"]
    assert presumed.get("ar") == "off"


async def test_ha_failure_does_not_change_presumed_state(presumed):
    result = await controller(FakeHA(fail=True), presumed).control("ar", "ligar")

    assert not result.ok and "fora do ar" in result.content
    assert presumed.get("ar") is None


async def test_unknown_device_and_action(presumed):
    home = controller(FakeHA(), presumed)

    assert not (await home.control("geladeira", "ligar")).ok
    assert not (await home.control("fita", "piscar")).ok


async def test_status_reads_lights_and_reports_presumed_ir(presumed):
    ha = FakeHA({
        "light.fita": {"state": "on", "attributes": {"brightness": 128, "rgb_color": [0, 0, 255]}},
        "switch.pc": {"state": "unavailable", "attributes": {}},
    })
    presumed.set("ar", "off")

    status = (await controller(ha, presumed).status()).content

    assert "fita LED: ligado, brilho 50%, cor RGB [0, 0, 255]" in status
    assert "PC: indisponível" in status
    assert "ar: desligado (presumido" in status


async def test_routine_runs_every_step_and_reports_failures(presumed):
    ha = FakeHA()
    home = controller(ha, presumed)
    presumed.set("ar", "on")  # o passo do ar vai ser recusado

    result = await home.run_routine("cheguei")

    assert not result.ok
    assert "falhou: Pelo meu registro" in result.content
    assert ha.calls == [
        ("light", "turn_on", {"entity_id": "light.fita", "brightness_pct": 80, "rgb_color": [0, 0, 255]}),
        ("script", "turn_on", {"entity_id": "script.musica"}),
    ]


async def test_control_tool_validates_llm_arguments(presumed):
    ha = FakeHA()
    tool = HomeControlTool(controller(ha, presumed))

    bad = await tool.execute({"dispositivo": "fita", "acao": "ligar", "brilho": 300})
    good = await tool.execute({"dispositivo": "fita", "acao": "ligar", "cor": [1, 2, 3]})

    assert not bad.ok and "brilho" in bad.content
    assert good.ok and ha.calls[0][2]["rgb_color"] == [1, 2, 3]


def test_tool_schemas_only_expose_configured_devices(presumed):
    tools = {tool.definition.name: tool for tool in home_tools(controller(FakeHA(), presumed))}

    control = tools["casa_controlar"].definition.parameters["properties"]["dispositivo"]
    assert control["enum"] == ["fita", "pc", "ar"]
    assert "forcar" in tools["casa_controlar"].definition.parameters["properties"]
    assert isinstance(tools["casa_rotina"], HomeRoutineTool)
    assert tools["casa_rotina"].definition.parameters["properties"]["rotina"]["enum"] == ["cheguei"]


def test_routine_tool_is_omitted_without_routines(presumed):
    config = parse_home_config({"dispositivos": CONFIG["dispositivos"]})

    names = [tool.definition.name for tool in home_tools(HomeController(FakeHA(), config, presumed))]

    assert names == ["casa_controlar", "casa_estado"]


async def test_discrete_ir_device_always_sends_and_hides_force(presumed):
    config = parse_home_config({"dispositivos": {
        "ar": {"nome": "ar", "tipo": "ar_ir", "ligar": "scene.on", "desligar": "scene.off"},
    }})
    ha = FakeHA()
    home = HomeController(ha, config, presumed)

    first, again = await home.control("ar", "ligar"), await home.control("ar", "ligar")

    assert first.ok and again.ok and "desconhecido" not in first.content
    assert len(ha.calls) == 2
    assert presumed.get("ar") == "on"
    assert "forcar" not in HomeControlTool(home).definition.parameters["properties"]


MODES = {
    "dispositivos": {
        "fita": {"nome": "fita", "entidade": "light.fita"},
        "ar": {
            "nome": "ar", "tipo": "ar_ir", "ligar": "scene.on", "desligar": "scene.off",
            "modos": {"24 graus": "scene.t24", "dormir": "scene.sono"},
        },
    },
    "rotinas": {"noite": {"descricao": "dormir", "passos": [
        {"dispositivo": "fita", "acao": "desligar"},
        {"dispositivo": "ar", "acao": "ligar", "modo": "dormir"},
    ]}},
}


FITA_OFF = {"light.fita": {"state": "off", "attributes": {}}}


async def test_mode_activates_its_scene_and_is_remembered(presumed):
    ha = FakeHA(FITA_OFF)
    home = HomeController(ha, parse_home_config(MODES), presumed)

    result = await home.control("ar", "ligar", mode="24 graus")
    status = (await home.status()).content

    assert result.ok and "modo 24 graus" in result.content
    assert ha.calls == [("scene", "turn_on", {"entity_id": "scene.t24"})]
    assert "ar: ligado no modo 24 graus (presumido" in status


async def test_plain_on_forgets_mode_and_off_hides_it(presumed):
    ha = FakeHA(FITA_OFF)
    home = HomeController(ha, parse_home_config(MODES), presumed)

    await home.control("ar", "ligar", mode="dormir")
    await home.control("ar", "ligar")
    assert "ar: ligado (presumido" in (await home.status()).content

    await home.control("ar", "ligar", mode="dormir")
    await home.control("ar", "desligar")
    assert "ar: desligado (presumido" in (await home.status()).content


async def test_invalid_mode_usage(presumed):
    home = HomeController(FakeHA(), parse_home_config(MODES), presumed)

    unknown = await home.control("ar", "ligar", mode="18 graus")
    off_with_mode = await home.control("ar", "desligar", mode="dormir")
    light_mode = await home.control("fita", "ligar", mode="dormir")

    assert not unknown.ok and "24 graus, dormir" in unknown.content
    assert not off_with_mode.ok
    assert not light_mode.ok


async def test_routine_step_with_mode(presumed):
    ha = FakeHA()

    result = await HomeController(ha, parse_home_config(MODES), presumed).run_routine("noite")

    assert result.ok
    assert [c[2]["entity_id"] for c in ha.calls] == ["light.fita", "scene.sono"]


def test_mode_schema_and_config_validation(presumed):
    tool = HomeControlTool(HomeController(FakeHA(), parse_home_config(MODES), presumed))
    modo = tool.definition.parameters["properties"]["modo"]
    assert modo["enum"] == ["24 graus", "dormir"]
    assert "ar: 24 graus, dormir" in modo["description"]

    plain = HomeControlTool(HomeController(FakeHA(), parse_home_config({"dispositivos": {"f": {"nome": "f", "entidade": "light.f"}}}), presumed))
    assert "modo" not in plain.definition.parameters["properties"]

    bad_step = {"dispositivos": MODES["dispositivos"], "rotinas": {"r": {"descricao": "r", "passos": [{"dispositivo": "ar", "acao": "ligar", "modo": "x"}]}}}
    with pytest.raises(HomeConfigError, match="modo 'x'"):
        parse_home_config(bad_step)
    bad_entity = {"dispositivos": {"ar": {**MODES["dispositivos"]["ar"], "modos": {"24": "light.x"}}}}
    with pytest.raises(HomeConfigError, match="modos"):
        parse_home_config(bad_entity)


async def test_control_tool_passes_mode(presumed):
    ha = FakeHA()
    tool = HomeControlTool(HomeController(ha, parse_home_config(MODES), presumed))

    result = await tool.execute({"dispositivo": "ar", "acao": "ligar", "modo": "dormir"})

    assert result.ok and ha.calls[0][2]["entity_id"] == "scene.sono"


async def test_plain_on_reports_mode_when_on_scene_is_a_mode(presumed):
    config = {"dispositivos": {"ar": {
        "nome": "ar", "tipo": "ar_ir", "ligar": "scene.t24", "desligar": "scene.off",
        "modos": {"24 graus": "scene.t24", "26 graus": "scene.t26"},
    }}}
    ha = FakeHA()
    home = HomeController(ha, parse_home_config(config), presumed)

    await home.control("ar", "ligar")

    assert ha.calls == [("scene", "turn_on", {"entity_id": "scene.t24"})]
    assert "ligado no modo 24 graus" in (await home.status()).content


def test_device_note_reaches_the_llm(presumed):
    config = parse_home_config({"dispositivos": {"ar": {
        "nome": "ar", "tipo": "ar_ir", "ligar": "scene.a", "desligar": "scene.b", "observacao": "26 é o mais quente",
    }}})
    tool = HomeControlTool(HomeController(FakeHA(), config, presumed))

    assert "ar = ar (26 é o mais quente)" in tool.definition.parameters["properties"]["dispositivo"]["description"]
    with pytest.raises(HomeConfigError, match="observacao"):
        parse_home_config({"dispositivos": {"f": {"nome": "f", "entidade": "light.f", "observacao": 3}}})


PROTECTED = {
    "dispositivos": {
        "setup": {"nome": "setup do PC", "entidade": "switch.filtro", "confirmar_desligar": True},
        "fita": {"nome": "fita", "entidade": "light.fita"},
    },
    "rotinas": {
        "sai": {"descricao": "saindo", "passos": [{"dispositivo": "setup", "acao": "desligar"}]},
        "luz": {"descricao": "luz", "passos": [{"dispositivo": "fita", "acao": "desligar"}]},
    },
}


def test_only_turning_off_protected_device_needs_confirmation(presumed):
    home = HomeController(FakeHA(), parse_home_config(PROTECTED), presumed)
    control, routine = HomeControlTool(home), HomeRoutineTool(home)

    assert control.needs_confirmation({"dispositivo": "setup", "acao": "desligar"})
    assert not control.needs_confirmation({"dispositivo": "setup", "acao": "ligar"})
    assert not control.needs_confirmation({"dispositivo": "fita", "acao": "desligar"})
    assert control.describe({"dispositivo": "setup", "acao": "desligar"}) == "desligar setup do PC"
    assert routine.needs_confirmation({"rotina": "sai"})
    assert not routine.needs_confirmation({"rotina": "luz"})
    with pytest.raises(HomeConfigError, match="confirmar_desligar"):
        parse_home_config({"dispositivos": {"x": {"nome": "x", "entidade": "switch.x", "confirmar_desligar": "sim"}}})


@pytest.mark.anyio
async def test_protected_off_waits_for_yes_through_engine(store, presumed):
    from conftest import ScriptedLLM, make_engine
    from biony.core.models import LLMReply, ToolCall

    ha = FakeHA()
    tool = HomeControlTool(HomeController(ha, parse_home_config(PROTECTED), presumed))
    llm = ScriptedLLM(
        LLMReply(tool_calls=(ToolCall("a", "casa_controlar", {"dispositivo": "setup", "acao": "desligar"}),)),
        LLMReply("Desliguei."),
    )
    engine = make_engine(llm, store, tool)

    ask = await engine.handle("desliga o setup", "s")
    assert ask.awaiting_confirmation and "desligar setup do PC" in ask.text and ha.calls == []
    await engine.handle("sim", "s")
    assert ha.calls == [("switch", "turn_off", {"entity_id": "switch.filtro"})]


EFFECTS = {
    "dispositivos": {
        "fita": {"nome": "fita", "entidade": "light.fita", "efeitos": ["red_fade", "music"]},
        "pc": {"nome": "pc", "entidade": "switch.pc"},
    },
    "rotinas": {"festa": {"descricao": "festa", "passos": [{"dispositivo": "fita", "acao": "ligar", "efeito": "music"}]}},
}


async def test_light_effects(presumed):
    ha = FakeHA({"light.fita": {"state": "on", "attributes": {"brightness": 255, "effect": "red_fade"}}, "switch.pc": {"state": "off", "attributes": {}}})
    home = HomeController(ha, parse_home_config(EFFECTS), presumed)
    tool = HomeControlTool(home)

    assert (await tool.execute({"dispositivo": "fita", "acao": "ligar", "efeito": "red_fade", "brilho": 30, "cor": [255, 0, 0]})).ok
    assert ha.calls[-1] == ("light", "turn_on", {"entity_id": "light.fita", "brightness_pct": 30, "effect": "red_fade"})
    assert not (await tool.execute({"dispositivo": "fita", "acao": "ligar", "efeito": "disco"})).ok
    assert not (await tool.execute({"dispositivo": "pc", "acao": "ligar", "efeito": "music"})).ok
    assert "efeito red_fade" in (await home.status()).content
    assert (await home.run_routine("festa")).ok and ha.calls[-1][2]["effect"] == "music"
    assert tool.definition.parameters["properties"]["efeito"]["enum"] == ["music", "red_fade"]


def test_effect_config_validation():
    with pytest.raises(HomeConfigError, match="efeito 'x'"):
        parse_home_config({**EFFECTS, "rotinas": {"r": {"descricao": "r", "passos": [{"dispositivo": "fita", "acao": "ligar", "efeito": "x"}]}}})
    with pytest.raises(HomeConfigError, match="efeitos"):
        parse_home_config({"dispositivos": {"f": {"nome": "f", "entidade": "light.f", "efeitos": "music"}}})
