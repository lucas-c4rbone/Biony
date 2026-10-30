"""Rotas HTTP. Só traduzem JSON ↔ ConversationEngine; a lógica fica no core."""

from __future__ import annotations

import base64
from hmac import compare_digest
from typing import Any, AsyncContextManager, Callable

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from biony.api.schemas import HealthResponse, TextoRequest, TextoResponse, VozResponse
from biony.core.conversation import ConversationEngine
from biony.core.ports import AudioError, LLMError
from biony.core.voice import VoiceSlot

MAX_AUDIO_BYTES = 10 * 1024 * 1024


def create_app(
    engine: ConversationEngine,
    api_token: str,
    voice: VoiceSlot | None = None,
    lifespan: Callable[[FastAPI], AsyncContextManager[Any]] | None = None,
) -> FastAPI:
    app = FastAPI(title="Biony", version="0.2.0", lifespan=lifespan)
    voice = voice or VoiceSlot(enabled=False)
    bearer = HTTPBearer(auto_error=False)

    def require_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
        if credentials is None or not compare_digest(credentials.credentials.encode(), api_token.encode()):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Token inválido.", headers={"WWW-Authenticate": "Bearer"}
            )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", voz=voice.status)

    @app.post("/texto", response_model=TextoResponse, dependencies=[Depends(require_token)])
    async def texto(request: TextoRequest) -> TextoResponse:
        try:
            reply = await engine.handle(request.texto, request.sessao)
        except LLMError as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
        return TextoResponse(
            sessao=reply.session_id, resposta=reply.text, aguardando_confirmacao=reply.awaiting_confirmation
        )

    @app.post("/voz", response_model=VozResponse, dependencies=[Depends(require_token)])
    async def voz(
        audio: UploadFile = File(..., description="Arquivo de áudio: WAV, WebM, OGG, MP3..."),
        sessao: str | None = Form(default=None, max_length=128),
        responder_com_audio: bool = Form(default=True),
    ) -> VozResponse:
        assistant = voice.assistant
        if assistant is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Voz {voice.status}.")
        data = await audio.read(MAX_AUDIO_BYTES + 1)
        if len(data) > MAX_AUDIO_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Áudio maior que 10 MB.")
        try:
            result = await assistant.handle(data, sessao, with_audio=responder_com_audio)
        except AudioError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
        except LLMError as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
        return VozResponse(
            sessao=result.reply.session_id,
            transcricao=result.transcript,
            resposta=result.reply.text,
            aguardando_confirmacao=result.reply.awaiting_confirmation,
            audio_wav_base64=base64.b64encode(result.audio).decode() if result.audio is not None else None,
        )

    return app
