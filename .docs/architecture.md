# Architecture Decisions

Significant design decisions, trade-offs, and deferred improvements.

---

## LangGraph replaces the sequential pipeline

**Decision:** The clarification loop and agent sequencing moved from `orchestrator/pipeline.py` into a LangGraph `StateGraph` (`workflow/graph.py` + `workflow/nodes.py`).

**Why:** The CLI pipeline used a blocking `input()` loop. This works on a terminal but cannot serve an HTTP client — the process would block waiting for stdin while the HTTP request has already responded. LangGraph's `interrupt()` mechanism pauses the graph at an explicit checkpoint, serializes state to a checkpointer, and resumes when `Command(resume=...)` is called in a subsequent HTTP request. This makes the same clarification loop work across multiple HTTP round-trips without changing any agent code.

**Trade-off:** LangGraph adds an indirection layer. To understand the flow, you must read the graph wiring in `graph.py` and the node functions in `nodes.py`, not a single sequential function. The `QAState` TypedDict and `Session` dataclass now coexist, which adds surface area.

**Why not pure FastAPI with in-memory session objects?** State would live only in a Python dict, with no serializable checkpoint. Resuming a session after a server restart would lose all progress. LangGraph's checkpointer is swappable (memory → SQLite → Redis) without changing any node code.

---

## Session as a node-to-agent bridge

**Decision:** Each node constructs a temporary `Session` dataclass, calls the agent with it, then extracts results back into a state dict. `Session` is never stored directly in `QAState`.

**Why:** Agents were designed to receive a `Session` and mutate it. Changing them to accept/return raw dicts or `QAState` would require rewriting all agents and their tests. The bridge pattern keeps agents unchanged while making nodes compatible with LangGraph's state model.

**Trade-off:** Each node duplicates a small amount of construction boilerplate. The alternative (making agents LangGraph-native) would couple them to a specific orchestration framework.

**`deepcopy` requirement:** Nodes pass `copy.deepcopy(list(state["clarification_rounds"]))` to `Session`. This is mandatory — passing the live list by reference would allow `ClarificationAgent` (which mutates questions in place) to corrupt the objects already stored in the LangGraph checkpoint, causing non-deterministic behavior on resume.

---

## Session is mutable inside agents (unchanged)

**Decision:** Agents mutate `Session` in place rather than returning new instances. This has not changed with the LangGraph migration.

**Why:** Agent code is unchanged. The `deepcopy` in node construction ensures mutations inside an agent do not affect LangGraph's checkpointed state. Agents remain testable in isolation without any graph machinery.

**Partitioning:**
- `RequirementsAnalyst` → `session.requirement`
- `ClarificationAgent` → `session.clarification_rounds` (append only)
- `TestCaseGenerator` → `session.test_cases`

**Deferred:** If agents ever run concurrently, the `Session` bridge pattern must be replaced with a fully immutable approach — `deepcopy` in the node only protects checkpoint state, not cross-agent concurrency.

---

## completeness_score is computed, not LLM-generated

**Decision:** `ClarificationRound.completeness_score` is a deterministic property computed from question counts, not a field returned by Claude.

**Why:** Delegating the stopping decision to Claude creates a self-referential feedback loop — the model that generates the gaps also decides whether they are sufficient. This is untestable and opaque. A computed score is auditable, tunable, and consistent across runs.

**Formula:** `1.0 - min(blocking * 0.30, 0.60) - min(clarifying * 0.10, 0.30)`

**Threshold:** `SCORE_THRESHOLD = 0.85` in `config.py`. The `clarify` node imports it from there. Adjust in `config.py`, not in the node or the model.

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

---

## Two-endpoint API with unified SessionResponse

**Decision:** The HTTP API exposes exactly two endpoints — `POST /sessions` (start) and `POST /sessions/{id}/answers` (resume) — both returning the same `SessionResponse` schema.

**Why:** The clarification loop is a conversation: multiple round-trips, each either asking more questions or finishing. Splitting into separate endpoints per state (start, clarify, generate) would require the client to manage state machine transitions. A unified response with a `status` discriminator (`awaiting_clarification` | `complete`) lets the client use a single loop: send request → check status → either submit answers or use the result.

**Trade-off:** A single response schema carries optional fields for both states (`questions` for AWAITING, `test_cases`/`traceability` for COMPLETE), which can be confusing at first read. The alternative — separate response types per status — would require the client to handle two distinct schemas from the same endpoint, which is equally awkward. The discriminator field makes the current approach workable.

**Why not three endpoints?** An earlier design had separate endpoints for clarification and generation. This forced the client to know the session's current phase and route to the right endpoint — effectively reimplementing the state machine on the client side. Removing that duplication is the primary motivation for the unified design.

---

## ReviewAgent: deterministic + LLM hybrid

**Decision:** `ReviewAgent` (`agents/review_agent.py`) extends `BaseAgent` and runs two layers: (1) `ReviewReport.build()` for all structural findings — pure, deterministic, no LLM; (2) an LLM call via `prompts/review.md` for semantic findings (`WEAK_STEP`, `MISLINKED`, `SEMANTIC_GAP`, `SEMANTIC_DUPLICATE`). Both finding lists are merged into one `ReviewReport`.

**Why two layers:** Structural checks (coverage gaps, hallucinated links, duplicates, malformed tests) are computable from typed data — delegating them to the LLM would trade determinism for no accuracy gain. Semantic checks (vague step wording, mislinked intent, missing scenarios) require natural language understanding that structured data alone cannot surface. Each layer does what it's suited for.

