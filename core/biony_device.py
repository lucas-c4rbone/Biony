"""Contrato e especificações do dispositivo Biony 1.0."""

from __future__ import annotations

from typing import Mapping
from uuid import uuid4

from core.devices import DeviceCommand
from core.models import Device, DeviceKind
from face.expressions import FaceExpression

# Capacidades oficiais do Biony 1.0
BIONY_1_0_CAPABILITIES: frozenset[str] = frozenset(
    {"display", "audio", "microphone", "expressions", "animations", "wifi"}
)

# Estados válidos para o dispositivo Biony 1.0
VALID_STATES: frozenset[str] = frozenset(
    {"BOOTING", "SLEEPING", "IDLE", "WAKING", "LISTENING", "THINKING", "SPEAKING"}
)

# Expressões válidas (derivadas de FaceExpression)
VALID_EXPRESSIONS: frozenset[str] = frozenset(e.name for e in FaceExpression)

# Animações oficiais do Biony 1.0
VALID_ANIMATIONS: frozenset[str] = frozenset(
    {
        "look_left_right",
        "yawn",
        "curious",
        "look_up",
        "quick_glitch",
        "code_rain",
        "hammer",
        "meditation",
        "gamer_xp",
        "running",
        "almost_sleeping",
        "pesqueiro",
        "octane",
        "spaghetti_hunter",
    }
)

# Tipos de comando oficiais do Biony 1.0
VALID_COMMAND_TYPES: frozenset[str] = frozenset(
    {"set_state", "set_expression", "play_animation", "speak", "stop_speaking", "set_volume"}
)

# Tipos de evento oficiais do Biony 1.0
VALID_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "wake_detected",
        "button_pressed",
        "audio_started",
        "audio_finished",
        "animation_finished",
        "device_error",
    }
)


class InvalidCommandError(ValueError):
    """Exceção para comando inválido ou com argumentos incorretos para o Biony 1.0."""


class InvalidEventError(ValueError):
    """Exceção para evento inválido ou com formato incorreto enviado pelo Biony 1.0."""


def validate_biony_command(
    command_type: str, arguments: Mapping[str, object] | None = None
) -> dict[str, object]:
    """Valida um comando do Biony 1.0. Retorna os argumentos validados ou lança InvalidCommandError."""
    if not isinstance(command_type, str) or command_type not in VALID_COMMAND_TYPES:
        raise InvalidCommandError(
            f"Comando desconhecido '{command_type}'. Comandos válidos: {sorted(VALID_COMMAND_TYPES)}"
        )

    args = dict(arguments) if arguments is not None else {}

    if command_type == "set_state":
        state = args.get("state")
        if not isinstance(state, str) or state not in VALID_STATES:
            raise InvalidCommandError(
                f"Estado inválido '{state}'. Estados válidos: {sorted(VALID_STATES)}"
            )

    elif command_type == "set_expression":
        expression = args.get("expression")
        if not isinstance(expression, str) or expression not in VALID_EXPRESSIONS:
            raise InvalidCommandError(
                f"Expressão inválida '{expression}'. Expressões válidas: {sorted(VALID_EXPRESSIONS)}"
            )

    elif command_type == "play_animation":
        animation = args.get("animation")
        if not isinstance(animation, str) or animation not in VALID_ANIMATIONS:
            raise InvalidCommandError(
                f"Animação desconhecida '{animation}'. Animações válidas: {sorted(VALID_ANIMATIONS)}"
            )

    elif command_type == "speak":
        audio_id = args.get("audio_id")
        if not isinstance(audio_id, str) or not audio_id:
            raise InvalidCommandError("O comando 'speak' exige o argumento 'audio_id' como string.")
        interruptible = args.get("interruptible", True)
        if not isinstance(interruptible, bool):
            raise InvalidCommandError("O argumento 'interruptible' no comando 'speak' deve ser booleano.")
        args["interruptible"] = interruptible

    elif command_type == "stop_speaking":
        pass  # Sem argumentos obrigatórios

    elif command_type == "set_volume":
        if "volume" not in args:
            raise InvalidCommandError("O comando 'set_volume' exige o argumento 'volume'.")
        volume = args["volume"]
        if isinstance(volume, bool) or not isinstance(volume, (int, float)):
            raise InvalidCommandError("O argumento 'volume' deve ser um número entre 0 e 100.")
        if not (0 <= volume <= 100):
            raise InvalidCommandError(f"Volume {volume} fora da faixa permitida [0, 100].")

    return args


def validate_biony_event(
    event_type: str, data: Mapping[str, object] | None = None
) -> dict[str, object]:
    """Valida um evento do Biony 1.0. Retorna os dados validados ou lança InvalidEventError."""
    if not isinstance(event_type, str) or event_type not in VALID_EVENT_TYPES:
        raise InvalidEventError(
            f"Evento desconhecido '{event_type}'. Eventos válidos: {sorted(VALID_EVENT_TYPES)}"
        )

    evt_data = dict(data) if data is not None else {}
    return evt_data


def create_biony_device(device_id: str, is_available: bool = False) -> Device:
    """Cria uma instância do modelo Device pré-configurada com as capacidades do Biony 1.0."""
    return Device(
        identifier=device_id,
        kind=DeviceKind.BIONY,
        is_available=is_available,
        capabilities=BIONY_1_0_CAPABILITIES,
    )


def create_biony_command(
    device_id: str, command_type: str, arguments: Mapping[str, object] | None = None
) -> DeviceCommand:
    """Valida e cria um DeviceCommand para um dispositivo Biony 1.0."""
    validated_args = validate_biony_command(command_type, arguments)
    return DeviceCommand(
        command_id=str(uuid4()),
        device_id=device_id,
        command_type=command_type,
        arguments=validated_args,
    )
