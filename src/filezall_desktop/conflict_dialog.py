from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from filezall_core.models import ConflictPolicy


@dataclass(frozen=True)
class ConflictDecision:
    policy: ConflictPolicy
    apply_to_all: bool = False


class ConflictPolicyDialog(QDialog):
    def __init__(self, destination_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("File exists")

        layout = QVBoxLayout(self)
        message = QLabel(f"'{destination_name}' already exists. Choose how to continue.", self)
        message.setWordWrap(True)
        layout.addWidget(message)

        self.button_group = QButtonGroup(self)
        self.overwrite_radio = QRadioButton("Overwrite", self)
        self.skip_radio = QRadioButton("Skip", self)
        self.rename_radio = QRadioButton("Rename", self)
        self.newer_only_radio = QRadioButton("Only if newer", self)
        self.policy_buttons = [
            self.overwrite_radio,
            self.skip_radio,
            self.rename_radio,
            self.newer_only_radio,
        ]
        for index, button in enumerate(self.policy_buttons):
            self.button_group.addButton(button, index)
            layout.addWidget(button)
        self.overwrite_radio.setChecked(True)

        self.apply_to_all_checkbox = QCheckBox("Apply to all conflicts", self)
        layout.addWidget(self.apply_to_all_checkbox)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def decision(self) -> ConflictDecision:
        policy_by_button = {
            self.overwrite_radio: ConflictPolicy.OVERWRITE,
            self.skip_radio: ConflictPolicy.SKIP,
            self.rename_radio: ConflictPolicy.RENAME,
            self.newer_only_radio: ConflictPolicy.NEWER_ONLY,
        }
        checked = next(button for button in self.policy_buttons if button.isChecked())
        return ConflictDecision(
            policy=policy_by_button[checked],
            apply_to_all=self.apply_to_all_checkbox.isChecked(),
        )


def choose_conflict_policy(parent, destination_name: str) -> ConflictDecision | None:
    dialog = ConflictPolicyDialog(destination_name, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.decision()
