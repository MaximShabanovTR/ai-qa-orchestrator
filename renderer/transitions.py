from models.automation import Scenario, Screen

_SCREEN_RESOLVING_VERBS = {"enter_text", "activate", "select", "toggle", "verify"}


def element_screen_map(screens: list[Screen]) -> dict[str, str]:
    return {
        element.id: screen.id for screen in screens for element in screen.elements
    }


def step_screen_id(step, element_screen: dict[str, str]) -> str | None:
    if step.verb == "navigate":
        return step.screen_ref
    if step.verb in _SCREEN_RESOLVING_VERBS:
        return element_screen.get(step.element_ref)
    return None


def derive_transitions(
    screens: list[Screen], scenarios: list[Scenario]
) -> dict[str, dict[str, str]]:
    """from_screen_id -> {to_screen_id: id of the element whose activation triggers it}.

    Only `activate` steps are treated as transition triggers - clicking is
    the one action that canonically means "this might navigate somewhere".
    Derived purely from element-to-screen ownership (a declared fact),
    never from step text/label similarity. If a scenario shows more than
    one element triggering the same from -> to transition, the first one
    encountered wins - deterministic given scenario order, not silently
    arbitrary.

    Shared between PageObjectRenderer (which generates the go_to_* methods
    this describes) and TestRenderer (which needs the same lookahead to
    know whether an `activate` step should render as a transition call or
    a plain click) - both renderers must agree on which steps are
    transitions, so this lives in one place, not two.
    """
    element_screen = element_screen_map(screens)
    transitions: dict[str, dict[str, str]] = {}
    for scenario in scenarios:
        steps = scenario.steps
        for i in range(len(steps) - 1):
            step = steps[i]
            if step.verb != "activate":
                continue
            from_screen = element_screen.get(step.element_ref)
            if from_screen is None:
                continue
            to_screen = step_screen_id(steps[i + 1], element_screen)
            if to_screen is None or to_screen == from_screen:
                continue
            transitions.setdefault(from_screen, {}).setdefault(
                to_screen, step.element_ref
            )
    return transitions
