import json
import pytest
from agents.exceptions import AgentError
from agents.test_case_generator import TestCaseGenerator
from models.requirement import StructuredRequirement, TestScope as Scope
from models.test_case import Priority, TestCaseType as CaseType
from orchestrator.session import Session


# Two test cases: one with tags, one without (exercises the tags default).
VALID_RESPONSE = json.dumps([
    {
        "id": "tc1",
        "title": "Successful login with valid credentials",
        "type": "happy_path",
        "priority": "high",
        "preconditions": ["User has a registered account"],
        "steps": [
            {
                "step_number": 1,
                "action": "Navigate to login page",
                "expected_result": "Login form is displayed",
            },
            {
                "step_number": 2,
                "action": "Enter valid email and password, click Submit",
                "expected_result": "Credentials are accepted",
            },
        ],
        "expected_outcome": "User is redirected to the dashboard",
        "tags": ["login", "smoke"],
    },
    {
        "id": "tc2",
        "title": "Login fails with invalid password",
        "type": "negative",
        "priority": "high",
        "preconditions": ["User has a registered account"],
        "steps": [
            {
                "step_number": 1,
                "action": "Enter valid email and wrong password, click Submit",
                "expected_result": "Error message is displayed",
            },
        ],
        "expected_outcome": "User remains on the login page",
        # tags field intentionally absent — exercises the Pydantic default
    },
])


@pytest.fixture
def generator():
    return TestCaseGenerator()


@pytest.fixture
def session():
    s = Session(raw_input="The system must allow users to log in.")
    s.requirement = StructuredRequirement(
        title="User Login",
        description="Allow authentication.",
        actors=["End user"],
        acceptance_criteria=["User can log in with valid credentials"],
        test_scope=Scope(in_scope=["login flow"], out_of_scope=["registration"]),
        raw_input="The system must allow users to log in.",
    )
    return s


# --- happy path ---

@pytest.mark.contract
def test_run_sets_test_cases_on_valid_response(generator, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value=VALID_RESPONSE)
    generator.run(session)
    assert len(session.test_cases) == 2
    assert session.test_cases[0].id == "tc1"
    assert session.test_cases[1].id == "tc2"


@pytest.mark.contract
def test_run_parses_enum_fields_correctly(generator, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value=VALID_RESPONSE)
    generator.run(session)
    assert session.test_cases[0].type == CaseType.HAPPY_PATH
    assert session.test_cases[0].priority == Priority.HIGH
    assert session.test_cases[1].type == CaseType.NEGATIVE


@pytest.mark.contract
def test_run_parses_steps_correctly(generator, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value=VALID_RESPONSE)
    generator.run(session)
    steps = session.test_cases[0].steps
    assert len(steps) == 2
    assert steps[0].step_number == 1
    assert steps[1].step_number == 2
    assert steps[0].action == "Navigate to login page"


@pytest.mark.contract
def test_run_uses_empty_list_as_tags_default(generator, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value=VALID_RESPONSE)
    generator.run(session)
    assert session.test_cases[1].tags == []


# --- max_tokens ---

@pytest.mark.contract
def test_run_uses_max_tokens_16000(generator, session, mocker):
    # 16000 is set explicitly to avoid truncation on large test suites.
    # If this regresses to the 4096 default, generation silently truncates.
    mock_chat = mocker.patch("agents.base_agent.chat", return_value=VALID_RESPONSE)
    generator.run(session)
    _, kwargs = mock_chat.call_args
    assert kwargs["max_tokens"] == 16000


# --- error handling ---

@pytest.mark.contract
def test_run_raises_agent_error_on_malformed_json(generator, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value="not json at all")
    with pytest.raises(AgentError, match="TestCaseGenerator"):
        generator.run(session)


@pytest.mark.contract
def test_run_raises_agent_error_when_response_is_object_not_array(generator, session, mocker):
    # The isinstance(data, list) guard is a separate check before Pydantic validation.
    mocker.patch("agents.base_agent.chat", return_value=json.dumps({"test_cases": []}))
    with pytest.raises(AgentError, match="TestCaseGenerator"):
        generator.run(session)


@pytest.mark.contract
def test_run_raises_agent_error_on_invalid_enum_value(generator, session, mocker):
    bad_response = json.dumps([{
        "id": "tc1",
        "title": "Some test",
        "type": "not_a_valid_type",
        "priority": "high",
        "preconditions": [],
        "steps": [],
        "expected_outcome": "Something happens",
    }])
    mocker.patch("agents.base_agent.chat", return_value=bad_response)
    with pytest.raises(AgentError, match="TestCaseGenerator"):
        generator.run(session)


@pytest.mark.contract
def test_run_does_not_set_test_cases_on_error(generator, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value="not json")
    with pytest.raises(AgentError):
        generator.run(session)
    assert session.test_cases == []
