"""Controles IR (TV etc.): aperta botões cadastrados em [controles] do config/casa.toml."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Mapping, Protocol

from biony.core.tools import Tool, ToolDefinition, ToolResult
from biony.tools.home_config import IrButton, Remote

MAX_PRESSES = 15
_GAP_SECONDS = 0.4  # entre apertos repetidos, para o aparelho registrar cada um


class IrSendError(RuntimeError):
    """O serviço do IR não respondeu ou recusou o comando."""


class IrBlaster(Protocol):
    async def press(self, remote: Remote, button: IrButton) -> None:
        """Manda o sinal de um botão do controle."""


class RemotePressTool(Tool):
    def __init__(
        self,
        blaster: IrBlaster,
        remotes: Mapping[str, Remote],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._blaster = blaster
        self._remotes = remotes
        self._sleep = sleep
        self.definition = ToolDefinition(
            name="controle_apertar",
            description=(
                "Aperta um botão de um controle remoto IR (ex.: a TV): ligar/desligar, volume, canal, "
                "navegação. Os aparelhos IR não informam o estado: o Biony só manda o sinal."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "controle": {
                        "type": "string",
                        "enum": list(remotes),
                        "description": "; ".join(
                            f"{key} = {r.name}: botões {', '.join(r.buttons)}" + (f" ({r.note})" if r.note else "")
                            for key, r in remotes.items()
                        ),
                    },
                    "botao": {"type": "string", "enum": sorted({b for r in remotes.values() for b in r.buttons})},
                    "vezes": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_PRESSES,
                        "description": (
                            "Quantas vezes apertar (padrão 1). Para volume: \"um pouco\" = 3, "
                            "\"aumenta\"/\"abaixa\" sem quantidade = 5, \"bastante\" = 10."
                        ),
                    },
                },
                "required": ["controle", "botao"],
            },
        )

    def describe(self, arguments: Mapping[str, Any]) -> str:
        return f"apertar {arguments.get('botao')} no controle {arguments.get('controle')}"

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        remote = self._remotes.get(str(arguments.get("controle")))
        if remote is None:
            return ToolResult(False, f"Controle desconhecido: {arguments.get('controle')}.")
        name = str(arguments.get("botao"))
        button = remote.buttons.get(name)
        if button is None:
            return ToolResult(False, f"{remote.name} não tem o botão {name!r} (botões: {', '.join(remote.buttons)}).")
        times = arguments.get("vezes", 1)
        if isinstance(times, bool) or not isinstance(times, int) or not 1 <= times <= MAX_PRESSES:
            return ToolResult(False, f"vezes precisa ser um inteiro de 1 a {MAX_PRESSES}.")

        for done in range(times):
            if done:
                await self._sleep(_GAP_SECONDS)
            try:
                await self._blaster.press(remote, button)
            except IrSendError as error:
                sent = f" (apertei {done} de {times} vezes antes)" if done else ""
                return ToolResult(False, f"Falhou ao apertar {name} em {remote.name}{sent}: {error}")
        plural = f" {times} vezes" if times > 1 else ""
        return ToolResult(True, f"{remote.name}: apertei {name}{plural} (sinal enviado; o aparelho não confirma).")
