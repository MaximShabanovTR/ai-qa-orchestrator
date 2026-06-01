import json
from pathlib import Path
from models import TestCase
from models.requirement import StructuredRequirement
from models.traceability import TraceabilityMatrix
from orchestrator.session import Session


def write_json(test_cases: list[TestCase], path: Path) -> None:
    path.write_text(
        json.dumps([tc.model_dump() for tc in test_cases], indent=2),
        encoding="utf-8",
    )


def write_session(session: Session, path: Path) -> None:
    data = {
        "raw_input": session.raw_input,
        "requirement": session.requirement.model_dump() if session.requirement else None,
        "clarification_rounds": [
            {
                "questions": [q.model_dump() for q in round_.questions],
                "completeness_score": round_.completeness_score,
            }
            for round_ in session.clarification_rounds
        ],
        "test_cases": [tc.model_dump() for tc in session.test_cases],
        "traceability_matrix": session.traceability_matrix.model_dump() if session.traceability_matrix else None,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_markdown(
    test_cases: list[TestCase],
    path: Path,
    matrix: TraceabilityMatrix | None = None,
    requirement: StructuredRequirement | None = None,
) -> None:
    lines: list[str] = ["# Test Cases\n"]
    for tc in test_cases:
        lines.append(f"## {tc.id} · [{tc.priority.value.upper()}] {tc.title}")
        lines.append(f"**Type:** {tc.type.value}  ")
        if tc.preconditions:
            lines.append(f"**Preconditions:** {', '.join(tc.preconditions)}\n")
        lines.append("**Steps:**")
        for step in tc.steps:
            lines.append(f"{step.step_number}. {step.action}  ")
            lines.append(f"   _Expected: {step.expected_result}_")
        lines.append(f"\n**Expected outcome:** {tc.expected_outcome}\n")
        if tc.tags:
            lines.append(f"**Tags:** {', '.join(tc.tags)}\n")
        if tc.linked_criteria:
            lines.append(f"**Covers:** {', '.join(tc.linked_criteria)}\n")
        lines.append("---\n")

    if matrix:
        ac_text: dict[str, str] = (
            {ac.id: ac.text for ac in requirement.acceptance_criteria}
            if requirement else {}
        )
        lines.append("# Traceability Matrix\n")
        lines.append(f"**Coverage:** {matrix.coverage_pct}%\n")
        lines.append("| ID | Acceptance Criterion | Test Cases |")
        lines.append("|---|---|---|")
        for ac_id, tc_ids in matrix.coverage.items():
            text = ac_text.get(ac_id, "")
            tc_list = ", ".join(tc_ids) if tc_ids else "_not covered_"
            lines.append(f"| {ac_id} | {text} | {tc_list} |")
        if matrix.gaps:
            lines.append("\n**Uncovered criteria:**\n")
            for ac in matrix.gaps:
                lines.append(f"- [{ac.id}] {ac.text}")

    path.write_text("\n".join(lines), encoding="utf-8")
