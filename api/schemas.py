from enum import Enum
from pydantic import BaseModel


class SessionStatus(str, Enum):
    ANALYZED = "analyzed"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    READY_TO_GENERATE = "ready_to_generate"
    COMPLETE = "complete"
    FAILED = "failed"


# --- requests ---

class CreateSessionRequest(BaseModel):
    requirement: str


class SubmitAnswersRequest(BaseModel):
    answers: dict[str, str] = {}  # question id → answer text


# --- response building blocks ---

class AcceptanceCriterionOut(BaseModel):
    id: str
    text: str


class TestScopeOut(BaseModel):
    in_scope: list[str]
    out_of_scope: list[str]


class RequirementOut(BaseModel):
    title: str
    description: str
    actors: list[str]
    acceptance_criteria: list[AcceptanceCriterionOut]
    test_scope: TestScopeOut


class QuestionOut(BaseModel):
    id: str
    question: str
    context: str
    tier: str
    assumption: str | None


class TestStepOut(BaseModel):
    step_number: int
    action: str
    expected_result: str

class ReviewFindingOut(BaseModel):
    category: str
    severity: str
    message: str
    criterion_ids: list[str]
    test_case_ids: list[str]
    source: str

class TestCaseOut(BaseModel):
    id: str
    title: str
    type: str
    priority: str
    preconditions: list[str]
    steps: list[TestStepOut]
    expected_outcome: str
    tags: list[str]
    linked_criteria: list[str]


class TraceabilityOut(BaseModel):
    coverage: dict[str, list[str]]
    gaps: list[AcceptanceCriterionOut]
    coverage_pct: float

class ReviewReportOut(BaseModel):
    findings: list[ReviewFindingOut]
    error_count: int
    passed: bool

# --- endpoint responses ---

class SessionResponse(BaseModel):
    session_id: str
    status: SessionStatus
    requirement: RequirementOut | None = None        # present when AWAITING_CLARIFICATION, COMPLETE
    questions: list[QuestionOut] | None = None       # present when AWAITING_CLARIFICATION
    test_cases: list[TestCaseOut] | None = None      # present when COMPLETE
    traceability: TraceabilityOut | None = None      # present when COMPLETE
    review_report: ReviewReportOut | None = None     # present when COMPLETE
    review_rounds: int | None = None                 # number of regeneration retries triggered
