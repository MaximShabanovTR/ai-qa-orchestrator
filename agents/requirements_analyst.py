from .base_agent import BaseAgent
from orchestrator.session import Session


class RequirementsAnalyst(BaseAgent):
    prompt_file = "requirements_analysis.md"

    def run(self, session: Session) -> None:
        raise NotImplementedError
