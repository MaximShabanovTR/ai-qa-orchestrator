import ast

import pytest

from models.automation import (
    Activate,
    CallOperation,
    Count,
    ContainsText,
    DataProfile,
    DataCategory,
    Disabled,
    Element,
    ElementRole,
    Enabled,
    EnterText,
    HasValue,
    HeaderEquals,
    LiteralValue,
    Navigate,
    Operation,
    OperationBinding,
    ProfileRef,
    Scenario,
    Screen,
    Select,
    StatusClass,
    TargetDescriptor,
    Toggle,
    Unsupported,
    Verify,
    VerifyResponse,
    Visible,
    BodyContains,
)
from renderer.models import RendererConventions
from renderer.test_renderer import render_tests


def scenarios_content(scenarios, screens=(), operations=(), profiles=()) -> str:
    artifacts = render_tests(
        list(scenarios), list(screens), list(operations), list(profiles), RendererConventions()
    )
    return next(a.content for a in artifacts if a.path.endswith("test_scenarios.py"))


# --- render_tests: top-level shape ---

@pytest.mark.unit
def test_render_tests_returns_empty_for_no_scenarios():
    assert render_tests([], [], [], [], RendererConventions()) == []


@pytest.mark.unit
def test_render_tests_emits_tests_init():
    scenario = Scenario(id="s1", test_case_id="TC-1", steps=[], obstacles=[])
    artifacts = render_tests([scenario], [], [], [], RendererConventions())
    paths = [a.path for a in artifacts]
    assert "tests/__init__.py" in paths
    assert "tests/test_scenarios.py" in paths


@pytest.mark.unit
def test_generated_file_always_parses():
    screens = [
        Screen(
            id="login",
            name="Login",
            path="/login",
            elements=[
                Element(id="e1", descriptor=TargetDescriptor(role=ElementRole.TEXTBOX, name="Email")),
                Element(id="e2", descriptor=TargetDescriptor(role=ElementRole.BUTTON, name="Submit")),
            ],
        ),
    ]
    scenario = Scenario(
        id="s1",
        test_case_id="TC-1",
        steps=[
            Navigate(screen_ref="login"),
            EnterText(element_ref="e1", data=LiteralValue(value="a@b.com")),
            Activate(element_ref="e2"),
        ],
    )
    content = scenarios_content([scenario], screens)
    ast.parse(content)


# --- conditional imports ---

@pytest.mark.unit
def test_no_optional_imports_when_unused():
    scenario = Scenario(id="s1", test_case_id="TC-1", steps=[])
    content = scenarios_content([scenario])
    assert "from playwright.sync_api import expect" not in content
    assert "import profiles" not in content
    assert "import ApiClient" not in content


@pytest.mark.unit
def test_verify_import_only_when_used():
    screens = [Screen(id="scr", name="Screen", elements=[
        Element(id="e1", descriptor=TargetDescriptor(role=ElementRole.MESSAGE, name="Banner")),
    ])]
    scenario = Scenario(
        id="s1",
        test_case_id="TC-1",
        steps=[Navigate(screen_ref="scr"), Verify(element_ref="e1", condition=Visible())],
    )
    content = scenarios_content([scenario], screens)
    assert "from playwright.sync_api import expect" in content


@pytest.mark.unit
def test_api_import_only_when_used():
    operations = [
        Operation(
            id="op1", intent="Ping", expected_outcome_class="success",
            binding=OperationBinding(method="GET", path="/ping"),
        )
    ]
    scenario = Scenario(id="s1", test_case_id="TC-1", steps=[CallOperation(operation_ref="op1", inputs={})])
    content = scenarios_content([scenario], [], operations)
    assert "from api.client import ApiClient" in content
    assert "api = ApiClient()" in content


# --- suitability / skip routing ---

@pytest.mark.unit
def test_manual_scenario_renders_skip_with_obstacle_reason():
    from models.automation import ObstacleType

    scenario = Scenario(
        id="s1", test_case_id="TC-1", steps=[], obstacles=[ObstacleType.HARDWARE_INTERACTION]
    )
    content = scenarios_content([scenario])
    assert '@pytest.mark.skip(reason="Manual: hardware_interaction")' in content
    assert "def test_tc_1(page, base_url):" in content
    ast.parse(content)


@pytest.mark.unit
def test_automated_with_prereqs_renders_prereq_comment():
    from models.automation import ObstacleType

    scenario = Scenario(
        id="s1", test_case_id="TC-1", steps=[], obstacles=[ObstacleType.CAPTCHA]
    )
    content = scenarios_content([scenario])
    assert "# Prerequisites: captcha_bypass_token" in content
    assert "@pytest.mark.skip" not in content


@pytest.mark.unit
def test_unsupported_step_skips_whole_scenario_and_preserves_description():
    scenario = Scenario(
        id="s1",
        test_case_id="TC-1",
        steps=[Unsupported(description='Drag "Item" via canvas')],
    )
    content = scenarios_content([scenario])
    assert "@pytest.mark.skip" in content
    assert 'Drag "Item" via canvas' in content
    ast.parse(content)


