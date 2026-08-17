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

---

# Stage 4: Automation generation (design — not yet implemented)

Agreed design for the Playwright automation stage. Decisions below are design-time commitments; contracts and names may be refined during implementation, but the boundaries should hold.

**Implementation status:** the schema described below (`AutomationModel` and its nested contracts — `Screen`/`Element`, `Operation`, `DataProfile`, `Scenario`, `Step` and its per-verb payloads, `SuitabilityAssessment`) is implemented in `models/automation.py`, covered by `tests/unit/test_automation_models.py`. Nothing downstream exists yet — no perception agent populates it, no renderer consumes it, no workflow node or graph edge references it. It is a standalone, tested data contract, not yet part of the running system.

**Known gap vs. this design:** the "Model inputs" decision below commits to declarations recording their specific grounding source (AC ids, clarification question ids) for cheap staleness lookups in Stage C. The current schema only has a coarse `GroundingSource.STATED | ASSUMED` flag on `TargetDescriptor` and `DataProfile` — it does not yet link to the specific AC or question id that grounded it. Revisit this before Stage C impact analysis is designed.

---

## Automation stage is design-time only; runtime is postponed

**Decision:** Stage A produces an automation framework as code artifacts. Playwright execution, browser/DOM interaction, and repair loops are postponed to a later stage.

**Why:** Without a live application there is no DOM, no reliable locators, no API contracts, no authentication, no runtime environment, no test data. Execution and repair form a different problem space (runtime AI) with different inputs and failure modes. Building them before the design-time pipeline is mature would couple two unsolved problems.

**Roadmap:**
- **Stage A** — Semantic Automation Model + greenfield automation framework generation
- **Stage B** — framework awareness (`FrameworkInventory` + analyzer for existing codebases)
- **Stage C** — requirement impact analysis + incremental framework updates
- **Stage D** — runtime execution + repair loops

**Stage A investments that keep C/D cheap:** provenance annotations (TC/AC ids) in generated code; the Semantic Automation Model persisted as a first-class artifact (state + disk), never a transient prompt step; `FrameworkInventory` and `RendererConventions` contracts defined now and populated trivially (self-inventory, hardcoded defaults) until Stage B.

**New contracts (all Pydantic):** `AutomationModel`, `AutomationFacts`, `AutomationPlan`, `CodeArtifact`, `FrameworkManifest`, `FrameworkInventory`, `RendererConventions`, plus validation-report and planner-decision analogs of `ReviewReport`/`PlannerDecision`.

---

## Semantic Automation Model + deterministic renderer (no LLM codegen)

**Decision:** Code generation is split in two: `test cases + requirement → (LLM perception) → Semantic Automation Model → (deterministic renderer) → framework files`. The LLM never writes Playwright code.

