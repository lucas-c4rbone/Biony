"""Cliente da Tuya OpenAPI (nuvem): usado para apertar botões de controles IR virtuais.

Usa o SDK oficial (tuya-connector-python) por baixo. Uma versão própria com httpx gerava a mesma
assinatura e os mesmos cabeçalhos, mas a Tuya respondia "sign invalid" e o SDK, com a mesma chave
no mesmo minuto, era aceito. O SDK é síncrono, então as chamadas rodam numa thread.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import parse_qsl

import requests
from tuya_connector import TuyaOpenAPI

from biony.tools.home_config import IrButton, Remote
from biony.tools.ir_remote import IrSendError

# Data centers da Tuya. Contas do Brasil costumam ficar em "Western America" (us).
ENDPOINTS = {
    "us": "https://openapi.tuyaus.com",
    "eu": "https://openapi.tuyaeu.com",
    "cn": "https://openapi.tuyacn.com",
    "in": "https://openapi.tuyain.com",
}


class TuyaError(RuntimeError):
    pass


class TuyaCloud:
    def __init__(self, *, access_id: str, access_secret: str, region: str = "us", api: Any = None) -> None:
        if region not in ENDPOINTS:
            raise ValueError(f"TUYA_REGION precisa ser um de {', '.join(ENDPOINTS)}")
        # Espaços ou aspas sobrando ao copiar do site quebram a assinatura ("sign invalid").
        access_id = access_id.strip().strip('"').strip("'")
        access_secret = access_secret.strip().strip('"').strip("'")
        self._api = api or TuyaOpenAPI(ENDPOINTS[region], access_id, access_secret)
        self._lock = asyncio.Lock()  # a sessão do requests não é feita para uso simultâneo

    async def aclose(self) -> None:
        session = getattr(self._api, "session", None)
        if session is not None:
            session.close()

    async def connect(self) -> None:
        """Pede o token de acesso. As outras chamadas fazem isso sozinhas quando preciso."""
        async with self._lock:
            await asyncio.to_thread(self._connect)

    async def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        async with self._lock:
            return await asyncio.to_thread(self._request, method.upper(), path, body)

    def _connect(self) -> None:
        _check(_guard(self._api.connect), "/v1.0/token")

    def _request(self, method: str, path: str, body: dict[str, Any] | None) -> Any:
        if not self._api.is_connect():
            self._connect()
        path, _, query = path.partition("?")
        params = dict(parse_qsl(query)) or None
        if method == "GET":
            response = _guard(self._api.get, path, params)
        elif method == "DELETE":
            response = _guard(self._api.delete, path, params)
        elif method == "POST":
            response = _guard(self._api.post, path, body)
        elif method == "PUT":
            response = _guard(self._api.put, path, body)
        else:
            raise ValueError(f"método não suportado: {method}")
        return _check(response, path)


def _guard(call, *args) -> Any:
    try:
        return call(*args)
    except requests.RequestException as error:
        raise TuyaError(f"sem conexão com a Tuya ({error.__class__.__name__})") from error


def _check(response: Any, path: str) -> Any:
    if not response:  # o SDK devolve None quando o HTTP não é 2xx
        raise TuyaError(f"resposta inválida da Tuya em {path}")
    if not response.get("success"):
        raise TuyaError(f"Tuya recusou {path}: código {response.get('code')} — {response.get('msg')}")
    return response.get("result")


class TuyaIrBlaster:
    """Aperta botões de controles IR cadastrados no app Smart Life / Tuya."""

    def __init__(self, cloud: TuyaCloud) -> None:
        self._cloud = cloud

    async def press(self, remote: Remote, button: IrButton) -> None:
        base = f"/v2.0/infrareds/{remote.infrared_id}/remotes/{remote.remote_id}"
        try:
            # Comando padrão (controles da biblioteca da Tuya): category_id + key.
            await self._cloud.request("POST", f"{base}/command", {"category_id": remote.category_id, "key": button.key})
        except TuyaError as error:
            # Alguns controles só aceitam o comando "raw", pelo key_id.
            try:
                await self._cloud.request(
                    "POST", f"{base}/raw/command", {"category_id": remote.category_id, "key_id": button.key_id}
                )
            except TuyaError as raw_error:
                raise IrSendError(f"{error} / raw: {raw_error}") from raw_error
