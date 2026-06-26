from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class GettingStartedDialog(QDialog):
    focus_connection_requested = Signal()
    focus_local_requested = Signal()
    focus_remote_requested = Signal()
    test_connection_requested = Signal()
    save_site_requested = Signal()
    dismissed_changed = Signal(bool)

    def __init__(self, texts: dict[str, str | list[str]], parent=None) -> None:
        super().__init__(parent)
        self.step_labels: list[QLabel] = []
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        self.intro_label = QLabel("", self)
        self.intro_label.setWordWrap(True)
        layout.addWidget(self.intro_label)

        for _index in range(6):
            label = QLabel("", self)
            label.setWordWrap(True)
            self.step_labels.append(label)
            layout.addWidget(label)

        actions = QHBoxLayout()
        self.focus_connection_button = QPushButton(self)
        self.focus_local_button = QPushButton(self)
        self.focus_remote_button = QPushButton(self)
        self.start_setup_button = QPushButton(self)
        self.test_connection_button = QPushButton(self)
        self.save_site_button = QPushButton(self)
        self.close_button = QPushButton(self)
        actions.addWidget(self.focus_connection_button)
        actions.addWidget(self.focus_local_button)
        actions.addWidget(self.focus_remote_button)
        actions.addWidget(self.start_setup_button)
        actions.addWidget(self.test_connection_button)
        actions.addWidget(self.save_site_button)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.dismiss_checkbox = QCheckBox(self)
        layout.addWidget(self.dismiss_checkbox)

        self.focus_connection_button.clicked.connect(self.focus_connection_requested)
        self.focus_local_button.clicked.connect(self.focus_local_requested)
        self.focus_remote_button.clicked.connect(self.focus_remote_requested)
        self.start_setup_button.clicked.connect(self.focus_connection_requested)
        self.test_connection_button.clicked.connect(self.test_connection_requested)
        self.save_site_button.clicked.connect(self.save_site_requested)
        self.close_button.clicked.connect(self.close)
        self.dismiss_checkbox.toggled.connect(self.dismissed_changed)
        self.set_connection_ready(False)
        self.set_texts(texts)

    def set_texts(self, texts: dict[str, str | list[str]]) -> None:
        self.setWindowTitle(str(texts["title"]))
        self.intro_label.setText(str(texts["intro"]))
        steps = list(texts["steps"])
        for label, text in zip(self.step_labels, steps, strict=True):
            label.setText(str(text))
        self.focus_connection_button.setText(str(texts["focus_connection"]))
        self.focus_local_button.setText(str(texts["focus_local"]))
        self.focus_remote_button.setText(str(texts["focus_remote"]))
        self.start_setup_button.setText(str(texts["start_setup"]))
        self.test_connection_button.setText(str(texts["test_connection"]))
        self.save_site_button.setText(str(texts["save_site"]))
        self.close_button.setText(str(texts["close"]))
        self.dismiss_checkbox.setText(str(texts["dismiss"]))

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def set_connection_ready(self, ready: bool) -> None:
        self.save_site_button.setEnabled(ready)
