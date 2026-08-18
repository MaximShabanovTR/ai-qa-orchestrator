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
        _render_step(FakeStep(), None, None, {}, {}, {}, {}, {}, {})


# --- regression: activate transition decision must be per-scenario, not global ---
# The global `transitions` map built by derive_transitions() keeps only ONE
# triggering element per (from_screen, to_screen) edge, first-scenario-wins.
# Looking a step up in that map by element identity alone (the old
# _transition_target) meant any scenario activating the same element as some
# OTHER scenario's transition trigger was treated as transitioning too - even
# when this scenario's own next step stays on the same screen. The fix uses
# this scenario's own steps[i+1] to decide, consulting the aggregate map only
# to confirm a go_to_* method exists for that specific edge.

def _login_dashboard_screens():
    return [
        Screen(
            id="login", name="Login", path="/login",
            elements=[
                Element(id="submit", descriptor=TargetDescriptor(role=ElementRole.BUTTON, name="Submit")),
                Element(id="error_message", descriptor=TargetDescriptor(role=ElementRole.MESSAGE, name="Error Message")),
            ],
        ),
        Screen(id="dashboard", name="Dashboard", path="/dashboard", elements=[]),
    ]


def _happy_and_invalid_login_scenarios():
    happy = Scenario(
        id="s-happy", test_case_id="TC-HAPPY",
        steps=[
            Navigate(screen_ref="login"),
            Activate(element_ref="submit"),
            Navigate(screen_ref="dashboard"),
        ],
    )
    invalid = Scenario(
        id="s-invalid", test_case_id="TC-INVALID",
        steps=[
            Navigate(screen_ref="login"),
            Activate(element_ref="submit"),
            Verify(element_ref="error_message", condition=Visible()),
        ],
    )
    return happy, invalid


@pytest.mark.unit
def test_activate_transition_decision_is_per_scenario_not_global():
    screens = _login_dashboard_screens()
    happy, invalid = _happy_and_invalid_login_scenarios()

    content = scenarios_content([happy, invalid], screens)
    compile(content, "<test>", "exec")

    happy_func = content.split("def test_tc_happy")[1].split("def test_tc_invalid")[0]
    invalid_func = content.split("def test_tc_invalid", 1)[1]

    # Happy path: activate(submit) is followed by Navigate(dashboard) in ITS
    # OWN steps -> a real transition, so it must reuse the page object method.
    assert "page_obj = page_obj.go_to_dashboard()" in happy_func
    assert "page_obj.submit.click()" not in happy_func

    # Invalid-credentials: activate(submit) is followed by Verify(error_message)
    # - same screen - in ITS OWN steps, even though the *other* scenario
    # registered "submit" as the login -> dashboard trigger in the aggregate
    # map. Must render a plain click and resolve the following Verify against
    # LoginPage (error_message belongs to login), not DashboardPage.
    assert "page_obj.submit.click()" in invalid_func
    assert "go_to_dashboard" not in invalid_func
    assert "expect(page_obj.error_message).to_be_visible()" in invalid_func


