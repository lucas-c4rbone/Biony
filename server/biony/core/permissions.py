"""Decide se uma ferramenta pode rodar, precisa de confirmação ou é bloqueada."""

from __future__ import annotations

from enum import Enum, auto

from biony.core.tools import ToolDefinition


class Decision(Enum):
    ALLOWED = auto()
    REQUIRES_CONFIRMATION = auto()
    DENIED = auto()


class PermissionPolicy:
    def __init__(self, denied: frozenset[str] = frozenset()) -> None:
        self._denied = denied

    def decide(self, tool: ToolDefinition, confirmed: bool = False) -> Decision:
        if tool.name in self._denied:
            return Decision.DENIED
        if tool.requires_confirmation and not confirmed:
            return Decision.REQUIRES_CONFIRMATION
        return Decision.ALLOWED
