import json
import re
from abc import ABC, abstractmethod
from config import PROMPTS_DIR
from orchestrator.session import Session
from services.claude_client import chat


class BaseAgent(ABC):
    prompt_file: str

    def _load_prompt(self, **kwargs: str) -> str:
        path = PROMPTS_DIR / self.prompt_file
        template = path.read_text(encoding="utf-8")
        return template.format(**kwargs) if kwargs else template

    def _call(self, system: str, user_message: str) -> str:
        return chat(
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )

    def _parse_json(self, text: str):
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text.strip())

    @abstractmethod
    def run(self, session: Session) -> None:
        ...
