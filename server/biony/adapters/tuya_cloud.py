"""Cliente da Tuya OpenAPI (nuvem): usado para apertar botões de controles IR virtuais.

Autenticação: cada requisição é assinada com HMAC-SHA256 (Access ID + Access Secret do projeto
em iot.tuya.com). O token de acesso é pedido na primeira chamada e renovado sozinho.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any
import uuid

import httpx

log = logging.getLogger(__name__)

# Data centers da Tuya. Contas do Brasil costumam ficar em "Western America" (us).
ENDPOINTS = {
    "us": "https://openapi.tuyaus.com",
    "eu": "https://openapi.tuyaeu.com",
    "cn": "https://openapi.tuyacn.com",
    "in": "https://openapi.tuyain.com",
}


class TuyaError(RuntimeError):
    pass


def string_to_sign(method: str, path: str, body: bytes) -> str:
    """Formato da Tuya: método, SHA-256 do corpo, cabeçalhos assinados (nenhum) e URL."""
    return "\n".join([method.upper(), hashlib.sha256(body).hexdigest(), "", path])


def sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest().upper()


class TuyaCloud:
    def __init__(
        self,
        *,
        access_id: str,
        access_secret: str,
        region: str = "us",
        transport: httpx.AsyncBaseTransport | None = None,
        clock=time.time,
    ) -> None:
        if region not in ENDPOINTS:
            raise ValueError(f"TUYA_REGION precisa ser um de {', '.join(ENDPOINTS)}")
        # Espaços ou aspas sobrando ao copiar do site quebram a assinatura ("sign invalid").
        self._id = access_id.strip().strip('"').strip("'")
        self._secret = access_secret.strip().strip('"').strip("'")
        self._clock = clock
        self._http = httpx.AsyncClient(base_url=ENDPOINTS[region], timeout=10.0, transport=transport)
        self._token: str | None = None
        self._token_expires = 0.0

    async def aclose(self) -> None:
        await self._http.aclose()

    async def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        token = await self._access_token()
        return await self._send(method, path, body, token)

    async def _access_token(self) -> str:
        if self._token and self._clock() < self._token_expires - 60:
            return self._token
        result = await self._send("GET", "/v1.0/token?grant_type=1", None, None)
        self._token = result["access_token"]
        self._token_expires = self._clock() + float(result.get("expire_time", 3600))
        return self._token

    async def _send(self, method: str, path: str, body: dict[str, Any] | None, token: str | None) -> Any:
        raw = json.dumps(body, separators=(",", ":")).encode() if body is not None else b""
        t = str(int(self._clock() * 1000))
        nonce = uuid.uuid4().hex
        prefix = self._id + (token or "") + t + nonce
        headers = {
            "client_id": self._id,
            "t": t,
            "nonce": nonce,
            "sign_method": "HMAC-SHA256",
            "sign": sign(self._secret, prefix + string_to_sign(method, path, raw)),
        }
        if token:
            headers["access_token"] = token
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            response = await self._http.request(method, path, content=raw or None, headers=headers)
        except httpx.HTTPError as error:
            raise TuyaError(f"sem conexão com a Tuya ({error.__class__.__name__})") from error
        try:
            data = response.json()
        except ValueError as error:
            raise TuyaError(f"resposta inválida da Tuya (HTTP {response.status_code})") from error
        if not data.get("success"):
            if data.get("code") in (1010, 1011):  # token expirado/inválido: pede outro na próxima
                self._token = None
            raise TuyaError(f"Tuya recusou {path.split('?')[0]}: código {data.get('code')} — {data.get('msg')}")
        return data.get("result")
