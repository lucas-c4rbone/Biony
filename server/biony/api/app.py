"""Rotas HTTP. Só traduzem JSON ↔ ConversationEngine; a lógica fica no core."""

from __future__ import annotations

from hmac import compare_digest
from typing import Any, AsyncContextManager, Callable

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from biony.api.schemas import HealthResponse, TextoRequest, TextoResponse
from biony.core.conversation import ConversationEngine
from biony.core.ports import LLMError


def create_app(
    engine: ConversationEngine,
    api_token: str,
    lifespan: Callable[[FastAPI], AsyncContextManager[Any]] | None = None,
) -> FastAPI:
    app = FastAPI(title="Biony", version="0.2.0", lifespan=lifespan)
    bearer = HTTPBearer(auto_error=False)

    def require_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
        if credentials is None or not compare_digest(credentials.credentials.encode(), api_token.encode()):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Token inválido.", headers={"WWW-Authenticate": "Bearer"}
            )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.post("/texto", response_model=TextoResponse, dependencies=[Depends(require_token)])
    async def texto(request: TextoRequest) -> TextoResponse:
        try:
            reply = await engine.handle(request.texto, request.sessao)
        except LLMError as error:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error
        return TextoResponse(
            sessao=reply.session_id, resposta=reply.text, aguardando_confirmacao=reply.awaiting_confirmation
        )

    return app
