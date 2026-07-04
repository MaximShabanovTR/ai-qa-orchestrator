import json

from pydantic import ValidationError

from agents.base_agent import BaseAgent
from agents.exceptions import AgentError
from config import COVERAGE_WARN_THRESHOLD
from models.review import ReviewFinding, ReviewReport
from orchestrator.session import Session


class ReviewAgent(BaseAgent):
    prompt_file = "review.md"

    def run(self, session: Session) -> None:
        session.review_report = ReviewReport.build(
            matrix=session.traceability_matrix,
            requirement=session.requirement,
            test_cases=session.test_cases,
            coverage_threshold=COVERAGE_WARN_THRESHOLD,
        )
        system = self._load_prompt(
            requirement_json=session.requirement.model_dump_json(indent=2),
            clarifications_json=json.dumps([clarification.model_dump() for clarification in session.all_answered_questions], indent=2),
            assumptions=json.dumps(session.assumptions_made, indent=2),
            test_cases_json=json.dumps([test_case.model_dump() for test_case in session.test_cases], indent=2),
        )
        raw_response = self._call(
            system=system,
            user_message="Identify gaps and return the JSON.",
            max_tokens=8192,
        )
        try:
            data = self._parse_json(raw_response)
            session.review_report.findings.extend(ReviewFinding.model_validate(item) for item in data)
        except json.JSONDecodeError as e:
            raise AgentError(f"ReviewAgent: response was not valid JSON — {e}")
        except (KeyError, TypeError) as e:
            raise AgentError(f"ReviewAgent: unexpected response structure — {e}")
        except ValidationError as e:
            raise AgentError(f"ReviewAgent: response failed schema validation —\n{e}")
