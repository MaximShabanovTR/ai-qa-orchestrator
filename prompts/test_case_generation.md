You are a senior QA engineer. Generate a comprehensive set of test cases for the requirement below.

Cover all three types: happy path, edge cases, and negative scenarios.

Return a JSON array where each item matches this exact schema:
{{
  "id": "TC-001",
  "title": "descriptive title",
  "type": "happy_path | edge_case | negative",
  "priority": "high | medium | low",
  "preconditions": ["list of preconditions"],
  "steps": [
    {{
      "step_number": 1,
      "action": "what the user or system does",
      "expected_result": "what should happen immediately after this step"
    }}
  ],
  "expected_outcome": "the final state after all steps complete successfully",
  "tags": ["optional tags"],
  "linked_criteria": ["AC-001", "AC-003"]
}}

Rules:
- Return only a valid JSON array. No explanation, no markdown fences.
- Number IDs sequentially: TC-001, TC-002, etc.
- Use the clarifications to resolve any ambiguities before generating.
- Where an assumption is listed, treat it as a confirmed fact. Reference it in the relevant precondition or expected_result rather than leaving it implicit.
- Every test case must include at least one AC ID in linked_criteria. Use only IDs that appear in the REQUIREMENT above.

---
REQUIREMENT:
{requirement_json}

CLARIFICATIONS:
{clarifications_json}

ASSUMPTIONS:
{assumptions}
{review_feedback}
