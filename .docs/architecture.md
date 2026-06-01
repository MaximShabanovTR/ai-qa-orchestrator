# Architecture Decisions

Significant design decisions, trade-offs, and deferred improvements.

---

## Session is mutable, not immutable

**Decision:** Agents mutate `Session` in place rather than returning new instances.

**Why:** The pipeline is strictly sequential. There is no parallelism, no branching, and no need to diff states between agents. `deepcopy` on nested Pydantic models would add overhead with no functional benefit at this scale. Debugging is better served by logging than by snapshot copies.

**Trade-off:** No structural audit trail of session state after each agent. Debugging a downstream failure requires reading the pipeline flow to understand what each agent was responsible for.

**Deferred:** If the pipeline ever becomes parallel (task graph execution, concurrent agents), this needs a full redesign — not just immutable copies. Immutable session would not solve the concurrency problem; it would just shift it.

**Mitigation now:** Agent responsibilities are clearly partitioned. Each agent owns exactly one field on the session:
- `RequirementsAnalyst` → `session.requirement`
- `ClarificationAgent` → `session.clarification_rounds` (append only)
- `TestCaseGenerator` → `session.test_cases`

---

## completeness_score is computed, not LLM-generated

**Decision:** `ClarificationRound.completeness_score` is a deterministic property computed from question counts, not a field returned by Claude.

**Why:** Delegating the stopping decision to Claude creates a self-referential feedback loop — the model that generates the gaps also decides whether they are sufficient. This is untestable and opaque. A computed score is auditable, tunable, and consistent across runs.

**Formula:** `1.0 - min(blocking * 0.30, 0.60) - min(clarifying * 0.10, 0.30)`

**Threshold:** `SCORE_THRESHOLD = 0.85` in `pipeline.py`. Adjust there, not in the model.

---

## Prompt templates are files, not inline strings

**Decision:** All prompt text lives in `prompts/*.md`, loaded at runtime by `BaseAgent._load_prompt()`.

**Why:** Prompt engineering is iterative. Keeping prompts in files means you can change wording, add few-shot examples, or adjust instructions without touching agent code or running tests. The separation also makes prompts reviewable as their own artifact.

**Trade-off:** A missing or malformed placeholder raises a `KeyError` at runtime, not at import time. The failure surface is visible only when the agent runs.

---

## max_tokens is required, not defaulted in claude_client

**Decision:** `claude_client.chat()` has no default for `max_tokens`. Every caller must be explicit.

**Why:** Silently defaulting to 4096 on the test case generator caused truncation on large requirement sets. Making callers declare their budget makes the decision visible at the call site rather than hidden in a wrapper.

**Current values:** All agents use 4096 except `TestCaseGenerator`, which uses 16000.

---

## TraceabilityMatrix is computed, not LLM-generated

**Decision:** Coverage is derived from `TestCase.linked_criteria` (LLM-populated AC IDs) and `StructuredRequirement.acceptance_criteria`. The matrix is built by `TraceabilityMatrix.build()` — a pure classmethod with no Claude call.

**Why:** Asking Claude "which test cases cover which ACs?" would create a second LLM pass over already-generated data, introducing a second failure surface and making coverage figures non-reproducible. The LLM's job is to populate `linked_criteria` in each test case. Once those IDs exist, aggregation is deterministic.

**Trade-off:** Coverage quality depends on how accurately the LLM populates `linked_criteria`. A test case that covers AC-003 but omits it from `linked_criteria` will show as a false gap. The prompt instructs the model to include at least one AC ID per test case, but this cannot be strictly enforced.

**Mitigation:** Unknown AC IDs in `linked_criteria` are silently ignored (hallucination guard). The `gaps` list in the matrix carries full `AcceptanceCriterion` objects so output can show gap descriptions without a separate lookup.

**Deferred:** A review agent could cross-check `linked_criteria` against actual test steps to catch mislabeled coverage. That is the purpose of the planned test case review layer.
