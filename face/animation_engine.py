"""Motor de animações pixeladas do Biony Virtual."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from PySide6.QtCore import QObject, QTimer

Pixel = tuple[int, int, str]
FrameListener = Callable[["AnimationFrame | None"], None]
FinishListener = Callable[[str], None]


@dataclass(frozen=True)
class AnimationFrame:
    """Frame discreto formado apenas por pixels nítidos da grade lógica."""

    pixels: tuple[Pixel, ...]
    duration_ms: int = 150


@dataclass(frozen=True)
class PixelAnimation:
    """Sequência explícita de frames com execução única ou em loop."""

    name: str
    frames: tuple[AnimationFrame, ...]
    loop: bool = False


def _pixels(cells: Iterable[tuple[int, int]], color: str = "blue") -> tuple[Pixel, ...]:
    return tuple((x, y, color) for x, y in cells)


def _eye(cx: int, cy: int, width: int = 5, height: int = 12) -> tuple[Pixel, ...]:
    pixels: list[Pixel] = []
    for y in range(cy - height // 2, cy + height // 2):
        for x in range(cx - width // 2, cx + width // 2 + 1):
            pixels.append((x, y, "blue"))
    return tuple(pixels)


def _eyes(left_x: int = 22, right_x: int = 42, y: int = 15, width: int = 5, height: int = 12) -> tuple[Pixel, ...]:
    return _eye(left_x, y, width, height) + _eye(right_x, y, width, height)


def _sprite(origin_x: int, origin_y: int, rows: tuple[str, ...], color: str = "blue") -> tuple[Pixel, ...]:
    cells = tuple(
        (origin_x + column, origin_y + row)
        for row, line in enumerate(rows)
        for column, value in enumerate(line)
        if value == "#"
    )
    return _pixels(cells, color)


def _frames() -> dict[str, PixelAnimation]:
    normal = _eyes()
    look_left = _eyes(18, 38)
    look_right = _eyes(26, 46)
    look_up = _eyes(y=11)
    blink = _eyes(height=3)
    tiny = _eyes(y=19, height=2)

    hammer_a = _sprite(26, 19, ("##", "##", "#.", "#."), "orange") + _pixels(((31, 24), (32, 24)), "blue")
    hammer_b = _sprite(31, 16, ("###", ".#.", ".#.", ".#.", ".#.", ".#."), "orange") + _pixels(((31, 24), (32, 24)), "blue")
    hammer_c = _sprite(35, 20, ("###", ".#.", ".#.", ".#."), "orange") + _pixels(((28, 25), (29, 24), (30, 25), (33, 25), (34, 24), (35, 25)), "white")

    meditate_1 = normal + _pixels(((20, 25), (24, 23), (40, 23), (44, 25)), "blue")
    meditate_2 = normal + _pixels(((18, 24), (22, 22), (26, 25), (38, 25), (42, 22), (46, 24)), "blue")
    meditate_3 = normal + _pixels(((17, 21), (20, 25), (24, 21), (27, 24), (37, 24), (40, 21), (44, 25), (47, 21)), "blue")

    octane = (
        _sprite(23, 17, ("..##....", ".####...", "##..##..", "########", ".#....#.", "#......#"), "blue")
        + _pixels(((20, 25), (21, 25), (34, 25), (35, 25)), "white")
    )
    fish_line_1 = normal + _pixels(((34, 21), (35, 20), (36, 19), (37, 18), (38, 17)), "orange")
    fish_line_2 = _eyes(22, 42, 14) + _pixels(((34, 21), (35, 20), (36, 19), (37, 18), (38, 17), (39, 17), (40, 18)), "orange")
    fish_catch = _eyes(22, 42, 14) + _pixels(((36, 18), (37, 17), (38, 18), (39, 17), (40, 18), (39, 19), (38, 20)), "orange")

    glitch_1 = normal
    glitch_2 = _pixels(((16, 9), (17, 9), (18, 9), (22, 10), (23, 10), (30, 14), (31, 14), (39, 8), (40, 8), (43, 9), (44, 9), (48, 18), (49, 18)), "blue")
    glitch_3 = _pixels(((18, 18), (19, 17), (20, 19), (24, 11), (25, 12), (26, 13), (37, 17), (38, 18), (42, 13), (43, 12), (44, 11), (47, 20)), "blue")

    running_1 = _sprite(27, 16, (".###.", "#####", ".###.", "#####", "#...#", ".#.#."), "blue")
    running_2 = _sprite(28, 15, (".###.", "#####", ".###.", "#####", ".##..", "#..#."), "blue") + _pixels(((22, 20), (24, 20)), "white")
    running_3 = _sprite(27, 16, (".###.", "#####", ".###.", "#####", "..##.", ".#..#"), "blue") + _pixels(((38, 20), (40, 20)), "white")

    spaghetti_1 = normal + _pixels(((20, 24), (21, 23), (22, 22)), "yellow")
    spaghetti_2 = _eyes(22, 42, 15) + _pixels(((31, 19), (32, 18), (33, 17), (34, 16), (35, 15)), "yellow")
    spaghetti_3 = _eyes(22, 42, 15) + _pixels(((34, 16), (35, 15), (36, 14), (37, 13), (38, 12), (42, 20), (43, 21)), "yellow")
    spaghetti_4 = _eyes(22, 42, 15) + _pixels(((45, 17), (46, 16), (47, 15), (48, 14), (49, 13), (50, 12), (47, 19), (48, 20)), "yellow")

    yawn_1 = normal
    yawn_2 = blink + _pixels(((29, 25), (30, 25), (31, 25), (32, 25), (33, 25), (34, 25)), "blue")
    yawn_3 = blink + _pixels(((30, 23), (31, 22), (32, 21), (33, 22), (34, 23), (31, 24), (32, 24), (33, 24)), "blue")

    return {
        "hammer": PixelAnimation("hammer", (AnimationFrame(hammer_a), AnimationFrame(hammer_b), AnimationFrame(hammer_c), AnimationFrame(normal)), False),
        "look_left_right": PixelAnimation("look_left_right", (AnimationFrame(normal), AnimationFrame(look_left), AnimationFrame(look_right), AnimationFrame(normal)), False),
        "look_up": PixelAnimation("look_up", (AnimationFrame(normal), AnimationFrame(look_up), AnimationFrame(normal)), False),
        "meditation": PixelAnimation("meditation", (AnimationFrame(meditate_1), AnimationFrame(meditate_2), AnimationFrame(meditate_3), AnimationFrame(meditate_2), AnimationFrame(meditate_1)), False),
        "octane": PixelAnimation("octane", (AnimationFrame(octane), AnimationFrame(octane, 300)), False),
        "pesqueiro": PixelAnimation("pesqueiro", (AnimationFrame(fish_line_1), AnimationFrame(fish_line_2), AnimationFrame(fish_catch), AnimationFrame(fish_line_1)), False),
        "quick_glitch": PixelAnimation("quick_glitch", (AnimationFrame(glitch_1, 90), AnimationFrame(glitch_2, 90), AnimationFrame(glitch_3, 90), AnimationFrame(normal, 90)), False),
        "running": PixelAnimation("running", (AnimationFrame(running_1), AnimationFrame(running_2), AnimationFrame(running_3), AnimationFrame(running_2), AnimationFrame(running_1)), False),
        "spaghetti_hunter": PixelAnimation("spaghetti_hunter", (AnimationFrame(spaghetti_1), AnimationFrame(spaghetti_2), AnimationFrame(spaghetti_3), AnimationFrame(spaghetti_4)), False),
        "yawn": PixelAnimation("yawn", (AnimationFrame(yawn_1), AnimationFrame(yawn_2), AnimationFrame(yawn_3), AnimationFrame(yawn_2), AnimationFrame(tiny)), False),
    }


OFFICIAL_ANIMATIONS = _frames()


class AnimationEngine(QObject):
    """Avança animações por QTimer sem bloquear a interface Qt."""

    def __init__(self, on_frame: FrameListener | None = None, on_finished: FinishListener | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._advance)
        self._on_frame = on_frame
        self._on_finished = on_finished
        self._animation: PixelAnimation | None = None
        self._frame_index = -1
        self._generation = 0

    @property
    def is_running(self) -> bool:
        return self._animation is not None

    @property
    def current_animation(self) -> str | None:
        return self._animation.name if self._animation else None

    @property
    def current_frame(self) -> AnimationFrame | None:
        if self._animation is None or self._frame_index < 0:
            return None
        return self._animation.frames[self._frame_index]

    def start(self, name: str) -> None:
        animation = OFFICIAL_ANIMATIONS.get(name)
        if animation is None:
            raise ValueError(f"Unknown Biony animation: {name}")
        self.stop(notify=False)
        self._generation += 1
        self._animation = animation
        self._frame_index = 0
        self._emit_current_frame()

    def stop(self, notify: bool = True) -> None:
        if self._animation is None:
            return
        name = self._animation.name
        self._timer.stop()
        self._animation = None
        self._frame_index = -1
        self._generation += 1
        if self._on_frame is not None:
            self._on_frame(None)
        if notify and self._on_finished is not None:
            self._on_finished(name)

    def advance_for_test(self) -> None:
        """Avança um frame sem aguardar o relógio do Qt; usado somente por testes."""
        self._advance()

    def _emit_current_frame(self) -> None:
        frame = self.current_frame
        if frame is None:
            return
        if self._on_frame is not None:
            self._on_frame(frame)
        self._timer.start(frame.duration_ms)

    def _advance(self) -> None:
        animation = self._animation
        if animation is None:
            return
        next_index = self._frame_index + 1
        if next_index >= len(animation.frames):
            if animation.loop:
                next_index = 0
            else:
                self.stop()
                return
        self._frame_index = next_index
        self._emit_current_frame()