**Why:** LLMs excel at bridging informal intent to formal structure — that bridge is the requirement→model step, where ambiguity gets resolved. Once the model is fully typed, code emission is compilation: a total, mechanical mapping with exactly one correct output. Using an LLM there adds variance and unaudited decisions to a solved deterministic problem (the project's core principle applied at the point of highest consequence — the deliverable).

**Validator asymmetry (why "LLM codegen + deterministic reviewer" fails):** a design-time reviewer can only check surface properties (syntax, lint, imports, naming). Semantic fidelity — does the code faithfully implement the model? — is verifiable only by execution (postponed) or by a complete model→code spec-checker, which *is* the renderer written in reverse. You would pay the renderer's complexity anyway, plus prompts, retry loops, and residual risk.

**Reproducibility:** deterministic rendering is idempotent — same model, byte-identical output. Stage C (impact analysis, incremental updates) depends on clean diffs; LLM codegen produces gratuitous diffs on every run and kills that stage.

**Scale:** whole-framework LLM output would hit truncation (`TestCaseGenerator` already needs `max_tokens=16000` for ~25 test cases) and cross-file coherence problems. The renderer gets coherence from shared declarations, not from a context window.

**Trade-off:** the renderer is the largest deterministic component in the system, with real up-front template cost — but it is golden-file testable in CI at zero API cost, and bugs are fixed once, not handled probabilistically on every run. Steps outside the model vocabulary render as honest gaps rather than improvised code.

**Deferred:** Stage B (extending an existing framework with arbitrary house style) may justify a constrained LLM pass at the renderer's *edge* (style adaptation of rendered output). Decided then, with real examples — never replacing the deterministic core.

---

## Perception vs policy: the pattern name for every LLM boundary

**Decision:** The LLM extracts structured facts from unstructured input (*perception*); deterministic code makes every decision over those facts (*policy*). This generalizes the project's existing precedents: `linked_criteria` (perception) vs `TraceabilityMatrix.build()` (policy); semantic review findings vs `PlannerDecision.from_report()`.

**Applications in this stage:**

| Decision | Perception (LLM) | Policy (deterministic) |
|---|---|---|
| UI vs API channel | classify test intent | rules over classification + inventory capabilities |
| Reuse vs create Page Object | screen descriptor extraction | descriptor match against inventory |
| New spec vs extend | — | naming/organization convention |
| Fixture reuse | preconditions → capability tags | tag match against fixture inventory |
| Automation suitability | obstacle detection | obstacle → suitability rules |

**Design test for every new feature:** what facts does the LLM extract, and what rules consume them? If the LLM output *is* the decision, the boundary is drawn wrong.

---

## Domain-centric model: declarations + scenarios as typed references

**Decision:** The model is organized around domain declarations, not actions:

```
AutomationModel
├── screens[]          each with an element registry
├── operations[]       API capability descriptors
├── data_profiles[]    symbolic test data definitions
└── scenarios[]        linear step sequences; each step is a typed edge:
                       (verb, element_ref | operation_ref, data_ref?, condition?)
```

Elements, operations, and data are declared once and referenced by ID. Steps are relationships between domain objects; a scenario is a path through the domain graph.

**Why:** deduplication makes Page Object derivation deterministic ("Email field" in TC-001 and TC-007 is provably the same element). Impact analysis operates on declarations (a change touches an element → find referencing scenarios → regenerate exactly those artifacts). Stage B inventory matching is declaration-to-declaration. Action-centric, self-contained scenarios produce duplication and drift instead.

**Targets are semantic element descriptors** — role, accessible name, containing region (accessibility-tree based), never selectors. Framework-neutral by construction (ARIA is a W3C standard) yet renders directly to `get_by_role(...)`, which is Playwright's own best practice.

**Typing rule:** any field the renderer consumes must be an enum or typed structure. A free-text field is either a comment or a hole in determinism. Verify conditions are a closed enum with typed parameters (`VISIBLE`, `CONTAINS_TEXT(text)`, `HAS_VALUE(value)`, `ENABLED`, `DISABLED`, `COUNT(n)`).

**Data profiles:** steps carry either a literal value or a symbolic reference to a declared data profile (`valid_email`, `oversized_string`). Profiles render as typed data factories in the generated framework.

**Discipline rule:** every concept in the model must be consumed by at least one deterministic derivation rule; a concept nothing derives from is decoration, and decoration in a contract is where drift starts. Corollary: verifications stay inline steps (no top-level shared collection) until duplication evidence justifies promotion.

---

## Model scope: admission rule and explicit exclusions

**Admission rule — a step type belongs in the model only if all three hold:**
1. A manual QA engineer would write it as a test step.
2. It describes user-observable behavior, not browser/framework mechanism.
3. It renders to exactly one correct implementation given the conventions.

**Vocabulary:** small closed enums — roughly `Navigate`, `EnterText`, `Activate`, `Select`, `Toggle`, `Verify` (UI family) and `CallOperation`, `VerifyResponse` (API family), plus `Unsupported`. Target: ~90–95% coverage of the generated test-case corpus, measured empirically — not completeness over Playwright.

**Exclusions and where each concern lives instead:**

| Excluded from the model | Home |
|---|---|
| Waits, retries, polling, network-idle | renderer (Playwright auto-waiting) |
| Selectors (CSS/XPath/`nth()`) | renderer, derived from semantic descriptors |
| Browser/context config, parallelism, tracing | generated scaffold (`playwright.config`, `conftest`) |
| Network interception / response mocking | future runtime stage (needs real API shapes) |
| `evaluate()`, script injection, direct cookie/storage manipulation | never in the model; state setup belongs to fixtures (Stage B+) |
| Control flow inside a scenario (if/else, loops, try/except) | forbidden — scenarios are strictly linear; a branching test is two tests |
| Multi-tab/window, popups, iframes, drag-and-drop, gestures | `Unsupported` escape hatch |
| Visual/pixel-diff assertions, a11y/perf audits | out entirely |
| Non-UI assertions (database state, emails sent, downloads) | `Unsupported` — honest gap |
| Auth/session engineering (storage state, token injection) | fixtures layer, Stage B |

**Escape hatch:** `Unsupported(description)` renders as a skipped test carrying the original step text — a visible, countable gap, never a silent omission. It doubles as the measurement instrument for the vocabulary ceiling: escape-hatch frequency data drives verb admission (a new verb gets in when it recurs in real runs *and* passes the admission rule).

**Versioning:** the model carries a `schema_version`; vocabulary grows by deliberate, versioned decision, never by the generator emitting a new verb ad hoc.

---

## Channels: UI, API, and hybrid — channel is derived, bindings are provenance-gated

**Decision:** MVP covers UI, API, and hybrid scenarios. Every verb inherently belongs to one channel family; a scenario's channel (`UI` | `API` | `HYBRID`) is *computed* from its steps, never declared. Hybrid falls out naturally (set up state via API, verify via UI).

**API operation descriptors capture capability, never contract:** `intent`, `logical_inputs` (data profile refs), `expected_outcome_class` (success / rejection / validation error). This is derivable from requirement text ("the user can subscribe" states the capability). Transport details (method, path, payload shape, auth) live in an optional `binding` sub-object with a hard rule: **it may only be populated from information explicitly present in the requirement** — otherwise it stays `None`. The LLM never fills contract gaps with plausible REST conventions.

**Renderer behavior:** the client splits into two layers. `BaseApiClient` provides generic `get`/`post`/`put`/`patch`/`delete` builders, all funnelling into one shared `_request(method, path, **kwargs)` — that single method is the actual stub ("HTTP transport not implemented at design time"), since sending a real request needs a live base URL and auth wiring that don't exist until Stage B fixtures. Per-`Operation` methods on `ApiClient` are **not** all stubs: when `operation.binding` is set, the method is real, deterministic call-construction code (`return self.post("/api/payments", json={...})`) built from the known method/path — it still raises when actually invoked, but only because the shared transport isn't wired up, not because the call itself is unknown. Only operations with `binding is None` raise for their own reason ("contract unknown at generation time"). Test functions are fully real either way — they call client methods and assert on outcome class. The contract-shaped hole is typed, visible, localized to `_request`, and countable as a finding.

**Why:** the UI/API grounding asymmetry is real — UI targets are observations from requirement text; API bindings are assumptions. The model encodes the asymmetry structurally instead of papering over it.

---

## Operation resource grouping + environment-sourced endpoint URLs

**Decision:** `Operation` gains an optional `resource: str | None = None` field. `ApiClientRenderer` groups operations by `resource` into one `{Resource}Endpoint(BaseApiClient)` class per distinct value; operations with `resource is None` stay directly on the root `ApiClient`. `ApiClient` composes named endpoints as attributes (`self.payments = PaymentsEndpoint()`). Each `Endpoint`'s base URL is not stored in the model at all — it's read at runtime from a generated, environment-sourced config (`ENDPOINT_URLS`, keyed by resource name, populated from `os.environ.get(...)`).

**Why grounded by test cases, not requirements:** an `Operation` only exists in the model because some test case's steps call it (`CallOperation`/`VerifyResponse` referencing it) — per the existing "test cases are the sole source of scenarios" rule. `resource` follows the same grounding: it's derived from the test case's own action text (which names the resource being exercised), not the higher-level requirement, consistent with how the operation itself was discovered.

**Why optional:** not every operation will cleanly resolve to a named resource (mirrors why `binding` is optional) — grouping is a bonus organizational signal, not a required one, and ungrouped operations still work correctly on the flat `ApiClient`.

**Why base URL lives in a config file, not the model:** a resource's base URL differs per deployment environment (dev/staging/prod) but its relative path does not — `OperationBinding.path` is already environment-independent model data. Base URL is pure environment configuration, not something extractable from a requirement or test case, so it was never a good fit for `AutomationModel`. Sourcing it from `os.environ` at runtime (rather than baking a `{resource: {env: url}}` structure into a generated file) means switching environments never touches generated code — the same "renderer generates structure, human supplies environment-specific values" pattern already used for `base_url` in `ScaffoldRenderer`'s `conftest.py` fixture, just extended per-resource.

**Trade-off:** this bends "declared not inferred" slightly — nothing forces every real resource to get a `resource` value; a perception step choosing not to populate it degrades gracefully to the flat client, so under-grouping is possible but never produces incorrect code, only a less-organized one.

---

## Typed API request bodies with individual-param method signatures

**Decision:** `ApiClientRenderer` additionally consumes `data_profiles`. For each `logical_inputs` entry with a resolvable `DataProfile`, its `DataCategory` maps to a concrete Python type (`NUMBER→float`, `BOOLEAN→bool`, `TEXT`/`EMAIL`/`URL`/`DATE`/`DATETIME→str`), and each bound operation's method generates a `@dataclass` `{MethodName}Request` with those typed fields — stdlib `dataclasses`, not Pydantic, per the "zero third-party runtime dependencies" decision, which applies here too (Pydantic v2's validation core is a compiled Rust extension, not a pure-Python package — a materially bigger install ask than stdlib in a locked-down environment, and not a hard requirement for the generated tests to run the way `pytest`/`pytest-playwright` are). The method signature itself keeps individual named parameters (`def submit_payment(self, order_id, amount):`) — the request object is constructed *inside* the method, then serialized (`dataclasses.asdict(request)`) for the transport call; callers never construct or see the dataclass type directly.