@pytest.mark.unit
def test_unsupported_takes_precedence_over_manual():
    from models.automation import ObstacleType

    scenario = Scenario(
        id="s1",
        test_case_id="TC-1",
        steps=[Unsupported(description="freeform canvas drawing")],
        obstacles=[ObstacleType.HARDWARE_INTERACTION],
    )
    content = scenarios_content([scenario])
    assert "Unsupported: freeform canvas drawing" in content
    assert "Manual:" not in content


@pytest.mark.unit
def test_scenario_with_no_renderable_body_gets_pass():
    scenario = Scenario(id="s1", test_case_id="TC-1", steps=[])
    content = scenarios_content([scenario])
    assert "def test_tc_1(page, base_url):\n    pass" in content
    ast.parse(content)


# --- navigate / screen path ---

@pytest.mark.unit
def test_missing_screen_path_renders_honest_gap():
    screens = [Screen(id="scr", name="Screen", elements=[])]
    scenario = Scenario(id="s1", test_case_id="TC-1", steps=[Navigate(screen_ref="scr")])
    content = scenarios_content([scenario], screens)
    assert "raise NotImplementedError" in content
    assert "no path declared for screen scr" in content
    ast.parse(content)


@pytest.mark.unit
def test_screen_with_path_renders_navigate_call():
    screens = [Screen(id="scr", name="Screen", path="/scr", elements=[])]
    scenario = Scenario(id="s1", test_case_id="TC-1", steps=[Navigate(screen_ref="scr")])
    content = scenarios_content([scenario], screens)
    assert "page_obj.navigate('/scr')" in content


# --- enter_text / select / toggle ---

@pytest.mark.unit
def test_enter_text_resolves_literal_value():
    screens = [Screen(id="scr", name="Screen", path="/scr", elements=[
        Element(id="e1", descriptor=TargetDescriptor(role=ElementRole.TEXTBOX, name="Email")),
    ])]
    scenario = Scenario(
        id="s1", test_case_id="TC-1",
        steps=[Navigate(screen_ref="scr"), EnterText(element_ref="e1", data=LiteralValue(value="x@y.com"))],
    )
    content = scenarios_content([scenario], screens)
    assert "page_obj.email.fill('x@y.com')" in content


@pytest.mark.unit
def test_enter_text_resolves_profile_ref_literal_constant():
    screens = [Screen(id="scr", name="Screen", path="/scr", elements=[
        Element(id="e1", descriptor=TargetDescriptor(role=ElementRole.TEXTBOX, name="Email")),
    ])]
    profiles = [DataProfile(id="p1", name="Valid Email", category=DataCategory.EMAIL, literal_value="a@b.com")]
    scenario = Scenario(
        id="s1", test_case_id="TC-1",
        steps=[Navigate(screen_ref="scr"), EnterText(element_ref="e1", data=ProfileRef(profile_id="p1"))],
    )
    content = scenarios_content([scenario], screens, profiles=profiles)
    assert "page_obj.email.fill(profiles.VALID_EMAIL)" in content


@pytest.mark.unit
def test_enter_text_resolves_profile_ref_generator():
    screens = [Screen(id="scr", name="Screen", path="/scr", elements=[
        Element(id="e1", descriptor=TargetDescriptor(role=ElementRole.TEXTBOX, name="Age")),
    ])]
    profiles = [DataProfile(id="p1", name="Age", category=DataCategory.NUMBER)]
    scenario = Scenario(
        id="s1", test_case_id="TC-1",
        steps=[Navigate(screen_ref="scr"), EnterText(element_ref="e1", data=ProfileRef(profile_id="p1"))],
    )
    content = scenarios_content([scenario], screens, profiles=profiles)
    assert "page_obj.age.fill(profiles.generate_age())" in content


@pytest.mark.unit
def test_select_renders_select_option():
    screens = [Screen(id="scr", name="Screen", path="/scr", elements=[
        Element(id="e1", descriptor=TargetDescriptor(role=ElementRole.COMBOBOX, name="Country")),
    ])]
    scenario = Scenario(
        id="s1", test_case_id="TC-1",
        steps=[Navigate(screen_ref="scr"), Select(element_ref="e1", data=LiteralValue(value="US"))],
    )
    content = scenarios_content([scenario], screens)
    assert "page_obj.country.select_option('US')" in content


@pytest.mark.unit
@pytest.mark.parametrize("state,expected", [("checked", "check"), ("unchecked", "uncheck")])
def test_toggle_renders_check_or_uncheck(state, expected):
    screens = [Screen(id="scr", name="Screen", path="/scr", elements=[
        Element(id="e1", descriptor=TargetDescriptor(role=ElementRole.CHECKBOX, name="Remember")),
    ])]
    scenario = Scenario(
        id="s1", test_case_id="TC-1",
        steps=[Navigate(screen_ref="scr"), Toggle(element_ref="e1", state=state)],
    )
    content = scenarios_content([scenario], screens)
    assert f"page_obj.remember.{expected}()" in content


