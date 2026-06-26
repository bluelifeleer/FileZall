from PySide6.QtCore import Qt

from filezall_core.models import ConflictPolicy
from filezall_desktop.conflict_dialog import ConflictDecision, ConflictPolicyDialog


def test_conflict_policy_dialog_offers_expected_choices(qtbot) -> None:
    dialog = ConflictPolicyDialog("app.txt")
    qtbot.addWidget(dialog)

    assert [button.text() for button in dialog.policy_buttons] == [
        "Overwrite",
        "Skip",
        "Rename",
        "Only if newer",
    ]
    assert dialog.apply_to_all_checkbox.text() == "Apply to all conflicts"


def test_conflict_policy_dialog_returns_selected_policy(qtbot) -> None:
    dialog = ConflictPolicyDialog("app.txt")
    qtbot.addWidget(dialog)

    dialog.rename_radio.setChecked(True)
    dialog.apply_to_all_checkbox.setChecked(True)
    qtbot.mouseClick(dialog.ok_button, Qt.MouseButton.LeftButton)

    assert dialog.decision() == ConflictDecision(
        policy=ConflictPolicy.RENAME,
        apply_to_all=True,
    )
