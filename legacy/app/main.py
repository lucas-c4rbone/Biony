"""Ponto de entrada do Biony Virtual Simulator."""

from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QGridLayout, QGroupBox, QLabel, QLineEdit, QListWidget, QMainWindow, QPushButton, QVBoxLayout, QWidget

from app.simulator import SimulatorModel, brain_mode_from_environment, create_brain
from core.biony_device import VALID_ANIMATIONS
from core.state_machine import BionyState
from face import FaceExpression, FaceWidget


class BionyWindow(QMainWindow):
    """Ferramenta compacta para observar e dirigir o Core virtual."""

    def __init__(self, model: SimulatorModel) -> None:
        super().__init__()
        self.model = model
        self.setWindowTitle("Biony Virtual Simulator")
        self.setMinimumSize(900, 620)
        self.resize(1080, 720)

        self.face = FaceWidget(self)
        self._animation_revision = 0
        self.state_label = QLabel()
        self.response_label = QLabel("Aguardando mensagem...")
        self.response_label.setWordWrap(True)
        self.last_event_label = QLabel()
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Digite uma mensagem para o Biony...")
        self.message_input.returnPressed.connect(self.send_message)
        self.send_button = QPushButton("Enviar")
        self.send_button.clicked.connect(self.send_message)
        self.state_box = self._create_state_box()
        self.expression_box = self._create_expression_box()
        self.animation_box = self._create_animation_box()
        self.confirm_box = QGroupBox("Confirmacao")
        self.confirm_box.setVisible(False)
        self._create_confirmation_controls()

        face_column = QVBoxLayout()
        face_column.addWidget(self.face, 1)
        face_column.addWidget(self.state_label)
        face_column.addWidget(self.response_label)
        input_row = QGridLayout()
        input_row.addWidget(self.message_input, 0, 0)
        input_row.addWidget(self.send_button, 0, 1)
        face_column.addLayout(input_row)

        tools_column = QVBoxLayout()
        tools_column.addWidget(self.state_box)
        tools_column.addWidget(self.expression_box)
        tools_column.addWidget(self.animation_box)
        tools_column.addWidget(self.confirm_box)
        tools_column.addWidget(QLabel("Eventos recentes"))
        self.events_list = QListWidget()
        tools_column.addWidget(self.events_list, 1)
        tools_column.addWidget(self.last_event_label)

        container = QWidget(self)
        layout = QGridLayout(container)
        layout.addLayout(face_column, 0, 0)
        layout.addLayout(tools_column, 0, 1)
        layout.setColumnStretch(0, 3)
        layout.setColumnStretch(1, 1)
        self.setCentralWidget(container)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #0b1119; color: #d8edf4; }
            QLabel { color: #a9bcc9; padding: 4px; }
            QGroupBox { border: 1px solid #26394e; margin-top: 8px; padding: 12px 8px 8px; }
            QGroupBox::title { color: #69eaf5; subcontrol-origin: margin; left: 8px; padding: 0 4px; }
            QLineEdit, QComboBox, QListWidget { background: #182231; border: 1px solid #26394e; padding: 8px; color: #d8edf4; }
            QPushButton { background: #173e49; border: 1px solid #318b9b; padding: 8px 12px; color: #d8edf4; }
            QPushButton:hover { background: #205969; }
        """)
        self.model.subscribe(self._update_from_model)

    def _create_state_box(self) -> QGroupBox:
        box = QGroupBox("Estado")
        layout = QVBoxLayout(box)
        selector = QComboBox(box)
        for state in BionyState:
            selector.addItem(state.name, state)
        button = QPushButton("Aplicar")
        button.clicked.connect(lambda: self.model.core.transition_to(selector.currentData()))
        layout.addWidget(selector)
        layout.addWidget(button)
        return box

    def _create_expression_box(self) -> QGroupBox:
        box = QGroupBox("Expressao")
        layout = QVBoxLayout(box)
        selector = QComboBox(box)
        for expression in FaceExpression:
            selector.addItem(expression.name, expression)
        selector.currentIndexChanged.connect(lambda _: self.model.set_expression(selector.currentData()))
        layout.addWidget(selector)
        return box

    def _create_animation_box(self) -> QGroupBox:
        box = QGroupBox("Animacao")
        layout = QVBoxLayout(box)
        selector = QComboBox(box)
        for animation in sorted(VALID_ANIMATIONS):
            selector.addItem(animation, animation)
        button = QPushButton("Executar")
        button.clicked.connect(lambda: self.model.play_animation(str(selector.currentData())))
        layout.addWidget(selector)
        layout.addWidget(button)
        return box

    def _create_confirmation_controls(self) -> None:
        layout = QVBoxLayout(self.confirm_box)
        self.confirm_label = QLabel()
        row = QGridLayout()
        yes = QPushButton("Sim")
        no = QPushButton("Nao")
        yes.clicked.connect(lambda: self._confirm("sim"))
        no.clicked.connect(lambda: self._confirm("nao"))
        row.addWidget(yes, 0, 0)
        row.addWidget(no, 0, 1)
        layout.addWidget(self.confirm_label)
        layout.addLayout(row)

    def send_message(self) -> None:
        message = self.message_input.text().strip()
        if not message:
            return
        self.message_input.clear()
        self.send_button.setEnabled(False)
        QTimer.singleShot(80, lambda: self._process_message(message))

    def _process_message(self, message: str) -> None:
        self.model.handle_message(message)
        self.send_button.setEnabled(True)
        self.message_input.setFocus()

    def _confirm(self, response: str) -> None:
        action_id = self.model.snapshot.pending_action_id
        if action_id:
            self.model.confirm_pending_action(action_id, response)

    def _update_from_model(self, snapshot: object) -> None:
        animation_revision = getattr(snapshot, "animation_revision", 0)
        animation = getattr(snapshot, "animation", "")
        self.face.set_state(self.model.state_machine.state)
        if self.model.state_machine.state is not BionyState.IDLE:
            self.face.stop_animation()
        elif animation and animation_revision > self._animation_revision:
            self._animation_revision = animation_revision
            self.face.play_animation(animation)
        self.state_label.setText(f"STATE: {self.model.state_machine.state.name}")
        self.response_label.setText(self.model.snapshot.response or "Aguardando mensagem...")
        self.last_event_label.setText(f"LAST EVENT: {self.model.snapshot.last_event or '-'} | DEVICE: virtual")
        self.events_list.clear()
        self.events_list.addItems(self.model.snapshot.events)
        pending = self.model.snapshot.pending_action_id
        self.confirm_box.setVisible(pending is not None)
        if pending:
            self.confirm_label.setText(f"Acao pendente: {pending}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Biony Virtual Simulator")
    parser.add_argument("--brain", choices=("simulated", "openai", "openrouter"), default=brain_mode_from_environment())
    args = parser.parse_args(argv)
    app = QApplication(sys.argv)
    app.setApplicationName("Biony Virtual Simulator")
    window = BionyWindow(SimulatorModel(create_brain(args.brain)))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
