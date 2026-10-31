from __future__ import annotations

import pytest

from biony.adapters.tuya_cloud import TuyaCloud, TuyaError

pytestmark = pytest.mark.anyio


class FakeApi:
    """Imita o TuyaOpenAPI do SDK oficial."""

    def __init__(self, fail: dict | None = None) -> None:
        self.calls = []
        self.connected = False
        self.fail = fail

    def connect(self):
        self.calls.append(("connect",))
        if self.fail:
            return self.fail
        self.connected = True
        return {"success": True, "result": {"access_token": "TOK"}}

    def is_connect(self):
        return self.connected

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        return {"success": True, "result": {"ok": 1}}

    def post(self, path, body=None):
        self.calls.append(("POST", path, body))
        return {"success": True, "result": True}


async def test_connects_once_and_splits_query():
    api = FakeApi()
    tuya = TuyaCloud(access_id="ID", access_secret="SEC", api=api)
    assert await tuya.request("GET", "/v2.0/x?page_size=20&a=b") == {"ok": 1}
    assert await tuya.request("post", "/v2.0/y", {"k": 1}) is True
    assert api.calls == [
        ("connect",),
        ("GET", "/v2.0/x", {"page_size": "20", "a": "b"}),
        ("POST", "/v2.0/y", {"k": 1}),
    ]


async def test_errors_are_raised():
    tuya = TuyaCloud(access_id="ID", access_secret="SEC",
                     api=FakeApi(fail={"success": False, "code": 1004, "msg": "sign invalid"}))
    with pytest.raises(TuyaError, match="1004"):
        await tuya.request("GET", "/v2.0/y")
    with pytest.raises(TuyaError, match="1004"):
        await tuya.connect()
