"""Cliente do agente do Biony que roda no PC (clients/pc-agente)."""

from __future__ import annotations

from typing import Any

import httpx

from biony.tools.pc import PcAgentError


class PcAgentClient:
    def __init__(self, *, base_url: str, token: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=4.0,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def status(self) -> dict[str, Any] | None:
        """None quando o PC não responde (desligado, dormindo ou sem rede)."""
        try:
            response = await self._http.get("/status")
        except httpx.HTTPError:
            return None
        if response.status_code == 401:
            raise PcAgentError("o agente do PC recusou o token (PC_AGENT_TOKEN errado?)")
        return response.json() if response.status_code == 200 else None

    async def shutdown(self, seconds: int) -> None:
        try:
            response = await self._http.post("/desligar", json={"segundos": seconds})
        except httpx.HTTPError as error:
            raise PcAgentError(f"o PC não respondeu ({error.__class__.__name__})") from error
        if response.status_code != 200:
            raise PcAgentError(f"o agente do PC recusou: {response.text[:200]}")
