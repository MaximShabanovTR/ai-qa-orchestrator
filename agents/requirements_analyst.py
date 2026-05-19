import json
from pydantic import ValidationError
from .base_agent import BaseAgent
from .exceptions import AgentError
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
        try:
            data = self._parse_json(raw_response)
            data["raw_input"] = session.raw_input
            requirement = StructuredRequirement(**data)
        except json.JSONDecodeError as e:
            raise AgentError(f"RequirementsAnalyst: response was not valid JSON — {e}")
        except (KeyError, TypeError) as e:
            raise AgentError(f"RequirementsAnalyst: unexpected response structure — {e}")
        except ValidationError as e:
            raise AgentError(f"RequirementsAnalyst: response failed schema validation —\n{e}")
        session.requirement = requirement
