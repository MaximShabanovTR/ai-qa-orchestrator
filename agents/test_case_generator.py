from .base_agent import BaseAgent
from orchestrator.session import Session


class TestCaseGenerator(BaseAgent):
    prompt_file = "test_case_generation.md"

    def run(self, session: Session) -> None:
        raise NotImplementedError
