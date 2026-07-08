import pytest
from models.requirement import AcceptanceCriterion as AC
from models.review import ReviewReport, FindingCategory, Severity
from models.test_case import TestCase, TestCaseType, Priority, TestStep
from models.traceability import TraceabilityMatrix


def make_matrix(gaps: list[AC] = None, coverage_pct: float = 100.0) -> TraceabilityMatrix:
    gaps = gaps or []
    coverage = {ac.id: [] for ac in gaps}
    return TraceabilityMatrix(coverage=coverage, gaps=gaps, coverage_pct=coverage_pct)


def make_ac(ac_id: str) -> AC:
    return AC(id=ac_id, text=f"Criterion {ac_id}")


def make_test_case(
    tc_id: str,
    *linked: str,
    title: str = None,
    type_: TestCaseType = TestCaseType.HAPPY_PATH,
    steps: list[TestStep] = None,
    expected_outcome: str = "Done.",
) -> TestCase:
    return TestCase(
        id=tc_id,
        title=title or f"Test {tc_id}",
        type=type_,
        priority=Priority.MEDIUM,
        preconditions=[],
        steps=steps if steps is not None else [TestStep(step_number=1, action="Do it", expected_result="It happened")],
        expected_outcome=expected_outcome,
        linked_criteria=list(linked),
    )


# --- _check_coverage_gaps ---

@pytest.mark.unit
def test_check_coverage_gaps_returns_error_per_uncovered_ac():
    matrix = make_matrix(gaps=[make_ac("AC-001"), make_ac("AC-002")])
    findings = ReviewReport._check_coverage_gaps(matrix)
    assert len(findings) == 2
    assert all(f.category == FindingCategory.COVERAGE_GAP for f in findings)
    assert all(f.severity == Severity.ERROR for f in findings)


@pytest.mark.unit
def test_check_coverage_gaps_empty_when_all_covered():
    matrix = make_matrix(gaps=[], coverage_pct=100.0)
    assert ReviewReport._check_coverage_gaps(matrix) == []


@pytest.mark.unit
def test_check_coverage_gaps_finding_references_ac_id():
    matrix = make_matrix(gaps=[make_ac("AC-003")])
    finding = ReviewReport._check_coverage_gaps(matrix)[0]
    assert "AC-003" in finding.criterion_ids


# --- _check_low_coverage ---

@pytest.mark.unit
def test_check_low_coverage_returns_warning_when_below_threshold():
    matrix = make_matrix(gaps=[], coverage_pct=80.0)
    findings = ReviewReport._check_low_coverage(matrix, coverage_threshold=90.0)
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.LOW_COVERAGE
    assert findings[0].severity == Severity.WARNING


@pytest.mark.unit
def test_check_low_coverage_empty_when_at_threshold():
    matrix = make_matrix(gaps=[], coverage_pct=90.0)
    assert ReviewReport._check_low_coverage(matrix, coverage_threshold=90.0) == []


@pytest.mark.unit
def test_check_low_coverage_skipped_when_gaps_exist():
    matrix = make_matrix(gaps=[make_ac("AC-001")], coverage_pct=50.0)
    assert ReviewReport._check_low_coverage(matrix, coverage_threshold=90.0) == []


# --- _check_link_validity ---

@pytest.mark.unit
def test_check_link_validity_empty():
    tc = make_test_case("TC-001")
    findings = ReviewReport._check_link_validity([tc], valid_ac_ids={"AC-001", "AC-002"})
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.ORPHAN_TEST


@pytest.mark.unit
def test_check_link_validity_all_invalid():
    tc = make_test_case("TC-001", "AC-001", "AC-002")
    findings = ReviewReport._check_link_validity([tc], valid_ac_ids={"AC-003", "AC-004"})
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.ORPHAN_TEST
    assert set(findings[0].criterion_ids) == {"AC-001", "AC-002"}


@pytest.mark.unit
def test_link_validity_some_invalid():
    tc = make_test_case("TC-001", "AC-001", "AC-002")
    findings = ReviewReport._check_link_validity([tc], valid_ac_ids={"AC-002", "AC-003"})
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.HALLUCINATED_LINK
    assert set(findings[0].criterion_ids) == {"AC-001"}


# --- _check_malformed ---

@pytest.mark.unit
def test_check_malformed_returns_error_when_no_steps():
    tc = make_test_case("TC-001", "AC-001", steps=[])
    findings = ReviewReport._check_malformed([tc])
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.MALFORMED_TEST
    assert findings[0].severity == Severity.ERROR


@pytest.mark.unit
def test_check_malformed_returns_error_when_no_expected_outcome():
    tc = make_test_case("TC-001", "AC-001", expected_outcome="")
    findings = ReviewReport._check_malformed([tc])
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.MALFORMED_TEST


@pytest.mark.unit
def test_check_malformed_empty_when_well_formed():
    tc = make_test_case("TC-001", "AC-001")
    assert ReviewReport._check_malformed([tc]) == []


# --- _check_duplicate_titles ---

@pytest.mark.unit
def test_check_duplicate_titles_returns_warning_for_duplicate():
    tc1 = make_test_case("TC-001", "AC-001", title="Login succeeds")
    tc2 = make_test_case("TC-002", "AC-001", title="Login succeeds")
    findings = ReviewReport._check_duplicate_titles([tc1, tc2])
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.DUPLICATE_TEST
    assert findings[0].severity == Severity.WARNING


@pytest.mark.unit
def test_check_duplicate_titles_empty_when_all_unique():
    tc1 = make_test_case("TC-001", title="Happy path")
    tc2 = make_test_case("TC-002", title="Edge case")
    assert ReviewReport._check_duplicate_titles([tc1, tc2]) == []


# --- _check_missing_types ---

@pytest.mark.unit
def test_check_missing_types_warns_when_no_negative_tests():
    tcs = [
        make_test_case("TC-001", type_=TestCaseType.HAPPY_PATH),
        make_test_case("TC-002", type_=TestCaseType.EDGE_CASE),
    ]
    findings = ReviewReport._check_missing_types(tcs)
    categories = [f.category for f in findings]
    assert FindingCategory.MISSING_TEST_TYPE in categories


@pytest.mark.unit
def test_check_missing_types_warns_when_no_edge_case_tests():
    tcs = [
        make_test_case("TC-001", type_=TestCaseType.HAPPY_PATH),
        make_test_case("TC-002", type_=TestCaseType.NEGATIVE),
    ]
    findings = ReviewReport._check_missing_types(tcs)
    categories = [f.category for f in findings]
    assert FindingCategory.MISSING_TEST_TYPE in categories


@pytest.mark.unit
def test_check_missing_types_empty_when_all_types_present():
    tcs = [
        make_test_case("TC-001", type_=TestCaseType.HAPPY_PATH),
        make_test_case("TC-002", type_=TestCaseType.EDGE_CASE),
        make_test_case("TC-003", type_=TestCaseType.NEGATIVE),
    ]
    assert ReviewReport._check_missing_types(tcs) == []


@pytest.mark.unit
def test_check_missing_types_skipped_on_empty_suite():
    assert ReviewReport._check_missing_types([]) == []
