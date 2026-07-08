import json
import pytest
from models.planning import RemediationAction
from workflow.graph import build_graph


# --- LLM response constants ---
# Each constant is what Claude returns for one call, in the order the graph makes them.

REQUIREMENT_RESPONSE = json.dumps({
    "title": "User Login",
    "description": "Allow users to authenticate.",
    "actors": ["User"],
    "acceptance_criteria": [
        {"id": "AC-001", "text": "User can log in with valid credentials"},
        {"id": "AC-002", "text": "User sees an error on invalid credentials"},
    ],
    "test_scope": {"in_scope": ["login flow"], "out_of_scope": []},
})

CLARIFY_NO_QUESTIONS = json.dumps({"questions": []})

REVIEW_NO_SEMANTIC_FINDINGS = json.dumps([])

# Both ACs covered — TraceabilityMatrix has no gaps → ReviewReport.passed = True
FULL_COVERAGE_SUITE = json.dumps([
    {
        "id": "TC-001",
        "title": "Successful login",
        "type": "happy_path",
        "priority": "high",
        "preconditions": [],
        "steps": [{"step_number": 1, "action": "Login", "expected_result": "Logged in"}],
        "expected_outcome": "User is on dashboard",
        "linked_criteria": ["AC-001"],
    },
    {
        "id": "TC-002",
        "title": "Invalid login shows error",
        "type": "negative",
        "priority": "high",
        "preconditions": [],
        "steps": [{"step_number": 1, "action": "Login with bad creds", "expected_result": "Error shown"}],
        "expected_outcome": "Error message displayed",
        "linked_criteria": ["AC-002"],
    },
])

# Only AC-001 covered — AC-002 is a gap → ReviewReport._check_coverage_gaps fires
# → COVERAGE_GAP ERROR → PlannerDecision.from_report returns REGENERATE_ALL
PARTIAL_COVERAGE_SUITE = json.dumps([
    {
        "id": "TC-001",
        "title": "Successful login",
        "type": "happy_path",
        "priority": "high",
        "preconditions": [],
        "steps": [{"step_number": 1, "action": "Login", "expected_result": "Logged in"}],
        "expected_outcome": "User is on dashboard",
        "linked_criteria": ["AC-001"],
    },
])


def _initial_state(raw_input: str = "User must be able to log in.") -> dict:
    return {
        "raw_input": raw_input,
        "requirement": None,
        "clarification_rounds": [],
        "clarification_complete": False,
        "pending_answers": {},
        "test_cases": [],
        "traceability_matrix": None,
        "review_report": None,
        "review_rounds": 0,
        "planner_decision": None,
    }


# --- no retry: generate passes on first attempt ---

@pytest.mark.contract
def test_graph_completes_without_retry_when_review_passes(mocker):
    # 4 LLM calls: analyze → clarify → generate → review-semantic
    mocker.patch("agents.base_agent.chat", side_effect=[
        REQUIREMENT_RESPONSE,
        CLARIFY_NO_QUESTIONS,
        FULL_COVERAGE_SUITE,
        REVIEW_NO_SEMANTIC_FINDINGS,
    ])
    graph = build_graph()
    config = {"configurable": {"thread_id": "test-no-retry"}}
    graph.invoke(_initial_state(), config=config)
    state = graph.get_state(config).values
    assert state["review_rounds"] == 0
    assert state["planner_decision"].action == RemediationAction.DONE
    assert state["planner_decision"].reason == "passed"


# --- one retry: generate fails first, passes on second attempt ---

@pytest.mark.contract
def test_graph_retries_once_when_first_suite_has_coverage_gaps(mocker):
    # 6 LLM calls: analyze → clarify → generate(partial) → review-semantic
    #              → generate(full) → review-semantic
    mock_chat = mocker.patch("agents.base_agent.chat", side_effect=[
        REQUIREMENT_RESPONSE,
        CLARIFY_NO_QUESTIONS,
        PARTIAL_COVERAGE_SUITE,
        REVIEW_NO_SEMANTIC_FINDINGS,
        FULL_COVERAGE_SUITE,
        REVIEW_NO_SEMANTIC_FINDINGS
    ])
    graph = build_graph()
    config = {"configurable": {"thread_id": "test-one-retry"}}
    graph.invoke(_initial_state(), config=config)
    state = graph.get_state(config).values
    assert state["review_rounds"] == 1
    assert state["planner_decision"].action == RemediationAction.DONE
    assert state["planner_decision"].reason == "passed"
    assert mock_chat.call_count == 6
