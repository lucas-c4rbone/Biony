"""Monta o Biony a partir da configuração. Rodar com: uvicorn biony.main:app"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from biony.adapters.openai_compat import OpenAICompatClient
from biony.adapters.sqlite_store import Database, SqliteConversationStore
from biony.api.app import create_app
from biony.config import Settings
from biony.core.conversation import ConversationEngine
from biony.core.permissions import PermissionPolicy
from biony.core.tools import ToolRegistry


def build_app(settings: Settings) -> FastAPI:
    db = Database(settings.biony_db_path)
    llm = OpenAICompatClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
        timeout=settings.llm_timeout,
    )
    tools = ToolRegistry()  # As ferramentas entram a partir da F2.
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
        yield
        await llm.aclose()
        db.close()

    return create_app(engine, settings.biony_api_token.get_secret_value(), lifespan)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = build_app(Settings())
