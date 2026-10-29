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


class HealthResponse(BaseModel):
    status: str