**Why individual params, not a caller-supplied object:** `CallOperation.inputs: dict[str, DataRef]` is already a flat, named mapping at the model level — `TestRenderer` (Task 11) will render calls directly from that shape. Keyword arguments map onto it with no intermediate step; requiring callers to construct a typed object first would mean `TestRenderer` also has to know how to build and import that object per operation, for no benefit.

**Trade-off vs. Pydantic:** a `@dataclass` documents the expected shape and gives IDE support, but doesn't validate types at construction the way Pydantic would. Accepted because the data flowing into these request objects is already produced by a guaranteed-correct pipeline (`DataRenderer`'s category-derived generators, `DataProfile`'s own literal-value validator) — the narrower remaining risk (a human hand-editing generated test code with a wrong type) doesn't justify the portability cost of a compiled third-party dependency.

**Deferred to TestRenderer:** a "baseline request + scenario-specific overrides" pattern (each scenario only naming what it deviates from) is a good idea but isn't `ApiClientRenderer`'s decision — the model has no declared concept of a canonical/default value per field, only per-scenario `CallOperation.inputs`. Individual-param method signatures are what make this pattern possible later (`client.submit_payment(**{**defaults, **overrides})`), without `ApiClientRenderer` needing to know anything about it now.

---

## Model inputs: test cases own scenarios; the requirement grounds declarations

