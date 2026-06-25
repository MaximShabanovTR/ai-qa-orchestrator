from config import COVERAGE_WARN_THRESHOLD
from models.review import ReviewReport
from orchestrator.session import Session


class ReviewAgent:

    def run(self, session: Session) -> None:
        session.review_report = ReviewReport.build(
            matrix=session.traceability_matrix,
            requirement=session.requirement,
            test_cases=session.test_cases,
            coverage_threshold=COVERAGE_WARN_THRESHOLD,
        )
