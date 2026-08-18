from typing import Any, Callable

from models.automation import DataProfile, Element, Operation, Scenario, Screen, SuitabilityClass
from renderer.api_client_renderer import method_name
from renderer.data_renderer import constant_name, generator_name
from renderer.models import ArtifactKind, CodeArtifact, RendererConventions
from renderer.naming import slugify
from renderer.page_object_renderer import class_name as page_class_name
from renderer.transitions import derive_transitions, element_screen_map, step_screen_id

_API_STEP_VERBS = ("call_operation", "verify_response")


def render_tests(
    scenarios: list[Scenario],
    screens: list[Screen],
    operations: list[Operation],
    data_profiles: list[DataProfile],
    conventions: RendererConventions,
) -> list[CodeArtifact]:
    if not scenarios:
        return []

    screens_by_id = {screen.id: screen for screen in screens}
    element_by_id = {
        element.id: element for screen in screens for element in screen.elements
    }
    element_screen = element_screen_map(screens)
    profiles_by_id = {profile.id: profile for profile in data_profiles}
    operations_by_id = {operation.id: operation for operation in operations}
    transitions = derive_transitions(screens, scenarios)

    start_screens: dict[str, str] = {}
    navigate_screen_ids: set[str] = set()
    uses_profiles = False
    uses_verify = False
    uses_api = False
    for scenario in scenarios:
        for step in scenario.steps:
            if step.verb in ("enter_text", "select") and step.data.kind == "profile_ref":
                uses_profiles = True
            if step.verb == "call_operation" and any(
                value.kind == "profile_ref" for value in step.inputs.values()
            ):
                uses_profiles = True
            if step.verb == "verify":
                uses_verify = True
            if step.verb in _API_STEP_VERBS:
                uses_api = True
            if step.verb == "navigate":
                navigate_screen_ids.add(step.screen_ref)
            sid = step_screen_id(step, element_screen)
            if sid is not None and scenario.id not in start_screens:
                start_screens[scenario.id] = sid

    # Every screen a Navigate step resolves to needs its page class imported
    # at module scope, not just each scenario's opening screen - a
    # mid-scenario Navigate instantiates its target class directly (see
    # _render_step's navigate branch), same as the opening-navigate setup
    # code does.
    used_screen_ids = sorted({sid for sid in start_screens.values()} | navigate_screen_ids)
    lines = ["import pytest", ""]
    if uses_verify:
        lines.append("from playwright.sync_api import expect")
    if uses_profiles:
        lines.append(f"from {conventions.data_dir} import profiles")
    if uses_api:
        lines.append(f"from {conventions.api_dir}.client import ApiClient")
    for screen_id in used_screen_ids:
        screen = screens_by_id[screen_id]
        # slugify(screen.id), not the raw id - a screen id like "SCR-001"
        # (the model's own documented convention) contains a hyphen, which
        # is invalid in a Python import path segment. PageObjectRenderer
        # slugifies identically for the actual pages/{...}.py filename, so
        # the two sides agree without needing to coordinate live.
        lines.append(
            f"from {conventions.pages_dir}.{slugify(screen.id)} import {page_class_name(screen)}"
        )
    lines.extend(["", ""])

    for scenario in scenarios:
        lines.extend(
            _render_test_function(
                scenario,
                start_screens.get(scenario.id),
                screens_by_id,
                element_by_id,
                profiles_by_id,
                operations_by_id,
                transitions,
                element_screen,
            )
        )

    content = "\n".join(lines) + "\n"
    return [
        CodeArtifact(
            path=f"{conventions.tests_dir}/__init__.py",
            content="",
            kind=ArtifactKind.TEST,
        ),
        CodeArtifact(
            path=f"{conventions.tests_dir}/test_scenarios.py",
            content=content,
            kind=ArtifactKind.TEST,
            provenance=[scenario.id for scenario in scenarios],
        )
    ]


def resolve_data_ref(data_ref, profiles_by_id: dict[str, DataProfile]) -> str:
    if data_ref.kind == "literal":
        return repr(data_ref.value)
    profile = profiles_by_id[data_ref.profile_id]
    if profile.literal_value is not None:
        return f"profiles.{constant_name(profile)}"
    return f"profiles.{generator_name(profile)}()"


