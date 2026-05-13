from dataclasses import dataclass, field
from models import StructuredRequirement, ClarificationRound, TestCase


@dataclass
class Session:
    raw_input: str
    requirement: StructuredRequirement | None = None
    clarification_rounds: list[ClarificationRound] = field(default_factory=list)
    test_cases: list[TestCase] = field(default_factory=list)

    @property
    def is_clarified(self) -> bool:
        return any(r.is_sufficient for r in self.clarification_rounds)

    @property
    def all_answered_questions(self) -> list:
        return [q for r in self.clarification_rounds for q in r.questions if q.answer]
