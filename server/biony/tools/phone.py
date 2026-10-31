"""Ações no celular do Lucas (despertador, timer, lanterna, abrir app).

O servidor não mexe no celular: valida o pedido e o devolve junto da resposta (`client_actions`);
quem executa é o app Android do Biony (clients/android). Só aceita o pedido se o cliente da conversa
avisou que sabe executá-lo (capacidade "acoes_celular"); no Telegram ou no PC, a ferramenta recusa.
"""

from __future__ import annotations

from typing import Any, Mapping

from biony.core.tools import Tool, ToolDefinition, ToolResult, client_capabilities

CAPABILITY = "acoes_celular"
ACTIONS = ("despertador", "timer", "lanterna", "abrir_app")
DAYS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")
MAX_TIMER_SECONDS = 24 * 60 * 60
MAX_TEXT = 60


class PhoneActionTool(Tool):
    def __init__(self) -> None:
        self.definition = ToolDefinition(
            name="celular_acao",
            description=(
                "Faz algo no CELULAR do Lucas: cria um despertador, inicia um timer, liga/desliga a lanterna "
                "ou abre um aplicativo. Só funciona quando ele fala pelo app do Biony no celular; nos outros "
                "canais a ferramenta avisa que não dá. Só cria: não consegue listar nem apagar despertadores."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "acao": {"type": "string", "enum": list(ACTIONS)},
                    "hora": {"type": "integer", "minimum": 0, "maximum": 23, "description": "Despertador: hora (0-23). 17h = 17."},
                    "minuto": {"type": "integer", "minimum": 0, "maximum": 59, "description": "Despertador: minuto (padrão 0)."},
                    "dias": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(DAYS)},
                        "description": "Despertador: dias em que repete. Omita para tocar só na próxima vez.",
                    },
                    "mensagem": {"type": "string", "description": "Despertador ou timer: nome curto exibido (opcional)."},
                    "segundos": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_TIMER_SECONDS,
                        "description": "Timer: duração em segundos (5 minutos = 300).",
                    },
                    "ligar": {"type": "boolean", "description": "Lanterna: true liga, false desliga."},
                    "app": {"type": "string", "description": "Abrir app: nome como aparece no celular (ex.: WhatsApp)."},
                },
                "required": ["acao"],
            },
        )

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        if CAPABILITY not in client_capabilities.get():
            return ToolResult(
                False,
                "Este canal não controla o celular. Só dá para fazer isso falando pelo app do Biony no celular.",
            )
        action = arguments.get("acao")
        try:
            if action == "despertador":
                return _alarm(arguments)
            if action == "timer":
                return _timer(arguments)
            if action == "lanterna":
                return _flashlight(arguments)
            if action == "abrir_app":
                return _open_app(arguments)
        except ValueError as error:
            return ToolResult(False, str(error))
        return ToolResult(False, f"Ação desconhecida: {action} (use {', '.join(ACTIONS)}).")


def _integer(arguments: Mapping[str, Any], name: str, low: int, high: int, default: int | None = None) -> int:
    value = arguments.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} precisa ser um inteiro de {low} a {high} (veio {value!r}).")
    return value


def _text(arguments: Mapping[str, Any], name: str) -> str:
    return " ".join(str(arguments.get(name) or "").split())[:MAX_TEXT]


def _sent(content: str, **action: Any) -> ToolResult:
    return ToolResult(True, f"{content} Pedido enviado ao app do celular; ele executa agora.", (action,))


def _alarm(arguments: Mapping[str, Any]) -> ToolResult:
    hour = _integer(arguments, "hora", 0, 23)
    minute = _integer(arguments, "minuto", 0, 59, default=0)
    days = arguments.get("dias") or []
    if not isinstance(days, list) or not all(day in DAYS for day in days):
        raise ValueError(f"dias precisa ser uma lista com {', '.join(DAYS)}.")
    days = [day for day in DAYS if day in days]  # sem repetidos, em ordem
    message = _text(arguments, "mensagem")
    repeat = f", repetindo {', '.join(days)}" if days else ""
    return _sent(
        f"Despertador às {hour:02d}:{minute:02d}{repeat}.",
        tipo="despertador", hora=hour, minuto=minute, dias=days, mensagem=message,
    )


def _timer(arguments: Mapping[str, Any]) -> ToolResult:
    seconds = _integer(arguments, "segundos", 1, MAX_TIMER_SECONDS)
    return _sent(f"Timer de {seconds} segundos.", tipo="timer", segundos=seconds, mensagem=_text(arguments, "mensagem"))


def _flashlight(arguments: Mapping[str, Any]) -> ToolResult:
    turn_on = arguments.get("ligar")
    if not isinstance(turn_on, bool):
        raise ValueError("ligar precisa ser true ou false.")
    return _sent(f"Lanterna {'ligada' if turn_on else 'desligada'}.", tipo="lanterna", ligar=turn_on)


def _open_app(arguments: Mapping[str, Any]) -> ToolResult:
    name = _text(arguments, "app")
    if not name:
        raise ValueError("Faltou o nome do app.")
    return _sent(f"Abrir {name}.", tipo="abrir_app", app=name)
