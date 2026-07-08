import json
import pytest
from agents.exceptions import AgentError
from agents.review_agent import ReviewAgent
from models.requirement import AcceptanceCriterion as AC, StructuredRequirement, TestScope as Scope
from models.test_case import Priority, TestCase, TestCaseType, TestStep
from models.traceability import TraceabilityMatrix
from orchestrator.session import Session


VALID_SEMANTIC_RESPONSE = json.dumps([
    {
        "category": "weak_step",
        "severity": "warning",
        "message": "Step 1 says 'verify it works' — not executable.",
        "test_case_ids": ["TC-001"],
        "criterion_ids": [],
        "source": "llm",
    },
    {
        "category": "semantic_gap",
        "severity": "error",
        "message": "No test covers logout after session timeout.",
        "test_case_ids": [],
        "criterion_ids": ["AC-001"],
        "source": "llm",
    },
])


@pytest.fixture
def agent():
    return ReviewAgent()


@pytest.fixture
def session():
    requirement = StructuredRequirement(
        title="User Login",
        description="Allow authentication.",
        actors=["End user"],
        acceptance_criteria=[AC(id="AC-001", text="User can log in with valid credentials")],
        test_scope=Scope(in_scope=["login flow"], out_of_scope=["registration"]),
        raw_input="The system must allow users to log in.",
    )
    test_cases = [
        TestCase(
            id="TC-001",
            title="Successful login",
            type=TestCaseType.HAPPY_PATH,
            priority=Priority.HIGH,
            preconditions=[],
            steps=[TestStep(step_number=1, action="Log in", expected_result="Logged in")],
            expected_outcome="User is on dashboard",
            linked_criteria=["AC-001"],
        )
    ]
    s = Session(raw_input="The system must allow users to log in.")
    s.requirement = requirement
    s.test_cases = test_cases
    s.traceability_matrix = TraceabilityMatrix.build(requirement, test_cases)
    return s


# --- happy path ---

@pytest.mark.contract
def test_run_merges_semantic_findings_with_deterministic_findings(agent, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value=VALID_SEMANTIC_RESPONSE)
    agent.run(session)
    sources = [f.source for f in session.review_report.findings]
    assert sources.count("llm") == 2
    assert "deterministic" in sources  # MISSING_TEST_TYPE fires: only a happy_path case exists


@pytest.mark.contract
def test_run_preserves_deterministic_findings_on_llm_call(agent, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value=VALID_SEMANTIC_RESPONSE)
    agent.run(session)
    categories = [f.category.value for f in session.review_report.findings]
    assert "missing_test_type" in categories
    assert "weak_step" in categories
    assert "semantic_gap" in categories


# --- error handling ---

@pytest.mark.contract
def test_run_raises_agent_error_on_malformed_json(agent, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value="not json at all")
    with pytest.raises(AgentError, match="ReviewAgent"):
        agent.run(session)


@pytest.mark.contract
def test_run_keeps_only_deterministic_findings_when_llm_response_is_malformed_json(agent, session, mocker):
    mocker.patch("agents.base_agent.chat", return_value="not json at all")
    with pytest.raises(AgentError):
        agent.run(session)
    assert all(f.source == "deterministic" for f in session.review_report.findings)


@pytest.mark.contract
def test_run_discards_entire_batch_when_one_semantic_finding_fails_validation(agent, session, mocker):
    # First item is valid, second has an invalid category — model_validate raises
    # partway through the batch. This must not leave the first item merged in:
    # a partially-validated LLM batch is worse than none at all.
    mixed_response = json.dumps([
        {
            "category": "weak_step",
            "severity": "warning",
            "message": "Step 1 is vague.",
            "test_case_ids": ["TC-001"],
            "criterion_ids": [],
            "source": "llm",
        },
        {
            "category": "not_a_real_category",
            "severity": "warning",
            "message": "This item is malformed.",
            "test_case_ids": [],
            "criterion_ids": [],
            "source": "llm",
        },
    ])
    mocker.patch("agents.base_agent.chat", return_value=mixed_response)
    with pytest.raises(AgentError, match="ReviewAgent"):
        agent.run(session)
    assert all(f.source == "deterministic" for f in session.review_report.findings)
