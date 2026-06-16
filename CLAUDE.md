# CLAUDE.md — AI QA Orchestrator

This file provides project context for Claude Code sessions. Read it before making any changes.

---

## What this project is

An AI-driven QA orchestration system that takes a plain-text requirement and produces a structured test suite. The system analyzes requirements, runs a tiered clarification loop with the user, then generates test cases covering happy path, edge cases, and negative scenarios.

This is not a chatbot or a generic agent framework. It is a focused, domain-specific QA workflow with deterministic control flow and typed data contracts at every boundary.

---

## Architecture

Six layers. Each has a single responsibility. They communicate only through Pydantic models — no raw dicts, no string passing between layers.

```
api/app.py (FastAPI)
  └── workflow/graph.py (LangGraph StateGraph + MemorySaver)
        ├── workflow/nodes.py: analyze    → agents/requirements_analyst.py
        ├── workflow/nodes.py: clarify    → agents/clarification_agent.py
        ├── workflow/nodes.py: collect_answers  (LangGraph interrupt/resume)
        └── workflow/nodes.py: generate   → agents/test_case_generator.py
              └── services/claude_client.py → Anthropic SDK
```

| Layer | Location | Responsibility |
|---|---|---|
| API | `api/` | FastAPI routes, request/response schemas, session registry |
| Workflow | `workflow/` | LangGraph graph, node functions, QAState definition |
| Orchestration | `orchestrator/` | Session dataclass — bridge between nodes and agents |
| Agents | `agents/` | Stateless Claude callers; one per pipeline stage |
| Models | `models/` | Pydantic data contracts between all layers |
| Services | `services/` | Anthropic SDK wrapper, JSON/Markdown serializers |
| Prompts | `prompts/` | Markdown templates with `{placeholder}` variables |
| Generators | `generators/` | Code generation — Playwright stub, not yet implemented |

---

## Workflow state

### `QAState` (`workflow/state.py`)

The primary state container managed by LangGraph's checkpointer. All nodes read from and write partial updates to this TypedDict.

```python
class QAState(TypedDict):
    raw_input: str
    requirement: StructuredRequirement | None
    clarification_rounds: Annotated[list[ClarificationRound], operator.add]  # reducer: append
    clarification_complete: bool
    pending_answers: dict[str, str]   # question id → answer text, set by interrupt
    test_cases: list[TestCase]
    traceability_matrix: TraceabilityMatrix | None
```

`clarification_rounds` uses an `operator.add` reducer — nodes return only the new round in a list and LangGraph appends it to the existing list automatically.

### `Session` (`orchestrator/session.py`)

A local bridge dataclass constructed inside each node to pass data into agents without changing the agent interface. Nodes build it from `QAState`, call `agent.run(session)`, then extract results back out into a return dict. It is never persisted — LangGraph state is the source of truth.

Properties: `latest_round`, `all_answered_questions` (answered only), `assumptions_made`.

---

## Data models

### `StructuredRequirement` (`models/requirement.py`)
Extracted from raw input. Contains `title`, `description`, `actors`, `acceptance_criteria: list[AcceptanceCriterion]`, and `test_scope: TestScope`.

`AcceptanceCriterion` has `id: str` (e.g. `"AC-001"`) and `text: str`. IDs are assigned sequentially by the LLM and are used as keys throughout the traceability layer.

`TestScope` has `in_scope: list[str]` and `out_of_scope: list[str]`. The clarification agent only asks about in-scope items. This boundary prevents requirement expansion.

### `ClarificationQuestion` (`models/clarification.py`)
Fields: `id`, `question`, `context`, `tier: QuestionTier`, `assumption: str | None`, `answer: str | None`.

**Tiers:**
- `BLOCKING` — user must answer; test cases cannot be reliably written without it
- `CLARIFYING` — improves coverage; tests are still writable without the answer
- `ASSUMABLE` — auto-resolved silently using the `assumption` field value

### `ClarificationRound` (`models/clarification.py`)
Contains `questions: list[ClarificationQuestion]` and computed properties:
- `blocking_count`, `clarifying_count`, `assumable_count`
- `completeness_score: float` — deterministic: `1.0 - min(blocking*0.30, 0.60) - min(clarifying*0.10, 0.30)`