def _transition_target(
    current_screen_id: str | None,
    next_step,
    element_screen: dict[str, str],
    transitions: dict[str, dict[str, str]],
) -> str | None:
    """If *this scenario's own next step* resolves to a screen different
    from `current_screen_id`, and PageObjectRenderer generated a go_to_*
    method for that specific (from, to) pair, return the target screen id.
    Otherwise None - render a plain click, no screen change.

    Deliberately per-scenario, not a lookup keyed by element identity alone
    against the aggregated `transitions` map. That map is built by scanning
    every scenario in the corpus and keeps only the first-encountered
    triggering element per (from, to) edge (see derive_transitions in
    transitions.py) - it answers "does some transition exist from this
    screen via this element anywhere in the corpus?", not "does activating
    this element in *this* scenario, right now, actually change screens?".

    Two scenarios can both activate the same element (e.g. a "Submit"
    button on a login screen): a happy-path scenario where it navigates to
    a dashboard, and a negative scenario (invalid credentials) where the
    next step is a Verify against an error message on the *same* screen.
    Looking the element up in the aggregate map alone would incorrectly
    treat the negative scenario's click as a transition too (it would
    reuse whichever screen the happy-path scenario registered), corrupting
    current_screen_id for every step that follows in that scenario. Using
    this scenario's own steps[i+1] avoids that: the transition/plain-click
    decision is always grounded in what actually happens next *here*.

    The aggregate `transitions` map is still consulted, but only to confirm
    PageObjectRenderer actually generated a go_to_* method for this exact
    (from, to) pair (its method name is derived purely from the target
    screen's name - see page_object_renderer._render_transition_method -
    so no element identity is needed from the map itself).
    """
    if current_screen_id is None or next_step is None:
        return None
    next_screen_id = step_screen_id(next_step, element_screen)
    if next_screen_id is None or next_screen_id == current_screen_id:
        return None
    if next_screen_id not in transitions.get(current_screen_id, {}):
        return None
    return next_screen_id


def _dedupe_step_inputs(inputs: dict[str, Any]) -> list[tuple[str, Any]]:
    """Collapse a call_operation step's inputs to one entry per slugified
    name, keeping the first occurrence.

    Two distinct dict keys that slugify to the same identifier (e.g.
    "Order ID" and "order-id" both -> order_id) would otherwise render as
    `api.foo(order_id=X, order_id=Y)` - a duplicate-keyword `SyntaxError`
    caught only by compile(), not ast.parse(). This mirrors
    api_client_renderer._dedupe_logical_inputs's rationale exactly (same
    problem, same first-occurrence-wins resolution), but is a local copy
    rather than a shared import: api_client_renderer.py is owned by a
    concurrently-running agent this run. Duplicating this small helper
    across the two files is a reasonable-for-now tradeoff; extracting a
    shared version into renderer/naming.py would be worth doing in a
    follow-up pass once both files are stable again.
    """
    seen: set[str] = set()
    deduped: list[tuple[str, Any]] = []
    for name, value in inputs.items():
        slug = slugify(name)
        if slug in seen:
            continue
        seen.add(slug)
        deduped.append((name, value))
    return deduped


def _operation_call_expr(operation: Operation) -> str:
    if operation.resource is None:
        return f"api.{method_name(operation)}"
    return f"api.{slugify(operation.resource)}.{method_name(operation)}"


# kind -> render an `expect(locator).to_...()` call tail from the condition.
# Exhaustive over VerifyCondition's discriminated union; an unhandled kind
# must raise, never silently skip - same discipline as page_object_renderer's
# _ARIA_ROLES/_TEXT_MATCHED_ROLES and data_renderer's _GENERATORS.
_VERIFY_CONDITION_RENDERERS: dict[str, Callable[[Any], str]] = {
    "visible": lambda c: "to_be_visible()",
    "contains_text": lambda c: f"to_contain_text({c.text!r})",
    "has_value": lambda c: f"to_have_value({c.value!r})",
    "enabled": lambda c: "to_be_enabled()",
    "disabled": lambda c: "to_be_disabled()",
    "count": lambda c: f"to_have_count({c.count!r})",
}

