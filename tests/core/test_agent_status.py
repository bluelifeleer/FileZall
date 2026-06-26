from filezall_core.agent_status import (
    AgentStatus,
    AgentStatusViewModel,
    view_model_for_agent,
)


def test_agent_status_view_model_states() -> None:
    assert view_model_for_agent(None).state is AgentStatus.UNKNOWN
    assert view_model_for_agent(False).state is AgentStatus.NOT_INSTALLED
    assert view_model_for_agent(True, version="0.1.0").state is AgentStatus.INSTALLED
    assert view_model_for_agent(True, version="0.0.1", current_version="0.1.0").state is AgentStatus.OUTDATED
    assert view_model_for_agent(True, healthy=False).state is AgentStatus.UNHEALTHY
    assert view_model_for_agent(True, update_available=True).state is AgentStatus.UPDATE_AVAILABLE
    assert view_model_for_agent(None, operation="installing").state is AgentStatus.INSTALLING
    assert view_model_for_agent(True, operation="uninstalling").state is AgentStatus.UNINSTALLING
    assert view_model_for_agent(False, unavailable=True).state is AgentStatus.UNAVAILABLE


def test_agent_status_view_model_actions_and_message() -> None:
    model = view_model_for_agent(
        False,
        message="Agent token is missing.",
    )

    assert model == AgentStatusViewModel(
        state=AgentStatus.NOT_INSTALLED,
        version=None,
        message="Agent token is missing.",
        primary_action="Install Agent",
        danger_action=None,
    )

    outdated = view_model_for_agent(True, version="0.0.1", current_version="0.1.0")
    assert outdated.primary_action == "Update Agent"
    assert outdated.danger_action == "Uninstall Agent"