`completeness_score` is never delegated to Claude. It is always computed from question counts.

### `TestCase` (`models/test_case.py`)
Fields: `id`, `title`, `type: TestCaseType`, `priority: Priority`, `preconditions`, `steps: list[TestStep]`, `expected_outcome`, `tags`, `linked_criteria: list[str]`.

`linked_criteria` contains AC IDs (e.g. `["AC-001", "AC-003"]`) populated by the LLM. Unknown IDs are silently ignored when building the traceability matrix.

### `TraceabilityMatrix` (`models/traceability.py`)
Built deterministically after generation. Never delegated to Claude.

Fields:
- `coverage: dict[str, list[str]]` — AC ID → list of TC IDs that cover it
- `gaps: list[AcceptanceCriterion]` — ACs with zero coverage (full objects, not just IDs)
- `coverage_pct: float` — percentage of ACs covered by at least one TC

Built via `TraceabilityMatrix.build(requirement, test_cases)`. Unknown AC IDs in `linked_criteria` are ignored (hallucination guard). `gaps` carries full objects so output can show AC text without a separate lookup.

---

## Workflow: clarification loop and stopping logic

The graph flow is: `analyze → clarify → [collect_answers → clarify]* → generate`.

The `clarify` node (`workflow/nodes.py`) sets `clarification_complete` based on these conditions (in order):
1. `not session.latest_round.questions` → no gaps found, stop
2. `blocking_count == 0 and completeness_score >= SCORE_THRESHOLD` → sufficient clarity, stop
3. `len(session.clarification_rounds) >= MAX_CLARIFICATION_ROUNDS` → hard cap reached, stop

The `route_after_clarification` function in `workflow/graph.py` reads `clarification_complete` to route to either `collect_answers` (interrupt) or `generate`.

The `collect_answers` node calls `interrupt(...)`, which pauses the graph and returns control to the HTTP layer. The API sends a response with `status: awaiting_clarification`. When `POST /sessions/{id}/answers` is called, `Command(resume=answers)` resumes the graph.

`_resolve_assumptions` in `nodes.py` auto-fills `answer = assumption` for all `ASSUMABLE` questions after each clarification run. Only `BLOCKING` and `CLARIFYING` questions are surfaced to the user.

After `generate`: `TraceabilityMatrix.build(session.requirement, session.test_cases)` is called in the node and stored in `QAState.traceability_matrix`.

---

## Agent pattern

All agents extend `BaseAgent` (`agents/base_agent.py`).

```python
class BaseAgent(ABC):
    prompt_file: str                          # filename under prompts/

    def _load_prompt(self, **kwargs) -> str   # reads template, fills placeholders
    def _call(self, system, user_message, max_tokens=4096) -> str  # calls Claude
    def _parse_json(self, text) -> any        # strips markdown fences, parses JSON

    @abstractmethod
    def run(self, session: Session) -> None   # each agent implements this
```

Agents are stateless. All context comes in via `session`; all output goes back onto `session`. Never store state on agent instances.

**To add a new agent:**
1. Create `agents/my_agent.py` extending `BaseAgent`
2. Set `prompt_file = "my_prompt.md"`
3. Implement `run(session: Session) -> None`
4. Create `prompts/my_prompt.md` with `{variable}` placeholders
5. Add a node function in `workflow/nodes.py` that builds a `Session`, calls the agent, and returns updated state fields as a dict
6. Wire the node into the graph in `workflow/graph.py`

---

## Claude client and caching

`services/claude_client.py` wraps the Anthropic SDK. The system prompt is always cached with `cache_control: ephemeral`.

```python
def chat(system: str, messages: list[dict], max_tokens: int, model: str = DEFAULT_MODEL) -> str
```

`max_tokens` has no default — callers must be explicit. `TestCaseGenerator` uses `max_tokens=16000` to avoid truncation on large test suites.

---

## Prompt conventions

Templates live in `prompts/*.md`. They use Python's `.format(**kwargs)` for variable substitution.

