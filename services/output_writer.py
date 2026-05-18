import json
from pathlib import Path
from models import TestCase


def write_json(test_cases: list[TestCase], path: Path) -> None:
    path.write_text(
        json.dumps([tc.model_dump() for tc in test_cases], indent=2),
        encoding="utf-8",
    )


def write_markdown(test_cases: list[TestCase], path: Path) -> None:
    lines: list[str] = ["# Test Cases\n"]
    for tc in test_cases:
        lines.append(f"## [{tc.priority.value.upper()}] {tc.title}")
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
        lines.append("---\n")
    path.write_text("\n".join(lines), encoding="utf-8")
