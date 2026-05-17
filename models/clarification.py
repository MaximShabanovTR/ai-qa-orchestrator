from enum import Enum
from pydantic import BaseModel


class QuestionTier(str, Enum):
    BLOCKING = "blocking"
    CLARIFYING = "clarifying"
    ASSUMABLE = "assumable"


class ClarificationQuestion(BaseModel):
    id: str
    question: str
    context: str
    tier: QuestionTier
    assumption: str | None = None
    answer: str | None = None


class ClarificationRound(BaseModel):
    questions: list[ClarificationQuestion]

    @property
    def blocking_count(self) -> int:
        return sum(1 for q in self.questions if q.tier == QuestionTier.BLOCKING)

    @property
    def clarifying_count(self) -> int:
        return sum(1 for q in self.questions if q.tier == QuestionTier.CLARIFYING)

    @property
    def assumable_count(self) -> int:
        return sum(1 for q in self.questions if q.tier == QuestionTier.ASSUMABLE)

    @property
    def completeness_score(self) -> float:
        blocking_penalty = min(self.blocking_count * 0.30, 0.60)
        clarifying_penalty = min(self.clarifying_count * 0.10, 0.30)
        return round(1.0 - blocking_penalty - clarifying_penalty, 2)