- Literal braces in JSON schema examples must be escaped: `{{` and `}}`
- Every template ends with `Return only valid JSON. No explanation, no markdown fences.`
- `_parse_json` in `BaseAgent` strips markdown fences defensively regardless

---

## Design principles to preserve

**Deterministic stopping.** `completeness_score` must remain a computed property on `ClarificationRound`, not a Claude-generated field. Do not add an `is_sufficient` flag back.

**Deterministic traceability.** `TraceabilityMatrix` must always be built from `linked_criteria` data, not by asking Claude to assess coverage. The same principle applies: model output is input data, not a decision-making layer.

**Typed contracts.** All data crossing layer boundaries must be a Pydantic model. Do not pass dicts, strings, or untyped structures between agents, orchestrator, and services.

**Bounded scope.** `TestScope.in_scope` is the clarification agent's working boundary. Do not remove it or make the clarification prompt ask about items outside that list.

**Stateless agents.** Agents must not store instance state between calls. If an agent needs data from a previous step, it reads it from `session`.

**Prompt files over inline strings.** Prompt text belongs in `prompts/*.md`, not in agent `run()` methods. This keeps prompt iteration decoupled from code changes.

---

## What is not yet implemented

- `generators/playwright_generator.py` — stub only; raises `NotImplementedError`
- Test case review layer — a validation agent to detect gaps in the generated suite

Do not implement these unless explicitly asked.

---

## Configuration

`config.py` reads from `.env` via `python-dotenv`.

| Constant | Default | Notes |
|---|---|---|
| `DEFAULT_MODEL` | `claude-sonnet-4-6` | Used by all agents unless overridden |
| `MAX_CLARIFICATION_ROUNDS` | `3` | Hard cap; tune in config, not in nodes |
| `SCORE_THRESHOLD` | `0.85` | Minimum completeness score to stop clarification; used in `clarify` node |
| `PROMPTS_DIR` | `Path(__file__).parent / "prompts"` | Absolute, relative to config.py |

Penalty weights live in `ClarificationRound.completeness_score` in `models/clarification.py`.

---

## File layout reference

```
CLAUDE.md                    ← this file (public, tracked)
CLAUDE.local.md              ← local session context (git-ignored)
.docs/architecture.md        ← architecture decisions (git-ignored, in progress)
config.py                    ← DEFAULT_MODEL, MAX_CLARIFICATION_ROUNDS, SCORE_THRESHOLD
main.py                      ← legacy CLI entry point (kept for reference)
requirements.txt
api/
  app.py                     ← FastAPI app, state wiring (graph, store)
  schemas.py                 ← SessionResponse, CreateSessionRequest, SubmitAnswersRequest, *Out
  session_store.py           ← in-memory session registry (set of UUIDs)
  routes/
    sessions.py              ← POST /sessions, POST /sessions/{id}/answers
workflow/
  state.py                   ← QAState TypedDict with operator.add reducer
  nodes.py                   ← analyze, clarify, collect_answers, generate node functions
  graph.py                   ← StateGraph wiring, MemorySaver checkpointer
models/
  __init__.py
  requirement.py             ← StructuredRequirement, AcceptanceCriterion, TestScope
  clarification.py           ← ClarificationQuestion, ClarificationRound, QuestionTier
  test_case.py               ← TestCase, TestStep, Priority, TestCaseType
  traceability.py            ← TraceabilityMatrix
orchestrator/
  session.py                 ← Session dataclass (node-to-agent bridge)
  pipeline.py                ← legacy CLI pipeline (kept for reference)
agents/
  base_agent.py
  requirements_analyst.py
  clarification_agent.py
  test_case_generator.py
prompts/
  requirements_analysis.md
  clarification.md
  test_case_generation.md
services/
  claude_client.py
  output_writer.py
generators/
  base_generator.py
  playwright_generator.py    ← stub
tests/
  unit/                      ← fast, no I/O (TraceabilityMatrix, pipeline logic, etc.)
  contract/                  ← mocked LLM, schema validation
  smoke/                     ← real LLM, schema-only assertions
  evals/                     ← real LLM, quality rubric
output/                      ← generated files (git-ignored)
```
