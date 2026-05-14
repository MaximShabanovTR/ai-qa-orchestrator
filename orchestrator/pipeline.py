from config import MAX_CLARIFICATION_ROUNDS
from orchestrator.session import Session
from agents.requirements_analyst import RequirementsAnalyst
from agents.clarification_agent import ClarificationAgent
from agents.test_case_generator import TestCaseGenerator


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
            if latest.is_sufficient:
                print("Requirements are sufficiently clear.")
                break

            self._collect_answers(latest)

        print("\nGenerating test cases...")
        self._generator.run(session)

        return session

    def _collect_answers(self, round_) -> None:
        print("\nPlease answer the following questions:\n")
        for q in round_.questions:
            print(f"[{q.id}] {q.question}")
            print(f"      Why this matters: {q.context}")
            q.answer = input("      Your answer: ").strip()
