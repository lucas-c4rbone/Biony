"""Configuração lida das variáveis de ambiente (ou de um arquivo .env)."""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Fora do Docker, procura o .env na raiz do repositório.
_REPO_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ENV, env_file_encoding="utf-8", extra="ignore")

    # LLM (qualquer API no formato OpenAI; o padrão é o OpenRouter)
    llm_api_key: SecretStr
    llm_model: str = "deepseek/deepseek-chat"
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_timeout: float = 30.0

    # Token que todo cliente (PWA, terminal, ESP32) manda no header Authorization.
    biony_api_token: SecretStr = Field(min_length=24)

    biony_user_name: str = "Lucas"
    biony_timezone: str = "America/Sao_Paulo"
    biony_db_path: Path = Path("data/biony.sqlite3")
    biony_history_messages: int = 30

    @field_validator("biony_timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.biony_timezone)
