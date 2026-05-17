from .base_agent import BaseAgent
from models import ClarificationRound, ClarificationQuestion
from orchestrator.session import Session


class ClarificationAgent(BaseAgent):
    prompt_file = "clarification.md"

    def run(self, session: Session) -> None:
        system = self._load_prompt(
            requirement_json=session.requirement.model_dump_json(indent=2),
            previous_qa=self._format_previous_qa(session),
        )
        raw_response = self._call(
            system=system,
            user_message="Identify gaps and return the JSON.",
        )
        data = self._parse_json(raw_response)
        round_ = ClarificationRound(
            questions=[ClarificationQuestion(**q) for q in data["questions"]],
        )
        session.clarification_rounds.append(round_)

    def _format_previous_qa(self, session: Session) -> str:
        answered = session.all_answered_questions
        if not answered:
            return "None"
        lines = []
        for q in answered:
            lines.append(f"Q ({q.id}) [{q.tier.value}]: {q.question}")
            lines.append(f"Context: {q.context}")
            lines.append(f"A: {q.answer}")
        return "\n".join(lines)
