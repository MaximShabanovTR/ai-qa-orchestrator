# AI QA Orchestrator

An AI-driven QA workflow system that takes a plain-text requirement and produces a structured, prioritized test suite. Built for learning and evolving toward an enterprise-grade QA automation pipeline.

---

## What it does

1. **Analyzes** a requirement and extracts structured information: actors, acceptance criteria (with sequential IDs), and explicit test scope boundaries.
2. **Clarifies** gaps through a tiered question loop — blocking gaps require user answers, assumable gaps are resolved silently using industry-standard defaults.
3. **Generates** a comprehensive test suite covering happy path, edge cases, and negative scenarios, with each test case linked to the acceptance criteria it covers.
4. **Traces** coverage: builds a deterministic traceability matrix showing which ACs are covered, by which test cases, and which remain uncovered.
5. **Writes** results to `output/test_cases.json`, `output/test_cases.md` (with inline traceability table), and `output/session.json`.

The system is designed around a QA-first philosophy: AI outputs are treated as probabilistic, not ground truth. Scope is bounded explicitly to prevent requirement expansion. Stopping logic is deterministic, not delegated to the model.

---

## Example output

Input requirement:
```
Newsletter subscription form with an Email field and a Subscribe button.
On success, show inline message: "You have successfully subscribed to the newsletter."
On invalid email, show: "Please enter a valid email address."
On empty field, show: "Email is required."
On duplicate, show: "This email is already subscribed."
The Subscribe button should be disabled during processing.
```

Generated output (excerpt from `output/test_cases.md`):

```markdown
## TC-001 · [HIGH] Successfully subscribe with a standard valid email address
**Type:** happy_path
**Steps:**
1. Type 'testuser@example.com' into the Email field
   _Expected: field displays the address_
2. Click Subscribe
   _Expected: button becomes disabled while processing_
3. Wait for completion
   _Expected: inline message "You have successfully subscribed to the newsletter." is shown_
**Covers:** AC-001, AC-004

## TC-012 · [HIGH] Submit an email containing a SQL injection attempt
**Type:** negative
**Steps:**
1. Type "'; DROP TABLE subscribers; --@example.com" into the Email field
   _Expected: text entered into field_
2. Click Subscribe
   _Expected: error "Please enter a valid email address." is shown, database unaffected_
**Covers:** AC-003

# Traceability Matrix

**Coverage:** 100.0%

| ID | Acceptance Criterion | Test Cases |
|---|---|---|
| AC-001 | Email field is present on the form | TC-001, TC-002 |
| AC-003 | Invalid email shows inline error | TC-005, TC-012, TC-018 |
```

The full run produces ~25 test cases spanning form presence, validation, boundary conditions, error recovery, duplicate handling, and security inputs.

---

## Architecture

The system is organized into six layers. Each layer has a single responsibility and communicates through typed Pydantic contracts.

```
api/app.py (FastAPI)
  └── workflow/graph.py (LangGraph StateGraph)
        ├── workflow/nodes.py: analyze    → agents/requirements_analyst
        ├── workflow/nodes.py: clarify    → agents/clarification_agent
        ├── workflow/nodes.py: collect_answers  (HTTP interrupt/resume)
        └── workflow/nodes.py: generate   → agents/test_case_generator
              └── services/claude_client  # Anthropic SDK wrapper (cached)
```

### Layers

| Layer | Location | Responsibility |
|---|---|---|
| API | `api/` | FastAPI routes, request/response schemas, session registry |
| Workflow | `workflow/` | LangGraph graph, node functions, QAState definition |
| Orchestration | `orchestrator/` | Session dataclass shared between nodes and agents |
| Agents | `agents/` | Single-responsibility Claude callers; stateless |
| Models | `models/` | Typed Pydantic contracts between all layers |
| Services | `services/` | Claude SDK wrapper, file output writers |
| Generators | `generators/` | Code generation (Playwright phase — stubbed) |
| Prompts | `prompts/` | Markdown templates loaded at runtime |

