from fastapi import APIRouter, HTTPException, Request
from agents.exceptions import AgentError
from models.clarification import QuestionTier
from api.schemas import (
    AcceptanceCriterionOut, ClarificationResponse, CreateSessionRequest,
    GenerateResponse, QuestionOut, RequirementOut, SessionCreatedResponse,
    SessionStatus, SubmitAnswersRequest, TestCaseOut, TestScopeOut,
    TestStepOut, TraceabilityOut,
)

router = APIRouter()


# --- helpers ---

def _require_session(request: Request, session_id: str):
    session = request.app.state.store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session


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


# --- endpoints ---

@router.post("", response_model=SessionCreatedResponse, status_code=201)
def create_session(body: CreateSessionRequest, request: Request):
    """Analyze a requirement. Returns a session id and the structured requirement."""
    store = request.app.state.store
    pipeline = request.app.state.pipeline

    session_id, session = store.create(body.requirement)
    try:
        pipeline.analyze(session)
    except AgentError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return SessionCreatedResponse(
        id=session_id,
        status=SessionStatus.ANALYZED,
        requirement=_requirement_out(session.requirement),
    )


@router.post("/{session_id}/clarification", response_model=ClarificationResponse)
def run_clarification(session_id: str, request: Request, body: SubmitAnswersRequest | None = None):
    """Run one clarification round. Optionally submit answers to the previous round first."""
    session = _require_session(request, session_id)
    pipeline = request.app.state.pipeline

    # Apply answers to the most recent round before running the next one
    if body and body.answers and session.latest_round:
        for question in session.latest_round.questions:
            if question.id in body.answers:
                question.answer = body.answers[question.id]

    try:
        pipeline.clarify(session)
    except AgentError as e:
        raise HTTPException(status_code=422, detail=str(e))

    latest = session.latest_round
    questions_for_user = [
        QuestionOut(
            id=q.id,
            question=q.question,
            context=q.context,
            tier=q.tier.value,
            assumption=q.assumption,
        )
        for q in latest.questions
        if q.tier in (QuestionTier.BLOCKING, QuestionTier.CLARIFYING)
    ]

    if not questions_for_user or (
        latest.blocking_count == 0 and latest.completeness_score >= 0.85
    ):
        status = SessionStatus.READY_TO_GENERATE
    else:
        status = SessionStatus.AWAITING_CLARIFICATION

    return ClarificationResponse(
        session_id=session_id,
        status=status,
        round_number=len(session.clarification_rounds),
        questions=questions_for_user,
    )


@router.post("/{session_id}/generate", response_model=GenerateResponse)
def generate_test_cases(session_id: str, request: Request):
    """Generate test cases and build the traceability matrix."""
    session = _require_session(request, session_id)
    pipeline = request.app.state.pipeline

    try:
        pipeline.generate(session)
    except AgentError as e:
        raise HTTPException(status_code=422, detail=str(e))

    test_cases = [
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
        for tc in session.test_cases
    ]

    traceability = None
    if session.traceability_matrix:
        tm = session.traceability_matrix
        traceability = TraceabilityOut(
            coverage=tm.coverage,
            gaps=[AcceptanceCriterionOut(id=ac.id, text=ac.text) for ac in tm.gaps],
            coverage_pct=tm.coverage_pct,
        )

    return GenerateResponse(
        session_id=session_id,
        status=SessionStatus.COMPLETE,
        test_cases=test_cases,
        traceability=traceability,
    )
