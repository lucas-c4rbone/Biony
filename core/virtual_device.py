"""Conexao em memoria para exercitar o contrato do dispositivo Biony."""

from __future__ import annotations

from collections.abc import Callable

from core.devices import DeviceCommand

CommandObserver = Callable[[DeviceCommand], None]


class VirtualBionyDevice:
    """Implementa a porta de dispositivo sem audio ou hardware real."""

    def __init__(self, observer: CommandObserver | None = None) -> None:
        self.observer = observer
        self.state = "IDLE"
        self.expression = "NORMAL"
        self.animations: list[str] = []
        self.spoken_audio_ids: list[str] = []
        self.volume = 100
        self.is_closed = False
        self.received_commands: list[DeviceCommand] = []

    def send(self, command: DeviceCommand) -> bool:
        self.received_commands.append(command)
        arguments = command.arguments
        if command.command_type == "set_state":
            self.state = str(arguments["state"])
        elif command.command_type == "set_expression":
            self.expression = str(arguments["expression"])
        elif command.command_type == "play_animation":
            self.animations.append(str(arguments["animation"]))
        elif command.command_type == "speak":
            self.spoken_audio_ids.append(str(arguments["audio_id"]))
        elif command.command_type == "stop_speaking":
            self.spoken_audio_ids.clear()
        elif command.command_type == "set_volume":
            self.volume = int(arguments["volume"])
        if self.observer is not None:
            self.observer(command)
        return True

    def close(self) -> None:
        self.is_closed = True