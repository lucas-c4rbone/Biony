from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from biony.adapters.sqlite_store import Database, SqliteConversationStore
from biony.core.conversation import ConversationEngine
from biony.core.models import ChatMessage, LLMReply
from biony.core.permissions import PermissionPolicy
from biony.core.tools import Tool, ToolDefinition, ToolRegistry, ToolResult

TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class ScriptedLLM:
    """LLM falso: devolve as respostas na ordem e guarda o que recebeu."""

    def __init__(self, *replies: LLMReply) -> None:
        self.replies = list(replies)
        self.calls: list[list[ChatMessage]] = []

    async def chat(self, messages: Sequence[ChatMessage], tools: Sequence[ToolDefinition]) -> LLMReply:
        self.calls.append(list(messages))
        return self.replies.pop(0)


class RecordingTool(Tool):
    def __init__(self, name: str, *, requires_confirmation: bool = False, fail: bool = False) -> None:
        self.definition = ToolDefinition(name, f"Ferramenta {name}", requires_confirmation=requires_confirmation)
        self.executions: list[Mapping[str, Any]] = []
        self._fail = fail

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        self.executions.append(arguments)
        if self._fail:
            raise RuntimeError("quebrou")
        return ToolResult(True, f"{self.definition.name} feito")


@pytest.fixture
def store() -> SqliteConversationStore:
    return SqliteConversationStore(Database(":memory:"))


def make_engine(llm, store, *tools: Tool, history_limit: int = 30, max_tool_rounds: int = 5) -> ConversationEngine:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return ConversationEngine(
        llm,
        store,
        registry,
        PermissionPolicy(),
        user_name="Lucas",
        timezone=TZ,
        history_limit=history_limit,
        max_tool_rounds=max_tool_rounds,
        clock=lambda tz: datetime(2026, 10, 29, 15, 42, tzinfo=tz),
    )
