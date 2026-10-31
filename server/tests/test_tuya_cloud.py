from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from biony.adapters.tuya_cloud import TuyaCloud, TuyaError, sign, string_to_sign

pytestmark = pytest.mark.anyio


def test_string_to_sign_format():
    assert string_to_sign("get", "/v1.0/token?grant_type=1", b"") == (
        "GET\n" + hashlib.sha256(b"").hexdigest() + "\n\n/v1.0/token?grant_type=1"
    )
    assert sign("segredo", "abc") == sign("segredo", "abc").upper() and len(sign("segredo", "abc")) == 64


async def test_token_then_signed_request_and_token_reuse():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/v1.0/token":
            return httpx.Response(200, json={"success": True, "result": {"access_token": "TOK", "expire_time": 7200}})
        return httpx.Response(200, json={"success": True, "result": {"ok": 1}})

    tuya = TuyaCloud(access_id="ID", access_secret="SEC", transport=httpx.MockTransport(handler), clock=lambda: 1000.0)
    assert await tuya.request("POST", "/v2.0/x", {"a": 1}) == {"ok": 1}
    assert await tuya.request("GET", "/v2.0/y") == {"ok": 1}

    token_req, call = seen[0], seen[1]
    assert token_req.headers["access_token"] == "" and "nonce" not in token_req.headers
    assert call.headers["access_token"] == "TOK" and call.headers["client_id"] == "ID"
    body = call.content
    expected = sign("SEC", "ID" + "TOK" + call.headers["t"] + string_to_sign("POST", "/v2.0/x", body))
    assert call.headers["sign"] == expected
    assert json.loads(body) == {"a": 1}
    assert len(seen) == 3  # o token foi reaproveitado


async def test_errors_are_raised():
    tuya = TuyaCloud(access_id="ID", access_secret="SEC",
                     transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"success": False, "code": 1004, "msg": "sign invalid"})))
    with pytest.raises(TuyaError, match="1004"):
        await tuya.request("GET", "/v2.0/y")
