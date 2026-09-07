"""Rosto pixelado do Biony, desenhado em uma grade lógica escalável."""

from __future__ import annotations

import math
from datetime import datetime

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer, Property
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .expressions import FaceExpression


class FaceWidget(QWidget):
    """Renderiza o rosto em 64×32 pixels lógicos, sem conhecer o Biony Core."""

    LOGICAL_WIDTH = 64
    LOGICAL_HEIGHT = 32
    BACKGROUND = QColor("#060a10")
    SCREEN_BORDER = QColor("#111a24")
    PIXEL_COLOR = QColor("#69eaf5")
    CLOCK_COLOR = QColor("#318b9b")

    STATE_EXPRESSIONS = {
        "SLEEPING": FaceExpression.SLEEPING,
        "IDLE": FaceExpression.NORMAL,
        "WAKING": FaceExpression.WAKING,
        "LISTENING": FaceExpression.LISTENING,
        "THINKING": FaceExpression.THINKING,
        "SPEAKING": FaceExpression.SPEAKING,
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = "IDLE"
        self._expression = FaceExpression.NORMAL
        self._blink = 0.0
        self._phase = 0.0
        self._waking_progress = 1.0
        self._elapsed_ms = 0
        self.setMinimumSize(520, 360)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(16)
        self._frame_timer.timeout.connect(self._advance_animation)
        self._frame_timer.start()
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1_000)
        self._clock_timer.timeout.connect(self.update)
        self._clock_timer.start()
        self._wake_animation = QPropertyAnimation(self, b"wakingProgress", self)
        self._wake_animation.setDuration(900)
        self._wake_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_state(self, state: object) -> None:
        """Traduz um estado genérico em expressão, sem importar o núcleo."""
        state_name = getattr(state, "name", str(state))
        previous_state = self._state
        self._state = state_name
        self._expression = self.STATE_EXPRESSIONS.get(state_name, FaceExpression.NORMAL)
        if state_name == "WAKING" and previous_state != "WAKING":
            self._wake_animation.stop()
            self._waking_progress = 0.0
            self._wake_animation.setStartValue(0.0)
            self._wake_animation.setEndValue(1.0)
            self._wake_animation.start()
        self.update()

    def set_expression(self, expression: FaceExpression) -> None:
        """Disponibiliza expressões visuais para comportamentos futuros."""
        self._expression = expression
        self.update()

    def get_waking_progress(self) -> float:
        return self._waking_progress

    def set_waking_progress(self, value: float) -> None:
        self._waking_progress = value
        self.update()

    wakingProgress = Property(float, get_waking_progress, set_waking_progress)

    def _advance_animation(self) -> None:
        self._phase += 0.065
        self._elapsed_ms += self._frame_timer.interval()
        if self._expression is FaceExpression.SLEEPING:
            self._blink = 1.0
        else:
            cycle = self._elapsed_ms % 4_200
            blink_phase = (cycle - 3_760) / 440
            self._blink = math.sin(blink_phase * math.pi) ** 2 if blink_phase >= 0 else 0.0
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.BACKGROUND)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        target = self._screen_rect()
        painter.setPen(QPen(self.SCREEN_BORDER, 2))
        painter.setBrush(self.BACKGROUND)
        painter.drawRoundedRect(target.adjusted(-3, -3, 3, 3), 16, 16)
        screen = QImage(self.LOGICAL_WIDTH, self.LOGICAL_HEIGHT, QImage.Format.Format_ARGB32)
        screen.fill(self.BACKGROUND)
        screen_painter = QPainter(screen)
        screen_painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self._draw_logical_face(screen_painter)
        screen_painter.end()
        painter.drawImage(target, screen)

    def _screen_rect(self) -> QRectF:
        available_width = max(1, self.width() - 46)
        available_height = max(1, self.height() - 36)
        scale = min(available_width / self.LOGICAL_WIDTH, available_height / self.LOGICAL_HEIGHT)
        width = self.LOGICAL_WIDTH * scale
        height = self.LOGICAL_HEIGHT * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2 - 6, width, height)

    def _draw_logical_face(self, painter: QPainter) -> None:
        if self._expression is FaceExpression.SLEEPING:
            self._draw_sleeping_eyes(painter)
        else:
            left_pose, right_pose = self._eye_poses()
            self._draw_pixel_eye(painter, *left_pose)
            self._draw_pixel_eye(painter, *right_pose)
        if self._expression is FaceExpression.SPEAKING:
            self._draw_equalizer(painter)
        elif self._expression is FaceExpression.LISTENING:
            self._draw_listening_indicator(painter)
        elif self._expression is FaceExpression.NORMAL:
            self._draw_clock(painter)

    def _eye_poses(self) -> tuple[tuple[int, int, int, int, float], tuple[int, int, int, int, float]]:
        bob = int(round(math.sin(self._phase) * 0.7))
        blink_height = max(1, int(round(8 * (1 - self._blink))))
        left = [21, 14 + bob, 11, blink_height, 0.0]
        right = [43, 14 + bob, 11, blink_height, 0.0]
        expression = self._expression
        if expression is FaceExpression.WAKING:
            opening = max(1, int(round(8 * self._waking_progress)))
            left[3] = right[3] = opening
            left[1] = right[1] = 15
        elif expression is FaceExpression.LISTENING:
            left[2] = right[2] = 12
            left[3] = right[3] = max(2, blink_height)
            shift = int(round(math.sin(self._phase * 0.55)))
            left[0] += shift
            right[0] += shift
        elif expression is FaceExpression.THINKING:
            sway = int(round(math.sin(self._phase * 0.42)))
            left[0], right[0] = 18 + sway, 40 + sway
            left[1], right[1] = 11, 11
            left[3], right[3] = max(3, blink_height - 1), max(3, blink_height - 1)
            left[4], right[4] = -0.22, -0.22
        elif expression is FaceExpression.SPEAKING:
            pulse = int(round((math.sin(self._phase * 2.0) + 1) * 0.7))
            left[3] = right[3] = max(3, blink_height - pulse)
        elif expression is FaceExpression.HAPPY:
            left[3] = right[3] = max(2, blink_height - 3)
            left[4], right[4] = 0.22, -0.22
        elif expression is FaceExpression.CURIOUS:
            left[0], right[0] = 25, 47
            left[1], right[1] = 12, 12
        elif expression is FaceExpression.SURPRISED:
            left[2] = right[2] = 13
            left[3] = right[3] = 10
        elif expression is FaceExpression.CONFUSED:
            left[0], right[0] = 18, 45
            left[3], right[3] = max(3, blink_height - 2), max(4, blink_height)
            left[4], right[4] = -0.25, 0.25
        return tuple(left), tuple(right)  # type: ignore[return-value]

    def _draw_pixel_eye(self, painter: QPainter, center_x: int, center_y: int, width: int, height: int, tilt: float) -> None:
        half_width = width / 2
        half_height = height / 2
        for y in range(center_y - math.ceil(half_height), center_y + math.ceil(half_height) + 1):
            for x in range(center_x - math.ceil(half_width), center_x + math.ceil(half_width) + 1):
                normalized_x = (x - center_x) / max(1, half_width)
                shifted_y = y - center_y - normalized_x * tilt * 2
                normalized_y = shifted_y / max(1, half_height)
                if abs(normalized_x) ** 3 + abs(normalized_y) ** 3 <= 1.12:
                    self._pixel(painter, x, y)

    def _draw_sleeping_eyes(self, painter: QPainter) -> None:
        bob = int(round(math.sin(self._phase) * 0.5))
        for center_x in (21, 43):
            for offset_x, offset_y in ((-4, 1), (-3, 0), (-2, -1), (-1, -1), (0, -1), (1, -1), (2, -1), (3, 0), (4, 1)):
                self._pixel(painter, center_x + offset_x, 15 + bob + offset_y)

    def _draw_equalizer(self, painter: QPainter) -> None:
        for index in range(9):
            wave = (math.sin(self._phase * 2.7 + index * 1.31) + math.sin(self._phase * 1.37 - index * 0.77)) / 2
            height = 1 + int(round((wave + 1) * 1.7))
            x = 32 + (index - 4) * 3
            for y in range(height):
                self._pixel(painter, x, 25 - y)
                self._pixel(painter, x + 1, 25 - y)

    def _draw_listening_indicator(self, painter: QPainter) -> None:
        pulse = int(round((math.sin(self._phase * 2.2) + 1) * 1.5))
        for index in range(3):
            x = 28 + index * 4
            y = 25 - ((index + pulse) % 3)
            self._pixel(painter, x, y)
            self._pixel(painter, x + 1, y)

    def _draw_clock(self, painter: QPainter) -> None:
        glyphs = {
            "0": ("111", "101", "101", "101", "111"), "1": ("010", "110", "010", "010", "111"),
            "2": ("111", "001", "111", "100", "111"), "3": ("111", "001", "111", "001", "111"),
            "4": ("101", "101", "111", "001", "001"), "5": ("111", "100", "111", "001", "111"),
            "6": ("111", "100", "111", "101", "111"), "7": ("111", "001", "010", "010", "010"),
            "8": ("111", "101", "111", "101", "111"), "9": ("111", "101", "111", "001", "111"),
            ":": ("0", "1", "0", "1", "0"),
        }
        x = 23
        for character in datetime.now().strftime("%H:%M"):
            glyph = glyphs[character]
            for row, line in enumerate(glyph):
                for column, value in enumerate(line):
                    if value == "1":
                        self._pixel(painter, x + column, 26 + row, self.CLOCK_COLOR)
            x += len(glyph[0]) + 1

    def _pixel(self, painter: QPainter, x: int, y: int, color: QColor | None = None) -> None:
        if 0 <= x < self.LOGICAL_WIDTH and 0 <= y < self.LOGICAL_HEIGHT:
            painter.fillRect(x, y, 1, 1, color or self.PIXEL_COLOR)
