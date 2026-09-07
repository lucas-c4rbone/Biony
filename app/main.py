"""Ponto de entrada do primeiro protótipo visual do Biony."""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QMainWindow, QVBoxLayout, QWidget

from core import BionyState, Brain, SimulatedBrain, StateMachine
from face import FaceExpression, FaceWidget


class BionyWindow(QMainWindow):
    """Janela de tela única que conecta o núcleo ao rosto do Biony."""

    KEY_STATES = {
        Qt.Key.Key_S: BionyState.SLEEPING,
        Qt.Key.Key_B: BionyState.WAKING,
        Qt.Key.Key_L: BionyState.LISTENING,
        Qt.Key.Key_T: BionyState.THINKING,
        Qt.Key.Key_P: BionyState.SPEAKING,
        Qt.Key.Key_I: BionyState.IDLE,
    }

    def __init__(self, brain: Brain | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Biony")
        self.setMinimumSize(620, 460)
        self.resize(760, 560)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowCloseButtonHint)

        self._brain = brain or SimulatedBrain()
        self._pending_response = ""

        self.face = FaceWidget(self)
        self.response_label = QLabel("", self)
        self.response_label.setObjectName("responseLabel")
        self.response_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.response_label.setWordWrap(True)
        self.response_label.setMinimumHeight(28)

        self.message_input = QLineEdit(self)
        self.message_input.setObjectName("messageInput")
        self.message_input.setPlaceholderText("Diga algo ao Biony...")
        self.message_input.setClearButtonEnabled(True)
        self.message_input.returnPressed.connect(self.send_message)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(22, 12, 22, 18)
        layout.setSpacing(8)
        layout.addWidget(self.face, 1)
        layout.addWidget(self.response_label)
        layout.addWidget(self.message_input)
        self.setCentralWidget(container)
        self._apply_conversation_style()

        self.state_machine = StateMachine()
        self.state_machine.subscribe(self.face.set_state)
        self._expression_shortcuts = self._create_expression_shortcuts()

    def _create_expression_shortcuts(self) -> list[QShortcut]:
        """Atalhos de inspeção visual que não conflitam com a caixa de texto."""
        expressions = {
            "Ctrl+Alt+N": FaceExpression.NORMAL,
            "Ctrl+Alt+H": FaceExpression.HAPPY,
            "Ctrl+Alt+C": FaceExpression.CURIOUS,
            "Ctrl+Alt+U": FaceExpression.SURPRISED,
            "Ctrl+Alt+F": FaceExpression.CONFUSED,
        }
        shortcuts: list[QShortcut] = []
        for sequence, expression in expressions.items():
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(lambda selected=expression: self.face.set_expression(selected))
            shortcuts.append(shortcut)
        return shortcuts

    def send_message(self) -> None:
        """Simula os turnos de uma conversa, mantendo o rosto como protagonista."""
        message = self.message_input.text().strip()
        if not message or not self.message_input.isEnabled():
            return

        self.message_input.clear()
        self.message_input.setEnabled(False)
        self.response_label.setText("")
        self.state_machine.transition_to(BionyState.LISTENING)
        QTimer.singleShot(450, lambda: self._start_thinking(message))

    def _start_thinking(self, message: str) -> None:
        self.state_machine.transition_to(BionyState.THINKING)
        self._pending_response = self._brain.respond(message)
        QTimer.singleShot(850, self._start_speaking)

    def _start_speaking(self) -> None:
        self.response_label.setText(self._pending_response)
        self.state_machine.transition_to(BionyState.SPEAKING)
        display_time = max(1_800, min(4_000, len(self._pending_response) * 38))
        QTimer.singleShot(display_time, self._return_to_idle)

    def _return_to_idle(self) -> None:
        self.state_machine.transition_to(BionyState.IDLE)
        self.message_input.setEnabled(True)
        self.message_input.setFocus()

    def _apply_conversation_style(self) -> None:
        self.setStyleSheet("""
            QLineEdit#messageInput {
                background: #182231;
                border: 1px solid #26394e;
                border-radius: 14px;
                color: #d8edf4;
                font: 13px 'Segoe UI';
                padding: 10px 14px;
            }
            QLineEdit#messageInput:focus { border-color: #5cbcd3; }
            QLineEdit#messageInput:disabled { color: #748596; }
            QLabel#responseLabel {
                color: #a9bcc9;
                font: 12px 'Segoe UI';
                padding: 2px 18px;
            }
        """)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if self.message_input.hasFocus() and event.key() not in self.KEY_STATES:
            super().keyPressEvent(event)
            return
        state = self.KEY_STATES.get(event.key())
        if state is not None:
            self.state_machine.transition_to(state)
            event.accept()
            return
        super().keyPressEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Biony")
    window = BionyWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
