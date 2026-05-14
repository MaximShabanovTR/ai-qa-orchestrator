import json
from .base_agent import BaseAgent
from models import TestCase
from orchestrator.session import Session


class TestCaseGenerator(BaseAgent):
    prompt_file = "test_case_generation.md"

    def run(self, session: Session) -> None:
        system = self._load_prompt(
            requirement_json=session.requirement.model_dump_json(indent=2),
            clarifications_json=self._format_clarifications(session),
        )
        raw_response = self._call(
            system=system,
            user_message="Generate the test cases and return the JSON array.",
        )
        data = json.loads(raw_response)
        session.test_cases = [TestCase(**tc) for tc in data]

    def _format_clarifications(self, session: Session) -> str:
        answered = session.all_answered_questions
        if not answered:
            return "No clarifications were needed."
        lines = []
        for q in answered:
            lines.append(f"Q: {q.question}")
            lines.append(f"A: {q.answer}")
        return "\n".join(lines)
