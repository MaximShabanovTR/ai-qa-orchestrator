from __future__ import annotations
from pydantic import BaseModel
from models.requirement import AcceptanceCriterion, StructuredRequirement
from models.test_case import TestCase


class TraceabilityMatrix(BaseModel):
    # AC ID → list of TC IDs that cover it
    coverage: dict[str, list[str]]
    # full objects for ACs with zero coverage — carry the text for readable output
    gaps: list[AcceptanceCriterion]
    # percentage of ACs covered by at least one test case
    coverage_pct: float

    @classmethod
    def build(
        cls,
        requirement: StructuredRequirement,
        test_cases: list[TestCase],
    ) -> TraceabilityMatrix:
        coverage: dict[str, list[str]] = {
            ac.id: [] for ac in requirement.acceptance_criteria
        }
        for tc in test_cases:
            for ac_id in tc.linked_criteria:
                if ac_id in coverage:
                    coverage[ac_id].append(tc.id)

        gaps = [
            ac for ac in requirement.acceptance_criteria
            if not coverage[ac.id]
        ]
        total = len(requirement.acceptance_criteria)
        covered = total - len(gaps)
        coverage_pct = round(covered / total * 100, 1) if total > 0 else 0.0

        return cls(coverage=coverage, gaps=gaps, coverage_pct=coverage_pct)
