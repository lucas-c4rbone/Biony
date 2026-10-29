"""Protocolo lógico de comunicação JSON v1.0 entre dispositivos Biony e Biony Core."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from typing import Mapping, Protocol, Union

from core.api.service import LocalDeviceAuthenticator
from core.devices import DeviceCommand, DeviceConnection, DeviceManager
from core.events import EventPublisher
from core.models import CoreEvent, Device, DeviceKind

PROTOCOL_VERSION = "1.0"


class ProtocolError(Exception):
    """Erro genérico no protocolo Biony."""


class InvalidProtocolVersionError(ProtocolError):
    """Versão do protocolo incompatível."""


@dataclass(frozen=True)
class HelloMessage:
    device_id: str
    device_kind: str
    capabilities: tuple[str, ...]
    credential: str
    type: str = "HELLO"
    protocol_version: str = PROTOCOL_VERSION


@dataclass(frozen=True)
class HelloAckMessage:
    accepted: bool
    error: str | None = None
    server_info: str | None = None
    type: str = "HELLO_ACK"
    protocol_version: str = PROTOCOL_VERSION


@dataclass(frozen=True)
class HeartbeatMessage:
    timestamp: float
    type: str = "HEARTBEAT"
    protocol_version: str = PROTOCOL_VERSION


@dataclass(frozen=True)
class HeartbeatAckMessage:
    timestamp: float
    type: str = "HEARTBEAT_ACK"
    protocol_version: str = PROTOCOL_VERSION


@dataclass(frozen=True)
class CommandMessage:
    command_id: str
    command_type: str
    arguments: Mapping[str, object] = field(default_factory=dict)
    type: str = "COMMAND"
    protocol_version: str = PROTOCOL_VERSION


@dataclass(frozen=True)
class CommandAckMessage:
    command_id: str
    accepted: bool
    error: str | None = None
    type: str = "COMMAND_ACK"
    protocol_version: str = PROTOCOL_VERSION


@dataclass(frozen=True)
class EventMessage:
    event_id: str
    event_type: str
    data: Mapping[str, object] = field(default_factory=dict)
    timestamp: float = 0.0
    type: str = "EVENT"
    protocol_version: str = PROTOCOL_VERSION


@dataclass(frozen=True)
class ErrorMessage:
    code: str
    message: str
    type: str = "ERROR"
    protocol_version: str = PROTOCOL_VERSION


ProtocolMessage = Union[
    HelloMessage,
    HelloAckMessage,
    HeartbeatMessage,
    HeartbeatAckMessage,
    CommandMessage,
    CommandAckMessage,
    EventMessage,
    ErrorMessage,
]


def serialize_message(message: ProtocolMessage) -> str:
    """Serializa um objeto de mensagem do protocolo Biony para uma string JSON."""
    data = asdict(message)
    return json.dumps(data)


def deserialize_message(raw_json: str) -> ProtocolMessage:
    """Desserializa uma string JSON para um objeto tipado do protocolo Biony."""
    try:
        data = json.loads(raw_json)
    except Exception as err:
        raise ProtocolError(f"Invalid JSON: {err}") from err

    if not isinstance(data, dict):
        raise ProtocolError("Message must be a JSON object.")

    msg_type = data.get("type")
    if not isinstance(msg_type, str) or not msg_type:
        raise ProtocolError("Missing or invalid 'type' field.")

    version = data.get("protocol_version")
    if version != PROTOCOL_VERSION:
        raise InvalidProtocolVersionError(
            f"Incompatible protocol version '{version}'. Expected '{PROTOCOL_VERSION}'."
        )

    try:
        if msg_type == "HELLO":
            capabilities = data.get("capabilities", ())
            if isinstance(capabilities, list):
                capabilities = tuple(capabilities)
            return HelloMessage(
                device_id=str(data["device_id"]),
                device_kind=str(data["device_kind"]),
                capabilities=tuple(str(c) for c in capabilities),
                credential=str(data["credential"]),
                protocol_version=str(version),
            )
        elif msg_type == "HELLO_ACK":
            return HelloAckMessage(
                accepted=bool(data["accepted"]),
                error=data.get("error"),
                server_info=data.get("server_info"),
                protocol_version=str(version),
            )
        elif msg_type == "HEARTBEAT":
            return HeartbeatMessage(
                timestamp=float(data["timestamp"]),
                protocol_version=str(version),
            )
        elif msg_type == "HEARTBEAT_ACK":
            return HeartbeatAckMessage(
                timestamp=float(data["timestamp"]),
                protocol_version=str(version),
            )
        elif msg_type == "COMMAND":
            args = data.get("arguments", {})
            if not isinstance(args, dict):
                args = {}
            return CommandMessage(
                command_id=str(data["command_id"]),
                command_type=str(data["command_type"]),
                arguments=args,
                protocol_version=str(version),
            )
        elif msg_type == "COMMAND_ACK":
            return CommandAckMessage(
                command_id=str(data["command_id"]),
                accepted=bool(data["accepted"]),
                error=data.get("error"),
                protocol_version=str(version),
            )
        elif msg_type == "EVENT":
            evt_data = data.get("data", {})
            if not isinstance(evt_data, dict):
                evt_data = {}
            return EventMessage(
                event_id=str(data["event_id"]),
                event_type=str(data["event_type"]),
                data=evt_data,
                timestamp=float(data.get("timestamp", 0.0)),
                protocol_version=str(version),
            )
        elif msg_type == "ERROR":
            return ErrorMessage(
                code=str(data["code"]),
                message=str(data["message"]),
                protocol_version=str(version),
            )
        else:
            raise ProtocolError(f"Unknown message type '{msg_type}'.")
    except (KeyError, TypeError, ValueError) as err:
        raise ProtocolError(f"Malformed '{msg_type}' message: {err}") from err


class TransportSink(Protocol):
    """Interface do transporte (ex: WebSocket) que envia texto."""

    def send_text(self, text: str) -> bool:
        """Envia texto pelo transporte e retorna se foi bem-sucedido."""

    def close(self) -> None:
        """Encerra a conexão de transporte."""


class ProtocolDeviceConnection:
    """Adapta DeviceConnection para enviar comandos como mensagens do protocolo Biony."""

    def __init__(self, transport: TransportSink) -> None:
        self.transport = transport

    def send(self, command: DeviceCommand) -> bool:
        cmd_msg = CommandMessage(
            command_id=command.command_id,
            command_type=command.command_type,
            arguments=command.arguments,
        )
        json_str = serialize_message(cmd_msg)
        return self.transport.send_text(json_str)

    def close(self) -> None:
        try:
            self.transport.close()
        except Exception:
            pass


class DeviceProtocolHandler:
    """Processa mensagens do protocolo e integra com DeviceManager e Authenticator."""

    def __init__(
        self,
        device_manager: DeviceManager,
        authenticator: LocalDeviceAuthenticator,
    ) -> None:
        self.device_manager = device_manager
        self.authenticator = authenticator
        self._device_connections: dict[str, ProtocolDeviceConnection] = {}

    def handle_raw_message(
        self, raw_json: str, transport: TransportSink, current_device_id: str | None = None
    ) -> tuple[ProtocolMessage | None, str | None]:
        """Processa uma mensagem bruta JSON enviada pelo transporte."""
        try:
            message = deserialize_message(raw_json)
            return self.handle_message(message, transport, current_device_id)
        except InvalidProtocolVersionError as err:
            return HelloAckMessage(accepted=False, error=str(err)), current_device_id
        except ProtocolError as err:
            return ErrorMessage(code="INVALID_MESSAGE", message=str(err)), current_device_id

    def handle_message(
        self,
        message: ProtocolMessage,
        transport: TransportSink,
        current_device_id: str | None = None,
    ) -> tuple[ProtocolMessage | None, str | None]:
        if isinstance(message, HelloMessage):
            return self._handle_hello(message, transport)

        device_id = current_device_id or getattr(message, "device_id", None)

        if isinstance(message, HeartbeatMessage):
            return self._handle_heartbeat(message, device_id)
        elif isinstance(message, CommandAckMessage):
            return self._handle_command_ack(message, device_id)
        elif isinstance(message, EventMessage):
            return self._handle_event(message, device_id)
        elif isinstance(message, ErrorMessage):
            return self._handle_error(message, device_id)
        elif isinstance(message, (HelloAckMessage, HeartbeatAckMessage, CommandMessage)):
            return None, device_id
        else:
            return ErrorMessage(code="UNKNOWN_MESSAGE", message="Unknown message type"), device_id

    def _handle_hello(
        self, message: HelloMessage, transport: TransportSink
    ) -> tuple[HelloAckMessage, str | None]:
        device_id = message.device_id
        is_valid = self.authenticator.authenticate(
            device_id, message.credential
        ) or self.authenticator.register(device_id, message.credential)

        if not is_valid:
            return (
                HelloAckMessage(accepted=False, error="Invalid device credential."),
                None,
            )

        kind = self._parse_device_kind(message.device_kind)
        device = self.device_manager.get_device(device_id)
        if device is None:
            device = Device(
                identifier=device_id,
                kind=kind,
                capabilities=frozenset(message.capabilities),
            )
            self.device_manager.register_device(device)
        else:
            device.capabilities = frozenset(message.capabilities)

        protocol_conn = ProtocolDeviceConnection(transport)
        self._device_connections[device_id] = protocol_conn
        self.device_manager.connect(device_id, protocol_conn)

        ack = HelloAckMessage(accepted=True, server_info="Biony Core 1.0")
        return ack, device_id

    def _handle_heartbeat(
        self, message: HeartbeatMessage, device_id: str | None
    ) -> tuple[HeartbeatAckMessage | ErrorMessage, str | None]:
        if device_id is None or self.device_manager.get_device(device_id) is None:
            return (
                ErrorMessage(code="UNAUTHORIZED", message="Device not connected."),
                device_id,
            )

        device = self.device_manager.get_device(device_id)
        if device is not None:
            device.last_seen = datetime.now(timezone.utc).timestamp()

        return HeartbeatAckMessage(timestamp=message.timestamp), device_id

    def _handle_command_ack(
        self, message: CommandAckMessage, device_id: str | None
    ) -> tuple[None, str | None]:
        if device_id:
            if message.accepted:
                self.device_manager.event_publisher.publish(
                    CoreEvent(
                        event_type="command_acknowledged",
                        data={
                            "command_id": message.command_id,
                            "device_id": device_id,
                            "accepted": True,
                        },
                    )
                )
            else:
                self.device_manager.event_publisher.publish(
                    CoreEvent(
                        event_type="command_failed",
                        data={
                            "command_id": message.command_id,
                            "device_id": device_id,
                            "accepted": False,
                            "error": message.error or "Command rejected by device",
                        },
                    )
                )
        return None, device_id

    def _handle_event(
        self, message: EventMessage, device_id: str | None
    ) -> tuple[None, str | None]:
        if device_id:
            self.device_manager.event_publisher.publish(
                CoreEvent(
                    event_type="device_event",
                    data={
                        "event_id": message.event_id,
                        "device_id": device_id,
                        "event_type": message.event_type,
                        "data": dict(message.data),
                        "timestamp": message.timestamp,
                    },
                )
            )
        return None, device_id

    def _handle_error(
        self, message: ErrorMessage, device_id: str | None
    ) -> tuple[None, str | None]:
        if device_id:
            self.device_manager.event_publisher.publish(
                CoreEvent(
                    event_type="device_error",
                    data={
                        "device_id": device_id,
                        "code": message.code,
                        "message": message.message,
                    },
                )
            )
        return None, device_id

    @staticmethod
    def _parse_device_kind(kind_str: str) -> DeviceKind:
        try:
            return DeviceKind[kind_str.upper()]
        except (KeyError, AttributeError):
            return DeviceKind.BIONY
