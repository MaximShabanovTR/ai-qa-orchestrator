# CLAUDE.md — AI QA Orchestrator

This file provides project context for Claude Code sessions. Read it before making any changes.

---

## What this project is

An AI-driven QA orchestration system that takes a plain-text requirement and produces a structured test suite. The system analyzes requirements, runs a tiered clarification loop with the user, then generates test cases covering happy path, edge cases, and negative scenarios.

This is not a chatbot or a generic agent framework. It is a focused, domain-specific QA workflow with deterministic control flow and typed data contracts at every boundary.

---

## Architecture

Five layers. Each has a single responsibility. They communicate only through Pydantic models — no raw dicts, no string passing between layers.

```
orchestrator/pipeline.py
  ├── agents/requirements_analyst.py   → StructuredRequirement
  ├── agents/clarification_agent.py    → ClarificationRound (loop)
  └── agents/test_case_generator.py    → list[TestCase]
        └── services/claude_client.py  → Anthropic SDK
```

| Layer | Location | Responsibility |
|---|---|---|
| Entry | `main.py` | CLI input, pipeline invocation, output writing |
| Orchestration | `orchestrator/` | Pipeline flow, clarification loop, stopping logic |
| Agents | `agents/` | Stateless Claude callers; one per pipeline stage |
| Models | `models/` | Pydantic data contracts between all layers |
| Services | `services/` | Anthropic SDK wrapper, JSON/Markdown serializers |
| Prompts | `prompts/` | Markdown templates with `{placeholder}` variables |
| Generators | `generators/` | Code generation — Playwright stub, not yet implemented |

---

## Session state

`orchestrator/session.py` — a dataclass that travels through the entire pipeline. Every agent receives it, reads what it needs, and writes output back onto it.

```python
@dataclass
class Session:
    raw_input: str                              # original user text
    requirement: StructuredRequirement | None   # set by RequirementsAnalyst
    clarification_rounds: list[ClarificationRound]  # appended each loop iteration
    test_cases: list[TestCase]                  # set by TestCaseGenerator
```

Properties: `latest_round`, `all_answered_questions` (answered only), `assumptions_made`.

---

## Data models

### `StructuredRequirement` (`models/requirement.py`)
Extracted from raw input. Contains `title`, `description`, `actors`, `acceptance_criteria`, and `test_scope: TestScope`.

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
Fields: `id`, `title`, `type: TestCaseType`, `priority: Priority`, `preconditions`, `steps: list[TestStep]`, `expected_outcome`, `tags`.

---

## Pipeline: clarification loop and stopping logic

Located in `orchestrator/pipeline.py`. `SCORE_THRESHOLD = 0.85`.

Each iteration:
1. `ClarificationAgent.run(session)` — appends a new `ClarificationRound`
2. `_resolve_assumptions(round)` — auto-fills `answer = assumption` for all `ASSUMABLE` questions
3. Check stopping conditions (in order):
   - `not latest.questions` → stop (no gaps found)
   - `blocking_count == 0 and completeness_score >= 0.85` → stop
   - `round_num == MAX_CLARIFICATION_ROUNDS` → warn if blocking gaps remain, stop
4. `_collect_answers(round)` — prompts user for `BLOCKING` and `CLARIFYING` questions only

After the loop: print assumptions summary, then run `TestCaseGenerator`.

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
5. Wire it into `orchestrator/pipeline.py`

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

**Typed contracts.** All data crossing layer boundaries must be a Pydantic model. Do not pass dicts, strings, or untyped structures between agents, orchestrator, and services.

**Bounded scope.** `TestScope.in_scope` is the clarification agent's working boundary. Do not remove it or make the clarification prompt ask about items outside that list.

**Stateless agents.** Agents must not store instance state between calls. If an agent needs data from a previous step, it reads it from `session`.

**Prompt files over inline strings.** Prompt text belongs in `prompts/*.md`, not in agent `run()` methods. This keeps prompt iteration decoupled from code changes.

---

## What is not yet implemented

- `generators/playwright_generator.py` — stub only; raises `NotImplementedError`
- FastAPI interface — planned to replace the CLI entry point
- Test case review layer — a validation agent to detect gaps in the generated suite
- Traceability — linking test cases back to acceptance criteria

Do not implement these unless explicitly asked.

---

## Configuration

`config.py` reads from `.env` via `python-dotenv`.

| Constant | Default | Notes |
|---|---|---|
| `DEFAULT_MODEL` | `claude-sonnet-4-6` | Used by all agents unless overridden |
| `MAX_CLARIFICATION_ROUNDS` | `3` | Hard cap; tune in config, not in pipeline |
| `PROMPTS_DIR` | `Path(__file__).parent / "prompts"` | Absolute, relative to config.py |

`SCORE_THRESHOLD = 0.85` lives in `pipeline.py`. Penalty weights live in `ClarificationRound.completeness_score`.

---

## File layout reference

```
CLAUDE.md                    ← this file (public, tracked)
.dev/CLAUDE.local.md         ← local session context (git-ignored)
.docs/architecture.md        ← architecture decisions (git-ignored, in progress)
config.py
main.py
requirements.txt
models/
  __init__.py
  requirement.py             ← StructuredRequirement, TestScope
  clarification.py           ← ClarificationQuestion, ClarificationRound, QuestionTier
  test_case.py               ← TestCase, TestStep, Priority, TestCaseType
orchestrator/
  session.py
  pipeline.py
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
output/                      ← generated files (git-ignored)
```
