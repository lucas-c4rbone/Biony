"""Lista os apps instalados num Fire Stick / Android TV (pelo ADB do Home Assistant) e sugere o que colar em
[players.<id>.apps] do config/casa.toml.

Rodar no servidor:  docker compose exec -T biony python -m biony.player_apps [entidade]
Só LÊ a lista de pacotes (pm list packages); não mostra chaves nem tokens.
"""

from __future__ import annotations

import asyncio
import sys

import httpx

from biony.config import Settings
from biony.tools.home_config import load_home_config

# Pacotes conhecidos → como o Lucas fala. Só aparecem os que estão instalados no aparelho.
KNOWN = {
    "com.netflix.ninja": "Netflix",
    "com.amazon.firetv.youtube": "YouTube",
    "com.amazon.amazonvideo.livingroom": "Prime Video",
    "com.spotify.tv.android": "Spotify",
    "com.disney.disneyplus": "Disney+",
    "com.wbd.stream": "Max",
    "com.hbo.hbonow": "HBO Max",
    "com.globo.globotv": "Globoplay",
    "com.apple.atve.amazon.appletv": "Apple TV",
    "tv.pluto.android": "Pluto TV",
    "com.crunchyroll.crunchyroid": "Crunchyroll",
    "com.plexapp.android": "Plex",
    "org.xbmc.kodi": "Kodi",
    "tv.twitch.android.app": "Twitch",
}


def parse_packages(response: str) -> list[str]:
    """Saída do `pm list packages` ("package:com.x" por linha) → lista de pacotes."""
    return sorted({line.strip().removeprefix("package:") for line in response.splitlines() if line.startswith("package:")})


def suggest(all_packages: list[str], user_packages: list[str]) -> tuple[dict[str, str], list[str]]:
    """(apps conhecidos instalados: nome → pacote, outros apps instalados pelo usuário sem nome conhecido)."""
    installed = set(all_packages) | set(user_packages)
    known = {name: package for package, name in KNOWN.items() if package in installed}
    others = [package for package in user_packages if package not in KNOWN]
    return known, others


async def adb(client: httpx.AsyncClient, entity: str, command: str) -> str:
    before = (await client.get(f"/api/states/{entity}")).json()["attributes"].get("adb_response")
    (await client.post("/api/services/androidtv/adb_command", json={"entity_id": entity, "command": command})).raise_for_status()
    for _ in range(20):
        await asyncio.sleep(0.5)
        response = (await client.get(f"/api/states/{entity}")).json()["attributes"].get("adb_response")
        if response and response != before:
            return str(response)
    raise TimeoutError(f"o Fire Stick não respondeu a '{command}' (está ligado e com a depuração ADB ativa?)")


async def main() -> int:
    settings = Settings()
    if not (settings.ha_url and settings.ha_token):
        print("Faltam HA_URL e HA_TOKEN no .env.")
        return 1
    entity = sys.argv[1] if len(sys.argv) > 1 else None
    if entity is None:
        players = load_home_config(settings.biony_home_config).players
        if not players:
            print("Passe a entidade (media_player....) ou cadastre um [players.x] no casa.toml.")
            return 1
        entity = next(iter(players.values())).entity
    headers = {"Authorization": "Bearer " + settings.ha_token.get_secret_value()}
    async with httpx.AsyncClient(base_url=settings.ha_url, headers=headers, timeout=20) as client:
        try:
            everything = parse_packages(await adb(client, entity, "pm list packages"))
            user_apps = parse_packages(await adb(client, entity, "pm list packages -3"))
        except (TimeoutError, httpx.HTTPError) as error:
            print(f"❌ {error}")
            return 1
    known, others = suggest(everything, user_apps)
    print(f"{entity}: {len(everything)} pacotes, {len(user_apps)} instalados por você.\n")
    print("Apps conhecidos neste aparelho (cole em [players.firetv.apps] do casa.toml):")
    for name, package in sorted(known.items()):
        print(f'"{name}" = "{package}"')
    if not known:
        print("  (nenhum dos apps conhecidos foi encontrado)")
    print("\nOutros apps que você instalou (se quiser abrir algum por voz, dê um nome e copie a linha):")
    for package in others:
        print(f'# "NOME" = "{package}"')
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