**Decision:** Model generation consumes both the reviewed test cases and the `StructuredRequirement` (plus answered clarifications), with asymmetric authority:
- **Test cases are the sole source of scenarios.** One scenario per test case; perception may never invent a scenario from requirement text. The reviewed, remediated suite is the only authorized path into generated code.
- **The requirement grounds declarations** — element naming, operation bindings, `TestScope`, AC text for provenance, data facts from clarification answers and assumptions (e.g., "RFC 5321 max length" grounds a data profile).

**Why test-cases-only fails:** the binding provenance rule is unsatisfiable without requirement visibility; `TestScope` enforcement disappears; clarification-answer facts would have to be reconstructed from procedure prose while the typed source sits one field away.

**Contradiction rule:** the requirement may enrich declarations, never contradict procedures. Detected drift between test cases and requirement is surfaced as a finding, not silently resolved.

**Provenance:** declarations record their grounding source (AC ids, clarification question ids) so Stage C's "requirement changed → which declarations are stale?" is a lookup, not an investigation.

**Plumbing cost: zero.** The `Session` bridge already carries `raw_input`, `requirement`, `clarification_rounds`, and `test_cases`.

---

## Content vs architecture: the renderer owns all architecture

**Decision:** The Semantic Automation Model describes *what to test* (content — varies per requirement). All architecture of the generated framework — patterns, OOP structure, naming, directory layout, which base classes/enums/utils exist — is the renderer's fixed, versioned opinion, encoded in templates, derivation rules, and a `RendererConventions` config (hardcoded defaults in MVP).

