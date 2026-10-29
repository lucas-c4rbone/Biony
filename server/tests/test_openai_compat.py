from __future__ import annotations

import json

import httpx
import pytest

from biony.adapters.openai_compat import OpenAICompatClient
from biony.core.models import ChatMessage, Role, ToolCall
from biony.core.ports import LLMError
from biony.core.tools import ToolDefinition

pytestmark = pytest.mark.anyio


def client_returning(status: int, body: object, seen: list[httpx.Request]) -> OpenAICompatClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return OpenAICompatClient(
        base_url="https://llm.test/v1/", api_key="chave", model="modelo-x", transport=httpx.MockTransport(handler)
    )


async def test_sends_history_tools_and_parses_tool_calls():
    seen: list[httpx.Request] = []
    body = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {"id": "a", "type": "function", "function": {"name": "luz", "arguments": '{"on": true}'}},
                        {"id": "b", "type": "function", "function": {"name": "ar", "arguments": "{quebrado"}},
                    ],
                }
            }
        ]
    }
    client = client_returning(200, body, seen)
    history = [
        ChatMessage(Role.SYSTEM, "sistema"),
        ChatMessage(Role.USER, "liga"),
        ChatMessage(Role.ASSISTANT, None, (ToolCall("x", "luz", {"on": True}),)),
        ChatMessage(Role.TOOL, "ok", tool_call_id="x"),
    ]

    reply = await client.chat(history, [ToolDefinition("luz", "Liga a luz")])

    request = seen[0]
    assert request.url == "https://llm.test/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer chave"
    sent = json.loads(request.content)
    assert sent["model"] == "modelo-x"
    assert [m["role"] for m in sent["messages"]] == ["system", "user", "assistant", "tool"]
    assert sent["messages"][2]["tool_calls"][0]["function"] == {"name": "luz", "arguments": '{"on": true}'}
    assert sent["messages"][3]["tool_call_id"] == "x"
    assert sent["tools"][0]["function"]["name"] == "luz"

    assert reply.content is None
    assert reply.tool_calls[0] == ToolCall("a", "luz", {"on": True})
    assert reply.tool_calls[1].arguments_error is not None
    await client.aclose()


async def test_omits_tools_when_there_are_none():
    seen: list[httpx.Request] = []
    client = client_returning(200, {"choices": [{"message": {"content": "oi"}}]}, seen)

    reply = await client.chat([ChatMessage(Role.USER, "oi")], [])

    assert "tools" not in json.loads(seen[0].content)
    assert reply.content == "oi"


@pytest.mark.parametrize(
    "status, body",
    [
        (401, {"error": {"message": "chave inválida"}}),
        (200, {"error": {"message": "sem créditos"}}),
        (200, {"choices": []}),
    ],
)
async def test_errors_raise_llm_error(status, body):
    client = client_returning(status, body, [])

    with pytest.raises(LLMError):
        await client.chat([ChatMessage(Role.USER, "oi")], [])
