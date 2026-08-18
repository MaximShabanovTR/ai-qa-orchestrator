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
    uses_profiles = False
    uses_verify = False
    uses_api = False
    for scenario in scenarios:
        for step in scenario.steps:
            if step.verb in ("enter_text", "select") and step.data.kind == "profile_ref":
                uses_profiles = True
            if step.verb == "verify":
                uses_verify = True
            if step.verb in _API_STEP_VERBS:
                uses_api = True
            sid = step_screen_id(step, element_screen)
            if sid is not None and scenario.id not in start_screens:
                start_screens[scenario.id] = sid

    used_screen_ids = sorted({sid for sid in start_screens.values()})
    lines = ["import pytest", ""]
    if uses_verify:
        lines.append("from playwright.sync_api import expect")
    if uses_profiles:
        lines.append(f"from {conventions.data_dir} import profiles")
    if uses_api:
        lines.append(f"from {conventions.api_dir}.client import ApiClient")
    for screen_id in used_screen_ids:
        screen = screens_by_id[screen_id]
        lines.append(
            f"from {conventions.pages_dir}.{screen.id} import {page_class_name(screen)}"
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
    element_id: str,
    transitions: dict[str, dict[str, str]],
) -> str | None:
    """If activating `element_id` from `current_screen_id` is a known
    transition (per PageObjectRenderer's derive_transitions), return the
    target screen id. Otherwise None - a plain click, no screen change.
    """
    if current_screen_id is None:
        return None
    for to_screen_id, triggering_element in transitions.get(current_screen_id, {}).items():
        if triggering_element == element_id:
            return to_screen_id
    return None


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

    for step in scenario.steps:
        step_lines, current_screen_id = _render_step(
            step,
            current_screen_id,
            screens_by_id,
            element_by_id,
            profiles_by_id,
            operations_by_id,
            transitions,
        )
        lines.extend(step_lines)

    if len(lines) == body_start:
        lines.append("    pass")

    lines.append("")
    lines.append("")
    return lines


def _render_step(
    step,
    current_screen_id: str | None,
    screens_by_id: dict[str, Screen],
    element_by_id: dict[str, Element],
    profiles_by_id: dict[str, DataProfile],
    operations_by_id: dict[str, Operation],
    transitions: dict[str, dict[str, str]],
) -> tuple[list[str], str | None]:
    if step.verb == "navigate":
        return [], step.screen_ref

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
        target_id = _transition_target(current_screen_id, step.element_ref, transitions)
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
            for name, value in step.inputs.items()
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
