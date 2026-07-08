import pytest
from models.planning import PlannerDecision, RemediationAction
from models.review import ReviewReport, ReviewFinding, FindingCategory, Severity


def make_error_finding() -> ReviewFinding:
    return ReviewFinding(
        category=FindingCategory.COVERAGE_GAP,
        severity=Severity.ERROR,
        message="AC-001 has no coverage.",
        criterion_ids=["AC-001"],
        test_case_ids=[],
        source="deterministic",
    )


def make_warning_finding() -> ReviewFinding:
    return ReviewFinding(
        category=FindingCategory.DUPLICATE_TEST,
        severity=Severity.WARNING,
        message="Duplicate title.",
        criterion_ids=[],
        test_case_ids=["TC-001"],
        source="deterministic",
    )


# --- from_report: DONE branches ---

@pytest.mark.unit
def test_from_report_returns_done_when_report_is_none():
    decision = PlannerDecision.from_report(None, review_rounds=0, max_rounds=2)
    assert decision.action == RemediationAction.DONE
    assert decision.reason == "review_unavailable"


@pytest.mark.unit
def test_from_report_returns_done_when_report_passed():
    report = ReviewReport(findings=[make_warning_finding()])
    decision = PlannerDecision.from_report(report, review_rounds=0, max_rounds=2)
    assert decision.action == RemediationAction.DONE
    assert decision.reason == "passed"


@pytest.mark.unit
def test_from_report_returns_done_when_max_rounds_reached():
    report = ReviewReport(findings=[make_error_finding()])
    decision = PlannerDecision.from_report(report, review_rounds=2, max_rounds=2)
    assert decision.action == RemediationAction.DONE
    assert decision.reason == "max_rounds_reached"


# --- from_report: REGENERATE_ALL branch ---

@pytest.mark.unit
def test_from_report_returns_regenerate_when_errors_remain():
    report = ReviewReport(findings=[make_error_finding()])
    decision = PlannerDecision.from_report(report, review_rounds=0, max_rounds=2)
    assert decision.action == RemediationAction.REGENERATE_ALL


@pytest.mark.unit
def test_from_report_reason_is_first_error_category():
    report = ReviewReport(findings=[make_error_finding()])
    decision = PlannerDecision.from_report(report, review_rounds=0, max_rounds=2)
    assert decision.reason == FindingCategory.COVERAGE_GAP.value


@pytest.mark.unit
def test_from_report_max_rounds_check_uses_current_rounds_not_incremented():
    report = ReviewReport(findings=[make_error_finding()])
    decision = PlannerDecision.from_report(report, review_rounds=1, max_rounds=2)
    assert decision.action == RemediationAction.REGENERATE_ALL


@pytest.mark.unit
def test_from_report_none_check_takes_priority_over_rounds():
    decision = PlannerDecision.from_report(None, review_rounds=99, max_rounds=2)
    assert decision.action == RemediationAction.DONE
    assert decision.reason == "review_unavailable"
