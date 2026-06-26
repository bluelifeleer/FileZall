from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QWidget

from filezall_core.agent_status import AgentStatus, AgentStatusViewModel


class AgentStatusCard(QWidget):
    primary_action_requested = Signal()
    danger_action_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title_label = QLabel("Agent", self)
        self.state_label = QLabel("Unknown", self)
        self.version_label = QLabel("", self)
        header.addWidget(self.title_label)
        header.addWidget(self.state_label)
        header.addWidget(self.version_label)
        header.addStretch(1)
        layout.addLayout(header)

        self.message_label = QLabel("", self)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        actions = QHBoxLayout()
        self.primary_button = QPushButton("", self)
        self.danger_button = QPushButton("", self)
        actions.addWidget(self.primary_button)
        actions.addWidget(self.danger_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.steps_layout = QVBoxLayout()
        self.step_labels: list[QLabel] = []
        layout.addLayout(self.steps_layout)

        self.primary_button.clicked.connect(self.primary_action_requested)
        self.danger_button.clicked.connect(self.danger_action_requested)
        self.primary_button.hide()
        self.danger_button.hide()

    def set_status(self, model: AgentStatusViewModel) -> None:
        self.state_label.setText(_state_text(model.state))
        self.version_label.setText(f"v{model.version}" if model.version else "")
        self.message_label.setText(model.message)
        self._configure_button(self.primary_button, model.primary_action, _primary_role(model.state))
        self._configure_button(self.danger_button, model.danger_action, "danger")

    def clear_operation_steps(self) -> None:
        while self.steps_layout.count():
            item = self.steps_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.step_labels = []

    def add_operation_step(self, message: str) -> None:
        label = QLabel(f"{len(self.step_labels) + 1}. {message}", self)
        label.setWordWrap(True)
        self.step_labels.append(label)
        self.steps_layout.addWidget(label)

    def set_operation_steps(
        self,
        messages: list[str],
        *,
        final_message: str | None = None,
    ) -> None:
        self.clear_operation_steps()
        for message in messages:
            self.add_operation_step(message)
        if final_message is not None:
            self.message_label.setText(final_message)

    def set_operation_result(self, message: str) -> None:
        self.message_label.setText(message)

    @staticmethod
    def _configure_button(button: QPushButton, text: str | None, role: str) -> None:
        if not text:
            button.hide()
            return
        button.setText(text)
        button.setProperty("buttonRole", role)
        button.show()


def _state_text(state: AgentStatus) -> str:
    return state.value.replace("_", " ").title()


def _primary_role(state: AgentStatus) -> str:
    if state in {AgentStatus.OUTDATED, AgentStatus.UPDATE_AVAILABLE, AgentStatus.UNHEALTHY}:
        return "warning"
    return "primary"
