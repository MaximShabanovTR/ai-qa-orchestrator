import pytest

from models.automation import (
    Activate,
    CallOperation,
    Element,
    ElementRole,
    EnterText,
    LiteralValue,
    Navigate,
    Scenario,
    Screen,
    Select,
    TargetDescriptor,
    Toggle,
    Unsupported,
    Verify,
    Visible,
)
from renderer.transitions import derive_transitions, element_screen_map, step_screen_id


def _screen(screen_id, *element_ids):
    return Screen(
        id=screen_id,
        name=screen_id.capitalize(),
        elements=[
            Element(id=e, descriptor=TargetDescriptor(role=ElementRole.BUTTON, name=e))
            for e in element_ids
        ],
    )


def _scenario(steps):
    return Scenario(id="s1", test_case_id="TC-1", steps=steps)


# --- element_screen_map ---

@pytest.mark.unit
def test_element_screen_map_maps_each_element_to_its_owning_screen():
    screens = [_screen("page1", "e1", "e2"), _screen("page2", "e3")]
    result = element_screen_map(screens)
    assert result == {"e1": "page1", "e2": "page1", "e3": "page2"}


@pytest.mark.unit
def test_element_screen_map_empty_screens_returns_empty_dict():
    assert element_screen_map([]) == {}


@pytest.mark.unit
def test_element_screen_map_screen_with_no_elements_contributes_nothing():
    screens = [Screen(id="empty", name="Empty", elements=[])]
    assert element_screen_map(screens) == {}


# --- step_screen_id ---

@pytest.mark.unit
def test_step_screen_id_navigate_returns_screen_ref_directly():
    step = Navigate(screen_ref="target")
    # element_screen deliberately doesn't contain "target" - navigate must
    # not consult the map at all.
    assert step_screen_id(step, {}) == "target"


@pytest.mark.unit
@pytest.mark.parametrize(
    "step",
    [
        EnterText(element_ref="e1", data=LiteralValue(value="x")),
        Activate(element_ref="e1"),
        Select(element_ref="e1", data=LiteralValue(value="x")),
        Toggle(element_ref="e1", state="checked"),
        Verify(element_ref="e1", condition=Visible()),
    ],
    ids=["enter_text", "activate", "select", "toggle", "verify"],
)
def test_step_screen_id_resolves_via_element_ownership_for_every_resolving_verb(step):
    element_screen = {"e1": "owning_screen"}
    assert step_screen_id(step, element_screen) == "owning_screen"


@pytest.mark.unit
@pytest.mark.parametrize(
    "step",
    [
        CallOperation(operation_ref="op1", inputs={}),
        Unsupported(description="freeform"),
    ],
    ids=["call_operation", "unsupported"],
)
def test_step_screen_id_returns_none_for_non_resolving_verbs(step):
    assert step_screen_id(step, {"e1": "owning_screen"}) is None


@pytest.mark.unit
def test_step_screen_id_returns_none_when_element_not_in_map():
    step = Activate(element_ref="unknown_element")
    assert step_screen_id(step, {}) is None


# --- derive_transitions ---

@pytest.mark.unit
def test_derive_transitions_detects_activate_then_navigate_to_new_screen():
    screens = [_screen("page1", "link"), _screen("page2")]
    scenario = _scenario(
        [Navigate(screen_ref="page1"), Activate(element_ref="link"), Navigate(screen_ref="page2")]
    )
    result = derive_transitions(screens, [scenario])
    assert result == {"page1": {"page2": "link"}}


@pytest.mark.unit
def test_derive_transitions_next_step_can_be_any_screen_resolving_verb_not_just_navigate():
    # Activate followed by an enter_text step whose element is owned by a
    # different screen is still evidence of a transition - the lookahead
    # isn't limited to `navigate` steps.
    screens = [
        _screen("page1", "link"),
        Screen(
            id="page2",
            name="Page2",
            elements=[Element(id="field", descriptor=TargetDescriptor(role=ElementRole.TEXTBOX, name="Field"))],
        ),
    ]
    scenario = _scenario(
        [
            Navigate(screen_ref="page1"),
            Activate(element_ref="link"),
            EnterText(element_ref="field", data=LiteralValue(value="x")),
        ]
    )
    result = derive_transitions(screens, [scenario])
    assert result == {"page1": {"page2": "link"}}


@pytest.mark.unit
def test_derive_transitions_no_transition_when_activate_is_last_step():
    screens = [_screen("page1", "link")]
    scenario = _scenario([Navigate(screen_ref="page1"), Activate(element_ref="link")])
    assert derive_transitions(screens, [scenario]) == {}


@pytest.mark.unit
def test_derive_transitions_no_transition_when_next_step_resolves_to_same_screen():
    screens = [_screen("page1", "link", "other")]
    scenario = _scenario(
        [Navigate(screen_ref="page1"), Activate(element_ref="link"), Verify(element_ref="other", condition=Visible())]
    )
    assert derive_transitions(screens, [scenario]) == {}


@pytest.mark.unit
def test_derive_transitions_skips_when_activating_element_not_owned_by_any_screen():
    screens = [Screen(id="page2", name="Page2", elements=[])]
    scenario = _scenario([Activate(element_ref="orphan"), Navigate(screen_ref="page2")])
    assert derive_transitions(screens, [scenario]) == {}


@pytest.mark.unit
def test_derive_transitions_skips_when_lookahead_target_screen_unresolvable():
    # next step is call_operation - step_screen_id returns None for it, so
    # no transition can be inferred even though an activate happened.
    screens = [_screen("page1", "link")]
    scenario = _scenario(
        [Navigate(screen_ref="page1"), Activate(element_ref="link"), CallOperation(operation_ref="op1", inputs={})]
    )
    assert derive_transitions(screens, [scenario]) == {}


@pytest.mark.unit
def test_derive_transitions_first_element_wins_across_scenarios():
    screens = [_screen("page1", "link_a", "link_b"), _screen("page2")]
    scenario_a = _scenario(
        [Navigate(screen_ref="page1"), Activate(element_ref="link_a"), Navigate(screen_ref="page2")]
    )
    scenario_b = _scenario(
        [Navigate(screen_ref="page1"), Activate(element_ref="link_b"), Navigate(screen_ref="page2")]
    )
    result = derive_transitions(screens, [scenario_a, scenario_b])
    # scenario_a is listed first, so link_a's transition claims page1->page2;
    # scenario_b's link_b, discovering the same from->to pair, is dropped.
    assert result == {"page1": {"page2": "link_a"}}


@pytest.mark.unit
def test_derive_transitions_supports_branching_to_multiple_targets():
    screens = [_screen("page1", "link_a", "link_b"), _screen("page2"), _screen("page3")]
    scenario_a = _scenario(
        [Navigate(screen_ref="page1"), Activate(element_ref="link_a"), Navigate(screen_ref="page2")]
    )
    scenario_b = _scenario(
        [Navigate(screen_ref="page1"), Activate(element_ref="link_b"), Navigate(screen_ref="page3")]
    )
    result = derive_transitions(screens, [scenario_a, scenario_b])
    assert result == {"page1": {"page2": "link_a", "page3": "link_b"}}


@pytest.mark.unit
def test_derive_transitions_empty_scenarios_and_screens_returns_empty_dict():
    assert derive_transitions([], []) == {}


@pytest.mark.unit
def test_derive_transitions_single_step_scenario_does_not_crash():
    screens = [_screen("page1", "link")]
    scenario = _scenario([Activate(element_ref="link")])
    assert derive_transitions(screens, [scenario]) == {}
