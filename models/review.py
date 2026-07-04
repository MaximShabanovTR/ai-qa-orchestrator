from enum import Enum
from typing import Literal

from pydantic import BaseModel, computed_field

from models.requirement import StructuredRequirement
from models.test_case import TestCase, TestCaseType
from models.traceability import TraceabilityMatrix


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class FindingCategory(str, Enum):
    COVERAGE_GAP = "coverage_gap"
    LOW_COVERAGE = "low_coverage"
    ORPHAN_TEST = "orphan_test"
    HALLUCINATED_LINK = "hallucinated_link"
    MISSING_TEST_TYPE = "missing_test_type"
    DUPLICATE_TEST = "duplicate_test"
    MALFORMED_TEST = "malformed_test"
    WEAK_STEP = "weak_step"
    MISLINKED = "mislinked"
    SEMANTIC_GAP = "semantic_gap"
    SEMANTIC_DUPLICATE = "semantic_duplicate"


class ReviewFinding(BaseModel):
    category: FindingCategory
    severity: Severity
    message: str
    criterion_ids: list[str] = []
    test_case_ids: list[str] = []
    source: Literal["deterministic", "llm"]


class ReviewReport(BaseModel):
    findings: list[ReviewFinding]

    @computed_field
    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.ERROR)

    @computed_field
    @property
    def passed(self) -> bool:
        return self.error_count == 0

    @classmethod
    def build(
        cls,
        matrix: TraceabilityMatrix,
        requirement: StructuredRequirement,
        test_cases: list[TestCase],
        coverage_threshold: float,
    ) -> ReviewReport:
        findings: list[ReviewFinding] = []
        seen_titles: set[str] = set()
        if matrix.gaps:
            findings.extend( 
                ReviewFinding(
                    category=FindingCategory.COVERAGE_GAP,
                    severity=Severity.ERROR,
                    message=f"Acceptance criterion '{ac.id}' is not covered by any test case.",
                    criterion_ids=[ac.id],
                    source="deterministic",
                )
                for ac in matrix.gaps
            )
        if not matrix.gaps and matrix.coverage_pct < coverage_threshold:
            findings.append(
                ReviewFinding(
                    category=FindingCategory.LOW_COVERAGE,
                    severity=Severity.WARNING,
                    message=f"Coverage is below threshold: {matrix.coverage_pct:.2f}% < {coverage_threshold:.2f}%",
                    source="deterministic",
                )
            )
        valid_ac_ids = {ac.id for ac in requirement.acceptance_criteria}
        for tc in test_cases:
            invalid_ids = [ac_id for ac_id in tc.linked_criteria if ac_id not in valid_ac_ids]
            if not tc.linked_criteria:
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.ORPHAN_TEST,
                        severity=Severity.WARNING,
                        message=f"Test case '{tc.id}' is not linked to any acceptance criterion.",
                        test_case_ids=[tc.id],
                        source="deterministic",
                    )
                )
            elif all(ac_id not in valid_ac_ids for ac_id in tc.linked_criteria):
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.ORPHAN_TEST,
                        severity=Severity.WARNING,
                        message=f"Test case '{tc.id}' is linked to non-existent acceptance criterion {', '.join(invalid_ids)}.",
                        criterion_ids=invalid_ids,
                        test_case_ids=[tc.id],
                        source="deterministic",
                    )
                )
            elif invalid_ids:
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.HALLUCINATED_LINK,
                        severity=Severity.WARNING,
                        message=f"Test case '{tc.id}' is linked to non-existent acceptance criterion {', '.join(invalid_ids)}.",
                        criterion_ids=invalid_ids,
                        test_case_ids=[tc.id],
                        source="deterministic",
                    )
                )
            if not tc.steps or not tc.expected_outcome:
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.MALFORMED_TEST,
                        severity=Severity.ERROR,
                        message=f"Test case '{tc.id}' is malformed: missing steps or expected outcome.",
                        test_case_ids=[tc.id],
                        source="deterministic",
                    )
                )
            if tc.title.strip().lower() in seen_titles:
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.DUPLICATE_TEST,
                        severity=Severity.WARNING,
                        message=f"Test case '{tc.id}' has a duplicate title '{tc.title}'.",
                        test_case_ids=[tc.id],
                        source="deterministic",
                    )
                )
            seen_titles.add(tc.title.strip().lower())
        if test_cases:
            if not any(tc.type == TestCaseType.NEGATIVE for tc in test_cases):
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.MISSING_TEST_TYPE,
                        severity=Severity.WARNING,
                        message="No negative test cases found.",
                        source="deterministic",
                    )
                )
            if not any(tc.type == TestCaseType.EDGE_CASE for tc in test_cases):
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.MISSING_TEST_TYPE,
                        severity=Severity.WARNING,
                        message="No edge case test cases found.",
                        source="deterministic",
                    )
                )
        return ReviewReport(findings=findings)
