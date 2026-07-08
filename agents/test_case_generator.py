import json
from pydantic import ValidationError
from .base_agent import BaseAgent
from .exceptions import AgentError
from models import TestCase
from orchestrator.session import Session


class TestCaseGenerator(BaseAgent):
    prompt_file = "test_case_generation.md"

    def run(self, session: Session) -> None:
        system = self._load_prompt(
            requirement_json=session.requirement.model_dump_json(indent=2),
            clarifications_json=self._format_clarifications(session),
            assumptions=self._format_assumptions(session),
            review_feedback=self._format_review_feedback(session),
        )
        raw_response = self._call(
            system=system,
            user_message="Generate the test cases and return the JSON array.",
            max_tokens=16000,
        )
        try:
            data = self._parse_json(raw_response)
            if not isinstance(data, list):
                raise AgentError("TestCaseGenerator: expected a JSON array, got something else")
            test_cases = [TestCase(**tc) for tc in data]
        except json.JSONDecodeError as e:
            raise AgentError(f"TestCaseGenerator: response was not valid JSON — {e}")
        except (KeyError, TypeError) as e:
            raise AgentError(f"TestCaseGenerator: unexpected response structure — {e}")
        except ValidationError as e:
            raise AgentError(f"TestCaseGenerator: response failed schema validation —\n{e}")
        session.test_cases = test_cases

    def _format_clarifications(self, session: Session) -> str:
        from models.clarification import QuestionTier
        answered = [
            q for q in session.all_answered_questions
            if q.tier in (QuestionTier.BLOCKING, QuestionTier.CLARIFYING)
        ]
        if not answered:
            return "None"
        lines = []
        for q in answered:
            lines.append(f"Q: {q.question}")
            lines.append(f"A: {q.answer}")
        return "\n".join(lines)

    def _format_assumptions(self, session: Session) -> str:
        assumptions = session.assumptions_made
        if not assumptions:
            return "None"
        return "\n".join(f"- {a}" for a in assumptions)

    def _format_review_feedback(self, session: Session) -> str:
        review_feedback = session.review_report
        if not review_feedback or review_feedback.error_count == 0:
            return ""
        lines = ["PREVIOUS REVIEW - ERROR AND WARNING FINDINGS:\n"]
        for finding in review_feedback.findings:
            lines.append(f"- Category: {finding.category.value}")
            lines.append(f"  Severity: {finding.severity.value}")
            lines.append(f"  Message: {finding.message}")
            if finding.criterion_ids:
                lines.append(f"  Linked Criteria IDs: {', '.join(finding.criterion_ids)}")
            if finding.test_case_ids:
                lines.append(f"  Linked Test Case IDs: {', '.join(finding.test_case_ids)}")
            lines.append("")  # Add a blank line between findings
        return "\n".join(lines)
