import operator
from typing import Annotated, TypedDict

from models.clarification import ClarificationRound
from models.requirement import StructuredRequirement
from models.test_case import TestCase
from models.traceability import TraceabilityMatrix


class QAState(TypedDict):
    raw_input: str
    requirement: StructuredRequirement | None
    clarification_rounds: Annotated[list[ClarificationRound], operator.add]
    clarification_complete: bool
    pending_answers: dict[str, str]   # question id → answer text, set by the interrupt
    test_cases: list[TestCase]
    traceability_matrix: TraceabilityMatrix | None
