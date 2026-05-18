from config import MAX_CLARIFICATION_ROUNDS
from models.clarification import QuestionTier
from orchestrator.session import Session
from agents.requirements_analyst import RequirementsAnalyst
from agents.clarification_agent import ClarificationAgent
from agents.test_case_generator import TestCaseGenerator

SCORE_THRESHOLD = 0.85


class Pipeline:
    def __init__(self) -> None:
        self._analyst = RequirementsAnalyst()
        self._clarifier = ClarificationAgent()
        self._generator = TestCaseGenerator()

    def run(self, raw_input: str) -> Session:
        session = Session(raw_input=raw_input)

        print("Analyzing requirements...")
        self._analyst.run(session)

        for round_num in range(1, MAX_CLARIFICATION_ROUNDS + 1):
            print(f"\nClarification round {round_num}/{MAX_CLARIFICATION_ROUNDS}...")
            self._clarifier.run(session)

            latest = session.clarification_rounds[-1]
            self._resolve_assumptions(latest)

            if not latest.questions:
                print("No gaps found. Requirements are clear.")
                break

            if latest.blocking_count == 0 and latest.completeness_score >= SCORE_THRESHOLD:
                print(f"Completeness score: {latest.completeness_score}. Proceeding to generation.")
                break

            if round_num == MAX_CLARIFICATION_ROUNDS:
                if latest.blocking_count > 0:
                    print(
                        f"Warning: {latest.blocking_count} blocking gap(s) unresolved. "
                        "Test coverage may be incomplete."
                    )
                break

            self._collect_answers(latest)

        if session.assumptions_made:
            print(f"\nAssumptions made ({len(session.assumptions_made)}):")
            for assumption in session.assumptions_made:
                print(f"  - {assumption}")

        print("\nGenerating test cases...")
        self._generator.run(session)

        return session

    def _resolve_assumptions(self, round_) -> None:
        for q in round_.questions:
            if q.tier == QuestionTier.ASSUMABLE:
                q.answer = q.assumption

    def _collect_answers(self, round_) -> None:
        questions_for_user = [
            q for q in round_.questions
            if q.tier in (QuestionTier.BLOCKING, QuestionTier.CLARIFYING)
        ]
        if not questions_for_user:
            return

        print("\nPlease answer the following questions:\n")
        for q in questions_for_user:
            print(f"[{q.id}] [{q.tier.value.upper()}] {q.question}")
            print(f"      Why this matters: {q.context}")
            q.answer = input("      Your answer: ").strip()
