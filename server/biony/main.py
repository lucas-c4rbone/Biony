"""Monta o Biony a partir da configuração. Rodar com: uvicorn biony.main:app"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
import importlib.util
import logging

from fastapi import FastAPI

from biony.adapters.apscheduler_scheduler import APSchedulerScheduler
from biony.adapters.home_assistant import HomeAssistantClient
from biony.adapters.piper_tts import PiperTTS
from biony.adapters.whisper_stt import WhisperSTT
from biony.adapters.openai_compat import OpenAICompatClient
from biony.adapters.sqlite_store import (
    Database,
    SqliteConversationStore,
    SqliteMemoryStore,
    SqlitePresumedStateStore,
    SqliteReminderStore,
)
from biony.adapters.telegram import TelegramClient, TelegramNotifier
from biony.api.app import create_app
from biony.api.telegram_bot import TelegramBot
from biony.config import Settings
from biony.core.conversation import ConversationEngine
from biony.core.memory import memory_context
from biony.core.permissions import PermissionPolicy
from biony.core.reminder_service import ReminderService
from biony.core.reminders import NoticePolicy, QuietHours
from biony.core.tools import ToolRegistry
from biony.core.voice import VoiceAssistant, VoiceSlot
from biony.tools.home import HomeController, home_tools
from biony.tools.home_config import load_home_config
from biony.tools.memory import memory_tools
from biony.tools.tasks import task_tools

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

    telegram = None
    if settings.telegram_bot_token:
        telegram = TelegramClient(settings.telegram_bot_token.get_secret_value())
        cleanup.push_async_callback(telegram.aclose)
    notifier = TelegramNotifier(telegram, settings.telegram_chat_id) if telegram and settings.telegram_chat_id else None
    if notifier is None:
        log.warning("Telegram incompleto (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID): lembretes ficam salvos, mas não chegam.")

    scheduler = APSchedulerScheduler()
    reminders = ReminderService(
        SqliteReminderStore(db),
        scheduler,
        notifier,
        timezone=settings.timezone,
        policy=NoticePolicy(
            days_before=settings.deadline_days,
            at=settings.biony_deadline_time,
            quiet=QuietHours(settings.biony_quiet_start, settings.biony_quiet_end),
        ),
    )
    scheduler.callback = reminders.fire
    memories = SqliteMemoryStore(db)
    for tool in [*task_tools(reminders), *memory_tools(memories)]:
        tools.register(tool)

    engine = ConversationEngine(
        llm,
        SqliteConversationStore(db),
        tools,
        PermissionPolicy(),
        user_name=settings.biony_user_name,
        timezone=settings.timezone,
        history_limit=settings.biony_history_messages,
        extra_context=lambda: memory_context(memories.all()),
    )

    voice = VoiceSlot(enabled=settings.voice_enabled)
    if not settings.voice_enabled:
        log.warning("VOICE_ENABLED=false: /voz desativado.")
    else:
        _check_voice_dependencies()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        scheduler.start()
        log.info("Lembretes: %d pendente(s) reagendado(s).", reminders.restore())
        background = []
        if voice.enabled:
            background.append(asyncio.create_task(_load_voice(settings, engine, voice)))
        if telegram is not None:
            bot = TelegramBot(telegram, engine, voice, settings.telegram_chat_id)
            background.append(asyncio.create_task(bot.run()))
        async with cleanup:
            yield
            for task in background:
                task.cancel()
            scheduler.shutdown()

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


def _check_voice_dependencies() -> None:
    missing = [name for name in ("faster_whisper", "piper") if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError(
            f'Dependências de voz ausentes ({", ".join(missing)}): pip install -e ".[voz]" '
            "ou VOICE_ENABLED=false no .env."
        )


async def _load_voice(settings: Settings, engine: ConversationEngine, slot: VoiceSlot) -> None:
    """Carrega os modelos numa thread; o servidor já atende texto enquanto isso."""
    try:
        slot.assistant = await asyncio.to_thread(_build_voice, settings, engine)
        log.info("Voz pronta: /voz liberado.")
    except Exception as error:
        slot.error = str(error)
        log.exception("A voz não carregou; /voz vai responder 503.")


def _build_voice(settings: Settings, engine: ConversationEngine) -> VoiceAssistant:
    stt = WhisperSTT(
        model=settings.stt_model,
        models_dir=settings.biony_models_dir / "whisper",
        beam_size=settings.stt_beam_size,
    )
    tts = PiperTTS(voice=settings.tts_voice, voices_dir=settings.biony_models_dir / "piper")
    return VoiceAssistant(engine, stt, tts)


class _HideHealthChecks(logging.Filter):
    """O Docker chama /health a cada 30 s; não precisa poluir o log."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "GET /health" not in record.getMessage()


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("uvicorn.access").addFilter(_HideHealthChecks())
# O httpx loga a URL de cada requisição, e a URL da Bot API do Telegram contém o token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
app = build_app(Settings())
