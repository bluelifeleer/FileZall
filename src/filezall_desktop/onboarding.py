from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class GettingStartedDialog(QDialog):
    focus_connection_requested = Signal()
    focus_local_requested = Signal()
    focus_remote_requested = Signal()

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
        actions.addWidget(self.focus_connection_button)
        actions.addWidget(self.focus_local_button)
        actions.addWidget(self.focus_remote_button)
        layout.addLayout(actions)

        self.focus_connection_button.clicked.connect(self.focus_connection_requested)
        self.focus_local_button.clicked.connect(self.focus_local_requested)
        self.focus_remote_button.clicked.connect(self.focus_remote_requested)
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
