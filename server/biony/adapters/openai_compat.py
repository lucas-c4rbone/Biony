"""Cliente de chat no formato OpenAI (/chat/completions), usado com o OpenRouter."""

from __future__ import annotations

import json
from typing import Any, Sequence

import httpx

from biony.core.models import ChatMessage, LLMReply, Role, ToolCall
from biony.core.ports import LLMError
from biony.core.tools import ToolDefinition


class OpenAICompatClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
                # Identificação opcional do app no painel do OpenRouter.
                "X-Title": "Biony",
            },
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def chat(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolDefinition]
    ) -> LLMReply:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [_encode_message(message) for message in messages],
        }
        if tools:
            payload["tools"] = [_encode_tool(tool) for tool in tools]

        try:
            response = await self._http.post("/chat/completions", json=payload)
        except httpx.HTTPError as error:
            raise LLMError(f"Falha de rede ao chamar o LLM: {error}") from error
        if response.status_code != 200:
            raise LLMError(f"LLM respondeu HTTP {response.status_code}: {response.text[:500]}")

        try:
            data = response.json()
            # O OpenRouter às vezes responde 200 com um objeto de erro.
            if "error" in data:
                raise LLMError(f"Erro do LLM: {data['error']}")
            message = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise LLMError(f"Resposta inesperada do LLM: {response.text[:500]}") from error
        return _decode_reply(message)


def _encode_message(message: ChatMessage) -> dict[str, Any]:
    encoded: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.tool_calls:
        encoded["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)},
            }
            for call in message.tool_calls
        ]
    if message.role is Role.TOOL:
        encoded["tool_call_id"] = message.tool_call_id
    return encoded


def _encode_tool(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": tool.name, "description": tool.description, "parameters": dict(tool.parameters)},
    }


def _decode_reply(message: dict[str, Any]) -> LLMReply:
    calls = []
    for raw in message.get("tool_calls") or ():
        function = raw.get("function", {})
        arguments, error = _parse_arguments(function.get("arguments"))
        calls.append(ToolCall(raw["id"], function.get("name", ""), arguments, error))
    return LLMReply(content=message.get("content") or None, tool_calls=tuple(calls))


def _parse_arguments(raw: object) -> tuple[dict[str, Any], str | None]:
    if raw in (None, ""):
        return {}, None
    if isinstance(raw, dict):
        return raw, None
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError as error:
        return {}, f"JSON inválido ({error.msg})"
    if not isinstance(parsed, dict):
        return {}, "os argumentos precisam ser um objeto JSON"
    return parsed, None
