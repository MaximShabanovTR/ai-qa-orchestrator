from .base_agent import BaseAgent
from orchestrator.session import Session


class ClarificationAgent(BaseAgent):
    prompt_file = "clarification.md"

    def run(self, session: Session) -> None:
        raise NotImplementedError
