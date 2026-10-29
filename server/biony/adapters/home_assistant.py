"""Cliente da API REST do Home Assistant."""

from __future__ import annotations

from typing import Any, Mapping

import httpx

from biony.tools.home import HomeAssistantError


class HomeAssistantClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_state(self, entity_id: str) -> Mapping[str, Any]:
        response = await self._request("GET", f"/api/states/{entity_id}")
        return response.json()

    async def call_service(self, domain: str, service: str, data: Mapping[str, Any]) -> None:
        await self._request("POST", f"/api/services/{domain}/{service}", json=dict(data))

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise HomeAssistantError(f"sem conexão com o Home Assistant ({error.__class__.__name__})") from error
        if response.status_code == 401:
            raise HomeAssistantError("token do Home Assistant inválido")
        if response.status_code == 404:
            raise HomeAssistantError(f"não encontrado no Home Assistant: {path}")
        if response.status_code >= 400:
            raise HomeAssistantError(f"HTTP {response.status_code}: {response.text[:200]}")
        return response
