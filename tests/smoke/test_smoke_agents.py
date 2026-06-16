"""
Smoke tests — real LLM calls, schema validity only.

Each test is independent: ClarificationAgent and TestCaseGenerator receive a
hardcoded StructuredRequirement rather than depending on RequirementsAnalyst.

Run with: pytest -m smoke
"""
import pytest
from agents.clarification_agent import ClarificationAgent
from agents.requirements_analyst import RequirementsAnalyst
from agents.test_case_generator import TestCaseGenerator
from models.requirement import AcceptanceCriterion as AC, StructuredRequirement, TestScope as Scope
from models.test_case import TestCaseType, Priority
from orchestrator.session import Session


RAW_INPUT = (
    "Registered users can reset a forgotten password by requesting an email "
    "with a reset link. The link expires after 24 hours."
)


def _base_session() -> Session:
    """Session with a hardcoded requirement — no LLM call needed."""
    s = Session(raw_input=RAW_INPUT)
    s.requirement = StructuredRequirement(
        title="Password Reset",
        description="Allow registered users to reset their password via email link.",
        actors=["Registered user", "Email service"],
        acceptance_criteria=[
            AC(id="AC-001", text="User receives a reset email after requesting it"),
            AC(id="AC-002", text="Reset link expires after 24 hours"),
            AC(id="AC-003", text="User can set a new password via the link"),
        ],
        test_scope=Scope(
            in_scope=["reset request flow", "link expiry", "password update"],
            out_of_scope=["registration", "login flow"],
        ),
        raw_input=RAW_INPUT,
    )
    return s


# --- RequirementsAnalyst ---

@pytest.mark.smoke
def test_requirements_analyst_produces_valid_schema():
    session = Session(raw_input=RAW_INPUT)
    RequirementsAnalyst().run(session)

    req = session.requirement
    assert req is not None
    assert isinstance(req, StructuredRequirement)
    assert req.title
    assert req.description
    assert isinstance(req.actors, list)
    assert isinstance(req.acceptance_criteria, list)
    for ac in req.acceptance_criteria:
        assert ac.id.startswith("AC-")
        assert ac.text
    assert isinstance(req.test_scope.in_scope, list)
    assert isinstance(req.test_scope.out_of_scope, list)
    assert req.raw_input == RAW_INPUT


# --- ClarificationAgent ---

@pytest.mark.smoke
def test_clarification_agent_produces_valid_schema():
    session = _base_session()
    ClarificationAgent().run(session)

    assert len(session.clarification_rounds) == 1
    round_ = session.clarification_rounds[0]
    assert isinstance(round_.questions, list)
    for q in round_.questions:
        assert q.id
        assert q.question
        assert q.context
        assert q.tier in ("blocking", "clarifying", "assumable")


# --- TestCaseGenerator ---

@pytest.mark.smoke
def test_test_case_generator_produces_valid_schema():
    session = _base_session()
    TestCaseGenerator().run(session)

    assert len(session.test_cases) >= 1
    for tc in session.test_cases:
        assert tc.id
        assert tc.title
        assert isinstance(tc.type, TestCaseType)
        assert isinstance(tc.priority, Priority)
        assert isinstance(tc.preconditions, list)
        assert len(tc.steps) >= 1
        assert tc.expected_outcome
        assert isinstance(tc.linked_criteria, list)
        for step in tc.steps:
            assert step.step_number >= 1
            assert step.action
            assert step.expected_result