**Derivation rules (renderer-side):** screen → page class extending `BasePage`; element registry → locator properties; data profile → typed factory/enum; API operation → client method; scenario → test function with provenance annotations.

**Why:** (1) reproducibility — if the model carried architectural choices, the LLM would decide architecture per-run and the clean-diff property dies; (2) uniformity — one opinion applied everywhere is what makes a generated framework feel engineered; (3) independent evolution — improving the architecture means changing templates and re-rendering the *same stored models* (a deterministic migration, zero LLM cost).

**Stage B evolution:** conventions go from constant to variable — the `FrameworkAnalyzer` populates `RendererConventions`/`FrameworkInventory` from an existing codebase, and the renderer consumes them as parameters instead of defaults. The boundary does not move; what flows through it changes.

---

## Renderer is a layer of per-artifact renderers, not a God class

**Decision:**

```
FrameworkRenderer.render(model, conventions) -> FrameworkManifest   ← thin composition root
  ├── ScaffoldRenderer     static templates: config, conftest, base classes (near-zero logic)
  ├── PageObjectRenderer   screens → page classes
  ├── ApiClientRenderer    operations → client interface + stubs
  ├── DataRenderer         profiles → factories / enums
  └── TestRenderer         scenarios → test functions
```

Each artifact renderer is a pure function `(model slice, conventions) → list[CodeArtifact]`, independently golden-file-testable. Shared tier: `RendererConventions` (data) + emit primitives (imports, naming, provenance annotations). Same decomposition move as `ReviewReport._check_*`.

**Output:** `FrameworkManifest` — every generated artifact with path, kind, and provenance (TC/AC ids). The manifest *is* the MVP self-inventory and the seed of Stage B's `FrameworkInventory`.

**Framework is the unit of generation:** output is a maintainable project (`pages/`, `tests/`, `api/`, `fixtures/`, `utils/`, config), not loose spec files. Render target: **Python + pytest + playwright-python** (one language across the project; pytest fixtures map onto the fixtures concept).

**Guardrail:** modules with a common signature, full stop — no renderer plugin registry, no abstract factories, no dynamic discovery.

---

## Generated framework has zero third-party runtime dependencies

**Decision:** Renderer output may import only `pytest`, `pytest-playwright`, and the Python standard library — never a third-party package such as `Faker`. This applies to every artifact renderer, but is most consequential for `DataRenderer`'s constraint-driven generators (`random`/`string`/`datetime` only).

**Why:** the generated framework runs on whatever machine the end QA team has, frequently a locked-down corporate VDI with no outbound package-index access or an approval process for new dependencies. A generated automation project that fails `pip install` is worse than one with less realistic test data. This is a stronger bar than "avoid unnecessary dependencies" in the orchestrator's own `requirements.txt` — it is a hard constraint on code handed to someone else's environment, not a style preference for this codebase.

