"""Memória de longo prazo: fatos sobre o Lucas que valem para todas as conversas."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Memory:
    id: int
    content: str


def memory_context(memories: list[Memory]) -> str:
    """Bloco do prompt de sistema com o que o Biony sabe sobre o usuário."""
    if not memories:
        return "Você ainda não guardou nenhuma memória sobre o usuário."
    lines = "\n".join(f"- [{memory.id}] {memory.content}" for memory in memories)
    return f"O que você sabe sobre o usuário (memórias salvas; o número é o id):\n{lines}"
