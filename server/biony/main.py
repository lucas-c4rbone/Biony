"""Monta o Biony a partir da configuração. Rodar com: uvicorn biony.main:app"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
import importlib.util
import logging

from fastapi import FastAPI

from biony.adapters.apscheduler_scheduler import APSchedulerScheduler
from biony.adapters.groq_stt import GroqSTT
from biony.adapters.home_assistant import HomeAssistantClient
from biony.adapters.pc_agent import PcAgentClient
from biony.adapters.tuya_cloud import TuyaCloud, TuyaIrBlaster
from biony.adapters.piper_tts import PiperTTS
from biony.adapters.whisper_stt import WhisperSTT
from biony.adapters.openai_compat import OpenAICompatClient
from biony.adapters.sqlite_store import (
    Database,
    SqliteConversationStore,
    SqliteLoginTokenStore,
    SqliteMemoryStore,
    SqlitePresumedStateStore,
    SqliteReminderStore,
)
from biony.adapters.telegram import TelegramClient, TelegramNotifier
from biony.api.app import create_app
from biony.api.auth import Auth
from biony.api.telegram_bot import TelegramBot
from biony.config import Settings
from biony.core.conversation import ConversationEngine
from biony.core.memory import memory_context
from biony.core.permissions import PermissionPolicy
from biony.core.reminder_service import ReminderService
from biony.core.reminders import NoticePolicy, QuietHours
from biony.core.tools import ToolRegistry
from biony.core.voice import FallbackSpeechToText, VoiceAssistant, VoiceSlot
from biony.tools.home import HomeController, home_tools
from biony.tools.home_config import load_home_config
from biony.tools.ir_remote import RemotePressTool
from biony.tools.memory import memory_tools
from biony.tools.pc import PcController, pc_tools
from biony.tools.server_status import ServerStatusTool
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
    home = _register_home_tools(settings, db, tools, cleanup)
    _register_remote_tools(settings, tools, cleanup)

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
    status = ServerStatusTool(disk_path=settings.biony_db_path.parent)
    for tool in [*task_tools(reminders), *memory_tools(memories), status]:
        tools.register(tool)
    _register_pc_tools(settings, home, notifier, tools, cleanup)

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

    password = settings.biony_password.get_secret_value() if settings.biony_password else None
    if password is None:
        log.warning("BIONY_PASSWORD não definida: login da PWA desativado.")
    auth = Auth(settings.biony_api_token.get_secret_value(), SqliteLoginTokenStore(db), password)
    return create_app(engine, auth, voice, lifespan)


def _register_pc_tools(
    settings: Settings, home: HomeController | None, notifier, tools: ToolRegistry, cleanup: AsyncExitStack
) -> None:
    if not (settings.pc_agent_url and settings.pc_agent_token):
        log.warning("PC_AGENT_URL/PC_AGENT_TOKEN não configurados: ligar/desligar o PC desativado.")
        return
    agent = PcAgentClient(base_url=settings.pc_agent_url, token=settings.pc_agent_token.get_secret_value())
    cleanup.push_async_callback(agent.aclose)
    pc = PcController(agent, home, settings.pc_setup_device, notifier)
    if home is not None:
        home.pc = pc  # rotinas podem ligar/desligar o PC
    for tool in pc_tools(pc):
        tools.register(tool)
    log.info("PC: agente em %s, filtro = %s.", settings.pc_agent_url, settings.pc_setup_device)


def _register_remote_tools(settings: Settings, tools: ToolRegistry, cleanup: AsyncExitStack) -> None:
    if not settings.biony_home_config.exists():
        return
    remotes = load_home_config(settings.biony_home_config).remotes
    if not remotes:
        return
    if not (settings.tuya_access_id and settings.tuya_access_secret):
        log.warning("casa.toml tem [controles], mas faltam TUYA_ACCESS_ID/TUYA_ACCESS_SECRET: controles IR desligados.")
        return
    cloud = TuyaCloud(
        access_id=settings.tuya_access_id,
        access_secret=settings.tuya_access_secret.get_secret_value(),
        region=settings.tuya_region,
    )
    cleanup.push_async_callback(cloud.aclose)
    tools.register(RemotePressTool(TuyaIrBlaster(cloud), remotes))
    log.info("Controles IR (Tuya): %s.", ", ".join(remotes))


def _register_home_tools(
    settings: Settings, db: Database, tools: ToolRegistry, cleanup: AsyncExitStack
) -> HomeController | None:
    if not (settings.ha_url and settings.ha_token):
        log.warning("HA_URL/HA_TOKEN não configurados: ferramentas da casa desligadas.")
        return None
    if not settings.biony_home_config.exists():
        log.warning("%s não existe: ferramentas da casa desligadas.", settings.biony_home_config)
        return None

    # Config inválido derruba a inicialização de propósito: melhor um erro claro que uma casa pela metade.
    config = load_home_config(settings.biony_home_config)
    ha = HomeAssistantClient(
        base_url=settings.ha_url, token=settings.ha_token.get_secret_value(), timeout=settings.ha_timeout
    )
    cleanup.push_async_callback(ha.aclose)
    controller = HomeController(ha, config, SqlitePresumedStateStore(db))
    for tool in home_tools(controller):
        tools.register(tool)
    log.info(
        "Casa: %d dispositivo(s), %d rotina(s) de %s.",
        len(config.devices), len(config.routines), settings.biony_home_config,
    )
    return controller


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
    if settings.groq_api_key:
        # Groq na nuvem (muito mais preciso e rápido); o Whisper local fica de reserva.
        groq = GroqSTT(api_key=settings.groq_api_key.get_secret_value(), model=settings.groq_stt_model)
        stt = FallbackSpeechToText(groq, stt)
        log.info("STT: Groq (%s) com Whisper local de reserva.", settings.groq_stt_model)
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