**Consequence for `DataCategory` generation:** `NUMBER`, `BOOLEAN`, and unconstrained-length `TEXT` are trivially stdlib (`random`). `EMAIL`/`URL`/`DATE`/`DATETIME` don't actually need Faker's realism either — test data only needs to be syntactically valid for its category, not naturalistic, so a synthetic stdlib value (e.g. `f"user{random.randint(...)}@example.com"`) is sufficient. The one case stdlib genuinely cannot cover honestly is `TEXT` with a `pattern` constraint — matching an arbitrary regex is a real algorithmic gap, not a missing-dependency problem, so it renders as an honest gap (`source="unsupported"`) rather than an ad hoc partial implementation. `DataCategory.UNSUPPORTED` is the same tier by definition.

**Trade-off:** this costs generation coverage, not correctness — the model already has the vocabulary (`source="unsupported"`) to express "cannot generate this" honestly rather than silently degrading. Revisit only if telemetry shows `pattern`-constrained profiles are common enough to justify a dependency, and even then the choice belongs to whoever owns the target deployment environment, not the renderer.

---

## Automation Planner: bounded fact-gathering agent + deterministic plan

**Decision:** Planning splits in two:
1. **Agentic fact-gathering (bounded):** an LLM-driven loop fills a typed `AutomationFacts` object (per-TC channel classification, screen descriptors, fixture needs, inventory matches, obstacles) by choosing among typed tools. Terminates on a deterministic completeness check over `AutomationFacts` or a hard iteration cap — same philosophy as the clarification loop's stopping logic.
2. **Deterministic plan assembly:** `AutomationPlan.build(facts, inventory)` — a pure classmethod in the `PlannerDecision` mold — makes every actual decision (channel, target files, reuse vs create, fixture binding).

**Why agency there and only there:** tool needs genuinely vary per input (an unambiguous test case needs no classifier call; a greenfield run makes inventory lookups pointless) — real conditionals. A fixed tool chain would be a pipeline wearing an agent costume: latency and nondeterminism paid for no decision value. Decisions stay deterministic per perception/policy.

**Graph rule:** the graph orchestrates stages; an agent may orchestrate *within* a stage but must emerge with a typed artifact and typed status. Model generation and validation are graph nodes, not planner tools — folding them into the planner would create a god-node and forfeit LangGraph checkpointing, resumability, and the validated review→plan→generate loop shape.

**`BaseTool` (minimal, no registry):** `name`, `description` (needed for LLM tool selection), typed Pydantic input model, typed output model, `run(input) -> output`. Determinism is a **declared per-tool property** (`deterministic: bool`), not an assumption of the interface — perception tools wrap LLM calls behind the same interface, and the flag becomes audit metadata on gathered facts. A registry (discovery, permissions) is deferred until more than one agent shares tools.

---

## Automation suitability: typed obstacles, derived classes, no numeric confidence

**Decision:** Suitability enters the model as typed facts with the perception/policy split applied:
- **Perception:** detect *obstacles* from scenario content — closed enum: `CAPTCHA`, `OTP_SECOND_FACTOR`, `EXTERNAL_PAYMENT`, `HARDWARE_INTERACTION`, `VISUAL_JUDGMENT`, `EXTERNAL_SYSTEM_VERIFICATION`. Gathered during planner fact-gathering.
- **Policy:** a rules table maps obstacles → suitability class (`AUTOMATED` | `AUTOMATED_WITH_PREREQS` | `MANUAL`) and typed prerequisites (`PAYMENT_SANDBOX`, `OTP_TEST_HOOK`, `CAPTCHA_BYPASS_TOKEN`). The LLM never assigns suitability directly — it reports what it saw; rules decide what it means.

**Renderer behavior:** `MANUAL` scenarios render as skipped tests with reason + provenance — the framework carries a visible, greppable manual-test register instead of silently shrinking. `AUTOMATED_WITH_PREREQS` renders the real test plus explicitly stubbed prerequisite fixtures. Nothing unautomatable is dropped; everything is accounted for.

