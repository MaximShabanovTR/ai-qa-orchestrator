# AI QA Orchestrator

An AI-driven QA workflow system that takes a plain-text requirement and produces a structured, prioritized test suite. Built for learning and evolving toward an enterprise-grade QA automation pipeline.

---

## What it does

1. **Analyzes** a requirement and extracts structured information: actors, acceptance criteria, and explicit test scope boundaries.
2. **Clarifies** gaps through a tiered question loop — blocking gaps require user answers, assumable gaps are resolved silently using industry-standard defaults.
3. **Generates** a comprehensive test suite covering happy path, edge cases, and negative scenarios.
4. **Writes** results to `output/test_cases.json` and `output/test_cases.md`.

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

```
## [HIGH] Successfully subscribe with a standard valid email address
Type: happy_path
Steps:
  1. Type 'testuser@example.com' into the Email field → field displays the address
  2. Click Subscribe → button becomes disabled while processing
  3. Wait for completion → inline message "You have successfully subscribed to the newsletter." is shown

## [HIGH] Submit an email containing a SQL injection attempt
Type: negative
Steps:
  1. Type "'; DROP TABLE subscribers; --@example.com" → text entered into field
  2. Click Subscribe → form submission attempted
  3. Observe inline area → error "Please enter a valid email address." is shown, database unaffected
```

The full run produces ~25 test cases spanning form presence, validation, boundary conditions, error recovery, duplicate handling, and security inputs.

---

## Architecture

The system is organized into five layers. Each layer has a single responsibility and communicates through typed Pydantic contracts.

```
main.py
  └── orchestrator/pipeline.py          # Stage coordinator + clarification loop
        ├── agents/requirements_analyst  # Stage 1: extract structured requirement
        ├── agents/clarification_agent   # Stage 2: identify and tier gaps
        └── agents/test_case_generator   # Stage 3: generate test cases
              └── services/claude_client # Anthropic SDK wrapper (cached)
```

### Layers

| Layer | Location | Responsibility |
|---|---|---|
| Entry point | `main.py` | Collects input, runs pipeline, writes output |
| Orchestration | `orchestrator/` | Pipeline flow, clarification loop, stopping logic |
| Agents | `agents/` | Single-responsibility Claude callers; stateless |
| Models | `models/` | Typed Pydantic contracts between all layers |
| Services | `services/` | Claude SDK wrapper, file output writers |
| Generators | `generators/` | Code generation (Playwright phase — stubbed) |
| Prompts | `prompts/` | Markdown templates loaded at runtime |

### Data flow

```
raw requirement text
        │
        ▼
[RequirementsAnalyst]  →  StructuredRequirement (title, actors, AC, test_scope)
        │
        ▼
[ClarificationAgent]   →  ClarificationRound (questions with tier + assumption)
        │                         │
        │               ASSUMABLE → auto-resolved silently
        │               BLOCKING/CLARIFYING → user prompted
        │
        ▼  (loop until score ≥ 0.85 or MAX_ROUNDS)
        │
        ▼
[TestCaseGenerator]    →  list[TestCase]
        │
        ▼
[output_writer]        →  output/test_cases.json
                           output/test_cases.md
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
├── main.py                          # CLI entry point
├── config.py                        # Env vars, model, constants
├── requirements.txt
├── .env.example
│
├── orchestrator/
│   ├── pipeline.py                  # Stage sequencer + clarification loop
│   └── session.py                   # Mutable run state passed between agents
│
├── agents/
│   ├── base_agent.py                # Abstract: prompt load, Claude call, JSON parse
│   ├── requirements_analyst.py
│   ├── clarification_agent.py
│   └── test_case_generator.py
│
├── models/
│   ├── requirement.py               # StructuredRequirement, TestScope
│   ├── clarification.py             # ClarificationQuestion, ClarificationRound, QuestionTier
│   └── test_case.py                 # TestCase, TestStep, Priority, TestCaseType
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
python main.py
```

Paste your requirement text at the prompt. Enter a blank line when done. The system will analyze, ask any necessary clarification questions, and write the generated test cases to `output/`.

---

## Configuration

All tunable constants live in `config.py`:

| Constant | Default | Purpose |
|---|---|---|
| `DEFAULT_MODEL` | `claude-sonnet-4-6` | Claude model used by all agents |
| `MAX_CLARIFICATION_ROUNDS` | `3` | Hard cap on clarification loop iterations |

The completeness threshold (`0.85`) and penalty weights live in `pipeline.py` and `clarification.py` respectively — adjust them to tune how aggressively the loop exits.

---

## Extending the system

### Adding a new agent

1. Create `agents/my_agent.py` extending `BaseAgent`
2. Set `prompt_file = "my_prompt.md"`
3. Implement `run(session: Session) -> None`
4. Create `prompts/my_prompt.md` with `{placeholder}` variables
5. Call the agent from `pipeline.py`

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
| JSON + Markdown output | Done | `output/test_cases.json`, `output/test_cases.md` |
| Playwright test generation | Planned | Transform `TestCase` models into `.spec.ts` files |
| FastAPI interface | Planned | REST API replacing CLI entry point |
| Test case review layer | Planned | Validation agent to detect gaps in generated suite |
| Traceability | Planned | Link each test case back to its source AC |

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
| Environment | `python-dotenv` |
| Test generation (planned) | Playwright |
| API layer (planned) | FastAPI |
