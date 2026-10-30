"""Configuração lida das variáveis de ambiente (ou de um arquivo .env)."""

from __future__ import annotations

from datetime import time
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

    # Senha da PWA (login por aparelho). Sem ela, o login fica desativado.
    biony_password: SecretStr | None = Field(default=None, min_length=8)

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
    # Transcrição na nuvem (opcional). Com a chave, a Groq vira o STT principal.
    groq_api_key: SecretStr | None = None
    groq_stt_model: str = "whisper-large-v3-turbo"
    biony_models_dir: Path = Path("data/models")

    # Agente do PC (clients/pc-agente): ligar/desligar o PC com segurança.
    pc_agent_url: str | None = None
    pc_agent_token: SecretStr | None = None
    pc_setup_device: str = "setup"  # aparelho do casa.toml que é o filtro do PC

    # Telegram: notificações e conversa. Sem token, os lembretes ficam salvos mas não chegam.
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: int | None = None

    # Avisos automáticos de prazo
    biony_deadline_days: str = "3,1,0"
    biony_deadline_time: time = time(9, 0)
    biony_quiet_start: time = time(22, 30)
    biony_quiet_end: time = time(7, 0)

    @field_validator("biony_timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("biony_deadline_days")
    @classmethod
    def _valid_days(cls, value: str) -> str:
        cls._parse_days(value)
        return value

    @staticmethod
    def _parse_days(value: str) -> tuple[int, ...]:
        days = tuple(int(part) for part in value.split(",") if part.strip())
        if not days or any(day < 0 for day in days):
            raise ValueError("BIONY_DEADLINE_DAYS: lista de dias >= 0, ex.: 3,1,0")
        return days

    @property
    def deadline_days(self) -> tuple[int, ...]:
        return self._parse_days(self.biony_deadline_days)

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.biony_timezone)
