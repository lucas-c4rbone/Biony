"""Rotas HTTP. Só traduzem JSON ↔ ConversationEngine; a lógica fica no core."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, AsyncContextManager, Callable

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from biony.api.agenda import agenda_router
from biony.api.auth import Auth, LoginLocked
from biony.api.device_ws import register_device_ws
from biony.api.schemas import (
    HealthResponse,
    HistoricoResponse,
    LoginRequest,
    LoginResponse,
    Mensagem,
    TextoRequest,
    TextoResponse,
    VozResponse,
)
from biony.core.conversation import ConversationEngine
from biony.core.models import Role
from biony.core.ports import AudioError, LLMError
from biony.core.reminder_service import ReminderService
from biony.core.voice import VoiceSlot

MAX_AUDIO_BYTES = 10 * 1024 * 1024
WEB_DIR = Path(__file__).resolve().parents[1] / "web"


class PwaFiles(StaticFiles):
    """Arquivos da PWA sempre revalidados (ETag): sem isto o navegador reaproveita CSS/JS velho por horas."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def _capabilities(names: list[str]) -> frozenset[str]:
    return frozenset(name.strip() for name in names if 0 < len(name.strip()) <= 32)


def create_app(
    engine: ConversationEngine,
    auth: Auth | str,
    voice: VoiceSlot | None = None,
    lifespan: Callable[[FastAPI], AsyncContextManager[Any]] | None = None,
    agenda: ReminderService | None = None,
) -> FastAPI:
    app = FastAPI(title="Biony", version="0.2.0", lifespan=lifespan)
    voice = voice or VoiceSlot(enabled=False)
    auth = Auth(auth) if isinstance(auth, str) else auth
    bearer = HTTPBearer(auto_error=False)

    def require_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        if credentials is None or not auth.check(credentials.credentials):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Token inválido.", headers={"WWW-Authenticate": "Bearer"}
            )
        return credentials.credentials

    if agenda is not None:
        app.include_router(agenda_router(agenda, require_token))

    @app.post("/login", response_model=LoginResponse)
    async def login(request: LoginRequest) -> LoginResponse:
        if not auth.login_enabled:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Login desativado: defina BIONY_PASSWORD no .env.")
        try:
            token = auth.login(request.senha, request.aparelho)
        except LoginLocked as error:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error)) from error
        if token is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Senha errada.")
        return LoginResponse(token=token)

    @app.post("/logout", status_code=204)
    async def logout(token: str = Depends(require_token)) -> None:
        auth.logout(token)

    @app.get("/sessoes/{sessao}/mensagens", response_model=HistoricoResponse, dependencies=[Depends(require_token)])
    async def historico(sessao: str, limite: int = 100) -> HistoricoResponse:
        messages = engine.transcript(sessao, max(1, min(limite, 500)))
        return HistoricoResponse(
            sessao=sessao,
            mensagens=[
                Mensagem(papel="usuario" if m.role is Role.USER else "biony", texto=m.content) for m in messages
            ],
        )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", voz=voice.status)

    @app.post("/texto", response_model=TextoResponse, dependencies=[Depends(require_token)])
    async def texto(request: TextoRequest) -> TextoResponse:
        try:
            reply = await engine.handle(request.texto, request.sessao, capabilities=_capabilities(request.capacidades))
        except LLMError as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
        return TextoResponse(
            sessao=reply.session_id,
            resposta=reply.text,
            aguardando_confirmacao=reply.awaiting_confirmation,
            emocao=reply.emotion.value,
            acoes=[dict(action) for action in reply.client_actions],
        )

    @app.post("/voz", response_model=VozResponse, dependencies=[Depends(require_token)])
    async def voz(
        audio: UploadFile = File(..., description="Arquivo de áudio: WAV, WebM, OGG, MP3..."),
        sessao: str | None = Form(default=None, max_length=128),
        responder_com_audio: bool = Form(default=True),
        capacidades: str = Form(default="", max_length=200, description="Separadas por vírgula, ex.: acoes_celular"),
    ) -> VozResponse:
        assistant = voice.assistant
        if assistant is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Voz {voice.status}.")
        data = await audio.read(MAX_AUDIO_BYTES + 1)
        if len(data) > MAX_AUDIO_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Áudio maior que 10 MB.")
        try:
            result = await assistant.handle(
                data, sessao, with_audio=responder_com_audio, capabilities=_capabilities(capacidades.split(","))
            )
        except AudioError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
        except LLMError as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
        return VozResponse(
            sessao=result.reply.session_id,
            transcricao=result.transcript,
            resposta=result.reply.text,
            aguardando_confirmacao=result.reply.awaiting_confirmation,
            emocao=result.reply.emotion.value,
            acoes=[dict(action) for action in result.reply.client_actions],
            audio_wav_base64=base64.b64encode(result.audio).decode() if result.audio is not None else None,
        )

    register_device_ws(app, engine, auth, voice)

    if WEB_DIR.is_dir():
        # Por último: as rotas da API acima têm prioridade sobre os arquivos da PWA.
        app.mount("/", PwaFiles(directory=WEB_DIR, html=True), name="pwa")
    return app
