"""Porta e armazenamento temporário de memórias do Biony Core."""

from __future__ import annotations

from typing import Protocol

from core.models import Memory


class MemoryStore(Protocol):
    """Contrato para o armazenamento de memórias do Core."""

    def save(self, memory: Memory) -> None:
        """Salva uma memória."""

    def search(self, query: str) -> list[Memory]:
        """Retorna as memórias que correspondem a uma busca textual."""

    def list_all(self) -> list[Memory]:
        """Retorna todas as memórias salvas."""

    def remove(self, memory: Memory) -> bool:
        """Remove uma memória e informa se ela estava armazenada."""

    def clear(self) -> None:
        """Remove todas as memórias salvas."""


class InMemoryMemoryStore:
    """Armazena memórias em RAM para desenvolvimento e testes."""

    def __init__(self) -> None:
        self._memories: list[Memory] = []

    def save(self, memory: Memory) -> None:
        self._memories.append(memory)

    def search(self, query: str) -> list[Memory]:
        normalized_query = query.casefold()
        return [memory for memory in self._memories if normalized_query in memory.content.casefold()]

    def list_all(self) -> list[Memory]:
        return list(self._memories)

    def remove(self, memory: Memory) -> bool:
        try:
            self._memories.remove(memory)
        except ValueError:
            return False
        return True

    def clear(self) -> None:
        self._memories.clear()