### Data flow

```
POST /sessions  { requirement: "..." }
        │
        ▼
[analyze node]         →  StructuredRequirement (title, actors, AC-001…AC-N, test_scope)
        │
        ▼
[clarify node]         →  ClarificationRound (questions with tier + assumption)
        │                         │
        │               ASSUMABLE → auto-resolved silently in node
        │               BLOCKING/CLARIFYING → graph interrupted, HTTP response sent
        │
        ▼  POST /sessions/{id}/answers  { answers: { q-id: "answer" } }
        │
        ▼  (loop until score ≥ 0.85 or MAX_ROUNDS)
        │
        ▼
[generate node]        →  list[TestCase]  (each TC has linked_criteria: [AC-ids])
        │
        ▼
[TraceabilityMatrix]   →  coverage dict + gaps + coverage_pct  (computed, not LLM)
        │
        ▼
SessionResponse { status: COMPLETE, test_cases: [...], traceability: {...} }
```

---

## Clarification tiering

The clarification loop classifies every identified gap into one of three tiers:

| Tier | Behavior | Example |
|---|---|---|
| `BLOCKING` | User must answer — test cases cannot be reliably written without this | Lockout threshold, session expiration behavior |
| `CLARIFYING` | User is asked — improves coverage but tests are still writable | Exact error message wording, UX behavior on re-submit |
| `ASSUMABLE` | Auto-resolved silently using industry-standard defaults | HTTP 401 for invalid credentials, RFC 5321 email max length |

### Stopping logic

The loop exits when any of these conditions is met:

1. Claude returns an empty questions list — no gaps found
2. `blocking_count == 0` AND `completeness_score >= 0.85`
3. `MAX_CLARIFICATION_ROUNDS` reached (warns if blocking gaps remain)

`completeness_score` is computed deterministically from question counts — not delegated to Claude:

```python
score = 1.0 - min(blocking_count * 0.30, 0.60) - min(clarifying_count * 0.10, 0.30)
```

This removes the LLM-as-judge-of-itself feedback loop and makes the stopping decision auditable and tunable.

---

## Project structure

```
ai-qa-orchestrator/
│
├── main.py                          # Legacy CLI entry point (kept for reference)
├── config.py                        # Env vars, model, constants (SCORE_THRESHOLD, MAX_ROUNDS)
├── requirements.txt
├── .env.example
│
├── api/
│   ├── app.py                       # FastAPI app + state wiring (graph, store)
│   ├── schemas.py                   # Request/response Pydantic models
│   ├── session_store.py             # In-memory session registry (set of UUIDs)
│   └── routes/
│       └── sessions.py              # POST /sessions, POST /sessions/{id}/answers
│
├── workflow/
│   ├── state.py                     # QAState TypedDict (LangGraph shared state)
│   ├── nodes.py                     # Node functions: analyze, clarify, collect_answers, generate
│   └── graph.py                     # StateGraph wiring + MemorySaver checkpointer
│
├── orchestrator/
│   ├── pipeline.py                  # Legacy CLI pipeline (kept for reference)
│   └── session.py                   # Session dataclass — bridge between nodes and agents
│
├── agents/
│   ├── base_agent.py                # Abstract: prompt load, Claude call, JSON parse
│   ├── requirements_analyst.py
│   ├── clarification_agent.py
│   └── test_case_generator.py
│
├── models/
│   ├── requirement.py               # StructuredRequirement, AcceptanceCriterion, TestScope
│   ├── clarification.py             # ClarificationQuestion, ClarificationRound, QuestionTier
│   ├── test_case.py                 # TestCase, TestStep, Priority, TestCaseType
│   └── traceability.py              # TraceabilityMatrix
│
├── prompts/
│   ├── requirements_analysis.md
│   ├── clarification.md
│   └── test_case_generation.md
│
├── services/
│   ├── claude_client.py             # Anthropic SDK + ephemeral prompt caching
│   └── output_writer.py             # JSON and Markdown serializers
│
├── generators/
│   ├── base_generator.py            # Abstract: test cases → runnable files
│   └── playwright_generator.py      # Playwright/TypeScript (stub)
│
└── output/                          # Generated test cases (git-ignored)
```

