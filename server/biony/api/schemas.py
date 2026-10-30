"""Formato JSON das requisições e respostas (documentado em protocol/PROTOCOL.md)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TextoRequest(BaseModel):
    texto: str = Field(min_length=1, max_length=8_000)
    sessao: str | None = Field(default=None, max_length=128)


class TextoResponse(BaseModel):
    sessao: str
    resposta: str
    aguardando_confirmacao: bool


class VozResponse(BaseModel):
    sessao: str
    transcricao: str
    resposta: str
    aguardando_confirmacao: bool
    # WAV em base64; null quando responder_com_audio=false.
    audio_wav_base64: str | None


class LoginRequest(BaseModel):
    senha: str = Field(min_length=1, max_length=200)
    aparelho: str = Field(default="navegador", max_length=100)


class LoginResponse(BaseModel):
    token: str


class Mensagem(BaseModel):
    papel: str  # "usuario" ou "biony"
    texto: str


class HistoricoResponse(BaseModel):
    sessao: str
    mensagens: list[Mensagem]


class HealthResponse(BaseModel):
    status: str
    voz: str
