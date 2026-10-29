"""Transporte HTTP e WebSocket local que adapta chamadas para o BionyCore."""

from __future__ import annotations

import asyncio
from hmac import compare_digest

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from core.api.contracts import (
    ConfirmationRequest,
    DeviceRegistrationRequest,
    EventResponse,
    HealthResponse,
    MessageRequest,
    MessageResponse,
    SessionMessageResponse,
    SessionResponse,
)
from core.biony_core import BionyCore
from core.models import ConversationRequest, CoreEvent


class LocalDeviceAuthenticator:
    """Autentica dispositivos locais registrados por um segredo injetado."""

    def __init__(self, registration_credential: str) -> None:
        if not registration_credential:
            raise ValueError("A device registration credential is required.")
        self._registration_credential = registration_credential
        self._registered_devices: set[str] = set()

    def register(self, device_id: str, credential: str) -> bool:
        if not compare_digest(credential, self._registration_credential):
            return False
        self._registered_devices.add(device_id)
        return True

    def authenticate(self, device_id: str, credential: str) -> bool:
        return device_id in self._registered_devices and compare_digest(
            credential, self._registration_credential
        )


class CoreApiService:
    """Converte contratos de transporte em chamadas ao BionyCore."""

    def __init__(self, core: BionyCore, authenticator: LocalDeviceAuthenticator) -> None:
        self._core = core
        self._authenticator = authenticator

    def register_device(self, request: DeviceRegistrationRequest) -> None:
        if not self._authenticator.register(request.device_id, request.credential):
            raise HTTPException(status_code=401, detail="Invalid device credential.")

    def handle_message(self, request: MessageRequest) -> MessageResponse:
        self._require_authenticated(request.device_id, request.credential)
        session = self._core.get_or_create_session(request.session_id)
        response = self._core.handle_message(
            ConversationRequest(message=request.message), session.identifier
        )
        return MessageResponse(session_id=session.identifier, message=response.message)

    def confirm_action(
        self, session_id: str, action_id: str, request: ConfirmationRequest
    ) -> MessageResponse:
        self._require_authenticated(request.device_id, request.credential)
        response = self._core.confirm_pending_action(session_id, action_id, request.response)
        if response is None:
            raise HTTPException(status_code=404, detail="Pending action not found.")
        return MessageResponse(session_id=session_id, message=response.message)

    def get_session(self, session_id: str, device_id: str, credential: str) -> SessionResponse:
        self._require_authenticated(device_id, credential)
        context = self._core.get_context(session_id)
        return SessionResponse(
            session_id=session_id,
            messages=[SessionMessageResponse(role=item.role, content=item.content) for item in context],
        )

    def health(self) -> HealthResponse:
        return HealthResponse(status="ok", state=self._core.state_machine.state.name)

    def authenticate(self, device_id: str, credential: str) -> bool:
        return self._authenticator.authenticate(device_id, credential)

    def _require_authenticated(self, device_id: str, credential: str) -> None:
        if not self.authenticate(device_id, credential):
            raise HTTPException(status_code=401, detail="Invalid device credential.")


def create_app(core: BionyCore, authenticator: LocalDeviceAuthenticator) -> FastAPI:
    """Cria uma aplicação local que delega todas as operações ao BionyCore."""
    service = CoreApiService(core, authenticator)
    app = FastAPI(title="Biony Local API")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return service.health()

    @app.post("/devices/register", status_code=204)
    def register_device(request: DeviceRegistrationRequest) -> None:
        service.register_device(request)

    @app.post("/messages", response_model=MessageResponse)
    def handle_message(request: MessageRequest) -> MessageResponse:
        try:
            return service.handle_message(request)
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=500, detail="Unable to process message.") from error

    @app.post("/sessions/{session_id}/confirmations/{action_id}", response_model=MessageResponse)
    def confirm_action(
        session_id: str, action_id: str, request: ConfirmationRequest
    ) -> MessageResponse:
        try:
            return service.confirm_action(session_id, action_id, request)
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=500, detail="Unable to process confirmation.") from error

    @app.get("/sessions/{session_id}", response_model=SessionResponse)
    def get_session(session_id: str, device_id: str, credential: str) -> SessionResponse:
        return service.get_session(session_id, device_id, credential)

    @app.websocket("/ws")
    async def websocket_events(websocket: WebSocket) -> None:
        device_id = websocket.query_params.get("device_id", "")
        credential = websocket.query_params.get("credential", "")
        if not service.authenticate(device_id, credential):
            await websocket.close(code=1008)
            return

        await websocket.accept()
        event_queue: asyncio.Queue[CoreEvent] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def publish_to_socket(event: CoreEvent) -> None:
            loop.call_soon_threadsafe(event_queue.put_nowait, event)

        core.event_publisher.subscribe(publish_to_socket)
        try:
            while True:
                event = await event_queue.get()
                payload = EventResponse(event_type=event.event_type, data=dict(event.data))
                await websocket.send_json(payload.model_dump())
        except WebSocketDisconnect:
            pass
        finally:
            core.event_publisher.unsubscribe(publish_to_socket)

    return app