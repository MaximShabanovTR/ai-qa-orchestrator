import pytest
from agents.test_case_generator import TestCaseGenerator
from models.clarification import ClarificationQuestion, ClarificationRound, QuestionTier
from orchestrator.session import Session


def make_question(
    tier: QuestionTier,
    id: str = "q1",
    question: str = "Some question?",
    answer: str | None = None,
    assumption: str | None = None,
) -> ClarificationQuestion:
    return ClarificationQuestion(
        id=id, question=question, context="context.", tier=tier,
        answer=answer, assumption=assumption,
    )


def make_session(*rounds: ClarificationRound) -> Session:
    s = Session(raw_input="some requirement")
    s.clarification_rounds = list(rounds)
    return s


def make_round(*questions: ClarificationQuestion) -> ClarificationRound:
    return ClarificationRound(questions=list(questions))


@pytest.fixture
def gen() -> TestCaseGenerator:
    return TestCaseGenerator()


# --- _format_clarifications ---

@pytest.mark.unit
def test_format_clarifications_returns_none_string_when_no_answered(gen):
    s = make_session(make_round(make_question(QuestionTier.BLOCKING, id="q1")))
    assert gen._format_clarifications(s) == "None"


@pytest.mark.unit
def test_format_clarifications_excludes_assumable_answers(gen):
    # ASSUMABLE questions are auto-resolved and must not appear in the clarifications
    # block — they belong in the assumptions block instead
    q = make_question(QuestionTier.ASSUMABLE, id="q1", answer="Assumed value.")
    s = make_session(make_round(q))
    assert gen._format_clarifications(s) == "None"


@pytest.mark.unit
@pytest.mark.parametrize("tier", [QuestionTier.BLOCKING, QuestionTier.CLARIFYING])
def test_format_clarifications_includes_answered_question(gen, tier):
    q = make_question(tier, id="q1", question="Is login required?", answer="Yes.")
    s = make_session(make_round(q))
    result = gen._format_clarifications(s)
    assert result == "Q: Is login required?\nA: Yes."


@pytest.mark.unit
def test_format_clarifications_formats_multiple_questions_in_order(gen):
    q1 = make_question(QuestionTier.BLOCKING, id="q1", question="First?", answer="A1.")
    q2 = make_question(QuestionTier.CLARIFYING, id="q2", question="Second?", answer="A2.")
    s = make_session(make_round(q1, q2))
    result = gen._format_clarifications(s)
    assert result == "Q: First?\nA: A1.\nQ: Second?\nA: A2."


@pytest.mark.unit
def test_format_clarifications_excludes_assumable_from_mixed_round(gen):
    blocking = make_question(QuestionTier.BLOCKING, id="q1", question="Q1?", answer="A1.")
    assumable = make_question(QuestionTier.ASSUMABLE, id="q2", answer="Auto.")
    s = make_session(make_round(blocking, assumable))
    result = gen._format_clarifications(s)
    assert result == "Q: Q1?\nA: A1."


@pytest.mark.unit
def test_format_clarifications_flattens_across_rounds(gen):
    r1 = make_round(make_question(QuestionTier.BLOCKING, id="q1", question="Q1?", answer="A1."))
    r2 = make_round(make_question(QuestionTier.CLARIFYING, id="q2", question="Q2?", answer="A2."))
    s = make_session(r1, r2)
    result = gen._format_clarifications(s)
    assert result == "Q: Q1?\nA: A1.\nQ: Q2?\nA: A2."


# --- _format_assumptions ---

@pytest.mark.unit
def test_format_assumptions_returns_none_string_when_no_assumptions(gen):
    s = make_session()
    assert gen._format_assumptions(s) == "None"


@pytest.mark.unit
def test_format_assumptions_formats_single_assumption(gen):
    q = make_question(QuestionTier.ASSUMABLE, id="q1", assumption="Auth is required.")
    q.answer = q.assumption  # simulate _resolve_assumptions
    s = make_session(make_round(q))
    assert gen._format_assumptions(s) == "- Auth is required."


@pytest.mark.unit
def test_format_assumptions_formats_multiple_assumptions(gen):
    q1 = make_question(QuestionTier.ASSUMABLE, id="q1", assumption="Auth is required.")
    q2 = make_question(QuestionTier.ASSUMABLE, id="q2", assumption="HTTPS only.")
    for q in (q1, q2):
        q.answer = q.assumption
    s = make_session(make_round(q1, q2))
    result = gen._format_assumptions(s)
    assert result == "- Auth is required.\n- HTTPS only."


@pytest.mark.unit
def test_format_assumptions_excludes_assumable_without_assumption(gen):
    q = make_question(QuestionTier.ASSUMABLE, id="q1")  # assumption=None
    s = make_session(make_round(q))
    assert gen._format_assumptions(s) == "None"
