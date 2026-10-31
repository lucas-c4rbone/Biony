"""Formato JSON das requisições e respostas (documentado em protocol/PROTOCOL.md)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TextoRequest(BaseModel):
    texto: str = Field(min_length=1, max_length=8_000)
    sessao: str | None = Field(default=None, max_length=128)
    # O que este cliente sabe executar, ex.: ["acoes_celular"] (o app do celular).
    capacidades: list[str] = Field(default_factory=list, max_length=8)


class TextoResponse(BaseModel):
    sessao: str
    resposta: str
    aguardando_confirmacao: bool
    # neutro | feliz | triste | duvida | confuso: para o rosto reagir.
    emocao: str = "neutro"
    # Ações para o CLIENTE executar (só vêm se ele declarou a capacidade), ex.: {"tipo": "despertador", ...}.
    acoes: list[dict[str, Any]] = Field(default_factory=list)


class VozResponse(BaseModel):
    sessao: str
    transcricao: str
    resposta: str
    aguardando_confirmacao: bool
    emocao: str = "neutro"
    acoes: list[dict[str, Any]] = Field(default_factory=list)
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


class Aviso(BaseModel):
    id: int
    quando: str  # ISO com fuso
    quando_texto: str  # "sábado, 15/11 às 09:00"


class TarefaOut(BaseModel):
    id: int
    titulo: str
    prazo: str | None  # "2026-11-15" ou "2026-11-15T14:00"
    prazo_texto: str | None
    observacoes: str
    avisos: list[Aviso]


class LembreteOut(BaseModel):
    id: int
    texto: str
    quando: str
    quando_texto: str


class AgendaResponse(BaseModel):
    tarefas: list[TarefaOut]
    lembretes: list[LembreteOut]


class TarefaRequest(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    prazo: str | None = Field(default=None, max_length=16)  # "2026-11-15" ou "2026-11-15T14:00"
    observacoes: str = Field(default="", max_length=1_000)
