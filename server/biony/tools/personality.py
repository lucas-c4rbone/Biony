"""Personalidade do Biony: o Lucas troca o jeito de falar conversando."""

from __future__ import annotations

from typing import Any, Mapping

from biony.core.persona import DEFAULT_PERSONALITY, PERSONALITIES
from biony.core.ports import SettingsStore
from biony.core.tools import Tool, ToolDefinition, ToolResult

SETTING = "personalidade"


def current_personality(store: SettingsStore, default: str = DEFAULT_PERSONALITY) -> str:
    saved = store.get(SETTING)
    return saved if saved in PERSONALITIES else default


class PersonalityTool(Tool):
    def __init__(self, store: SettingsStore, default: str = DEFAULT_PERSONALITY) -> None:
        self._store = store
        self._default = default
        self.definition = ToolDefinition(
            name="personalidade_mudar",
            description=(
                "Muda o jeito de falar do Biony (vale para todas as conversas). Use quando o Lucas pedir "
                "para ficar mais sério, mais divertido, voltar ao normal, falar como o JARVIS etc."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "personalidade": {
                        "type": "string",
                        "enum": list(PERSONALITIES),
                        "description": "; ".join(f"{key} = {summary}" for key, (summary, _) in PERSONALITIES.items()),
                    }
                },
                "required": ["personalidade"],
            },
        )

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        chosen = str(arguments.get("personalidade"))
        if chosen not in PERSONALITIES:
            return ToolResult(False, f"Personalidade desconhecida: {chosen} (use {', '.join(PERSONALITIES)}).")
        previous = current_personality(self._store, self._default)
        self._store.set(SETTING, chosen)
        return ToolResult(
            True,
            f"Personalidade mudada de {previous} para {chosen} ({PERSONALITIES[chosen][0]}). "
            "Já responda esta mensagem no jeito novo.",
        )