**Why `ReviewReport.build()` lives on the model, not the agent:** `TraceabilityMatrix.build()` set this precedent. Deterministic aggregations over typed models are pure functions — they belong as classmethods on the output model, not buried in agent logic. This keeps them testable without any agent or graph machinery. `ReviewReport.build()` was further refactored in Stage 3 (Part A) into six focused `_check_*` classmethods so each invariant is independently testable.

**Finding sources:** Every `ReviewFinding` carries a `source` field: `"deterministic"` for findings from `ReviewReport.build()`, `"llm"` for findings from the semantic LLM pass. Consumers can filter by source to distinguish structural from semantic issues.

**Resilience:** The `review` node wraps `_reviewer.run(session)` in a try/except. If the LLM call fails, deterministic findings survive (they are computed before the LLM call inside `ReviewAgent.run()`). If the entire agent crashes, the graph completes with `review_report=None` rather than locking the session at HTTP 409 forever. The review gate is advisory — a non-zero `error_count` does not block test case delivery.

**Advisory gate:** `ReviewReport.passed` is `True` when `error_count == 0`. The `plan` node reads this to decide whether to retry generation. Surfaced in the API response for human review.

---

## LangGraph Command(resume={}) empty-dict workaround

**Decision:** `POST /sessions/{id}/answers` wraps the answers dict before resuming: `Command(resume={"answers": body.answers})`. The `collect_answers` node unwraps it: `result.get("answers", {})`.

**Why:** LangGraph 1.2.2 classifies a resume value as a "resume-map" (keyed by interrupt IDs) when `isinstance(resume, dict) and all(is_xxh3_128_hexdigest(k) for k in resume)`. Python's `all()` over an empty iterable returns `True` (vacuous truth), so `Command(resume={})` is silently treated as an empty resume-map. The `interrupt()` call re-fires instead of returning `{}`, causing the session to remain stuck at `awaiting_clarification`.

**Fix depth:** The wrapper is the minimal fix that does not require patching LangGraph internals. The key `"answers"` is not an xxh3 hash, so `resume_is_map` evaluates to `False` for any answers dict including an empty one.

**Invariant:** `collect_answers` always expects `result` to be `{"answers": dict[str, str]}`. Any caller that bypasses the HTTP layer and resumes the graph directly must use the same shape.

---

## Remediation loop with deterministic planner

**Decision:** After `generate`, the graph runs `review → plan → route_after_plan → { generate | END }` in a bounded loop. The `plan` node calls `PlannerDecision.from_report()` to decide whether to retry. `ReviewReport.build()` was refactored into six focused `_check_*` classmethods so each invariant is independently testable.

**Graph shape:**
```
generate → review → plan → route_after_plan → { generate (retry) | END }
```

**Why `PlannerDecision` instead of a route function:** A bare `route_after_plan` function would be anonymous and untestable. `PlannerDecision.from_report()` is a pure classmethod — the same pattern as `TraceabilityMatrix.build()` and `ReviewReport.build()`. It is testable without graph machinery, and its `reason` field makes the stopping condition observable in the API response. When the planner eventually needs LLM input, the `plan` node upgrades to a `BaseAgent` subclass without changing the graph wiring.

**`PlannerDecision.from_report()` decision order** (checked in sequence — mirrors the clarify node stopping logic):
1. `report is None` → `DONE("review_unavailable")` — never loop on a crashed review
2. `report.passed` → `DONE("passed")`
3. `review_rounds >= MAX_REVIEW_ROUNDS` → `DONE("max_rounds_reached")`
4. otherwise → `REGENERATE_ALL(first_error.category.value)`

**Why `review_rounds` is incremented in `plan`, not `review`:** The `plan` node is the only place that knows a regeneration is about to happen. Incrementing in `review` would count reviews run; incrementing in `plan` counts regenerations triggered — which is the correct semantics for the cap check.

**Why node is named `plan` not `planner`:** All nodes use the verb form of their action: `analyze`, `clarify`, `generate`, `review`. `plan` is consistent with this convention.

**Generator feedback on retry:** `generate` passes `session.review_report` into `TestCaseGenerator`. `_format_review_feedback()` returns `""` on first pass (no prior review) and a formatted ERROR+WARNING findings block on retry. The `{review_feedback}` placeholder in `prompts/test_case_generation.md` receives this — empty string renders as nothing; populated string tells Claude exactly what to fix.

**Why include WARNING findings in retry feedback, not just ERRORs:** The full suite is regenerated on retry. Giving Claude the complete picture (errors that blocked + warnings that degraded quality) costs nothing extra and produces a better second attempt.

**`ReviewReport._check_*` refactor:** `ReviewReport.build()` was decomposed into six `_check_*` classmethods so each deterministic invariant can be unit-tested in isolation — no graph, no LLM, no fixtures beyond typed data. This is the same motivation as keeping `TraceabilityMatrix.build()` on the model rather than in an agent.

**Future remediation actions beyond MVP:**
- `REGENERATE_MISSING` — regenerate only test cases for uncovered ACs (requires partial-suite merge logic in generator)
- `REWRITE_TEST_CASES` — targeted rewrite of specific failing cases (requires new agent)


---

## SessionStore is a set, not a map

**Decision:** `api/session_store.py` stores only session UUIDs in a `set[str]`. It does not store session data.

**Why:** LangGraph's `MemorySaver` checkpointer owns all session state, keyed by `thread_id` (which equals `session_id`). A second data store would be a redundant copy with a divergence risk. The `SessionStore` exists only to answer "is this session_id valid?" for the 404 check — nothing more.

**Implication:** Deleting a session from the store does not delete LangGraph checkpoint data. In production, checkpoint cleanup would need to be handled separately (e.g., TTL on the checkpoint backend).