# StatusClass.status_class -> the HTTP status-code // 100 bucket it asserts.
_STATUS_CLASS_DIVISORS: dict[str, int] = {
    "success": 2,
    "client_error": 4,
    "server_error": 5,
}

# kind -> render a boolean expression asserted against the `response`
# variable set by the preceding call_operation step. Exhaustive over
# ResponseCondition's discriminated union; an unhandled kind must raise.
_RESPONSE_CONDITION_RENDERERS: dict[str, Callable[[Any], str]] = {
    "status_class": lambda c: (
        f"response.status_code // 100 == {_STATUS_CLASS_DIVISORS[c.status_class]}"
    ),
    "body_contains": lambda c: f"response.json()[{c.field!r}] == {c.value!r}",
    "header_equals": lambda c: f"response.headers[{c.header!r}] == {c.value!r}",
}


def _render_test_function(
    scenario: Scenario,
    start_screen_id: str | None,
    screens_by_id: dict[str, Screen],
    element_by_id: dict[str, Element],
    profiles_by_id: dict[str, DataProfile],
    operations_by_id: dict[str, Operation],
    transitions: dict[str, dict[str, str]],
    element_screen: dict[str, str],
) -> list[str]:
    func_name = f"test_{slugify(scenario.test_case_id)}"
    lines = [f"# Scenario: {scenario.id} | Test Case: {scenario.test_case_id}"]

    unsupported_steps = [step for step in scenario.steps if step.verb == "unsupported"]
    if unsupported_steps:
        # Per architecture.md's "Model scope" escape hatch: an Unsupported
        # step makes the *whole* scenario un-renderable - a visible,
        # countable gap, never a silent partial render around it. repr()
        # (not an f-string interpolation, unlike the MANUAL branch below
        # whose reason text is always safe enum values) because
        # `description` is free text that may itself contain quotes.
        descriptions = "; ".join(step.description for step in unsupported_steps)
        reason = repr(f"Unsupported: {descriptions}")
        lines.extend(
            [
                f"@pytest.mark.skip(reason={reason})",
                f"def {func_name}(page, base_url):",
                "    pass",
                "",
                "",
            ]
        )
        return lines

    if scenario.suitability.suitability_class == SuitabilityClass.MANUAL:
        reason = ", ".join(o.value for o in scenario.obstacles)
        lines.extend(
            [
                f'@pytest.mark.skip(reason="Manual: {reason}")',
                f"def {func_name}(page, base_url):",
                "    pass",
                "",
                "",
            ]
        )
        return lines

    if scenario.suitability.suitability_class == SuitabilityClass.AUTOMATED_WITH_PREREQS:
        prereqs = ", ".join(p.value for p in scenario.suitability.prerequisites)
        lines.append(f"# Prerequisites: {prereqs}")

    lines.append(f"def {func_name}(page, base_url):")
    body_start = len(lines)

    current_screen_id = start_screen_id
    if current_screen_id is not None:
        screen = screens_by_id[current_screen_id]
        lines.append(f"    page_obj = {page_class_name(screen)}(page, base_url)")
        if screen.path is not None:
            lines.append(f"    page_obj.navigate({screen.path!r})")
        else:
            lines.append(
                f'    raise NotImplementedError('
                f'"no path declared for screen {screen.id} - cannot navigate at design time")'
            )
            lines.append("")
            lines.append("")
            return lines

    if any(step.verb in _API_STEP_VERBS for step in scenario.steps):
        lines.append("    api = ApiClient()")

    for i, step in enumerate(scenario.steps):
        next_step = scenario.steps[i + 1] if i + 1 < len(scenario.steps) else None
        step_lines, current_screen_id = _render_step(
            step,
            next_step,
            current_screen_id,
            screens_by_id,
            element_by_id,
            profiles_by_id,
            operations_by_id,
            transitions,
            element_screen,
        )
        lines.extend(step_lines)

    if len(lines) == body_start:
        lines.append("    pass")

    lines.append("")
    lines.append("")
    return lines


