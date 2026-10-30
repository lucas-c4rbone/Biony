"""Ferramentas da memória de longo prazo."""

from __future__ import annotations

from typing import Any, Mapping

from biony.core.ports import MemoryStore
from biony.core.tools import Tool, ToolDefinition, ToolResult

MAX_MEMORY = 500


class MemorySaveTool(Tool):
    def __init__(self, store: MemoryStore) -> None:
        self._store = store
        self.definition = ToolDefinition(
            name="memoria_salvar",
            description=(
                "Guarda um fato duradouro sobre o Lucas para lembrar em todas as conversas: matérias, "
                "professores, horários da rotina, preferências, pessoas, gostos. Salve quando ele contar "
                "algo assim ou pedir para lembrar. Não salve coisas passageiras nem tarefas com prazo "
                "(essas vão em tarefa_criar). Escreva o fato completo e curto, em terceira pessoa."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "fato": {"type": "string", "description": "Ex.: 'Faz Cálculo 2 com o professor Marcos às terças, 19h'"}
                },
                "required": ["fato"],
            },
        )

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        fact = " ".join(str(arguments.get("fato", "")).split())
        if not fact:
            return ToolResult(False, "Faltou o fato a guardar.")
        if len(fact) > MAX_MEMORY:
            return ToolResult(False, f"Fato longo demais ({len(fact)} caracteres); resuma em até {MAX_MEMORY}.")
        memory = self._store.add(fact)
        return ToolResult(True, f"Memória {memory.id} guardada: {memory.content}")


class MemoryForgetTool(Tool):
    def __init__(self, store: MemoryStore) -> None:
        self._store = store
        self.definition = ToolDefinition(
            name="memoria_esquecer",
            description=(
                "Apaga uma memória pelo id (os ids estão na lista de memórias do prompt). Use quando o Lucas "
                "pedir para esquecer algo ou quando um fato mudou (apague o antigo e salve o novo)."
            ),
            parameters={"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
            requires_confirmation=True,
        )

    def describe(self, arguments: Mapping[str, Any]) -> str:
        memory = next((m for m in self._store.all() if m.id == arguments.get("id")), None)
        return f"esquecer que \"{memory.content}\"" if memory else "esquecer uma memória que não encontrei"

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        if not self._store.remove(int(arguments.get("id", -1))):
            return ToolResult(False, "Não achei essa memória.")
        return ToolResult(True, "Memória apagada.")


def memory_tools(store: MemoryStore) -> list[Tool]:
    return [MemorySaveTool(store), MemoryForgetTool(store)]
