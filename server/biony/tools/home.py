"""Ferramentas do Home Assistant. Só controlam o que está em config/casa.toml."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from biony.core.tools import Tool, ToolDefinition, ToolResult
from biony.tools.home_config import (
    ACTIONS,
    Device,
    HomeConfig,
    HomeConfigError,
    IrDevice,
    Light,
    Step,
    domain_of,
    validate_brightness,
    validate_color,
)

ON, OFF = "on", "off"
_WORD = {ON: "ligado", OFF: "desligado", None: "desconhecido"}


class HomeAssistantError(RuntimeError):
    """O Home Assistant não respondeu ou recusou o pedido."""


class HomeAssistant(Protocol):
    async def get_state(self, entity_id: str) -> Mapping[str, Any]:
        """Estado de uma entidade no formato da API REST do HA."""

    async def call_service(self, domain: str, service: str, data: Mapping[str, Any]) -> None:
        """Chama um serviço do HA (ex.: light.turn_on)."""


class PresumedStateStore(Protocol):
    """Guarda o estado de aparelhos que o HA não consegue ler (IR de botão único)."""

    def get(self, device: str) -> str | None: ...

    def set(self, device: str, state: str) -> None: ...


class HomeController:
    def __init__(self, ha: HomeAssistant, config: HomeConfig, presumed: PresumedStateStore) -> None:
        self._ha = ha
        self.config = config
        self._presumed = presumed

    async def control(
        self,
        key: str,
        action: str,
        brightness: int | None = None,
        color: tuple[int, int, int] | None = None,
        force: bool = False,
    ) -> ToolResult:
        device = self.config.devices.get(key)
        if device is None:
            return ToolResult(False, f"Dispositivo desconhecido: {key}.")
        if action not in ACTIONS:
            return ToolResult(False, f"Ação inválida: {action}. Use ligar ou desligar.")
        target = ON if action == "ligar" else OFF
        try:
            if isinstance(device, IrDevice):
                return await self._control_ir(device, target, force)
            data: dict[str, Any] = {"entity_id": device.entity}
            if isinstance(device, Light) and target == ON:
                if brightness is not None:
                    data["brightness_pct"] = brightness
                if color is not None:
                    data["rgb_color"] = list(color)
            await self._ha.call_service(domain_of(device.entity), f"turn_{target}", data)
        except HomeAssistantError as error:
            return ToolResult(False, f"O Home Assistant falhou ao {action} {device.name}: {error}")
        return ToolResult(True, f"{device.name}: {_WORD[target]}.")

    async def _control_ir(self, device: IrDevice, target: str, force: bool) -> ToolResult:
        previous = self._presumed.get(device.key)
        if device.toggles and previous == target and not force:
            return ToolResult(
                False,
                f"Pelo meu registro, {device.name} já está {_WORD[target]}. Não mandei o sinal: "
                "ele alterna liga/desliga e acabaria invertendo. Se o registro estiver errado, "
                "chame de novo com forcar=true.",
            )
        await self._activate(device.on_entity if target == ON else device.off_entity)
        self._presumed.set(device.key, target)
        note = " (o estado anterior era desconhecido)" if device.toggles and previous is None else ""
        return ToolResult(True, f"{device.name}: sinal enviado, deve estar {_WORD[target]}{note}.")

    async def status(self) -> ToolResult:
        lines = []
        for device in self.config.devices.values():
            try:
                lines.append(await self._describe(device))
            except HomeAssistantError as error:
                lines.append(f"{device.name}: não consegui ler ({error})")
        return ToolResult(True, "\n".join(lines) or "Nenhum dispositivo configurado.")

    async def _describe(self, device: Device) -> str:
        if isinstance(device, IrDevice):
            return f"{device.name}: {_WORD[self._presumed.get(device.key)]} (presumido; o Biony não lê o aparelho)"
        state = await self._ha.get_state(device.entity)
        value = state.get("state")
        if value == "unavailable":
            return f"{device.name}: indisponível (offline no HA)"
        text = f"{device.name}: {_WORD.get(value, value)}"
        attributes = state.get("attributes", {})
        if isinstance(device, Light) and value == ON:
            if attributes.get("brightness") is not None:
                text += f", brilho {round(attributes['brightness'] / 255 * 100)}%"
            if attributes.get("rgb_color"):
                text += f", cor RGB {list(attributes['rgb_color'])}"
        return text

    async def run_routine(self, key: str) -> ToolResult:
        routine = self.config.routines.get(key)
        if routine is None:
            return ToolResult(False, f"Rotina desconhecida: {key}.")
        results = [await self._run_step(step) for step in routine.steps]
        lines = "\n".join(("ok: " if r.ok else "falhou: ") + r.content for r in results)
        return ToolResult(all(r.ok for r in results), f"Rotina {key}:\n{lines}")

    async def _run_step(self, step: Step) -> ToolResult:
        if step.entity is not None:
            try:
                await self._activate(step.entity)
            except HomeAssistantError as error:
                return ToolResult(False, f"{step.entity}: {error}")
            return ToolResult(True, f"{step.entity} ativado.")
        return await self.control(step.device, step.action, step.brightness, step.color)

    async def _activate(self, entity: str) -> None:
        await self._ha.call_service(domain_of(entity), "turn_on", {"entity_id": entity})


# ------------------------------------------------------------------ ferramentas


class HomeControlTool(Tool):
    def __init__(self, controller: HomeController) -> None:
        self._controller = controller
        devices = controller.config.devices
        self.definition = ToolDefinition(
            name="casa_controlar",
            description=(
                "Liga ou desliga um aparelho do quarto do Lucas. "
                "Para vários aparelhos, chame uma vez para cada um."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "dispositivo": {
                        "type": "string",
                        "enum": list(devices),
                        "description": "; ".join(f"{key} = {device.name}" for key, device in devices.items()),
                    },
                    "acao": {"type": "string", "enum": list(ACTIONS)},
                    "brilho": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "description": "Só para luzes: brilho em %.",
                    },
                    "cor": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 0, "maximum": 255},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "Só para luzes: cor [R, G, B].",
                    },
                },
                "required": ["dispositivo", "acao"],
            },
        )
        if any(isinstance(d, IrDevice) and d.toggles for d in devices.values()):
            self.definition.parameters["properties"]["forcar"] = {
                "type": "boolean",
                "description": (
                    "Só para aparelhos IR de botão único: manda o sinal mesmo que o registro diga que "
                    "já está no estado pedido. Use apenas se o Lucas disser que o registro está errado."
                ),
            }

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        try:
            brightness = validate_brightness(arguments["brilho"]) if arguments.get("brilho") is not None else None
            color = validate_color(arguments["cor"]) if arguments.get("cor") is not None else None
        except HomeConfigError as error:
            return ToolResult(False, str(error))
        return await self._controller.control(
            str(arguments.get("dispositivo")),
            str(arguments.get("acao")),
            brightness,
            color,
            force=arguments.get("forcar") is True,
        )


class HomeStatusTool(Tool):
    def __init__(self, controller: HomeController) -> None:
        self._controller = controller
        self.definition = ToolDefinition(
            name="casa_estado",
            description="Consulta o estado atual dos aparelhos do quarto (ligado, brilho, cor...).",
        )

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        return await self._controller.status()


class HomeRoutineTool(Tool):
    def __init__(self, controller: HomeController) -> None:
        self._controller = controller
        routines = controller.config.routines
        self.definition = ToolDefinition(
            name="casa_rotina",
            description=(
                "Executa uma rotina do quarto (várias ações de uma vez). Prefira uma rotina "
                "quando o pedido combinar com a descrição dela."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "rotina": {
                        "type": "string",
                        "enum": list(routines),
                        "description": "; ".join(f"{key} = {r.description}" for key, r in routines.items()),
                    }
                },
                "required": ["rotina"],
            },
        )

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        return await self._controller.run_routine(str(arguments.get("rotina")))


def home_tools(controller: HomeController) -> list[Tool]:
    tools: list[Tool] = [HomeControlTool(controller), HomeStatusTool(controller)]
    if controller.config.routines:
        tools.append(HomeRoutineTool(controller))
    return tools
