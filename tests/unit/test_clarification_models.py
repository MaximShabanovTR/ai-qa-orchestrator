import pytest
from models.clarification import ClarificationQuestion, ClarificationRound, QuestionTier


def make_question(tier: QuestionTier, id: str = "q1") -> ClarificationQuestion:
    return ClarificationQuestion(
        id=id,
        question="Does the system support X?",
        context="Relevant to the main flow.",
        tier=tier,
    )


def make_round(*tiers: QuestionTier) -> ClarificationRound:
    questions = [make_question(tier, id=f"q{i}") for i, tier in enumerate(tiers, 1)]
    return ClarificationRound(questions=questions)


# --- completeness_score ---

@pytest.mark.unit
@pytest.mark.parametrize("tiers,expected_score", [
    # no questions → perfect score
    ([], 1.0),
    # blocking penalty: 0.30 per question, capped at 0.60
    ([QuestionTier.BLOCKING], 0.70),
    ([QuestionTier.BLOCKING, QuestionTier.BLOCKING], 0.40),
    ([QuestionTier.BLOCKING, QuestionTier.BLOCKING, QuestionTier.BLOCKING], 0.40),  # cap
    # clarifying penalty: 0.10 per question, capped at 0.30
    ([QuestionTier.CLARIFYING], 0.90),
    ([QuestionTier.CLARIFYING, QuestionTier.CLARIFYING, QuestionTier.CLARIFYING], 0.70),
    ([QuestionTier.CLARIFYING] * 4, 0.70),  # cap
    # assumable questions carry no penalty
    ([QuestionTier.ASSUMABLE], 1.0),
    ([QuestionTier.ASSUMABLE] * 5, 1.0),
    # combined penalties
    ([QuestionTier.BLOCKING, QuestionTier.CLARIFYING], 0.60),
    ([QuestionTier.BLOCKING] * 2 + [QuestionTier.CLARIFYING] * 3, 0.10),  # both capped
    ([QuestionTier.BLOCKING] * 3 + [QuestionTier.CLARIFYING] * 4, 0.10),  # both capped
    # assumable does not affect combined score
    ([QuestionTier.BLOCKING, QuestionTier.ASSUMABLE], 0.70),
])
def test_completeness_score(tiers, expected_score):
    round_ = make_round(*tiers)
    assert round_.completeness_score == expected_score


# --- pipeline threshold boundary ---
# SCORE_THRESHOLD = 0.85 in pipeline.py.
# With the current formula, 0.85 is never a reachable value —
# the boundary that matters is: 0 blocking + ≤1 clarifying passes (0.90),
# while 0 blocking + 2 clarifying fails (0.80).

@pytest.mark.unit
def test_score_above_threshold_with_one_clarifying():
    round_ = make_round(QuestionTier.CLARIFYING)
    assert round_.completeness_score >= 0.85


@pytest.mark.unit
def test_score_below_threshold_with_two_clarifying():
    round_ = make_round(QuestionTier.CLARIFYING, QuestionTier.CLARIFYING)
    assert round_.completeness_score < 0.85


# --- count properties ---

@pytest.mark.unit
def test_counts_on_empty_round():
    round_ = make_round()
    assert round_.blocking_count == 0
    assert round_.clarifying_count == 0
    assert round_.assumable_count == 0


@pytest.mark.unit
def test_counts_on_mixed_round():
    round_ = make_round(
        QuestionTier.BLOCKING,
        QuestionTier.BLOCKING,
        QuestionTier.CLARIFYING,
        QuestionTier.ASSUMABLE,
        QuestionTier.ASSUMABLE,
        QuestionTier.ASSUMABLE,
    )
    assert round_.blocking_count == 2
    assert round_.clarifying_count == 1
    assert round_.assumable_count == 3


# --- ClarificationQuestion defaults ---

@pytest.mark.unit
def test_question_defaults():
    q = make_question(QuestionTier.BLOCKING)
    assert q.assumption is None
    assert q.answer is None


@pytest.mark.unit
def test_question_accepts_assumption_and_answer():
    q = ClarificationQuestion(
        id="q1",
        question="Is authentication required?",
        context="Login flow.",
        tier=QuestionTier.ASSUMABLE,
        assumption="Yes, based on standard security requirements.",
        answer="Yes, based on standard security requirements.",
    )
    assert q.assumption is not None
    assert q.answer == q.assumption
