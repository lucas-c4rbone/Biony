"""Monta o Biony a partir da configuração. Rodar com: uvicorn biony.main:app"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
import importlib.util
import logging

from fastapi import FastAPI

from biony.adapters.home_assistant import HomeAssistantClient
from biony.adapters.piper_tts import PiperTTS
from biony.adapters.whisper_stt import WhisperSTT
from biony.adapters.openai_compat import OpenAICompatClient
from biony.adapters.sqlite_store import Database, SqliteConversationStore, SqlitePresumedStateStore
from biony.api.app import create_app
from biony.config import Settings
from biony.core.conversation import ConversationEngine
from biony.core.permissions import PermissionPolicy
from biony.core.tools import ToolRegistry
from biony.core.voice import VoiceAssistant
from biony.tools.home import HomeController, home_tools
from biony.tools.home_config import load_home_config

log = logging.getLogger("biony")


def build_app(settings: Settings) -> FastAPI:
    cleanup = AsyncExitStack()
    db = Database(settings.biony_db_path)
    cleanup.callback(db.close)
    llm = OpenAICompatClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
        timeout=settings.llm_timeout,
    )
    cleanup.push_async_callback(llm.aclose)

    tools = ToolRegistry()
    _register_home_tools(settings, db, tools, cleanup)

    engine = ConversationEngine(
        llm,
        SqliteConversationStore(db),
        tools,
        PermissionPolicy(),
        user_name=settings.biony_user_name,
        timezone=settings.timezone,
        history_limit=settings.biony_history_messages,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async with cleanup:
            yield

    voice = _build_voice(settings, engine)
    return create_app(engine, settings.biony_api_token.get_secret_value(), voice, lifespan)


def _register_home_tools(settings: Settings, db: Database, tools: ToolRegistry, cleanup: AsyncExitStack) -> None:
    if not (settings.ha_url and settings.ha_token):
        log.warning("HA_URL/HA_TOKEN não configurados: ferramentas da casa desligadas.")
        return
    if not settings.biony_home_config.exists():
        log.warning("%s não existe: ferramentas da casa desligadas.", settings.biony_home_config)
        return

    # Config inválido derruba a inicialização de propósito: melhor um erro claro que uma casa pela metade.
    config = load_home_config(settings.biony_home_config)
    ha = HomeAssistantClient(
        base_url=settings.ha_url, token=settings.ha_token.get_secret_value(), timeout=settings.ha_timeout
    )
    cleanup.push_async_callback(ha.aclose)
    for tool in home_tools(HomeController(ha, config, SqlitePresumedStateStore(db))):
        tools.register(tool)
    log.info(
        "Casa: %d dispositivo(s), %d rotina(s) de %s.",
        len(config.devices), len(config.routines), settings.biony_home_config,
    )


def _build_voice(settings: Settings, engine: ConversationEngine) -> VoiceAssistant | None:
    if not settings.voice_enabled:
        log.warning("VOICE_ENABLED=false: /voz desativado.")
        return None
    missing = [name for name in ("faster_whisper", "piper") if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError(
            f'Dependências de voz ausentes ({", ".join(missing)}): pip install -e ".[voz]" '
            "ou VOICE_ENABLED=false no .env."
        )
    stt = WhisperSTT(
        model=settings.stt_model,
        models_dir=settings.biony_models_dir / "whisper",
        beam_size=settings.stt_beam_size,
    )
    tts = PiperTTS(voice=settings.tts_voice, voices_dir=settings.biony_models_dir / "piper")
    return VoiceAssistant(engine, stt, tts)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = build_app(Settings())
