from pydantic import BaseModel


class ClarificationQuestion(BaseModel):
    id: str
    question: str
    context: str
    answer: str | None = None


class ClarificationRound(BaseModel):
    questions: list[ClarificationQuestion]
    is_sufficient: bool = False
