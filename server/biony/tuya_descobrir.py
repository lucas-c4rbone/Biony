"""Lista os aparelhos da conta Tuya e os botões de cada controle IR.

Rodar no servidor:  docker compose exec biony python -m biony.tuya_descobrir
Não mostra chaves nem tokens: só nomes, ids e botões (pode colar a saída no chat).
"""

from __future__ import annotations

import asyncio
import sys

from biony.adapters.tuya_cloud import ENDPOINTS, TuyaCloud, TuyaError
from biony.config import Settings


async def list_devices(tuya: TuyaCloud) -> list[dict]:
    # Endpoints de listagem mudam entre versões da API; tenta os mais comuns.
    attempts = ["/v2.0/cloud/thing/device?page_size=20", "/v1.3/iot-03/devices?page_size=20"]
    errors = []
    for path in attempts:
        try:
            result = await tuya.request("GET", path)
        except TuyaError as error:
            errors.append(str(error))
            continue
        if isinstance(result, dict):
            result = result.get("list") or result.get("devices") or []
        return list(result or [])
    raise TuyaError("não consegui listar os aparelhos: " + " | ".join(errors))


async def main() -> int:
    settings = Settings()
    if not (settings.tuya_access_id and settings.tuya_access_secret):
        print("Faltam TUYA_ACCESS_ID e TUYA_ACCESS_SECRET no .env.")
        return 1
    tuya = TuyaCloud(
        access_id=settings.tuya_access_id,
        access_secret=settings.tuya_access_secret.get_secret_value(),
        region=settings.tuya_region,
    )
    access_id = settings.tuya_access_id.strip()
    secret = settings.tuya_access_secret.get_secret_value().strip()
    print(f"Access ID: {len(access_id)} caracteres · Access Secret: {len(secret)} caracteres · região: {settings.tuya_region}")
    if "*" in secret:
        print("⚠️  O Access Secret tem '*': ele foi copiado escondido. Clique no olho no site antes de copiar.")
    try:
        await tuya.request("GET", "/v1.0/token?grant_type=1")
        print("✅ Conectado à Tuya.\n")
        devices = await list_devices(tuya)
        print(f"Aparelhos na conta ({len(devices)}):")
        for device in devices:
            print(f"  - {device.get('name')} | id={device.get('id')} | categoria={device.get('category')}")
        print()
        found = False
        for device in devices:
            try:
                remotes = await tuya.request("GET", f"/v2.0/infrareds/{device['id']}/remotes")
            except TuyaError:
                continue  # não é um controle IR
            found = True
            print(f"📡 IR: {device.get('name')} (infrared_id={device['id']})")
            for remote in remotes or []:
                rid = remote.get("remote_id")
                print(f"   🎛  {remote.get('remote_name')} | remote_id={rid} | category_id={remote.get('category_id')}")
                try:
                    keys = await tuya.request("GET", f"/v2.0/infrareds/{device['id']}/remotes/{rid}/keys")
                except TuyaError as error:
                    print(f"      (não consegui ler os botões: {error})")
                    continue
                for key in (keys or {}).get("key_list", []):
                    print(f"      - {key.get('key_name')} | key={key.get('key')} | key_id={key.get('key_id')}")
            print()
        if not found:
            print("Nenhum controle IR encontrado. O IR está vinculado na conta (Devices → Link App Account)?")
        return 0
    except TuyaError as error:
        print(f"❌ {error}")
        if "1004" in str(error):
            # Chave certa no data center errado também dá "sign invalid": testa os outros.
            print("\nTestando variações (data center e assinatura sem nonce)...")
            for region in ENDPOINTS:
                for use_nonce in (True, False):
                    if region == settings.tuya_region and use_nonce:
                        continue
                    other = TuyaCloud(access_id=access_id, access_secret=secret, region=region, use_nonce=use_nonce)
                    label = region if use_nonce else f"{region} sem nonce"
                    try:
                        await other.request("GET", "/v1.0/token?grant_type=1")
                        print(f"✅ Funcionou: {label}. Me avise esse resultado.")
                        return 1
                    except TuyaError as other_error:
                        print(f"   {label}: {other_error}")
                    finally:
                        await other.aclose()
            print("\nNenhuma região aceitou. Confira se copiou o Access ID e o Access Secret do MESMO projeto,")
            print("na aba Overview (o Secret aparece só depois de clicar no ícone de olho).")
        return 1
    finally:
        await tuya.aclose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
