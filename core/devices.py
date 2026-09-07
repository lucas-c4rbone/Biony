"""Gerenciamento e fila de comandos de dispositivos do Biony Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Protocol
from uuid import uuid4

from core.events import EventPublisher
from core.models import CoreEvent, Device


@dataclass(frozen=True)
class DeviceCommand:
    """Comando direcionado a um dispositivo específico."""

    command_id: str
    device_id: str
    command_type: str
    arguments: Mapping[str, object] = field(default_factory=dict)


class DeviceConnection(Protocol):
    """Canal de comunicação com um dispositivo conectado."""

    def send(self, command: DeviceCommand) -> bool:
        """Envia um comando para o dispositivo e indica o sucesso."""

    def close(self) -> None:
        """Encerra a conexão ativamente."""


class DeviceManager:
    """Gerencia o cadastro, estado de presença e comandos dos dispositivos."""

    def __init__(self, event_publisher: EventPublisher) -> None:
        self.event_publisher = event_publisher
        self._devices: dict[str, Device] = {}
        self._connections: dict[str, DeviceConnection] = {}
        self._pending_commands: dict[str, list[DeviceCommand]] = {}

    def register_device(self, device: Device) -> None:
        """Registra um dispositivo no gerenciador."""
        if device.identifier in self._devices:
            raise ValueError(f"Device '{device.identifier}' is already registered.")
        self._devices[device.identifier] = device
        self._pending_commands[device.identifier] = []
        self.event_publisher.publish(
            CoreEvent(event_type="device_registered", data={"device_id": device.identifier})
        )

    def remove_device(self, device_id: str) -> bool:
        """Remove um dispositivo registrado e encerra conexões ativas."""
        if device_id not in self._devices:
            return False
        self.disconnect(device_id)
        self._devices.pop(device_id)
        self._pending_commands.pop(device_id, None)
        self.event_publisher.publish(
            CoreEvent(event_type="device_removed", data={"device_id": device_id})
        )
        return True

    def get_device(self, device_id: str) -> Device | None:
        """Retorna o dispositivo pelo identificador."""
        return self._devices.get(device_id)

    def list_devices(self) -> list[Device]:
        """Lista todos os dispositivos cadastrados."""
        return list(self._devices.values())

    def connect(
        self, device_id: str, connection: DeviceConnection | None = None
    ) -> list[DeviceCommand]:
        """Marca um dispositivo como online e entrega comandos pendentes."""
        device = self.get_device(device_id)
        if device is None:
            raise ValueError(f"Device '{device_id}' is not registered.")

        device.is_available = True
        device.last_seen = datetime.now(timezone.utc).timestamp()
        if connection is not None:
            self._connections[device_id] = connection

        self.event_publisher.publish(
            CoreEvent(event_type="device_connected", data={"device_id": device_id})
        )

        return self._deliver_pending_commands(device_id)

    def disconnect(self, device_id: str) -> None:
        """Marca o dispositivo como offline e desconecta o canal ativo."""
        device = self.get_device(device_id)
        if device is None or not device.is_available:
            return

        device.is_available = False
        connection = self._connections.pop(device_id, None)
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

        self.event_publisher.publish(
            CoreEvent(event_type="device_disconnected", data={"device_id": device_id})
        )

    def send_command(
        self, device_id: str, command_type: str, arguments: Mapping[str, object] | None = None
    ) -> DeviceCommand:
        """Envia um comando diretamente ou o coloca na fila se o dispositivo estiver offline."""
        if device_id not in self._devices:
            raise ValueError(f"Device '{device_id}' is not registered.")

        command = DeviceCommand(
            command_id=str(uuid4()),
            device_id=device_id,
            command_type=command_type,
            arguments=arguments or {},
        )

        device = self._devices[device_id]
        connection = self._connections.get(device_id)

        if device.is_available and connection is not None:
            try:
                success = connection.send(command)
            except Exception:
                success = False

            if success:
                self.event_publisher.publish(
                    CoreEvent(
                        event_type="command_delivered",
                        data={
                            "command_id": command.command_id,
                            "device_id": device_id,
                            "command_type": command_type,
                        },
                    )
                )
                return command

        self._pending_commands.setdefault(device_id, []).append(command)
        self.event_publisher.publish(
            CoreEvent(
                event_type="command_queued",
                data={
                    "command_id": command.command_id,
                    "device_id": device_id,
                    "command_type": command_type,
                },
            )
        )
        return command

    def get_pending_commands(self, device_id: str) -> tuple[DeviceCommand, ...]:
        """Retorna a fila de comandos pendentes do dispositivo."""
        return tuple(self._pending_commands.get(device_id, []))

    def _deliver_pending_commands(self, device_id: str) -> list[DeviceCommand]:
        connection = self._connections.get(device_id)
        pending = self._pending_commands.get(device_id, [])
        delivered: list[DeviceCommand] = []

        if connection is None or not pending:
            return delivered

        remaining: list[DeviceCommand] = []
        for command in list(pending):
            try:
                success = connection.send(command)
            except Exception:
                success = False

            if success:
                delivered.append(command)
                self.event_publisher.publish(
                    CoreEvent(
                        event_type="command_delivered",
                        data={
                            "command_id": command.command_id,
                            "device_id": device_id,
                            "command_type": command.command_type,
                        },
                    )
                )
            else:
                remaining.append(command)

        self._pending_commands[device_id] = remaining
        return delivered
