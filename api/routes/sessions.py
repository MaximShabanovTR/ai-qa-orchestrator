from fastapi import APIRouter, HTTPException, Request
from langgraph.types import Command
from agents.exceptions import AgentError
from models.clarification import QuestionTier
from api.schemas import (
    AcceptanceCriterionOut,
    CreateSessionRequest,
    QuestionOut,
    RequirementOut,
    ReviewFindingOut,
    ReviewReportOut,
    SessionResponse,
    SessionStatus,
    SubmitAnswersRequest,
    TestScopeOut,
    TestCaseOut,
    TestStepOut,
    TraceabilityOut,
)

router = APIRouter()


# --- helpers ---


def _require_session(request: Request, session_id: str):
    session = request.app.state.store.exists(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    

def _session_complete_check(request: Request, config: dict):
    state = request.app.state.graph.get_state(config)
    if state.values.get("clarification_complete"):
        raise HTTPException(status_code=409, detail="Session is already complete")


def _requirement_out(req) -> RequirementOut:
    return RequirementOut(
        title=req.title,
        description=req.description,
        actors=req.actors,
        acceptance_criteria=[
            AcceptanceCriterionOut(id=ac.id, text=ac.text)
            for ac in req.acceptance_criteria
        ],
        test_scope=TestScopeOut(
            in_scope=req.test_scope.in_scope,
            out_of_scope=req.test_scope.out_of_scope,
        ),
    )


def _question_out(questions: list) -> list[QuestionOut]:
    questions_for_user = [
        QuestionOut(
            id=q.id,
            question=q.question,
            context=q.context,
            tier=q.tier.value,
            assumption=q.assumption,
        )
        for q in questions
        if q.tier in (QuestionTier.BLOCKING, QuestionTier.CLARIFYING)
    ]
    return questions_for_user


def _test_cases_out(test_cases: list) -> list[TestCaseOut]:
    return [
        TestCaseOut(
            id=tc.id,
            title=tc.title,
            type=tc.type.value,
            priority=tc.priority.value,
            preconditions=tc.preconditions,
            steps=[
                TestStepOut(
                    step_number=s.step_number,
                    action=s.action,
                    expected_result=s.expected_result,
                )
                for s in tc.steps
            ],
            expected_outcome=tc.expected_outcome,
            tags=tc.tags,
            linked_criteria=tc.linked_criteria,
        )
        for tc in test_cases
    ]


def _traceability_out(traceability_matrix) -> TraceabilityOut:
    return TraceabilityOut(
        coverage=traceability_matrix.coverage,
        gaps=[
            AcceptanceCriterionOut(id=ac.id, text=ac.text)
            for ac in traceability_matrix.gaps
        ],
        coverage_pct=traceability_matrix.coverage_pct,
    )

def _review_out(review_report) -> ReviewReportOut:
    return ReviewReportOut(
        findings=[
            ReviewFindingOut(
                category=f.category.value,
                severity=f.severity.value,
                message=f.message,
                criterion_ids=f.criterion_ids,
                test_case_ids=f.test_case_ids,
                source=f.source,
            )
            for f in review_report.findings
        ],
        error_count=review_report.error_count,
        passed=review_report.passed,
    )



def _build_response(session_id: str, state) -> SessionResponse:
    req = state.values.get("requirement")
    if not state.values.get("clarification_complete", True):
        return SessionResponse(
            session_id=session_id,
            status=SessionStatus.AWAITING_CLARIFICATION,   
            requirement=_requirement_out(req) if req else None,
            questions=_question_out(state.values["clarification_rounds"][-1].questions) if state.values.get("clarification_rounds") else [],
        )
    else:
        return SessionResponse(
            session_id=session_id,
            status=SessionStatus.COMPLETE,
            requirement=_requirement_out(req) if req else None,
            test_cases=_test_cases_out(state.values.get("test_cases", [])),
            traceability=_traceability_out(tm) if (tm := state.values["traceability_matrix"]) else None,
            review_report=_review_out(state.values.get("review_report")) if state.values.get("review_report") else None,
        )


# --- endpoints ---


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(body: CreateSessionRequest, request: Request):
    """Analyze a requirement. Returns a session id and the structured requirement."""
    store = request.app.state.store

    session_id = store.create()
    config = {"configurable": {"thread_id": session_id}}
    try:
        request.app.state.graph.invoke(
            {
                "raw_input": body.requirement,
                "requirement": None,
                "clarification_rounds": [],
                "clarification_complete": False,
                "pending_answers": {},
                "test_cases": [],
                "traceability_matrix": None,
                "review_report": None,
                "review_rounds": 0,
                "planner_decision": None,
            },
            config=config,
        )
    except AgentError as e:
        store.delete(session_id)
        raise HTTPException(status_code=422, detail=str(e))

    state = request.app.state.graph.get_state(config)

    return _build_response(session_id, state)


@router.post("/{session_id}/answers", response_model=SessionResponse)
def submit_answers(session_id: str, body: SubmitAnswersRequest, request: Request):
    """Submit answers for a session. Returns the updated session."""
    _require_session(request, session_id)
    config = {"configurable": {"thread_id": session_id}}
    _session_complete_check(request, config)
    
    try:
        request.app.state.graph.invoke(Command(resume={"answers": body.answers}), config=config)
    except AgentError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    
    state = request.app.state.graph.get_state(config)

    return _build_response(session_id, state)