@pytest.mark.unit
def test_activate_transition_decision_executes_correctly_against_fakes(tmp_path):
    """Full semantic proof, not just syntax: render real page objects +
    tests for the happy/invalid-login pair above, write them to a real
    temp package tree, import with real Python import machinery, and run
    both generated test functions against fakes. Pre-fix, the invalid
    scenario's page_obj would have been wrongly reassigned to DashboardPage
    (no `error_message` property) and would AttributeError; post-fix it
    stays on LoginPage and resolves correctly.
    """
    import importlib.util
    import sys

    from renderer.page_object_renderer import render_page_objects

    screens = _login_dashboard_screens()
    happy, invalid = _happy_and_invalid_login_scenarios()
    conventions = RendererConventions(pages_dir="fix1_pages", tests_dir="fix1_tests")

    page_artifacts = render_page_objects(screens, [happy, invalid], conventions)
    test_artifacts = render_tests([happy, invalid], screens, [], [], conventions)

    for artifact in [*page_artifacts, *test_artifacts]:
        path = tmp_path / artifact.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.content, encoding="utf-8")

    sys.path.insert(0, str(tmp_path))
    try:
        spec = importlib.util.spec_from_file_location(
            "fix1_test_scenarios_mod", tmp_path / "fix1_tests" / "test_scenarios.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        # Real playwright's expect() expects real Locators; swap in a fake
        # that just records which locator it was called with, so we can
        # prove *which page object's property* fed into it without needing
        # a real browser.
        expect_calls: list = []

        class FakeExpectation:
            def __init__(self, locator):
                self.locator = locator

            def to_be_visible(self):
                expect_calls.append(self.locator)

        module.expect = lambda locator: FakeExpectation(locator)

        class FakeLocator:
            def __init__(self, tag):
                self.tag = tag
                self.clicked = False

            def click(self):
                self.clicked = True

        class FakePage:
            def __init__(self):
                self.goto_calls: list = []
                self.made_locators: dict = {}

            def goto(self, url):
                self.goto_calls.append(url)

            def get_by_role(self, role, name=None):
                loc = FakeLocator(("role", role, name))
                self.made_locators[("role", role, name)] = loc
                return loc

            def get_by_text(self, text):
                loc = FakeLocator(("text", text))
                self.made_locators[("text", text)] = loc
                return loc

        happy_page = FakePage()
        module.test_tc_happy(happy_page, "http://x")
        assert happy_page.made_locators[("role", "button", "Submit")].clicked
        assert happy_page.goto_calls == ["http://x/login"]

        invalid_page = FakePage()
        module.test_tc_invalid(invalid_page, "http://x")
        assert invalid_page.made_locators[("role", "button", "Submit")].clicked
        error_locator = invalid_page.made_locators[("text", "Error Message")]
        assert expect_calls == [error_locator]
    finally:
        sys.path.remove(str(tmp_path))
        for name in list(sys.modules):
            if name.startswith("fix1_pages") or name == "fix1_test_scenarios_mod":
                del sys.modules[name]


# --- regression: uses_profiles must also scan call_operation inputs ---

@pytest.mark.unit
def test_uses_profiles_detected_from_call_operation_inputs_only():
    operations = [
        Operation(
            id="op1", intent="Submit Payment", logical_inputs=["Order Id"],
            expected_outcome_class="success",
            binding=OperationBinding(method="POST", path="/api/payments"),
        )
    ]
    profiles = [
        DataProfile(id="p1", name="Order Id", category=DataCategory.TEXT, literal_value="ORD-1"),
    ]
    scenario = Scenario(
        id="s1", test_case_id="TC-1",
        steps=[CallOperation(operation_ref="op1", inputs={"Order Id": ProfileRef(profile_id="p1")})],
    )
    content = scenarios_content([scenario], [], operations, profiles)
    assert "from data import profiles" in content
    ast.parse(content)
    compile(content, "<test>", "exec")


# --- regression: call_operation kwargs must dedupe colliding slugified names ---

@pytest.mark.unit
def test_call_operation_dedupes_colliding_kwargs():
    operations = [
        Operation(
            id="op1", intent="Submit Payment", logical_inputs=["Order ID"],
            expected_outcome_class="success", resource="payments",
            binding=OperationBinding(method="POST", path="/api/payments"),
        )
    ]
    scenario = Scenario(
        id="s1", test_case_id="TC-1",
        steps=[
            CallOperation(
                operation_ref="op1",
                inputs={
                    "Order ID": LiteralValue(value="ORD-1"),
                    "order-id": LiteralValue(value="ORD-2"),
                },
            )
        ],
    )
    content = scenarios_content([scenario], [], operations)
    assert content.count("order_id=") == 1
    assert "order_id='ORD-1'" in content
    ast.parse(content)
    compile(content, "<test>", "exec")


# --- regression: mid-scenario Navigate must render real navigation ---

@pytest.mark.unit
def test_mid_scenario_navigate_renders_real_navigation_and_reassigns_page_obj():
    screens = [
        Screen(id="a", name="Screen A", path="/a", elements=[
            Element(id="field", descriptor=TargetDescriptor(role=ElementRole.TEXTBOX, name="Field")),
        ]),
        Screen(id="b", name="Screen B", path="/b", elements=[
            Element(id="banner", descriptor=TargetDescriptor(role=ElementRole.MESSAGE, name="Banner")),
        ]),
    ]
    scenario = Scenario(
        id="s1", test_case_id="TC-1",
        steps=[
            Navigate(screen_ref="a"),
            EnterText(element_ref="field", data=LiteralValue(value="x")),
            Navigate(screen_ref="b"),
            Verify(element_ref="banner", condition=Visible()),
        ],
    )
    content = scenarios_content([scenario], screens)

    assert "from pages.a import ScreenAPage" in content
    assert "from pages.b import ScreenBPage" in content
    assert "page_obj = ScreenBPage(page, base_url)" in content
    assert "page_obj.navigate('/b')" in content
    assert "expect(page_obj.banner).to_be_visible()" in content
    ast.parse(content)
    compile(content, "<test>", "exec")


@pytest.mark.unit
def test_mid_scenario_navigate_executes_and_resolves_against_new_screen(tmp_path):
    """Semantic proof: if page_obj were never reassigned (the pre-fix
    behavior), `page_obj.banner` would AttributeError against ScreenAPage,
    which has no `banner` property - only ScreenBPage does.
    """
    import importlib.util
    import sys

    from renderer.page_object_renderer import render_page_objects

    screens = [
        Screen(id="a", name="Screen A", path="/a", elements=[
            Element(id="field", descriptor=TargetDescriptor(role=ElementRole.TEXTBOX, name="Field")),
        ]),
        Screen(id="b", name="Screen B", path="/b", elements=[
            Element(id="banner", descriptor=TargetDescriptor(role=ElementRole.MESSAGE, name="Banner")),
        ]),
    ]
    scenario = Scenario(
        id="s1", test_case_id="TC-1",
        steps=[
            Navigate(screen_ref="a"),
            EnterText(element_ref="field", data=LiteralValue(value="x")),
            Navigate(screen_ref="b"),
            Verify(element_ref="banner", condition=Visible()),
        ],
    )
    conventions = RendererConventions(pages_dir="fix4_pages", tests_dir="fix4_tests")

    page_artifacts = render_page_objects(screens, [scenario], conventions)
    test_artifacts = render_tests([scenario], screens, [], [], conventions)

    for artifact in [*page_artifacts, *test_artifacts]:
        path = tmp_path / artifact.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.content, encoding="utf-8")

    sys.path.insert(0, str(tmp_path))
    try:
        spec = importlib.util.spec_from_file_location(
            "fix4_test_scenarios_mod", tmp_path / "fix4_tests" / "test_scenarios.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        expect_calls: list = []

        class FakeExpectation:
            def __init__(self, locator):
                self.locator = locator

            def to_be_visible(self):
                expect_calls.append(self.locator)

        module.expect = lambda locator: FakeExpectation(locator)

        class FakeLocator:
            def __init__(self, tag):
                self.tag = tag
                self.filled = None

            def fill(self, value):
                self.filled = value

        class FakePage:
            def __init__(self):
                self.goto_calls: list = []
                self.made_locators: dict = {}

            def goto(self, url):
                self.goto_calls.append(url)

            def get_by_role(self, role, name=None):
                loc = FakeLocator(("role", role, name))
                self.made_locators[("role", role, name)] = loc
                return loc

            def get_by_text(self, text):
                loc = FakeLocator(("text", text))
                self.made_locators[("text", text)] = loc
                return loc

        fake_page = FakePage()
        module.test_tc_1(fake_page, "http://x")

        assert fake_page.goto_calls == ["http://x/a", "http://x/b"]
        banner_locator = fake_page.made_locators[("text", "Banner")]
        assert expect_calls == [banner_locator]
    finally:
        sys.path.remove(str(tmp_path))
        for name in list(sys.modules):
            if name.startswith("fix4_pages") or name == "fix4_test_scenarios_mod":
                del sys.modules[name]


# --- regression: import statements must slugify screen.id ---

@pytest.mark.unit
def test_import_statement_slugifies_hyphenated_screen_id():
    screens = [Screen(id="SCR-001", name="Screen", path="/scr", elements=[])]
    scenario = Scenario(id="s1", test_case_id="TC-1", steps=[Navigate(screen_ref="SCR-001")])
    content = scenarios_content([scenario], screens)
    assert "from pages.scr_001 import ScreenPage" in content
    assert "pages.SCR-001" not in content
    ast.parse(content)
    compile(content, "<test>", "exec")
