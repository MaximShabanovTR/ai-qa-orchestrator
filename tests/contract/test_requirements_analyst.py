import json
import pytest
from agents.exceptions import AgentError
from agents.requirements_analyst import RequirementsAnalyst
from orchestrator.session import Session


# Minimal valid Claude response — all fields required by StructuredRequirement.
# raw_input is intentionally absent: the agent injects it from session, not Claude.
VALID_RESPONSE = json.dumps({
    "title": "User Login",
    "description": "Allow users to authenticate with email and password.",
    "actors": ["End user", "Auth service"],
    "acceptance_criteria": [
        "User can log in with valid credentials",
        "User sees an error on invalid credentials",
    ],
    "test_scope": {
        "in_scope": ["login flow", "password validation"],
        "out_of_scope": ["registration", "password reset"],
    },
})


@pytest.fixture
def analyst():
    return RequirementsAnalyst()


@pytest.fixture
def session():
    return Session(raw_input="The system must allow users to log in.")


@pytest.mark.contract
def test_run_populates_requirement_on_valid_response(analyst, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value=VALID_RESPONSE)
    analyst.run(session)
    assert session.requirement is not None
    assert session.requirement.title == "User Login"
    assert session.requirement.actors == ["End user", "Auth service"]
    assert len(session.requirement.acceptance_criteria) == 2
    assert session.requirement.test_scope.in_scope == ["login flow", "password validation"]
    assert session.requirement.test_scope.out_of_scope == ["registration", "password reset"]


@pytest.mark.contract
def test_run_injects_raw_input_from_session_not_from_claude(analyst, session, mocker):
    # raw_input is not part of the Claude response schema — the agent adds it manually.
    # This test confirms the value comes from session, not from whatever Claude returned.
    mocker.patch("agents.base_agent.chat", return_value=VALID_RESPONSE)
    analyst.run(session)
    assert session.requirement.raw_input == session.raw_input


@pytest.mark.contract
def test_run_uses_default_max_tokens(analyst, session, mocker):
    mock_chat = mocker.patch("agents.base_agent.chat", return_value=VALID_RESPONSE)
    analyst.run(session)
    _, kwargs = mock_chat.call_args
    assert kwargs["max_tokens"] == 4096


@pytest.mark.contract
def test_run_raises_agent_error_on_malformed_json(analyst, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value="not json at all")
    with pytest.raises(AgentError, match="RequirementsAnalyst"):
        analyst.run(session)


@pytest.mark.contract
def test_run_raises_agent_error_on_missing_required_fields(analyst, session, mocker):
    # Claude returns valid JSON but omits required fields (e.g. acceptance_criteria)
    incomplete = json.dumps({"title": "Login", "description": "..."})
    mocker.patch("agents.base_agent.chat", return_value=incomplete)
    with pytest.raises(AgentError, match="RequirementsAnalyst"):
        analyst.run(session)


@pytest.mark.contract
def test_run_raises_agent_error_when_response_is_array_not_object(analyst, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value="[]")
    with pytest.raises(AgentError, match="RequirementsAnalyst"):
        analyst.run(session)


@pytest.mark.contract
def test_run_does_not_set_requirement_on_error(analyst, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value="not json")
    with pytest.raises(AgentError):
        analyst.run(session)
    assert session.requirement is None
