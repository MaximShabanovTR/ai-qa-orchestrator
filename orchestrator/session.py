from dataclasses import dataclass, field
from models import StructuredRequirement, ClarificationRound, TestCase, TraceabilityMatrix
from models.clarification import ClarificationQuestion, QuestionTier


@dataclass
class Session:
    raw_input: str
    requirement: StructuredRequirement | None = None
    clarification_rounds: list[ClarificationRound] = field(default_factory=list)
    test_cases: list[TestCase] = field(default_factory=list)
    traceability_matrix: TraceabilityMatrix | None = None

    @property
    def latest_round(self) -> ClarificationRound | None:
        return self.clarification_rounds[-1] if self.clarification_rounds else None

    @property
    def all_answered_questions(self) -> list[ClarificationQuestion]:
        return [q for r in self.clarification_rounds for q in r.questions if q.answer]

    @property
    def assumptions_made(self) -> list[str]:
        return [
            q.assumption
            for r in self.clarification_rounds
            for q in r.questions
            if q.tier == QuestionTier.ASSUMABLE and q.assumption
        ]