def _render_step(
    step,
    next_step,
    current_screen_id: str | None,
    screens_by_id: dict[str, Screen],
    element_by_id: dict[str, Element],
    profiles_by_id: dict[str, DataProfile],
    operations_by_id: dict[str, Operation],
    transitions: dict[str, dict[str, str]],
    element_screen: dict[str, str],
) -> tuple[list[str], str | None]:
    if step.verb == "navigate":
        if step.screen_ref == current_screen_id:
            # Either the scenario's opening Navigate (already rendered by
            # _render_test_function's setup block: instantiate + navigate),
            # or a redundant re-navigate to the screen we're already on
            # (e.g. immediately after an `activate` transition already put
            # us here - see _transition_target). Either way there's
            # nothing new to emit; page_obj already points at the right
            # class.
            return [], step.screen_ref
        # A genuine mid-scenario Navigate to a *different* screen: setup
        # never touched this one, so it must render real navigation,
        # mirroring the opening-navigate setup code exactly (including the
        # honest-gap raise when no path is declared) - otherwise this step
        # silently drops all code and page_obj is left pointing at the old
        # page class for whatever follows.
        target_screen = screens_by_id[step.screen_ref]
        if target_screen.path is None:
            return (
                [
                    f'    raise NotImplementedError('
                    f'"no path declared for screen {target_screen.id} - cannot navigate at design time")'
                ],
                step.screen_ref,
            )
        return (
            [
                f"    page_obj = {page_class_name(target_screen)}(page, base_url)",
                f"    page_obj.navigate({target_screen.path!r})",
            ],
            step.screen_ref,
        )

    if step.verb in ("enter_text", "select", "toggle"):
        prop = slugify(element_by_id[step.element_ref].descriptor.name)
        if step.verb == "enter_text":
            value_expr = resolve_data_ref(step.data, profiles_by_id)
            return [f"    page_obj.{prop}.fill({value_expr})"], current_screen_id
        if step.verb == "select":
            value_expr = resolve_data_ref(step.data, profiles_by_id)
            return [f"    page_obj.{prop}.select_option({value_expr})"], current_screen_id
        action = "check" if step.state == "checked" else "uncheck"
        return [f"    page_obj.{prop}.{action}()"], current_screen_id

    if step.verb == "activate":
        prop = slugify(element_by_id[step.element_ref].descriptor.name)
        target_id = _transition_target(current_screen_id, next_step, element_screen, transitions)
        if target_id is not None:
            target_screen = screens_by_id[target_id]
            method = f"go_to_{slugify(target_screen.name)}"
            return [f"    page_obj = page_obj.{method}()"], target_id
        return [f"    page_obj.{prop}.click()"], current_screen_id

    if step.verb == "verify":
        prop = slugify(element_by_id[step.element_ref].descriptor.name)
        renderer = _VERIFY_CONDITION_RENDERERS.get(step.condition.kind)
        if renderer is None:
            raise NotImplementedError(
                f"_render_step: verify condition kind {step.condition.kind!r} not supported"
            )
        return [f"    expect(page_obj.{prop}).{renderer(step.condition)}"], current_screen_id

    if step.verb == "call_operation":
        operation = operations_by_id[step.operation_ref]
        call_expr = _operation_call_expr(operation)
        # Keyword names must match ApiClientRenderer's own `_method_params`
        # naming exactly (slugify of the same logical_inputs strings) -
        # inputs keys are expected to reference those same logical input
        # names, so slugifying them the same way keeps the two renderers
        # in lockstep without needing to look the operation's own param
        # list up.
        kwargs = ", ".join(
            f"{slugify(name)}={resolve_data_ref(value, profiles_by_id)}"
            for name, value in _dedupe_step_inputs(step.inputs)
        )
        return [f"    response = {call_expr}({kwargs})"], current_screen_id

    if step.verb == "verify_response":
        renderer = _RESPONSE_CONDITION_RENDERERS.get(step.condition.kind)
        if renderer is None:
            raise NotImplementedError(
                f"_render_step: response condition kind {step.condition.kind!r} not supported"
            )
        return [f"    assert {renderer(step.condition)}"], current_screen_id

    raise NotImplementedError(f"_render_step: verb {step.verb!r} not yet supported")
