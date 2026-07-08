from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from models.review import ReviewReport, Severity


class RemediationAction(str, Enum):
    DONE = "done"
    REGENERATE_ALL = "regenerate_all"


class PlannerDecision(BaseModel):
    action: RemediationAction
    reason: str

    @classmethod
    def from_report(
        cls,
        report: ReviewReport | None,
        review_rounds: int,
        max_rounds: int,
    ) -> PlannerDecision:
        if report is None:
            return cls(action=RemediationAction.DONE, reason="review_unavailable")
        if report.passed:
            return cls(action=RemediationAction.DONE, reason="passed")
        if review_rounds >= max_rounds:
            return cls(action=RemediationAction.DONE, reason="max_rounds_reached")
        
        first_error = next(f for f in report.findings if f.severity == Severity.ERROR)
        return cls(action=RemediationAction.REGENERATE_ALL, reason=first_error.category.value)
