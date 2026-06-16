import pytest
from models.requirement import AcceptanceCriterion as AC, StructuredRequirement, TestScope
from models.test_case import TestCase, TestCaseType, Priority, TestStep
from models.traceability import TraceabilityMatrix


def make_requirement(*ac_ids: str) -> StructuredRequirement:
    return StructuredRequirement(
        title="Test Feature",
        description="A feature.",
        actors=["User"],
        acceptance_criteria=[AC(id=ac_id, text=f"Criterion {ac_id}") for ac_id in ac_ids],
        test_scope=TestScope(in_scope=["feature"], out_of_scope=[]),
        raw_input="Some requirement.",
    )


def make_test_case(tc_id: str, *linked: str) -> TestCase:
    return TestCase(
        id=tc_id,
        title=f"Test {tc_id}",
        type=TestCaseType.HAPPY_PATH,
        priority=Priority.MEDIUM,
        preconditions=[],
        steps=[TestStep(step_number=1, action="Do something", expected_result="Something happens")],
        expected_outcome="Done.",
        linked_criteria=list(linked),
    )


# --- coverage dict ---

@pytest.mark.unit
def test_build_all_acs_appear_as_keys():
    req = make_requirement("AC-001", "AC-002", "AC-003")
    matrix = TraceabilityMatrix.build(req, [])
    assert set(matrix.coverage.keys()) == {"AC-001", "AC-002", "AC-003"}


@pytest.mark.unit
def test_build_covered_ac_contains_tc_id():
    req = make_requirement("AC-001", "AC-002")
    tc = make_test_case("TC-001", "AC-001")
    matrix = TraceabilityMatrix.build(req, [tc])
    assert matrix.coverage["AC-001"] == ["TC-001"]
    assert matrix.coverage["AC-002"] == []


@pytest.mark.unit
def test_build_multiple_tcs_can_cover_same_ac():
    req = make_requirement("AC-001")
    tcs = [make_test_case("TC-001", "AC-001"), make_test_case("TC-002", "AC-001")]
    matrix = TraceabilityMatrix.build(req, tcs)
    assert set(matrix.coverage["AC-001"]) == {"TC-001", "TC-002"}


@pytest.mark.unit
def test_build_one_tc_can_cover_multiple_acs():
    req = make_requirement("AC-001", "AC-002")
    tc = make_test_case("TC-001", "AC-001", "AC-002")
    matrix = TraceabilityMatrix.build(req, [tc])
    assert "TC-001" in matrix.coverage["AC-001"]
    assert "TC-001" in matrix.coverage["AC-002"]


@pytest.mark.unit
def test_build_unknown_ac_id_in_linked_criteria_is_ignored():
    req = make_requirement("AC-001")
    tc = make_test_case("TC-001", "AC-001", "AC-999")  # AC-999 does not exist
    matrix = TraceabilityMatrix.build(req, [tc])
    assert "AC-999" not in matrix.coverage
    assert matrix.coverage["AC-001"] == ["TC-001"]


# --- gaps ---

@pytest.mark.unit
def test_build_uncovered_ac_appears_in_gaps():
    req = make_requirement("AC-001", "AC-002")
    tc = make_test_case("TC-001", "AC-001")
    matrix = TraceabilityMatrix.build(req, [tc])
    assert len(matrix.gaps) == 1
    assert matrix.gaps[0].id == "AC-002"


@pytest.mark.unit
def test_build_no_gaps_when_all_acs_covered():
    req = make_requirement("AC-001", "AC-002")
    tcs = [make_test_case("TC-001", "AC-001"), make_test_case("TC-002", "AC-002")]
    matrix = TraceabilityMatrix.build(req, tcs)
    assert matrix.gaps == []


@pytest.mark.unit
def test_build_all_acs_are_gaps_when_no_test_cases():
    req = make_requirement("AC-001", "AC-002")
    matrix = TraceabilityMatrix.build(req, [])
    assert len(matrix.gaps) == 2


@pytest.mark.unit
def test_build_gaps_carry_full_ac_objects():
    req = make_requirement("AC-001")
    matrix = TraceabilityMatrix.build(req, [])
    assert matrix.gaps[0].id == "AC-001"
    assert matrix.gaps[0].text == "Criterion AC-001"


# --- coverage_pct ---

@pytest.mark.unit
def test_build_coverage_pct_is_100_when_all_covered():
    req = make_requirement("AC-001", "AC-002")
    tcs = [make_test_case("TC-001", "AC-001", "AC-002")]
    matrix = TraceabilityMatrix.build(req, tcs)
    assert matrix.coverage_pct == 100.0


@pytest.mark.unit
def test_build_coverage_pct_is_0_when_nothing_covered():
    req = make_requirement("AC-001", "AC-002")
    matrix = TraceabilityMatrix.build(req, [])
    assert matrix.coverage_pct == 0.0


@pytest.mark.unit
def test_build_coverage_pct_is_partial():
    req = make_requirement("AC-001", "AC-002", "AC-003", "AC-004")
    tc = make_test_case("TC-001", "AC-001", "AC-002")
    matrix = TraceabilityMatrix.build(req, [tc])
    assert matrix.coverage_pct == 50.0


@pytest.mark.unit
def test_build_coverage_pct_is_0_when_no_acs():
    req = make_requirement()  # edge case: empty AC list
    matrix = TraceabilityMatrix.build(req, [])
    assert matrix.coverage_pct == 0.0
