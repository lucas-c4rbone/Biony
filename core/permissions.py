"""Decisões básicas de permissão para ferramentas do Biony Core."""

from __future__ import annotations

from enum import Enum, auto
from typing import Protocol

from core.tools import ToolDefinition


class PermissionDecision(Enum):
    """Resultado de uma verificação de permissão para uma ferramenta."""

    ALLOWED = auto()
    REQUIRES_CONFIRMATION = auto()
    DENIED = auto()


class PermissionPolicy(Protocol):
    """Contrato para políticas substituíveis de permissão."""

    def decide(self, tool: ToolDefinition, confirmed: bool = False) -> PermissionDecision:
        """Decide se uma ferramenta pode ser executada."""


class SimplePermissionPolicy:
    """Aplica bloqueios explícitos e a confirmação declarada pela ferramenta."""

    def __init__(self, denied_tool_names: frozenset[str] = frozenset()) -> None:
        self._denied_tool_names = denied_tool_names

    def decide(self, tool: ToolDefinition, confirmed: bool = False) -> PermissionDecision:
        if tool.name in self._denied_tool_names:
            return PermissionDecision.DENIED
        if tool.requires_confirmation and not confirmed:
            return PermissionDecision.REQUIRES_CONFIRMATION
        return PermissionDecision.ALLOWED