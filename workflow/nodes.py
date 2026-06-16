import copy

from agents.clarification_agent import ClarificationAgent
from agents.requirements_analyst import RequirementsAnalyst
from agents.test_case_generator import TestCaseGenerator
from models.clarification import QuestionTier
from models.traceability import TraceabilityMatrix
from orchestrator.session import Session
from config import MAX_CLARIFICATION_ROUNDS, SCORE_THRESHOLD
from workflow.state import QAState
from langgraph.types import interrupt

# Agents are stateless — safe to share as module-level singletons.
_analyst = RequirementsAnalyst()
_generator = TestCaseGenerator()
_clarifier = ClarificationAgent()


def _resolve_assumptions(round_) -> None:
    for q in round_.questions:
        if q.tier == QuestionTier.ASSUMABLE and q.assumption:
            q.answer = q.assumption


def analyze(state: QAState) -> dict:
    session = Session(raw_input=state["raw_input"])
    _analyst.run(session)
    return {"requirement": session.requirement}


def collect_answers(state: QAState) -> dict:
    answers = interrupt({"questions": state["clarification_rounds"][-1].questions})
    return {"pending_answers": answers}


def clarify(state: QAState) -> dict:
    session = Session(
        raw_input=state["raw_input"],
        requirement=state["requirement"],
        clarification_rounds=copy.deepcopy(list(state["clarification_rounds"])),
    )
    if session.clarification_rounds:
        for q in session.clarification_rounds[-1].questions:
            if q.id in state["pending_answers"]:
                q.answer = state["pending_answers"][q.id]
    _clarifier.run(session)
    _resolve_assumptions(session.clarification_rounds[-1])

    return {
        "clarification_rounds": [
            session.clarification_rounds[-1]
        ],  # returns only the new round, to be appended to existing list
        "clarification_complete": not session.latest_round.questions
        or (
            session.latest_round.blocking_count == 0
            and session.latest_round.completeness_score >= SCORE_THRESHOLD
        )
        or len(session.clarification_rounds) >= MAX_CLARIFICATION_ROUNDS,
        "pending_answers": {},
    }


def generate(state: QAState) -> dict:
    session = Session(
        raw_input=state["raw_input"],
        requirement=state["requirement"],
        clarification_rounds=copy.deepcopy(list(state["clarification_rounds"])),
    )
    _generator.run(session)

    traceability = None
    if session.requirement:
        traceability = TraceabilityMatrix.build(session.requirement, session.test_cases)

    return {
        "test_cases": session.test_cases,
        "traceability_matrix": traceability,
    }
