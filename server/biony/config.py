"""Configuração lida das variáveis de ambiente (ou de um arquivo .env)."""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO = Path(__file__).resolve().parents[2]
# Fora do Docker, procura o .env na raiz do repositório.
_REPO_ENV = _REPO / ".env"


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

    # Home Assistant (opcional: sem URL e token, as ferramentas da casa ficam desligadas)
    ha_url: str | None = None
    ha_token: SecretStr | None = None
    ha_timeout: float = 10.0
    biony_home_config: Path = _REPO / "config" / "casa.toml"

    # Voz (faster-whisper + Piper). Os modelos são baixados na primeira vez para biony_models_dir.
    voice_enabled: bool = True
    stt_model: str = "small"
    stt_beam_size: int = 1
    tts_voice: str = "pt_BR-faber-medium"
    biony_models_dir: Path = Path("data/models")

    @field_validator("biony_timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.biony_timezone)
