from __future__ import annotations

import json

import httpx
import pytest

from biony.adapters.home_assistant import HomeAssistantClient
from biony.tools.home import HomeAssistantError

pytestmark = pytest.mark.anyio


def client(handler) -> HomeAssistantClient:
    return HomeAssistantClient(base_url="http://ha.test:8123/", token="tok", transport=httpx.MockTransport(handler))


async def test_call_service_and_get_state():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"entity_id": "light.x", "state": "on"})
        return httpx.Response(200, json=[])

    ha = client(handler)
    await ha.call_service("light", "turn_on", {"entity_id": "light.x", "brightness_pct": 50})
    state = await ha.get_state("light.x")

    assert seen[0].url == "http://ha.test:8123/api/services/light/turn_on"
    assert seen[0].headers["Authorization"] == "Bearer tok"
    assert json.loads(seen[0].content) == {"entity_id": "light.x", "brightness_pct": 50}
    assert seen[1].url == "http://ha.test:8123/api/states/light.x"
    assert state["state"] == "on"
    await ha.aclose()


@pytest.mark.parametrize("status, message", [(401, "token"), (404, "não encontrado"), (500, "HTTP 500")])
async def test_http_errors_become_home_assistant_error(status, message):
    ha = client(lambda request: httpx.Response(status, text="erro"))

    with pytest.raises(HomeAssistantError, match=message):
        await ha.get_state("light.x")


async def test_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("recusado")

    with pytest.raises(HomeAssistantError, match="sem conexão"):
        await client(handler).call_service("light", "turn_on", {})
