import json
from .base_agent import BaseAgent
from models import StructuredRequirement
from orchestrator.session import Session


class RequirementsAnalyst(BaseAgent):
    prompt_file = "requirements_analysis.md"

    def run(self, session: Session) -> None:
        system = self._load_prompt(raw_input=session.raw_input)
        raw_response = self._call(
            system=system,
            user_message="Analyze the requirement and return the JSON.",
        )
        data = json.loads(raw_response)
        data["raw_input"] = session.raw_input
        session.requirement = StructuredRequirement(**data)
