from PySide6.QtCore import Qt

from filezall_core.agent_status import AgentStatus, AgentStatusViewModel
from filezall_desktop.agent_status_card import AgentStatusCard


def test_agent_status_card_renders_states_and_actions(qtbot) -> None:
    card = AgentStatusCard()
    qtbot.addWidget(card)

    card.set_status(
        AgentStatusViewModel(
            state=AgentStatus.NOT_INSTALLED,
            message="Agent is not installed.",
            primary_action="Install Agent",
        )
    )

    assert card.state_label.text() == "Not Installed"
    assert card.message_label.text() == "Agent is not installed."
    assert card.primary_button.text() == "Install Agent"
    assert card.primary_button.property("buttonRole") == "success"
    assert card.danger_button.isHidden()

    card.set_status(
        AgentStatusViewModel(
            state=AgentStatus.OUTDATED,
            version="0.0.1",
            message="Agent update is available.",
            primary_action="Update Agent",
            danger_action="Uninstall Agent",
        )
    )

    assert card.state_label.text() == "Outdated"
    assert card.version_label.text() == "v0.0.1"
    assert card.primary_button.text() == "Update Agent"
    assert card.primary_button.property("buttonRole") == "warning"
    assert card.danger_button.text() == "Uninstall Agent"
    assert card.danger_button.property("buttonRole") == "danger"
    assert not card.danger_button.isHidden()


def test_agent_status_card_emits_actions(qtbot) -> None:
    card = AgentStatusCard()
    qtbot.addWidget(card)
    triggered = []
    card.primary_action_requested.connect(lambda: triggered.append("primary"))
    card.danger_action_requested.connect(lambda: triggered.append("danger"))
    card.set_status(
        AgentStatusViewModel(
            state=AgentStatus.UNHEALTHY,
            message="Agent is unhealthy.",
            primary_action="Reinstall Agent",
            danger_action="Uninstall Agent",
        )
    )

    qtbot.mouseClick(card.primary_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(card.danger_button, Qt.MouseButton.LeftButton)

    assert triggered == ["primary", "danger"]


def test_agent_card_shows_operation_steps(qtbot) -> None:
    card = AgentStatusCard()
    qtbot.addWidget(card)

    card.set_operation_steps(
        [
            "Agent install: uploading package",
            "Agent install: checking health endpoint",
        ],
        final_message="Agent installed and verified",
    )

    assert [label.text() for label in card.step_labels] == [
        "1. Agent install: uploading package",
        "2. Agent install: checking health endpoint",
    ]
    assert card.message_label.text() == "Agent installed and verified"