**Why no confidence float:** an LLM-emitted `0.7` is unfalsifiable — nobody can say why it isn't `0.6`, so nobody can act on it or tune it. Discrete obstacles and counted assumptions (stub bindings, low-confidence locators) carry the same information in auditable form; any scalar is derived deterministically from those counts.

**Locator honesty:** without a live DOM, locators are educated guesses. Semantic descriptors carry a confidence marker; low-confidence locators surface as advisory findings. Stage D execution is what eventually grounds them — pretending design-time locators are reliable would be self-deception.

---

## Controlled LLM rendering fallback for unsupported interactions (deferred past Stage A)

**Decision:** For steps outside the model vocabulary (canvas interactions, signature pads, custom widgets), a constrained LLM fallback may generate the implementation of a *single interaction* instead of rendering a bare `fixme`. The deterministic renderer still handles the entire common path; the fallback is invoked only for `Unsupported` steps. **Not built in Stage A** — the MVP renders `fixme`, but the renderer is designed with the socket from day one.

**Why this survives the arguments against full LLM codegen:** the claim attached to the code changes. Deterministic output claims *correct by construction*; a fallback snippet claims *draft, requires human validation* — and is tagged as such. A guarantee is not undermined by an artifact that explicitly declares it does not carry that guarantee. The honest baseline comparison is not fallback-vs-renderer (the renderer cannot render these steps by definition) but fallback-vs-human-filling-the-fixme — and "LLM drafts, review gates" is the project's founding pattern (`TestCaseGenerator` → `ReviewAgent`) at smaller granularity.

**Containment is structural, not prompt-based (the decisive condition):**
- **Socket and plug:** the deterministic renderer emits everything — page class, method signature, test function, imports, provenance — except one method *body* with a fixed signature. The LLM fills the hole; it never sees "generate code for this test."
- **AST validation on the way in:** import allowlist, no new classes, no file I/O, no fixture declarations, bounded length. Rejected snippet → fall back to `fixme`. Unlike semantic fidelity, containment *is* deterministically checkable — that is the difference between this and full LLM codegen.

**Reproducibility mitigation:** a content-addressed snippet cache persisted alongside the model — key = hash(step description + socket signature + renderer version). Re-rendering reuses cached snippets byte-for-byte; a snippet regenerates only when its inputs change. This preserves the clean-diff property Stage C depends on.

**Three-tier claim hierarchy in the manifest:** every code region is tagged **deterministic** (correct by construction), **AI-drafted** (contained, awaiting human validation), or **unsupported** (honest gap, skipped). Artifacts must never silently migrate between tiers — `CodeArtifact`/`FrameworkManifest` carry a per-region `source` field from Stage A onward, mirroring `ReviewFinding.source`.

**Primary risk — classification drift:** once the escape hatch produces working-looking code instead of a visible `fixme`, the perception layer's path of least resistance shifts toward classifying borderline steps as `Unsupported`. Guards: the perception prompt requires vocabulary-first mapping; escape-hatch rate is a monitored metric; crossing a configured threshold raises an advisory finding (`HIGH_UNSUPPORTED_RATE`, same mold as `LOW_COVERAGE`).

**Vocabulary promotion refinement:** fallback telemetry drives verb admission, but promotion requires frequency *and* the admission rule. Frequent interactions that cannot be deterministically rendered from a semantic description (e.g., freeform canvas drawing) stay in the fallback permanently — that is correct behavior, not a gap.

**Why deferred:** the fallback is an optimization of the escape hatch, and its guardrails (AST validator, snippet cache, rate finding) are real components. Building containment infrastructure before escape-hatch telemetry shows the contained thing occurs often enough to matter is speculative work. Stage A's cheap dead-end prevention: unsupported steps render as a delegated hole-with-fixed-signature (whose MVP filling is a `fixme` body), so adding the fallback later means "add a plug supplier," not "rearchitect the renderer." This is the concrete form of the previously reserved seam — "a constrained LLM pass at the renderer's edge."
