"""Leitura e validação do config/casa.toml."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import tomllib
from typing import Any, Mapping, Union

ACTIONS = ("ligar", "desligar")
_ACTIVATABLE = ("scene", "script")


class HomeConfigError(ValueError):
    """casa.toml inválido. A mensagem diz o que corrigir."""


@dataclass(frozen=True)
class Light:
    key: str
    name: str
    entity: str
    note: str = ""
    confirm_off: bool = False


@dataclass(frozen=True)
class Switch:
    key: str
    name: str
    entity: str
    note: str = ""
    confirm_off: bool = False


@dataclass(frozen=True)
class IrDevice:
    """Aparelho controlado por cenas/scripts que mandam sinais IR."""

    key: str
    name: str
    on_entity: str
    off_entity: str
    toggles: bool
    # Nome do modo → cena/script que liga o aparelho já nele (ex.: "24 graus").
    modes: Mapping[str, str] = field(default_factory=dict)
    note: str = ""
    confirm_off: bool = False


Device = Union[Light, Switch, IrDevice]


@dataclass(frozen=True)
class Step:
    device: str | None = None
    action: str | None = None
    brightness: int | None = None
    color: tuple[int, int, int] | None = None
    entity: str | None = None
    mode: str | None = None


@dataclass(frozen=True)
class Routine:
    key: str
    description: str
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class HomeConfig:
    devices: dict[str, Device]
    routines: dict[str, Routine]


def load_home_config(path: Path) -> HomeConfig:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise HomeConfigError(f"{path}: TOML inválido: {error}") from error
    return parse_home_config(data)


def parse_home_config(data: dict[str, Any]) -> HomeConfig:
    devices = {key: _parse_device(key, raw) for key, raw in data.get("dispositivos", {}).items()}
    routines = {key: _parse_routine(key, raw, devices) for key, raw in data.get("rotinas", {}).items()}
    return HomeConfig(devices, routines)


def domain_of(entity: str) -> str:
    return entity.split(".", 1)[0]


def validate_brightness(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        raise HomeConfigError(f"brilho precisa ser um inteiro de 1 a 100 (veio {value!r})")
    return value


def validate_color(value: object) -> tuple[int, int, int]:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 3
        or not all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in value)
    ):
        raise HomeConfigError(f"cor precisa ser [R, G, B] com valores de 0 a 255 (veio {value!r})")
    return (value[0], value[1], value[2])


def _parse_device(key: str, raw: dict[str, Any]) -> Device:
    device = _parse_device_kind(key, raw)
    note = raw.get("observacao", "")
    if not isinstance(note, str):
        raise HomeConfigError(f"dispositivos.{key}.observacao precisa ser texto")
    confirm_off = raw.get("confirmar_desligar", False)
    if not isinstance(confirm_off, bool):
        raise HomeConfigError(f"dispositivos.{key}.confirmar_desligar precisa ser true ou false")
    return replace(device, note=note.strip(), confirm_off=confirm_off)


def _parse_device_kind(key: str, raw: dict[str, Any]) -> Device:
    where = f"dispositivos.{key}"
    name = _require_str(raw, "nome", where)
    kind = raw.get("tipo")

    if kind == "ar_ir":
        on_entity = _require_entity(raw, "ligar", where, _ACTIVATABLE)
        off_entity = _require_entity(raw, "desligar", where, _ACTIVATABLE)
        toggles = raw.get("sinal_alterna", False)
        if not isinstance(toggles, bool):
            raise HomeConfigError(f"{where}.sinal_alterna precisa ser true ou false")
        raw_modes = raw.get("modos", {})
        if not isinstance(raw_modes, dict):
            raise HomeConfigError(f"{where}.modos precisa ser uma tabela: nome = \"scene.x\"")
        modes = {mode: _require_entity(raw_modes, mode, f"{where}.modos", _ACTIVATABLE) for mode in raw_modes}
        return IrDevice(key, name, on_entity, off_entity, toggles, modes)

    entity = _require_entity(raw, "entidade", where, ("light", "switch", "input_boolean"))
    if kind is None:
        kind = "luz" if domain_of(entity) == "light" else "interruptor"
    if kind == "luz":
        if domain_of(entity) != "light":
            raise HomeConfigError(f"{where}: tipo luz precisa de uma entidade light.*")
        return Light(key, name, entity)
    if kind == "interruptor":
        return Switch(key, name, entity)
    raise HomeConfigError(f"{where}.tipo desconhecido: {kind!r} (use luz, interruptor ou ar_ir)")


def _parse_routine(key: str, raw: dict[str, Any], devices: dict[str, Device]) -> Routine:
    where = f"rotinas.{key}"
    description = _require_str(raw, "descricao", where)
    raw_steps = raw.get("passos")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise HomeConfigError(f"{where}.passos precisa ser uma lista com pelo menos um passo")
    return Routine(key, description, tuple(_parse_step(f"{where}.passos[{i}]", s, devices) for i, s in enumerate(raw_steps)))


def _parse_step(where: str, raw: dict[str, Any], devices: dict[str, Device]) -> Step:
    if "entidade" in raw:
        return Step(entity=_require_entity(raw, "entidade", where, _ACTIVATABLE))

    device_key = _require_str(raw, "dispositivo", where)
    device = devices.get(device_key)
    if device is None:
        raise HomeConfigError(f"{where}: dispositivo {device_key!r} não existe em [dispositivos]")
    action = raw.get("acao")
    if action not in ACTIONS:
        raise HomeConfigError(f"{where}.acao precisa ser 'ligar' ou 'desligar'")

    mode = raw.get("modo")
    if mode is not None:
        if not isinstance(device, IrDevice) or mode not in device.modes:
            raise HomeConfigError(f"{where}: modo {mode!r} não existe em dispositivos.{device_key}.modos")
        if action != "ligar":
            raise HomeConfigError(f"{where}: modo só vale com acao = \"ligar\"")

    brightness = color = None
    try:
        if "brilho" in raw:
            brightness = validate_brightness(raw["brilho"])
        if "cor" in raw:
            color = validate_color(raw["cor"])
    except HomeConfigError as error:
        raise HomeConfigError(f"{where}: {error}") from error
    if (brightness or color) and not isinstance(device, Light):
        raise HomeConfigError(f"{where}: brilho/cor só valem para luzes")
    return Step(device_key, action, brightness, color, mode=mode)


def _require_str(raw: dict[str, Any], field: str, where: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise HomeConfigError(f"{where}.{field} é obrigatório (texto)")
    return value


def _require_entity(raw: dict[str, Any], field: str, where: str, domains: tuple[str, ...]) -> str:
    entity = _require_str(raw, field, where)
    if "." not in entity or domain_of(entity) not in domains:
        raise HomeConfigError(f"{where}.{field}: {entity!r} precisa ser uma entidade {'/'.join(d + '.*' for d in domains)}")
    return entity
