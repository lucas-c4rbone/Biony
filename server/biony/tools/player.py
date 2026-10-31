"""Players de mídia do Home Assistant (ex.: o Fire Stick da TV): pausar, continuar, pular, abrir app.

Só controla o que está em [players] do config/casa.toml, e só abre os apps listados ali (nome falado → pacote).
"""

from __future__ import annotations

from typing import Any, Mapping

from biony.core.tools import Tool, ToolDefinition, ToolResult
from biony.tools.home import HomeAssistant, HomeAssistantError
from biony.tools.home_config import Player

# Ação → serviço media_player.* do HA. Nada fora desta lista chega ao aparelho.
SERVICES = {
    "pausar": "media_pause",
    "continuar": "media_play",
    "proxima": "media_next_track",
    "anterior": "media_previous_track",
    "parar": "media_stop",
    "ligar": "turn_on",
    "desligar": "turn_off",
}
OPEN_APP = "abrir_app"
STATE_WORDS = {
    "playing": "tocando", "paused": "pausado", "idle": "parado", "standby": "em repouso",
    "on": "ligado", "off": "desligado", "unavailable": "indisponível",
}


def describe_state(state: Mapping[str, Any], player: Player) -> str:
    value = state.get("state")
    text = f"{player.name}: {STATE_WORDS.get(value, value)}"
    package = state.get("attributes", {}).get("source")
    if package and value not in ("unavailable", "off"):
        names = {pkg: name for name, pkg in player.apps.items()}
        text += f", no app {names.get(package, package)}"
    return text


class PlayerTool(Tool):
    def __init__(self, ha: HomeAssistant, players: Mapping[str, Player]) -> None:
        self._ha = ha
        self._players = players
        self.definition = ToolDefinition(
            name="player_controlar",
            description=(
                "Controla um player de mídia (ex.: o Fire Stick da TV): pausa, continua, pula faixa/episódio, "
                "para, acorda ou põe em repouso e abre aplicativos. Para pausar ou continuar vídeo e música "
                "nele, use ESTA ferramenta (nunca o mudo nem o OK da TV). Não mexe no volume nem liga a TV."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "player": {
                        "type": "string",
                        "enum": list(players),
                        "description": "; ".join(
                            f"{key} = {p.name}" + (f" ({p.note})" if p.note else "") for key, p in players.items()
                        ),
                    },
                    "acao": {
                        "type": "string",
                        "enum": [*SERVICES, OPEN_APP],
                        "description": (
                            "pausar, continuar (despausar), proxima, anterior, parar, ligar (acorda), "
                            "desligar (repouso) ou abrir_app (precisa do campo app)."
                        ),
                    },
                    "app": {
                        "type": "string",
                        "enum": sorted({name for p in players.values() for name in p.apps}) or ["(nenhum)"],
                        "description": "Só com acao=abrir_app: nome do aplicativo. "
                        + "; ".join(f"{key}: {', '.join(p.apps) or 'nenhum configurado'}" for key, p in players.items()),
                    },
                },
                "required": ["player", "acao"],
            },
        )

    def describe(self, arguments: Mapping[str, Any]) -> str:
        return f"{arguments.get('acao')} no player {arguments.get('player')}"

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        player = self._players.get(str(arguments.get("player")))
        if player is None:
            return ToolResult(False, f"Player desconhecido: {arguments.get('player')}.")
        action = str(arguments.get("acao"))
        data: dict[str, Any] = {"entity_id": player.entity}
        if action == OPEN_APP:
            name = str(arguments.get("app") or "")
            package = player.apps.get(name)
            if package is None:
                available = ", ".join(player.apps) or "nenhum configurado"
                return ToolResult(False, f"{player.name} não tem o app {name!r} cadastrado (apps: {available}).")
            service, data["source"] = "select_source", package
        elif action in SERVICES:
            service = SERVICES[action]
        else:
            return ToolResult(False, f"Ação inválida: {action}.")

        try:
            state = await self._ha.get_state(player.entity)
            if state.get("state") == "unavailable":
                return ToolResult(
                    False,
                    f"{player.name} está indisponível no Home Assistant (sem energia, fora da rede ou com a "
                    "depuração ADB desligada).",
                )
            await self._ha.call_service("media_player", service, data)
        except HomeAssistantError as error:
            return ToolResult(False, f"O Home Assistant falhou com {player.name}: {error}")
        extra = f" ({arguments.get('app')})" if action == OPEN_APP else ""
        return ToolResult(
            True,
            f"{player.name}: {action}{extra} enviado. O estado pode levar alguns segundos para atualizar; "
            "não afirme que pausou/continuou sem confirmar em casa_estado.",
        )
