from biony.adapters.sqlite_store import Database, SqliteConversationStore
from biony.core.models import ChatMessage, Role, ToolCall


def test_roundtrip_keeps_tool_calls(store):
    calls = (ToolCall("c1", "luz", {"cor": "azul", "brilho": 80}),)
    store.append("s1", ChatMessage(Role.USER, "liga"))
    store.append("s1", ChatMessage(Role.ASSISTANT, None, calls))
    store.append("s1", ChatMessage(Role.TOOL, "ok", tool_call_id="c1"))

    assert store.recent("s1", 10) == [
        ChatMessage(Role.USER, "liga"),
        ChatMessage(Role.ASSISTANT, None, calls),
        ChatMessage(Role.TOOL, "ok", tool_call_id="c1"),
    ]


def test_recent_returns_last_messages_in_order(store):
    for index in range(5):
        store.append("s1", ChatMessage(Role.USER, str(index)))
    store.append("s2", ChatMessage(Role.USER, "outra"))

    assert [m.content for m in store.recent("s1", 2)] == ["3", "4"]


def test_history_survives_restart(tmp_path):
    path = tmp_path / "sub" / "biony.sqlite3"
    db = Database(path)
    SqliteConversationStore(db).append("s1", ChatMessage(Role.USER, "lembra disso"))
    db.close()

    reopened = Database(path)

    assert SqliteConversationStore(reopened).recent("s1", 5)[0].content == "lembra disso"
    assert reopened.connection.execute("PRAGMA user_version").fetchone()[0] == 2
    reopened.close()
