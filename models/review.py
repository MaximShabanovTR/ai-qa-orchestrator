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
    def _check_coverage_gaps(cls, matrix: TraceabilityMatrix) -> list[ReviewFinding]:
        return [
            ReviewFinding(
                category=FindingCategory.COVERAGE_GAP,
                severity=Severity.ERROR,
                message=f"Acceptance criterion '{ac.id}' is not covered by any test case.",
                criterion_ids=[ac.id],
                source="deterministic",
            )
            for ac in matrix.gaps
        ]

    @classmethod
    def _check_low_coverage(cls, matrix: TraceabilityMatrix, coverage_threshold: float) -> list[ReviewFinding]:
        if not matrix.gaps and matrix.coverage_pct < coverage_threshold:
            return [
                ReviewFinding(
                    category=FindingCategory.LOW_COVERAGE,
                    severity=Severity.WARNING,
                    message=f"Coverage is below threshold: {matrix.coverage_pct:.2f}% < {coverage_threshold:.2f}%",
                    source="deterministic",
                )
            ]
        return []

    @classmethod
    def _check_link_validity(cls, test_cases: list[TestCase], valid_ac_ids: set[str]) -> list[ReviewFinding]:
        findings = []
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
            elif len(invalid_ids) == len(tc.linked_criteria):
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.ORPHAN_TEST,
                        severity=Severity.WARNING,
                        message=f"Test case '{tc.id}' has no valid AC links — all referenced criteria do not exist: {', '.join(invalid_ids)}.",
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
                        message=f"Test case '{tc.id}' references non-existent criteria {', '.join(invalid_ids)} alongside valid ones.",
                        criterion_ids=invalid_ids,
                        test_case_ids=[tc.id],
                        source="deterministic",
                    )
                )
        return findings

    @classmethod
    def _check_malformed(cls, test_cases: list[TestCase]) -> list[ReviewFinding]:
        return [
            ReviewFinding(
                category=FindingCategory.MALFORMED_TEST,
                severity=Severity.ERROR,
                message=f"Test case '{tc.id}' is malformed: missing steps or expected outcome.",
                test_case_ids=[tc.id],
                source="deterministic",
            )
            for tc in test_cases
            if not tc.steps or not tc.expected_outcome
        ]

    @classmethod
    def _check_duplicate_titles(cls, test_cases: list[TestCase]) -> list[ReviewFinding]:
        findings = []
        seen: set[str] = set()
        for tc in test_cases:
            normalized = tc.title.strip().lower()
            if normalized in seen:
                findings.append(
                    ReviewFinding(
                        category=FindingCategory.DUPLICATE_TEST,
                        severity=Severity.WARNING,
                        message=f"Test case '{tc.id}' has a duplicate title '{tc.title}'.",
                        test_case_ids=[tc.id],
                        source="deterministic",
                    )
                )
            seen.add(normalized)
        return findings

    @classmethod
    def _check_missing_types(cls, test_cases: list[TestCase]) -> list[ReviewFinding]:
        if not test_cases:
            return []
        findings = []
        if not any(tc.type == TestCaseType.NEGATIVE for tc in test_cases):
            findings.append(ReviewFinding(
                category=FindingCategory.MISSING_TEST_TYPE,
                severity=Severity.WARNING,
                message="No negative test cases found.",
                source="deterministic",
            ))
        if not any(tc.type == TestCaseType.EDGE_CASE for tc in test_cases):
            findings.append(ReviewFinding(
                category=FindingCategory.MISSING_TEST_TYPE,
                severity=Severity.WARNING,
                message="No edge case test cases found.",
                source="deterministic",
            ))
        return findings

    @classmethod
    def build(
        cls,
        matrix: TraceabilityMatrix,
        requirement: StructuredRequirement,
        test_cases: list[TestCase],
        coverage_threshold: float,
    ) -> ReviewReport:
        valid_ac_ids = {ac.id for ac in requirement.acceptance_criteria}
        findings = [
            *cls._check_coverage_gaps(matrix),
            *cls._check_low_coverage(matrix, coverage_threshold),
            *cls._check_link_validity(test_cases, valid_ac_ids),
            *cls._check_malformed(test_cases),
            *cls._check_duplicate_titles(test_cases),
            *cls._check_missing_types(test_cases),
        ]
        return ReviewReport(findings=findings)
