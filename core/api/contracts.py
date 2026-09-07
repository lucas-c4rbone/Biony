"""Contratos estáveis usados pelo transporte local do Biony."""

from __future__ import annotations

from pydantic import BaseModel


class DeviceRegistrationRequest(BaseModel):
    device_id: str
    credential: str


class MessageRequest(BaseModel):
    device_id: str
    credential: str
    message: str
    session_id: str | None = None


class ConfirmationRequest(BaseModel):
    device_id: str
    credential: str
    response: str


class MessageResponse(BaseModel):
    session_id: str
    message: str | None


class SessionMessageResponse(BaseModel):
    role: str
    content: str


class SessionResponse(BaseModel):
    session_id: str
    messages: list[SessionMessageResponse]


class HealthResponse(BaseModel):
    status: str
    state: str


class EventResponse(BaseModel):
    event_type: str
    data: dict[str, object]