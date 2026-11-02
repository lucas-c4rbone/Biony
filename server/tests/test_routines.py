"""Passos novos das rotinas (botão da TV, desligar o PC mantendo o filtro) e a intenção das rotinas do casa.toml."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from biony.adapters.sqlite_store import Database, SqlitePresumedStateStore
from biony.core.tools import ToolResult
from biony.tools.home import HomeController, HomeRoutineTool
from biony.tools.home_config import HomeConfigError, load_home_config, parse_home_config

from test_home import FakeHA

pytestmark = pytest.mark.anyio

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config" / "casa.toml"

BASE = {
    "dispositivos": {"setup": {"nome": "setup", "entidade": "switch.filtro"}},
    "controles": {
        "tv": {
            "nome": "TV",
            "infravermelho": "IR1",
            "controle": "RC1",
            "categoria": 2,
            "botoes": {"ligar_desligar": {"tecla": "Power", "id": 1}},
        }
    },
}


def with_steps(*steps) -> dict:
    return {**BASE, "rotinas": {"r": {"descricao": "x", "passos": list(steps)}}}


class StubPc:
    setup_device = "setup"

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def turn_on(self) -> ToolResult:
        self.calls.append(("ligar",))
        return ToolResult(True, "ligou")

    async def turn_off(self, already_off_ok: bool = False, keep_power: bool = False) -> ToolResult:
        self.calls.append(("desligar", keep_power))
        return ToolResult(True, "desligou")


class FakeRemote:
    def __init__(self, ok: bool = True) -> None:
        self.pressed: list[dict] = []
        self.ok = ok

    async def execute(self, arguments) -> ToolResult:
        self.pressed.append(dict(arguments))
        return ToolResult(self.ok, "apertou" if self.ok else "a Tuya recusou")


class Inbox:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, text: str) -> None:
        self.messages.append(text)


def home_for(config: dict, filter_state: str | None = "off", remote: FakeRemote | None = None):
    states = {"switch.filtro": {"state": filter_state, "attributes": {}}} if filter_state else {}
    ha = FakeHA(states)
    home = HomeController(ha, parse_home_config(config), SqlitePresumedStateStore(Database(":memory:")))
    home.pc, home.remote, home.notifier = StubPc(), remote, Inbox()
    return home, ha


async def settle() -> None:
    await asyncio.sleep(0.1)  # deixa a tarefa em segundo plano rodar


# ------------------------------------------------------------------ leitura do casa.toml


@pytest.mark.parametrize(
    "step, message",
    [
        ({"controle": "som", "botao": "x"}, "controle 'som'"),
        ({"controle": "tv", "botao": "netflix"}, "botão 'netflix'"),
        ({"controle": "tv", "botao": "ligar_desligar", "depois": -1}, "depois"),
        ({"controle": "tv", "botao": "ligar_desligar", "depois": 999}, "depois"),
        ({"controle": "tv", "botao": "ligar_desligar", "depois": True}, "depois"),
        ({"controle": "tv", "botao": "ligar_desligar", "so_se_setup_desligado": "sim"}, "so_se_setup_desligado"),
        ({"pc": "desligar", "manter_filtro": "sim"}, "manter_filtro"),
        ({"pc": "ligar", "manter_filtro": True}, "manter_filtro"),
    ],
)
def test_invalid_new_steps_are_explained(step, message):
    with pytest.raises(HomeConfigError, match=message):
        parse_home_config(with_steps(step))


def test_new_steps_are_parsed():
    config = parse_home_config(
        with_steps(
            {"controle": "tv", "botao": "ligar_desligar", "depois": 25, "so_se_setup_desligado": True},
            {"pc": "desligar", "manter_filtro": True},
        )
    )
    tv, pc = config.routines["r"].steps
    assert tv.remote == ("tv", "ligar_desligar") and tv.delay == 25.0 and tv.only_if_setup_off
    assert pc.pc == "desligar" and pc.keep_power


# ------------------------------------------------------------------ botão da TV dentro de uma rotina

TV_AFTER_SETUP = with_steps(
    {"pc": "ligar"},
    {"controle": "tv", "botao": "ligar_desligar", "depois": 0.01, "so_se_setup_desligado": True},
)


async def test_tv_is_pressed_in_the_background_when_the_setup_was_off():
    remote = FakeRemote()
    home, _ = home_for(TV_AFTER_SETUP, "off", remote)
    result = await home.run_routine("r")
    assert result.ok and "em segundo plano" in result.content
    assert remote.pressed == []  # ainda não: a rotina responde na hora e a TV espera ela ligar
    await settle()
    assert remote.pressed == [{"controle": "tv", "botao": "ligar_desligar"}]


@pytest.mark.parametrize("filter_state", ["on", "unavailable", None])  # ligado, offline ou não deu para conferir
async def test_tv_is_not_pressed_when_the_setup_was_already_on_or_unknown(filter_state):
    remote = FakeRemote()
    home, _ = home_for(TV_AFTER_SETUP, filter_state, remote)
    result = await home.run_routine("r")
    await settle()
    assert result.ok and "não apertei" in result.content and remote.pressed == []  # apertar alternaria a TV


async def test_button_without_delay_runs_inline_and_without_the_condition():
    remote = FakeRemote()
    config = with_steps({"controle": "tv", "botao": "ligar_desligar"})
    home, _ = home_for(config, "on", remote)
    assert (await home.run_routine("r")).ok
    assert remote.pressed == [{"controle": "tv", "botao": "ligar_desligar"}]


async def test_background_failure_is_reported_on_telegram():
    remote = FakeRemote(ok=False)
    home, _ = home_for(TV_AFTER_SETUP, "off", remote)
    await home.run_routine("r")
    await settle()
    assert home.notifier.messages and "Não consegui apertar ligar_desligar" in home.notifier.messages[0]
    assert "a Tuya recusou" in home.notifier.messages[0]


async def test_tv_step_without_ir_controls_configured_fails_clearly():
    home, _ = home_for(TV_AFTER_SETUP, "off", remote=None)
    result = await home.run_routine("r")
    assert not result.ok and "controles IR" in result.content


async def test_pc_step_passes_keep_power():
    home, _ = home_for(with_steps({"pc": "desligar", "manter_filtro": True}, {"pc": "desligar"}), "on")
    await home.run_routine("r")
    assert home.pc.calls == [("desligar", True), ("desligar", False)]


# ------------------------------------------------------------------ o que cada rotina do casa.toml faz


def steps(routine) -> set[tuple]:
    out = set()
    for s in routine.steps:
        if s.device:
            out.add((s.device, s.action, s.mode, s.effect))
        elif s.pc:
            out.add(("pc", s.pc, s.keep_power))
        elif s.remote:
            out.add(("tv", s.remote[1]))
    return out


@pytest.fixture(scope="module")
def routines():
    return load_home_config(REPO_CONFIG).routines


def test_repo_routines_do_what_lucas_asked(routines):
    ar24, ar26, ardormir = "24 graus", "26 graus", "dormir (22 graus e turbo)"
    assert steps(routines["cheguei"]) == {
        ("ar", "ligar", ar24, None), ("pc", "ligar", False), ("teto", "ligar", None, None), ("tv", "ligar_desligar"),
    }
    assert steps(routines["sai"]) == {
        ("ar", "desligar", None, None), ("teto", "desligar", None, None), ("dicroicas", "desligar", None, None),
        ("fita_led", "desligar", None, None), ("pc", "desligar", False),
    }
    # "vou dormir" deixa as dicroicas ligadas; "boa noite" apaga tudo.
    assert steps(routines["dormir"]) == {
        ("pc", "desligar", False), ("teto", "desligar", None, None), ("fita_led", "desligar", None, None),
        ("dicroicas", "ligar", None, None), ("ar", "ligar", ardormir, None),
    }
    assert steps(routines["boa_noite"]) == {
        ("pc", "desligar", False), ("teto", "desligar", None, None), ("fita_led", "desligar", None, None),
        ("dicroicas", "desligar", None, None), ("ar", "ligar", ardormir, None),
    }
    assert steps(routines["bom_dia"]) == {("ar", "ligar", ar26, None), ("dicroicas", "ligar", None, None)}
    assert steps(routines["jogar"]) == {
        ("pc", "ligar", False), ("teto", "desligar", None, None), ("dicroicas", "desligar", None, None),
        ("fita_led", "ligar", None, "purple_fade"), ("ar", "ligar", ar24, None),
    }
    # modo filme: o Windows desliga mas o filtro fica (a TV está nele).
    assert ("pc", "desligar", True) in steps(routines["filme"])
    assert {("teto", "desligar", None, None), ("dicroicas", "ligar", None, None), ("ar", "ligar", ar24, None)} <= steps(
        routines["filme"]
    )


def test_apaga_e_acende_tudo_only_touch_the_room_lights_not_the_led_strip(routines):
    assert steps(routines["apaga_tudo"]) == {("teto", "desligar", None, None), ("dicroicas", "desligar", None, None)}
    assert steps(routines["acende_tudo"]) == {("teto", "ligar", None, None), ("dicroicas", "ligar", None, None)}


def test_movie_mode_led_strip_is_warm_and_dim(routines):
    led = next(s for s in routines["filme"].steps if s.device == "fita_led")
    red, green, blue = led.color
    assert red == 255 and green < 200 and blue < green  # tom quente (âmbar)
    assert led.brightness is not None and led.brightness <= 30


def test_routines_that_shut_the_pc_down_ask_for_confirmation_and_the_others_do_not():
    home = HomeController(FakeHA(), load_home_config(REPO_CONFIG), None)
    tool = HomeRoutineTool(home)
    for key in ("sai", "dormir", "boa_noite", "filme"):
        assert tool.needs_confirmation({"rotina": key}), key
    for key in ("cheguei", "bom_dia", "jogar", "apaga_tudo", "acende_tudo"):
        assert not tool.needs_confirmation({"rotina": key}), key


# ------------------------------------------------------------------ o "sim" só vale a pena com o PC ligado


class StubPcOnline(StubPc):
    def __init__(self, online: bool | None) -> None:
        super().__init__()
        self._online = online

    async def is_online(self):
        return self._online


@pytest.mark.parametrize(
    "online, asks",
    [(True, True), (False, False), (None, True)],  # PC ligado pede; desligado roda direto; na dúvida pede
)
async def test_routine_that_shuts_the_pc_down_asks_only_when_it_is_on(online, asks):
    home = HomeController(FakeHA(), load_home_config(REPO_CONFIG), None)
    home.pc = StubPcOnline(online)
    tool = HomeRoutineTool(home)
    assert await tool.confirmation_needed({"rotina": "boa_noite"}) is asks
    assert await tool.confirmation_needed({"rotina": "sai"}) is asks
    assert await tool.confirmation_needed({"rotina": "filme"}) is asks


async def test_routines_without_a_pc_shutdown_never_ask_and_without_pc_agent_always_ask():
    home = HomeController(FakeHA(), load_home_config(REPO_CONFIG), None)
    home.pc = StubPcOnline(True)
    tool = HomeRoutineTool(home)
    assert not await tool.confirmation_needed({"rotina": "bom_dia"})
    home.pc = None  # sem agente do PC não dá para saber: pede
    assert await tool.confirmation_needed({"rotina": "boa_noite"})


async def test_protected_device_still_asks_even_if_the_pc_is_off():
    config = {
        "dispositivos": {"setup": {"nome": "setup", "entidade": "switch.filtro", "confirmar_desligar": True}},
        "rotinas": {"r": {"descricao": "x", "passos": [{"dispositivo": "setup", "acao": "desligar"}]}},
    }
    home = HomeController(FakeHA(), parse_home_config(config), None)
    home.pc = StubPcOnline(False)
    assert await HomeRoutineTool(home).confirmation_needed({"rotina": "r"})
