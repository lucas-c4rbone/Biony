"""Cliente da Bot API do Telegram (só o que o Biony usa)."""

from __future__ import annotations

from typing import Any

import httpx

from biony.core.ports import NotificationError

MAX_MESSAGE = 4096  # limite do Telegram por mensagem


class TelegramError(NotificationError):
    pass


class TelegramClient:
    def __init__(self, token: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        # O token vai na URL (é assim na Bot API); nunca logue a URL completa.
        self._http = httpx.AsyncClient(base_url=f"https://api.telegram.org/bot{token}", timeout=70, transport=transport)
        self._files = httpx.AsyncClient(base_url=f"https://api.telegram.org/file/bot{token}", timeout=60, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()
        await self._files.aclose()

    async def send_message(self, chat_id: int, text: str) -> None:
        for start in range(0, max(len(text), 1), MAX_MESSAGE):
            await self._call("sendMessage", {"chat_id": chat_id, "text": text[start : start + MAX_MESSAGE] or "…"})

    async def send_typing(self, chat_id: int) -> None:
        await self._call("sendChatAction", {"chat_id": chat_id, "action": "typing"})

    async def get_updates(self, offset: int | None, timeout: int = 50) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        return await self._call("getUpdates", payload)

    async def download_file(self, file_id: str) -> bytes:
        info = await self._call("getFile", {"file_id": file_id})
        try:
            response = await self._files.get(f"/{info['file_path']}")
        except httpx.HTTPError as error:
            raise TelegramError(f"falha ao baixar arquivo do Telegram ({error.__class__.__name__})") from error
        if response.status_code != 200:
            raise TelegramError(f"falha ao baixar arquivo do Telegram (HTTP {response.status_code})")
        return response.content

    async def _call(self, method: str, payload: dict[str, Any]) -> Any:
        try:
            response = await self._http.post(f"/{method}", json=payload)
        except httpx.HTTPError as error:
            raise TelegramError(f"sem conexão com o Telegram ({error.__class__.__name__})") from error
        try:
            data = response.json()
        except ValueError as error:
            raise TelegramError(f"resposta inválida do Telegram (HTTP {response.status_code})") from error
        if not data.get("ok"):
            raise TelegramError(f"Telegram recusou {method}: {data.get('description', response.status_code)}")
        return data["result"]


class TelegramNotifier:
    def __init__(self, client: TelegramClient, chat_id: int) -> None:
        self._client = client
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        await self._client.send_message(self._chat_id, text)
