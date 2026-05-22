import json
import pytest
from agents.clarification_agent import ClarificationAgent
from agents.exceptions import AgentError
from models.clarification import QuestionTier
from models.requirement import StructuredRequirement, TestScope as Scope
from orchestrator.session import Session


VALID_RESPONSE = json.dumps({
    "questions": [
        {
            "id": "q1",
            "question": "Is multi-factor authentication required?",
            "context": "Affects login flow complexity.",
            "tier": "blocking",
            "assumption": None,
        },
        {
            "id": "q2",
            "question": "Should login attempts be rate-limited?",
            "context": "Security consideration.",
            "tier": "clarifying",
            "assumption": None,
        },
        {
            "id": "q3",
            "question": "Should session timeout be enforced?",
            "context": "Standard security practice.",
            "tier": "assumable",
            "assumption": "Yes, 30-minute timeout is standard.",
        },
    ]
})


@pytest.fixture
def agent():
    return ClarificationAgent()


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
def test_run_appends_round_on_valid_response(agent, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value=VALID_RESPONSE)
    agent.run(session)
    assert len(session.clarification_rounds) == 1
    assert len(session.clarification_rounds[0].questions) == 3


@pytest.mark.contract
def test_run_parses_question_tiers_correctly(agent, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value=VALID_RESPONSE)
    agent.run(session)
    questions = session.clarification_rounds[0].questions
    assert questions[0].tier == QuestionTier.BLOCKING
    assert questions[1].tier == QuestionTier.CLARIFYING
    assert questions[2].tier == QuestionTier.ASSUMABLE


@pytest.mark.contract
def test_run_preserves_assumption_field(agent, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value=VALID_RESPONSE)
    agent.run(session)
    assumable = session.clarification_rounds[0].questions[2]
    assert assumable.assumption == "Yes, 30-minute timeout is standard."


@pytest.mark.contract
def test_run_appends_successive_rounds_without_replacing(agent, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value=VALID_RESPONSE)
    agent.run(session)
    agent.run(session)
    assert len(session.clarification_rounds) == 2


# --- graceful empty round ---

@pytest.mark.contract
def test_run_appends_empty_round_when_questions_list_is_empty(agent, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value=json.dumps({"questions": []}))
    agent.run(session)
    assert len(session.clarification_rounds) == 1
    assert session.clarification_rounds[0].questions == []


@pytest.mark.contract
def test_run_appends_empty_round_when_questions_key_is_absent(agent, session, mocker):
    # data.get("questions") or [] is a graceful fallback — not an error
    mocker.patch("agents.base_agent.chat", return_value=json.dumps({}))
    agent.run(session)
    assert len(session.clarification_rounds) == 1
    assert session.clarification_rounds[0].questions == []


# --- start_id computation ---

@pytest.mark.contract
def test_run_computes_start_id_from_cumulative_prior_questions(agent, session, mocker):
    # First round has 3 questions — second round's start_id should be 4.
    # Verified by inspecting what _load_prompt was called with.
    mocker.patch("agents.base_agent.chat", return_value=VALID_RESPONSE)
    agent.run(session)  # round 1: 3 questions appended

    mock_load = mocker.patch.object(agent, "_load_prompt", return_value="system prompt")
    mocker.patch("agents.base_agent.chat", return_value=json.dumps({"questions": []}))
    agent.run(session)  # round 2

    _, kwargs = mock_load.call_args
    assert kwargs["start_id"] == 4


# --- error handling ---

@pytest.mark.contract
def test_run_raises_agent_error_on_malformed_json(agent, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value="not json")
    with pytest.raises(AgentError, match="ClarificationAgent"):
        agent.run(session)


@pytest.mark.contract
def test_run_raises_agent_error_on_invalid_tier_value(agent, session, mocker):
    bad_response = json.dumps({
        "questions": [{
            "id": "q1",
            "question": "Something?",
            "context": "context.",
            "tier": "not_a_valid_tier",
        }]
    })
    mocker.patch("agents.base_agent.chat", return_value=bad_response)
    with pytest.raises(AgentError, match="ClarificationAgent"):
        agent.run(session)


@pytest.mark.contract
def test_run_does_not_append_round_on_error(agent, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value="not json")
    with pytest.raises(AgentError):
        agent.run(session)
    assert session.clarification_rounds == []
