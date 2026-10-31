from __future__ import annotations

from datetime import datetime, timezone

import pytest

from biony.adapters.sqlite_store import Database, SqliteSettingsStore
from biony.core.persona import PERSONALITIES, system_prompt
from biony.tools.personality import PersonalityTool, current_personality

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 31, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def store() -> SqliteSettingsStore:
    return SqliteSettingsStore(Database(":memory:"))


def test_prompt_uses_the_chosen_personality():
    serious = system_prompt("Lucas", NOW, personality="serio")
    assert PERSONALITIES["serio"][1] in serious
    assert PERSONALITIES["divertido"][1] not in serious
    # Nome desconhecido não quebra: volta ao padrão.
    assert PERSONALITIES["equilibrado"][1] in system_prompt("Lucas", NOW, personality="pirata")


async def test_tool_saves_and_engine_reads_it(store):
    assert current_personality(store) == "equilibrado"
    assert current_personality(store, default="jarvis") == "jarvis"
    result = await PersonalityTool(store).execute({"personalidade": "jarvis"})
    assert result.ok and "equilibrado para jarvis" in result.content
    assert current_personality(store) == "jarvis"
    assert not (await PersonalityTool(store).execute({"personalidade": "pirata"})).ok
    assert current_personality(store) == "jarvis"


def test_settings_store_overwrites(store):
    store.set("personalidade", "serio")
    store.set("personalidade", "divertido")
    assert store.get("personalidade") == "divertido"
    assert store.get("outra") is None
