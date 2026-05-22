"""
Eval tests for TestCaseGenerator — real LLM, deterministic rubric checks.

Each parametrized case makes ONE LLM call then checks all metrics against
that single response. Splitting metrics into separate tests would multiply
API cost without improving signal.

Run with: pytest -m eval
"""
import pytest
from agents.test_case_generator import TestCaseGenerator
from models.test_case import TestCaseType
from orchestrator.session import Session
from tests.evals.fixtures import ALL_FIXTURES, EvalFixture


def _run_generator(fixture: EvalFixture) -> Session:
    session = Session(raw_input=fixture.requirement.raw_input)
    session.requirement = fixture.requirement
    TestCaseGenerator().run(session)
    return session


@pytest.mark.eval
@pytest.mark.parametrize("fixture", ALL_FIXTURES, ids=lambda f: f.name)
def test_type_coverage(fixture):
    """Suite must contain at least one happy path, negative, and edge case."""
    session = _run_generator(fixture)
    types = {tc.type for tc in session.test_cases}

    assert TestCaseType.HAPPY_PATH in types, (
        f"[{fixture.name}] No happy path test cases in suite of {len(session.test_cases)}"
    )
    assert TestCaseType.NEGATIVE in types, (
        f"[{fixture.name}] No negative test cases in suite of {len(session.test_cases)}"
    )
    assert TestCaseType.EDGE_CASE in types, (
        f"[{fixture.name}] No edge case test cases in suite of {len(session.test_cases)}"
    )


@pytest.mark.eval
@pytest.mark.parametrize("fixture", ALL_FIXTURES, ids=lambda f: f.name)
def test_ac_traceability(fixture):
    """Number of test cases must be at least equal to number of acceptance criteria.

    This is a proxy for traceability: if the generator produces fewer tests than
    there are ACs, at least one AC is likely untested.
    """
    session = _run_generator(fixture)
    ac_count = len(fixture.requirement.acceptance_criteria)
    tc_count = len(session.test_cases)

    assert tc_count >= ac_count, (
        f"[{fixture.name}] {tc_count} test cases for {ac_count} acceptance criteria"
    )


@pytest.mark.eval
@pytest.mark.parametrize("fixture", ALL_FIXTURES, ids=lambda f: f.name)
def test_structural_completeness(fixture):
    """Every test case must have at least one step and a non-empty expected outcome."""
    session = _run_generator(fixture)

    for tc in session.test_cases:
        assert len(tc.steps) >= 1, (
            f"[{fixture.name}] Test case '{tc.id}' has no steps"
        )
        assert tc.expected_outcome, (
            f"[{fixture.name}] Test case '{tc.id}' has an empty expected outcome"
        )
        for step in tc.steps:
            assert step.action, (
                f"[{fixture.name}] Step {step.step_number} in '{tc.id}' has no action"
            )
            assert step.expected_result, (
                f"[{fixture.name}] Step {step.step_number} in '{tc.id}' has no expected result"
            )