# --- activate: plain click vs. transition ---

@pytest.mark.unit
def test_activate_plain_click_same_screen():
    screens = [Screen(id="scr", name="Screen", path="/scr", elements=[
        Element(id="e1", descriptor=TargetDescriptor(role=ElementRole.BUTTON, name="Save")),
    ])]
    scenario = Scenario(
        id="s1", test_case_id="TC-1",
        steps=[Navigate(screen_ref="scr"), Activate(element_ref="e1")],
    )
    content = scenarios_content([scenario], screens)
    assert "page_obj.save.click()" in content
    assert "go_to_" not in content


@pytest.mark.unit
def test_activate_transition_reuses_page_object_method():
    screens = [
        Screen(id="page1", name="Page 1", path="/p1", elements=[
            Element(id="link", descriptor=TargetDescriptor(role=ElementRole.LINK, name="Go To Page 2")),
        ]),
        Screen(id="page2", name="Page 2", elements=[]),
    ]
    scenario = Scenario(
        id="s1", test_case_id="TC-1",
        steps=[
            Navigate(screen_ref="page1"),
            Activate(element_ref="link"),
            Navigate(screen_ref="page2"),
        ],
    )
    content = scenarios_content([scenario], screens)
    assert "page_obj = page_obj.go_to_page_2()" in content
    assert "page_obj.go_to_page_2_link.click()" not in content


# --- verify: exhaustive over VerifyCondition kinds ---

@pytest.mark.unit
@pytest.mark.parametrize(
    "condition,expected_tail",
    [
        (Visible(), "to_be_visible()"),
        (ContainsText(text="Welcome"), "to_contain_text('Welcome')"),
        (HasValue(value="42"), "to_have_value('42')"),
        (Enabled(), "to_be_enabled()"),
        (Disabled(), "to_be_disabled()"),
        (Count(count=3), "to_have_count(3)"),
    ],
)
def test_verify_covers_every_condition_kind(condition, expected_tail):
    screens = [Screen(id="scr", name="Screen", path="/scr", elements=[
        Element(id="e1", descriptor=TargetDescriptor(role=ElementRole.MESSAGE, name="Banner")),
    ])]
    scenario = Scenario(
        id="s1", test_case_id="TC-1",
        steps=[Navigate(screen_ref="scr"), Verify(element_ref="e1", condition=condition)],
    )
    content = scenarios_content([scenario], screens)
    assert f"expect(page_obj.banner).{expected_tail}" in content


# --- call_operation / verify_response ---

@pytest.mark.unit
def test_call_operation_ungrouped():
    operations = [
        Operation(
            id="op1", intent="Ping Health", expected_outcome_class="success",
            binding=OperationBinding(method="GET", path="/health"),
        )
    ]
    scenario = Scenario(id="s1", test_case_id="TC-1", steps=[CallOperation(operation_ref="op1", inputs={})])
    content = scenarios_content([scenario], [], operations)
    assert "response = api.ping_health()" in content


@pytest.mark.unit
def test_call_operation_resource_grouped_with_inputs():
    operations = [
        Operation(
            id="op1", intent="Submit Payment", logical_inputs=["order_id"],
            expected_outcome_class="success", resource="payments",
            binding=OperationBinding(method="POST", path="/api/payments"),
        )
    ]
    scenario = Scenario(
        id="s1", test_case_id="TC-1",
        steps=[CallOperation(operation_ref="op1", inputs={"order_id": LiteralValue(value="ORD-1")})],
    )
    content = scenarios_content([scenario], [], operations)
    assert "response = api.payments.submit_payment(order_id='ORD-1')" in content


@pytest.mark.unit
@pytest.mark.parametrize(
    "condition,expected",
    [
        (StatusClass(status_class="success"), "response.status_code // 100 == 2"),
        (StatusClass(status_class="client_error"), "response.status_code // 100 == 4"),
        (BodyContains(field="status", value="ok"), "response.json()['status'] == 'ok'"),
        (HeaderEquals(header="Content-Type", value="application/json"),
         "response.headers['Content-Type'] == 'application/json'"),
    ],
)
def test_verify_response_covers_every_condition_kind(condition, expected):
    operations = [
        Operation(
            id="op1", intent="Ping", expected_outcome_class="success",
            binding=OperationBinding(method="GET", path="/ping"),
        )
    ]
    scenario = Scenario(
        id="s1", test_case_id="TC-1",
        steps=[
            CallOperation(operation_ref="op1", inputs={}),
            VerifyResponse(operation_ref="op1", condition=condition),
        ],
    )
    content = scenarios_content([scenario], [], operations)
    assert f"assert {expected}" in content


# --- unknown verb: exhaustiveness guard ---

@pytest.mark.unit
def test_render_step_raises_on_unhandled_verb():
    from renderer.test_renderer import _render_step

    class FakeStep:
        verb = "teleport"

    with pytest.raises(NotImplementedError, match="teleport"):
        _render_step(FakeStep(), None, {}, {}, {}, {}, {})
