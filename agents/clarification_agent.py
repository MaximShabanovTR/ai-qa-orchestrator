import json
from pydantic import ValidationError
from .base_agent import BaseAgent
from .exceptions import AgentError
from models import ClarificationRound, ClarificationQuestion
from orchestrator.session import Session


class ClarificationAgent(BaseAgent):
    prompt_file = "clarification.md"

    def run(self, session: Session) -> None:
        asked_so_far = sum(len(r.questions) for r in session.clarification_rounds)
        system = self._load_prompt(
            requirement_json=session.requirement.model_dump_json(indent=2),
            previous_qa=self._format_previous_qa(session),
            start_id=asked_so_far + 1,
        )
        raw_response = self._call(
            system=system,
            user_message="Identify gaps and return the JSON.",
        )
        try:
            data = self._parse_json(raw_response)
            questions_raw = data.get("questions") or []
            round_ = ClarificationRound(
                questions=[ClarificationQuestion(**q) for q in questions_raw],
            )
        except json.JSONDecodeError as e:
            raise AgentError(f"ClarificationAgent: response was not valid JSON — {e}")
        except (KeyError, TypeError) as e:
            raise AgentError(f"ClarificationAgent: unexpected response structure — {e}")
        except ValidationError as e:
            raise AgentError(f"ClarificationAgent: response failed schema validation —\n{e}")
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