---

## Getting started

### Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/)

### Setup

```bash
# Clone and enter the project
git clone <repo-url>
cd ai-qa-orchestrator

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=your_key_here
```

### Run

```bash
uvicorn api.app:app --reload
```

The API is now available at `http://localhost:8000`. See the two endpoints below.

**Start a session:**
```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"requirement": "Newsletter subscription form with email field..."}'
```

Returns either `status: awaiting_clarification` (with questions) or `status: complete` (with test cases).

**Submit answers:**
```bash
curl -X POST http://localhost:8000/sessions/{session_id}/answers \
  -H "Content-Type: application/json" \
  -d '{"answers": {"Q-001": "Yes, lockout after 5 attempts"}}'
```

Returns the same unified `SessionResponse` — repeat until `status: complete`.

---

## Configuration

All tunable constants live in `config.py`:

| Constant | Default | Purpose |
|---|---|---|
| `DEFAULT_MODEL` | `claude-sonnet-4-6` | Claude model used by all agents |
| `MAX_CLARIFICATION_ROUNDS` | `3` | Hard cap on clarification loop iterations |
| `SCORE_THRESHOLD` | `0.85` | Minimum completeness score to exit clarification without all answers |

Penalty weights live in `ClarificationRound.completeness_score` in `models/clarification.py`.

---

## Extending the system

### Adding a new agent

1. Create `agents/my_agent.py` extending `BaseAgent`
2. Set `prompt_file = "my_prompt.md"`
3. Implement `run(session: Session) -> None`
4. Create `prompts/my_prompt.md` with `{placeholder}` variables
5. Add a node function in `workflow/nodes.py` that constructs a `Session`, calls the agent, and returns updated state fields
6. Wire the node into the graph in `workflow/graph.py`

### Adding a new output format

1. Create `generators/my_generator.py` extending `BaseGenerator`
2. Implement `generate(test_cases, output_dir) -> list[Path]`

---

## Roadmap

| Phase | Status | Description |
|---|---|---|
| Requirements analysis | Done | Structured extraction with explicit test scope |
| Tiered clarification loop | Done | BLOCKING / CLARIFYING / ASSUMABLE question tiers |
| Test case generation | Done | Happy path, edge cases, negative scenarios |
| Traceability matrix | Done | AC coverage map, gap detection, coverage % |
| JSON + Markdown output | Done | `test_cases.json`, `test_cases.md`, `session.json` |
| LangGraph workflow | Done | Interrupt/resume graph replacing sequential pipeline |
| FastAPI interface | Done | Two-endpoint REST API with unified `SessionResponse` |
| Test case review layer | Planned | Validation agent to detect gaps in generated suite |
| Playwright test generation | Planned | Transform `TestCase` models into `.spec.ts` files |

---

## Design principles

- **Deterministic stopping** — the clarification loop exits based on computed scores, not model self-assessment
- **Typed contracts** — all inter-layer data is Pydantic; no raw dicts passed between agents
- **Prompt as code** — templates live in `.md` files, iterable without touching agent logic
- **Bounded scope** — `TestScope.in_scope` / `out_of_scope` prevents the model from expanding requirements
- **Explicit caching** — system prompts use `cache_control: ephemeral` to reduce latency and cost on repeated calls
- **Single responsibility** — each agent has one job; the pipeline owns flow control

---

## Tech stack

| Concern | Library |
|---|---|
| AI | Anthropic Claude (`anthropic` SDK) |
| Data validation | Pydantic v2 |
| Workflow orchestration | LangGraph |
| API layer | FastAPI + Uvicorn |
| Environment | `python-dotenv` |
| Test generation (planned) | Playwright |
