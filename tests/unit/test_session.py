import pytest
from orchestrator.session import Session
from models.clarification import ClarificationQuestion, ClarificationRound, QuestionTier


def make_question(
    tier: QuestionTier,
    id: str = "q1",
    answer: str | None = None,
    assumption: str | None = None,
) -> ClarificationQuestion:
    return ClarificationQuestion(
        id=id,
        question="Some question?",
        context="Some context.",
        tier=tier,
        answer=answer,
        assumption=assumption,
    )


def make_round(*questions: ClarificationQuestion) -> ClarificationRound:
    return ClarificationRound(questions=list(questions))


def make_session(*rounds: ClarificationRound) -> Session:
    s = Session(raw_input="some requirement")
    s.clarification_rounds = list(rounds)
    return s


# --- latest_round ---

@pytest.mark.unit
def test_latest_round_is_none_with_no_rounds():
    s = make_session()
    assert s.latest_round is None


@pytest.mark.unit
def test_latest_round_returns_only_round():
    round_ = make_round(make_question(QuestionTier.BLOCKING))
    s = make_session(round_)
    assert s.latest_round is round_


@pytest.mark.unit
def test_latest_round_returns_last_not_first():
    first = make_round(make_question(QuestionTier.BLOCKING, id="q1"))
    second = make_round(make_question(QuestionTier.CLARIFYING, id="q2"))
    third = make_round(make_question(QuestionTier.ASSUMABLE, id="q3"))
    s = make_session(first, second, third)
    assert s.latest_round is third


# --- all_answered_questions ---

@pytest.mark.unit
def test_all_answered_questions_empty_with_no_rounds():
    s = make_session()
    assert s.all_answered_questions == []


@pytest.mark.unit
def test_all_answered_questions_excludes_unanswered():
    answered = make_question(QuestionTier.BLOCKING, id="q1", answer="Yes")
    unanswered = make_question(QuestionTier.CLARIFYING, id="q2")
    s = make_session(make_round(answered, unanswered))
    result = s.all_answered_questions
    assert len(result) == 1
    assert result[0].id == "q1"


@pytest.mark.unit
def test_all_answered_questions_flattens_across_rounds():
    r1 = make_round(
        make_question(QuestionTier.BLOCKING, id="q1", answer="Yes"),
        make_question(QuestionTier.CLARIFYING, id="q2"),  # unanswered
    )
    r2 = make_round(
        make_question(QuestionTier.CLARIFYING, id="q3", answer="No"),
        make_question(QuestionTier.ASSUMABLE, id="q4", answer="Assumed"),
    )
    s = make_session(r1, r2)
    result = s.all_answered_questions
    assert [q.id for q in result] == ["q1", "q3", "q4"]


@pytest.mark.unit
def test_all_answered_questions_treats_empty_string_as_unanswered():
    # empty string is falsy — same behavior as no answer
    q = make_question(QuestionTier.BLOCKING, id="q1", answer="")
    s = make_session(make_round(q))
    assert s.all_answered_questions == []


# --- assumptions_made ---

@pytest.mark.unit
def test_assumptions_made_empty_with_no_rounds():
    s = make_session()
    assert s.assumptions_made == []


@pytest.mark.unit
def test_assumptions_made_returns_assumption_strings():
    q = make_question(
        QuestionTier.ASSUMABLE,
        id="q1",
        assumption="Authenticated users only.",
    )
    s = make_session(make_round(q))
    assert s.assumptions_made == ["Authenticated users only."]


@pytest.mark.unit
def test_assumptions_made_excludes_assumable_without_assumption():
    q = make_question(QuestionTier.ASSUMABLE, id="q1")  # assumption=None
    s = make_session(make_round(q))
    assert s.assumptions_made == []


@pytest.mark.unit
def test_assumptions_made_excludes_non_assumable_tiers():
    # a BLOCKING or CLARIFYING question with an assumption field set is not an assumption
    blocking = make_question(QuestionTier.BLOCKING, id="q1", assumption="Guessed.")
    clarifying = make_question(QuestionTier.CLARIFYING, id="q2", assumption="Inferred.")
    s = make_session(make_round(blocking, clarifying))
    assert s.assumptions_made == []


@pytest.mark.unit
def test_assumptions_made_flattens_across_rounds():
    r1 = make_round(
        make_question(QuestionTier.ASSUMABLE, id="q1", assumption="First assumption."),
    )
    r2 = make_round(
        make_question(QuestionTier.ASSUMABLE, id="q2", assumption="Second assumption."),
        make_question(QuestionTier.ASSUMABLE, id="q3"),  # no assumption
    )
    s = make_session(r1, r2)
    assert s.assumptions_made == ["First assumption.", "Second assumption."]


# --- mutable default safety ---

@pytest.mark.unit
def test_sessions_do_not_share_clarification_rounds():
    s1 = Session(raw_input="req 1")
    s2 = Session(raw_input="req 2")
    s1.clarification_rounds.append(make_round(make_question(QuestionTier.BLOCKING)))
    assert s2.clarification_rounds == []


@pytest.mark.unit
def test_sessions_do_not_share_test_cases():
    s1 = Session(raw_input="req 1")
    s2 = Session(raw_input="req 2")
    s1.test_cases.append(object())  # type: ignore[arg-type]
    assert s2.test_cases == []
