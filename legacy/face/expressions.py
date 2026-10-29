"""Vocabulário visual do rosto, independente dos estados do núcleo."""

from enum import Enum, auto


class FaceExpression(Enum):
    """Expressões que o rosto do Biony sabe representar pelos olhos."""

    NORMAL = auto()
    HAPPY = auto()
    CURIOUS = auto()
    THINKING = auto()
    SURPRISED = auto()
    CONFUSED = auto()
    SLEEPING = auto()
    LISTENING = auto()
    SPEAKING = auto()
    WAKING = auto()
