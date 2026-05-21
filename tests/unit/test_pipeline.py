import pytest
from agents.exceptions import AgentError
from config import MAX_CLARIFICATION_ROUNDS
from models.clarification import ClarificationQuestion, ClarificationRound, QuestionTier
from orchestrator.pipeline import Pipeline, SCORE_THRESHOLD


def make_question(
    tier: QuestionTier,
    id: str = "q1",
    assumption: str | None = None,
) -> ClarificationQuestion:
    return ClarificationQuestion(
        id=id, question="Some question?", context="Some context.", tier=tier, assumption=assumption
    )


def make_round(*questions: ClarificationQuestion) -> ClarificationRound:
    return ClarificationRound(questions=list(questions))


def clarifier_appends(*questions: ClarificationQuestion):
    """Returns a side_effect function that appends a fixed round each time the clarifier is called."""
    def _side_effect(session):
        session.clarification_rounds.append(make_round(*questions))
    return _side_effect


@pytest.fixture
def p():
    return Pipeline()


# --- _resolve_assumptions ---

@pytest.mark.unit
def test_resolve_assumptions_sets_answer_for_assumable(p):
    q = make_question(QuestionTier.ASSUMABLE, assumption="Auth required by default.")
    p._resolve_assumptions(make_round(q))
    assert q.answer == "Auth required by default."


@pytest.mark.unit
def test_resolve_assumptions_skips_assumable_without_assumption(p):
    q = make_question(QuestionTier.ASSUMABLE)  # assumption=None
    p._resolve_assumptions(make_round(q))
    assert q.answer is None


@pytest.mark.unit
@pytest.mark.parametrize("tier", [QuestionTier.BLOCKING, QuestionTier.CLARIFYING])
def test_resolve_assumptions_ignores_non_assumable_tiers(p, tier):
    q = make_question(tier, assumption="Would be wrong to auto-resolve.")
    p._resolve_assumptions(make_round(q))
    assert q.answer is None


@pytest.mark.unit
def test_resolve_assumptions_handles_mixed_round(p):
    blocking = make_question(QuestionTier.BLOCKING, id="q1")
    assumable_filled = make_question(QuestionTier.ASSUMABLE, id="q2", assumption="Yes.")
    assumable_empty = make_question(QuestionTier.ASSUMABLE, id="q3")
    p._resolve_assumptions(make_round(blocking, assumable_filled, assumable_empty))
    assert blocking.answer is None
    assert assumable_filled.answer == "Yes."
    assert assumable_empty.answer is None


# --- _collect_answers ---

@pytest.mark.unit
def test_collect_answers_prompts_blocking_and_clarifying(p, mocker):
    mocker.patch("builtins.input", return_value="user answer")
    blocking = make_question(QuestionTier.BLOCKING, id="q1")
    clarifying = make_question(QuestionTier.CLARIFYING, id="q2")
    assumable = make_question(QuestionTier.ASSUMABLE, id="q3")
    p._collect_answers(make_round(blocking, clarifying, assumable))
    assert blocking.answer == "user answer"
    assert clarifying.answer == "user answer"
    assert assumable.answer is None  # never touched by _collect_answers


@pytest.mark.unit
def test_collect_answers_does_not_call_input_when_only_assumable(p, mocker):
    mock_input = mocker.patch("builtins.input")
    p._collect_answers(make_round(make_question(QuestionTier.ASSUMABLE)))
    mock_input.assert_not_called()


@pytest.mark.unit
def test_collect_answers_does_not_call_input_on_empty_round(p, mocker):
    mock_input = mocker.patch("builtins.input")
    p._collect_answers(make_round())
    mock_input.assert_not_called()


# --- run(): stopping conditions ---

@pytest.mark.unit
def test_run_stops_after_one_round_when_no_questions(p, mocker):
    mocker.patch.object(p._analyst, "run")
    mocker.patch.object(p._clarifier, "run", side_effect=clarifier_appends())  # empty round
    mock_generator = mocker.patch.object(p._generator, "run")

    p.run("some requirement")

    assert p._clarifier.run.call_count == 1
    mock_generator.assert_called_once()


@pytest.mark.unit
def test_run_stops_when_score_meets_threshold(p, mocker):
    # 1 clarifying → score = 0.90 ≥ 0.85, blocking = 0 → stop
    mocker.patch.object(p._analyst, "run")
    mocker.patch.object(p._clarifier, "run", side_effect=clarifier_appends(
        make_question(QuestionTier.CLARIFYING, id="q1"),
    ))
    mock_generator = mocker.patch.object(p._generator, "run")

    p.run("some requirement")

    assert p._clarifier.run.call_count == 1
    mock_generator.assert_called_once()


@pytest.mark.unit
def test_run_does_not_stop_early_when_score_below_threshold(p, mocker):
    # 2 clarifying → score = 0.80 < 0.85, blocking = 0 → does not hit threshold stop
    mocker.patch.object(p._analyst, "run")
    mocker.patch.object(p._clarifier, "run", side_effect=clarifier_appends(
        make_question(QuestionTier.CLARIFYING, id="q1"),
        make_question(QuestionTier.CLARIFYING, id="q2"),
    ))
    mocker.patch("builtins.input", return_value="answer")
    mocker.patch.object(p._generator, "run")

    p.run("some requirement")

    assert p._clarifier.run.call_count == MAX_CLARIFICATION_ROUNDS


@pytest.mark.unit
def test_run_exhausts_max_rounds_when_blocking_persists(p, mocker):
    mocker.patch.object(p._analyst, "run")
    mocker.patch.object(p._clarifier, "run", side_effect=clarifier_appends(
        make_question(QuestionTier.BLOCKING, id="q1"),
    ))
    mocker.patch("builtins.input", return_value="answer")
    mock_generator = mocker.patch.object(p._generator, "run")

    p.run("some requirement")

    assert p._clarifier.run.call_count == MAX_CLARIFICATION_ROUNDS
    mock_generator.assert_called_once()


# --- run(): error handling ---

@pytest.mark.unit
def test_run_returns_early_on_analyst_error(p, mocker):
    mocker.patch.object(p._analyst, "run", side_effect=AgentError("parse failed"))
    mock_clarifier = mocker.patch.object(p._clarifier, "run")
    mock_generator = mocker.patch.object(p._generator, "run")

    session = p.run("some requirement")

    mock_clarifier.assert_not_called()
    mock_generator.assert_not_called()
    assert session.test_cases == []


@pytest.mark.unit
def test_run_proceeds_to_generator_after_clarifier_error(p, mocker):
    mocker.patch.object(p._analyst, "run")
    mocker.patch.object(p._clarifier, "run", side_effect=AgentError("timeout"))
    mock_generator = mocker.patch.object(p._generator, "run")

    p.run("some requirement")

    mock_generator.assert_called_once()


@pytest.mark.unit
def test_run_returns_without_test_cases_on_generator_error(p, mocker):
    mocker.patch.object(p._analyst, "run")
    mocker.patch.object(p._clarifier, "run", side_effect=clarifier_appends())  # empty → stops early
    mocker.patch.object(p._generator, "run", side_effect=AgentError("truncated response"))

    session = p.run("some requirement")

    assert session.test_cases == []
